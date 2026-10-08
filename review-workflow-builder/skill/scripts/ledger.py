#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产台账：任务状态的权威数据源。一切状态读写经本脚本，Markdown 视图只读渲染。

用法（在 skill 根目录执行；runs/ 生成在 skill 上一级，与 skill 平级）:
  python scripts/ledger.py init <任务名>                # 初始化台账
  python scripts/ledger.py status <任务名>              # 查看当前状态
  python scripts/ledger.py pass <任务名> <步骤> [备注]   # 门禁通过，推进到下一步
  python scripts/ledger.py fail <任务名> <步骤> <原因>   # 记录门禁失败
  python scripts/ledger.py render <任务名>              # 重新渲染只读进度视图
  python scripts/ledger.py reopen <任务名> <步骤> <归因文件名>
      # 问题回流：仅 DONE 任务可重开。前置条件是 bad-case 归因文件过 check_attribution.py 门禁，
      # 且目标步骤与归因定位一致；重开步骤起旧产物归档 _history/<时间戳>/，下游步骤级联置为待开始。
"""
import json
import sys
import time
from pathlib import Path

STEPS = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
STEP_META = {
    "S1": ("业务澄清", "01-工作流画像.md", "check_profile.py"),
    "S2": ("依赖分析", "02-依赖清单.md", "check_dependencies.py"),
    "S3": ("流程拆解与设计审查", "03-流程拆解.md", "check_decomposition.py"),
    "S4": ("节点映射", "04-节点方案.md", "validate_solution.py"),
    "S5": ("prompt起草", "05-prompts/", "schema 完整性校验"),
    "S6": ("方法论审查", "06-审查报告.md", "五条清零"),
    "S7": ("平台落地跑通", "07-dsl.json + 08-跑通报告.md", "platform_deploy.py + platform_run.py"),
}
ROOT = Path(__file__).resolve().parent.parent
# reopen 归档用：每步的全部产物（STEP_META 的产物列串不可靠拆分，S7 是多文件）
STEP_ARTIFACTS = {
    "S1": ["01-工作流画像.md"],
    "S2": ["02-依赖清单.md"],
    "S3": ["03-流程拆解.md"],
    "S4": ["04-节点方案.md"],
    "S5": ["05-prompts"],
    "S6": ["06-审查报告.md"],
    "S7": ["07-dsl.json", "07a-部署结果.json", "08-测试输入.json", "08-跑通报告.md", "09-画布.html"],
}


def path_of(task):
    return ROOT.parent / "runs" / task / "ledger.json"


def load(task):
    p = path_of(task)
    if not p.exists():
        sys.exit(f"台账不存在：{p}（先 init）")
    return json.loads(p.read_text(encoding="utf-8"))


def save(task, data):
    p = path_of(task)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)  # 原子写，防误覆盖
    render(task, data)


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def init(task):
    p = path_of(task)
    if p.exists():
        sys.exit(f"台账已存在，拒绝覆盖：{p}")
    data = {"task": task, "created_at": now(), "current_step": "S1",
            "steps": {s: {"name": STEP_META[s][0], "artifact": STEP_META[s][1],
                          "gate": STEP_META[s][2], "status": "pending",
                          "passed_at": None, "note": ""} for s in STEPS},
            "history": [{"at": now(), "event": "init"}]}
    data["steps"]["S1"]["status"] = "in_progress"
    save(task, data)
    print(f"已初始化：../runs/{task}/ledger.json，当前步骤 S1")


def gate_pass(task, step, note=""):
    data = load(task)
    if step != data["current_step"]:
        sys.exit(f"拒绝：当前步骤是 {data['current_step']}，不能跳到 {step}（流程不许跳步）")
    art = ROOT.parent / "runs" / task / STEP_META[step][1].split(" ")[0]
    if not art.exists():
        sys.exit(f"拒绝：产物缺失 {art}（产物落文件后才能过门禁）")
    data["steps"][step].update(status="passed", passed_at=now(), note=note)
    data["history"].append({"at": now(), "event": f"{step} passed", "note": note})
    idx = STEPS.index(step)
    if idx + 1 < len(STEPS):
        nxt = STEPS[idx + 1]
        data["current_step"] = nxt
        data["steps"][nxt]["status"] = "in_progress"
        print(f"{step} 通过 → 推进到 {nxt}（{STEP_META[nxt][0]}）")
    else:
        data["current_step"] = "DONE"
        print(f"{step} 通过 → 全流程完成")
    save(task, data)


def gate_fail(task, step, reason):
    data = load(task)
    data["steps"][step]["status"] = "failed"
    data["steps"][step]["note"] = reason
    data["history"].append({"at": now(), "event": f"{step} failed", "note": reason})
    save(task, data)
    print(f"{step} 门禁未过：{reason}（修复后重跑门禁）")


def reopen(task, step, attribution):
    data = load(task)
    if data["current_step"] != "DONE":
        sys.exit(f"拒绝：当前步骤是 {data['current_step']}，只有 DONE 的任务可 reopen（未完成任务按门禁在原地修）")
    if step not in STEPS:
        sys.exit(f"拒绝：无效步骤 {step}")
    from check_attribution import validate
    errs, located = validate(task, attribution)
    if errs:
        print("拒绝：归因文件未过门禁：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    if located != step:
        sys.exit(f"拒绝：归因定位的第一次偏离步骤是 {located}，与 reopen 目标 {step} 不一致（按归因结论重开）")
    rundir = ROOT.parent / "runs" / task
    stamp = time.strftime("%Y%m%d%H%M%S")
    hist = rundir / "_history" / stamp
    hist.mkdir(parents=True, exist_ok=True)
    moved = []
    for s in STEPS[STEPS.index(step):]:
        for name in STEP_ARTIFACTS[s]:
            src = rundir / name
            if src.exists():
                src.rename(hist / name)
                moved.append(name)
        data["steps"][s].update(status="pending", passed_at=None, note="")
    data["current_step"] = step
    data["steps"][step]["status"] = "in_progress"
    data["history"].append({"at": now(), "event": f"reopen {step}",
                            "note": f"归因：bad-case/{attribution}；归档：_history/{stamp}/（{len(moved)} 项）"})
    save(task, data)
    print(f"已重开 {step}（{STEP_META[step][0]}）：{step} 起旧产物归档到 _history/{stamp}/，"
          f"下游步骤级联置为待开始；从 {step} 按原门禁重走到 S7，跑通才算迭代完成")


def status(task):
    data = load(task)
    print(f"任务：{task}  当前：{data['current_step']}")
    for s in STEPS:
        st = data["steps"][s]
        mark = {"passed": "✅", "in_progress": "▶", "failed": "❌", "pending": "·"}[st["status"]]
        print(f"  {mark} {s} {st['name']}  {st['status']}" + (f"  {st['note']}" if st["note"] else ""))


def render(task, data=None):
    data = data or load(task)
    lines = [f"# 进度视图（只读，由 ledger.py 渲染） · {task}", "",
             f"> 权威数据源：`ledger.json`。本文件手改无效，会被覆盖。",
             f"> 当前步骤：**{data['current_step']}** · 渲染时间：{now()}", "",
             "| 步骤 | 名称 | 产物 | 门禁 | 状态 | 通过时间 |", "|---|---|---|---|---|---|"]
    for s in STEPS:
        st = data["steps"][s]
        mk = {"passed": "✅ 通过", "in_progress": "▶ 进行中", "failed": "❌ 未过", "pending": "待开始"}[st["status"]]
        lines.append(f"| {s} | {st['name']} | `{st['artifact']}` | {st['gate']} | {mk} | {st['passed_at'] or '—'} |")
    lines += ["", "## 事件流水", ""]
    for h in data["history"][-20:]:
        lines.append(f"- {h['at']} · {h['event']}" + (f" · {h.get('note')}" if h.get("note") else ""))
    (ROOT.parent / "runs" / task / "进度视图.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, task = sys.argv[1], sys.argv[2]
    if cmd == "init":
        init(task)
    elif cmd == "status":
        status(task)
    elif cmd == "pass":
        gate_pass(task, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "fail":
        gate_fail(task, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "未注明")
    elif cmd == "render":
        render(task)
    elif cmd == "reopen":
        if len(sys.argv) < 5:
            sys.exit("用法：python scripts/ledger.py reopen <任务名> <步骤> <bad-case归因文件名>")
        reopen(task, sys.argv[3], sys.argv[4])
    else:
        sys.exit(__doc__)
