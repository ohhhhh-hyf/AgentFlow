"""时序里程碑演进路线渲染器（Timeline Flow Renderer）。"""
from __future__ import annotations

from ...models.ir import TimelineVisual
from .base import SVG_ICON_TIMELINE, escape


def render_timeline(model: TimelineVisual) -> str:
    events = model.data.events
    if not events:
        return ""

    cards = []
    for ev in events:
        detail_html = (
            f'<div class="vm-timeline-detail">{escape(ev.detail)}</div>'
            if ev.detail
            else ""
        )
        cards.append(
            f'<div class="vm-timeline-item">'
            f'  <div class="vm-timeline-time">{escape(ev.time_label)}</div>'
            f'  <div class="vm-timeline-title">{escape(ev.title)}</div>'
            f'  {detail_html}'
            f'</div>'
        )

    title = escape(model.title)
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{SVG_ICON_TIMELINE} {title}</div>
  <div class="vm-timeline-canvas">
    <div class="vm-timeline-track">
      {''.join(cards)}
    </div>
  </div>
</div>
"""


__all__ = ["render_timeline"]
