#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试：导入 → 发布 → 运行 → 回读 → 断言，四段全通即平台可用。
用法: 先启动 python platform.py，再跑 python demo-scripts/smoke_test.py
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8787"
HERE = Path(__file__).resolve().parent


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def check(name, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        sys.exit(1)


def run_case(defn_file, inputs, expect):
    defn = json.loads((HERE / defn_file).read_text(encoding="utf-8"))
    print(f"\n== {defn['app']['name']} ==")
    imp = call("POST", "/apps/imports", {"definition": defn})
    check("导入", imp.get("imported") is True, f"app_id={imp.get('app_id')}")
    app_id = imp["app_id"]
    pub = call("POST", f"/apps/{app_id}/publish")
    check("发布", pub.get("published") is True, f"v{pub.get('version')}")
    run = call("POST", "/workflows/run", {"app_id": app_id, "inputs": inputs})
    check("运行", run.get("status") == "succeeded",
          f"run_id={run.get('run_id')} {run.get('elapsed_ms')}ms"
          + (f" error={run.get('error')}" if run.get("error") else ""))
    back = call("GET", f"/workflows/run/{run['run_id']}")
    check("回读", back.get("status") == "succeeded",
          f"{len(back.get('node_runs', []))} 个节点流水")
    for k, v in expect.items():
        got = back["outputs"].get(k)
        check(f"断言 outputs.{k}={v!r}", str(got) == str(v), f"实际={got!r}")
    return app_id


def run_fail_case():
    """错误注入：mock 接口返回 500，断言失败分支与节点级报错可回读。"""
    defn = json.loads((HERE / "demo_质量管控迷你.json").read_text(encoding="utf-8"))
    defn["app"]["name"] = "错误注入-同图接口500"
    for n in defn["graph"]["nodes"]:
        if n["id"] == "same_img":
            n["config"]["body"]["__inject__"] = "500"
    print(f"\n== {defn['app']['name']} ==")
    imp = call("POST", "/apps/imports", {"definition": defn})
    app_id = imp["app_id"]
    call("POST", f"/apps/{app_id}/publish")
    run = call("POST", "/workflows/run", {"app_id": app_id, "inputs": {
        "review_text": "开放式厨房做饭油烟味半小时就散了，晚上开睡眠档基本听不到声音，只有凑近才有轻微嗡嗡声。App 远程开机很方便，超过六十个字了吧应该。",
        "image_urls": ["img/x.jpg"], "product_id": "100086651001"}})
    check("运行失败(预期)", run.get("status") == "failed", run.get("error", ""))
    back = call("GET", f"/workflows/run/{run['run_id']}")
    failed = [nr for nr in back["node_runs"] if nr["status"] == "failed"]
    check("节点级报错定位", len(failed) == 1 and failed[0]["node_id"] == "same_img",
          f"失败节点={failed[0]['node_id'] if failed else '无'} 错误={failed[0]['error'] if failed else ''}")


if __name__ == "__main__":
    print("FlowBench 冒烟测试（导入/发布/运行/回读 + 断言 + 错误注入）")
    run_case("sample_min.json",
             {"review_text": "这个净化器可真是太棒了啊，棒到我半夜被它的风声吵醒，感谢商家让我体验了守着拖拉机睡觉的感觉。"},
             {"verdict": 1})
    run_case("demo_质量管控迷你.json",
             {"review_text": "开放式厨房做饭油烟味半小时就散了，晚上开睡眠档基本听不到声音，只有凑近才有轻微嗡嗡声。App 远程开机很方便，下班路上打开到家空气就清新了。",
              "image_urls": ["img/u1a.jpg", "img/u1b.jpg"], "product_id": "100086651001"},
             {"quality": "高质量/普通"})
    run_case("demo_质量管控迷你.json",
             {"review_text": "宝贝收到了，质量很好，卖家服务态度好，物流很快，包装严实，值得购买，下次还来。这条评价故意凑到六十个字以上以便走高质量判定分支流程。",
              "image_urls": ["img/tpl-same-1.jpg"], "product_id": "100086651001"},
             {"quality": "低质量"})
    run_fail_case()
    print("\n全部通过 ✅ 平台四段链路（导入/发布/运行/回读）+ 错误注入可用")
