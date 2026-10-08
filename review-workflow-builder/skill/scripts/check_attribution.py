#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代门禁：校验 bad-case 归因文件——reopen 的前置条件。
用法: python scripts/check_attribution.py <任务名> <归因文件名>
文件位置: ../runs/<任务名>/bad-case/<归因文件名>
检查: 七段齐全 + 五层归因有主因（输入/数据/工具/流程/模型）
     + 第一次偏离步骤属于 S1-S7 + 证据链引用了任务产物文件。
归因文件七段:
  case描述 / 复现输入 / 实际输出 / 期望输出 / 五层归因 / 第一次偏离步骤 / 证据链
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["case描述", "复现输入", "实际输出", "期望输出", "五层归因", "第一次偏离步骤", "证据链"]
LAYERS = "输入|数据|工具|流程|模型"


def validate(task, fname):
    """返回 (errs, located_step)。located_step 是归因定位的第一次偏离步骤（如 'S5'）。"""
    f = ROOT.parent / "runs" / task / "bad-case" / fname
    if not f.exists():
        return [f"归因文件缺失：{f}"], None
    text = f.read_text(encoding="utf-8")
    errs = []
    for k in REQUIRED:
        if k not in text:
            errs.append(f"缺少段落：{k}")
    if not re.search(rf"主因[:：]?\s*[（(]?({LAYERS})", text):
        errs.append("五层归因未标注主因（须为 输入/数据/工具/流程/模型 之一）")
    m = re.search(r"第一次偏离步骤[\s\S]{0,80}?(S[1-7])", text)
    located = m.group(1) if m else None
    if not located:
        errs.append("第一次偏离步骤未定位到 S1-S7 中的某一步")
    ev = re.search(r"证据链([\s\S]*?)(?=\n#|\Z)", text)
    if not ev or not re.search(r"0[1-8]|05-prompts|ledger", ev.group(1)):
        errs.append("证据链未引用任务产物文件（01-08 产物 / 05-prompts / ledger）")
    return errs, located


def main(task, fname):
    errs, located = validate(task, fname)
    if errs:
        print("❌ 归因门禁未过：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    print(f"✅ 归因门禁通过：七段齐全，主因明确，定位到 {located}（reopen 目标步骤须与此一致）")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
