"""分层架构与系统拓扑渲染器（Layered Architecture & Hierarchy Renderer - 飞书旗舰商务版）。

确保系统架构（如 5 层体系）完整保留所有层级，
每一层都作为独立的飞书视觉层级呈现，严禁漏层或折叠。
"""
from __future__ import annotations

import re
from typing import List

from ...models.ir import TreeNode, TreeVisual
from .base import SVG_ICON_TREE, escape, render_figure_caption


def render_tree(model: TreeVisual, in_master: bool = False) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""

    # 1. 甄别是否包含多余的“全图总称容器根节点”
    # 仅当且仅当：只有一个根节点，且该根节点标题与图表标题基本一致、且无实际 detail 描述时，才剥离该外壳
    ids = {node.node_id for node in nodes}
    roots = [
        node for node in nodes
        if node.parent_id is None or node.parent_id not in ids
    ]

    target_nodes = list(nodes)
    if len(roots) == 1 and len(nodes) > 1:
        r = roots[0]
        # 判断 r 是否仅为全图标题占位
        is_dummy_wrapper = (
            r.title.strip().lower() in {model.title.strip().lower(), "架构图", "分层架构", "系统架构"}
            and not (r.detail or "").strip()
        )
        if is_dummy_wrapper:
            target_nodes = [n for n in nodes if n.node_id != r.node_id]

    effective_layers: List[tuple[str, str, str]] = []  # (badge, title, detail)

    if len(target_nodes) == 1 and ";" in (target_nodes[0].detail or ""):
        # 单节点分号拆分兜底
        sole = target_nodes[0]
        sub_items = re.split(r"[；;\n]+", sole.detail)
        clean_subs = [s.strip() for s in sub_items if s.strip()]
        if len(clean_subs) >= 2:
            for idx, item in enumerate(clean_subs, start=1):
                m = re.match(r"^([^()（）]+)(?:[（(](.*)[)）])?$", item)
                if m:
                    t = m.group(1).replace("包含：", "").strip()
                    d = (m.group(2) or "").strip()
                    effective_layers.append((f"L{idx:02d}", t, d))
                else:
                    effective_layers.append((f"L{idx:02d}", item, ""))
        else:
            effective_layers.append(("L01", sole.title, sole.detail))
    else:
        for idx, n in enumerate(target_nodes, start=1):
            effective_layers.append((f"L{idx:02d}", n.title, n.detail))

    # 渲染为飞书风格的现代化分层架构卡片（Layered Architecture Canvas）
    cards: list[str] = []
    # 飞书 5 色阶：自顶向下层级色彩
    badge_colors = [
        ("var(--vm-accent-blue)", "var(--vm-accent-blue-bg)", "var(--vm-accent-blue-border)"),
        ("var(--vm-accent-cyan)", "var(--vm-accent-cyan-bg)", "var(--vm-accent-cyan-border)"),
        ("var(--vm-accent-purple)", "var(--vm-accent-purple-bg)", "var(--vm-accent-purple-border)"),
        ("var(--vm-accent-emerald)", "var(--vm-accent-emerald-bg)", "var(--vm-accent-emerald-border)"),
        ("var(--vm-accent-amber)", "var(--vm-accent-amber-bg)", "var(--vm-accent-amber-border)"),
    ]

    for idx, (badge_text, title, detail) in enumerate(effective_layers):
        color, bg, border = badge_colors[idx % len(badge_colors)]
        style_badge = f'style="color: {color}; background-color: {bg}; border-color: {border};"'
        style_card = f'style="border-left-color: {color};"'

        detail_html = (
            f'<div class="vm-tree-layer-detail">{escape(detail)}</div>'
            if detail
            else ""
        )
        cards.append(
            f'<div class="vm-tree-layer-card" {style_card}>'
            f'  <span class="vm-tree-layer-badge" {style_badge}>{badge_text}</span>'
            f'  <div class="vm-tree-layer-title">{escape(title)}</div>'
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
