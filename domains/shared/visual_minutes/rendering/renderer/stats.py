"""关键量化成效大卡渲染器（Stats KPI Cards Renderer）。"""
from __future__ import annotations

from ...models.ir import StatsVisual
from .base import SVG_ICON_STATS, escape, render_figure_caption


def render_stats(model: StatsVisual, in_master: bool = False) -> str:
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

    stats_grid_html = f"""
  <div class="vm-stats-grid">
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
<div class="vm-master-widget vm-widget-stats">
  {title_html}
{stats_grid_html}
</div>
"""

    caption_html = render_figure_caption(model.title)
    return f"""
<div class="vm-visual">
{stats_grid_html}
  {caption_html}
</div>
"""


__all__ = ["render_stats"]
