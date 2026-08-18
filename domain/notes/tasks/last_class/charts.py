"""last_class —— 图表渲染层。

考点分布热力图、考点关系图（knowledge_graph 同款 Cytoscape HTML）、
思维导图（meeting/mindmap 同款可编辑 markmap）。
"""
from __future__ import annotations

import json
from html import escape


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


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


def _relations_graph_data(payload: str) -> tuple[list[dict], list[dict]] | None:
    """把 last_class 关系图 payload 转成 knowledge_graph 的 nodes / edges。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    points = data.get("points") or []
    prereq = data.get("prereq") or []
    relate = data.get("relate") or []
    nodes: list[dict] = []
    seen: set[str] = set()
    for point in points:
        if not isinstance(point, dict):
            continue
        name = str(point.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        nodes.append(
            {
                "name": name,
                "section": str(point.get("degree") or "重点").strip() or "重点",
                "definition": str(point.get("definition") or "").strip(),
            }
        )
    if not nodes:
        return None
    names = {node["name"] for node in nodes}
    edges: list[dict] = []
    for item in prereq or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        source, target = str(item[0]).strip(), str(item[1]).strip()
        if source in names and target in names and source != target:
            edges.append({"source": source, "target": target, "relation": "前置"})
    for item in relate or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        source, target = str(item[0]).strip(), str(item[1]).strip()
        label = str(item[2]).strip() if len(item) > 2 and str(item[2]).strip() else "相关"
        if source in names and target in names and source != target:
            edges.append({"source": source, "target": target, "relation": label})
    return nodes, edges


def _render_relations_html(payload: str) -> str:
    """考点关系图：嵌在当前 HTML 里，点击节点看详情。"""
    parsed = _relations_graph_data(payload)
    if not parsed:
        return ""
    nodes, edges = parsed
    from tools.knowledge_graph import build_knowledge_graph_embed

    return build_knowledge_graph_embed(nodes, edges, title="考点关系图")


def _render_mindmap_html(payload: str) -> str:
    """考点思维导图：嵌在当前 HTML 里编辑，保存下载这一份页面。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    outline = str(data.get("outline") or "").strip()
    title = str(data.get("title") or "期末复习思维导图").strip()
    if not outline:
        return ""
    from tools.mindmap import build_editable_mindmap_embed

    return build_editable_mindmap_embed(outline, title=title)


__all__ = [
    "_render_heatmap_chart",
    "_render_relations_html",
    "_render_mindmap_html",
]
