"""分层架构与系统拓扑渲染器（Layered Architecture & Hierarchy Renderer - 新拟物软质触感版）。

完整保留所有系统层级，去掉 L01 等多余标签，每一层作为独立的物理软质板块呈现。
"""
from __future__ import annotations

import re
from typing import List

from ...models.ir import TreeNode, TreeVisual
from .base import NEU_5_COLORS, SVG_ICON_TREE, escape, render_figure_caption


def render_tree(model: TreeVisual, in_master: bool = False) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""

    # 1. 甄别是否包含多余的“全图总称容器根节点”
    ids = {node.node_id for node in nodes}
    roots = [
        node for node in nodes
        if node.parent_id is None or node.parent_id not in ids
    ]

    target_nodes = list(nodes)
    if len(roots) == 1 and len(nodes) > 1:
        r = roots[0]
        is_dummy_wrapper = (
            r.title.strip().lower() in {model.title.strip().lower(), "架构图", "分层架构", "系统架构"}
            and not (r.detail or "").strip()
        )
        if is_dummy_wrapper:
            target_nodes = [n for n in nodes if n.node_id != r.node_id]

    effective_layers: List[tuple[str, str]] = []  # (title, detail)

    if len(target_nodes) == 1 and ";" in (target_nodes[0].detail or ""):
        # 单节点分号拆分兜底
        sole = target_nodes[0]
        sub_items = re.split(r"[；;\n]+", sole.detail)
        clean_subs = [s.strip() for s in sub_items if s.strip()]
        if len(clean_subs) >= 2:
            for item in clean_subs:
                m = re.match(r"^([^()（）]+)(?:[（(](.*)[)）])?$", item)
                if m:
                    t = m.group(1).replace("包含：", "").strip()
                    d = (m.group(2) or "").strip()
                    effective_layers.append((t, d))
                else:
                    effective_layers.append((item, ""))
        else:
            effective_layers.append((sole.title, sole.detail))
    else:
        for n in target_nodes:
            effective_layers.append((n.title, n.detail))

    # 渲染为新拟物软质触感的分层架构卡片（Neumorphic Layer Slabs）
    cards: list[str] = []

    for idx, (title, detail) in enumerate(effective_layers):
        color, bg, border = NEU_5_COLORS[idx % len(NEU_5_COLORS)]

        detail_html = (
            f'<div class="vm-tree-layer-detail">{escape(detail)}</div>'
            if detail
            else ""
        )
        cards.append(
            f'<div class="vm-tree-layer-card" style="--layer-accent: {color}; --layer-accent-bg: {bg}; --layer-accent-border: {border};">'
            f'  <div class="vm-tree-layer-lead">'
            f'    <span class="vm-tree-layer-dot" style="background: {color};"></span>'
            f'    <div class="vm-tree-layer-title">{escape(title)}</div>'
            f'  </div>'
            f'  <div class="vm-tree-layer-divider"></div>'
            f'  {detail_html}'
            f'</div>'
        )

    tree_container_html = f"""
  <div class="vm-tree-container">
    {''.join(cards)}
  </div>
"""

    if in_master:
        title_html = (
            f'<div class="vm-widget-title">{escape(model.title)}</div>'
            if model.title
            else ""
        )
        return f"""
<div class="vm-master-widget vm-widget-tree">
  {title_html}
{tree_container_html}
</div>
"""

    caption_html = render_figure_caption(model.title)
    return f"""
<div class="vm-visual">
{tree_container_html}
  {caption_html}
</div>
"""


__all__ = ["render_tree"]
