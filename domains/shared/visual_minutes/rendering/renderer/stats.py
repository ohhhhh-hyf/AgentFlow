"""指标卡渲染器。"""
from __future__ import annotations

from ...models.ir import StatsVisual
from .base import escape


def render_stats(model: StatsVisual) -> str:
    if not model.data.metrics:
        return ""
    cards = "".join(
        f'<div class="vm-stat"><div class="vm-stat-value">{escape(m.value)}</div>'
        f'<div class="vm-stat-label">{escape(m.label)}</div></div>'
        for m in model.data.metrics
    )
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{escape(model.title)}</div>
  <div class="vm-stats">{cards}</div>
</div>
"""


__all__ = ["render_stats"]
