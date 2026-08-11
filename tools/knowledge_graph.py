"""knowledge_graph.py —— 知识图谱渲染（graphviz 封装，无痛降级）。

把图数据（nodes + edges）渲染为 PNG 知识图谱图：

- 依赖：系统安装 Graphviz（``dot`` 可执行；Windows 需装 Graphviz，Linux 用
  apt/brew 装 graphviz + 中文字体）
- 产物：``dot -Tpng`` 输出 PNG；节点带定义 tooltip，边带关系 label
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
    "等价于": "#9333ea",
    "转化": "#0f766e",
    "相关": "#475569",
}
_CYTOSCAPE_CDN = "https://cdn.jsdelivr.net/npm/cytoscape@3.31.2/dist/cytoscape.min.js"


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
    return None


def graphviz_available() -> bool:
    """dot 是否可用（PATH 或常见安装路径）。"""
    return _find_dot() is not None


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
    """DOT 字符串转义：反斜杠与双引号。"""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _wrap_label(text: str, width: int = 8, max_len: int = 30) -> str:
    """把中文短语按固定字数换行，避免节点横向过宽。"""
    text = re.sub(r"\s+", " ", text.strip())[:max_len]
    if len(text) <= width:
        return text
    return "\\n".join(text[i : i + width] for i in range(0, len(text), width))


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
) -> tuple[str, list[dict]]:
    """把图数据转成 DOT 文本；返回 (dot_text, 有效边)。

    - 悬空边（source/target 不在 nodes 中）会被过滤并从返回值带出（供告警）
    - 节点 name 去重（同名节点合并）
    """
    font = _pick_font()
    degrees = _node_degrees(nodes, edges)
    max_degree = max(degrees.values(), default=1)
    lines = [
        "digraph knowledge_graph {",
        "  graph [",
        f'    fontname="{font}",',
        "    bgcolor=\"#fbfdff:#eef7ff\",",
        "    layout=fdp,",
        "    outputorder=edgesfirst,",
        "    overlap=false,",
        "    splines=true,",
        "    K=0.38,",
        "    sep=\"+8\",",
        "    size=\"13,7!\",",
        "    ratio=compress,",
        "    dpi=180,",
        "    concentrate=true,",
        "    pad=0.22,",
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
        "    fontsize=12,",
        "    margin=\"0.04,0.04\"",
        "  ];",
        "  edge [",
        f'    fontname="{font}",',
        "    fontsize=9,",
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
        size = 0.72 + (0.34 * ratio)
        if is_anchor:
            size = max(size, 1.08)
        fontsize = 15 if is_anchor else 10 if len(name) > 8 else 11
        fontcolor = "#ffffff" if is_anchor else "#0f172a"
        attrs = [
            f'label="{_dot_quote(_wrap_label(name, width=5 if is_anchor else 4, max_len=18))}"',
            'fixedsize="true"',
            f'width="{size:.2f}"',
            f'height="{size:.2f}"',
            f'fontsize="{fontsize}"',
            f'fillcolor="{fill}"',
            f'color="{color}"',
            f'fontcolor="{fontcolor}"',
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
        if relation in {"包含", "属于"}:
            attrs.append('weight="4"')
            attrs.append('len="0.85"')
        elif relation in {"相关", "示例"}:
            attrs.append('style="dashed"')
            attrs.append('weight="1"')
            attrs.append('len="1.18"')
        else:
            attrs.append('len="1.05"')
        edge_attr = f" [{', '.join(attrs)}]" if attrs else ""
        lines.append(f'  "{_dot_quote(source)}" -> "{_dot_quote(target)}"{edge_attr};')
    lines.append("}")
    return "\n".join(lines), valid_edges


def _render_graphviz(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    filename: str,
    output_format: str,
    title: str = "",
) -> Path | None:
    """用 Graphviz 把图数据渲染为指定格式。"""
    if not nodes:
        logger.warning("知识图谱无节点，跳过 %s 生成", output_format)
        return None
    dot = _find_dot()
    if not dot:
        logger.warning(
            "未检测到 graphviz（dot），无法生成知识图谱 %s"
            "（安装：Windows 装 Graphviz；Linux 用 apt/brew 安装）"
            % output_format
        )
        return None
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        dot_text, valid_edges = nodes_edges_to_dot(nodes, edges, title=title)
        if len(valid_edges) < len(edges):
            logger.warning(
                "知识图谱过滤了 %d 条悬空边（source/target 不在 nodes 中）",
                len(edges) - len(valid_edges),
            )
        out_path = out_dir / filename
        result = subprocess.run(
            [dot, "-Kfdp", f"-T{output_format}", "-o", str(out_path)],
            input=dot_text.encode("utf-8"),
            capture_output=True,
            timeout=_RENDER_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            logger.warning(
                "graphviz 渲染 %s 失败（rc=%s）：%s",
                output_format,
                result.returncode,
                (result.stderr or b"").decode("utf-8", errors="replace")[-500:],
            )
            return None
        if not out_path.exists():
            logger.warning("graphviz 未产出 %s 文件：%s", output_format, out_path)
            return None
        return out_path
    except subprocess.TimeoutExpired:
        logger.warning(
            "graphviz 渲染 %s 超时（>%ss），已放弃",
            output_format,
            _RENDER_TIMEOUT_SECONDS,
        )
        return None
    except Exception:  # noqa: BLE001 - 渲染失败不影响主流程
        logger.warning("知识图谱 %s 生成异常，已跳过", output_format, exc_info=True)
        return None


def render_knowledge_graph(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    filename: str = "knowledge_graph.png",
    title: str = "",
) -> Path | None:
    """把图数据渲染为 PNG 知识图谱文件。"""
    return _render_graphviz(nodes, edges, out_dir, filename, "png", title=title)


def render_knowledge_graph_svg(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    filename: str = "knowledge_graph.svg",
    title: str = "",
) -> Path | None:
    """把图数据渲染为 SVG 矢量知识图谱文件。"""
    return _render_graphviz(nodes, edges, out_dir, filename, "svg", title=title)


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
        size = 92 if is_anchor else 42 + round(26 * degree / max(max_degree, 1))
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
                }
            }
        )
    return elements


def render_knowledge_graph_html(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    filename: str = "knowledge_graph.html",
    title: str = "",
) -> Path | None:
    """生成 Cytoscape.js 交互式知识图谱 HTML。"""
    if not nodes:
        logger.warning("知识图谱无节点，跳过 HTML 生成")
        return None
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
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
      grid-template-columns: minmax(0, 1fr) 320px;
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
      <div class="meta">滚轮缩放，拖动画布或节点；点击节点查看定义，点击关系查看证据。</div>
      <div class="panel-title">当前选中</div>
      <div id="detail" class="detail">点击一个节点或关系查看详情。</div>
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
              'text-max-width': 78,
              'font-family': 'Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif',
              'font-size': ele => ele.data('anchor') ? 14 : 10,
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
              'border-width': 2.4,
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
              'line-opacity': 0.44,
              'width': 1.25,
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
          componentSpacing: 140,
          nodeRepulsion: 12000,
          idealEdgeLength: edge => edge.data('relation') === '包含' || edge.data('relation') === '属于' ? 96 : 138,
          edgeElasticity: 72,
          nestingFactor: 0.9,
          gravity: 0.36,
          numIter: 2400
        }}
      }});

      cy.ready(() => cy.fit(undefined, 48));
      cy.on('tap', 'node', event => {{
        const node = event.target;
        cy.elements().addClass('faded');
        node.removeClass('faded').addClass('selected');
        node.neighborhood().removeClass('faded');
        detail.innerHTML = `<strong>${{node.data('label')}}</strong><br>章节：${{node.data('section') || '未分组'}}<br>${{node.data('definition') || '暂无定义'}}`;
      }});
      cy.on('tap', 'edge', event => {{
        const edge = event.target;
        cy.elements().addClass('faded');
        edge.removeClass('faded');
        edge.connectedNodes().removeClass('faded').addClass('selected');
        detail.innerHTML = `<strong>${{edge.source().data('label')}} → ${{edge.target().data('label')}}</strong><br>关系：${{edge.data('label') || '相关'}}<br>${{edge.data('evidence') || '暂无证据'}}`;
      }});
      cy.on('tap', event => {{
        if (event.target === cy) {{
          cy.elements().removeClass('faded selected');
          detail.textContent = '点击一个节点或关系查看详情。';
        }}
      }});
    }}
  </script>
</body>
</html>
"""
        out_path = out_dir / filename
        out_path.write_text(html, encoding="utf-8")
        return out_path
    except Exception:  # noqa: BLE001 - HTML 生成失败不影响主流程
        logger.warning("知识图谱 HTML 生成异常，已跳过", exc_info=True)
        return None


def render_knowledge_graph_bundle(
    nodes: list[dict],
    edges: list[dict],
    out_dir: Path | str,
    stem: str = "knowledge_graph",
    title: str = "",
) -> dict[str, Path]:
    """同时导出 PNG、SVG 和交互式 HTML；失败的格式会被跳过。"""
    paths: dict[str, Path] = {}
    png_path = render_knowledge_graph(nodes, edges, out_dir, f"{stem}.png", title)
    if png_path:
        paths["png"] = png_path
    svg_path = render_knowledge_graph_svg(nodes, edges, out_dir, f"{stem}.svg", title)
    if svg_path:
        paths["svg"] = svg_path
    html_path = render_knowledge_graph_html(nodes, edges, out_dir, f"{stem}.html", title)
    if html_path:
        paths["html"] = html_path
    return paths


__all__ = [
    "graphviz_available",
    "nodes_edges_to_dot",
    "render_knowledge_graph",
    "render_knowledge_graph_bundle",
    "render_knowledge_graph_html",
    "render_knowledge_graph_svg",
]
