"""流程 / 因果 / 循环渲染器。"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...models.ir import FlowEdge, FlowNode, FlowVisual
from .base import escape


def _linear_order(
    nodes: List[FlowNode],
    edges: List[FlowEdge],
) -> Tuple[List[FlowNode], bool]:
    """若图是一条链，返回链顺序；否则按入度稳定排序并标记为非链。"""
    ids = [n.node_id for n in nodes]
    id_set = set(ids)
    valid = [e for e in edges if e.source in id_set and e.target in id_set]
    out: Dict[str, List[str]] = {i: [] for i in ids}
    indeg: Dict[str, int] = {i: 0 for i in ids}
    for edge in valid:
        out[edge.source].append(edge.target)
        indeg[edge.target] += 1

    sources = [i for i in ids if indeg[i] == 0]
    is_chain = (
        len(valid) == len(nodes) - 1
        and len(sources) == 1
        and all(len(out[i]) <= 1 for i in ids)
        and all(indeg[i] <= 1 for i in ids)
    )
    if is_chain:
        order_ids: list[str] = []
        cur: Optional[str] = sources[0]
        while cur is not None and cur not in order_ids:
            order_ids.append(cur)
            cur = out[cur][0] if out[cur] else None
        if len(order_ids) == len(nodes):
            by_id = {n.node_id: n for n in nodes}
            return [by_id[i] for i in order_ids], True

    # 非链式：Kahn 拓扑排序，同层按输入顺序，保证结果确定。
    remaining = list(ids)
    ordered: list[str] = []
    while remaining:
        ready = [i for i in remaining if indeg[i] == 0]
        if not ready:
            ordered.extend(remaining)
            break
        for i in ready:
            ordered.append(i)
            remaining.remove(i)
            for target in out[i]:
                indeg[target] -= 1
    by_id = {n.node_id: n for n in nodes}
    return [by_id[i] for i in ordered if i in by_id], False


def _arrow(label: str = "") -> str:
    svg = (
        '<svg class="vm-flow-arrow" width="34" height="14" viewBox="0 0 34 14" '
        'aria-hidden="true"><path d="M1 7h27" fill="none" stroke="currentColor" '
        'stroke-width="1.5" stroke-linecap="round"/><path d="M23 2.5 29 7l-6 4.5" '
        'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg>'
    )
    if label:
        return (
            f'<span class="vm-flow-arrow-wrap">{svg}'
            f'<span class="vm-flow-arrow-label">{escape(label)}</span></span>'
        )
    return f'<span class="vm-flow-arrow-wrap">{svg}</span>'


def render_flow(model: FlowVisual) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""
    edges = model.data.edges
    ordered, is_chain = _linear_order(nodes, edges)
    edge_by_pair = {(e.source, e.target): e for e in edges}

    cards: list[str] = []
    for idx, node in enumerate(ordered):
        if idx:
            prev = ordered[idx - 1]
            edge = edge_by_pair.get((prev.node_id, node.node_id))
            if is_chain and edge is not None:
                cards.append(_arrow(edge.label))
        cards.append(
            f'<div class="vm-flow-node">'
            f'<div class="vm-flow-node-title">{escape(node.title)}</div>'
            + (f'<div class="vm-flow-node-detail">{escape(node.detail)}</div>' if node.detail else "")
            + "</div>"
        )

    edge_lines = ""
    if not is_chain and edges:
        titles = {n.node_id: n.title for n in nodes}
        edge_lines = '<div class="vm-flow-edges">' + "".join(
            f'<div class="vm-flow-edge"><span>{escape(titles.get(e.source, e.source))}</span>'
            f'<span class="vm-flow-edge-arrow" aria-hidden="true">→</span>'
            f'<span>{escape(titles.get(e.target, e.target))}</span>'
            + (f'<span class="vm-flow-edge-label">{escape(e.label)}</span>' if e.label else "")
            + "</div>"
            for e in edges
        ) + "</div>"
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{escape(model.title)}</div>
  <div class="vm-flow">{''.join(cards)}</div>
  {edge_lines}
</div>
"""


__all__ = ["render_flow"]
