"""层级树渲染器。"""
from __future__ import annotations

from ...models.ir import TreeVisual
from .base import escape


def _render_nodes(nodes, parent_id=None) -> str:
    children = [n for n in nodes if n.parent_id == parent_id]
    if not children:
        return ""
    items = []
    for node in children:
        inner = _render_nodes(nodes, node.node_id)
        items.append(
            f"<li><div class=\"vm-tree-title\">{escape(node.title)}</div>"
            + (f'<div class="vm-tree-detail">{escape(node.detail)}</div>' if node.detail else "")
            + (f"<ul>{inner}</ul>" if inner else "")
            + "</li>"
        )
    return "".join(items)


def render_tree(model: TreeVisual) -> str:
    nodes = model.data.nodes
    if not nodes:
        return ""
    roots = [n for n in nodes if n.parent_id is None or n.parent_id not in {x.node_id for x in nodes}]
    if not roots:
        return ""
    items = []
    for node in roots:
        inner = _render_nodes(nodes, node.node_id)
        items.append(
            f"<li><div class=\"vm-tree-title\">{escape(node.title)}</div>"
            + (f'<div class="vm-tree-detail">{escape(node.detail)}</div>' if node.detail else "")
            + (f"<ul>{inner}</ul>" if inner else "")
            + "</li>"
        )
    body = "".join(items)
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{escape(model.title)}</div>
  <ul class="vm-tree">{body}</ul>
</div>
"""


__all__ = ["render_tree"]
