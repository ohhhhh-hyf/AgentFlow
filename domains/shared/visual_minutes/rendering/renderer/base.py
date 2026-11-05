"""Visual Minutes 商业级设计系统与通用样式（夜航高级毛玻璃拟态 Nocturne Glassmorphism 规范）。"""
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

# 夜航玻璃拟态 5 轮转微光色阶体系（月光蓝、水晶青、月华紫、极光绿、香槟金）
NEU_5_COLORS = [
    ("var(--vm-accent-blue)", "var(--vm-accent-blue-bg)", "var(--vm-accent-blue-border)"),
    ("var(--vm-accent-cyan)", "var(--vm-accent-cyan-bg)", "var(--vm-accent-cyan-border)"),
    ("var(--vm-accent-purple)", "var(--vm-accent-purple-bg)", "var(--vm-accent-purple-border)"),
    ("var(--vm-accent-emerald)", "var(--vm-accent-emerald-bg)", "var(--vm-accent-emerald-border)"),
    ("var(--vm-accent-amber)", "var(--vm-accent-amber-bg)", "var(--vm-accent-amber-border)"),
]

TASTE_CSS = """
:root {
  /* ─────────────────────────────────────────────────────────────
     夜航玻璃拟态 UI 规范 (Nocturne Glassmorphism Tokens)
     无色白玻璃（5%~10%），高斯模糊与饱和度增强，方向性高光与暗缘
     ───────────────────────────────────────────────────────────── */
  /* 夜景场景底色 */
  --vm-bg-night: #0B1322;
  --vm-bg-night-deep: #060A13;
  --vm-bg-elevated: #16233A;

  /* 唯一主强调色：香槟金 (Champagne Gold Accents) */
  --vm-accent-gold: #E4B863;
  --vm-accent-gold-light: #F3DCA8;
  --vm-accent-gold-bg: rgba(228, 184, 99, 0.12);
  --vm-accent-gold-border: rgba(228, 184, 99, 0.40);

  /* 夜航月光与微光色彩系统 (Moonlight Astral Palette) */
  --vm-accent-blue: #7C9CC4;
  --vm-accent-blue-bg: rgba(124, 156, 196, 0.12);
  --vm-accent-blue-border: rgba(124, 156, 196, 0.35);

  --vm-accent-cyan: #87E8DE;
  --vm-accent-cyan-bg: rgba(135, 232, 222, 0.12);
  --vm-accent-cyan-border: rgba(135, 232, 222, 0.35);

  --vm-accent-purple: #B8A9D9;
  --vm-accent-purple-bg: rgba(184, 169, 217, 0.12);
  --vm-accent-purple-border: rgba(184, 169, 217, 0.35);

  --vm-accent-emerald: #7FB69E;
  --vm-accent-emerald-bg: rgba(127, 182, 158, 0.12);
  --vm-accent-emerald-border: rgba(127, 182, 158, 0.35);

  --vm-accent-amber: #E4B863;
  --vm-accent-amber-bg: rgba(228, 184, 99, 0.12);
  --vm-accent-amber-border: rgba(228, 184, 99, 0.40);

  /* 玻璃外托盘 / 容器底盘 (Outer Frosted Tray) */
  --vm-glass-tray-bg: rgba(255, 255, 255, 0.04);
  --vm-glass-tray-border: rgba(255, 255, 255, 0.12);
  --vm-glass-tray-shadow: 0 20px 48px rgba(3, 7, 18, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.15), inset 0 -1px 0 rgba(2, 6, 16, 0.4);

  /* 玻璃卡片 (Inner Glass Card - 5%~10% 白玻璃，绝不上色) */
  --vm-glass-card-bg: rgba(255, 255, 255, 0.07);
  --vm-glass-card-bg-hover: rgba(255, 255, 255, 0.12);
  --vm-glass-card-border: rgba(255, 255, 255, 0.15);
  --vm-glass-card-border-hover: rgba(255, 255, 255, 0.32);

  /* 方向性阴影：顶边高光 + 底边暗缘 + 外层深阴影 */
  --vm-glass-card-shadow: 0 16px 40px rgba(3, 7, 18, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.22), inset 0 -1px 0 rgba(2, 6, 16, 0.35);
  --vm-glass-card-shadow-hover: 0 24px 64px rgba(3, 7, 18, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.32), inset 0 -1px 0 rgba(2, 6, 16, 0.35);

  /* 嵌入式凹槽小盒 (Glass Inset Pill / Box) */
  --vm-glass-inset-bg: rgba(6, 10, 19, 0.45);
  --vm-glass-inset-border: rgba(255, 255, 255, 0.10);
  --vm-glass-inset-shadow: inset 0 2px 5px rgba(2, 6, 16, 0.6), inset 0 -1px 0 rgba(255, 255, 255, 0.12);

  /* 文字墨水规范（针对深色玻璃夜景调优） */
  --vm-ink-title: #FFFFFF;
  --vm-ink-body: rgba(255, 255, 255, 0.85);
  --vm-ink-muted: rgba(255, 255, 255, 0.65);
  --vm-ink-subtle: rgba(255, 255, 255, 0.45);
  --vm-ink-faint: rgba(255, 255, 255, 0.25);

  /* 底色阶与边框兼容 */
  --vm-tone-canvas: #0B1322;
  --vm-tone-card: rgba(255, 255, 255, 0.07);
  --vm-tone-stone: rgba(255, 255, 255, 0.05);
  --vm-tone-stone-light: rgba(255, 255, 255, 0.03);
  --vm-border: rgba(255, 255, 255, 0.12);

  /* 基础尺寸与缓动规范 */
  --vm-radius: 12px;
  --vm-radius-lg: 16px;
  --vm-radius-xl: 24px;
  --vm-spring-easing: cubic-bezier(0.16, 1, 0.3, 1);
  --vm-duration: 0.5s;
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
  margin: 32px 0;
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
  color: #FFFFFF;
  margin: 0 0 14px 0;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

/* 玻璃拟态图注规范 (Figure Caption) */
.vm-figure-caption {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  font-size: 12.5px;
  color: var(--vm-ink-subtle);
  letter-spacing: 0.02em;
  user-select: none;
}

.vm-caption-prefix {
  font-weight: 700;
  color: var(--vm-accent-gold);
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
   1. 【开篇统领】Master Infographic (全景通览大图 - 玻璃拟态版)
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
  color: var(--vm-accent-gold-light);
  background: rgba(228, 184, 99, 0.12);
  border: 1px solid rgba(228, 184, 99, 0.35);
  box-shadow: 0 2px 10px rgba(228, 184, 99, 0.15);
  padding: 4px 12px;
  border-radius: 100px;
  margin-bottom: 12px;
  letter-spacing: 0.03em;
}

.vm-master-headline {
  font-size: 22px;
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: -0.02em;
  line-height: 1.35;
  margin: 0 0 14px 0;
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
  color: #FFFFFF;
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
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 18px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-master-block {
  flex: 1 1 240px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(50px) saturate(180%);
  -webkit-backdrop-filter: blur(50px) saturate(180%);
  border-radius: var(--vm-radius-lg);
  padding: 20px 22px 18px 22px;
  border: 1px solid var(--vm-glass-card-border);
  box-shadow: var(--vm-glass-card-shadow);
  transition: transform var(--vm-duration) var(--vm-spring-easing),
              box-shadow var(--vm-duration) var(--vm-spring-easing),
              border-color var(--vm-duration) var(--vm-spring-easing),
              background var(--vm-duration) var(--vm-spring-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

/* 顶边内发光 (Inner Top Luminance) */
.vm-master-block::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, transparent 100%);
  pointer-events: none;
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;
}

.vm-master-block:hover {
  transform: translateY(-4px);
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
  box-shadow: var(--vm-glass-card-shadow-hover);
}

/* 夜航主题微光分色体系 */
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
  box-shadow: 0 0 8px var(--block-accent, var(--vm-accent-gold));
  background-color: var(--block-accent, var(--vm-accent-gold));
  flex-shrink: 0;
}

.vm-master-block-title {
  font-size: 15px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.4;
}

.vm-master-block-summary {
  font-size: 12.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.6;
  margin-bottom: 12px;
}

.vm-master-points {
  margin: 0 0 16px 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.6;
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
  background-color: var(--block-accent, var(--vm-accent-gold));
  box-shadow: 0 0 6px var(--block-accent, var(--vm-accent-gold));
}

/* 嵌入式高光底盒 (Glass Inset Pill) */
.vm-master-block-highlight {
  margin-top: auto;
  background: var(--vm-glass-inset-bg);
  box-shadow: var(--vm-glass-inset-shadow);
  border: 1px solid var(--vm-glass-inset-border);
  border-radius: 10px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vm-highlight-tag-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.vm-highlight-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: var(--block-accent, var(--vm-accent-gold));
  box-shadow: 0 0 6px var(--block-accent, var(--vm-accent-gold));
}

.vm-highlight-tag {
  font-size: 11px;
  font-weight: 700;
  color: var(--vm-accent-gold-light);
  letter-spacing: 0.04em;
}

.vm-highlight-value {
  font-size: 13.5px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.4;
  word-break: break-word;
}

.vm-master-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  padding-top: 20px;
}

.vm-master-metric {
  flex: 1 1 180px;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border-radius: var(--vm-radius);
  padding: 12px 16px;
  border: 1px solid var(--vm-glass-card-border);
  border-left: 3px solid var(--vm-accent-gold);
}

.vm-master-metric-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #FFFFFF;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  text-shadow: 0 0 12px rgba(228, 184, 99, 0.2);
}

.vm-master-metric-label {
  display: block;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  margin-top: 3px;
  font-weight: 500;
}

/* ─────────────────────────────────────────────────────────────
   2. 【链路闭环】Flow & Closed Loop 渲染 (夜航玻璃流转版)
   ───────────────────────────────────────────────────────────── */
.vm-flow-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 18px 20px;
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
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-flow-step-card {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(50px) saturate(180%);
  -webkit-backdrop-filter: blur(50px) saturate(180%);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px 16px 20px;
  border: 1px solid var(--vm-glass-card-border);
  box-shadow: var(--vm-glass-card-shadow);
  transition: transform var(--vm-duration) var(--vm-spring-easing),
              box-shadow var(--vm-duration) var(--vm-spring-easing),
              border-color var(--vm-duration) var(--vm-spring-easing),
              background var(--vm-duration) var(--vm-spring-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.vm-flow-step-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 36px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, transparent 100%);
  pointer-events: none;
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;
}

.vm-flow-step-card:hover {
  transform: translateY(-4px);
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
  box-shadow: var(--vm-glass-card-shadow-hover);
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
  box-shadow: 0 0 8px var(--step-accent, var(--vm-accent-gold));
  flex-shrink: 0;
}

.vm-flow-node-title {
  font-size: 14.5px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.4;
}

.vm-flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  color: rgba(255, 255, 255, 0.35);
  user-select: none;
  transition: color 0.3s ease;
}

.vm-connector-arrow {
  opacity: 0.8;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.vm-flow-track:hover .vm-connector-arrow {
  opacity: 1;
}

.vm-flow-track:hover .vm-flow-connector {
  color: var(--vm-accent-gold);
}

.vm-flow-node-detail {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.75);
  line-height: 1.6;
  flex: 1;
}

.vm-flow-delivery {
  margin-top: 12px;
  padding: 7px 12px;
  background: var(--vm-glass-inset-bg);
  box-shadow: var(--vm-glass-inset-shadow);
  border: 1px solid var(--vm-glass-inset-border);
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--vm-ink-body);
}

.vm-delivery-arrow {
  color: var(--step-accent, var(--vm-accent-gold));
  flex-shrink: 0;
}

.vm-delivery-text {
  font-weight: 600;
  color: rgba(255, 255, 255, 0.90);
  line-height: 1.35;
}

/* ─────────────────────────────────────────────────────────────
   3. 【对比矩阵】Table / Matrix 对比表 (夜航玻璃拟态版)
   ───────────────────────────────────────────────────────────── */
.vm-table-wrap {
  overflow-x: auto;
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 16px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0 8px;
  font-size: 13px;
  min-width: 580px;
}

.vm-table th {
  padding: 10px 16px 8px 16px;
  text-align: left;
  font-weight: 700;
  color: #FFFFFF;
  font-size: 13.5px;
  border: none;
}

.vm-th-dim {
  width: 17%;
  min-width: 100px;
  color: rgba(255, 255, 255, 0.65);
}

.vm-th-col {
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
  filter: drop-shadow(0 4px 12px rgba(3, 7, 18, 0.45));
  transition: filter var(--vm-duration) var(--vm-spring-easing);
}

.vm-table-row:hover {
  filter: drop-shadow(0 8px 24px rgba(3, 7, 18, 0.65));
}

.vm-table td {
  padding: 14px 18px;
  text-align: left;
  vertical-align: middle;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border-top: 1px solid var(--vm-glass-card-border);
  border-bottom: 1px solid var(--vm-glass-card-border);
  color: var(--vm-ink-body);
  line-height: 1.6;
  transition: background var(--vm-duration) var(--vm-spring-easing), border-color var(--vm-duration) var(--vm-spring-easing);
}

.vm-table-row:hover td {
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
}

.vm-td-dim {
  width: 17%;
  min-width: 100px;
  border-left: 1px solid var(--vm-glass-card-border);
  border-top-left-radius: 12px;
  border-bottom-left-radius: 12px;
}

.vm-dim-badge {
  display: inline-block;
  font-size: 11.5px;
  font-weight: 700;
  color: #FFFFFF;
  background: var(--vm-glass-inset-bg);
  box-shadow: var(--vm-glass-inset-shadow);
  border: 1px solid var(--vm-glass-inset-border);
  padding: 4px 10px;
  border-radius: 8px;
  letter-spacing: 0.03em;
}

.vm-td-val {
  font-size: 13px;
}

.vm-table tr td:last-child {
  border-right: 1px solid var(--vm-glass-card-border);
  border-top-right-radius: 12px;
  border-bottom-right-radius: 12px;
}

/* ─────────────────────────────────────────────────────────────
   4. 【分层架构】Tree / Layered Architecture (夜航玻璃分层版)
   ───────────────────────────────────────────────────────────── */
.vm-tree-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 20px 22px;
}

.vm-tree-layer-card {
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(50px) saturate(180%);
  -webkit-backdrop-filter: blur(50px) saturate(180%);
  border: 1px solid var(--vm-glass-card-border);
  border-radius: var(--vm-radius-md);
  padding: 15px 20px;
  display: flex;
  align-items: center;
  gap: 18px;
  box-shadow: var(--vm-glass-card-shadow);
  transition: transform var(--vm-duration) var(--vm-spring-easing),
              box-shadow var(--vm-duration) var(--vm-spring-easing),
              border-color var(--vm-duration) var(--vm-spring-easing),
              background var(--vm-duration) var(--vm-spring-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.vm-tree-layer-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, transparent 100%);
  pointer-events: none;
}

.vm-tree-layer-card:hover {
  transform: translateY(-3px);
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
  box-shadow: var(--vm-glass-card-shadow-hover);
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
  box-shadow: 0 0 8px var(--layer-accent, var(--vm-accent-gold));
  flex-shrink: 0;
}

.vm-tree-layer-title {
  font-size: 14.5px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-tree-layer-divider {
  width: 1px;
  height: 22px;
  background: rgba(255, 255, 255, 0.18);
  flex-shrink: 0;
}

.vm-tree-layer-detail {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.80);
  line-height: 1.6;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   5. 【量化成效】Stats 关键指标大卡 (夜航玻璃拟态版)
   ───────────────────────────────────────────────────────────── */
.vm-stats-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 18px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-stat-card {
  flex: 1 1 200px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(50px) saturate(180%);
  -webkit-backdrop-filter: blur(50px) saturate(180%);
  border: 1px solid var(--vm-glass-card-border);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px;
  box-shadow: var(--vm-glass-card-shadow);
  transition: transform var(--vm-duration) var(--vm-spring-easing),
              box-shadow var(--vm-duration) var(--vm-spring-easing),
              border-color var(--vm-duration) var(--vm-spring-easing),
              background var(--vm-duration) var(--vm-spring-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.vm-stat-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 36px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, transparent 100%);
  pointer-events: none;
}

.vm-stat-card:hover {
  transform: translateY(-4px);
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
  box-shadow: var(--vm-glass-card-shadow-hover);
}

.vm-stat-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.vm-stat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  box-shadow: 0 0 8px var(--stat-accent, var(--vm-accent-gold));
  flex-shrink: 0;
}

.vm-stat-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--stat-accent, var(--vm-accent-gold));
  text-shadow: 0 0 16px rgba(228, 184, 99, 0.25);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.35;
}

.vm-stat-label {
  font-size: 12.5px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.80);
  line-height: 1.55;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   6. 【时序图谱】Timeline 时间演进 (夜航玻璃拟态版)
   ───────────────────────────────────────────────────────────── */
.vm-timeline-canvas {
  background: var(--vm-glass-tray-bg);
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid var(--vm-glass-tray-border);
  box-shadow: var(--vm-glass-tray-shadow);
  border-radius: var(--vm-radius-xl);
  padding: 24px 20px 20px 20px;
}

.vm-timeline-track {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  padding: 6px 12px 14px 12px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}

.vm-timeline-col {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  box-sizing: border-box;
}

.vm-timeline-time-label {
  font-size: 13.5px;
  font-weight: 700;
  font-family: var(--vm-font-mono), var(--vm-font-sans);
  color: var(--event-accent, var(--vm-accent-gold-light));
  text-shadow: 0 0 10px rgba(228, 184, 99, 0.2);
  text-align: center;
  margin-bottom: 10px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  line-height: 1.4;
  user-select: none;
  transition: transform 0.2s ease;
}

.vm-timeline-col:hover .vm-timeline-time-label {
  transform: translateY(-1px);
}

.vm-timeline-node {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  margin-bottom: 14px;
}

.vm-timeline-node::before {
  content: "";
  position: absolute;
  top: 50%;
  left: -8px;
  right: -8px;
  height: 2px;
  background: rgba(255, 255, 255, 0.22);
  transform: translateY(-50%);
  z-index: 1;
}

.vm-timeline-col:first-child .vm-timeline-node::before {
  left: -14px;
}
.vm-timeline-col:last-child .vm-timeline-node::before {
  right: -14px;
}

.vm-timeline-dot {
  position: relative;
  z-index: 2;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #0B1322;
  border: 3px solid var(--event-accent, var(--vm-accent-gold));
  box-shadow: 0 0 12px var(--event-accent, var(--vm-accent-gold)), 0 0 0 3px rgba(255, 255, 255, 0.12);
  transition: transform 0.3s var(--vm-spring-easing), box-shadow 0.3s ease;
}

.vm-timeline-col:hover .vm-timeline-dot {
  transform: scale(1.3);
  box-shadow: 0 0 16px var(--event-accent, var(--vm-accent-gold)), 0 0 0 4px rgba(255, 255, 255, 0.25);
}

.vm-timeline-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--vm-glass-card-bg);
  backdrop-filter: blur(50px) saturate(180%);
  -webkit-backdrop-filter: blur(50px) saturate(180%);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px 16px 20px;
  border: 1px solid var(--vm-glass-card-border);
  box-shadow: var(--vm-glass-card-shadow);
  transition: transform var(--vm-duration) var(--vm-spring-easing),
              box-shadow var(--vm-duration) var(--vm-spring-easing),
              border-color var(--vm-duration) var(--vm-spring-easing),
              background var(--vm-duration) var(--vm-spring-easing);
  box-sizing: border-box;
  text-align: left;
  position: relative;
  overflow: hidden;
}

.vm-timeline-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 36px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, transparent 100%);
  pointer-events: none;
}

.vm-timeline-col:hover .vm-timeline-card {
  transform: translateY(-4px);
  background: var(--vm-glass-card-bg-hover);
  border-color: var(--vm-glass-card-border-hover);
  box-shadow: var(--vm-glass-card-shadow-hover);
}

.vm-timeline-title {
  font-size: 14px;
  font-weight: 700;
  color: #FFFFFF;
  line-height: 1.45;
  margin-bottom: 6px;
}

.vm-timeline-detail {
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.80);
  line-height: 1.6;
  margin-top: 4px;
  flex: 1;
  white-space: pre-line;
}

/* ─────────────────────────────────────────────────────────────
   夜航高级毛玻璃滚动条 (Sleek Glass Scrollbar)
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
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.vm-master-grid::-webkit-scrollbar-thumb,
.vm-flow-track::-webkit-scrollbar-thumb,
.vm-stats-grid::-webkit-scrollbar-thumb,
.vm-timeline-track::-webkit-scrollbar-thumb,
.vm-table-wrap::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.20);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.vm-master-grid::-webkit-scrollbar-thumb:hover,
.vm-flow-track::-webkit-scrollbar-thumb:hover,
.vm-stats-grid::-webkit-scrollbar-thumb:hover,
.vm-timeline-track::-webkit-scrollbar-thumb:hover,
.vm-table-wrap::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.35);
}

/* 响应式精修 */
@media (max-width: 640px) {
  .vm-master-card { padding: 16px 12px; }
  .vm-tree-layer-card {
    flex-direction: column;
    gap: 6px;
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
