"""Dependency-free local adapter for real structured LLM calls.

The browser may submit a key to localhost. The key stays in this Python
process, is never returned, persisted, or logged, and disappears on shutdown.
DeepSeek Chat Completions is the default transport; OpenAI Responses and other
OpenAI-compatible Chat Completions endpoints remain configurable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable


DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 45
MAX_TEXT_CHARS = 48_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class LiveAgentError(Exception):
    def __init__(self, code: str, message: str, recovery: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recovery = recovery
        self.details = details or {}

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "recovery": self.recovery,
            "details": self.details,
        }


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: int
    source: str

    @property
    def provider(self) -> str:
        return urllib.parse.urlparse(self.base_url).netloc or "configured-provider"


_LOCK = threading.RLock()
_SESSION: dict[str, Any] = {}


def _clean_base_url(value: str) -> str:
    url = value.strip() or DEFAULT_BASE_URL
    if not url.startswith(("http://", "https://")):
        raise LiveAgentError("API_CONFIG_INVALID", "API 地址必须以 http:// 或 https:// 开头。", "检查兼容端点后重新保存。")
    url = url.rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.lower() == "api.deepseek.com" and parsed.path in {"", "/v1"}:
        url += "/chat/completions"
    if url.endswith("/v1"):
        url += "/responses"
    return url


def configure_session(payload: dict[str, Any]) -> dict[str, Any]:
    key = str(payload.get("api_key") or "").strip()
    if not key:
        raise LiveAgentError("API_KEY_REQUIRED", "还没有填写 API Key。", "填写自己的 Key 后再连接；Key 只保存在本机进程内存。")
    base_url = _clean_base_url(str(payload.get("base_url") or DEFAULT_BASE_URL))
    model = str(payload.get("model") or DEFAULT_MODEL).strip()
    if not model:
        raise LiveAgentError("API_CONFIG_INVALID", "模型名不能为空。", "填写当前账号有权限调用的模型名。")
    try:
        timeout = int(payload.get("timeout_seconds") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError) as exc:
        raise LiveAgentError("API_CONFIG_INVALID", "超时时间必须是数字。", "填写 10 到 120 秒之间的整数。") from exc
    timeout = max(10, min(120, timeout))
    with _LOCK:
        _SESSION.clear()
        _SESSION.update({"api_key": key, "base_url": base_url, "model": model, "timeout_seconds": timeout})
    return config_status()


def clear_session() -> dict[str, Any]:
    with _LOCK:
        _SESSION.clear()
    return config_status()


def _load_config() -> Config:
    with _LOCK:
        session = dict(_SESSION)
    key = str(session.get("api_key") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        raise LiveAgentError("API_KEY_REQUIRED", "实时模式还没有 API Key。", "打开右上角 API 设置，填写 Key 后重试。")
    base_url = _clean_base_url(str(session.get("base_url") or os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL))
    model = str(session.get("model") or os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
    timeout = int(session.get("timeout_seconds") or os.getenv("LLM_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)
    return Config(key, base_url, model, max(10, min(120, timeout)), "session_memory" if session else "server_environment")


def config_status() -> dict[str, Any]:
    try:
        config = _load_config()
    except LiveAgentError as exc:
        return {
            "configured": False,
            "status": "API_KEY_REQUIRED",
            "message": exc.message,
            "key_persistence": "NONE",
            "no_silent_fallback": True,
        }
    return {
        "configured": True,
        "status": "READY",
        "provider": config.provider,
        "model": config.model,
        "transport": "CHAT_COMPLETIONS" if "/chat/completions" in config.base_url else "RESPONSES",
        "key_mask": f"••••{config.api_key[-4:]}",
        "key_source": config.source,
        "key_persistence": "PROCESS_MEMORY_ONLY" if config.source == "session_memory" else "SERVER_ENVIRONMENT",
        "no_silent_fallback": True,
    }


def _http_request(config: Config, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        config.base_url,
        data=raw,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {config.api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:600]
        if exc.code in {401, 403}:
            raise LiveAgentError("API_AUTH_FAILED", "API Key 无效或当前模型没有权限。", "检查 Key 和模型名后重新连接。", details={"http_status": exc.code}) from exc
        if exc.code == 429:
            raise LiveAgentError("API_RATE_LIMITED", "接口达到频率或额度限制。", "稍后重试，或检查账号额度。", details={"http_status": exc.code}) from exc
        raise LiveAgentError("API_HTTP_FAILED", f"模型接口返回 HTTP {exc.code}。", "检查端点、模型和账号状态后重试。", details={"http_status": exc.code, "response_excerpt": body}) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise LiveAgentError("API_TIMEOUT", "模型接口不可达或超过等待时间。", "检查网络与端点后重试；页面不会切回固定案例。", details={"reason_type": type(exc).__name__}) from exc
    except json.JSONDecodeError as exc:
        raise LiveAgentError("API_RESPONSE_INVALID", "接口返回的外层内容不是 JSON。", "确认端点兼容 Responses 或 Chat Completions。") from exc


def _extract_output(response: dict[str, Any], chat_mode: bool) -> tuple[dict[str, Any], str]:
    if chat_mode:
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LiveAgentError("API_RESPONSE_INVALID", "响应缺少 choices.message.content。", "检查兼容端点返回格式。") from exc
    else:
        content = response.get("output_text")
        if not content:
            parts: list[str] = []
            for item in response.get("output", []):
                if not isinstance(item, dict):
                    continue
                for block in item.get("content", []):
                    if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
                        parts.append(str(block.get("text") or ""))
            content = "".join(parts)
        if not content:
            raise LiveAgentError("API_RESPONSE_INVALID", "响应中没有结构化文本结果。", "检查模型是否支持结构化输出。")
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    if isinstance(content, dict):
        result = content
        raw_text = json.dumps(content, ensure_ascii=False)
    else:
        raw_text = str(content).strip()
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()[1:]
            if lines and lines[-1].strip() == "```":
                lines.pop()
            raw_text = "\n".join(lines).strip()
        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LiveAgentError("API_RESPONSE_INVALID", "模型结果不是可解析的 JSON。", "重新运行；若持续失败，换用支持结构化输出的模型。") from exc
    if not isinstance(result, dict):
        raise LiveAgentError("API_RESPONSE_INVALID", "模型结果顶层必须是对象。", "检查项目输出合同。")
    return result, raw_text


def _validate_required(result: dict[str, Any], schema: dict[str, Any]) -> None:
    missing = [key for key in schema.get("required", []) if key not in result]
    if missing:
        raise LiveAgentError("API_RESPONSE_INVALID", "模型结果缺少项目必需产物。", "重新运行或检查模型能力。", details={"missing": missing})


RequestFunction = Callable[[Config, dict[str, Any]], dict[str, Any]]


def run_structured(
    *,
    system_prompt: str,
    user_text: str,
    schema_name: str,
    schema: dict[str, Any],
    images: list[dict[str, str]] | None = None,
    allow_web_search: bool = False,
    request_fn: RequestFunction | None = None,
) -> dict[str, Any]:
    text = str(user_text or "").strip()
    if not text:
        raise LiveAgentError("API_INPUT_REQUIRED", "还没有可供 Agent 理解的输入。", "填写本项目要求的正文、Brief 或变化说明。")
    if len(text) > MAX_TEXT_CHARS:
        raise LiveAgentError("API_INPUT_TOO_LONG", f"本轮输入超过 {MAX_TEXT_CHARS} 字符。", "缩短内容或拆成多份来源。")
    images = images or []
    for image in images:
        data_url = str(image.get("data_url") or "")
        if not data_url.startswith("data:image/"):
            raise LiveAgentError("API_INPUT_REQUIRED", "图片必须是浏览器上传的 data URL。", "重新选择 PNG、JPEG 或 WebP 图片。")
        if len(data_url) * 3 // 4 > MAX_IMAGE_BYTES:
            raise LiveAgentError("API_INPUT_TOO_LARGE", "单张图片超过 8MB。", "压缩图片后重试。")
    config = _load_config()
    chat_mode = "/chat/completions" in config.base_url
    request_id = f"local-{uuid.uuid4().hex[:12]}"
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if chat_mode:
        is_deepseek = "deepseek" in config.provider.lower() or config.model.lower().startswith("deepseek")
        schema_instruction = "\n\n请严格返回与以下 JSON Schema 一致的 JSON 对象，不要输出 Markdown：\n" + json.dumps(schema, ensure_ascii=False)
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        content.extend({"type": "image_url", "image_url": {"url": image["data_url"]}} for image in images)
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt + (schema_instruction if is_deepseek else "")},
                {"role": "user", "content": content if images else text},
            ],
            "response_format": (
                {"type": "json_object"}
                if is_deepseek
                else {"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}}
            ),
        }
    else:
        user_content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
        user_content.extend({"type": "input_image", "image_url": image["data_url"], "detail": image.get("detail", "low")} for image in images)
        payload = {
            "model": config.model,
            "input": [
                {"role": "developer", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": user_content},
            ],
            "text": {"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        }
        if allow_web_search:
            payload["tools"] = [{"type": "web_search"}]
    response = (request_fn or _http_request)(config, payload)
    result, raw_text = _extract_output(response, chat_mode)
    _validate_required(result, schema)
    return {
        "result": result,
        "metadata": {
            "mode": "LIVE_API",
            "status": "LIVE_API_PENDING_HUMAN_CONFIRMATION",
            "provider": config.provider,
            "model": config.model,
            "transport": "CHAT_COMPLETIONS" if chat_mode else "RESPONSES",
            "request_id": str(response.get("id") or request_id),
            "observed_at": observed_at,
            "response_chars": len(raw_text),
            "usage": response.get("usage") or {},
            "key_persistence": "PROCESS_MEMORY_ONLY" if config.source == "session_memory" else "SERVER_ENVIRONMENT",
            "requires_human_confirmation": True,
            "no_silent_fallback": True,
        },
    }
