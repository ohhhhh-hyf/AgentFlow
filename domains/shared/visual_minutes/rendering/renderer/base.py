"""Visual Minutes 商业级设计系统与通用样式（企业简洁风 Corporate Clean Style 规范）。

遵循现代企业级 UI 标准 (Corporate Clean)：
- 纯白卡片：bg-white rounded-xl shadow-sm border border-gray-200
- 悬停浮起：hover:-translate-y-0.5 hover:shadow-md
- 触觉确认：active:scale-[0.98]
- 专业蓝色系：blue-600 (#2563EB), blue-700 (#1D4ED8), blue-50 (#EFF6FF), blue-500 (#3B82F6)
- 严禁鲜艳杂乱渐变，严禁 rounded-none，动效时长 <= 200ms。
"""
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

# Corporate Clean 5 轮转语义色彩体系 (Blue, Indigo, Emerald, Amber, Sky)
NEU_5_COLORS = [
    ("var(--vm-cc-blue)", "var(--vm-cc-blue-bg)", "var(--vm-cc-blue-border)"),
    ("var(--vm-cc-indigo)", "var(--vm-cc-indigo-bg)", "var(--vm-cc-indigo-border)"),
    ("var(--vm-cc-emerald)", "var(--vm-cc-emerald-bg)", "var(--vm-cc-emerald-border)"),
    ("var(--vm-cc-amber)", "var(--vm-cc-amber-bg)", "var(--vm-cc-amber-border)"),
    ("var(--vm-cc-sky)", "var(--vm-cc-sky-bg)", "var(--vm-cc-sky-border)"),
]

TASTE_CSS = """
:root {
  /* ─────────────────────────────────────────────────────────────
     Corporate Clean (企业简洁风) Design System Tokens
     专业、可信、高效，严格遵守 WCAG AA 标准
     ───────────────────────────────────────────────────────────── */

  /* 品牌与主操作色（Blue 蓝色系） */
  --vm-cc-blue: #2563EB;          /* blue-600 主品牌色 */
  --vm-cc-blue-hover: #1D4ED8;    /* blue-700 悬停深蓝 */
  --vm-cc-blue-ring: #3B82F6;     /* blue-500 焦点环 */
  --vm-cc-blue-bg: #EFF6FF;       /* blue-50 浅蓝背景 */
  --vm-cc-blue-border: #BFDBFE;   /* blue-200 边框 */

  /* 辅助调色板（语义色彩体系） */
  --vm-cc-indigo: #4F46E5;        /* indigo-600 架构/系统 */
  --vm-cc-indigo-bg: #EEF2FF;     /* indigo-50 */
  --vm-cc-indigo-border: #C7D2FE; /* indigo-200 */

  --vm-cc-emerald: #059669;       /* emerald-600 达成/健康 */
  --vm-cc-emerald-bg: #ECFDF5;    /* emerald-50 */
  --vm-cc-emerald-border: #A7F3D0;/* emerald-200 */

  --vm-cc-amber: #D97706;         /* amber-600 关注/进行中 */
  --vm-cc-amber-bg: #FFFBEB;      /* amber-50 */
  --vm-cc-amber-border: #FDE68A;  /* amber-200 */

  --vm-cc-sky: #0284C7;           /* sky-600 流程/集成 */
  --vm-cc-sky-bg: #F0F9FF;        /* sky-50 */
  --vm-cc-sky-border: #BAE6FD;    /* sky-200 */

  /* 中性灰色系 (Slate / Gray Tokens) */
  --vm-cc-canvas: #F8FAFC;        /* slate-50 容器底色 */
  --vm-cc-card-bg: #FFFFFF;       /* white 卡片纯白基底 */
  --vm-cc-subtle-bg: #F1F5F9;     /* slate-100 内嵌小盒 */
  --vm-cc-border: #E2E8F0;        /* slate-200 / gray-200 边框 */
  --vm-cc-border-hover: #CBD5E1;  /* slate-300 悬停边框 */

  /* 文字颜色角色 (WCAG AA 合规) */
  --vm-cc-text-title: #0F172A;    /* slate-900 / gray-900 标题墨色 */
  --vm-cc-text-body: #334155;     /* slate-700 正文清晰可读 */
  --vm-cc-text-muted: #64748B;    /* slate-500 次要辅助信息 */
  --vm-cc-text-subtle: #94A3B8;   /* slate-400 弱化占位 */

  /* 阴影与微动效规范 (利落干脆，严禁 shadow-2xl 与 >200ms 慢动效) */
  --vm-cc-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);                                   /* shadow-sm 静止状态 */
  --vm-cc-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1); /* shadow-md 悬浮状态 */
  --vm-cc-ring-focus: 0 0 0 2px #FFFFFF, 0 0 0 4px #3B82F6;                             /* focus:ring-2 focus:ring-offset-2 */

  --vm-cc-duration: 180ms;
  --vm-cc-easing: cubic-bezier(0, 0, 0.2, 1); /* ease-out */

  /* 圆角规范 (企业级 rounded-lg / rounded-xl，绝对禁止 rounded-none) */
  --vm-radius-sm: 6px;
  --vm-radius-md: 8px;     /* rounded-lg */
  --vm-radius-lg: 12px;    /* rounded-xl */
  --vm-radius-xl: 16px;    /* rounded-2xl 外容器 */

  /* 企业字体：利落清晰无衬线，数据等宽 */
  --vm-font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  --vm-font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

  /* 向下兼容旧别名映射 */
  --vm-wc-blue: var(--vm-cc-blue);
  --vm-wc-blue-bg: var(--vm-cc-blue-bg);
  --vm-wc-blue-border: var(--vm-cc-blue-border);
  --vm-wc-peach-text: var(--vm-cc-amber);
  --vm-wc-peach-bg: var(--vm-cc-amber-bg);
  --vm-wc-peach-border: var(--vm-cc-amber-border);
  --vm-wc-teal-text: var(--vm-cc-emerald);
  --vm-wc-teal-bg: var(--vm-cc-emerald-bg);
  --vm-wc-teal-border: var(--vm-cc-emerald-border);
  --vm-wc-rose-text: var(--vm-cc-indigo);
  --vm-wc-rose-bg: var(--vm-cc-indigo-bg);
  --vm-wc-rose-border: var(--vm-cc-indigo-border);
  --vm-wc-sand-text: var(--vm-cc-sky);
  --vm-wc-sand-bg: var(--vm-cc-sky-bg);
  --vm-wc-sand-border: var(--vm-cc-sky-border);
  --vm-wc-text-main: var(--vm-cc-text-title);
  --vm-wc-text-muted: var(--vm-cc-text-muted);
  --vm-wc-border: var(--vm-cc-border);
  --vm-wc-border-hover: var(--vm-cc-border-hover);
  --vm-wc-shadow-sm: var(--vm-cc-shadow-sm);
  --vm-wc-shadow-md: var(--vm-cc-shadow-md);
  --vm-wc-shadow-bloom: var(--vm-cc-shadow-md);
  --vm-wc-duration: var(--vm-cc-duration);
  --vm-wc-easing: var(--vm-cc-easing);
  --vm-font-serif: var(--vm-font-sans);
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
   企业简洁风卡片外容器 (Corporate Clean Stage)
   以淡石板灰 (bg-slate-50) 作为微画板，高对比度突出内部纯白卡片
   ───────────────────────────────────────────────────────────── */
.vm-visual {
  position: relative;
  background-color: var(--vm-cc-canvas);
  background-image: none !important;
  border: 1px solid var(--vm-cc-border);
  border-radius: var(--vm-radius-xl);
  padding: 24px;
  box-shadow: var(--vm-cc-shadow-sm);
  font-family: var(--vm-font-sans);
  color: var(--vm-cc-text-body);
  margin: 32px 0;
  width: 100%;
  box-sizing: border-box;
}

.vm-visual::before {
  display: none !important; /* 严格禁止噪点与纸张纤维纹理 */
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
  font-family: var(--vm-font-sans);
  font-size: 15px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  margin: 0 0 14px 0;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

/* 企业图注规范 (Figure Caption) */
.vm-figure-caption {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 16px;
  font-size: 12px;
  color: var(--vm-cc-text-muted);
  font-family: var(--vm-font-sans);
  user-select: none;
}

.vm-caption-prefix {
  font-family: var(--vm-font-sans);
  font-weight: 600;
  color: var(--vm-cc-blue);
  font-size: 11px;
}

.vm-caption-divider {
  color: var(--vm-cc-border);
}

.vm-caption-title {
  font-weight: 500;
  color: var(--vm-cc-text-muted);
}

/* ─────────────────────────────────────────────────────────────
   1. 【开篇统领】Master Infographic (全景通览大图 - 企业简洁风版)
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
  font-size: 12px;
  font-family: var(--vm-font-sans);
  font-weight: 600;
  color: var(--vm-cc-blue);
  background: var(--vm-cc-blue-bg);
  border: 1px solid var(--vm-cc-blue-border);
  box-shadow: var(--vm-cc-shadow-sm);
  padding: 4px 12px;
  border-radius: var(--vm-radius-md); /* rounded-lg */
  margin-bottom: 12px;
  letter-spacing: -0.01em;
}

.vm-master-headline {
  font-family: var(--vm-font-sans);
  font-size: 18px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  letter-spacing: -0.02em;
  line-height: 1.4;
  margin: 0 0 16px 0;
}

.vm-master-widgets-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.vm-master-widget {
  width: 100%;
}

.vm-widget-title {
  font-family: var(--vm-font-sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  margin-bottom: 12px;
  letter-spacing: -0.01em;
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
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 4px 2px 14px 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--vm-cc-border) transparent;
}

.vm-master-block {
  flex: 1 1 240px;
  min-width: 220px;
  display: flex;
  flex-direction: column;
  background: var(--vm-cc-card-bg); /* bg-white */
  border-radius: var(--vm-radius-lg); /* rounded-xl (12px) */
  padding: 20px 20px 18px 20px;       /* p-5 */
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing),
              box-shadow var(--vm-cc-duration) var(--vm-cc-easing),
              border-color var(--vm-cc-duration) var(--vm-cc-easing);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

/* 顶部企业级精致 3px 纯色标识线 */
.vm-master-block::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--block-accent, var(--vm-cc-blue));
}

.vm-master-block:hover {
  transform: translateY(-2px); /* hover:-translate-y-0.5 */
  border-color: var(--vm-cc-border-hover);
  box-shadow: var(--vm-cc-shadow-md); /* hover:shadow-md */
}

.vm-master-block:active {
  transform: scale(0.98) translateY(0); /* active:scale-[0.98] */
  box-shadow: var(--vm-cc-shadow-sm);
}

/* 主题分色体系 (Corporate Clean 语义色) */
.vm-theme-blue {
  --block-accent: var(--vm-cc-blue);
  --block-accent-bg: var(--vm-cc-blue-bg);
  --block-accent-border: var(--vm-cc-blue-border);
}

.vm-theme-cyan {
  --block-accent: var(--vm-cc-sky);
  --block-accent-bg: var(--vm-cc-sky-bg);
  --block-accent-border: var(--vm-cc-sky-border);
}

.vm-theme-purple {
  --block-accent: var(--vm-cc-indigo);
  --block-accent-bg: var(--vm-cc-indigo-bg);
  --block-accent-border: var(--vm-cc-indigo-border);
}

.vm-theme-emerald {
  --block-accent: var(--vm-cc-emerald);
  --block-accent-bg: var(--vm-cc-emerald-bg);
  --block-accent-border: var(--vm-cc-emerald-border);
}

.vm-theme-amber {
  --block-accent: var(--vm-cc-amber);
  --block-accent-bg: var(--vm-cc-amber-bg);
  --block-accent-border: var(--vm-cc-amber-border);
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
  background-color: var(--block-accent, var(--vm-cc-blue));
  flex-shrink: 0;
}

.vm-master-block-title {
  font-family: var(--vm-font-sans);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-master-block-summary {
  font-size: 12.5px;
  color: var(--vm-cc-text-body);
  line-height: 1.6;
  margin-bottom: 12px;
}

.vm-master-points {
  margin: 0 0 16px 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: var(--vm-cc-text-body);
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
  background-color: var(--block-accent, var(--vm-cc-blue));
}

/* 嵌入式企业信息底盒 */
.vm-master-block-highlight {
  margin-top: auto;
  background: var(--vm-cc-canvas); /* bg-slate-50 */
  border: 1px solid var(--vm-cc-border);
  border-radius: var(--vm-radius-md); /* rounded-lg (8px) */
  padding: 9px 12px;
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
  background-color: var(--block-accent, var(--vm-cc-blue));
}

.vm-highlight-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--block-accent, var(--vm-cc-blue));
  letter-spacing: 0.01em;
}

.vm-highlight-value {
  font-family: var(--vm-font-sans);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  line-height: 1.4;
  word-break: break-word;
}

.vm-master-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  border-top: 1px solid var(--vm-cc-border);
  padding-top: 18px;
}

.vm-master-metric {
  flex: 1 1 180px;
  background: var(--vm-cc-card-bg);
  border-radius: var(--vm-radius-md);
  padding: 12px 16px;
  border: 1px solid var(--vm-cc-border);
  box-shadow: var(--vm-cc-shadow-sm);
  border-left: 3px solid var(--vm-cc-blue);
}

.vm-master-metric-value {
  display: block;
  font-family: var(--vm-font-sans);
  font-size: 20px;
  font-weight: 700;
  color: var(--vm-cc-blue);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

.vm-master-metric-label {
  display: block;
  font-size: 12px;
  color: var(--vm-cc-text-muted);
  margin-top: 3px;
  font-weight: 500;
}

/* ─────────────────────────────────────────────────────────────
   2. 【流程推进】Flow Process Pipeline (企业简洁风版)
   ───────────────────────────────────────────────────────────── */
.vm-flow-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 4px 2px;
}

.vm-flow-track {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 14px;
  align-items: stretch;
  padding: 4px 2px 14px 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--vm-cc-border) transparent;
}

.vm-flow-step-card {
  flex: 1 1 220px;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  background: var(--vm-cc-card-bg); /* bg-white */
  border-radius: var(--vm-radius-lg); /* rounded-xl (12px) */
  padding: 18px 18px 16px 18px;
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing),
              box-shadow var(--vm-cc-duration) var(--vm-cc-easing),
              border-color var(--vm-cc-duration) var(--vm-cc-easing);
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
  height: 3px;
  background: var(--step-accent, var(--vm-cc-blue));
}

.vm-flow-step-card:hover {
  transform: translateY(-2px); /* hover:-translate-y-0.5 */
  border-color: var(--vm-cc-border-hover);
  box-shadow: var(--vm-cc-shadow-md); /* hover:shadow-md */
}

.vm-flow-step-card:active {
  transform: scale(0.98) translateY(0); /* active:scale-[0.98] */
  box-shadow: var(--vm-cc-shadow-sm);
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
  background: var(--step-accent, var(--vm-cc-blue));
  flex-shrink: 0;
}

.vm-flow-node-title {
  font-family: var(--vm-font-sans);
  font-size: 14.5px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-flow-connector {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  color: var(--vm-cc-text-subtle);
  user-select: none;
  transition: color var(--vm-cc-duration) var(--vm-cc-easing);
}

.vm-connector-arrow {
  opacity: 0.7;
  transition: opacity var(--vm-cc-duration) ease, transform var(--vm-cc-duration) ease;
}

.vm-flow-track:hover .vm-connector-arrow {
  opacity: 1;
}

.vm-flow-track:hover .vm-flow-connector {
  color: var(--vm-cc-blue);
}

.vm-flow-node-detail {
  font-size: 12.5px;
  color: var(--vm-cc-text-body);
  line-height: 1.6;
  flex: 1;
}

.vm-flow-delivery {
  margin-top: 12px;
  padding: 6px 10px;
  background: var(--vm-cc-blue-bg);
  border: 1px solid var(--vm-cc-blue-border);
  border-radius: var(--vm-radius-md); /* rounded-lg */
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--vm-cc-blue);
}

.vm-delivery-arrow {
  color: var(--vm-cc-blue);
  flex-shrink: 0;
}

.vm-delivery-text {
  font-weight: 600;
  color: var(--vm-cc-blue);
  line-height: 1.35;
}

/* ─────────────────────────────────────────────────────────────
   3. 【对比矩阵】Table / Comparison Matrix (企业简洁风版)
   ───────────────────────────────────────────────────────────── */
.vm-table-wrap {
  overflow-x: auto;
  background: var(--vm-cc-card-bg); /* bg-white */
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  border-radius: var(--vm-radius-lg);   /* rounded-xl */
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  padding: 0;
  scrollbar-width: thin;
  scrollbar-color: var(--vm-cc-border) transparent;
}

.vm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 580px;
}

.vm-table thead {
  background: var(--vm-cc-canvas); /* bg-slate-50 / bg-gray-50 */
  border-bottom: 1px solid var(--vm-cc-border);
}

.vm-table th {
  padding: 12px 18px;
  text-align: left;
  font-family: var(--vm-font-sans);
  font-weight: 600;
  color: var(--vm-cc-text-muted);
  font-size: 12px;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  border: none;
}

.vm-th-dim {
  width: 18%;
  min-width: 100px;
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
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.vm-table-row {
  border-bottom: 1px solid var(--vm-cc-border);
  transition: background-color 150ms var(--vm-cc-easing);
}

.vm-table-row:last-child {
  border-bottom: none;
}

/* 企业简洁风标准表格行悬停高亮：hover:bg-gray-50 */
.vm-table-row:hover {
  background-color: var(--vm-cc-canvas) !important;
}

.vm-table td {
  padding: 14px 18px;
  text-align: left;
  vertical-align: middle;
  background: transparent;
  color: var(--vm-cc-text-body);
  line-height: 1.6;
  border: none;
}

.vm-dim-badge {
  display: inline-block;
  font-size: 12px;
  font-family: var(--vm-font-sans);
  font-weight: 600;
  color: var(--vm-cc-text-title);
  background: var(--vm-cc-subtle-bg);
  border: 1px solid var(--vm-cc-border);
  padding: 3px 8px;
  border-radius: var(--vm-radius-sm);
}

.vm-td-val {
  font-size: 13px;
  color: var(--vm-cc-text-body);
}

/* ─────────────────────────────────────────────────────────────
   4. 【分层架构】Tree / Layered Architecture (企业简洁风版)
   ───────────────────────────────────────────────────────────── */
.vm-tree-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 4px 2px;
}

.vm-tree-layer-card {
  background: var(--vm-cc-card-bg); /* bg-white */
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  border-radius: var(--vm-radius-lg);   /* rounded-xl (12px) */
  padding: 14px 18px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing),
              box-shadow var(--vm-cc-duration) var(--vm-cc-easing),
              border-color var(--vm-cc-duration) var(--vm-cc-easing);
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
  width: 3px;
  background: var(--layer-accent, var(--vm-cc-blue));
}

.vm-tree-layer-card:hover {
  transform: translateY(-2px); /* hover:-translate-y-0.5 */
  border-color: var(--vm-cc-border-hover);
  box-shadow: var(--vm-cc-shadow-md); /* hover:shadow-md */
}

.vm-tree-layer-card:active {
  transform: scale(0.98) translateY(0);
  box-shadow: var(--vm-cc-shadow-sm);
}

.vm-tree-layer-lead {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  min-width: 120px;
}

.vm-tree-layer-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--layer-accent, var(--vm-cc-blue));
  flex-shrink: 0;
}

.vm-tree-layer-title {
  font-family: var(--vm-font-sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.vm-tree-layer-divider {
  width: 1px;
  height: 20px;
  background: var(--vm-cc-border);
  flex-shrink: 0;
}

.vm-tree-layer-detail {
  font-size: 13px;
  color: var(--vm-cc-text-body);
  line-height: 1.6;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   5. 【量化成效】Stats 关键指标大卡 (企业简洁风版)
   ───────────────────────────────────────────────────────────── */
.vm-stats-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 4px 2px 14px 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--vm-cc-border) transparent;
}

.vm-stat-card {
  flex: 1 1 200px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  background: var(--vm-cc-card-bg); /* bg-white */
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  border-radius: var(--vm-radius-lg);   /* rounded-xl (12px) */
  padding: 18px 20px;
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing),
              box-shadow var(--vm-cc-duration) var(--vm-cc-easing),
              border-color var(--vm-cc-duration) var(--vm-cc-easing);
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
  height: 3px;
  background: var(--stat-accent, var(--vm-cc-blue));
}

.vm-stat-card:hover {
  transform: translateY(-2px); /* hover:-translate-y-0.5 */
  border-color: var(--vm-cc-border-hover);
  box-shadow: var(--vm-cc-shadow-md); /* hover:shadow-md */
}

.vm-stat-card:active {
  transform: scale(0.98) translateY(0);
  box-shadow: var(--vm-cc-shadow-sm);
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
  background: var(--stat-accent, var(--vm-cc-blue));
  flex-shrink: 0;
}

.vm-stat-value {
  font-family: var(--vm-font-sans);
  font-size: 22px;
  font-weight: 700;
  color: var(--stat-accent, var(--vm-cc-blue));
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.25;
}

.vm-stat-label {
  font-size: 12.5px;
  color: var(--vm-cc-text-muted);
  line-height: 1.5;
  flex: 1;
}

/* ─────────────────────────────────────────────────────────────
   6. 【时序图谱】Timeline 时间演进 (企业简洁风版)
   ───────────────────────────────────────────────────────────── */
.vm-timeline-canvas {
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 8px 2px 4px 2px;
}

.vm-timeline-track {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  gap: 16px;
  align-items: stretch;
  padding: 4px 2px 14px 2px;
  scrollbar-width: thin;
  scrollbar-color: var(--vm-cc-border) transparent;
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
  font-family: var(--vm-font-sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--event-accent, var(--vm-cc-blue));
  text-align: center;
  margin-bottom: 10px;
  letter-spacing: 0.01em;
  white-space: nowrap;
  line-height: 1.4;
  user-select: none;
}

.vm-timeline-node {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  margin-bottom: 12px;
}

.vm-timeline-node::before {
  content: "";
  position: absolute;
  top: 50%;
  left: -8px;
  right: -8px;
  height: 2px;
  background: var(--vm-cc-border);
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
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #FFFFFF;
  border: 2px solid var(--event-accent, var(--vm-cc-blue));
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing), box-shadow var(--vm-cc-duration) ease;
}

.vm-timeline-col:hover .vm-timeline-dot {
  transform: scale(1.2);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.20);
}

.vm-timeline-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--vm-cc-card-bg); /* bg-white */
  border-radius: var(--vm-radius-lg); /* rounded-xl (12px) */
  padding: 16px 18px;
  border: 1px solid var(--vm-cc-border); /* border border-gray-200 */
  box-shadow: var(--vm-cc-shadow-sm);   /* shadow-sm */
  transition: transform var(--vm-cc-duration) var(--vm-cc-easing),
              box-shadow var(--vm-cc-duration) var(--vm-cc-easing),
              border-color var(--vm-cc-duration) var(--vm-cc-easing);
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
  height: 3px;
  background: var(--event-accent, var(--vm-cc-blue));
}

.vm-timeline-col:hover .vm-timeline-card {
  transform: translateY(-2px); /* hover:-translate-y-0.5 */
  border-color: var(--vm-cc-border-hover);
  box-shadow: var(--vm-cc-shadow-md); /* hover:shadow-md */
}

.vm-timeline-col:active .vm-timeline-card {
  transform: scale(0.98) translateY(0);
  box-shadow: var(--vm-cc-shadow-sm);
}

.vm-timeline-title {
  font-family: var(--vm-font-sans);
  font-size: 14px;
  font-weight: 600;
  color: var(--vm-cc-text-title);
  line-height: 1.4;
  margin-bottom: 6px;
  letter-spacing: -0.01em;
}

.vm-timeline-detail {
  font-size: 12.5px;
  color: var(--vm-cc-text-body);
  line-height: 1.6;
  margin-top: 4px;
  flex: 1;
  white-space: pre-line;
}

/* ─────────────────────────────────────────────────────────────
   企业简洁风质感滚动条 (Corporate Clean Scrollbar)
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
  background: var(--vm-cc-canvas);
  border-radius: 4px;
}

.vm-master-grid::-webkit-scrollbar-thumb,
.vm-flow-track::-webkit-scrollbar-thumb,
.vm-stats-grid::-webkit-scrollbar-thumb,
.vm-timeline-track::-webkit-scrollbar-thumb,
.vm-table-wrap::-webkit-scrollbar-thumb {
  background: var(--vm-cc-border);
  border-radius: 4px;
  transition: background var(--vm-cc-duration) ease;
}

.vm-master-grid::-webkit-scrollbar-thumb:hover,
.vm-flow-track::-webkit-scrollbar-thumb:hover,
.vm-stats-grid::-webkit-scrollbar-thumb:hover,
.vm-timeline-track::-webkit-scrollbar-thumb:hover,
.vm-table-wrap::-webkit-scrollbar-thumb:hover {
  background: var(--vm-cc-border-hover);
}

/* 响应式精修 */
@media (max-width: 640px) {
  .vm-master-card { padding: 14px 10px; }
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
        f'  <span class="vm-caption-prefix">图表</span>'
        f'  <span class="vm-caption-divider">/</span>'
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
