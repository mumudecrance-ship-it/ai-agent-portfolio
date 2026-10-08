#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S7-b：触发试运行 + 回读断言 + 生成跑通报告。
用法: python scripts/platform_run.py <任务名> [平台base]
输入: ../runs/{任务}/08-测试输入.json  格式:
  {"cases": [{"name": "...", "inputs": {...}, "expect": {"outputs.字段": 期望值}, "expect_fail": false}]}
产物: ../runs/{任务}/08-跑通报告.md（含逐节点流水与失败定位）
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def call(base, method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get(d, dotted):
    cur = d
    for k in dotted.split("."):
        cur = (cur or {}).get(k) if isinstance(cur, dict) else None
    return cur


def main(task, base="http://127.0.0.1:8787"):
    rundir = ROOT.parent / "runs" / task
    deploy = json.loads((rundir / "07a-部署结果.json").read_text(encoding="utf-8"))
    app_id = deploy["import"]["app_id"]
    cases = json.loads((rundir / "08-测试输入.json").read_text(encoding="utf-8"))["cases"]
    lines = [f"# S7 跑通报告 · {task}", "", f"- 平台：{base} · app_id：{app_id}", ""]
    all_ok = True
    for c in cases:
        r = call(base, "POST", "/workflows/run", {"app_id": app_id, "inputs": c["inputs"]})
        back = call(base, "GET", f"/workflows/run/{r['run_id']}")
        ok = back["status"] == ("failed" if c.get("expect_fail") else "succeeded")
        detail = []
        for key, want in (c.get("expect") or {}).items():
            got = get(back, key)
            hit = str(got) == str(want)
            ok = ok and hit
            detail.append(f"    - 断言 `{key}` = `{want}` → 实际 `{got}` {'✅' if hit else '❌'}")
        all_ok = all_ok and ok
        lines.append(f"## 用例：{c['name']} — {'✅ 通过' if ok else '❌ 未过'}")
        lines.append(f"- run_id `{r['run_id']}` · {back['status']} · {back['elapsed_ms']}ms")
        if back.get("error"):
            failed = [nr for nr in back["node_runs"] if nr["status"] == "failed"]
            loc = failed[0] if failed else {}
            lines.append(f"- 节点级报错：`{loc.get('node_id')}`（{loc.get('title')}）：{loc.get('error')}")
        lines += detail
        lines.append("- 节点流水：" + " → ".join(
            f"{nr['title']}{'✓' if nr['status']=='succeeded' else '✕'}" for nr in back["node_runs"]))
        lines.append("")
    lines.append(f"## 结论：{'✅ 跑通（全部用例通过）' if all_ok else '❌ 未跑通'}")
    (rundir / "08-跑通报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(("✅ S7 跑通" if all_ok else "❌ S7 未跑通") + f"，报告：../runs/{task}/08-跑通报告.md")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main(*sys.argv[1:])
