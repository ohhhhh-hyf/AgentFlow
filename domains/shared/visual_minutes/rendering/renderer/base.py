"""Visual Minutes 商业级设计系统与通用样式（飞书文档质感与色彩系统）。"""
from __future__ import annotations

import html
from typing import Any

# 原生内联矢量 SVG 图标（零 Emoji，纯净企业级内联矢量）
SVG_ICON_MASTER = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>'
SVG_ICON_FLOW = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>'
SVG_ICON_TABLE = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="3" y1="15" x2="21" y2="15"></line><line x1="9" y1="3" x2="9" y2="21"></line><line x1="15" y1="3" x2="15" y2="21"></line></svg>'
SVG_ICON_TREE = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>'
SVG_ICON_STATS = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>'
SVG_ICON_TIMELINE = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon></svg>'
SVG_ICON_LOOP = '<svg class="vm-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>'


TASTE_CSS = """
:root {
  /* 飞书商务色彩系统 */
  --vm-accent-blue: #3370FF;
  --vm-accent-blue-bg: #F0F4FE;
  --vm-accent-blue-border: #BED5FE;

  --vm-accent-cyan: #00B5B5;
  --vm-accent-cyan-bg: #E8FFFB;
  --vm-accent-cyan-border: #87E8DE;

  --vm-accent-purple: #722ED1;
  --vm-accent-purple-bg: #F9F0FF;
  --vm-accent-purple-border: #D3ADF7;

  --vm-accent-emerald: #00B42A;
  --vm-accent-emerald-bg: #E8FFEA;
  --vm-accent-emerald-border: #AFF0B5;

  --vm-accent-amber: #FF7D00;
  --vm-accent-amber-bg: #FFF7E8;
  --vm-accent-amber-border: #FFD591;

  /* 文字墨水规范（保持全局字体大小稳定） */
  --vm-ink-title: #1D2129;
  --vm-ink-body: #4E5969;
  --vm-ink-muted: #646A73;
  --vm-ink-subtle: #86909C;
  --vm-ink-faint: #C9CDD4;

  /* 底色阶与边框 */
  --vm-tone-canvas: #FAFAFA;
  --vm-tone-card: #FFFFFF;
  --vm-tone-stone: #F2F3F5;
  --vm-tone-stone-light: #F7F8FA;
  --vm-border: #E5E6EB;

  /* 基础尺寸 */
  --vm-radius: 8px;
  --vm-radius-lg: 12px;
  --vm-font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  --vm-font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.vm-svg-icon {
  width: 16px;
  height: 16px;
  display: inline-block;
  vertical-align: -2.5px;
  margin-right: 6px;
  flex-shrink: 0;
}

.vm-visual {
  font-family: var(--vm-font-sans);
  color: var(--vm-ink-body);
  margin: 30px 0;
  width: 100%;
  box-sizing: border-box;
}

.vm-visual * {
  box-sizing: border-box;
}

.vm-visual-title {
  display: flex;
  align-items: center;
  font-size: 15px;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin: 0 0 14px 0;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

/* ─────────────────────────────────────────────────────────────
   1. 【开篇统领】Master Infographic (全景通览大图 - 飞书旗舰商务版)
   ───────────────────────────────────────────────────────────── */
.vm-master-card {
  background: linear-gradient(180deg, #F4F7FE 0%, #FFFFFF 160px, #FFFFFF 100%);
  border: 1px solid var(--vm-border);
  border-radius: 14px;
  padding: 30px 34px;
  box-shadow: 0 4px 20px -2px rgba(17, 31, 44, 0.05);
  position: relative;
  overflow: hidden;
}

.vm-master-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--vm-accent-blue);
  background: rgba(51, 112, 255, 0.08);
  border: 1px solid rgba(51, 112, 255, 0.15);
  padding: 3px 10px;
  border-radius: 100px;
  margin-bottom: 12px;
  letter-spacing: 0.03em;
}

.vm-master-headline {
  font-size: 22px;
  font-weight: 700;
  color: var(--vm-ink-title);
  letter-spacing: -0.02em;
  line-height: 1.35;
  margin: 0 0 12px 0;
}

.vm-master-thesis {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--vm-ink-body);
  background: #FFFFFF;
  border: 1px solid var(--vm-border);
  border-left: 3.5px solid var(--vm-accent-blue);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 0 0 24px 0;
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.vm-master-widgets-container {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.vm-master-widget {
  width: 100%;
}

.vm-widget-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin-bottom: 12px;
}

.vm-master-card .vm-visual {
  margin: 0;
}

.vm-master-grid {
  display: grid;
  gap: 16px;
  align-items: stretch;
}

.vm-master-grid.vm-cols-1 { grid-template-columns: 1fr; }
.vm-master-grid.vm-cols-2 { grid-template-columns: repeat(2, 1fr); }
.vm-master-grid.vm-cols-3 { grid-template-columns: repeat(3, 1fr); }
.vm-master-grid.vm-cols-4 { grid-template-columns: repeat(4, 1fr); }
.vm-master-grid.vm-cols-5 { grid-template-columns: repeat(5, 1fr); }
.vm-master-grid.vm-flow { display: flex; flex-wrap: wrap; align-items: stretch; }

.vm-master-block {
  display: flex;
  flex-direction: column;
  background: #FFFFFF;
  border-radius: var(--vm-radius);
  padding: 20px 20px 16px 20px;
  border: 1px solid var(--vm-border);
  border-top: 3.5px solid var(--block-accent, var(--vm-accent-blue));
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.vm-master-block:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
}

/* 飞书主题分色体系 */
.vm-theme-blue {
  --block-accent: var(--vm-accent-blue);
  --block-accent-bg: var(--vm-accent-blue-bg);
  --block-accent-border: var(--vm-accent-blue-border);
}

.vm-theme-cyan {
  --block-accent: var(--vm-accent-cyan);
  --block-accent-bg: var(--vm-accent-cyan-bg);
  --block-accent-border: var(--vm-accent-cyan-border);
}

.vm-theme-purple {
  --block-accent: var(--vm-accent-purple);
  --block-accent-bg: var(--vm-accent-purple-bg);
  --block-accent-border: var(--vm-accent-purple-border);
}

.vm-theme-emerald {
  --block-accent: var(--vm-accent-emerald);
  --block-accent-bg: var(--vm-accent-emerald-bg);
  --block-accent-border: var(--vm-accent-emerald-border);
}

.vm-theme-amber {
  --block-accent: var(--vm-accent-amber);
  --block-accent-bg: var(--vm-accent-amber-bg);
  --block-accent-border: var(--vm-accent-amber-border);
}

.vm-block-header {
  margin-bottom: 8px;
}

.vm-block-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  color: var(--block-accent, var(--vm-accent-blue));
  background: var(--block-accent-bg, var(--vm-accent-blue-bg));
  border: 1px solid var(--block-accent-border, var(--vm-accent-blue-border));
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.vm-master-block-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
  margin-bottom: 6px;
}

.vm-master-block-summary {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--vm-ink-body);
  line-height: 1.55;
  margin-bottom: 12px;
}

.vm-master-points {
  margin: 0 0 16px 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--vm-ink-muted);
  line-height: 1.55;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.vm-master-points li {
  position: relative;
  padding-left: 14px;
}

.vm-master-points li::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 7px;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: var(--block-accent, var(--vm-accent-blue));
}

/* 嵌入式专属高光底盒 */
.vm-master-block-highlight {
  margin-top: auto;
  background: var(--block-accent-bg, var(--vm-accent-blue-bg));
  border: 1px solid var(--block-accent-border, var(--vm-accent-blue-border));
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.vm-highlight-tag-wrap {
  display: flex;
  align-items: center;
  gap: 5px;
}

.vm-highlight-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: var(--block-accent, var(--vm-accent-blue));
}

.vm-highlight-tag {
  font-size: 11px;
  font-weight: 700;
  color: var(--block-accent, var(--vm-accent-blue));
  letter-spacing: 0.03em;
}

.vm-highlight-value {
  font-size: 13px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
  word-break: break-word;
}

.vm-master-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  border-top: 1px solid var(--vm-border);
  padding-top: 20px;
}

.vm-master-metric {
  flex: 1 1 180px;
  background: var(--vm-tone-stone-light);
  border-radius: var(--vm-radius);
  padding: 12px 16px;
  border: 1px solid var(--vm-border);
  border-left: 3px solid var(--vm-accent-blue);
}

.vm-master-metric-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: var(--vm-ink-title);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.vm-master-metric-label {
  display: block;
  font-size: 12px;
  color: var(--vm-ink-subtle);
  margin-top: 3px;
  font-weight: 500;
}

/* ─────────────────────────────────────────────────────────────
   2. 【链路闭环】Flow & Closed Loop 渲染 (飞书旗舰流转版)
   ───────────────────────────────────────────────────────────── */
.vm-flow-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.vm-flow-track {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  align-items: stretch;
}

.vm-flow-step-card {
  display: flex;
  flex-direction: column;
  background: var(--vm-tone-card);
  border-radius: var(--vm-radius);
  padding: 16px 18px 14px 18px;
  border: 1px solid var(--vm-border);
  border-top: 3px solid var(--vm-accent-blue);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.vm-flow-step-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(51, 112, 255, 0.08);
}

.vm-step-card-header {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 8px;
}

.vm-flow-node-step {
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  color: var(--vm-accent-blue);
  background: var(--vm-accent-blue-bg);
  border: 1px solid var(--vm-accent-blue-border);
  padding: 1px 6px;
  border-radius: 4px;
  letter-spacing: 0.05em;
}

.vm-flow-node-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
}

.vm-flow-node-detail {
  font-size: 12.5px;
  color: var(--vm-ink-muted);
  line-height: 1.6;
  flex: 1;
}

.vm-flow-delivery {
  margin-top: 12px;
  padding: 6px 10px;
  background: #F7F8FA;
  border: 1px solid var(--vm-border);
  border-radius: 5px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--vm-ink-body);
}

.vm-delivery-arrow {
  color: var(--vm-accent-blue);
  flex-shrink: 0;
}

.vm-delivery-text {
  font-weight: 600;
  line-height: 1.35;
}

/* ─────────────────────────────────────────────────────────────
   3. 【对比矩阵】Table / Matrix 对比表 (飞书结构化表格)
   ───────────────────────────────────────────────────────────── */
.vm-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--vm-border);
  border-radius: 10px;
  background: var(--vm-tone-card);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}

.vm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 580px;
}

.vm-table th, .vm-table td {
  padding: 12px 16px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--vm-border);
  line-height: 1.6;
}

.vm-table th {
  background: #F7F8FA;
  color: var(--vm-ink-title);
  font-weight: 700;
  font-size: 13px;
  border-bottom: 2px solid var(--vm-border);
}

.vm-table td:first-child {
  font-weight: 700;
  color: var(--vm-ink-title);
  background: #FAFBFC;
  width: 22%;
  min-width: 130px;
}

.vm-table tr:last-child td {
  border-bottom: 0;
}

.vm-table tr:hover td {
  background-color: #F0F4FE;
}

/* ─────────────────────────────────────────────────────────────
   4. 【分层架构】Tree / Layered Architecture (飞书旗舰分层卡)
   ───────────────────────────────────────────────────────────── */
.vm-tree-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: #FFFFFF;
  border: 1px solid var(--vm-border);
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
}

.vm-tree-layer-card {
  background: #FAFBFC;
  border: 1px solid var(--vm-border);
  border-left: 4px solid var(--vm-accent-blue);
  border-radius: 6px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.vm-tree-layer-card:hover {
  background: #FFFFFF;
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.05);
}

.vm-tree-layer-badge {
  flex-shrink: 0;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  font-family: var(--vm-font-mono);
  letter-spacing: 0.02em;
}

.vm-tree-layer-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--vm-ink-title);
  min-width: 120px;
  flex-shrink: 0;
}

.vm-tree-layer-divider {
  width: 1px;
  height: 18px;
  background: var(--vm-border);
  flex-shrink: 0;
}

.vm-tree-layer-detail {
  font-size: 13px;
  color: var(--vm-ink-body);
  line-height: 1.6;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   5. 【量化成效】Stats 关键指标大卡
   ───────────────────────────────────────────────────────────── */
.vm-stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
}

.vm-stat-card {
  background: #FFFFFF;
  border: 1px solid var(--vm-border);
  border-top: 3.5px solid var(--vm-accent-blue);
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.vm-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
}

.vm-stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--vm-accent-blue);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.vm-stat-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--vm-ink-title);
  margin-top: 6px;
}

.vm-stat-evidence {
  font-size: 11.5px;
  color: var(--vm-ink-muted);
  margin-top: 6px;
  line-height: 1.5;
  background: #F7F8FA;
  padding: 4px 8px;
  border-radius: 4px;
}

/* ─────────────────────────────────────────────────────────────
   6. 【时序图谱】Timeline 时间演进
   ───────────────────────────────────────────────────────────── */
.vm-timeline-canvas {
  background: var(--vm-tone-stone-light);
  border: 1px solid var(--vm-border);
  border-radius: var(--vm-radius-lg);
  padding: 22px 24px;
}

.vm-timeline-track {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
}

.vm-timeline-item {
  background: #FFFFFF;
  border: 1px solid var(--vm-border);
  border-radius: var(--vm-radius);
  padding: 14px 16px;
}

.vm-timeline-time {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--vm-accent-blue);
  margin-bottom: 5px;
}

.vm-timeline-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
}

.vm-timeline-detail {
  font-size: 12.5px;
  color: var(--vm-ink-muted);
  line-height: 1.55;
  margin-top: 5px;
}

/* 响应式断点 */
@media (max-width: 900px) {
  .vm-master-grid.vm-cols-3,
  .vm-master-grid.vm-cols-4,
  .vm-master-grid.vm-cols-5 {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .vm-master-card { padding: 20px 16px; }
  .vm-master-grid.vm-cols-2,
  .vm-master-grid.vm-cols-3,
  .vm-master-grid.vm-cols-4,
  .vm-master-grid.vm-cols-5 {
    grid-template-columns: 1fr;
  }
  .vm-tree-layer-card {
    flex-direction: column;
    gap: 4px;
  }
}
"""


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


__all__ = [
    "SVG_ICON_FLOW",
    "SVG_ICON_LOOP",
    "SVG_ICON_MASTER",
    "SVG_ICON_STATS",
    "SVG_ICON_TABLE",
    "SVG_ICON_TIMELINE",
    "SVG_ICON_TREE",
    "TASTE_CSS",
    "escape",
]
