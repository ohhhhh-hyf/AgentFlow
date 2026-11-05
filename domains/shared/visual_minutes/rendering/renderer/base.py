"""Visual Minutes 商业级设计系统与通用样式（水彩画风 Watercolor Style 规范）。"""
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

# 水彩画风 5 轮转半透明水彩色阶体系（蓝灰色、蜜桃色、青绿色、玫瑰色、沙色）
NEU_5_COLORS = [
    ("var(--vm-wc-blue)", "var(--vm-wc-blue-bg)", "var(--vm-wc-blue-border)"),
    ("var(--vm-wc-peach-text)", "var(--vm-wc-peach-bg)", "var(--vm-wc-peach-border)"),
    ("var(--vm-wc-teal-text)", "var(--vm-wc-teal-bg)", "var(--vm-wc-teal-border)"),
    ("var(--vm-wc-rose-text)", "var(--vm-wc-rose-bg)", "var(--vm-wc-rose-border)"),
    ("var(--vm-wc-sand-text)", "var(--vm-wc-sand-bg)", "var(--vm-wc-sand-border)"),
]

TASTE_CSS = """
:root {
  /* ─────────────────────────────────────────────────────────────
     水彩画风 UI 规范 (Watercolor Style Design System Tokens)
     温暖纸张色底、柔和半透明水彩晕染渗透、大圆角与柔和漫射阴影
     ───────────────────────────────────────────────────────────── */

  /* 外部主文档纯白画布文字墨水规范 (Light Canvas Tokens) */
  --vm-ink-title: #1F2329;
  --vm-ink-body: #4E5969;
  --vm-ink-muted: #86909C;
  --vm-ink-subtle: #C9CDD4;
  --vm-ink-faint: #E5E6EB;

  /* 外部主文档底色阶与边框规范 */
  --vm-tone-canvas: #FFFFFF;
  --vm-tone-card: #FFFFFF;
  --vm-tone-stone: #F2F3F5;
  --vm-tone-stone-light: #F7F8FA;
  --vm-border: #E5E6EB;

  /* ─────────────────────────────────────────────────────────────
     水彩画风专属色彩系统 (Watercolor Palette)
     ───────────────────────────────────────────────────────────── */
  /* 主色调：蓝灰色与纸张色 */
  --vm-wc-blue: #4a6fa5;
  --vm-wc-blue-bg: rgba(74, 111, 165, 0.12);
  --vm-wc-blue-border: rgba(74, 111, 165, 0.28);

  --vm-wc-paper: #faf8f5;
  --vm-wc-paper-subtle: #f0ebe3;
  --vm-wc-paper-card: rgba(255, 255, 255, 0.78);
  --vm-wc-paper-card-hover: rgba(255, 255, 255, 0.94);

  /* 水彩色系（半透明扩散） */
  --vm-wc-peach: #e8a87c;
  --vm-wc-peach-text: #b36840;
  --vm-wc-peach-bg: rgba(232, 168, 124, 0.15);
  --vm-wc-peach-border: rgba(232, 168, 124, 0.35);

  --vm-wc-teal: #85cdca;
  --vm-wc-teal-text: #37827f;
  --vm-wc-teal-bg: rgba(133, 205, 202, 0.16);
  --vm-wc-teal-border: rgba(133, 205, 202, 0.35);

  --vm-wc-rose: #c38d94;
  --vm-wc-rose-text: #96535d;
  --vm-wc-rose-bg: rgba(195, 141, 148, 0.15);
  --vm-wc-rose-border: rgba(195, 141, 148, 0.35);

  --vm-wc-sand: #d4a373;
  --vm-wc-sand-text: #9a6430;
  --vm-wc-sand-bg: rgba(212, 163, 115, 0.15);
  --vm-wc-sand-border: rgba(212, 163, 115, 0.35);

  /* 水彩文字角色 (WCAG AA 合规) */
  --vm-wc-text-main: #3a3a3a;
  --vm-wc-text-sub: #4a6fa5;
  --vm-wc-text-muted: #8a8a8a;
  --vm-wc-text-subtle: #a8a8a8;

  /* 水彩柔和边框与阴影规范 (Token 映射) */
  --vm-wc-border: rgba(74, 111, 165, 0.18);
  --vm-wc-border-hover: rgba(74, 111, 165, 0.35);

  /* 柔和漫射阴影与晕染扩散 (Pigment Bloom Shadows) */
  --vm-wc-shadow-sm: 0 2px 10px rgba(74, 111, 165, 0.08);
  --vm-wc-shadow-md: 0 4px 20px rgba(74, 111, 165, 0.10);
  --vm-wc-shadow-lg: 0 8px 30px rgba(74, 111, 165, 0.12);
  --vm-wc-shadow-bloom: 0 10px 36px rgba(74, 111, 165, 0.22);

  /* 基础尺寸与缓动规范 (液态慢速缓动) */
  --vm-radius-md: 14px;
  --vm-radius: 16px;
  --vm-radius-lg: 20px;
  --vm-radius-xl: 26px;
  --vm-wc-duration: 0.4s;
  --vm-wc-easing: ease-out;

  /* 字体规范：标题艺术衬线，正文轻盈无衬线 */
  --vm-font-serif: "Georgia", "Songti SC", "Noto Serif SC", "STSong", "SimSun", serif;
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

/* ─────────────────────────────────────────────────────────────
   水彩画风微画板容器 (Watercolor Canvas Stage)
   嵌入纯白文档中，作为温暖水彩渗透纸面画板
   ───────────────────────────────────────────────────────────── */
.vm-visual {
  /* 局部作用域重定义：水彩画板的文字与边框 */
  --vm-ink-title: var(--vm-wc-text-main);
  --vm-ink-body: var(--vm-wc-text-main);
  --vm-ink-muted: var(--vm-wc-text-muted);
  --vm-ink-subtle: var(--vm-wc-text-subtle);
  --vm-border: var(--vm-wc-border);

  /* 温暖水彩纸张底色 + 多个柔和水彩晕染径向渐变渗透 */
  position: relative;
  overflow: hidden;
  background-color: var(--vm-wc-paper);
  background-image:
    radial-gradient(circle 500px at 88% 12%, rgba(232, 168, 124, 0.20) 0%, transparent 65%),
    radial-gradient(circle 550px at 12% 88%, rgba(133, 205, 202, 0.20) 0%, transparent 65%),
    radial-gradient(circle 420px at 45% 35%, rgba(195, 141, 148, 0.14) 0%, transparent 60%),
    radial-gradient(circle 380px at 78% 78%, rgba(212, 163, 115, 0.16) 0%, transparent 60%);
  border: 1px solid var(--vm-wc-border);
  border-radius: var(--vm-radius-xl);
  padding: 24px 26px 22px 26px;
  box-shadow: 0 8px 30px rgba(74, 111, 165, 0.09), 0 2px 8px rgba(74, 111, 165, 0.04);
  font-family: var(--vm-font-sans);
  color: var(--vm-wc-text-main);
  margin: 32px 0;
  width: 100%;
  box-sizing: border-box;
}

/* 细腻水彩纸张纤维微质感纹理 */
.vm-visual::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0.02;
  pointer-events: none;
  z-index: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
}

.vm-visual > * {
  position: relative;
  z-index: 1;
}

.vm-visual * {
  box-sizing: border-box;
}

.vm-visual-title {
  display: flex;
  align-items: center;
  font-family: var(--vm-font-serif);
  font-size: 16px;
  font-weight: 600;
  color: var(--vm-wc-blue);
  margin: 0 0 14px 0;
  line-height: 1.4;
  letter-spacing: 0.02em;
}

/* 水彩画风图注规范 (Figure Caption) */
.vm-figure-caption {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  font-size: 12.5px;
  color: var(--vm-wc-text-muted);
  letter-spacing: 0.02em;
  user-select: none;
}

.vm-caption-prefix {
  font-family: var(--vm-font-serif);
  font-weight: 600;
  color: var(--vm-wc-blue);
  font-size: 11.5px;
}

.vm-caption-divider {
  color: var(--vm-wc-sand);
}

.vm-caption-title {
  font-weight: 500;
  color: var(--vm-wc-text-muted);
}

/* ─────────────────────────────────────────────────────────────
   1. 【开篇统领】Master Infographic (全景通览大图 - 水彩画风版)
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
  font-family: var(--vm-font-serif);
  font-weight: 600;
  color: var(--vm-wc-blue);
  background: var(--vm-wc-blue-bg);
  border: 1px solid var(--vm-wc-blue-border);
  box-shadow: 0 2px 8px rgba(74, 111, 165, 0.08);
  padding: 4px 14px;
  border-radius: 100px;
  margin-bottom: 12px;
  letter-spacing: 0.03em;
}

.vm-master-headline {
  font-family: var(--vm-font-serif);
  font-size: 21px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  letter-spacing: 0.02em;
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
  font-family: var(--vm-font-serif);
  font-size: 15px;
  font-weight: 600;
  color: var(--vm-wc-blue);
  margin-bottom: 12px;
  letter-spacing: 0.01em;
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
  background: rgba(240, 235, 227, 0.45);
  border: 1px solid var(--vm-wc-border);
  box-shadow: inset 0 1px 3px rgba(74, 111, 165, 0.04);
  border-radius: var(--vm-radius-xl);
  padding: 18px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(74, 111, 165, 0.2) transparent;
}

.vm-master-block {
  flex: 1 1 240px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  background: var(--vm-wc-paper-card);
  border-radius: var(--vm-radius-lg);
  padding: 20px 22px 18px 22px;
  border: 1px solid var(--vm-wc-border);
  box-shadow: var(--vm-wc-shadow-md);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing),
              box-shadow var(--vm-wc-duration) var(--vm-wc-easing),
              border-color var(--vm-wc-duration) var(--vm-wc-easing),
              background var(--vm-wc-duration) var(--vm-wc-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.vm-master-block::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--block-accent, var(--vm-wc-blue));
  opacity: 0.65;
}

.vm-master-block:hover {
  transform: scale(1.015);
  background: var(--vm-wc-paper-card-hover);
  border-color: var(--vm-wc-border-hover);
  box-shadow: var(--vm-wc-shadow-bloom);
}

.vm-master-block:active {
  transform: scale(0.98);
}

/* 水彩主题分色体系 */
.vm-theme-blue {
  --block-accent: var(--vm-wc-blue);
  --block-accent-bg: var(--vm-wc-blue-bg);
  --block-accent-border: var(--vm-wc-blue-border);
}

.vm-theme-cyan {
  --block-accent: var(--vm-wc-teal-text);
  --block-accent-bg: var(--vm-wc-teal-bg);
  --block-accent-border: var(--vm-wc-teal-border);
}

.vm-theme-purple {
  --block-accent: var(--vm-wc-rose-text);
  --block-accent-bg: var(--vm-wc-rose-bg);
  --block-accent-border: var(--vm-wc-rose-border);
}

.vm-theme-emerald {
  --block-accent: var(--vm-wc-peach-text);
  --block-accent-bg: var(--vm-wc-peach-bg);
  --block-accent-border: var(--vm-wc-peach-border);
}

.vm-theme-amber {
  --block-accent: var(--vm-wc-sand-text);
  --block-accent-bg: var(--vm-wc-sand-bg);
  --block-accent-border: var(--vm-wc-sand-border);
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
  background-color: var(--block-accent, var(--vm-wc-blue));
  box-shadow: 0 0 6px var(--block-accent, var(--vm-wc-blue));
  flex-shrink: 0;
}

.vm-master-block-title {
  font-family: var(--vm-font-serif);
  font-size: 15px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.4;
}

.vm-master-block-summary {
  font-size: 12.5px;
  color: #5a5a5a;
  line-height: 1.6;
  margin-bottom: 12px;
}

.vm-master-points {
  margin: 0 0 16px 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: #5a5a5a;
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
  background-color: var(--block-accent, var(--vm-wc-blue));
  opacity: 0.75;
}

/* 嵌入式纸质底盒 (Damp Paper Inset Box) */
.vm-master-block-highlight {
  margin-top: auto;
  background: rgba(240, 235, 227, 0.60);
  border: 1px solid var(--vm-wc-border);
  border-radius: 12px;
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
  background-color: var(--block-accent, var(--vm-wc-blue));
}

.vm-highlight-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--block-accent, var(--vm-wc-blue));
  letter-spacing: 0.03em;
}

.vm-highlight-value {
  font-family: var(--vm-font-serif);
  font-size: 14px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.4;
  word-break: break-word;
}

.vm-master-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  border-top: 1px solid var(--vm-wc-border);
  padding-top: 20px;
}

.vm-master-metric {
  flex: 1 1 180px;
  background: var(--vm-wc-paper-card);
  border-radius: var(--vm-radius);
  padding: 12px 16px;
  border: 1px solid var(--vm-wc-border);
  box-shadow: var(--vm-wc-shadow-sm);
  border-left: 3px solid var(--vm-wc-blue);
}

.vm-master-metric-value {
  display: block;
  font-family: var(--vm-font-serif);
  font-size: 20px;
  font-weight: 600;
  color: var(--vm-wc-blue);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

.vm-master-metric-label {
  display: block;
  font-size: 12px;
  color: var(--vm-wc-text-muted);
  margin-top: 3px;
  font-weight: 400;
}

/* ─────────────────────────────────────────────────────────────
   2. 【链路闭环】Flow & Closed Loop 渲染 (水彩流转版)
   ───────────────────────────────────────────────────────────── */
.vm-flow-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: rgba(240, 235, 227, 0.45);
  border: 1px solid var(--vm-wc-border);
  box-shadow: inset 0 1px 3px rgba(74, 111, 165, 0.04);
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
  scrollbar-color: rgba(74, 111, 165, 0.2) transparent;
}

.vm-flow-step-card {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  background: var(--vm-wc-paper-card);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px 16px 20px;
  border: 1px solid var(--vm-wc-border);
  box-shadow: var(--vm-wc-shadow-md);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing),
              box-shadow var(--vm-wc-duration) var(--vm-wc-easing),
              border-color var(--vm-wc-duration) var(--vm-wc-easing),
              background var(--vm-wc-duration) var(--vm-wc-easing);
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
  height: 4px;
  background: var(--step-accent, var(--vm-wc-blue));
  opacity: 0.65;
}

.vm-flow-step-card:hover {
  transform: scale(1.015);
  background: var(--vm-wc-paper-card-hover);
  border-color: var(--vm-wc-border-hover);
  box-shadow: var(--vm-wc-shadow-bloom);
}

.vm-flow-step-card:active {
  transform: scale(0.98);
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
  background: var(--step-accent, var(--vm-wc-blue));
  box-shadow: 0 0 6px var(--step-accent, var(--vm-wc-blue));
  flex-shrink: 0;
}

.vm-flow-node-title {
  font-family: var(--vm-font-serif);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.4;
}

.vm-flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  color: rgba(74, 111, 165, 0.40);
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
  color: var(--vm-wc-blue);
}

.vm-flow-node-detail {
  font-size: 12.5px;
  color: #5a5a5a;
  line-height: 1.6;
  flex: 1;
}

.vm-flow-delivery {
  margin-top: 12px;
  padding: 7px 12px;
  background: rgba(240, 235, 227, 0.60);
  border: 1px solid var(--vm-wc-border);
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: #5a5a5a;
}

.vm-delivery-arrow {
  color: var(--step-accent, var(--vm-wc-blue));
  flex-shrink: 0;
}

.vm-delivery-text {
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.35;
}

/* ─────────────────────────────────────────────────────────────
   3. 【对比矩阵】Table / Matrix 对比表 (水彩画风版)
   ───────────────────────────────────────────────────────────── */
.vm-table-wrap {
  overflow-x: auto;
  background: rgba(240, 235, 227, 0.40);
  border: 1px solid var(--vm-wc-border);
  border-radius: var(--vm-radius-xl);
  padding: 16px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(74, 111, 165, 0.2) transparent;
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
  font-family: var(--vm-font-serif);
  font-weight: 600;
  color: var(--vm-wc-blue);
  font-size: 13.5px;
  border: none;
}

.vm-th-dim {
  width: 17%;
  min-width: 100px;
  color: var(--vm-wc-text-muted);
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
  filter: drop-shadow(0 2px 6px rgba(74, 111, 165, 0.06));
  transition: filter var(--vm-wc-duration) var(--vm-wc-easing);
}

.vm-table-row:hover {
  filter: drop-shadow(0 6px 16px rgba(74, 111, 165, 0.14));
}

.vm-table td {
  padding: 14px 18px;
  text-align: left;
  vertical-align: middle;
  background: var(--vm-wc-paper-card);
  border-top: 1px solid var(--vm-wc-border);
  border-bottom: 1px solid var(--vm-wc-border);
  color: var(--vm-wc-text-main);
  line-height: 1.6;
  transition: background var(--vm-wc-duration) var(--vm-wc-easing), border-color var(--vm-wc-duration) var(--vm-wc-easing);
}

.vm-table-row:hover td {
  background: rgba(232, 168, 124, 0.12);
  border-color: rgba(232, 168, 124, 0.35);
}

.vm-td-dim {
  width: 17%;
  min-width: 100px;
  border-left: 1px solid var(--vm-wc-border);
  border-top-left-radius: 14px;
  border-bottom-left-radius: 14px;
}

.vm-dim-badge {
  display: inline-block;
  font-size: 11.5px;
  font-family: var(--vm-font-serif);
  font-weight: 600;
  color: var(--vm-wc-blue);
  background: var(--vm-wc-blue-bg);
  border: 1px solid var(--vm-wc-blue-border);
  padding: 4px 10px;
  border-radius: 8px;
  letter-spacing: 0.02em;
}

.vm-td-val {
  font-size: 13px;
}

.vm-table tr td:last-child {
  border-right: 1px solid var(--vm-wc-border);
  border-top-right-radius: 14px;
  border-bottom-right-radius: 14px;
}

/* ─────────────────────────────────────────────────────────────
   4. 【分层架构】Tree / Layered Architecture (水彩分层版)
   ───────────────────────────────────────────────────────────── */
.vm-tree-container {
  display: flex;
  flex-direction: column;
  gap: 14px;
  background: rgba(240, 235, 227, 0.40);
  border: 1px solid var(--vm-wc-border);
  border-radius: var(--vm-radius-xl);
  padding: 20px 22px;
}

.vm-tree-layer-card {
  background: var(--vm-wc-paper-card);
  border: 1px solid var(--vm-wc-border);
  border-radius: var(--vm-radius-md);
  padding: 15px 20px;
  display: flex;
  align-items: center;
  gap: 18px;
  box-shadow: var(--vm-wc-shadow-sm);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing),
              box-shadow var(--vm-wc-duration) var(--vm-wc-easing),
              border-color var(--vm-wc-duration) var(--vm-wc-easing),
              background var(--vm-wc-duration) var(--vm-wc-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.vm-tree-layer-card::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 4px;
  background: var(--layer-accent, var(--vm-wc-blue));
  opacity: 0.7;
}

.vm-tree-layer-card:hover {
  transform: scale(1.015);
  background: var(--vm-wc-paper-card-hover);
  border-color: var(--vm-wc-border-hover);
  box-shadow: var(--vm-wc-shadow-bloom);
}

.vm-tree-layer-card:active {
  transform: scale(0.98);
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
  background: var(--layer-accent, var(--vm-wc-blue));
  box-shadow: 0 0 6px var(--layer-accent, var(--vm-wc-blue));
  flex-shrink: 0;
}

.vm-tree-layer-title {
  font-family: var(--vm-font-serif);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-tree-layer-divider {
  width: 1px;
  height: 22px;
  background: rgba(74, 111, 165, 0.20);
  flex-shrink: 0;
}

.vm-tree-layer-detail {
  font-size: 13px;
  color: #5a5a5a;
  line-height: 1.6;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   5. 【量化成效】Stats 关键指标大卡 (水彩画风版)
   ───────────────────────────────────────────────────────────── */
.vm-stats-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  background: rgba(240, 235, 227, 0.45);
  border: 1px solid var(--vm-wc-border);
  box-shadow: inset 0 1px 3px rgba(74, 111, 165, 0.04);
  border-radius: var(--vm-radius-xl);
  padding: 18px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(74, 111, 165, 0.2) transparent;
}

.vm-stat-card {
  flex: 1 1 200px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  background: var(--vm-wc-paper-card);
  border: 1px solid var(--vm-wc-border);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px;
  box-shadow: var(--vm-wc-shadow-md);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing),
              box-shadow var(--vm-wc-duration) var(--vm-wc-easing),
              border-color var(--vm-wc-duration) var(--vm-wc-easing),
              background var(--vm-wc-duration) var(--vm-wc-easing);
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
  height: 4px;
  background: var(--stat-accent, var(--vm-wc-blue));
  opacity: 0.65;
}

.vm-stat-card:hover {
  transform: scale(1.015);
  background: var(--vm-wc-paper-card-hover);
  border-color: var(--vm-wc-border-hover);
  box-shadow: var(--vm-wc-shadow-bloom);
}

.vm-stat-card:active {
  transform: scale(0.98);
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
  background: var(--stat-accent, var(--vm-wc-blue));
  box-shadow: 0 0 6px var(--stat-accent, var(--vm-wc-blue));
  flex-shrink: 0;
}

.vm-stat-value {
  font-family: var(--vm-font-serif);
  font-size: 19px;
  font-weight: 600;
  color: var(--stat-accent, var(--vm-wc-blue));
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.35;
}

.vm-stat-label {
  font-size: 12.5px;
  color: var(--vm-wc-text-muted);
  line-height: 1.55;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   6. 【时序图谱】Timeline 时间演进 (水彩画风版)
   ───────────────────────────────────────────────────────────── */
.vm-timeline-canvas {
  background: rgba(240, 235, 227, 0.45);
  border: 1px solid var(--vm-wc-border);
  box-shadow: inset 0 1px 3px rgba(74, 111, 165, 0.04);
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
  scrollbar-color: rgba(74, 111, 165, 0.2) transparent;
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
  font-family: var(--vm-font-serif);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--event-accent, var(--vm-wc-blue));
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
  background: rgba(74, 111, 165, 0.22);
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
  background: #faf8f5;
  border: 3px solid var(--event-accent, var(--vm-wc-blue));
  box-shadow: 0 0 8px rgba(74, 111, 165, 0.20), 0 0 0 3px rgba(74, 111, 165, 0.10);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing), box-shadow var(--vm-wc-duration) ease;
}

.vm-timeline-col:hover .vm-timeline-dot {
  transform: scale(1.25);
  box-shadow: 0 0 12px rgba(74, 111, 165, 0.35), 0 0 0 4px rgba(74, 111, 165, 0.15);
}

.vm-timeline-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--vm-wc-paper-card);
  border-radius: var(--vm-radius-lg);
  padding: 18px 20px 16px 20px;
  border: 1px solid var(--vm-wc-border);
  box-shadow: var(--vm-wc-shadow-md);
  transition: transform var(--vm-wc-duration) var(--vm-wc-easing),
              box-shadow var(--vm-wc-duration) var(--vm-wc-easing),
              border-color var(--vm-wc-duration) var(--vm-wc-easing),
              background var(--vm-wc-duration) var(--vm-wc-easing);
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
  height: 4px;
  background: var(--event-accent, var(--vm-wc-blue));
  opacity: 0.65;
}

.vm-timeline-col:hover .vm-timeline-card {
  transform: scale(1.015);
  background: var(--vm-wc-paper-card-hover);
  border-color: var(--vm-wc-border-hover);
  box-shadow: var(--vm-wc-shadow-bloom);
}

.vm-timeline-col:active .vm-timeline-card {
  transform: scale(0.98);
}

.vm-timeline-title {
  font-family: var(--vm-font-serif);
  font-size: 14px;
  font-weight: 600;
  color: var(--vm-wc-text-main);
  line-height: 1.45;
  margin-bottom: 6px;
}

.vm-timeline-detail {
  font-size: 12.5px;
  color: #5a5a5a;
  line-height: 1.6;
  margin-top: 4px;
  flex: 1;
  white-space: pre-line;
}

/* ─────────────────────────────────────────────────────────────
   水彩柔和质感滚动条 (Soft Watercolor Scrollbar)
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
  background: rgba(74, 111, 165, 0.05);
  border-radius: 4px;
}

.vm-master-grid::-webkit-scrollbar-thumb,
.vm-flow-track::-webkit-scrollbar-thumb,
.vm-stats-grid::-webkit-scrollbar-thumb,
.vm-timeline-track::-webkit-scrollbar-thumb,
.vm-table-wrap::-webkit-scrollbar-thumb {
  background: rgba(74, 111, 165, 0.20);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.vm-master-grid::-webkit-scrollbar-thumb:hover,
.vm-flow-track::-webkit-scrollbar-thumb:hover,
.vm-stats-grid::-webkit-scrollbar-thumb:hover,
.vm-timeline-track::-webkit-scrollbar-thumb:hover,
.vm-table-wrap::-webkit-scrollbar-thumb:hover {
  background: rgba(74, 111, 165, 0.35);
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
