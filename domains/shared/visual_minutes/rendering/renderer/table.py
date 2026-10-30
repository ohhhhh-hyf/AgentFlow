"""结构化对比与映射表格渲染器（Table & Comparison Matrix Renderer）。"""
from __future__ import annotations

from ...models.ir import TableVisual
from .base import SVG_ICON_TABLE, escape, render_figure_caption


def render_table(model: TableVisual, in_master: bool = False) -> str:
    cols = model.data.columns
    rows = model.data.rows
    if not cols or not rows:
        return ""

    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(c)}</td>" for c in row.cells)
        body.append(f"<tr>{cells}</tr>")

    table_wrap_html = f"""
  <div class="vm-table-wrap">
    <table class="vm-table">
      <thead><tr>{head}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
  </div>
"""

    if in_master:
        title_html = (
            f'<div class="vm-widget-title">{escape(model.title)}</div>'
            if model.title
            else ""
        )
        return f"""
<div class="vm-master-widget vm-widget-table">
  {title_html}
{table_wrap_html}
</div>
"""

    caption_html = render_figure_caption(model.title)
    return f"""
<div class="vm-visual">
{table_wrap_html}
  {caption_html}
</div>
"""


__all__ = ["render_table"]
