"""开篇通览图渲染器。"""
from __future__ import annotations

from ...models.ir import MasterVisual
from .base import escape


def render_master(model: MasterVisual) -> str:
    if not model.blocks:
        return ""
    count = min(max(len(model.blocks), 1), 5)
    if model.layout in {"flow", "timeline"}:
        grid_class = "vm-flow"
    else:
        grid_class = f"vm-cols-{count}"
    blocks = []
    for block in model.blocks:
        sid = block.section_ids[0] if block.section_ids else ""
        href = f' href="#{escape(sid)}"' if sid else ""
        points = "".join(f"<li>{escape(p)}</li>" for p in block.key_points)
        blocks.append(
            f'<a class="vm-master-block"{href}>'
            f'<div class="vm-master-block-title">{escape(block.title)}</div>'
            f'<div class="vm-master-block-summary">{escape(block.summary)}</div>'
            + (f'<ul class="vm-master-points">{points}</ul>' if points else "")
            + "</a>"
        )
    metrics = ""
    if model.metrics:
        items = "".join(
            f'<div class="vm-master-metric"><span class="vm-master-metric-value">{escape(m.value)}</span>'
            f'<span class="vm-master-metric-label">{escape(m.label)}</span></div>'
            for m in model.metrics
        )
        metrics = f'<div class="vm-master-metrics">{items}</div>'
    return f"""
<div class="vm-visual vm-master">
  <div class="vm-master-card">
    <h1 class="vm-master-headline">{escape(model.headline)}</h1>
    <div class="vm-master-thesis">{escape(model.thesis)}</div>
    <div class="vm-master-grid {grid_class}">
      {''.join(blocks)}
    </div>
    {metrics}
  </div>
</div>
"""


__all__ = ["render_master"]
