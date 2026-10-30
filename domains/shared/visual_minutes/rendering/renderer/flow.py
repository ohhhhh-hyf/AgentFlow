"""流转推进管线渲染器（Process Pipeline Renderer - 飞书旗舰商务版）。

专注于呈现清晰、专业、高质感的先后推进步骤与交付链路，杜绝任何杂乱的堆叠文本。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...models.ir import FlowEdge, FlowNode, FlowVisual
from .base import SVG_ICON_FLOW, escape, render_figure_caption


def render_flow(model: FlowVisual, in_master: bool = False) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""
    edges = model.data.edges

    # 建立顺向边索引
    forward_edges: Dict[Tuple[str, str], FlowEdge] = {}
    for e in edges:
        forward_edges[(e.source, e.target)] = e

    # 渲染推进管线卡片流（Feishu Pipeline Cards）
    step_items: list[str] = []
    num_nodes = len(nodes)

    for idx, node in enumerate(nodes, start=1):
        step_tag = f"STEP {idx:02d}"

        # 检查是否有从当前节点流向下一个节点的顺向边
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
            f'<div class="vm-flow-step-card">'
            f'  <div class="vm-step-card-header">'
            f'    <span class="vm-flow-node-step">{step_tag}</span>'
            f'    <div class="vm-flow-node-title">{escape(node.title)}</div>'
            f'  </div>'
            f'  {detail_html}'
            f'  {delivery_html}'
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
