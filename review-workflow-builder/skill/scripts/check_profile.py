#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S1 门禁：校验 01-工作流画像.md。
用法: python scripts/check_profile.py <任务名>
检查: 五段齐全 + 每段非空 + S1 红线（画像/提问里不得出现技术词）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["业务问题", "成功标准", "产出对象", "量级", "人审底线"]
TECH_WORDS = ["接口", "数据库", "API", "并发", "表结构", "模型选型", "服务器"]


def main(task):
    f = ROOT.parent / "runs" / task / "01-工作流画像.md"
    if not f.exists():
        sys.exit(f"❌ 产物缺失：{f}")
    text = f.read_text(encoding="utf-8")
    errs = []
    for k in REQUIRED:
        m = re.search(rf"{k}[^\n]*\n+([^\n#]+)", text)
        if k not in text:
            errs.append(f"缺少段落：{k}")
        elif m and len(m.group(1).strip()) < 6:
            errs.append(f"段落「{k}」内容过短（{m.group(1).strip()!r}）")
    ask = re.findall(r"(?:追问|提问|问题)[:：]?(.*)", text)
    for line in ask:
        for w in TECH_WORDS:
            if w in line:
                errs.append(f"S1 红线：向业务方提了技术问题（{w}）：{line.strip()[:40]}")
    if errs:
        print("❌ S1 门禁未过：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    print("✅ S1 门禁通过：画像五段齐全，无技术提问")


if __name__ == "__main__":
    main(sys.argv[1])
