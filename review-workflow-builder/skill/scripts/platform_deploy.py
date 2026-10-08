#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S7-a：把 ../runs/{任务}/07-dsl.json 导入平台并发布，取回 app_id。
用法: python scripts/platform_deploy.py <任务名> [平台base，默认 http://127.0.0.1:8787]
产物: ../runs/{任务}/07a-部署结果.json（app_id / version / 导入校验错误）
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
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code


def main(task, base="http://127.0.0.1:8787"):
    dsl_file = ROOT.parent / "runs" / task / "07-dsl.json"
    if not dsl_file.exists():
        sys.exit(f"❌ 产物缺失：{dsl_file}")
    defn = json.loads(dsl_file.read_text(encoding="utf-8"))
    imp, code = call(base, "POST", "/apps/imports", {"definition": defn})
    result = {"base": base, "import": imp}
    if code != 201:
        (ROOT.parent / "runs" / task / "07a-部署结果.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("❌ 导入失败（平台校验错误）：")
        [print("  -", e) for e in imp.get("errors", [imp])]
        sys.exit(1)
    app_id = imp["app_id"]
    pub, _ = call(base, "POST", f"/apps/{app_id}/publish")
    result["publish"] = pub
    (ROOT.parent / "runs" / task / "07a-部署结果.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 导入并发布成功：app_id={app_id} v{pub.get('version')}")


if __name__ == "__main__":
    main(*sys.argv[1:])
