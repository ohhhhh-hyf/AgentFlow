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


def _cytoscape_elements(nodes: list[dict], edges: list[dict]) -> list[dict]:
    degrees = _node_degrees(nodes, edges)
    max_degree = max(degrees.values(), default=1)
    node_names = {
        str(node.get("name") or "").strip()
        for node in nodes
        if str(node.get("name") or "").strip()
    }
    elements: list[dict] = []
    seen_nodes: set[str] = set()
    for node in nodes:
        name = str(node.get("name") or "").strip()
        if not name or name in seen_nodes:
            continue
        seen_nodes.add(name)
        degree = degrees.get(name, 0)
        is_anchor = _is_section_anchor(node)
        size = 112 if is_anchor else 56 + round(30 * degree / max(max_degree, 1))
        elements.append(
            {
                "data": {
                    "id": name,
                    "label": name,
                    "type": str(node.get("type") or "").strip() or "concept",
                    "definition": str(node.get("definition") or "").strip(),
                    "section": str(node.get("section") or "").strip() or "未分组",
                    "degree": degree,
                    "size": size,
                    "anchor": is_anchor,
                    "origin": str(node.get("origin") or "").strip(),
                }
            }
        )
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
    .aside-header {{
      border-bottom: 2px solid #111111;
      padding-bottom: 12px;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 1.5rem;
      line-height: 1.35;
      font-weight: 700;
      font-variant: small-caps;
      letter-spacing: 0.4px;
      color: #111111;
    }}
    .meta {{
      color: #666666;
      font-size: 12px;
      line-height: 1.6;
      font-style: italic;
    }}

    /* Search Input */
    .search-wrap {{
      position: relative;
    }}
    .search-input {{
      width: 100%;
      box-sizing: border-box;
      padding: 8px 12px;
      background: #faf9f6;
      border: 1px solid #d4d0c7;
      border-radius: 3px;
      font-family: inherit;
      font-size: 13px;
      color: #111111;
      transition: all 0.18s ease;
    }}
    .search-input:focus {{
      outline: none;
      background: #ffffff;
      border-color: #0047ab;
      box-shadow: 0 0 0 2px rgba(0, 71, 171, 0.15);
    }}

    /* Filter Panel */
    .filter-section {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .filter-title {{
      font-size: 11px;
      font-weight: 700;
      color: #333333;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .filter-toggles {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .filter-tag {{
      padding: 2px 8px;
      font-size: 11px;
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

    /* Detail Card */
    .panel-head {{
      font-size: 12px;
      font-weight: 700;
      color: #222222;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid #e0dcd4;
      padding-bottom: 5px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .detail {{
      border: 1px solid #dedad2;
      border-radius: 4px;
      padding: 16px;
      background: #faf9f6;
      line-height: 1.65;
      font-size: 13px;
      word-break: break-word;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
    }}
    .name-row {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
    }}
    .detail .name {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #111111;
      font-variant: small-caps;
      letter-spacing: 0.3px;
      line-height: 1.35;
    }}

    /* Badges */
    .badge-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin: 8px 0 12px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1px 7px;
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
    .badge-hub {{ background: #fffbe6; color: #b78103; border-color: #ffe58f; font-weight: 700; }}
    .badge-sub {{ background: #f5f5f5; color: #595959; border-color: #d9d9d9; }}
    .badge-new {{ background: #fff8db; color: #b86a04; border-color: #ffe58f; font-weight: 700; }}
    .badge-old {{ background: #f5f5f5; color: #595959; border-color: #d9d9d9; }}
    .badge-section {{ background: #ffffff; color: #333333; border-color: #d4d0c7; font-weight: 500; }}

    /* Definition Callout */
    .def-box {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-left: 3.5px solid #0047ab;
      border-radius: 2px;
      padding: 10px 14px;
      font-size: 13px;
      color: #222222;
      line-height: 1.7;
      margin-top: 4px;
      font-style: italic;
    }}

    /* Reasoning Path Card */
    .path-card {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 4px;
      padding: 14px;
      margin: 14px 0;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);
    }}
    .path-card-title {{
      font-size: 11px;
      font-weight: 700;
      color: #111111;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      border-bottom: 1px solid #eee9e0;
      padding-bottom: 5px;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .path-row {{ margin-top: 6px; }}
    .path-label {{
      font-size: 11px;
      font-weight: 600;
      color: #555555;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    .path-arrow {{
      text-align: center;
      color: #888888;
      font-size: 11px;
      margin: 3px 0;
      font-weight: bold;
    }}

    /* Interactive Chips */
    .detail .block {{ margin: 12px 0 0; }}
    .detail .label {{
      color: #444444;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.3px;
      margin-bottom: 5px;
    }}
    .detail .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .interactive-chip {{
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 2px 7px;
      border-radius: 3px;
      background: #ffffff;
      border: 1px solid #d4d0c7;
      color: #0047ab;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s ease;
      text-decoration: none;
    }}
    .interactive-chip:hover {{
      text-decoration: underline;
      background: #e8f0fe;
      border-color: #0047ab;
      box-shadow: 0 1px 4px rgba(0, 71, 171, 0.15);
    }}
    .chip-prereq {{ background: #fff7e6; border-color: #ffd591; color: #d46b08; }}
    .chip-app {{ background: #f0f4ff; border-color: #c6d7ff; color: #0047ab; }}
    .chip-pitfall {{ background: #fff1f0; border-color: #ffa39e; color: #cf1322; }}
    .chip-diff {{ background: #f9f0ff; border-color: #d3adf7; color: #531dab; }}

    /* Edge Detail Card */
    .edge-card {{
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 4px;
      padding: 14px;
    }}
    .edge-triplet {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      padding-bottom: 10px;
      border-bottom: 1px dashed #dcd8cf;
    }}
    .edge-explanation {{
      background: #f0f4ff;
      border-left: 3.5px solid #0047ab;
      border-radius: 2px;
      padding: 8px 12px;
      color: #003380;
      font-size: 13px;
      font-weight: 500;
      line-height: 1.6;
      margin: 8px 0;
    }}
    .edge-evidence-box {{
      background: #faf9f6;
      border: 1px solid #dedad2;
      border-radius: 3px;
      padding: 8px 12px;
      color: #333333;
      font-size: 12px;
      line-height: 1.65;
      font-style: italic;
    }}
    .edge-evidence-title {{
      font-weight: 700;
      color: #111111;
      margin-bottom: 4px;
      font-size: 11px;
      font-style: normal;
      display: flex;
      align-items: center;
      gap: 4px;
    }}

    /* Outgoing & Incoming Row */
    .detail .rel {{
      margin: 6px 0 0;
      padding: 8px 10px;
      background: #ffffff;
      border: 1px solid #dedad2;
      border-radius: 3px;
      transition: border-color 0.15s ease;
    }}
    .detail .rel:hover {{ border-color: #b5b0a5; }}
    .detail .rel-line {{
      font-weight: 600;
      color: #111111;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 5px;
      font-size: 12px;
    }}
    .detail .ev {{
      color: #444444;
      font-size: 12px;
      margin-top: 5px;
      background: #faf9f6;
      padding: 5px 8px;
      border-radius: 2px;
      border-left: 2px solid #b5b0a5;
      line-height: 1.55;
      font-style: italic;
    }}

    /* Legend */
    .legend {{
      display: grid;
      gap: 6px;
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
        <button class="tool-btn" id="btn-layout" onclick="toggleLayout(this)">⇄ 布局: 网状力导向 ▾</button>
        <button class="tool-btn" id="btn-backbone" onclick="toggleBackbone(this)">✦ 核心推导骨架</button>
        <button class="tool-btn" id="btn-new" onclick="toggleNewOnly(this)">★ 仅看本场新增</button>
      </div>
      <div id="cy"></div>
    </div>
    <aside>
      <div class="aside-header">
        <h1>{escape(title or "知识图谱")}</h1>
        <div class="meta">滚轮缩放，拖动画布或节点。点击节点查看推导链、定义、出入边，点击边查看白话因果与原文证据。</div>
      </div>

      <div class="search-wrap">
        <input type="text" id="kg-search" class="search-input" placeholder="实时检索概念、公式、方法、题型... (Enter定位)" />
      </div>

      <div class="filter-section">
        <div class="filter-title">
          <span>实体类别过滤 (Filters)</span>
          <span style="font-size:10px;color:#888;cursor:pointer" onclick="resetTypeFilters()">全部点亮</span>
        </div>
        <div class="filter-toggles">
          <span class="filter-tag is-active" data-type="concept" onclick="toggleType('concept', this)">✔ 核心概念</span>
          <span class="filter-tag is-active" data-type="formula" onclick="toggleType('formula', this)">✔ 公式定理</span>
          <span class="filter-tag is-active" data-type="method" onclick="toggleType('method', this)">✔ 解法技巧</span>
          <span class="filter-tag is-active" data-type="problem" onclick="toggleType('problem', this)">✔ 题型场景</span>
          <span class="filter-tag is-active" data-type="pitfall" onclick="toggleType('pitfall', this)">✔ 易错警示</span>
        </div>
      </div>

      <div class="panel-head">当前选中详情</div>
      <div id="detail" class="detail">点击画布中的节点或连线，查看详细知识卡片与推导路径。</div>

      <div class="panel-head">章节图例 (点击可高亮孤立章节)</div>
      <div id="legend" class="legend"></div>
    </aside>
  </div>
  <script src="{_CYTOSCAPE_CDN}"></script>
  <script>
    const elements = {dumps(elements, ensure_ascii=False)};
    const sectionColors = {dumps(section_colors, ensure_ascii=False)};
    const relationColors = {dumps(_RELATION_COLORS, ensure_ascii=False)};
    const detail = document.getElementById('detail');
    const legend = document.getElementById('legend');

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
              'text-max-width': 96,
              'font-family': '"Latin Modern Roman", "Computer Modern Roman", "Times New Roman", Times, "Songti SC", "SimSun", serif',
              'font-size': ele => ele.data('anchor') ? 16 : 13,
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
          randomize: true,
          componentSpacing: 100,
          nodeRepulsion: 7600,
          idealEdgeLength: edge => edge.data('relation') === '包含' || edge.data('relation') === '属于' ? 74 : 104,
          edgeElasticity: 72,
          nestingFactor: 0.9,
          gravity: 0.52,
          numIter: 2400
        }}
      }});

      const esc = (value) => String(value || '').replace(/[&<>"']/g, (ch) => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }})[ch]);

      window.focusNode = (name, ev) => {{
        if (ev) ev.stopPropagation();
        const target = cy.nodes().filter(n => n.data('label') === name || n.id() === name);
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

      const explainEdge = (src, rel, tgt) => {{
        const t = {{
          '前提': `“【${{src}}】是【${{tgt}}】能够成立或使用的必要前置条件。”`,
          '用于': `“以【${{src}}】为核心解题工具/方法，用于攻克【${{tgt}}】。”`,
          '包含': `“【${{src}}】涵盖了【${{tgt}}】这一关键要素或子范畴。”`,
          '属于': `“【${{src}}】归属于【${{tgt}}】这一上位范畴或章节。”`,
          '转化': `“将复杂的【${{src}}】等价转化为更易处理的【${{tgt}}】。”`,
          '等价于': `“【${{src}}】与【${{tgt}}】充要等价，二者在逻辑上完全互推。”`,
          '区别于': `“【${{src}}】与【${{tgt}}】存在本质判定边界，解题时切忌混淆。”`,
          '导致': `“若发生【${{src}}】，将直接引发【${{tgt}}】的计算或逻辑错误。”`
        }};
        return t[rel] || `“【${{src}}】与【${{tgt}}】通过【${{rel}}】紧密关联。”`;
      }};

      // ── Step 3 工具箱交互逻辑 ──────────────────────────────
      window.fitCanvas = () => {{
        cy.animate({{
          fit: {{ padding: 48 }},
          duration: 400,
          easing: 'ease-in-out-cubic'
        }});
      }};

      let currentLayoutName = 'cose';
      window.toggleLayout = (btn) => {{
        if (currentLayoutName === 'cose') {{
          currentLayoutName = 'breadthfirst';
          btn.textContent = '⇄ 布局: 层级推导树 ▾';
          btn.classList.add('is-active');
          cy.layout({{
            name: 'breadthfirst',
            directed: true,
            spacingFactor: 1.25,
            animate: true,
            animationDuration: 550,
            roots: cy.nodes().filter(n => n.data('anchor') || n.incomers('edge').length === 0)
          }}).run();
        }} else {{
          currentLayoutName = 'cose';
          btn.textContent = '⇄ 布局: 网状力导向 ▾';
          btn.classList.remove('is-active');
          cy.layout({{
            name: 'cose',
            animate: true,
            animationDuration: 550,
            componentSpacing: 100,
            nodeRepulsion: 7600,
            idealEdgeLength: edge => edge.data('relation') === '包含' || edge.data('relation') === '属于' ? 74 : 104,
            gravity: 0.52
          }}).run();
        }}
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
          const label = (n.data('label') || '').toLowerCase();
          const def = (n.data('definition') || '').toLowerCase();
          const sec = (n.data('section') || '').toLowerCase();
          const type = (n.data('type') || '').toLowerCase();
          return label.includes(q) || def.includes(q) || sec.includes(q) || type.includes(q);
        }});
        matches.removeClass('faded');
        matches.connectedEdges().removeClass('faded');
      }});

      searchInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter') {{
          const q = e.target.value.trim().toLowerCase();
          const matches = cy.nodes().filter(n => (n.data('label') || '').toLowerCase().includes(q));
          if (matches.length) {{
            focusNode(matches[0].data('label'));
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
          'concept': {{ label: '核心概念', cls: 'badge-concept' }},
          'formula': {{ label: '公式定理', cls: 'badge-formula' }},
          'method': {{ label: '解法技巧', cls: 'badge-method' }},
          'problem': {{ label: '题型场景', cls: 'badge-problem' }},
          'pitfall': {{ label: '易错警示', cls: 'badge-pitfall' }}
        }};
        const typeBadge = `<span class="badge ${{typeConfig[ntype]?.cls || 'badge-concept'}}">${{typeConfig[ntype]?.label || '核心概念'}}</span>`;
        const hubBadge = degree >= 4 
          ? `<span class="badge badge-hub">★ 核心枢纽 · ${{degree}}条关联</span>` 
          : `<span class="badge badge-sub">${{degree}}条关联</span>`;

        const origin = node.data('origin');
        const originBadge = origin === 'new'
          ? '<span class="badge badge-new">新增 (本场)</span>'
          : origin === 'history'
            ? '<span class="badge badge-old">历史 (已有)</span>'
            : '';

        // 1. 推导路径计算 (Reasoning Path)
        // 先修必备：入边为 前提 或 包含
        const prereqEdges = incoming.filter(e => ['前提', '前置', '包含'].includes(e.data('relation')));
        const prereqHtml = prereqEdges.length
          ? prereqEdges.map(e => `<span class="interactive-chip chip-prereq" onclick="focusNode('${{esc(e.source().data('label'))}}', event)">◲ ${{esc(e.source().data('label'))}}</span>`).join('')
          : '<span class="ev" style="margin:0">无特定前置条件</span>';

        // 实战应用：出边为 用于 或 转化
        const appEdges = outgoing.filter(e => ['用于', '转化'].includes(e.data('relation')));
        const appHtml = appEdges.length
          ? appEdges.map(e => `<span class="interactive-chip chip-app" onclick="focusNode('${{esc(e.target().data('label'))}}', event)">◳ ${{esc(e.target().data('label'))}}</span>`).join('')
          : '<span class="ev" style="margin:0">暂无下游应用</span>';

        // 易错警示：导致 边或与 pitfall 相连
        const pitfallEdges = node.connectedEdges().filter(e => {{
          if (e.data('relation') === '导致') return true;
          const other = e.source().id() === node.id() ? e.target() : e.source();
          return other.data('type') === 'pitfall';
        }});
        const pitfallHtml = pitfallEdges.length
          ? pitfallEdges.map(e => {{
              const other = e.source().id() === node.id() ? e.target() : e.source();
              return `<span class="interactive-chip chip-pitfall" onclick="focusNode('${{esc(other.data('label'))}}', event)">⚠ ${{esc(other.data('label'))}}</span>`;
            }}).join('')
          : '';

        // 对照辨析：区别于
        const diffEdges = node.connectedEdges().filter(e => e.data('relation') === '区别于');
        const diffHtml = diffEdges.length
          ? diffEdges.map(e => {{
              const other = e.source().id() === node.id() ? e.target() : e.source();
              return `<span class="interactive-chip chip-diff" onclick="focusNode('${{esc(other.data('label'))}}', event)">⇄ ${{esc(other.data('label'))}}</span>`;
            }}).join('')
          : '';

        // 2. 出入边列表
        const relBlock = (edge, isOut) => {{
          const other = isOut ? edge.target() : edge.source();
          const otherName = esc(other.data('label'));
          const relName = esc(edge.data('relation') || '相关');
          const color = relationColors[relName] || '#64748b';
          return `
            <div class="rel">
              <div class="rel-line">
                ${{isOut ? `本节点 ➔ <span class="badge" style="background:${{color}}15;color:${{color}};border:1px solid ${{color}}40">${{relName}}</span> ➔ <span class="interactive-chip" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span>` : `<span class="interactive-chip" onclick="focusNode('${{otherName}}', event)">${{otherName}}</span> ➔ <span class="badge" style="background:${{color}}15;color:${{color}};border:1px solid ${{color}}40">${{relName}}</span> ➔ 本节点`}}
              </div>
              <div class="ev">${{esc(edge.data('evidence') || '暂无原文证据')}}</div>
            </div>`;
        }};

        const outHtml = outgoing.length
          ? outgoing.map(e => relBlock(e, true)).join('')
          : '<div class="ev">暂无出边</div>';
        const inHtml = incoming.length
          ? incoming.map(e => relBlock(e, false)).join('')
          : '<div class="ev">暂无入边</div>';

        // 3. 同章节伙伴
        const currentSection = node.data('section');
        const cohortNodes = cy.nodes().filter(n => n.id() !== node.id() && n.data('section') === currentSection);
        const cohortHtml = cohortNodes.length
          ? cohortNodes.slice(0, 8).map(n => `<span class="interactive-chip" onclick="focusNode('${{esc(n.data('label'))}}', event)">${{esc(n.data('label'))}}</span>`).join('')
          : '<span class="ev" style="margin:0">本章暂无其他节点</span>';

        // 渲染完整立体卡片
        detail.innerHTML = `
          <div class="name-row">
            <div class="name">${{esc(node.data('label'))}}</div>
          </div>
          <div class="badge-group">
            ${{typeBadge}}
            ${{hubBadge}}
            ${{originBadge}}
            <span class="badge badge-section">§ ${{esc(node.data('section') || '未分组')}}</span>
          </div>

          <div class="block">
            <div class="label">定义 / 原文首次展开</div>
            <div class="def-box">${{esc(node.data('definition') || '原文未给出独立定义句')}}</div>
          </div>

          <div class="path-card">
            <div class="path-card-title">✦ 知识推导路径 (Reasoning Path)</div>
            <div class="path-row">
              <div class="path-label">◲ 先修必备 (Prerequisites):</div>
              <div class="chips">${{prereqHtml}}</div>
            </div>
            <div class="path-arrow">↓ 支撑前置</div>
            <div class="path-row">
              <div class="path-label">◉ 当前知识点: <strong>${{esc(node.data('label'))}}</strong></div>
            </div>
            <div class="path-arrow">↓ 实战推导</div>
            <div class="path-row">
              <div class="path-label">◳ 实战应用 (Applications):</div>
              <div class="chips">${{appHtml}}</div>
            </div>
            ${{pitfallHtml ? `
            <div class="path-row" style="margin-top:8px;padding-top:6px;border-top:1px dashed #fecaca">
              <div class="path-label" style="color:#cf1322">⚠ 易错警示 / 边界限制:</div>
              <div class="chips">${{pitfallHtml}}</div>
            </div>` : ''}}
            ${{diffHtml ? `
            <div class="path-row" style="margin-top:6px">
              <div class="path-label" style="color:#531dab">⇄ 对照辨析:</div>
              <div class="chips">${{diffHtml}}</div>
            </div>` : ''}}
          </div>

          <div class="block">
            <div class="label">出边 (该知识点推向)</div>
            ${{outHtml}}
          </div>
          <div class="block">
            <div class="label">入边 (支撑该知识点)</div>
            ${{inHtml}}
          </div>
          <div class="block">
            <div class="label">同章知识伙伴 (§ ${{esc(currentSection || '未分组')}})</div>
            <div class="chips">${{cohortHtml}}</div>
          </div>
        `;
      }});

      // ── 点击边交互 ────────────────────────────────────
      cy.on('tap', 'edge', event => {{
        const edge = event.target;
        cy.elements().addClass('faded');
        edge.removeClass('faded').addClass('selected');
        edge.connectedNodes().removeClass('faded').addClass('selected');

        const srcName = esc(edge.source().data('label'));
        const tgtName = esc(edge.target().data('label'));
        const relName = esc(edge.data('label') || '相关');
        const relColor = relationColors[relName] || '#0047ab';
        const explanation = explainEdge(srcName, relName, tgtName);
        const evidence = esc(edge.data('evidence') || '原文暂无直接引句');

        detail.innerHTML = `
          <div class="edge-card">
            <div class="edge-triplet">
              <span class="interactive-chip" onclick="focusNode('${{srcName}}', event)">${{srcName}}</span>
              <span class="badge" style="background:${{relColor}}15;color:${{relColor}};border:1px solid ${{relColor}}50;font-size:12px;font-weight:700;padding:2px 10px">${{relName}}</span>
              <span class="interactive-chip" onclick="focusNode('${{tgtName}}', event)">${{tgtName}}</span>
            </div>
            <div class="edge-explanation">${{explanation}}</div>
            <div class="edge-evidence-box">
              <div class="edge-evidence-title">📖 原文出处与证据支撑</div>
              <div>${{evidence}}</div>
            </div>
          </div>
          <div class="meta" style="margin-top:12px;text-align:center;font-size:12px">点击上方概念标签可直接在画布中平滑飞入定位</div>
        `;
      }});

      cy.on('tap', event => {{
        if (event.target === cy) {{
          cy.elements().removeClass('faded selected');
          detail.textContent = '点击画布中的节点或连线，查看详细知识卡片与推导路径。';
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
