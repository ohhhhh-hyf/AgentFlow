"""开篇全景简报看板渲染器（Master Infographic Renderer - 飞书旗舰商务复合版）。"""
from __future__ import annotations

from typing import List

from ...models.ir import CardsVisual, MasterVisual
from .base import escape
from .flow import render_flow
from .stats import render_stats
from .table import render_table
from .timeline import render_timeline
from .tree import render_tree

THEMES = ["blue", "cyan", "purple", "emerald", "amber"]


def _render_cards_widget(widget: CardsVisual) -> str:
    items = widget.data.items
    if not items:
        return ""
    count = min(max(len(items), 1), 5)
    cards = []
    for idx, item in enumerate(items, start=1):
        theme = THEMES[(idx - 1) % len(THEMES)]
        tag_text = item.tag or f"议题 {idx:02d}"
        points = "".join(f"<li>{escape(p)}</li>" for p in item.key_points if p.strip())
        points_html = f'<ul class="vm-master-points">{points}</ul>' if points else ""

        if item.highlight and (item.highlight.value or item.highlight.tag):
            htag = escape(item.highlight.tag or "核心抓手")
            hval = escape(item.highlight.value)
        else:
            htag = "核心定调"
            hval = escape(item.summary[:24] if item.summary else item.title)

        highlight_html = (
            f'<div class="vm-master-block-highlight">'
            f'  <div class="vm-highlight-tag-wrap">'
            f'    <span class="vm-highlight-dot"></span>'
            f'    <span class="vm-highlight-tag">{htag}</span>'
            f'  </div>'
            f'  <div class="vm-highlight-value">{hval}</div>'
            f'</div>'
        )

        cards.append(
            f'<div class="vm-master-block vm-theme-{theme}">'
            f'  <div class="vm-block-header">'
            f'    <span class="vm-block-tag">{escape(tag_text)}</span>'
            f'    <div class="vm-master-block-title">{escape(item.title)}</div>'
            f'  </div>'
            f'  <div class="vm-master-block-summary">{escape(item.summary)}</div>'
            f'  {points_html}'
            f'  {highlight_html}'
            f'</div>'
        )

    title_html = (
        f'<div class="vm-widget-title">{escape(widget.title)}</div>'
        if widget.title
        else ""
    )
    return f"""
<div class="vm-master-widget vm-widget-cards">
  {title_html}
  <div class="vm-master-grid vm-cols-{count}">
    {''.join(cards)}
  </div>
</div>
"""


def render_master(model: MasterVisual) -> str:
    # 1. 优先渲染自主多组件流（widgets）
    widgets_html: List[str] = []
    if model.widgets:
        for w in model.widgets:
            if w.kind == "cards":
                widgets_html.append(_render_cards_widget(w))
            elif w.kind == "stats":
                widgets_html.append(render_stats(w))
            elif w.kind == "timeline":
                widgets_html.append(render_timeline(w))
            elif w.kind == "table":
                widgets_html.append(render_table(w))
            elif w.kind == "flow":
                widgets_html.append(render_flow(w))
            elif w.kind == "tree":
                widgets_html.append(render_tree(w))

    # 2. 兼容兜底经典 blocks
    if not widgets_html and model.blocks:
        count = min(max(len(model.blocks), 1), 5)
        blocks = []
        for idx, block in enumerate(model.blocks, start=1):
            theme = THEMES[(idx - 1) % len(THEMES)]
            tag_text = f"议题 {idx:02d}"
            points = "".join(f"<li>{escape(p)}</li>" for p in block.key_points if p.strip())
            points_html = f'<ul class="vm-master-points">{points}</ul>' if points else ""

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
        widgets_html.append(f'<div class="vm-master-grid vm-cols-{count}">{"".join(blocks)}</div>')

    if not widgets_html:
        return ""

    headline = escape(model.headline)
    thesis = escape(model.thesis)

    return f"""
<div class="vm-visual vm-master">
  <div class="vm-master-card">
    <div class="vm-master-badge">
      <svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
      </svg>
      <span>会议全景架构与核心共识看板</span>
    </div>
    <h1 class="vm-master-headline">{headline}</h1>
    <div class="vm-master-thesis">
      <span class="vm-thesis-quote-bar"></span>
      <div class="vm-thesis-content">{thesis}</div>
    </div>
    <div class="vm-master-widgets-container">
      {''.join(widgets_html)}
    </div>
  </div>
</div>
"""


__all__ = ["render_master"]
