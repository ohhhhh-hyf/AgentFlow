"""graph.py —— 知识图谱渲染（graphviz 封装，无痛降级）。

把图数据（nodes + edges）渲染为 SVG / 交互 HTML / 学习地图：

- 依赖：系统安装 Graphviz（``dot`` 可执行；Windows 需装 Graphviz，Linux 用
  apt/brew 装 graphviz + 中文字体）
- 产物：``dot -Tsvg`` 输出矢量图；节点带定义 tooltip，边带关系 label
- 设计约束（沿用 tools/mindmap.py 的无痛惯例）：
  - ``dot`` 不可用 / 失败 / 超时 → 一律返回 ``None``，不影响主流程
  - 渲染前过滤悬空边（source/target 不在 nodes 中），防 dot 报错
  - 中文 label 自动探测系统字体（Windows → Microsoft YaHei；Linux → fc-match）
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from html import escape
from json import dumps
from pathlib import Path

logger = logging.getLogger(__name__)

_RENDER_TIMEOUT_SECONDS = 60

# 关系 label 长度上限（过长截断，避免图拥挤）
_MAX_LABEL_LEN = 12
# 节点定义 tooltip 长度上限
_MAX_TOOLTIP_LEN = 80
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


def _find_dot() -> str | None:
    """定位 dot 可执行文件。

    - 优先用 PATH（shutil.which）
    - Windows 上 PATH 未配置时，探测常见安装位置兜底
      （Graphviz 安装后 PATH 不生效是常见问题）
    """
    dot = shutil.which("dot")
    if dot:
        return dot
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        base86 = Path(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        )
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            base / "Graphviz" / "bin" / "dot.exe",
            base86 / "Graphviz" / "bin" / "dot.exe",
            local / "Graphviz" / "bin" / "dot.exe",
        ]
    for cand in candidates:
        if cand.exists():
            return str(cand)


def _pick_font() -> str:
    """探测中文字体：Windows 用雅黑；Linux/mac 用 fc-match 探测，失败回退 sans-serif。"""
    if sys.platform.startswith("win"):
        return "Microsoft YaHei"
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{family}", "sans-serif:lang=zh"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        family = (result.stdout or "").strip()
        if family:
            return family.split(",")[0].strip() or "sans-serif"
    except Exception:  # noqa: BLE001 - 字体探测失败回退默认
        pass
    return "sans-serif"


def _dot_quote(text: str) -> str:
    """DOT 字符串转义：反斜杠、双引号，真实换行转成 \\n 转义序列。"""
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    return text.replace("\n", "\\n")


def _wrap_label(text: str, width: int = 8, max_len: int = 30) -> str:
    """把中文短语按固定字数换行（真实换行符，_dot_quote 会转成 \\n），避免节点横向过宽。"""
    text = re.sub(r"\s+", " ", text.strip())[:max_len]
    if len(text) <= width:
        return text
    return "\n".join(text[i : i + width] for i in range(0, len(text), width))


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


def nodes_edges_to_dot(
    nodes: list[dict],
    edges: list[dict],
    title: str = "",
    *,  # noqa: C901
    node_fontsize: int | None = None,
    edge_fontsize: int | None = None,
    label_width: int | None = None,
    compact: bool = False,
) -> tuple[str, list[dict]]:
    """把图数据转成 DOT 文本；返回 (dot_text, 有效边)。

    - 悬空边（source/target 不在 nodes 中）会被过滤并从返回值带出（供告警）
    - 节点 name 去重（同名节点合并）
    - node_fontsize / edge_fontsize / label_width：可选覆盖默认字号与换行宽度
      （默认 None = 知识图谱既有风格：节点 13-14、边 9、每行 4 字）
    - compact：紧凑布局（整体更小、节点更近、边更短），默认 False 保持原样
    """
    font = _pick_font()
    degrees = _node_degrees(nodes, edges)
    max_degree = max(degrees.values(), default=1)
    node_font = node_fontsize
    edge_font = edge_fontsize if edge_fontsize is not None else 9
    lbl_w = label_width if label_width is not None else 4
    k_spacing = 0.16 if compact else 0.28
    sep_pts = "+2" if compact else "+5"
    graph_size = "8,5!" if compact else "11,6!"
    dpi = 120 if compact else 180
    pad_pt = 0.14 if compact else 0.22
    lines = [
        "digraph graph {",
        "  graph [",
        f'    fontname="{font}",',
        "    bgcolor=\"#fbfdff:#eef7ff\",",
        "    layout=fdp,",
        "    outputorder=edgesfirst,",
        "    overlap=false,",
        "    splines=true,",
        "    K=%s," % k_spacing,
        "    sep=\"%s\"," % sep_pts,
        "    size=\"%s\"," % graph_size,
        "    ratio=compress,",
        "    dpi=%s," % dpi,
        "    concentrate=true,",
        "    pad=%s," % pad_pt,
        "    margin=0.04",
        "  ];",
        "  node [",
        f'    fontname="{font}",',
        "    shape=circle,",
        "    style=\"filled\",",
        "    color=\"#ffffff\",",
        "    penwidth=2.2,",
        "    fillcolor=\"#dbeafe\",",
        "    fontcolor=\"#0f172a\",",
        "    fontsize=14,",
        "    margin=\"0.04,0.04\"",
        "  ];",
        "  edge [",
        f'    fontname="{font}",',
        "    fontsize=%s," % edge_font,
        "    fontcolor=\"#64748b\",",
        "    color=\"#94a3b880\",",
        "    arrowsize=0.55,",
        "    penwidth=1.05"
        "  ];",
    ]
    if title:
        lines.extend(
            [
                '  labelloc="t";',
                '  labeljust="c";',
                f'  label="{_dot_quote(_wrap_label(title, width=22, max_len=44))}";',
                "  fontsize=20;",
                '  fontcolor="#0f172a";',
            ]
        )
    node_names: set[str] = set()
    seen: set[str] = set()
    section_order: list[str] = []
    section_nodes: dict[str, list[dict]] = {}
    for node in nodes:
        name = str(node.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        node_names.add(name)
        section = str(node.get("section") or "").strip()
        if section and section not in section_order:
            section_order.append(section)
        section_nodes.setdefault(section, []).append(node)

    rendered_names: set[str] = set()

    def render_node(
        node: dict,
        fill: str = "#dbeafe",
        color: str = "#38bdf8",
    ) -> str:
        name = str(node.get("name") or "").strip()
        degree = degrees.get(name, 0)
        is_anchor = _is_section_anchor(node)
        ratio = degree / max(max_degree, 1)
        if compact:
            size = 0.68 + (0.30 * ratio)
            anchor_min = 0.98
        else:
            size = 0.92 + (0.42 * ratio)
            anchor_min = 1.34
        if is_anchor:
            size = max(size, anchor_min)
        origin = str(node.get("origin") or "").strip()
        if origin == "new":
            size = min(size + 0.12, 1.7)
            color = "#f59e0b"
            fill = "#fde68a" if not is_anchor else "#f59e0b"
        elif origin == "history":
            color = "#94a3b8"
            fill = "#e2e8f0" if not is_anchor else "#94a3b8"
        fontsize = (
            node_font
            if node_font
            else (18 if is_anchor else 13 if len(name) > 8 else 14)
        )
        fontcolor = "#ffffff" if is_anchor else "#0f172a"
        attrs = [
            f'label="{_dot_quote(_wrap_label(name, width=5 if is_anchor else lbl_w, max_len=18))}"',
            'fixedsize="true"',
            f'width="{size:.2f}"',
            f'height="{size:.2f}"',
            f'fontsize="{fontsize}"',
            f'fillcolor="{fill}"',
            f'color="{color}"',
            f'fontcolor="{fontcolor}"',
            f'penwidth="{"3.4" if origin == "new" else "1.6" if origin == "history" else "2.2"}"',
        ]
        definition = str(node.get("definition") or "").strip()
        if definition:
            attrs.append(f'tooltip="{_dot_quote(definition[:_MAX_TOOLTIP_LEN])}"')
        return f'    "{_dot_quote(name)}" [{", ".join(attrs)}];'

    for idx, section in enumerate(section_order):
        fill, color = _SECTION_COLORS[idx % len(_SECTION_COLORS)]
        for node in section_nodes.get(section, []):
            name = str(node.get("name") or "").strip()
            rendered_names.add(name)
            node_fill = color if _is_section_anchor(node) else fill
            lines.append(render_node(node, fill=node_fill, color=color))

    for node in section_nodes.get("", []):
        name = str(node.get("name") or "").strip()
        if name in rendered_names:
            continue
        rendered_names.add(name)
        lines.append(render_node(node))

    valid_edges: list[dict] = []
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation = str(edge.get("relation") or "").strip()
        if source not in node_names or target not in node_names:
            continue  # 悬空边：过滤（supervisor 应已拦截，此处防御）
        valid_edges.append(edge)
        attrs = []
        if relation:
            label = relation if len(relation) <= _MAX_LABEL_LEN else relation[:_MAX_LABEL_LEN] + "…"
            attrs.append(f'label="{_dot_quote(label)}"')
            attrs.append(f'color="{_RELATION_COLORS.get(relation, "#94a3b8")}"')
            attrs.append(f'fontcolor="{_RELATION_COLORS.get(relation, "#475569")}"')
        if str(edge.get("origin") or "").strip() == "new":
            attrs.append('penwidth="2.4"')
            attrs.append('color="#f59e0b"')
        elif str(edge.get("origin") or "").strip() == "history":
            attrs.append('penwidth="0.85"')
            attrs.append('color="#94a3b880"')
        if relation in {"包含", "属于"}:
            attrs.append('weight="4"')
            attrs.append('len="%s"' % ("0.5" if compact else "0.62"))
        elif relation in _DASHED_RELATIONS:
            attrs.append('style="dashed"')
            attrs.append('weight="1"')
            attrs.append('len="%s"' % ("0.7" if compact else "0.9"))
        else:
            attrs.append('len="%s"' % ("0.6" if compact else "0.78"))
        edge_attr = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f'  "{_dot_quote(source)}" -> "{_dot_quote(target)}"{edge_attr};')
    lines.append("}")



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
    """生成 Cytoscape.js 交互式知识图谱 HTML 文本（完整可点击页面）。"""
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
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
      color: #0f172a;
      background: #f8fbff;
    }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 400px;
      height: 100vh;
      min-height: 640px;
    }}
    #cy {{
      width: 100%;
      height: 100%;
      background:
        radial-gradient(circle at 18% 18%, rgba(56, 189, 248, 0.16), transparent 30%),
        radial-gradient(circle at 80% 24%, rgba(34, 197, 94, 0.12), transparent 26%),
        radial-gradient(circle at 66% 78%, rgba(251, 113, 133, 0.12), transparent 30%),
        linear-gradient(135deg, #ffffff 0%, #f5fbff 48%, #eef7ff 100%);
    }}
    aside {{
      border-left: 1px solid #e2e8f0;
      background: rgba(255, 255, 255, 0.92);
      padding: 22px;
      overflow: auto;
      backdrop-filter: blur(8px);
    }}
    h1 {{
      margin: 0 0 14px;
      font-size: 20px;
      line-height: 1.35;
    }}
    .meta {{
      color: #64748b;
      font-size: 13px;
      line-height: 1.7;
      margin-bottom: 18px;
    }}
    .panel-title {{
      font-size: 14px;
      color: #475569;
      margin: 20px 0 8px;
    }}
    .detail {{
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 14px;
      background: #f8fafc;
      line-height: 1.65;
      font-size: 14px;
      word-break: break-word;
    }}
    .detail .name {{ font-size: 16px; font-weight: 700; margin-bottom: 10px; }}
    .detail .block {{ margin: 10px 0 0; }}
    .detail .label {{
      color: #64748b;
      font-size: 12px;
      letter-spacing: 0.02em;
      margin-bottom: 4px;
    }}
    .detail .rel {{
      margin: 6px 0 0;
      padding: 8px 10px;
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
    }}
    .detail .rel-line {{ font-weight: 600; color: #0f172a; }}
    .detail .ev {{ color: #475569; font-size: 13px; margin-top: 4px; }}
    .detail .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .detail .chip {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e2e8f0;
      color: #334155;
      font-size: 12px;
    }}
    .detail .chip-new {{ background: #fde68a; color: #92400e; }}
    .detail .chip-old {{ background: #e2e8f0; color: #475569; }}
    .name-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .legend {{
      display: grid;
      gap: 8px;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: #334155;
      font-size: 13px;
    }}
    .swatch {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      flex: 0 0 auto;
    }}
    @media (max-width: 860px) {{
      .shell {{ grid-template-columns: 1fr; grid-template-rows: minmax(520px, 68vh) auto; }}
      aside {{ border-left: 0; border-top: 1px solid #e2e8f0; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div id="cy"></div>
    <aside>
      <h1>{escape(title or "知识图谱")}</h1>
      <div class="meta">滚轮缩放，拖动画布或节点。点击节点查看定义、章节、出入边、原文证据和相关概念。</div>
      <div class="panel-title">当前选中</div>
      <div id="detail" class="detail">点击一个节点查看定义、章节、出入边和相关概念。</div>
      <div class="panel-title">章节</div>
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
              'background-opacity': ele => {{
                if (ele.data('origin') === 'new') return ele.data('anchor') ? 1 : 0.78;
                if (ele.data('origin') === 'history') return ele.data('anchor') ? 0.52 : 0.16;
                return ele.data('anchor') ? 0.9 : 0.28;
              }},
              'border-color': ele => ele.data('origin') === 'new' ? '#f59e0b' : '#ffffff',
              'border-width': ele => ele.data('origin') === 'new' ? 4 : 2.4,
              'shadow-blur': ele => ele.data('anchor') ? 14 : 5,
              'shadow-color': ele => sectionColors[ele.data('section')] || '#94a3b8',
              'shadow-opacity': ele => ele.data('anchor') ? 0.28 : 0.16,
              'shadow-offset-x': 0,
              'shadow-offset-y': 2
            }}
          }},
          {{
            selector: 'edge',
            style: {{
              'curve-style': 'bezier',
              'target-arrow-shape': 'triangle',
              'target-arrow-color': ele => relationColors[ele.data('relation')] || '#94a3b8',
              'line-color': ele => relationColors[ele.data('relation')] || '#94a3b8',
              'line-opacity': ele => ele.data('origin') === 'new' ? 0.9 : (ele.data('origin') === 'history' ? 0.26 : 0.44),
              'width': ele => ele.data('origin') === 'new' ? 2.4 : 1.25,
              'label': 'data(label)',
              'font-size': 9,
              'font-family': 'Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif',
              'color': '#475569',
              'text-background-color': '#ffffff',
              'text-background-opacity': 0.72,
              'text-background-padding': 3,
              'text-rotation': 'autorotate'
            }}
          }},
          {{
            selector: '.faded',
            style: {{ 'opacity': 0.16, 'text-opacity': 0.16 }}
          }},
          {{
            selector: '.selected',
            style: {{ 'border-width': 4, 'z-index': 10 }}
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
      const relBlock = (edge) => `
        <div class="rel">
          <div class="rel-line">${{esc(edge.source().data('label'))}} → ${{esc(edge.data('label') || '相关')}} → ${{esc(edge.target().data('label'))}}</div>
          <div class="ev">${{esc(edge.data('evidence') || '暂无原文证据')}}</div>
        </div>`;

      cy.ready(() => cy.fit(undefined, 48));
      cy.on('tap', 'node', event => {{
        const node = event.target;
        cy.elements().addClass('faded');
        node.removeClass('faded').addClass('selected');
        node.neighborhood().removeClass('faded');
        const outgoing = node.outgoers('edge');
        const incoming = node.incomers('edge');
        const seen = new Set([node.id()]);
        const related = [];
        node.neighborhood('node').forEach((nb) => {{
          const id = nb.id();
          if (!seen.has(id)) {{
            seen.add(id);
            related.push(nb.data('label'));
          }}
        }});
        const relHtml = related.slice(0, 3).map((name) => `<span class="chip">${{esc(name)}}</span>`).join('')
          || '<span class="ev" style="margin:0">暂无一跳邻居</span>';
        const origin = node.data('origin');
        const originChip = origin === 'new'
          ? '<span class="chip chip-new">新增</span>'
          : origin === 'history'
            ? '<span class="chip chip-old">历史</span>'
            : '';
        const outHtml = outgoing.length
          ? outgoing.map(relBlock).join('')
          : '<div class="ev">暂无出边</div>';
        const inHtml = incoming.length
          ? incoming.map(relBlock).join('')
          : '<div class="ev">暂无入边</div>';
        detail.innerHTML = `
          <div class="name-row"><div class="name">${{esc(node.data('label'))}}</div>${{originChip}}</div>
          <div class="block"><div class="label">所属章节</div>${{esc(node.data('section') || '未分组')}}</div>
          <div class="block"><div class="label">定义（原文）</div>${{esc(node.data('definition') || '原文未给出独立定义')}}</div>
          <div class="block"><div class="label">出边</div>${{outHtml}}</div>
          <div class="block"><div class="label">入边</div>${{inHtml}}</div>
          <div class="block"><div class="label">相关概念</div><div class="chips">${{relHtml}}</div></div>`;
      }});
      cy.on('tap', 'edge', event => {{
        const edge = event.target;
        cy.elements().addClass('faded');
        edge.removeClass('faded');
        edge.connectedNodes().removeClass('faded').addClass('selected');
        detail.innerHTML = `
          <div class="name">${{esc(edge.source().data('label'))}} → ${{esc(edge.data('label') || '相关')}} → ${{esc(edge.target().data('label'))}}</div>
          <div class="block"><div class="label">原文证据</div>${{esc(edge.data('evidence') || '暂无原文证据')}}</div>`;
      }});
      cy.on('tap', event => {{
        if (event.target === cy) {{
          cy.elements().removeClass('faded selected');
          detail.textContent = '点击一个节点查看定义、章节、出入边和相关概念。';
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
    """同时导出交互式 HTML 和学习地图；失败的格式会被跳过。"""
    paths: dict[str, Path] = {}
    html_path = render_graph_html(nodes, edges, out_dir, f"{stem}.html", title)
    if html_path:
        paths["html"] = html_path
    try:
        md_path = Path(out_dir) / f"{stem}.md"
        md_path.write_text(
            build_learning_map(nodes, edges, title=title),
            encoding="utf-8",
        )
        paths["text"] = md_path
    except Exception:  # noqa: BLE001
        logger.warning("知识图谱学习地图落盘失败，已跳过", exc_info=True)
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
    "nodes_edges_to_dot",
    "render_graph_bundle",
    "render_graph_html",
]
