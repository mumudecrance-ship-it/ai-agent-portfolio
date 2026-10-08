#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FlowBench —— 评价域工作流平台（本地演示版）

纯 Python 标准库实现，零第三方依赖。
    启动:  python platform.py            (默认 http://127.0.0.1:8787)
    画布:  浏览器打开 http://127.0.0.1:8787

对外接口（契约借鉴主流开源工作流平台）:
    POST /apps/imports            导入工作流定义(JSON) -> {app_id}
    POST /apps/{id}/publish       发布 -> {published: true, version}
    GET  /apps                    应用列表
    GET  /apps/{id}               应用定义(画布用)
    POST /workflows/run           {app_id, inputs} -> {run_id, status, outputs}
    GET  /workflows/run/{id}      运行结果回读(含节点级输入输出与报错)

内置 mock 业务接口（评价域）:
    POST /mock/svc/same-image      同图识别      -> {result: 0/1/2}
    POST /mock/svc/ai-image        AI生图识别    -> {result: 0/1}
    POST /mock/svc/irrelevant-image无关图识别    -> {result: 0/1/2}
    POST /mock/svc/sensitive-words 敏感词        -> {hit: bool, words: []}
    POST /mock/svc/ocr             OCR           -> {text}
    POST /mock/item-center/detail    商品信息中心-商品信息  -> {product}
    POST /mock/review-base/query     评价查询服务-查评价-> {reviews: []}
错误注入: 请求体带 {"__inject__": "500"} 返回500, {"__inject__": "timeout"} 延迟8s。
"""
import json
import re
import sys
import time
import uuid
import hashlib
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = HERE / "seed-data"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8787

NODE_TYPES = [
    "start", "end", "llm", "knowledge_retrieval", "if_else",
    "question_classifier", "code", "http_request", "iteration",
    "variable_aggregator", "parameter_extractor", "template_transform",
]

APPS = {}    # app_id -> {definition, published, version, name}
RUNS = {}    # run_id -> run record
LOCK = threading.Lock()

# ---------------------------------------------------------------- seed data


def load_seed(name, default):
    p = SEED / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[seed] {name} 解析失败: {e}")
    return default


PRODUCTS = load_seed("products.json", [])
REVIEWS = load_seed("reviews.json", [])
LLM_DEMO = load_seed("llm_demo_outputs.json", {"rules": []})
CONFIG = load_seed("platform_config.json", {"llm_mode": "demo"})

# ---------------------------------------------------------------- 变量引用


VAR_RE = re.compile(r"\{\{#([\w\-\.]+)#\}\}")


def resolve_ref(ref, ctx):
    """'node_id.field.sub' -> 值。首段也可为 'inputs'。"""
    parts = ref.split(".")
    cur = ctx.get(parts[0])
    for p in parts[1:]:
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            cur = cur[int(p)] if int(p) < len(cur) else None
        else:
            return None
    return cur


def render(text, ctx):
    """把字符串里的 {{#a.b#}} 替换为上下文值。"""
    if not isinstance(text, str):
        return text

    def sub(m):
        v = resolve_ref(m.group(1), ctx)
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return "" if v is None else str(v)

    return VAR_RE.sub(sub, text)


def render_value(v, ctx):
    if isinstance(v, str):
        m = VAR_RE.fullmatch(v.strip())
        if m:  # 纯引用保留原始类型
            return resolve_ref(m.group(1), ctx)
        return render(v, ctx)
    if isinstance(v, dict):
        return {k: render_value(x, ctx) for k, x in v.items()}
    if isinstance(v, list):
        return [render_value(x, ctx) for x in v]
    return v

# ---------------------------------------------------------------- LLM 执行


def llm_call(prompt, node, ctx):
    mode = CONFIG.get("llm_mode", "demo")
    if mode == "api" and CONFIG.get("api_key"):
        return llm_api(prompt)
    return llm_demo(prompt, node)


def llm_api(prompt):
    body = json.dumps({
        "model": CONFIG.get("model", "gpt-4o-mini"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        CONFIG.get("api_base", "https://api.openai.com/v1") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + CONFIG["api_key"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def llm_demo(prompt, node):
    """内置演示模式：按 seed 规则匹配，保证确定性输出，零配置跑通。"""
    title = node.get("title", "")
    for rule in LLM_DEMO.get("rules", []):
        t_ok = ("title_contains" not in rule) or (rule["title_contains"] in title)
        p_ok = ("prompt_contains" not in rule) or (rule["prompt_contains"] in prompt)
        if t_ok and p_ok and ("title_contains" in rule or "prompt_contains" in rule):
            out = rule["output"]
            return json.dumps(out, ensure_ascii=False) if isinstance(out, (dict, list)) else str(out)
    # 兜底：基于 prompt 哈希的确定性占位输出
    h = hashlib.md5(prompt.encode()).hexdigest()[:6]
    return json.dumps({"result": f"[演示模式输出·{h}] 未命中种子规则，请在 seed-data/llm_demo_outputs.json 配置",
                       "prompt_len": len(prompt)}, ensure_ascii=False)


def try_json(s):
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}|\[.*\]", str(s), re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None

# ---------------------------------------------------------------- 节点执行器


def exec_node(node, ctx, graph):
    """返回 (output_dict, chosen_handle or None)"""
    t = node["type"]
    cfg = node.get("config", {})

    if t == "start":
        return {"inputs": ctx.get("inputs", {})}, None

    if t == "end":
        outputs = render_value(cfg.get("outputs", {}), ctx)
        return {"outputs": outputs}, None

    if t == "llm":
        prompt = render(cfg.get("prompt", ""), ctx)
        text = llm_call(prompt, node, ctx)
        out = {"text": text}
        j = try_json(text)
        if j is not None:
            out["json"] = j
        return out, None

    if t == "knowledge_retrieval":
        query = render(str(cfg.get("query", "")), ctx)
        top_k = int(cfg.get("top_k", 5))
        pid = render(str(cfg.get("product_id", "")), ctx)
        docs = [r for r in REVIEWS if not pid or str(r.get("product_id")) == pid]
        scored = []
        qwords = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", query))
        for r in docs:
            text = r.get("content", "")
            score = sum(1 for tk in qwords if tk in text)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda x: -x[0])
        hits = [dict(r, score=s) for s, r in scored[:top_k]]
        return {"result": hits, "count": len(hits)}, None

    if t == "if_else":
        # conditions: [{left, op, right}], logic: and/or
        conds = cfg.get("conditions", [])
        logic = cfg.get("logic", "and")
        results = []
        for c in conds:
            left = render_value(c.get("left"), ctx)
            right = render_value(c.get("right"), ctx)
            op = c.get("op", "==")
            try:
                if op == "==":
                    ok = str(left) == str(right)
                elif op == "!=":
                    ok = str(left) != str(right)
                elif op == "contains":
                    ok = str(right) in str(left)
                elif op == "not contains":
                    ok = str(right) not in str(left)
                elif op == ">":
                    ok = float(left) > float(right)
                elif op == "<":
                    ok = float(left) < float(right)
                elif op == ">=":
                    ok = float(left) >= float(right)
                elif op == "<=":
                    ok = float(left) <= float(right)
                elif op == "empty":
                    ok = left in (None, "", [], {})
                elif op == "not empty":
                    ok = left not in (None, "", [], {})
                else:
                    raise ValueError(f"不支持的比较符: {op}")
            except (TypeError, ValueError) as e:
                raise RuntimeError(f"条件判断失败: {left!r} {op} {right!r} ({e})")
            results.append(ok)
        final = all(results) if logic == "and" else any(results)
        return {"result": final}, ("true" if final else "false")

    if t == "question_classifier":
        text = render(str(cfg.get("input", "")), ctx)
        classes = cfg.get("classes", [])
        chosen = None
        for c in classes:
            for kw in c.get("keywords", []):
                if kw in text:
                    chosen = c
                    break
            if chosen:
                break
        if chosen is None and classes:
            chosen = next((c for c in classes if c.get("default")), classes[-1])
        if chosen is None:
            raise RuntimeError("问题分类器未配置任何类别")
        return {"class": chosen["id"], "class_name": chosen.get("name", chosen["id"])}, chosen["id"]

    if t == "code":
        code = cfg.get("code", "")
        inputs = render_value(cfg.get("inputs", {}), ctx)
        ns = {"inputs": inputs, "outputs": {}, "json": json, "re": re}
        exec(code, {"__builtins__": {"len": len, "str": str, "int": int, "float": float,
                                     "list": list, "dict": dict, "set": set, "sum": sum,
                                     "min": min, "max": max, "sorted": sorted, "range": range,
                                     "enumerate": enumerate, "abs": abs, "round": round,
                                     "any": any, "all": all, "zip": zip,
                                     "isinstance": isinstance, "bool": bool, "type": type}}, ns)
        out = ns.get("outputs")
        if not isinstance(out, dict):
            raise RuntimeError("代码执行节点必须给 outputs 赋 dict 值")
        return out, None

    if t == "http_request":
        url = render(str(cfg.get("url", "")), ctx)
        method = cfg.get("method", "POST").upper()
        body = render_value(cfg.get("body", {}), ctx)
        data = json.dumps(body, ensure_ascii=False).encode() if method != "GET" else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=int(cfg.get("timeout", 6))) as r:
                raw = r.read().decode()
                status = r.status
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: 接口返回错误（{url}）")
        except Exception as e:
            raise RuntimeError(f"HTTP 请求失败（{url}）: {e}")
        j = try_json(raw)
        return {"status_code": status, "body": j if j is not None else raw}, None

    if t == "iteration":
        items = render_value(cfg.get("input"), ctx)
        if not isinstance(items, list):
            raise RuntimeError(f"迭代节点输入必须是列表，得到 {type(items).__name__}")
        mode = cfg.get("mode", "template")
        results = []
        for it in items:
            ictx = dict(ctx)
            ictx["item"] = it if isinstance(it, dict) else {"value": it}
            if mode == "llm":
                prompt = render(cfg.get("prompt", ""), ictx)
                text = llm_call(prompt, node, ictx)
                j = try_json(text)
                results.append(j if j is not None else text)
            else:
                results.append(render(cfg.get("template", "{{#item.value#}}"), ictx))
        return {"result": results, "count": len(results)}, None

    if t == "variable_aggregator":
        variables = cfg.get("variables", [])
        strategy = cfg.get("strategy", "first_not_null")
        vals = [render_value(v, ctx) for v in variables]
        if strategy == "merge_list":
            merged = []
            for v in vals:
                merged.extend(v if isinstance(v, list) else [v])
            return {"output": merged}, None
        out = next((v for v in vals if v not in (None, "", [], {})), None)
        return {"output": out}, None

    if t == "parameter_extractor":
        text = render(str(cfg.get("input", "")), ctx)
        params = cfg.get("parameters", [])
        out = {}
        for p in params:
            name, ptype = p["name"], p.get("type", "string")
            pat = p.get("pattern")
            if pat:
                m = re.search(pat, text)
                out[name] = m.group(1) if (m and m.groups()) else (m.group(0) if m else None)
            elif ptype == "number":
                m = re.search(r"-?\d+(?:\.\d+)?", text)
                out[name] = float(m.group(0)) if m else None
            else:
                out[name] = text.strip()[: int(p.get("max_len", 200))] or None
        return out, None

    if t == "template_transform":
        return {"output": render(cfg.get("template", ""), ctx)}, None

    raise RuntimeError(f"未知节点类型: {t}")

# ---------------------------------------------------------------- 工作流引擎


def validate_definition(defn):
    errs = []
    graph = defn.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        errs.append("graph.nodes 为空")
    ids = set()
    starts = ends = 0
    for n in nodes:
        if not n.get("id"):
            errs.append("存在缺少 id 的节点")
            continue
        if n["id"] in ids:
            errs.append(f"节点 id 重复: {n['id']}")
        ids.add(n["id"])
        if n.get("type") not in NODE_TYPES:
            errs.append(f"节点 {n['id']} 类型非法: {n.get('type')}（合法: {NODE_TYPES}）")
        starts += n.get("type") == "start"
        ends += n.get("type") == "end"
    if starts != 1:
        errs.append(f"必须恰好 1 个 start 节点，当前 {starts}")
    if ends < 1:
        errs.append("至少 1 个 end 节点")
    for e in edges:
        if e.get("source") not in ids:
            errs.append(f"边 source 不存在: {e.get('source')}")
        if e.get("target") not in ids:
            errs.append(f"边 target 不存在: {e.get('target')}")
    return errs


def run_workflow(app, inputs):
    defn = app["definition"]
    graph = defn["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph.get("edges", [])
    out_edges = {}
    for e in edges:
        out_edges.setdefault(e["source"], []).append(e)

    run_id = uuid.uuid4().hex[:12]
    rec = {"run_id": run_id, "app_id": app["app_id"], "app_name": app["name"],
           "status": "running", "inputs": inputs, "outputs": None,
           "node_runs": [], "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "elapsed_ms": None, "error": None}
    with LOCK:
        RUNS[run_id] = rec

    t0 = time.time()
    ctx = {"inputs": inputs}
    in_edges = {}
    for e in edges:
        in_edges.setdefault(e["target"], []).append(e)

    # 拓扑执行：支持并行分流与汇聚。边状态 pending/active/pruned；
    # 节点全部入边有结论后才执行；无 active 入边的节点被剪枝(skipped)。
    edge_state = {}          # id(edge) -> active/pruned
    node_state = {nid: "pending" for nid in nodes}
    start_id = next(nid for nid, n in nodes.items() if n["type"] == "start")

    def decide_out_edges(nid, handle):
        for e in out_edges.get(nid, []):
            if handle is not None and str(e.get("source_handle")) != str(handle):
                edge_state[id(e)] = "pruned"
            else:
                edge_state[id(e)] = "active"

    def prune_out_edges(nid):
        for e in out_edges.get(nid, []):
            edge_state[id(e)] = "pruned"

    try:
        guard = 0
        progress = True
        while progress:
            progress = False
            guard += 1
            if guard > 500:
                raise RuntimeError("执行轮次超限(500)，疑似成环")
            for nid, node in nodes.items():
                if node_state[nid] != "pending":
                    continue
                ins = in_edges.get(nid, [])
                if nid != start_id:
                    if any(id(e) not in edge_state for e in ins):
                        continue  # 入边尚未有结论
                    if not ins or all(edge_state[id(e)] == "pruned" for e in ins):
                        node_state[nid] = "skipped"
                        prune_out_edges(nid)
                        progress = True
                        continue
                # 执行
                nt0 = time.time()
                nr = {"node_id": nid, "title": node.get("title", nid),
                      "type": node["type"], "status": "running", "output": None,
                      "error": None, "elapsed_ms": None}
                rec["node_runs"].append(nr)
                try:
                    out, handle = exec_node(node, ctx, graph)
                    nr["status"] = "succeeded"
                    nr["output"] = out
                    ctx[nid] = out
                except Exception as e:
                    nr["status"] = "failed"
                    nr["error"] = str(e)
                    nr["elapsed_ms"] = int((time.time() - nt0) * 1000)
                    raise RuntimeError(f"节点「{nr['title']}」执行失败: {e}")
                nr["elapsed_ms"] = int((time.time() - nt0) * 1000)
                node_state[nid] = "executed"
                decide_out_edges(nid, handle)
                if node["type"] == "end":
                    if rec["outputs"] is None:
                        rec["outputs"] = out.get("outputs", out)
                progress = True
        if rec["outputs"] is None:
            raise RuntimeError("流程结束但没有任何 end 节点被执行（检查连线与分支句柄）")
        rec["skipped_nodes"] = [nid for nid, s in node_state.items() if s == "skipped"]
        rec["status"] = "succeeded"
    except Exception as e:
        rec["status"] = "failed"
        rec["error"] = str(e)
    rec["elapsed_ms"] = int((time.time() - t0) * 1000)
    return rec

# ---------------------------------------------------------------- mock 业务接口


def det_hash(s, mod):
    return int(hashlib.md5(str(s).encode()).hexdigest(), 16) % mod


def mock_dispatch(path, body):
    inject = body.get("__inject__")
    if inject == "500":
        raise MockError(500, "内部服务错误（错误注入演示）")
    if inject == "timeout":
        time.sleep(8)

    if path == "/mock/svc/same-image":
        urls = body.get("image_urls", [])
        seed_hit = any("same" in str(u) for u in urls)
        r = 2 if seed_hit else (1 if any("suspect" in str(u) for u in urls) else 0)
        return {"result": r, "desc": {0: "非同图", 1: "疑似同图", 2: "同图"}[r]}
    if path == "/mock/svc/ai-image":
        urls = body.get("image_urls", [])
        r = 1 if any("aigen" in str(u) for u in urls) else 0
        return {"result": r, "desc": {0: "非AI图", 1: "AI生图"}[r]}
    if path == "/mock/svc/irrelevant-image":
        urls = body.get("image_urls", [])
        r = 2 if any("irrelevant" in str(u) for u in urls) else (1 if any("maybe" in str(u) for u in urls) else 0)
        return {"result": r, "desc": {0: "相关", 1: "疑似无关", 2: "无关"}[r]}
    if path == "/mock/svc/sensitive-words":
        text = body.get("text", "")
        hits = [w for w in ["加微信", "领大额券", "某宝更便宜"] if w in text]
        return {"hit": bool(hits), "words": hits}
    if path == "/mock/svc/ocr":
        return {"text": body.get("image_desc", "【OCR演示】主图文案：官方正品 一年质保")}
    if path == "/mock/item-center/detail":
        pid = str(body.get("product_id", ""))
        p = next((x for x in PRODUCTS if str(x.get("product_id")) == pid), None)
        if p is None:
            raise MockError(404, f"商品不存在: {pid}")
        return {"product": p}
    if path == "/mock/review-base/query":
        pid = str(body.get("product_id", ""))
        limit = int(body.get("limit", 20))
        rs = [r for r in REVIEWS if str(r.get("product_id")) == pid][:limit]
        return {"reviews": rs, "count": len(rs)}
    raise MockError(404, f"未知 mock 接口: {path}")


class MockError(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg

# ---------------------------------------------------------------- HTTP 服务


class Handler(BaseHTTPRequestHandler):
    server_version = "FlowBench/1.0"

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (HERE / "canvas.html")
            if html.exists():
                data = html.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_json({"error": "canvas.html 缺失"}, 500)
            return
        if self.path == "/apps":
            with LOCK:
                items = [{"app_id": a["app_id"], "name": a["name"],
                          "published": a["published"], "version": a["version"],
                          "node_count": len(a["definition"]["graph"]["nodes"])}
                         for a in APPS.values()]
            self.send_json({"apps": items})
            return
        m = re.fullmatch(r"/apps/([\w]+)", self.path)
        if m:
            app = APPS.get(m.group(1))
            if not app:
                self.send_json({"error": "app 不存在"}, 404)
            else:
                self.send_json(app)
            return
        m = re.fullmatch(r"/workflows/run/([\w]+)", self.path)
        if m:
            rec = RUNS.get(m.group(1))
            if not rec:
                self.send_json({"error": "run 不存在"}, 404)
            else:
                self.send_json(rec)
            return
        if self.path == "/runs":
            with LOCK:
                items = sorted(RUNS.values(), key=lambda r: r["created_at"], reverse=True)
            self.send_json({"runs": [{k: r[k] for k in
                                      ("run_id", "app_id", "app_name", "status", "created_at", "elapsed_ms")}
                                     for r in items[:50]]})
            return
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        body = self.read_body()
        if self.path == "/apps/imports":
            defn = body.get("definition") or body
            errs = validate_definition(defn)
            if errs:
                self.send_json({"imported": False, "errors": errs}, 422)
                return
            app_id = uuid.uuid4().hex[:8]
            name = (defn.get("app") or {}).get("name") or f"未命名应用-{app_id}"
            with LOCK:
                APPS[app_id] = {"app_id": app_id, "name": name, "definition": defn,
                                "published": False, "version": 0}
            self.send_json({"imported": True, "app_id": app_id, "name": name}, 201)
            return
        m = re.fullmatch(r"/apps/([\w]+)/publish", self.path)
        if m:
            app = APPS.get(m.group(1))
            if not app:
                self.send_json({"error": "app 不存在"}, 404)
                return
            with LOCK:
                app["published"] = True
                app["version"] += 1
            self.send_json({"published": True, "version": app["version"]})
            return
        if self.path == "/workflows/run":
            app = APPS.get(str(body.get("app_id")))
            if not app:
                self.send_json({"error": "app 不存在"}, 404)
                return
            if not app["published"]:
                self.send_json({"error": "应用未发布，先调用 /apps/{id}/publish"}, 409)
                return
            rec = run_workflow(app, body.get("inputs") or {})
            self.send_json({"run_id": rec["run_id"], "status": rec["status"],
                            "outputs": rec["outputs"], "error": rec["error"],
                            "elapsed_ms": rec["elapsed_ms"]})
            return
        if self.path.startswith("/mock/"):
            try:
                self.send_json(mock_dispatch(self.path, body))
            except MockError as e:
                self.send_json({"error": e.msg}, e.code)
            return
        self.send_json({"error": "not found"}, 404)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("=" * 56)
    print("  FlowBench 工作流平台（本地演示版）已启动")
    print(f"  画布视图:  http://127.0.0.1:{PORT}")
    print(f"  LLM 模式:  {CONFIG.get('llm_mode', 'demo')}"
          + ("（内置演示模式，零配置可跑通）" if CONFIG.get("llm_mode", "demo") == "demo" else ""))
    print(f"  种子数据:  商品 {len(PRODUCTS)} 条 / 评价 {len(REVIEWS)} 条")
    print("  停止: Ctrl+C")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
