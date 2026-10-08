#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画布快照：把 07-dsl.json 渲染成自包含的静态 HTML（SVG 节点图），不依赖平台运行。
用法: python scripts/render_canvas.py <任务名>
输入: ../runs/<任务名>/07-dsl.json
产物: ../runs/<任务名>/09-画布.html（双击浏览器打开即可看图）
布局: 按依赖关系分层（最长路径），层为列、层内为行；分支边带句柄标签。
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NW, NH, GX, GY, M = 200, 64, 90, 36, 40  # 节点宽高 / 列距 / 行距 / 边距

STYLE = {  # type -> (填充, 描边, 中文名)
    "start": ("#ececec", "#666666", "开始"),
    "end": ("#ececec", "#666666", "结束"),
    "llm": ("#ede4ff", "#7c4dff", "LLM"),
    "http_request": ("#e0efff", "#1976d2", "HTTP请求"),
    "code": ("#dff5f0", "#00897b", "代码执行"),
    "if_else": ("#fff3d6", "#f9a825", "条件分支"),
    "question_classifier": ("#ffe8d9", "#ef6c00", "问题分类器"),
    "knowledge_retrieval": ("#e3f2df", "#43a047", "知识检索"),
    "template_transform": ("#ffe4ec", "#d81b60", "模板转换"),
    "variable_aggregator": ("#e0f7fa", "#00acc1", "变量聚合"),
    "iteration": ("#e4e7ff", "#3f51b5", "迭代"),
    "parameter_extractor": ("#f0f4d0", "#9e9d24", "参数提取"),
}
DEFAULT = ("#f0f0f0", "#888888", "")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def layer_of(nodes, edges):
    """最长路径分层。带环保护（迭代类回边不参与加深）。"""
    preds = {n["id"]: [] for n in nodes}
    for e in edges:
        if e["source"] in preds and e["target"] in preds:
            preds[e["target"]].append(e["source"])
    memo = {}

    def depth(i, stack):
        if i in memo:
            return memo[i]
        if i in stack:
            return 0
        d = 0
        for p in preds[i]:
            d = max(d, depth(p, stack | {i}) + 1)
        memo[i] = d
        return d

    return {n["id"]: depth(n["id"], set()) for n in nodes}


def main(task):
    src = ROOT.parent / "runs" / task / "07-dsl.json"
    if not src.exists():
        sys.exit(f"❌ 缺少 {src}（S7 编译出 dsl 后才能渲染画布）")
    dsl = json.loads(src.read_text(encoding="utf-8"))
    g = dsl.get("graph", dsl)
    nodes, edges = g["nodes"], g["edges"]
    app = (dsl.get("app") or {}).get("name", task)

    lay = layer_of(nodes, edges)
    cols = {}
    for n in nodes:
        cols.setdefault(lay[n["id"]], []).append(n)
    ncols = max(cols) + 1
    nrows = max(len(v) for v in cols.values())
    W = M * 2 + ncols * NW + (ncols - 1) * GX
    H = M * 2 + nrows * NH + (nrows - 1) * GY
    pos = {}
    for c, ns in cols.items():
        x = M + c * (NW + GX)
        top = M + (H - 2 * M - (len(ns) * NH + (len(ns) - 1) * GY)) / 2
        for r, n in enumerate(ns):
            pos[n["id"]] = (x, top + r * (NH + GY))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="PingFang SC, Microsoft YaHei, sans-serif">',
           '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#98a2b3"/></marker></defs>']
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s not in pos or t not in pos:
            continue
        x1, y1 = pos[s][0] + NW, pos[s][1] + NH / 2
        x2, y2 = pos[t][0], pos[t][1] + NH / 2
        dx = max((x2 - x1) / 2, 40)
        svg.append(f'<path d="M{x1:.0f},{y1:.0f} C{x1 + dx:.0f},{y1:.0f} {x2 - dx:.0f},{y2:.0f} {x2:.0f},{y2:.0f}" '
                   f'fill="none" stroke="#98a2b3" stroke-width="1.6" marker-end="url(#a)"/>')
        label = e.get("source_handle") or e.get("handle") or e.get("condition") or e.get("case") or ""
        if label:
            svg.append(f'<text x="{(x1 + x2) / 2:.0f}" y="{(y1 + y2) / 2 - 6:.0f}" font-size="11" fill="#667085" '
                       f'text-anchor="middle">{esc(label)}</text>')
    for n in nodes:
        x, y = pos[n["id"]]
        fill, stroke, zh = STYLE.get(n.get("type", ""), DEFAULT)
        title = n.get("title") or n["id"]
        if len(title) > 13:
            title = title[:12] + "…"
        svg.append(f'<g><rect x="{x:.0f}" y="{y:.0f}" rx="10" width="{NW}" height="{NH}" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="1.5"/>'
                   f'<text x="{x + NW / 2:.0f}" y="{y + 27:.0f}" font-size="14" font-weight="600" fill="#1d2939" '
                   f'text-anchor="middle">{esc(title)}</text>'
                   f'<text x="{x + NW / 2:.0f}" y="{y + 47:.0f}" font-size="11" fill="{stroke}" '
                   f'text-anchor="middle">{esc(zh or n.get("type", ""))}</text></g>')
    svg.append("</svg>")

    seen = []
    for n in nodes:
        tp = n.get("type", "")
        if tp not in seen:
            seen.append(tp)
    chips = "".join(
        f'<span style="display:inline-block;margin:0 10px 6px 0;font-size:12px;color:#475467">'
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;'
        f'background:{STYLE.get(t, DEFAULT)[0]};border:1.5px solid {STYLE.get(t, DEFAULT)[1]}"></span> '
        f'{esc(STYLE.get(t, DEFAULT)[2] or t)}</span>' for t in seen)

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>画布快照 · {esc(task)}</title>
<style>body{{margin:0;padding:24px;background:#f8fafc;font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:#1d2939}}
.wrap{{overflow:auto;background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:12px}}
h1{{font-size:18px;margin:0 0 4px}}p{{font-size:12px;color:#667085;margin:0 0 12px}}</style></head><body>
<h1>{esc(app)}</h1>
<p>任务：{esc(task)} · {len(nodes)} 节点 / {len(edges)} 连线 · 静态快照（由 render_canvas.py 依据 07-dsl.json 生成，{time.strftime("%Y-%m-%d %H:%M")}）·
试运行请起 FlowBench 平台导入 07-dsl.json</p>
<div>{chips}</div>
<div class="wrap">{"".join(svg)}</div>
</body></html>
"""
    out = ROOT.parent / "runs" / task / "09-画布.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 画布快照已生成：../runs/{task}/09-画布.html（{len(nodes)} 节点 / {len(edges)} 连线）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
