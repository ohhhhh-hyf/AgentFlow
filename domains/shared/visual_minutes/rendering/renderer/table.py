"""结构化对比与映射表格渲染器（Table & Comparison Matrix Renderer）。"""
from __future__ import annotations

from ...models.ir import TableVisual
from .base import SVG_ICON_TABLE, escape


def render_table(model: TableVisual) -> str:
    cols = model.data.columns
    rows = model.data.rows
    if not cols or not rows:
        return ""

    head = "".join(f"<th>{escape(c)}</th>" for c in cols)
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(c)}</td>" for c in row.cells)
        body.append(f"<tr>{cells}</tr>")

    title = escape(model.title)
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{SVG_ICON_TABLE} {title}</div>
  <div class="vm-table-wrap">
    <table class="vm-table">
      <thead><tr>{head}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
  </div>
</div>
"""


__all__ = ["render_table"]
