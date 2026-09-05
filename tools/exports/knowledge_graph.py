"""graph.py —— 知识图谱渲染（Cytoscape.js 交互 HTML + 学习地图）。

把图数据（nodes + edges）渲染为交互 HTML / 学习地图 Markdown：

- 产物：Cytoscape.js 交互演示页（单文件离线 HTML）；节点带定义 tooltip，
  边带关系 label；附学习地图 Markdown 大纲
- 设计约束：
  - 渲染前过滤悬空边（source/target 不在 nodes 中），HTML 仍尽量生成
  - 全流程确定性、零 LLM、零外部进程
"""
from __future__ import annotations

import logging
from html import escape
from json import dumps
from pathlib import Path

logger = logging.getLogger(__name__)

_SECTION_COLORS = [
    ("#e0f2fe", "#38bdf8"),
    ("#dcfce7", "#22c55e"),
    ("#fef3c7", "#f59e0b"),
    ("#fee2e2", "#fb7185"),
    ("#ede9fe", "#8b5cf6"),
    ("#ccfbf1", "#14b8a6"),
]
_RELATION_COLORS = {
    "包含": "#64748b",
    "属于": "#64748b",
    "用于": "#2563eb",
    "定义": "#16a34a",
    "前提": "#ea580c",
    "前置": "#ea580c",
    "等价于": "#9333ea",
    "转化": "#0f766e",
    "区别于": "#c026d3",
    "导致": "#dc2626",
    "相关": "#475569",
    "对比/配套": "#0f766e",
    "同考法": "#475569",
    "互相支撑": "#9333ea",
}
_DASHED_RELATIONS = {"相关", "示例", "对比/配套", "同考法", "互相支撑"}
_CYTOSCAPE_CDN = "https://cdn.jsdelivr.net/npm/cytoscape@3.31.2/dist/cytoscape.min.js"


def _clean_node(node: dict) -> dict[str, str]:
    return {
        "name": str(node.get("name") or "").strip(),
        "type": str(node.get("type") or "").strip() or "concept",
        "definition": str(node.get("definition") or "").strip(),
        "section": str(node.get("section") or "").strip() or "未分组",
        "origin": str(node.get("origin") or "").strip(),
    }


def _clean_edge(edge: dict) -> dict[str, str]:
    return {
        "source": str(edge.get("source") or "").strip(),
        "relation": str(edge.get("relation") or "").strip() or "相关",
        "target": str(edge.get("target") or "").strip(),
        "evidence": str(edge.get("evidence") or "").strip(),
    }


def _incident_edges(
    name: str, edges: list[dict]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    outgoing: list[dict[str, str]] = []
    incoming: list[dict[str, str]] = []
    for raw in edges:
        edge = _clean_edge(raw)
        if edge["source"] == name and edge["target"]:
            outgoing.append(edge)
        if edge["target"] == name and edge["source"]:
            incoming.append(edge)
    return outgoing, incoming


def build_learning_map(
    nodes: list[dict],
    edges: list[dict] | None = None,
    title: str = "",
) -> str:
    """按章节拼「概念 + 关系 + 证据」学习地图（不调 LLM）。"""
    heading = (title or "").strip() or "知识图谱"
    cleaned = [_clean_node(node) for node in (nodes or []) if _clean_node(node)["name"]]
    if not cleaned:
        return f"# {heading}"
    names = {node["name"] for node in cleaned}
    usable_edges = [
        _clean_edge(edge)
        for edge in (edges or [])
        if _clean_edge(edge)["source"] in names and _clean_edge(edge)["target"] in names
    ]
    sections: list[str] = []
    grouped: dict[str, list[dict[str, str]]] = {}
    for node in cleaned:
        grouped.setdefault(node["section"], []).append(node)
        if node["section"] not in sections:
            sections.append(node["section"])
    lines = [f"# {heading}", ""]
    for section in sections:
        lines.append(f"## {section}")
        lines.append("")
        for node in grouped[section]:
            suffix = "（新增）" if str(node.get("origin") or "") == "new" else ""
            lines.append(f"### {node['name']}{suffix}")
            lines.append(f"- 定义：{node['definition'] or '原文未给出独立定义'}")
            outgoing, incoming = _incident_edges(node["name"], usable_edges)
            if outgoing or incoming:
                lines.append("- 关系：")
                for edge in outgoing:
                    lines.append(
                        f"  - {edge['source']} → {edge['relation']} → {edge['target']}"
                    )
                    if edge["evidence"]:
                        lines.append(f"    - 证据：{edge['evidence']}")
                for edge in incoming:
                    if edge in outgoing:
                        continue
                    lines.append(
                        f"  - {edge['source']} → {edge['relation']} → {edge['target']}"
                    )
                    if edge["evidence"]:
                        lines.append(f"    - 证据：{edge['evidence']}")
            else:
                lines.append("- 关系：暂无有据边")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _node_degrees(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    names = {
        str(node.get("name") or "").strip()
        for node in nodes
        if str(node.get("name") or "").strip()
    }
    degrees = {name: 0 for name in names}
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source in degrees and target in degrees:
            degrees[source] += 1
            degrees[target] += 1
    return degrees


def _is_section_anchor(node: dict) -> bool:
    name = str(node.get("name") or "").strip()
    section = str(node.get("section") or "").strip()
    return bool(name and section and name == section)


def _calculate_node_dimension(
    name: str,
    degree: int = 1,
    max_degree: int = 1,
    is_anchor: bool = False,
) -> dict:
    """计算能完全包裹住所有文字的节点尺寸、换行文本与最大换行宽度。"""
    import math

    n = len(name)
    font_size = 15 if is_anchor else 12.5
    char_w = font_size * 1.06
    line_h = font_size * 1.36

    # 1. 动态确定每行最适字符数，使长文本尽量呈现规整居中的矩形
    if n <= 4:
        chars_per_line = n
    elif n <= 7:
        chars_per_line = 3 if n in (5, 6) else 4
    elif n <= 10:
        chars_per_line = (n + 1) // 2
    elif n <= 15:
        chars_per_line = 5
    elif n <= 21:
        chars_per_line = 6
    else:
        chars_per_line = 7

    # 2. 格式化 label 为均匀换行的文本
    if "\n" in name:
        lines_list = name.split("\n")
    else:
        lines_list = []
        for i in range(0, n, chars_per_line):
            lines_list.append(name[i : i + chars_per_line])

    formatted_label = "\n".join(lines_list)
    line_count = len(lines_list)
    max_line_chars = max(len(l) for l in lines_list) if lines_list else 1

    box_w = max_line_chars * char_w
    box_h = line_count * line_h

    # 3. 计算能够将该文本框完全容纳的外接圆直径
    # 圆直径必须大于矩形对角线，并加上充足的呼吸衬距，确保圆弧绝不切割四角文字
    diagonal = math.hypot(box_w, box_h)
    margin = 32 if line_count > 1 else 24
    text_based_size = int(math.ceil(diagonal + margin))

    # 4. 结合度数与 anchor 设定下限
    if is_anchor:
        base_size = 112
    else:
        deg_ratio = degree / max(max_degree, 1)
        base_size = int(60 + round(20 * deg_ratio))

    final_size = max(text_based_size, base_size)
    text_max_width = int(math.ceil(box_w + 6))

    return {
        "formatted_label": formatted_label,
        "size": final_size,
        "text_max_width": text_max_width,
        "font_size": font_size,
    }


def _cytoscape_elements(nodes: list[dict], edges: list[dict]) -> list[dict]:
    import math

    degrees = _node_degrees(nodes, edges)
    max_degree = max(degrees.values(), default=1)
    node_names = {
        str(node.get("name") or "").strip()
        for node in nodes
        if str(node.get("name") or "").strip()
    }

    # 确定性初始空间排布（按章节确定角度与向外辐射，保证每次同输入布局收敛完全一致）
    sections_order: list[str] = []
    section_to_nodes: dict[str, list[str]] = {}
    seen_nodes: set[str] = set()
    for node in nodes:
        name = str(node.get("name") or "").strip()
        if not name or name in seen_nodes:
            continue
        seen_nodes.add(name)
        sec = str(node.get("section") or "").strip() or "未分组"
        if sec not in section_to_nodes:
            sections_order.append(sec)
            section_to_nodes[sec] = []
        section_to_nodes[sec].append(name)

    positions: dict[str, dict[str, float]] = {}
    num_sec = max(len(sections_order), 1)
    sec_radius = 280.0 if num_sec > 1 else 0.0
    for s_idx, sec in enumerate(sections_order):
        sec_names = section_to_nodes[sec]
        s_angle = (2.0 * math.pi * s_idx) / num_sec
        cx = sec_radius * math.cos(s_angle)
        cy = sec_radius * math.sin(s_angle)
        m = len(sec_names)
        for n_idx, n_name in enumerate(sec_names):
            if m == 1:
                positions[n_name] = {"x": round(cx, 1), "y": round(cy, 1)}
            else:
                n_angle = s_angle + (2.0 * math.pi * n_idx) / m
                dist = 85.0 + 35.0 * (n_idx % 3)
                px = cx + dist * math.cos(n_angle)
                py = cy + dist * math.sin(n_angle)
                positions[n_name] = {"x": round(px, 1), "y": round(py, 1)}

    elements: list[dict] = []
    seen_nodes.clear()
    for node in nodes:
        name = str(node.get("name") or "").strip()
        if not name or name in seen_nodes:
            continue
        seen_nodes.add(name)
        degree = degrees.get(name, 0)
        is_anchor = _is_section_anchor(node)
        dim = _calculate_node_dimension(
            name, degree=degree, max_degree=max_degree, is_anchor=is_anchor
        )
        item: dict[str, Any] = {
            "data": {
                "id": name,
                "name": name,
                "label": dim["formatted_label"],
                "type": str(node.get("type") or "").strip() or "concept",
                "definition": str(node.get("definition") or "").strip(),
                "section": str(node.get("section") or "").strip() or "未分组",
                "degree": degree,
                "size": dim["size"],
                "text_max_width": dim["text_max_width"],
                "font_size": dim["font_size"],
                "anchor": is_anchor,
                "origin": str(node.get("origin") or "").strip(),
            }
        }
        if name in positions:
            item["position"] = positions[name]
        elements.append(item)
    seen_edges: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges):
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = str(edge.get("relation") or "").strip()
        if source not in node_names or target not in node_names:
            continue
        key = (source, relation, target)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        elements.append(
            {
                "data": {
                    "id": f"edge-{index}",
                    "source": source,
                    "target": target,
                    "label": relation,
                    "evidence": str(edge.get("evidence") or "").strip(),
                    "relation": relation,
                    "origin": str(edge.get("origin") or "").strip(),
                }
            }
        )
    return elements


def build_graph_html(
    nodes: list[dict],
    edges: list[dict],
    title: str = "",
) -> str:
    """生成 Cytoscape.js 交互式知识图谱 HTML 文本（Meeting Domain / LaTeX Paper 学术风格 + 交互工具箱）。"""
    elements = _cytoscape_elements(nodes, edges)
    section_names = []
    for node in nodes:
        section = str(node.get("section") or "").strip() or "未分组"
        if section not in section_names:
            section_names.append(section)
    section_colors = {
        section: _SECTION_COLORS[index % len(_SECTION_COLORS)][1]
        for index, section in enumerate(section_names)
    }
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title or "知识图谱")}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0;
      background: #f6f5f0;
      color: #1a1a1a;
      font-family: "Latin Modern Roman", "Computer Modern Roman", "CMU Serif", "Times New Roman", Times, "Songti SC", "SimSun", "STSong", serif;
      -webkit-font-smoothing: antialiased;
    }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 460px;
      height: 100vh;
      min-height: 680px;
    }}
    .canvas-container {{
      position: relative;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #fbfaf7 radial-gradient(#e5dfd5 1.2px, transparent 1.2px);
      background-size: 26px 26px;
    }}
    #cy {{
      width: 100%;
      height: 100%;
    }}
    .canvas-toolbar {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 50;
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      padding: 6px 10px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
      backdrop-filter: blur(8px);
    }}
    .tool-btn {{
      appearance: none;
      border: 1px solid #d4d0c7;
      background: #faf9f6;
      color: #222222;
      font-family: inherit;
      font-size: 12px;
      font-weight: 600;
      padding: 5px 11px;
      border-radius: 3px;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .tool-btn:hover {{
      background: #ffffff;
      border-color: #0047ab;
      color: #0047ab;
      box-shadow: 0 1px 3px rgba(0, 71, 171, 0.15);
    }}
    .tool-btn.is-active {{
      background: #0047ab;
      color: #ffffff;
      border-color: #003380;
    }}

    aside {{
      border-left: 1.5px solid #d4d0c7;
      background: #ffffff;
      padding: 24px 26px;
      overflow-y: auto;
      box-shadow: -4px 0 20px rgba(0, 0, 0, 0.04);
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    /* Search Input */
    .search-wrap {{
      position: relative;
    }}
    .search-input {{
      width: 100%;
      box-sizing: border-box;
      padding: 9px 12px;
      background: #faf9f6;
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      font-family: inherit;
      font-size: 13px;
      color: #111111;
      transition: all 0.18s ease;
    }}
    .search-input:focus {{
      outline: none;
      background: #ffffff;
      border-color: #0047ab;
      box-shadow: 0 0 0 2px rgba(0, 71, 171, 0.12);
    }}

    /* Filter Panel */
    .filter-section {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .filter-toggles {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .filter-tag {{
      padding: 3px 9px;
      font-size: 11.5px;
      font-weight: 600;
      border-radius: 3px;
      cursor: pointer;
      user-select: none;
      border: 1px solid #d4d0c7;
      background: #faf9f6;
      color: #444444;
      transition: all 0.15s ease;
    }}
    .filter-tag:hover {{
      border-color: #0047ab;
      color: #0047ab;
    }}
    .filter-tag.is-active {{
      background: #0047ab;
      color: #ffffff;
      border-color: #003380;
    }}

    /* Legend */
    .panel-head {{
      font-size: 11.5px;
      font-weight: 700;
      color: #333333;
      letter-spacing: 0.5px;
      border-bottom: 1px solid #e2ded6;
      padding-bottom: 5px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .legend {{
      display: grid;
      gap: 5px;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: #333333;
      font-size: 12px;
      cursor: pointer;
      padding: 3px 6px;
      border-radius: 3px;
      transition: background 0.15s ease;
    }}
    .legend-item:hover {{
      background: #faf9f6;
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}

    /* Detail Inspector (Placed below Legend) */
    .detail-container {{
      min-height: 160px;
    }}
    .detail-empty {{
      border: 1px dashed #d6d1c7;
      background: #faf9f6;
      border-radius: 4px;
      padding: 26px 16px;
      text-align: center;
      color: #736f66;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
    }}
    .detail-empty .empty-icon {{
      margin-bottom: 8px;
      color: #8c857b;
      opacity: 0.85;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .detail-empty .empty-title {{
      font-size: 13px;
      font-weight: 700;
      color: #2b2b2b;
      margin-bottom: 4px;
      letter-spacing: 0.2px;
    }}
    .detail-empty .empty-desc {{
      font-size: 11.5px;
      line-height: 1.55;
      color: #7a756b;
      max-width: 250px;
      margin: 0 auto;
    }}

    /* Detail Card (When Selected) */
    .detail-card {{
      border: 1px solid #dedad2;
      border-radius: 4px;
      padding: 15px;
      background: #faf9f6;
      line-height: 1.6;
      font-size: 13px;
      word-break: break-word;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
    }}
    .node-header {{
      margin-bottom: 10px;
    }}
    .node-title {{
      font-size: 1.2rem;
      font-weight: 700;
      color: #111111;
      letter-spacing: 0.2px;
      line-height: 1.35;
      margin-bottom: 6px;
    }}
    .node-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1.5px 7px;
      border-radius: 3px;
      font-size: 11px;
      font-weight: 600;
      line-height: 1.5;
      border: 1px solid transparent;
      user-select: none;
    }}
    .badge-concept {{ background: #f0f4ff; color: #0047ab; border-color: #c6d7ff; }}
    .badge-formula {{ background: #f6ffed; color: #237804; border-color: #b7eb8f; }}
    .badge-method {{ background: #f9f0ff; color: #531dab; border-color: #d3adf7; }}
    .badge-problem {{ background: #fff7e6; color: #d46b08; border-color: #ffd591; }}
    .badge-pitfall {{ background: #fff1f0; color: #cf1322; border-color: #ffa39e; }}
    .badge-muted {{ background: #f3f2ee; color: #595959; border-color: #dcd8cf; }}
    .badge-new {{ background: #fffbe6; color: #b86a04; border-color: #ffe58f; font-weight: 700; }}
    .badge-section {{ background: #ffffff; color: #333333; border-color: #d4d0c7; font-weight: 500; }}

    /* Detail Blocks */
    .detail-block {{
      margin-top: 12px;
    }}
    .block-label {{
      color: #4f4b44;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.4px;
      margin-bottom: 5px;
    }}
    .def-box {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-left: 3px solid #0047ab;
      border-radius: 2px;
      padding: 9px 12px;
      font-size: 12.5px;
      color: #222222;
      line-height: 1.65;
    }}

    /* Structural Relations */
    .relation-grid {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 3px;
      padding: 8px 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .relation-row {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      font-size: 12px;
      line-height: 1.5;
    }}
    .relation-kind {{
      flex: 0 0 52px;
      color: #666666;
      font-size: 11px;
      font-weight: 600;
      padding-top: 2px;
    }}
    .relation-kind-warn {{ color: #cf1322; }}
    .relation-kind-diff {{ color: #531dab; }}
    .relation-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      flex: 1;
    }}

    /* Interactive Chips */
    .interactive-chip {{
      display: inline-flex;
      align-items: center;
      gap: 2px;
      padding: 2px 7px;
      border-radius: 3px;
      background: #ffffff;
      border: 1px solid #d4d0c7;
      color: #0047ab;
      font-size: 11.5px;
      font-weight: 600;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s ease;
      text-decoration: none;
    }}
    .interactive-chip:hover {{
      background: #f0f4ff;
      border-color: #0047ab;
      box-shadow: 0 1px 3px rgba(0, 71, 171, 0.15);
    }}
    .chip-prereq {{ background: #fffbf0; border-color: #ffe1b3; color: #b86a04; }}
    .chip-app {{ background: #f0f7ff; border-color: #b9d8ff; color: #0047ab; }}
    .chip-warn {{ background: #fff1f0; border-color: #ffa39e; color: #cf1322; }}
    .chip-diff {{ background: #f9f0ff; border-color: #d3adf7; color: #531dab; }}

    /* Edges List */
    .edge-list {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .edge-item {{
      padding: 7px 9px;
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 3px;
      font-size: 12px;
    }}
    .edge-flow {{
      display: flex;
      align-items: center;
      gap: 5px;
      flex-wrap: wrap;
      font-weight: 600;
      color: #111111;
    }}
    .edge-arrow {{
      color: #888888;
      font-size: 10px;
    }}
    .edge-ev {{
      color: #4b4843;
      font-size: 11.5px;
      margin-top: 4px;
      background: #faf9f6;
      padding: 4px 8px;
      border-radius: 2px;
      border-left: 2px solid #b5b0a5;
      line-height: 1.5;
      font-style: italic;
    }}

    /* Edge Detail Card (When an edge is tapped) */
    .edge-card {{
      border: 1px solid #dedad2;
      border-radius: 4px;
      padding: 15px;
      background: #faf9f6;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
    }}
    .edge-triplet-flow {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      flex-wrap: wrap;
      padding: 10px 6px;
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 3px;
    }}
    .edge-arrow-label {{
      padding: 2px 8px;
      font-size: 11.5px;
      font-weight: 700;
      border-radius: 3px;
      border: 1px solid transparent;
    }}
    .edge-evidence-box {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 3px;
      padding: 8px 12px;
      color: #2b2b2b;
      font-size: 12px;
      line-height: 1.6;
      font-style: italic;
    }}
    .edge-actions {{
      display: flex;
      gap: 8px;
      margin-top: 12px;
    }}
    .nav-chip {{
      flex: 1;
      appearance: none;
      border: 1px solid #d4d0c7;
      background: #ffffff;
      color: #0047ab;
      padding: 6px 8px;
      font-size: 11.5px;
      font-weight: 600;
      border-radius: 3px;
      cursor: pointer;
      transition: all 0.15s ease;
      text-align: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .nav-chip:hover {{
      background: #f0f4ff;
      border-color: #0047ab;
    }}

    @media (max-width: 860px) {{
      .shell {{ grid-template-columns: 1fr; grid-template-rows: minmax(520px, 68vh) auto; }}
      aside {{ border-left: 0; border-top: 1.5px solid #d4d0c7; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="canvas-container">
      <div class="canvas-toolbar">
        <button class="tool-btn" onclick="fitCanvas()">⟲ 适应画布</button>
        <button class="tool-btn" id="btn-backbone" onclick="toggleBackbone(this)">✦ 核心推导骨架</button>
        <button class="tool-btn" id="btn-new" onclick="toggleNewOnly(this)">★ 仅看本场新增</button>
      </div>
      <div id="cy"></div>
    </div>
    <aside>
      <div class="search-wrap">
        <input type="text" id="kg-search" class="search-input" placeholder="检索知识点、定理或题型..." autocomplete="off" />
      </div>

      <div class="filter-section">
        <div class="filter-toggles">
          <span class="filter-tag is-active" data-type="concept" onclick="toggleType('concept', this)">核心概念</span>
          <span class="filter-tag is-active" data-type="formula" onclick="toggleType('formula', this)">公式定理</span>
          <span class="filter-tag is-active" data-type="method" onclick="toggleType('method', this)">解法技巧</span>
          <span class="filter-tag is-active" data-type="problem" onclick="toggleType('problem', this)">题型场景</span>
          <span class="filter-tag is-active" data-type="pitfall" onclick="toggleType('pitfall', this)">易错警示</span>
        </div>
      </div>

      <div class="panel-head">章节图例</div>
      <div id="legend" class="legend"></div>

      <div class="panel-head" style="margin-top: 8px;">详细信息</div>
      <div id="detail" class="detail-container"></div>
    </aside>
  </div>
  <script src="{_CYTOSCAPE_CDN}"></script>
  <script>
    const elements = {dumps(elements, ensure_ascii=False)};
    const sectionColors = {dumps(section_colors, ensure_ascii=False)};
    const relationColors = {dumps(_RELATION_COLORS, ensure_ascii=False)};
    const detail = document.getElementById('detail');
    const legend = document.getElementById('legend');

    function renderEmptyState() {{
      return `
        <div class="detail-empty">
          <div class="empty-icon">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#9e978e" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="6" cy="6" r="3"></circle>
              <circle cx="18" cy="18" r="3"></circle>
              <line x1="8.5" y1="8.5" x2="15.5" y2="15.5"></line>
            </svg>
          </div>
          <div class="empty-title">未选择任何对象</div>
          <div class="empty-desc">在左侧画布中点击任意节点或连线，查看完整定义、关联路径与原文依据</div>
        </div>
      `;
    }}
    detail.innerHTML = renderEmptyState();

    Object.entries(sectionColors).forEach(([name, color]) => {{
      const item = document.createElement('div');
      item.className = 'legend-item';
      item.innerHTML = `<span class="swatch" style="background:${{color}}"></span><span>${{name}}</span>`;
      item.onclick = () => filterSection(name);
      legend.appendChild(item);
    }});
    if (elements.some((el) => el.data && (el.data.origin === 'new' || el.data.origin === 'history'))) {{
      [
        ['历史（已有）', '#94a3b8'],
        ['新增（本场）', '#f59e0b'],
      ].forEach(([name, color]) => {{
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `<span class="swatch" style="background:${{color}}"></span><span>${{name}}</span>`;
        legend.appendChild(item);
      }});
    }}

    if (!window.cytoscape) {{
      detail.textContent = 'Cytoscape.js 未加载。请联网后重新打开，或使用同目录 SVG 文件演示。';
    }} else {{
      const cy = cytoscape({{
        container: document.getElementById('cy'),
        elements,
        wheelSensitivity: 0.18,
        minZoom: 0.18,
        maxZoom: 2.6,
        style: [
          {{
            selector: 'node',
            style: {{
              'label': 'data(label)',
              'text-wrap': 'wrap',
              'text-max-width': ele => ele.data('text_max_width') || (ele.data('size') * 0.78),
              'font-family': '"Latin Modern Roman", "Computer Modern Roman", "Times New Roman", Times, "Songti SC", "SimSun", serif',
              'font-size': ele => ele.data('font_size') || (ele.data('anchor') ? 15 : 12.5),
              'font-weight': 700,
              'color': ele => ele.data('anchor') ? '#ffffff' : '#111111',
              'text-valign': 'center',
              'text-halign': 'center',
              'shape': 'ellipse',
              'width': 'data(size)',
              'height': 'data(size)',
              'background-color': ele => sectionColors[ele.data('section')] || '#94a3b8',
              'background-opacity': ele => {{
                if (ele.data('origin') === 'new') return ele.data('anchor') ? 1 : 0.85;
                if (ele.data('origin') === 'history') return ele.data('anchor') ? 0.55 : 0.22;
                return ele.data('anchor') ? 0.92 : 0.35;
              }},
              'border-color': ele => {{
                if (ele.data('origin') === 'new') return '#b86a04';
                const t = ele.data('type');
                if (t === 'formula') return '#237804';
                if (t === 'method') return '#531dab';
                if (t === 'problem') return '#d46b08';
                if (t === 'pitfall') return '#cf1322';
                return '#ffffff';
              }},
              'border-width': ele => ele.data('origin') === 'new' ? 3.5 : (ele.data('anchor') ? 2.5 : 2),
              'shadow-blur': ele => ele.data('anchor') ? 12 : (ele.data('origin') === 'new' ? 8 : 3),
              'shadow-color': ele => ele.data('origin') === 'new' ? '#ffe58f' : (sectionColors[ele.data('section')] || '#94a3b8'),
              'shadow-opacity': ele => ele.data('anchor') ? 0.3 : 0.16,
              'shadow-offset-x': 0,
              'shadow-offset-y': 2
            }}
          }},
          {{
            selector: 'edge',
            style: {{
              'curve-style': 'bezier',
              'target-arrow-shape': 'triangle',
              'arrow-scale': 1.15,
              'target-arrow-color': ele => relationColors[ele.data('relation')] || '#64748b',
              'line-color': ele => relationColors[ele.data('relation')] || '#64748b',
              'line-opacity': ele => ele.data('origin') === 'new' ? 0.92 : (ele.data('origin') === 'history' ? 0.32 : 0.52),
              'width': ele => ele.data('origin') === 'new' ? 2.6 : 1.4,
              'label': 'data(label)',
              'font-size': 10,
              'font-family': '"Latin Modern Roman", "Times New Roman", serif',
              'font-weight': 600,
              'color': '#333333',
              'text-background-color': '#faf9f6',
              'text-background-opacity': 0.88,
              'text-background-padding': 3,
              'text-rotation': 'autorotate'
            }}
          }},
          {{
            selector: '.faded',
            style: {{ 'opacity': 0.12, 'text-opacity': 0.12 }}
          }},
          {{
            selector: 'node.selected',
            style: {{ 'border-width': 4.5, 'border-color': '#0047ab', 'z-index': 15 }}
          }},
          {{
            selector: 'edge.selected',
            style: {{ 'width': 3.6, 'line-color': '#0047ab', 'target-arrow-color': '#0047ab', 'line-opacity': 1, 'z-index': 20 }}
          }}
        ],
        layout: {{
          name: 'cose',
          animate: false,
          randomize: false,
          componentSpacing: 115,
          nodeRepulsion: 9500,
          idealEdgeLength: edge => edge.data('relation') === '包含' || edge.data('relation') === '属于' ? 88 : 120,
          edgeElasticity: 72,
          nestingFactor: 0.9,
          gravity: 0.52,
          numIter: 2400
        }}
      }});

      const esc = (value) => String(value || '').replace(/[&<>"']/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }})[ch]);

      const cleanName = (val) => String(val || '').split(String.fromCharCode(10)).join('').split(String.fromCharCode(13)).join('').trim();

      window.focusNode = (name, ev) => {{
        if (ev) ev.stopPropagation();
        const cleanTarget = cleanName(name);
        const target = cy.nodes().filter(n => {{
          const nName = cleanName(n.data('name'));
          const nLabel = cleanName(n.data('label'));
          const nId = String(n.id() || '').trim();
          return nName === cleanTarget || nLabel === cleanTarget || nId === cleanTarget;
        }});
        if (target.length) {{
          cy.animate({{
            center: {{ eles: target }},
            zoom: Math.max(cy.zoom(), 1.25),
            duration: 450,
            easing: 'ease-in-out-cubic'
          }});
          target.emit('tap');
        }}
      }};

      // ── Step 3 工具箱交互逻辑 ──────────────────────────────
      window.fitCanvas = () => {{
        cy.animate({{
          fit: {{ padding: 48 }},
          duration: 400,
          easing: 'ease-in-out-cubic'
        }});
      }};

      let backboneOnly = false;
      window.toggleBackbone = (btn) => {{
        backboneOnly = !backboneOnly;
        btn.classList.toggle('is-active', backboneOnly);
        applyFilters();
      }};

      let newOnly = false;
      window.toggleNewOnly = (btn) => {{
        newOnly = !newOnly;
        btn.classList.toggle('is-active', newOnly);
        applyFilters();
      }};

      const activeTypes = new Set(['concept', 'formula', 'method', 'problem', 'pitfall']);
      window.toggleType = (type, btn) => {{
        if (activeTypes.has(type)) {{
          activeTypes.delete(type);
          btn.classList.remove('is-active');
        }} else {{
          activeTypes.add(type);
          btn.classList.add('is-active');
        }}
        applyFilters();
      }};

      window.resetTypeFilters = () => {{
        ['concept', 'formula', 'method', 'problem', 'pitfall'].forEach(t => activeTypes.add(t));
        document.querySelectorAll('.filter-tag').forEach(el => el.classList.add('is-active'));
        applyFilters();
      }};

      let isolatedSection = null;
      window.filterSection = (secName) => {{
        if (isolatedSection === secName) {{
          isolatedSection = null;
          cy.elements().removeClass('faded');
        }} else {{
          isolatedSection = secName;
          cy.elements().addClass('faded');
          const secNodes = cy.nodes().filter(n => n.data('section') === secName);
          secNodes.removeClass('faded');
          secNodes.connectedEdges().removeClass('faded');
        }}
      }};

      function applyFilters() {{
        cy.batch(() => {{
          cy.nodes().forEach(n => {{
            const t = n.data('type') || 'concept';
            const isAnchor = n.data('anchor');
            const isNew = n.data('origin') === 'new';

            let visible = isAnchor || activeTypes.has(t);
            if (newOnly && !isNew && !isAnchor) {{
              visible = false;
            }}
            n.style('display', visible ? 'element' : 'none');
          }});

          cy.edges().forEach(e => {{
            const rel = e.data('relation');
            const isBackbone = ['前提', '用于', '转化', '等价于'].includes(rel);
            let visible = true;
            if (backboneOnly && !isBackbone) {{
              visible = false;
            }}
            e.style('display', visible ? 'element' : 'none');
          }});
        }});
      }}

      // 实时检索
      const searchInput = document.getElementById('kg-search');
      searchInput.addEventListener('input', (e) => {{
        const q = e.target.value.trim().toLowerCase();
        if (!q) {{
          cy.elements().removeClass('faded selected');
          return;
        }}
        cy.elements().addClass('faded');
        const matches = cy.nodes().filter(n => {{
          const name = String(n.data('name') || n.data('label') || '').toLowerCase();
          const def = (n.data('definition') || '').toLowerCase();
          const sec = (n.data('section') || '').toLowerCase();
          const type = (n.data('type') || '').toLowerCase();
          return name.includes(q) || def.includes(q) || sec.includes(q) || type.includes(q);
        }});
        matches.removeClass('faded');
        matches.connectedEdges().removeClass('faded');
      }});

      searchInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter') {{
          const q = e.target.value.trim().toLowerCase();
          const matches = cy.nodes().filter(n => {{
            const name = String(n.data('name') || n.data('label') || '').toLowerCase();
            return name.includes(q);
          }});
          if (matches.length) {{
            focusNode(matches[0].data('name') || matches[0].data('label'));
          }}
        }}
      }});

      cy.ready(() => cy.fit(undefined, 48));

      // ── 点击节点交互 ──────────────────────────────────
      cy.on('tap', 'node', event => {{
        const node = event.target;
        cy.elements().addClass('faded');
        node.removeClass('faded').addClass('selected');
        node.neighborhood().removeClass('faded');

        const outgoing = node.outgoers('edge');
        const incoming = node.incomers('edge');
        const degree = node.data('degree') || (outgoing.length + incoming.length);
        const ntype = node.data('type') || 'concept';

        const typeConfig = {{
          'concept': {{ label: '概念', cls: 'badge-concept' }},
          'formula': {{ label: '公式', cls: 'badge-formula' }},
          'method': {{ label: '解法', cls: 'badge-method' }},
          'problem': {{ label: '题型', cls: 'badge-problem' }},
          'pitfall': {{ label: '警示', cls: 'badge-pitfall' }}
        }};
        const typeBadge = `<span class="badge ${{typeConfig[ntype]?.cls || 'badge-concept'}}">${{typeConfig[ntype]?.label || '概念'}}</span>`;
        const origin = node.data('origin');
        const originBadge = origin === 'new'
          ? '<span class="badge badge-new">新增</span>'
          : origin === 'history'
            ? '<span class="badge badge-muted">历史</span>'
            : '';

        const nodeName = esc(node.data('name') || node.data('label'));

        // 1. 结构关联 (Prerequisites, Applications, Pitfalls, Distinctions)
        const prereqEdges = incoming.filter(e => ['前提', '前置', '包含'].includes(e.data('relation')));
        const prereqHtml = prereqEdges.length
          ? prereqEdges.map(e => {{
              const src = esc(e.source().data('name') || e.source().data('label'));
              return `<span class="interactive-chip chip-prereq" onclick="focusNode('${{src}}', event)">${{src}}</span>`;
            }}).join('')
          : '';

        const appEdges = outgoing.filter(e => ['用于', '转化'].includes(e.data('relation')));
        const appHtml = appEdges.length
          ? appEdges.map(e => {{
              const tgt = esc(e.target().data('name') || e.target().data('label'));
              return `<span class="interactive-chip chip-app" onclick="focusNode('${{tgt}}', event)">${{tgt}}</span>`;
            }}).join('')
          : '';

        const pitfallEdges = node.connectedEdges().filter(e => {{
          if (e.data('relation') === '导致') return true;
          const other = e.source().id() === node.id() ? e.target() : e.source();
          return other.data('type') === 'pitfall';
        }});
        const pitfallHtml = pitfallEdges.length
          ? pitfallEdges.map(e => {{
              const other = e.source().id() === node.id() ? e.target() : e.source();
              const otherName = esc(other.data('name') || other.data('label'));
              return `<span class="interactive-chip chip-warn" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span>`;
            }}).join('')
          : '';

        const diffEdges = node.connectedEdges().filter(e => e.data('relation') === '区别于');
        const diffHtml = diffEdges.length
          ? diffEdges.map(e => {{
              const other = e.source().id() === node.id() ? e.target() : e.source();
              const otherName = esc(other.data('name') || other.data('label'));
              return `<span class="interactive-chip chip-diff" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span>`;
            }}).join('')
          : '';

        const hasStructural = prereqHtml || appHtml || pitfallHtml || diffHtml;

        // 2. 出入边列表与佐证
        const edgeItemHtml = (edge, isOut) => {{
          const other = isOut ? edge.target() : edge.source();
          const otherName = esc(other.data('name') || other.data('label'));
          const relName = esc(edge.data('relation') || '相关');
          const color = relationColors[relName] || '#64748b';
          const ev = edge.data('evidence');
          return `
            <div class="edge-item">
              <div class="edge-flow">
                ${{isOut 
                  ? `<span>本概念</span> <span class="edge-arrow">─</span> <span class="badge" style="background:${{color}}15;color:${{color}};border-color:${{color}}40">${{relName}}</span> <span class="edge-arrow">─▸</span> <span class="interactive-chip" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span>`
                  : `<span class="interactive-chip" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span> <span class="edge-arrow">─</span> <span class="badge" style="background:${{color}}15;color:${{color}};border-color:${{color}}40">${{relName}}</span> <span class="edge-arrow">─▸</span> <span>本概念</span>`
                }}
              </div>
              ${{ev ? `<div class="edge-ev">“${{esc(ev)}}”</div>` : ''}}
            </div>
          `;
        }};

        const allEdgesList = [
          ...outgoing.map(e => edgeItemHtml(e, true)),
          ...incoming.map(e => edgeItemHtml(e, false))
        ].join('');

        // 3. 同章其他知识点
        const currentSection = node.data('section');
        const cohortNodes = cy.nodes().filter(n => n.id() !== node.id() && n.data('section') === currentSection);
        const cohortHtml = cohortNodes.length
          ? cohortNodes.slice(0, 8).map(n => {{
              const cName = esc(n.data('name') || n.data('label'));
              return `<span class="interactive-chip" onclick="focusNode('${{cName}}', event)">${{cName}}</span>`;
            }}).join('')
          : '';

        // 渲染完整节点详情
        detail.innerHTML = `
          <div class="detail-card">
            <div class="node-header">
              <div class="node-title">${{nodeName}}</div>
              <div class="node-badges">
                ${{typeBadge}}
                <span class="badge badge-section">§ ${{esc(node.data('section') || '未分组')}}</span>
                <span class="badge badge-muted">${{degree}} 条关联</span>
                ${{originBadge}}
              </div>
            </div>

            <div class="detail-block">
              <div class="block-label">定义与阐述</div>
              <div class="def-box">${{esc(node.data('definition') || '原文未给出独立定义句')}}</div>
            </div>

            ${{hasStructural ? `
            <div class="detail-block">
              <div class="block-label">结构关联</div>
              <div class="relation-grid">
                ${{prereqHtml ? `
                <div class="relation-row">
                  <span class="relation-kind">前置前提</span>
                  <div class="relation-chips">${{prereqHtml}}</div>
                </div>` : ''}}
                ${{appHtml ? `
                <div class="relation-row">
                  <span class="relation-kind">后续应用</span>
                  <div class="relation-chips">${{appHtml}}</div>
                </div>` : ''}}
                ${{pitfallHtml ? `
                <div class="relation-row">
                  <span class="relation-kind relation-kind-warn">易错警示</span>
                  <div class="relation-chips">${{pitfallHtml}}</div>
                </div>` : ''}}
                ${{diffHtml ? `
                <div class="relation-row">
                  <span class="relation-kind relation-kind-diff">对照辨析</span>
                  <div class="relation-chips">${{diffHtml}}</div>
                </div>` : ''}}
              </div>
            </div>` : ''}}

            ${{allEdgesList ? `
            <div class="detail-block">
              <div class="block-label">关系明细与原文佐证</div>
              <div class="edge-list">${{allEdgesList}}</div>
            </div>` : ''}}

            ${{cohortHtml ? `
            <div class="detail-block">
              <div class="block-label">同章其他知识点</div>
              <div class="relation-chips">${{cohortHtml}}</div>
            </div>` : ''}}
          </div>
        `;
      }});

      // ── 点击边交互 ────────────────────────────────────
      cy.on('tap', 'edge', event => {{
        const edge = event.target;
        cy.elements().addClass('faded');
        edge.removeClass('faded').addClass('selected');
        edge.connectedNodes().removeClass('faded').addClass('selected');

        const srcName = esc(edge.source().data('name') || edge.source().data('label'));
        const tgtName = esc(edge.target().data('name') || edge.target().data('label'));
        const relName = esc(edge.data('label') || '相关');
        const relColor = relationColors[relName] || '#0047ab';
        const evidence = esc(edge.data('evidence') || '');

        detail.innerHTML = `
          <div class="edge-card">
            <div class="edge-triplet-flow">
              <span class="interactive-chip" onclick="focusNode('${{srcName}}', event)">${{srcName}}</span>
              <span class="edge-arrow-label" style="background:${{relColor}}15;color:${{relColor}};border-color:${{relColor}}40">
                ── ${{relName}} ──▸
              </span>
              <span class="interactive-chip" onclick="focusNode('${{tgtName}}', event)">${{tgtName}}</span>
            </div>

            <div class="detail-block" style="margin-top: 12px;">
              <div class="block-label">原文证据支撑</div>
              <div class="edge-evidence-box">
                ${{evidence ? `“${{evidence}}”` : '<span style="color:#8c857b;font-style:normal">（由正文上下文逻辑直接关联，未提取独立引句）</span>'}}
              </div>
            </div>

            <div class="edge-actions">
              <button class="nav-chip" onclick="focusNode('${{srcName}}', event)">定位起点：${{srcName}}</button>
              <button class="nav-chip" onclick="focusNode('${{tgtName}}', event)">定位终点：${{tgtName}}</button>
            </div>
          </div>
        `;
      }});

      cy.on('tap', event => {{
        if (event.target === cy) {{
          cy.elements().removeClass('faded selected');
          detail.innerHTML = renderEmptyState();
        }}
      }});
    }}
  </script>
</body>
</html>
"""
    return html


def render_graph_html(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    filename: str = "graph.html",
    title: str = "",
) -> Path | None:
    """生成 Cytoscape.js 交互式知识图谱 HTML。"""
    if not nodes:
        logger.warning("知识图谱无节点，跳过 HTML 生成")
        return None
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        html = build_graph_html(nodes, edges, title=title)
        out_path = out_dir / filename
        out_path.write_text(html, encoding="utf-8")
        return out_path
    except Exception:  # noqa: BLE001 - HTML 生成失败不影响主流程
        logger.warning("知识图谱 HTML 生成异常，已跳过", exc_info=True)
        return None


def render_graph_bundle(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    stem: str = "graph",
    title: str = "",
) -> dict[str, Path]:
    """导出交互式 HTML（学习地图文本由 API 响应携带，不落盘 md）。"""
    paths: dict[str, Path] = {}
    html_path = render_graph_html(nodes, edges, out_dir, f"{stem}.html", title)
    if html_path:
        paths["html"] = html_path
    return paths


def build_graph_embed(
    nodes: list[dict],
    edges: list[dict],
    title: str = "",
) -> str:
    """知识图谱可点击组件（嵌进其它 HTML，不单独成页）。"""
    elements = _cytoscape_elements(nodes, edges)
    section_names: list[str] = []
    for node in nodes:
        section = str(node.get("section") or "").strip() or "未分组"
        if section not in section_names:
            section_names.append(section)
    section_colors = {
        section: _SECTION_COLORS[index % len(_SECTION_COLORS)][1]
        for index, section in enumerate(section_names)
    }
    heading = (title or "").strip() or "知识图谱"
    return f"""<div class="lc-kg">
  <div class="lc-kg-shell">
    <div id="lc-cy"></div>
    <aside class="lc-kg-aside">
      <h3>{escape(heading)}</h3>
      <p class="lc-kg-meta">滚轮缩放，拖动画布或节点。点击节点查看定义、程度和关系。</p>
      <div class="lc-kg-label">当前选中</div>
      <div id="lc-kg-detail" class="lc-kg-detail">点击一个节点查看定义、程度、出入边和相关概念。</div>
      <div class="lc-kg-label">分组</div>
      <div id="lc-kg-legend" class="lc-kg-legend"></div>
    </aside>
  </div>
</div>
<script>
(function () {{
  const elements = {dumps(elements, ensure_ascii=False)};
  const sectionColors = {dumps(section_colors, ensure_ascii=False)};
  const relationColors = {dumps(_RELATION_COLORS, ensure_ascii=False)};
  const detail = document.getElementById('lc-kg-detail');
  const legend = document.getElementById('lc-kg-legend');
  if (!detail || !legend) return;
  Object.entries(sectionColors).forEach(([name, color]) => {{
    const item = document.createElement('div');
    item.className = 'lc-kg-legend-item';
    item.innerHTML = '<span class="lc-kg-swatch" style="background:' + color + '"></span><span>' + name + '</span>';
    legend.appendChild(item);
  }});
  if (!window.cytoscape) {{
    detail.textContent = '知识图谱脚本未加载。请联网后打开本 HTML。';
    return;
  }}
  const cy = cytoscape({{
    container: document.getElementById('lc-cy'),
    elements,
    wheelSensitivity: 0.18,
    minZoom: 0.18,
    maxZoom: 2.6,
    style: [
      {{
        selector: 'node',
        style: {{
          'label': 'data(label)',
          'text-wrap': 'wrap',
          'text-max-width': 96,
          'font-family': 'Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif',
          'font-size': ele => ele.data('anchor') ? 17 : 13,
          'font-weight': 600,
          'color': ele => ele.data('anchor') ? '#ffffff' : '#0f172a',
          'text-valign': 'center',
          'text-halign': 'center',
          'shape': 'ellipse',
          'width': 'data(size)',
          'height': 'data(size)',
          'background-color': ele => sectionColors[ele.data('section')] || '#94a3b8',
          'background-opacity': ele => ele.data('anchor') ? 0.9 : 0.28,
          'border-color': '#ffffff',
          'border-width': 2.4
        }}
      }},
      {{
        selector: 'edge',
        style: {{
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'target-arrow-color': ele => relationColors[ele.data('relation')] || '#94a3b8',
          'line-color': ele => relationColors[ele.data('relation')] || '#94a3b8',
          'line-opacity': 0.5,
          'width': 1.4,
          'label': 'data(label)',
          'font-size': 9,
          'color': '#475569',
          'text-background-color': '#ffffff',
          'text-background-opacity': 0.72,
          'text-rotation': 'autorotate'
        }}
      }},
      {{ selector: '.faded', style: {{ 'opacity': 0.16, 'text-opacity': 0.16 }} }},
      {{ selector: '.selected', style: {{ 'border-width': 4, 'z-index': 10 }} }}
    ],
    layout: {{
      name: 'cose',
      animate: false,
      randomize: true,
      componentSpacing: 100,
      nodeRepulsion: 7600,
      idealEdgeLength: 96,
      edgeElasticity: 72,
      gravity: 0.52,
      numIter: 2400
    }}
  }});
  const esc = (value) => String(value || '').replace(/[&<>"']/g, (ch) => ({{
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }})[ch]);
  const relBlock = (edge) => '<div class="lc-kg-rel"><div class="lc-kg-rel-line">' +
    esc(edge.source().data('label')) + ' → ' + esc(edge.data('label') || '相关') +
    ' → ' + esc(edge.target().data('label')) + '</div></div>';
  cy.ready(() => cy.fit(undefined, 36));
  cy.on('tap', 'node', event => {{
    const node = event.target;
    cy.elements().addClass('faded');
    node.removeClass('faded').addClass('selected');
    node.neighborhood().removeClass('faded');
    const outgoing = node.outgoers('edge');
    const incoming = node.incomers('edge');
    const related = [];
    node.neighborhood('node').forEach((nb) => related.push(nb.data('label')));
    const relHtml = related.slice(0, 3).map((name) => '<span class="lc-kg-chip">' + esc(name) + '</span>').join('')
      || '<span class="lc-kg-ev">暂无一跳邻居</span>';
    detail.innerHTML =
      '<div class="lc-kg-name">' + esc(node.data('label')) + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">程度 / 分组</div>' + esc(node.data('section') || '未分组') + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">定义</div>' + esc(node.data('definition') || '暂无独立定义') + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">出边</div>' + (outgoing.length ? outgoing.map(relBlock).join('') : '<div class="lc-kg-ev">暂无出边</div>') + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">入边</div>' + (incoming.length ? incoming.map(relBlock).join('') : '<div class="lc-kg-ev">暂无入边</div>') + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">相关概念</div><div class="lc-kg-chips">' + relHtml + '</div></div>';
  }});
  cy.on('tap', 'edge', event => {{
    const edge = event.target;
    cy.elements().addClass('faded');
    edge.removeClass('faded');
    edge.connectedNodes().removeClass('faded').addClass('selected');
    detail.innerHTML =
      '<div class="lc-kg-name">' + esc(edge.source().data('label')) + ' → ' +
      esc(edge.data('label') || '相关') + ' → ' + esc(edge.target().data('label')) + '</div>' +
      '<div class="lc-kg-block"><div class="lc-kg-k">说明</div>' + esc(edge.data('evidence') || '点击两端节点查看定义') + '</div>';
  }});
  cy.on('tap', event => {{
    if (event.target === cy) {{
      cy.elements().removeClass('faded selected');
      detail.textContent = '点击一个节点查看定义、程度、出入边和相关概念。';
    }}
  }});
}})();
</script>"""


__all__ = [
    "build_graph_embed",
    "build_graph_html",
    "build_learning_map",
    "render_graph_bundle",
    "render_graph_html",
]
