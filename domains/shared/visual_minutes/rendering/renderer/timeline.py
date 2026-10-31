"""时序里程碑演进路线渲染器（Timeline Flow Renderer - 新拟物软质触感版）。"""
from __future__ import annotations

from ...models.ir import TimelineVisual
from .base import NEU_5_COLORS, SVG_ICON_TIMELINE, escape, render_figure_caption


def render_timeline(model: TimelineVisual, in_master: bool = False) -> str:
    events = model.data.events
    if not events:
        return ""

    cards = []
    for idx, ev in enumerate(events):
        color, bg, border = NEU_5_COLORS[idx % len(NEU_5_COLORS)]
        detail_html = (
            f'<div class="vm-timeline-detail">{escape(ev.detail)}</div>'
            if ev.detail
            else ""
        )
        cards.append(
            f'<div class="vm-timeline-item" style="--event-accent: {color}; --event-accent-bg: {bg}; --event-accent-border: {border};">'
            f'  <div class="vm-timeline-item-header">'
            f'    <div class="vm-timeline-time">{escape(ev.time_label)}</div>'
            f'    <span class="vm-timeline-dot" style="background: {color};"></span>'
            f'  </div>'
            f'  <div class="vm-timeline-title">{escape(ev.title)}</div>'
            f'  {detail_html}'
            f'</div>'
        )

    timeline_canvas_html = f"""
  <div class="vm-timeline-canvas">
    <div class="vm-timeline-track">
      {''.join(cards)}
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
