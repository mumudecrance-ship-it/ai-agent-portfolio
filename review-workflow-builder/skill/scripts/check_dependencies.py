#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 门禁：校验 02-依赖清单.md。
用法: python scripts/check_dependencies.py <任务名>
检查: 表格存在；每行状态 ∈ {已有可用, 演示需mock, 缺失需人补}；
     标"已有可用"的能力名必须能在 references/domain-nodes/ 文本中检索到（防想象能力）；
     必须有"用户确认"标记。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALID = ["已有可用", "演示需mock", "缺失需人补"]


def main(task):
    f = ROOT.parent / "runs" / task / "02-依赖清单.md"
    if not f.exists():
        sys.exit(f"❌ 产物缺失：{f}")
    text = f.read_text(encoding="utf-8")
    domain = "\n".join(p.read_text(encoding="utf-8")
                       for p in (ROOT / "references/domain-nodes").glob("*.md"))
    errs = []
    all_rows = [r for r in re.findall(r"^\|(.+)\|$", text, re.M) if "---" not in r]
    # 仅当"状态"作为独立单元格出现才视为表头行
    rows = [r for r in all_rows
            if "状态" not in [c.strip() for c in r.split("|")]]
    if not rows:
        errs.append("未找到依赖清单表格")
    for r in rows:
        cells = [c.strip() for c in r.split("|")]
        if len(cells) < 2:
            continue
        name = cells[0]
        st = next((v for v in VALID for c in cells if v in c), None)
        if st is None:
            errs.append(f"依赖「{name}」状态非法（应为 {VALID}）")
        elif st == "已有可用":
            key = re.sub(r"[（(].*?[）)]", "", name).strip()
            probes = [key] + re.split(r"[-·/ ]", key)
            if not any(p and p in domain for p in probes):
                errs.append(f"依赖「{name}」标已有可用，但 domain-nodes 检索不到——疑似想象能力")
    if "用户确认" not in text:
        errs.append("缺少「用户确认」记录（S2 产物必须带确认状态）")
    if errs:
        print("❌ S2 门禁未过：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    print(f"✅ S2 门禁通过：{len(rows)} 项依赖，状态合法且已有能力皆有出处")


if __name__ == "__main__":
    main(sys.argv[1])
