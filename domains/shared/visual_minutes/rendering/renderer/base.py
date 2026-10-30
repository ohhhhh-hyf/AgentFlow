"""Visual Minutes 设计系统与通用样式。"""
from __future__ import annotations

import html
from typing import Any

TASTE_CSS = """
:root {
  --vm-ink-title: #09090B;
  --vm-ink-body: #27272A;
  --vm-ink-muted: #52525B;
  --vm-ink-subtle: #71717A;
  --vm-ink-faint: #A1A1AA;
  --vm-tone-card: #FFFFFF;
  --vm-tone-stone: #F4F4F5;
  --vm-tone-stone-light: #F8F8F9;
  --vm-accent-blue: #1D4ED8;
  --vm-accent-blue-bg: rgba(29, 78, 216, 0.06);
  --vm-accent-emerald: #047857;
  --vm-accent-emerald-bg: rgba(4, 120, 87, 0.06);
  --vm-accent-amber: #B45309;
  --vm-border: #E4E4E7;
  --vm-radius: 8px;
  --vm-radius-lg: 12px;
  --vm-font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  --vm-font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.vm-visual {
  font-family: var(--vm-font-sans);
  color: var(--vm-ink-body);
  margin: 28px 0;
  width: 100%;
  box-sizing: border-box;
}
.vm-visual * { box-sizing: border-box; }
.vm-visual-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin: 0 0 16px 0;
  line-height: 1.4;
}
.vm-master-card {
  background: var(--vm-tone-card);
  border: 1px solid var(--vm-border);
  border-radius: var(--vm-radius-lg);
  padding: 30px 34px;
  box-shadow: 0 2px 10px rgba(0,0,0,.025);
}
.vm-master-headline {
  font-size: clamp(1.35rem, 2.2vw, 1.85rem);
  font-weight: 700;
  color: var(--vm-ink-title);
  letter-spacing: -.025em;
  line-height: 1.25;
  margin: 0 0 12px;
}
.vm-master-thesis {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--vm-ink-body);
  background: var(--vm-tone-stone);
  border-left: 3px solid var(--vm-accent-blue);
  border-radius: 0 var(--vm-radius) var(--vm-radius) 0;
  padding: 12px 16px;
  margin: 0 0 24px;
}
.vm-master-grid {
  display: grid;
  gap: 14px;
  margin-bottom: 22px;
}
.vm-master-grid.vm-cols-2 { grid-template-columns: repeat(2, 1fr); }
.vm-master-grid.vm-cols-3 { grid-template-columns: repeat(3, 1fr); }
.vm-master-grid.vm-cols-4 { grid-template-columns: repeat(4, 1fr); }
.vm-master-grid.vm-cols-5 { grid-template-columns: repeat(5, 1fr); }
.vm-master-grid.vm-flow { display: flex; flex-wrap: wrap; align-items: stretch; }
.vm-master-grid.vm-flow .vm-master-block { flex: 1 1 200px; }
.vm-master-block {
  display: block;
  text-decoration: none;
  background: var(--vm-tone-stone-light);
  border-radius: var(--vm-radius);
  padding: 16px 18px;
  border: 1px solid transparent;
  transition: background .15s ease, border-color .15s ease;
}
.vm-master-block:hover { background: var(--vm-tone-stone); border-color: var(--vm-border); }
.vm-master-block-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
  margin-bottom: 7px;
}
.vm-master-block-summary {
  font-size: 12.5px;
  color: var(--vm-ink-muted);
  line-height: 1.55;
  margin-bottom: 8px;
}
.vm-master-points {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--vm-ink-subtle);
  line-height: 1.55;
}
.vm-master-points li { position: relative; padding-left: 13px; margin-top: 4px; }
.vm-master-points li::before { content: "—"; position: absolute; left: 0; color: var(--vm-ink-faint); }
.vm-master-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  border-top: 1px solid var(--vm-border);
  padding-top: 18px;
}
.vm-master-metric { min-width: 140px; flex: 1; }
.vm-master-metric-value { display: block; font-size: 20px; font-weight: 700; color: var(--vm-ink-title); font-variant-numeric: tabular-nums; }
.vm-master-metric-label { display: block; font-size: 12px; color: var(--vm-ink-subtle); margin-top: 3px; }
.vm-timeline { display: flex; align-items: stretch; gap: 8px; position: relative; padding: 18px 2px 2px; overflow-x: auto; }
.vm-timeline::before { content: ""; position: absolute; left: 7px; right: 7px; top: 8px; height: 1px; background: var(--vm-border); }
.vm-timeline-item { position: relative; flex: 1 0 170px; min-width: 170px; padding: 22px 14px 4px 0; }
.vm-timeline-item::before {
  content: ""; position: absolute; left: 0; top: 3px; width: 10px; height: 10px;
  border-radius: 50%; background: var(--vm-accent-blue); border: 2px solid var(--vm-tone-card);
  box-shadow: 0 0 0 1px var(--vm-accent-blue);
}
.vm-timeline-time { font-size: 12px; font-weight: 700; color: var(--vm-accent-blue); margin-bottom: 6px; }
.vm-timeline-title { font-size: 14.5px; font-weight: 700; color: var(--vm-ink-title); line-height: 1.4; }
.vm-timeline-detail { font-size: 12.5px; color: var(--vm-ink-muted); line-height: 1.6; margin-top: 5px; }
.vm-table-wrap { overflow-x: auto; border: 1px solid var(--vm-border); border-radius: var(--vm-radius-lg); background: var(--vm-tone-card); }
.vm-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 560px; }
.vm-table th, .vm-table td { padding: 11px 14px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--vm-border); line-height: 1.55; }
.vm-table th { background: var(--vm-tone-stone); color: var(--vm-ink-title); font-weight: 700; white-space: nowrap; }
.vm-table tr:last-child td { border-bottom: 0; }
.vm-table td:first-child { font-weight: 600; color: var(--vm-ink-title); background: var(--vm-tone-stone-light); }
.vm-flow { display: flex; flex-wrap: wrap; gap: 10px; align-items: stretch; }
.vm-flow-node { flex: 1 1 140px; min-width: 0; background: var(--vm-tone-stone-light); border-radius: var(--vm-radius); padding: 15px 16px; border: 1px solid var(--vm-border); }
.vm-flow-node-title { font-size: 14px; font-weight: 700; color: var(--vm-ink-title); margin-bottom: 5px; }
.vm-flow-node-detail { font-size: 12.5px; color: var(--vm-ink-muted); line-height: 1.55; }
.vm-flow-arrow-wrap { align-self: center; display: flex; flex-direction: column; align-items: center; gap: 2px; color: var(--vm-ink-faint); }
.vm-flow-arrow-label { font-size: 10.5px; color: var(--vm-ink-subtle); line-height: 1.3; text-align: center; max-width: 84px; }
.vm-flow-edges { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--vm-border); display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--vm-ink-subtle); line-height: 1.5; }
.vm-flow-edge { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
.vm-flow-edge-arrow { color: var(--vm-ink-faint); }
.vm-flow-edge-label { color: var(--vm-ink-faint); font-size: 11.5px; }
.vm-tree, .vm-tree ul { list-style: none; margin: 0; padding-left: 20px; }
.vm-tree { padding-left: 0; }
.vm-tree li { position: relative; padding: 5px 0 5px 16px; border-left: 1px solid var(--vm-border); }
.vm-tree > li { border-left: 0; padding-left: 0; }
.vm-tree li::before { content: ""; position: absolute; left: 0; top: 17px; width: 10px; height: 1px; background: var(--vm-border); }
.vm-tree > li::before { display: none; }
.vm-tree-title { font-size: 13.5px; font-weight: 700; color: var(--vm-ink-title); }
.vm-tree-detail { font-size: 12.5px; color: var(--vm-ink-muted); line-height: 1.55; margin-top: 3px; }
.vm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }
.vm-stat { background: var(--vm-tone-stone-light); border-radius: var(--vm-radius); padding: 18px; }
.vm-stat-value { font-size: 24px; font-weight: 700; color: var(--vm-ink-title); font-variant-numeric: tabular-nums; }
.vm-stat-label { font-size: 12.5px; color: var(--vm-ink-muted); margin-top: 5px; line-height: 1.5; }
@media (max-width: 900px) {
  .vm-master-grid.vm-cols-3, .vm-master-grid.vm-cols-4, .vm-master-grid.vm-cols-5 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
  .vm-master-card { padding: 22px 18px; }
  .vm-master-grid.vm-cols-2, .vm-master-grid.vm-cols-3, .vm-master-grid.vm-cols-4, .vm-master-grid.vm-cols-5 { grid-template-columns: 1fr; }
  .vm-master-grid.vm-flow { display: grid; }
  .vm-timeline-item { flex: 1 0 110px; min-width: 110px; }
  .vm-flow { flex-direction: column; }
  .vm-flow-node { flex: none; width: 100%; }
  .vm-flow-arrow-wrap { flex-direction: row; align-self: flex-start; padding-left: 12px; }
  .vm-flow-arrow-wrap svg { transform: rotate(90deg); }
}
"""


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


__all__ = ["TASTE_CSS", "escape"]
