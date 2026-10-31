"""时序里程碑演进路线渲染器（Timeline Flow Renderer - 轴线贯穿与顶置刻度版）。"""
from __future__ import annotations

from ...models.ir import TimelineVisual
from .base import NEU_5_COLORS, escape, render_figure_caption


def render_timeline(model: TimelineVisual, in_master: bool = False) -> str:
    events = model.data.events
    if not events:
        return ""

    cols = []
    for idx, ev in enumerate(events):
        color, bg, border = NEU_5_COLORS[idx % len(NEU_5_COLORS)]
        detail_html = (
            f'<div class="vm-timeline-detail">{escape(ev.detail)}</div>'
            if ev.detail
            else ""
        )
        cols.append(
            f'<div class="vm-timeline-col" style="--event-accent: {color}; --event-accent-bg: {bg}; --event-accent-border: {border};">'
            f'  <div class="vm-timeline-time-label">{escape(ev.time_label)}</div>'
            f'  <div class="vm-timeline-node">'
            f'    <span class="vm-timeline-dot"></span>'
            f'  </div>'
            f'  <div class="vm-timeline-card">'
            f'    <div class="vm-timeline-title">{escape(ev.title)}</div>'
            f'    {detail_html}'
            f'  </div>'
            f'</div>'
        )

    timeline_canvas_html = f"""
  <div class="vm-timeline-canvas">
    <div class="vm-timeline-track">
      {''.join(cols)}
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
<div class="vm-master-widget vm-widget-timeline">
  {title_html}
{timeline_canvas_html}
</div>
"""

    caption_html = render_figure_caption(model.title)
    return f"""
<div class="vm-visual">
{timeline_canvas_html}
  {caption_html}
</div>
"""


__all__ = ["render_timeline"]
