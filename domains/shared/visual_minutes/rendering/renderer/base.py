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

# 新拟物 5 轮转色阶体系 (蓝、青、紫、绿、橙)
NEU_5_COLORS = [
    ("var(--vm-accent-blue)", "var(--vm-accent-blue-bg)", "var(--vm-accent-blue-border)"),
    ("var(--vm-accent-cyan)", "var(--vm-accent-cyan-bg)", "var(--vm-accent-cyan-border)"),
    ("var(--vm-accent-purple)", "var(--vm-accent-purple-bg)", "var(--vm-accent-purple-border)"),
    ("var(--vm-accent-emerald)", "var(--vm-accent-emerald-bg)", "var(--vm-accent-emerald-border)"),
    ("var(--vm-accent-amber)", "var(--vm-accent-amber-bg)", "var(--vm-accent-amber-border)"),
]

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

  /* ─────────────────────────────────────────────────────────────
     新拟物软质触感 UI 规范 (Neumorphism Tactile Tokens)
     专用于 Flow、Timeline、Tree 三类核心图表卡片
     ───────────────────────────────────────────────────────────── */
  --vm-neu-bg: #EEF2F7;
  --vm-neu-card: #F4F7FC;
  --vm-neu-dark-shadow: rgba(166, 180, 200, 0.40);
  --vm-neu-light-shadow: #FFFFFF;
  --vm-neu-card-border: rgba(255, 255, 255, 0.9);
  --vm-neu-tray-shadow: inset 3px 3px 8px var(--vm-neu-dark-shadow), inset -3px -3px 8px var(--vm-neu-light-shadow);
  --vm-neu-raised-shadow: 4px 4px 10px var(--vm-neu-dark-shadow), -4px -4px 10px var(--vm-neu-light-shadow);
  --vm-neu-raised-hover: 6px 6px 14px rgba(166, 180, 200, 0.52), -6px -6px 14px var(--vm-neu-light-shadow);
  --vm-neu-inset-shadow: inset 2px 2px 4px var(--vm-neu-dark-shadow), inset -2px -2px 4px var(--vm-neu-light-shadow);

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

/* 飞书出版物图注规范 (Figure Caption) */
.vm-figure-caption {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 14px;
  font-size: 12.5px;
  color: var(--vm-ink-subtle);
  letter-spacing: 0.02em;
  user-select: none;
}

.vm-caption-prefix {
  font-weight: 700;
  color: var(--vm-accent-blue);
  font-size: 11.5px;
}

.vm-caption-divider {
  color: var(--vm-ink-faint);
}

.vm-caption-title {
  font-weight: 600;
  color: var(--vm-ink-muted);
}

/* ─────────────────────────────────────────────────────────────
   1. 【开篇统领】Master Infographic (全景通览大图 - 无外框自然融入版)
   ───────────────────────────────────────────────────────────── */
.vm-master-card {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
  position: relative;
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
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 16px;
  scrollbar-width: thin;
  scrollbar-color: #C9CDD4 transparent;
}

.vm-master-block {
  flex: 1 1 240px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  background: var(--vm-neu-card);
  border-radius: 12px;
  padding: 18px 20px 16px 20px;
  border: 1px solid var(--vm-neu-card-border);
  box-shadow: var(--vm-neu-raised-shadow);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
  box-sizing: border-box;
  position: relative;
}

.vm-master-block:hover {
  transform: translateY(-2px);
  box-shadow: var(--vm-neu-raised-hover);
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

.vm-master-block-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vm-block-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 6px var(--block-accent, var(--vm-accent-blue));
  background-color: var(--block-accent, var(--vm-accent-blue));
  flex-shrink: 0;
}

.vm-master-block-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
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
  box-shadow: 0 0 4px var(--block-accent, var(--vm-accent-blue));
}

/* 嵌入式专属高光底盒 (Neumorphic Inset Pill) */
.vm-master-block-highlight {
  margin-top: auto;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-inset-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 8px;
  padding: 8px 12px;
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
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 16px;
}

.vm-flow-track {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 14px;
  align-items: stretch;
  padding: 6px 4px 12px 4px;
  scrollbar-width: thin;
  scrollbar-color: #C9CDD4 transparent;
}

.vm-flow-step-card {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  background: var(--vm-neu-card);
  border-radius: 12px;
  padding: 16px 18px 14px 18px;
  border: 1px solid var(--vm-neu-card-border);
  box-shadow: var(--vm-neu-raised-shadow);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
  box-sizing: border-box;
  position: relative;
}

.vm-flow-step-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--vm-neu-raised-hover);
}

.vm-step-card-header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.vm-flow-node-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.vm-flow-step-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 6px var(--step-accent, var(--vm-accent-blue));
  flex-shrink: 0;
}

.vm-flow-node-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
}

.vm-flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  color: #A0ABC0;
  user-select: none;
}

.vm-connector-arrow {
  opacity: 0.8;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.vm-flow-track:hover .vm-connector-arrow {
  opacity: 1;
}

.vm-flow-node-detail {
  font-size: 12.5px;
  color: var(--vm-ink-body);
  line-height: 1.6;
  flex: 1;
}

.vm-flow-delivery {
  margin-top: 10px;
  padding: 6px 10px;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-inset-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--vm-ink-body);
}

.vm-delivery-arrow {
  color: var(--step-accent, var(--vm-accent-blue));
  flex-shrink: 0;
}

.vm-delivery-text {
  font-weight: 600;
  line-height: 1.35;
}

/* ─────────────────────────────────────────────────────────────
   3. 【对比矩阵】Table / Matrix 对比表 (新拟物软质触感版)
   ───────────────────────────────────────────────────────────── */
.vm-table-wrap {
  overflow-x: auto;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 14px 16px;
  scrollbar-width: thin;
  scrollbar-color: #C9CDD4 transparent;
}

.vm-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  font-size: 13px;
  min-width: 580px;
}

.vm-table th {
  padding: 8px 14px 6px 14px;
  text-align: left;
  font-weight: 700;
  color: var(--vm-ink-title);
  font-size: 13px;
  border: none;
}

.vm-th-dim {
  width: 17%;
  min-width: 100px;
  color: var(--vm-ink-muted);
}

.vm-th-col {
  /* 释放充足横向排布宽度，避免多字数挤压折行 */
  width: auto;
}

.vm-th-wrap {
  display: flex;
  align-items: center;
  gap: 7px;
}

.vm-th-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.vm-table-row {
  filter: drop-shadow(0 2px 5px rgba(166, 180, 200, 0.35));
  transition: filter 0.2s ease, transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.vm-table-row:hover {
  filter: drop-shadow(0 4px 10px rgba(166, 180, 200, 0.48));
}

.vm-table td {
  padding: 12px 16px;
  text-align: left;
  vertical-align: middle;
  background: var(--vm-neu-card);
  border-top: 1px solid var(--vm-neu-card-border);
  border-bottom: 1px solid var(--vm-neu-card-border);
  color: var(--vm-ink-body);
  line-height: 1.55;
}

.vm-td-dim {
  width: 17%;
  min-width: 100px;
  border-left: 1px solid var(--vm-neu-card-border);
  border-top-left-radius: 10px;
  border-bottom-left-radius: 10px;
}

.vm-dim-badge {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-inset-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  padding: 3px 8px;
  border-radius: 6px;
  letter-spacing: 0.02em;
}

.vm-td-val {
  font-size: 13px;
}

.vm-table tr td:last-child {
  border-right: 1px solid var(--vm-neu-card-border);
  border-top-right-radius: 10px;
  border-bottom-right-radius: 10px;
}

/* ─────────────────────────────────────────────────────────────
   4. 【分层架构】Tree / Layered Architecture (飞书旗舰分层卡)
   ───────────────────────────────────────────────────────────── */
.vm-tree-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 18px 20px;
}

.vm-tree-layer-card {
  background: var(--vm-neu-card);
  border: 1px solid var(--vm-neu-card-border);
  border-radius: 10px;
  padding: 13px 18px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--vm-neu-raised-shadow);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
  box-sizing: border-box;
}

.vm-tree-layer-card:hover {
  transform: translateY(-1.5px);
  box-shadow: var(--vm-neu-raised-hover);
}

.vm-tree-layer-lead {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-shrink: 0;
  min-width: 120px;
}

.vm-tree-layer-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 6px var(--layer-accent, var(--vm-accent-blue));
  flex-shrink: 0;
}

.vm-tree-layer-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-tree-layer-divider {
  width: 2px;
  height: 20px;
  background: #DCE3EC;
  border-right: 1px solid #FFFFFF;
  flex-shrink: 0;
}

.vm-tree-layer-detail {
  font-size: 13px;
  color: var(--vm-ink-body);
  line-height: 1.6;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   5. 【量化成效】Stats 关键指标大卡 (新拟物软质触感版)
   ───────────────────────────────────────────────────────────── */
.vm-stats-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 14px;
  align-items: stretch;
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 16px;
  scrollbar-width: thin;
  scrollbar-color: #C9CDD4 transparent;
}

.vm-stat-card {
  flex: 1 1 200px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  background: var(--vm-neu-card);
  border: 1px solid var(--vm-neu-card-border);
  border-radius: 12px;
  padding: 16px 18px;
  box-shadow: var(--vm-neu-raised-shadow);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
  box-sizing: border-box;
}

.vm-stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--vm-neu-raised-hover);
}

.vm-stat-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.vm-stat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 6px var(--stat-accent, var(--vm-accent-blue));
  flex-shrink: 0;
}

.vm-stat-value {
  font-size: 15.5px;
  font-weight: 700;
  color: var(--stat-accent, var(--vm-accent-blue));
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.35;
}

.vm-stat-label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--vm-ink-body);
  line-height: 1.55;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   6. 【时序图谱】Timeline 时间演进（轴线贯穿 + 顶置时间 + 纯净内容卡）
   ───────────────────────────────────────────────────────────── */
.vm-timeline-canvas {
  background: var(--vm-neu-bg);
  box-shadow: var(--vm-neu-tray-shadow);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 14px;
  padding: 22px 18px 18px 18px;
}

.vm-timeline-track {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  padding: 6px 12px 12px 12px;
  scrollbar-width: thin;
  scrollbar-color: #C9CDD4 transparent;
}

/* 纵向列容器：时间、轴线圆点、卡片纵向严格中心对齐 */
.vm-timeline-col {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  box-sizing: border-box;
}

/* 1. 顶层：时间刻度（纯净文本，无【】括号） */
.vm-timeline-time-label {
  font-size: 13.5px;
  font-weight: 700;
  font-family: var(--vm-font-mono), var(--vm-font-sans);
  color: var(--event-accent, var(--vm-ink-title));
  text-align: center;
  margin-bottom: 8px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  line-height: 1.4;
  user-select: none;
  transition: transform 0.2s ease;
}

.vm-timeline-col:hover .vm-timeline-time-label {
  transform: translateY(-1px);
}

/* 2. 中层：贯通轴线与圆点锚点 */
.vm-timeline-node {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  margin-bottom: 14px;
}

/* 贯穿水平直线（向左右各延展 8px 完美弥合列间 gap: 16px） */
.vm-timeline-node::before {
  content: "";
  position: absolute;
  top: 50%;
  left: -8px;
  right: -8px;
  height: 2px;
  background: #CBD5E1;
  transform: translateY(-50%);
  z-index: 1;
}

/* 首末节点向外侧适度延展，形成自然贯通视感 */
.vm-timeline-col:first-child .vm-timeline-node::before {
  left: -14px;
}
.vm-timeline-col:last-child .vm-timeline-node::before {
  right: -14px;
}

/* 轴线上的高亮圆点（立体微光） */
.vm-timeline-dot {
  position: relative;
  z-index: 2;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #FFFFFF;
  border: 3px solid var(--event-accent, var(--vm-accent-blue));
  box-shadow: 0 0 0 3px var(--event-accent-bg, rgba(51, 112, 255, 0.15)), 0 2px 4px rgba(0, 0, 0, 0.08);
  transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.25s ease;
}

.vm-timeline-col:hover .vm-timeline-dot {
  transform: scale(1.3);
  box-shadow: 0 0 0 4px var(--event-accent-bg, rgba(51, 112, 255, 0.25)), 0 0 8px var(--event-accent, var(--vm-accent-blue));
}

/* 3. 下层：纯净事件卡片（无重复时间标签） */
.vm-timeline-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--vm-neu-card);
  border-radius: 12px;
  padding: 16px 18px 16px 18px;
  border: 1px solid var(--vm-neu-card-border);
  box-shadow: var(--vm-neu-raised-shadow);
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
  box-sizing: border-box;
  text-align: left;
}

.vm-timeline-col:hover .vm-timeline-card {
  transform: translateY(-2px);
  box-shadow: var(--vm-neu-raised-hover);
}

.vm-timeline-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--vm-ink-title);
  line-height: 1.45;
  margin-bottom: 6px;
}

.vm-timeline-detail {
  font-size: 12.5px;
  color: var(--vm-ink-body);
  line-height: 1.6;
  margin-top: 4px;
  flex: 1;
  white-space: pre-line;
}

/* ─────────────────────────────────────────────────────────────
   飞书质感精细滚动条 (Feishu Sleek Scrollbar)
   ───────────────────────────────────────────────────────────── */
.vm-master-grid::-webkit-scrollbar,
.vm-flow-track::-webkit-scrollbar,
.vm-stats-grid::-webkit-scrollbar,
.vm-timeline-track::-webkit-scrollbar,
.vm-table-wrap::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.vm-master-grid::-webkit-scrollbar-track,
.vm-flow-track::-webkit-scrollbar-track,
.vm-stats-grid::-webkit-scrollbar-track,
.vm-timeline-track::-webkit-scrollbar-track,
.vm-table-wrap::-webkit-scrollbar-track {
  background: #F2F3F5;
  border-radius: 4px;
}

.vm-master-grid::-webkit-scrollbar-thumb,
.vm-flow-track::-webkit-scrollbar-thumb,
.vm-stats-grid::-webkit-scrollbar-thumb,
.vm-timeline-track::-webkit-scrollbar-thumb,
.vm-table-wrap::-webkit-scrollbar-thumb {
  background: #C9CDD4;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.vm-master-grid::-webkit-scrollbar-thumb:hover,
.vm-flow-track::-webkit-scrollbar-thumb:hover,
.vm-stats-grid::-webkit-scrollbar-thumb:hover,
.vm-timeline-track::-webkit-scrollbar-thumb:hover,
.vm-table-wrap::-webkit-scrollbar-thumb:hover {
  background: #86909C;
}

/* 响应式精修 */
@media (max-width: 640px) {
  .vm-master-card { padding: 20px 16px; }
  .vm-tree-layer-card {
    flex-direction: column;
    gap: 4px;
  }
}
"""


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render_figure_caption(title: str) -> str:
    if not title or not title.strip():
        return ""
    return (
        f'<div class="vm-figure-caption">'
        f'  <span class="vm-caption-prefix">▲ 图</span>'
        f'  <span class="vm-caption-divider">·</span>'
        f'  <span class="vm-caption-title">{escape(title.strip())}</span>'
        f'</div>'
    )


__all__ = [
    "SVG_ICON_FLOW",
    "SVG_ICON_LOOP",
    "SVG_ICON_MASTER",
    "SVG_ICON_STATS",
    "SVG_ICON_TABLE",
    "SVG_ICON_TIMELINE",
    "SVG_ICON_TREE",
    "NEU_5_COLORS",
    "TASTE_CSS",
    "escape",
    "render_figure_caption",
]
