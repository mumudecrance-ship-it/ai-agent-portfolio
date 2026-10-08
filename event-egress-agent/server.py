from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import importlib
import json
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse

import live_agent


ROOT = Path(__file__).resolve().parent


def _load_local_env() -> None:
    path = ROOT / "config.env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()
PROJECT = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "schemas" / "live-output-schema.json").read_text(encoding="utf-8"))
LOCK = threading.RLock()
STATE: dict[str, object] = {
    "fixed": None,
    "live": None,
    "confirmation": None,
    "error": None,
    "generations": {"fixed": 0, "live": 0},
}

try:
    RULES = importlib.import_module("project_rules")
except ModuleNotFoundError:
    RULES = None


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _public_state() -> dict[str, object]:
    return {
        "fixed": STATE["fixed"],
        "live": STATE["live"],
        "confirmation": STATE["confirmation"],
        "error": STATE["error"],
    }


def _start_operation(scope: str) -> int:
    """Invalidate older work in one mode and return this run's generation."""
    with LOCK:
        generations = STATE["generations"]
        assert isinstance(generations, dict)
        generation = int(generations[scope]) + 1
        generations[scope] = generation
        STATE[scope] = None
        STATE["confirmation"] = None
        STATE["error"] = None
        return generation


def _finish_operation(scope: str, generation: int, value: object) -> bool:
    """Commit only when no reset or newer run has superseded this request."""
    with LOCK:
        generations = STATE["generations"]
        assert isinstance(generations, dict)
        if int(generations[scope]) != generation:
            return False
        STATE[scope] = value
        STATE["confirmation"] = None
        STATE["error"] = None
        return True


def _operation_current(scope: str, generation: int) -> bool:
    with LOCK:
        generations = STATE["generations"]
        assert isinstance(generations, dict)
        return int(generations[scope]) == generation


def _reset_scopes(scope: str) -> None:
    targets = ("fixed", "live") if scope == "all" else (scope,)
    with LOCK:
        generations = STATE["generations"]
        assert isinstance(generations, dict)
        for target in targets:
            generations[target] = int(generations[target]) + 1
            STATE[target] = None
        STATE["confirmation"] = None
        STATE["error"] = None


def _confirmation_candidate(scope: str, candidate: object) -> tuple[dict, str]:
    if scope not in {"fixed", "live"}:
        raise live_agent.LiveAgentError("SCOPE_INVALID", "确认范围无效。", "回到当前模式重新查看结果。")
    if not isinstance(candidate, dict):
        raise live_agent.LiveAgentError("RESULT_REQUIRED", "当前还没有可以确认的结果。", "先运行对应模式。")
    result = candidate.get("result") if scope == "live" else candidate
    if not isinstance(result, dict):
        raise live_agent.LiveAgentError("RESULT_REQUIRED", "当前还没有可以确认的结果。", "先运行对应模式。")
    decision = str(result.get("decision") or "")
    if decision != "PENDING_HUMAN_CONFIRMATION":
        raise live_agent.LiveAgentError(
            "RESULT_NOT_CONFIRMABLE",
            "当前结果需要重新规划，不能进入人工确认。",
            "选择通过规则与仿真的候选后再确认。",
        )
    digest = str(candidate.get("candidate_digest") or result.get("candidate_digest") or "")
    if not digest:
        raise live_agent.LiveAgentError("VERSION_REQUIRED", "当前结果缺少版本摘要，不能确认。", "重新运行并查看最新候选。")
    return result, digest


class Handler(BaseHTTPRequestHandler):
    server_version = "DualModeAgentDemo/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Never log request bodies, API keys, or user source material.
        print(f"[demo] {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}")

    def _json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 12 * 1024 * 1024:
            raise live_agent.LiveAgentError("REQUEST_TOO_LARGE", "本地请求超过 12MB。", "压缩图片或缩短正文后重试。")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise live_agent.LiveAgentError("REQUEST_INVALID", "请求不是有效 JSON。", "刷新页面后重新提交。") from exc
        if not isinstance(payload, dict):
            raise live_agent.LiveAgentError("REQUEST_INVALID", "请求顶层必须是对象。", "刷新页面后重新提交。")
        return payload

    def _error(self, error: live_agent.LiveAgentError, status: int = HTTPStatus.BAD_REQUEST) -> None:
        with LOCK:
            STATE["error"] = error.as_dict()
        self._json(status, {"ok": False, "error": error.as_dict(), "state": _public_state()})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "project_id": PROJECT["project_id"], "live": live_agent.config_status()})
            return
        if path == "/api/bootstrap":
            self._json(200, {"ok": True, "project": PROJECT, "live_config": live_agent.config_status(), "state": _public_state()})
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read()
            if path == "/api/live/configure":
                self._json(200, {"ok": True, "live_config": live_agent.configure_session(payload)})
                return
            if path == "/api/live/clear-config":
                self._json(200, {"ok": True, "live_config": live_agent.clear_session()})
                return
            if path == "/api/fixed/run":
                mode = str(payload.get("mode") or "")
                outcome = next((item for item in PROJECT["fixed_case"]["outcomes"] if item["id"] == mode), None)
                if outcome is None:
                    raise live_agent.LiveAgentError("MODE_INVALID", "没有这个固定回归模式。", "请选择页面提供的三个回归按钮。")
                generation = _start_operation("fixed")
                result = {**outcome, "source": "FIXED_REGRESSION", "case_id": PROJECT["fixed_case"]["case_id"], "evidence_digest": _digest(outcome)}
                if RULES and hasattr(RULES, "run_fixed"):
                    result = RULES.run_fixed(result, PROJECT)
                result["candidate_digest"] = _digest(result)
                if not _finish_operation("fixed", generation, result):
                    error = live_agent.LiveAgentError("OPERATION_CANCELLED", "这次固定回放已被复位或更新操作取消。", "查看当前模式后重新运行。")
                    self._json(HTTPStatus.CONFLICT, {"ok": False, "error": error.as_dict(), "state": _public_state()})
                    return
                self._json(200, {"ok": True, "result": result, "state": _public_state()})
                return
            if path == "/api/live/run":
                if RULES and hasattr(RULES, "preflight_live"):
                    RULES.preflight_live(payload)
                generation = _start_operation("live")
                try:
                    output = live_agent.run_structured(
                        system_prompt=PROJECT["live"]["system_prompt"],
                        user_text=str(payload.get("input") or ""),
                        schema_name=PROJECT["live"]["schema_name"],
                        schema=SCHEMA,
                        images=payload.get("images") if isinstance(payload.get("images"), list) else [],
                        allow_web_search=bool(payload.get("allow_web_search") and PROJECT["live"].get("allow_web_search")),
                    )
                except Exception:
                    if not _operation_current("live", generation):
                        error = live_agent.LiveAgentError("OPERATION_CANCELLED", "这次实时推演已被复位或更新操作取消。", "查看当前模式后重新运行。")
                        self._json(HTTPStatus.CONFLICT, {"ok": False, "error": error.as_dict(), "state": _public_state()})
                        return
                    raise
                result = output["result"]
                if RULES and hasattr(RULES, "validate_live"):
                    result = RULES.validate_live(result, payload, PROJECT)
                output["result"] = result
                output["candidate_digest"] = _digest(result)
                if not _finish_operation("live", generation, output):
                    error = live_agent.LiveAgentError("OPERATION_CANCELLED", "这次实时推演已被复位或更新操作取消。", "查看当前模式后重新运行。")
                    self._json(HTTPStatus.CONFLICT, {"ok": False, "error": error.as_dict(), "state": _public_state()})
                    return
                self._json(200, {"ok": True, "data": output, "state": _public_state()})
                return
            if path == "/api/confirm":
                reviewer = str(payload.get("reviewer") or "").strip()
                scope = str(payload.get("scope") or "")
                if not reviewer:
                    raise live_agent.LiveAgentError("HUMAN_IDENTITY_REQUIRED", "确认人不能为空。", "填写真实姓名后重新确认。")
                with LOCK:
                    candidate = STATE.get(scope)
                    _, current_digest = _confirmation_candidate(scope, candidate)
                    expected = str(payload.get("expected_digest") or "")
                    if not expected:
                        raise live_agent.LiveAgentError("VERSION_REQUIRED", "确认请求缺少结果版本，不能继续。", "重新查看最新结果后再确认。")
                    if expected != current_digest:
                        raise live_agent.LiveAgentError("VERSION_CONFLICT", "结果已经变化，旧确认不能覆盖新候选。", "重新查看最新结果后再确认。")
                    confirmation = {
                        "status": "HUMAN_CONFIRMED",
                        "scope": scope,
                        "reviewer": reviewer,
                        "confirmed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                        "candidate_digest": current_digest,
                        "next_boundary": PROJECT["human_gate"]["after_confirmation"],
                    }
                    STATE["confirmation"] = confirmation
                    STATE["error"] = None
                self._json(200, {"ok": True, "confirmation": confirmation, "state": _public_state()})
                return
            if path == "/api/reset":
                scope = str(payload.get("scope") or "all")
                if scope not in {"fixed", "live", "all"}:
                    raise live_agent.LiveAgentError("SCOPE_INVALID", "复位范围无效。", "刷新页面后重新选择模式。")
                _reset_scopes(scope)
                self._json(200, {"ok": True, "message": f"{scope} 已复位", "state": _public_state()})
                return
            if path == "/api/external-action":
                error = live_agent.LiveAgentError("EXTERNAL_AUTHORITY_REQUIRED", PROJECT["boundaries"]["external_message"], "在真实业务系统中另行申请权限；本 Demo 到此停止。")
                self._error(error, HTTPStatus.FORBIDDEN)
                return
            raise live_agent.LiveAgentError("NOT_FOUND", "没有这个本地接口。", "刷新页面后重试。")
        except live_agent.LiveAgentError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if exc.code in {"API_KEY_REQUIRED", "API_AUTH_FAILED", "API_TIMEOUT", "API_RATE_LIMITED"} else HTTPStatus.BAD_REQUEST
            self._error(exc, status)
        except Exception as exc:  # pragma: no cover - final local guard
            self._error(live_agent.LiveAgentError("SERVER_ERROR", "本地服务没有完成这次操作。", "查看终端错误并重新启动 Demo。", details={"reason_type": type(exc).__name__}), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _static(self, path: str) -> None:
        relative = unquote(path.lstrip("/")) or "index.html"
        target = (ROOT / relative).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            self._json(403, {"ok": False, "error": {"code": "PATH_REJECTED"}})
            return
        if not target.is_file():
            self._json(404, {"ok": False, "error": {"code": "NOT_FOUND"}})
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(PROJECT.get("port", 8801)))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"{PROJECT['title']}：http://127.0.0.1:{args.port}")
    print("API Key 仅保存在当前本地进程内存；Ctrl+C 停止并清除。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        live_agent.clear_session()
        server.server_close()


if __name__ == "__main__":
    main()
