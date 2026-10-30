"""时间轴渲染器。"""
from __future__ import annotations

from ...models.ir import TimelineVisual
from .base import escape


def render_timeline(model: TimelineVisual) -> str:
    if not model.data.events:
        return ""
    items = "".join(
        f'<div class="vm-timeline-item">'
        f'<div class="vm-timeline-time">{escape(e.time_label)}</div>'
        f'<div class="vm-timeline-title">{escape(e.title)}</div>'
        + (f'<div class="vm-timeline-detail">{escape(e.detail)}</div>' if e.detail else "")
        + "</div>"
        for e in model.data.events
    )
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{escape(model.title)}</div>
  <div class="vm-timeline">{items}</div>
</div>
"""


__all__ = ["render_timeline"]
