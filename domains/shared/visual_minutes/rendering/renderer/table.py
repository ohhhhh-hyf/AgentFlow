"""通用表格渲染器。"""
from __future__ import annotations

from ...models.ir import TableVisual
from .base import escape


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
    return f"""
<div class="vm-visual">
  <div class="vm-visual-title">{escape(model.title)}</div>
  <div class="vm-table-wrap">
    <table class="vm-table">
      <thead><tr>{head}</tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
  </div>
</div>
"""


__all__ = ["render_table"]
