"""结构化对比与映射表格渲染器（Table & Comparison Matrix Renderer - 新拟物软质触感版）。"""
from __future__ import annotations

from ...models.ir import TableVisual
from .base import NEU_5_COLORS, SVG_ICON_TABLE, escape, render_figure_caption


def render_table(model: TableVisual, in_master: bool = False) -> str:
    cols = model.data.columns
    rows = model.data.rows
    if not cols or not rows:
        return ""

    # 列头渲染：首列维度 + 后续对比列带专属微光呼吸圆点
    th_items = []
    for idx, c in enumerate(cols):
        if idx == 0:
            th_items.append(f'<th class="vm-th-dim">{escape(c)}</th>')
        else:
            color, _, _ = NEU_5_COLORS[(idx - 1) % len(NEU_5_COLORS)]
            th_items.append(
                f'<th class="vm-th-col">'
                f'  <div class="vm-th-wrap">'
                f'    <span class="vm-th-dot" style="background: {color}; box-shadow: 0 0 6px {color};"></span>'
                f'    <span>{escape(c)}</span>'
                f'  </div>'
                f'</th>'
            )

    head = "".join(th_items)

    body = []
    for row in rows:
        cell_items = []
        for idx, c in enumerate(row.cells):
            if idx == 0:
                cell_items.append(
                    f'<td class="vm-td-dim">'
                    f'  <span class="vm-dim-badge">{escape(c)}</span>'
                    f'</td>'
                )
            else:
                cell_items.append(f'<td class="vm-td-val">{escape(c)}</td>')
        body.append(f'<tr class="vm-table-row">{"".join(cell_items)}</tr>')

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
