"""Visual Minutes 确定性渲染器入口。"""
from __future__ import annotations

from ...models.ir import VisualUnion
from .base import TASTE_CSS, escape
from .flow import render_flow
from .master import render_master
from .stats import render_stats
from .table import render_table
from .timeline import render_timeline
from .tree import render_tree

RENDERERS = {
    "timeline": render_timeline,
    "table": render_table,
    "flow": render_flow,
    "tree": render_tree,
    "stats": render_stats,
}


def render_visual(visual: VisualUnion) -> str:
    fn = RENDERERS.get(visual.kind)
    if fn is None:
        return ""
    try:
        return fn(visual)
    except Exception:  # noqa: BLE001 - 单图失败不拖垮整页
        return ""


__all__ = [
    "TASTE_CSS",
    "escape",
    "render_master",
    "render_visual",
]
