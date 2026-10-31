"""流转推进管线渲染器（Process Pipeline Renderer - 新拟物软质触感版）。

卡片无冗余序号前缀，卡片与卡片之间使用短有向箭头相连。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...models.ir import FlowEdge, FlowNode, FlowVisual
from .base import NEU_5_COLORS, SVG_ICON_FLOW, escape, render_figure_caption


def render_flow(model: FlowVisual, in_master: bool = False) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""
    edges = model.data.edges

    # 建立顺向边索引
    forward_edges: Dict[Tuple[str, str], FlowEdge] = {}
    for e in edges:
        forward_edges[(e.source, e.target)] = e

    # 渲染推进管线卡片流（Neumorphism Pipeline Cards）
    step_items: list[str] = []
    num_nodes = len(nodes)

    for idx, node in enumerate(nodes, start=1):
        color, bg, border = NEU_5_COLORS[(idx - 1) % len(NEU_5_COLORS)]

        # 检查是否有顺向边 label
        next_edge_label = ""
        if idx < num_nodes:
            nxt = nodes[idx]
            edge = forward_edges.get((node.node_id, nxt.node_id))
            if edge and edge.label:
                next_edge_label = edge.label

        delivery_html = ""
        if next_edge_label:
            delivery_html = (
                f'<div class="vm-flow-delivery">'
                f'  <svg class="vm-delivery-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                f'    <polyline points="9 18 15 12 9 6"></polyline>'
                f'  </svg>'
                f'  <span class="vm-delivery-text">{escape(next_edge_label)}</span>'
                f'</div>'
            )

        detail_html = (
            f'<div class="vm-flow-node-detail">{escape(node.detail)}</div>'
            if node.detail
            else ""
        )

        step_items.append(
            f'<div class="vm-flow-step-card" style="--step-accent: {color}; --step-accent-bg: {bg}; --step-accent-border: {border};">'
            f'  <div class="vm-step-card-header">'
            f'    <div class="vm-flow-node-title-row">'
            f'      <span class="vm-flow-step-dot" style="background: {color};"></span>'
            f'      <div class="vm-flow-node-title">{escape(node.title)}</div>'
            f'    </div>'
            f'  </div>'
            f'  {detail_html}'
            f'  {delivery_html}'
            f'</div>'
        )

        # 卡片之间连接的短有向箭头
        if idx < num_nodes:
            step_items.append(
                f'<div class="vm-flow-connector" aria-hidden="true">'
                f'  <svg class="vm-connector-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
                f'    <line x1="5" y1="12" x2="19" y2="12"></line>'
                f'    <polyline points="13 6 19 12 13 18"></polyline>'
                f'  </svg>'
                f'</div>'
            )

    flow_container_html = f"""
  <div class="vm-flow-container">
    <div class="vm-flow-track">
      {''.join(step_items)}
    </div>
  </div>
"""

    if in_master:
        title_html = (
            f'<div class="vm-widget-title">{escape(model.title)}</div>'
            if model.title
            else ""
        )
        return f"""
<div class="vm-master-widget vm-widget-flow">
  {title_html}
{flow_container_html}
</div>
"""

    caption_html = render_figure_caption(model.title)
    return f"""
<div class="vm-visual">
{flow_container_html}
  {caption_html}
</div>
"""


__all__ = ["render_flow"]
