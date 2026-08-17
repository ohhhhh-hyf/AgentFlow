"""last_class —— 图表渲染层（SVG / conic-gradient 饼图）。

从 display.py 拆出：考点分布热力图、题型分布饼图、考点关系图、自测流程图。
本模块自包含公共小工具（_clean / _wrap_chars / _svg_multiline），
display.py 单向依赖本模块。
"""
from __future__ import annotations

import json
import math
import re
from html import escape
from typing import Any


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _wrap_chars(text: str, max_chars: int) -> list[str]:
    raw = _clean(text)
    if not raw:
        return []
    return [raw[i : i + max_chars] for i in range(0, len(raw), max_chars)]


def _svg_multiline(
    text: str,
    *,
    x: int,
    y: int,
    max_chars: int,
    max_lines: int,
    size: int = 12,
    fill: str = "#1c1b19",
    weight: str = "400",
    anchor: str = "start",
    ellipsis: bool = False,
) -> str:
    """SVG 文本换行。默认写全，不截成省略号。"""
    raw = _clean(text)
    if not raw:
        return ""
    lines = _wrap_chars(raw, max_chars)
    if ellipsis and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1][:-1] + "…"
    else:
        lines = lines[:max_lines] if max_lines else lines
    tspans = "".join(
        f'<tspan x="{x}" dy="{0 if i == 0 else size + 4}">{escape(line, quote=False)}</tspan>'
        for i, line in enumerate(lines)
    )
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}">{tspans}</text>'
    )


def _pie(payload: str, *, card_class: str, pie_class: str, colors: list[str]) -> str:
    """通用 conic-gradient 饼图（含图例）。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, list):
        return ""
    rows: list[tuple[str, float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label"))
        try:
            value = float(item.get("value") or 0)
        except (TypeError, ValueError):
            value = 0.0
        if label and value > 0:
            rows.append((label, value))
    if len(rows) < 2:
        return ""

    total = sum(value for _label, value in rows) or 1.0
    cursor = 0.0
    segments: list[str] = []
    legend: list[str] = []
    for idx, (label, value) in enumerate(rows):
        start = cursor
        cursor += value / total * 100
        color = colors[idx % len(colors)]
        segments.append(f"{color} {start:.2f}% {cursor:.2f}%")
        legend.append(
            '<div class="lc-legend-item">'
            f'<span class="lc-dot" style="background:{color}"></span>'
            f'<span>{escape(label, quote=False)}</span>'
            f"<strong>{value:g}%</strong>"
            "</div>"
        )
    gradient = ", ".join(segments)
    return (
        f'<div class="{card_class}">'
        f'<div class="{pie_class}" style="background: conic-gradient({gradient});"></div>'
        f'<div class="lc-legend">{"".join(legend)}</div>'
        "</div>"
    )


def _render_heatmap_chart(payload: str) -> str:
    """考点分布热力图（章节或知识点占比饼图）。"""
    return _pie(
        payload,
        card_class="lc-heatmap-card",
        pie_class="lc-pie",
        colors=["#b3402e", "#c98a2d", "#497a78", "#6f5f90", "#7a867c", "#395f8a"],
    )


def _render_qtype_chart(payload: str) -> str:
    """单个知识点的题型分布饼图（对应考点，非全局）。"""
    return _pie(
        payload,
        card_class="lc-qtype-card",
        pie_class="lc-pie-sm",
        colors=["#395f8a", "#c98a2d", "#497a78", "#6f5f90", "#b3402e", "#7a867c"],
    )


def _render_relations_svg(payload: str) -> str:
    """考点关系图：优先沿用知识图谱（knowledge_graph）的 graphviz 风格渲染。

    数据格式与 knowledge_graph.nodes_edges_to_dot 对齐：
    节点按 degree 分组着色（必考/重点/了解 = 不同 section 色），
    前置关系标「前置」、对比/同考法沿用 relate 自带标签；
    graphviz 不可用/失败时降级为本地简化分列图。
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    points = data.get("points") or []
    prereq = data.get("prereq") or []
    relate = data.get("relate") or []
    nodes = [
        {"name": str(p.get("name") or "").strip(), "section": str(p.get("degree") or "重点")}
        for p in points
        if isinstance(p, dict) and str(p.get("name") or "").strip()
    ]
    if not nodes:
        return ""
    edges: list[dict[str, str]] = []
    for a, b in prereq or []:
        if a in {n["name"] for n in nodes} and b in {n["name"] for n in nodes}:
            edges.append({"source": str(a), "target": str(b), "relation": "前置"})
    for item in relate or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        a, b = str(item[0]), str(item[1])
        label = str(item[2]) if len(item) > 2 and str(item[2]).strip() else "相关"
        if a in {n["name"] for n in nodes} and b in {n["name"] for n in nodes}:
            edges.append({"source": a, "target": b, "relation": label})
    from tools.knowledge_graph import render_graph_to_svg_text

    svg = render_graph_to_svg_text(
        nodes,
        edges,
        title="考点关系图",
        node_fontsize=11,
        edge_fontsize=10,
        label_width=6,
        compact=True,
    )
    if svg:
        return _graphviz_svg_inline(svg)
    return _render_relations_svg_fallback(payload)


def _graphviz_svg_inline(svg: str) -> str:
    """graphviz SVG 内联自适应：去掉固定像素尺寸，保留 viewBox。"""
    svg = re.sub(
        r'<svg width="[^"]*" height="[^"]*"',
        '<svg style="max-width:100%;height:auto"',
        svg,
        count=1,
    )
    return f'<div class="lc-relations-gv">{svg}</div>'


def _render_relations_svg_fallback(payload: str) -> str:
    """考点关系图：按了解→重点→必考分列，圆角卡片写全名，箭头接到边框。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    points = data.get("points") or []
    prereq = data.get("prereq") or []
    relate = data.get("relate") or []
    if not points:
        return ""

    nodes = [
        {
            "name": str(p.get("name") or "").strip(),
            "degree": str(p.get("degree") or "重点"),
        }
        for p in points
        if isinstance(p, dict) and str(p.get("name") or "").strip()
    ]
    if not nodes:
        return ""

    layers: dict[str, list[dict[str, str]]] = {"了解": [], "重点": [], "必考": []}
    for node in nodes:
        layers.get(node["degree"], layers["重点"]).append(node)
    if not any(layers.values()):
        return ""
    order = [key for key in ("了解", "重点", "必考") if layers[key]]
    if len(order) == 1:
        # 单层时拆成上下两列，避免一条竖线
        only = layers[order[0]]
        mid = max(1, math.ceil(len(only) / 2))
        order = ["左", "右"]
        layers = {"左": only[:mid], "右": only[mid:] or only[:1]}

    box_w, max_chars = 196, 9

    def _box_h(name: str) -> int:
        nline = max(1, len(_wrap_chars(name, max_chars)))
        return 22 + nline * 16 + 18

    col_gap = 86
    width = 36 + len(order) * box_w + (len(order) - 1) * col_gap + 36
    col_heights = [
        72 + sum(_box_h(n["name"]) + 18 for n in layers[col])
        for col in order
    ]
    height = max(col_heights) if col_heights else 360
    fills = {"必考": "#fff1ee", "重点": "#eef7f1", "了解": "#fff8e8", "左": "#f7f5f0", "右": "#f7f5f0"}
    strokes = {"必考": "#b3402e", "重点": "#3d6b52", "了解": "#b07a20", "左": "#8a867c", "右": "#8a867c"}
    col_x = {col: 36 + i * (box_w + col_gap) for i, col in enumerate(order)}
    boxes: dict[str, tuple[int, int, int, int]] = {}
    for col in order:
        y = 64
        for node in layers[col]:
            h = _box_h(node["name"])
            boxes[node["name"]] = (col_x[col], y, box_w, h)
            y += h + 18

    def _port(name: str, toward: str) -> tuple[int, int]:
        x, y, w, h = boxes[name]
        tx, ty, tw, th = boxes[toward]
        cx1, cy1 = x + w / 2, y + h / 2
        cx2, cy2 = tx + tw / 2, ty + th / 2
        if abs(cx2 - cx1) >= abs(cy2 - cy1):
            if cx2 >= cx1:
                return int(x + w), int(cy1)
            return int(x), int(cy1)
        if cy2 >= cy1:
            return int(cx1), int(y + h)
        return int(cx1), int(y)

    parts: list[str] = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'xmlns="http://www.w3.org/2000/svg" font-family="sans-serif" '
        'class="lc-graph-svg" style="max-width:100%;height:auto;display:block;margin:8px 0;">',
        "<defs>",
        '<marker id="lc-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#3d5a80"/></marker>',
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="#fbfaf7" stroke="#ebe8e1"/>',
        '<text x="20" y="28" font-size="13" font-weight="700" fill="#3a3832">考点关系 · 从左到右推进</text>',
        '<text x="20" y="46" font-size="11" fill="#6b6860">实线：先会再攻　虚线：对比 / 同考法　颜色：了解 / 重点 / 必考</text>',
    ]
    for col in order:
        label = col if col in {"了解", "重点", "必考"} else ""
        if label:
            parts.append(
                f'<text x="{col_x[col] + box_w // 2}" y="58" text-anchor="middle" '
                f'font-size="12" font-weight="700" fill="{strokes.get(col, "#6b6860")}">{label}</text>'
            )
    for a, b in prereq:
        if a in boxes and b in boxes and a != b:
            x1, y1 = _port(a, b)
            x2, y2 = _port(b, a)
            parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                'stroke="#3d5a80" stroke-width="1.8" marker-end="url(#lc-arrow)"/>'
            )
    for item in relate:
        a, b = item[0], item[1]
        if a in boxes and b in boxes and a != b:
            x1, y1 = _port(a, b)
            x2, y2 = _port(b, a)
            parts.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                'stroke="#9a968c" stroke-width="1.3" stroke-dasharray="5 4"/>'
            )
    for node in nodes:
        name = node["name"]
        if name not in boxes:
            continue
        x, y, w, h = boxes[name]
        deg = node["degree"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
            f'fill="{fills.get(deg, "#f7f5f0")}" stroke="{strokes.get(deg, "#8a867c")}" stroke-width="1.6"/>'
        )
        nline = max(1, len(_wrap_chars(name, max_chars)))
        text_y = y + (h - nline * 16) // 2 + 13
        parts.append(
            _svg_multiline(
                name,
                x=x + w // 2,
                y=text_y,
                max_chars=max_chars,
                max_lines=nline,
                size=13,
                weight="700",
                anchor="middle",
            )
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _render_selfcheck_svg(payload: str) -> str:
    """自测有向图：每列一个阶段，每个节点写清要解决的问题，全文换行、不截省略号。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    phases = [p for p in (data.get("phases") or []) if p.get("checks")]
    if not phases:
        return ""

    phases = phases[:4]
    colors = ["#395f8a", "#497a78", "#6f5f90", "#b3402e"]
    col_w, gap, max_chars = 248, 36, 13
    node_pad = 12
    line_h = 16

    def _node_h(text: str) -> int:
        return 16 + max(1, len(_wrap_chars(text, max_chars))) * line_h + 12

    col_heights = []
    for ph in phases:
        checks = [_clean(c) for c in (ph.get("checks") or []) if _clean(c)][:5]
        col_heights.append(56 + sum(_node_h(c) + 14 for c in checks))
    width = 20 + len(phases) * col_w + max(0, len(phases) - 1) * gap + 20
    height = max(col_heights) + 24 if col_heights else 240

    parts: list[str] = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'xmlns="http://www.w3.org/2000/svg" font-family="sans-serif" '
        'class="lc-selfcheck-svg" style="max-width:100%;height:auto;display:block;margin:8px 0;">',
        '<defs><marker id="lc-flow-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="16" fill="#fbfaf7" stroke="#ebe8e1"/>',
    ]
    layouts: list[dict[str, Any]] = []
    for i, ph in enumerate(phases):
        checks = [_clean(c) for c in (ph.get("checks") or []) if _clean(c)][:5]
        x = 20 + i * (col_w + gap)
        y = 42
        nodes = []
        for cp in checks:
            h = _node_h(cp)
            nodes.append({"text": cp, "x": x, "y": y, "h": h})
            y += h + 14
        layouts.append(
            {
                "label": str(ph.get("label") or f"阶段{i + 1}"),
                "color": colors[i % len(colors)],
                "x": x,
                "nodes": nodes,
            }
        )
    for i, col in enumerate(layouts):
        color = col["color"]
        x = col["x"]
        parts.append(
            f'<text x="{x + col_w // 2}" y="28" text-anchor="middle" font-size="13" '
            f'font-weight="700" fill="{color}">{escape(col["label"], quote=False)}</text>'
        )
        for j, node in enumerate(col["nodes"]):
            parts.append(
                f'<rect x="{node["x"]}" y="{node["y"]}" width="{col_w}" height="{node["h"]}" '
                f'rx="10" fill="#fff" stroke="{color}" stroke-width="1.5"/>'
            )
            parts.append(
                _svg_multiline(
                    node["text"],
                    x=node["x"] + node_pad,
                    y=node["y"] + 18,
                    max_chars=max_chars,
                    max_lines=8,
                    size=12,
                    fill="#1c1b19",
                )
            )
            if j < len(col["nodes"]) - 1:
                nxt = col["nodes"][j + 1]
                parts.append(
                    f'<line x1="{x + col_w // 2}" y1="{node["y"] + node["h"]}" '
                    f'x2="{x + col_w // 2}" y2="{nxt["y"]}" '
                    'stroke="#8a867c" stroke-width="1.4" marker-end="url(#lc-flow-arrow)"/>'
                )
        if i < len(layouts) - 1 and col["nodes"] and layouts[i + 1]["nodes"]:
            src = col["nodes"][0]
            dst = layouts[i + 1]["nodes"][0]
            parts.append(
                f'<line x1="{col["x"] + col_w}" y1="{src["y"] + src["h"] // 2}" '
                f'x2="{dst["x"]}" y2="{dst["y"] + dst["h"] // 2}" '
                'stroke="#64748b" stroke-width="1.8" marker-end="url(#lc-flow-arrow)"/>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


__all__ = [
    "_render_heatmap_chart",
    "_render_qtype_chart",
    "_render_relations_svg",
    "_render_selfcheck_svg",
]
