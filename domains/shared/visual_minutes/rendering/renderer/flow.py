"""流转链路与闭环机制渲染器（Flow & Closed Loop Renderer - 飞书旗舰商务版）。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...models.ir import FlowEdge, FlowNode, FlowVisual
from .base import SVG_ICON_FLOW, SVG_ICON_LOOP, escape


def _detect_chain_and_loops(
    nodes: List[FlowNode],
    edges: List[FlowEdge],
) -> Tuple[List[FlowNode], List[FlowEdge], Dict[Tuple[str, str], FlowEdge]]:
    """分离主干推进步骤与反向闭环反馈边。"""
    ids = [n.node_id for n in nodes]
    pos_map = {nid: idx for idx, nid in enumerate(ids)}

    forward_nodes = list(nodes)
    loop_edges: List[FlowEdge] = []
    forward_edges: Dict[Tuple[str, str], FlowEdge] = {}

    for e in edges:
        if e.source in pos_map and e.target in pos_map:
            # 若 target 处于当前或更前位置，视为回流/闭环边
            if pos_map[e.target] <= pos_map[e.source]:
                loop_edges.append(e)
            else:
                forward_edges[(e.source, e.target)] = e

    return forward_nodes, loop_edges, forward_edges


def render_flow(model: FlowVisual) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""
    edges = model.data.edges

    forward_nodes, loop_edges, forward_edges = _detect_chain_and_loops(nodes, edges)

    # 1. 渲染主干推进卡片流（Feishu Pipeline Cards）
    step_items: list[str] = []
    num_nodes = len(forward_nodes)

    for idx, node in enumerate(forward_nodes, start=1):
        step_tag = f"STEP {idx:02d}"

        # 检查是否有从当前节点流向下一个节点的顺向边
        next_edge_label = ""
        if idx < num_nodes:
            nxt = forward_nodes[idx]
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

    # 2. 渲染闭环反馈机制面板（Feishu 反馈回路专区）
    loop_section_html = ""
    if loop_edges:
        node_title_map = {n.node_id: n.title for n in nodes}
        loop_cards: list[str] = []

        for idx, le in enumerate(loop_edges, start=1):
            src_name = escape(node_title_map.get(le.source, le.source))
            tgt_name = escape(node_title_map.get(le.target, le.target))
            lbl_text = escape(le.label) if le.label else "执行反向策略优化与迭代更新"

            loop_cards.append(
                f'<div class="vm-loop-card">'
                f'  <div class="vm-loop-card-top">'
                f'    <span class="vm-loop-card-badge">闭环回路 {idx:02d}</span>'
                f'    <span class="vm-loop-tag-type">反馈驱动</span>'
                f'  </div>'
                f'  <div class="vm-loop-route">'
                f'    <span class="vm-loop-node vm-loop-src">{src_name}</span>'
                f'    <span class="vm-loop-arrow-wrap">'
                f'      <svg class="vm-loop-svg" width="16" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                f'        <polyline points="9 14 4 9 9 4"></polyline>'
                f'        <path d="M20 20v-7a4 4 0 0 0-4-4H4"></path>'
                f'      </svg>'
                f'      <span class="vm-loop-arrow-text">反哺至</span>'
                f'    </span>'
                f'    <span class="vm-loop-node vm-loop-tgt">{tgt_name}</span>'
                f'  </div>'
                f'  <div class="vm-loop-action-box">'
                f'    <span class="vm-action-label">调优与反哺逻辑</span>'
                f'    <span class="vm-action-desc">{lbl_text}</span>'
                f'  </div>'
                f'</div>'
            )

        loop_section_html = f"""
    <div class="vm-flow-loop-box">
      <div class="vm-flow-loop-header">
        <span class="vm-loop-header-badge">{SVG_ICON_LOOP} 闭环反馈机制</span>
        <span class="vm-loop-header-desc">后序环节结果反哺前序模块，形成自演进回流回路</span>
      </div>
      <div class="vm-flow-loop-grid">
        {''.join(loop_cards)}
      </div>
    </div>
"""

    title = escape(model.title)
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{SVG_ICON_FLOW} {title}</div>
  <div class="vm-flow-container">
    <div class="vm-flow-track">
      {''.join(step_items)}
    </div>
    {loop_section_html}
  </div>
</div>
"""


__all__ = ["render_flow"]
