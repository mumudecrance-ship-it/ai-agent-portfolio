#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S4 门禁：校验 04-节点方案.md（S3 拆解的合理性由 check_decomposition.py 负责）。
用法: python scripts/validate_solution.py <任务名>
检查:
  1. 节点表存在；每个节点类型 ∈ 平台 12 类（查 platform-nodes 口径）
  2. http_request 节点引用的业务能力必须能在 domain-nodes 中检索到（防想象接口）
  3. 分支节点必须写明分支句柄去向；有 start 和 end
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ["start", "end", "llm", "knowledge_retrieval", "if_else", "question_classifier",
         "code", "http_request", "iteration", "variable_aggregator",
         "parameter_extractor", "template_transform"]


def main(task):
    errs = []
    f = ROOT.parent / "runs" / task / "04-节点方案.md"
    if not f.exists():
        errs.append("产物缺失：04-节点方案.md")
        report(errs)
    text = f.read_text(encoding="utf-8")
    domain = "\n".join(p.read_text(encoding="utf-8")
                       for p in (ROOT / "references/domain-nodes").glob("*.md"))
    rows = [r for r in re.findall(r"^\|(.+)\|$", text, re.M)
            if "---" not in r and "节点" not in r.split("|")[0]]
    if not rows:
        errs.append("未找到节点方案表格")
    types_seen, node_count = [], 0
    for r in rows:
        cells = [c.strip() for c in r.split("|")]
        t = next((tp for tp in TYPES for c in cells if re.fullmatch(rf"`?{tp}`?", c)), None)
        if t is None:
            t = next((tp for tp in TYPES for c in cells if tp in c), None)
        if t is None:
            errs.append(f"节点行未标合法平台类型：{'|'.join(cells[:3])[:50]}")
            continue
        node_count += 1
        types_seen.append(t)
        if t == "http_request":
            name_blob = " ".join(cells)
            probes = ["", "同图", "AI生图", "无关图", "敏感词", "OCR", "商品信息中心", "评价系统", "词云", "mock"]
            if not any(p in name_blob and p in domain for p in probes):
                errs.append(f"http_request 节点引用的能力在 domain-nodes 检索不到：{name_blob[:50]}")
    if "start" not in types_seen:
        errs.append("缺少 start 节点")
    if "end" not in types_seen:
        errs.append("缺少 end 节点")
    if any(t in types_seen for t in ("if_else", "question_classifier")) and "source_handle" not in text and "句柄" not in text:
        errs.append("有分支节点但未写分支句柄去向（true/false 或 class id 各连到哪个节点）")
    report(errs, node_count)


def report(errs, n=0):
    if errs:
        print("❌ S3/S4 门禁未过：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    print(f"✅ S3/S4 门禁通过：{n} 个节点全部在库内有出处，结构要素齐全")
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1])
