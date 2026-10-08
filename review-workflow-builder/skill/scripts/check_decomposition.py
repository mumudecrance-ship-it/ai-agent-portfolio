#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S3 门禁：校验 03-流程拆解.md——设计审查的主战场。
用法: python scripts/check_decomposition.py <任务名>
检查:
  1. 业务过程还原段存在
  2. 步骤表存在，必备列：步骤/输入/输出/判断类型/失败或拿不准去向
  3. 判断类型 ∈ {传统判断, 接口调用, LLM判定, 人工}
  4. 每个 LLM判定 步骤必须写"为什么非LLM不可"的理由（理由列或独立段落中出现该步骤）
  5. 分支与并行段存在（分流/并行/汇聚交代）
  6. 开销预估段存在且含数量级（数字×频率）
  7. 人审出口：至少一个步骤的去向是 人工/人审/转审
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALID_TYPES = ["传统判断", "接口调用", "LLM判定", "人工"]


def main(task):
    f = ROOT.parent / "runs" / task / "03-流程拆解.md"
    if not f.exists():
        sys.exit(f"❌ 产物缺失：{f}")
    text = f.read_text(encoding="utf-8")
    errs = []

    if not re.search(r"业务过程|过程还原", text):
        errs.append("缺少「业务过程还原」段")
    if not re.search(r"信息件|倒推", text):
        errs.append("缺少「信息件倒推」表（decomposition-guide 第一步）——每个步骤必须可追溯到最终输出")
    # 步骤表定位：表头含"判断类型"的那张表，取其后的连续表行
    lines = text.splitlines()
    rows, header_line, in_table = [], "", False
    for ln in lines:
        if re.match(r"^\|.+\|$", ln):
            body = ln.strip().strip("|")
            if "判断类型" in body:
                header_line, in_table = body, True
                continue
            if in_table:
                if "---" in body:
                    continue
                rows.append(body)
        elif in_table and ln.strip() == "":
            in_table = False
    if not rows:
        errs.append("未找到步骤表（表头须含「判断类型」列）")
    for col in ["输入", "输出", "判断类型", "去向"]:
        if col not in header_line:
            errs.append(f"步骤表缺少列：{col}")

    llm_steps, human_exit = [], False
    for r in rows:
        cells = [c.strip() for c in r.split("|")]
        t = next((v for v in VALID_TYPES for c in cells if v in c), None)
        if t is None:
            errs.append(f"步骤行判断类型非法（应为{VALID_TYPES}）：{'|'.join(cells[:2])[:40]}")
            continue
        if t == "LLM判定":
            llm_steps.append(cells[1] if len(cells) > 1 else r[:20])
        if re.search(r"人工|人审|转审", " ".join(cells)):
            human_exit = True
    for s in llm_steps:
        # 理由可写在行内（含"非LLM"或"理由"）或独立段落中提及该步骤名
        pat_inline = any(s in r and re.search(r"非LLM|语义|理由", r) for r in rows)
        pat_block = re.search(rf"{re.escape(s)}[^\n]*\n[^\n]*(非LLM|语义|无法用规则|传统做不了)", text)
        if not (pat_inline or pat_block):
            errs.append(f"LLM 步骤「{s}」未写『为什么非LLM不可』的理由")
    if not human_exit:
        errs.append("没有任何步骤的去向是人审——缺人审出口")
    if not re.search(r"分支|并行|汇聚", text):
        errs.append("缺少「分支与并行」段（分流/并行/汇聚交代）")
    m = re.search(r"开销预估([\s\S]{0,400})", text)
    if not m:
        errs.append("缺少「开销预估」段")
    elif not re.search(r"\d", m.group(1)):
        errs.append("开销预估段没有任何数量级数字")

    if errs:
        print("❌ S3 门禁未过：")
        [print("  -", e) for e in errs]
        sys.exit(1)
    print(f"✅ S3 门禁通过：{len(rows)} 步，LLM 步骤 {len(llm_steps)} 个均有非LLM不可理由，含人审出口/并行/开销预估")


if __name__ == "__main__":
    main(sys.argv[1])
