"""关键量化成效大卡渲染器（Stats KPI Cards Renderer）。"""
from __future__ import annotations

from ...models.ir import StatsVisual
from .base import SVG_ICON_STATS, escape


def render_stats(model: StatsVisual) -> str:
    if not model.data.metrics:
        return ""

    cards = []
    for m in model.data.metrics:
        ev_html = (
            f'<div class="vm-stat-evidence">{escape(m.evidence)}</div>'
            if m.evidence and len(m.evidence) < 80
            else ""
        )
        cards.append(
            f'<div class="vm-stat-card">'
            f'  <div class="vm-stat-value">{escape(m.value)}</div>'
            f'  <div class="vm-stat-label">{escape(m.label)}</div>'
            f'  {ev_html}'
            f'</div>'
        )

    title = escape(model.title)
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{SVG_ICON_STATS} {title}</div>
  <div class="vm-stats-grid">
    {''.join(cards)}
  </div>
</div>
"""


__all__ = ["render_stats"]
