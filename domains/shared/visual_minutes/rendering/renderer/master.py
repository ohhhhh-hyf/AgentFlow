"""开篇全景通览大图渲染器（Master Infographic Renderer）- 飞书高级商务版。"""
from __future__ import annotations

from ...models.ir import MasterVisual
from .base import escape

THEMES = ["blue", "cyan", "purple", "emerald", "amber"]


def render_master(model: MasterVisual) -> str:
    if not model.blocks:
        return ""

    num_blocks = len(model.blocks)
    count = min(max(num_blocks, 1), 5)

    if model.layout in {"flow", "timeline"}:
        grid_class = "vm-flow"
        tag_prefix = "阶段"
    else:
        grid_class = f"vm-cols-{count}"
        tag_prefix = "议题"

    blocks = []
    for idx, block in enumerate(model.blocks, start=1):
        theme = THEMES[(idx - 1) % len(THEMES)]
        tag_text = f"{tag_prefix} {idx:02d}"

        points = "".join(f"<li>{escape(p)}</li>" for p in block.key_points if p.strip())
        points_html = f'<ul class="vm-master-points">{points}</ul>' if points else ""

        # 卡片内嵌高光成果盒（Co-located Highlight）
        if block.highlight and (block.highlight.value or block.highlight.tag):
            htag = escape(block.highlight.tag or "核心抓手")
            hval = escape(block.highlight.value)
        else:
            htag = "核心定调"
            hval = escape(block.summary[:24] if block.summary else block.title)

        highlight_html = (
            f'<div class="vm-master-block-highlight">'
            f'  <div class="vm-highlight-tag-wrap">'
            f'    <span class="vm-highlight-dot"></span>'
            f'    <span class="vm-highlight-tag">{htag}</span>'
            f'  </div>'
            f'  <div class="vm-highlight-value">{hval}</div>'
            f'</div>'
        )

        blocks.append(
            f'<div class="vm-master-block vm-theme-{theme}">'
            f'  <div class="vm-block-header">'
            f'    <span class="vm-block-tag">{tag_text}</span>'
            f'    <div class="vm-master-block-title">{escape(block.title)}</div>'
            f'  </div>'
            f'  <div class="vm-master-block-summary">{escape(block.summary)}</div>'
            f'  {points_html}'
            f'  {highlight_html}'
            f'</div>'
        )

    headline = escape(model.headline)
    thesis = escape(model.thesis)

    return f"""
<div class="vm-visual vm-master">
  <div class="vm-master-card">
    <div class="vm-master-badge">
      <svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
      </svg>
      <span>会议全景架构与核心共识</span>
    </div>
    <h1 class="vm-master-headline">{headline}</h1>
    <div class="vm-master-thesis">
      <span class="vm-thesis-quote-bar"></span>
      <div class="vm-thesis-content">{thesis}</div>
    </div>
    <div class="vm-master-grid {grid_class}">
      {''.join(blocks)}
    </div>
  </div>
</div>
"""


__all__ = ["render_master"]
