# -*- coding: utf-8 -*-
'''Gradio 界面主题样式（从 web/app.py 拆出，纯字符串常量）。'''
from __future__ import annotations

CSS = """
/* 宽版工作台：暖灰纸面 + 细边框 + 充足留白 */
:root, .dark, .gradio-container {
  --body-background-fill: #f0eee9 !important;
  --body-text-color: #1c1b19 !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #ddd9d0 !important;
  --block-label-background-fill: transparent !important;
  --block-label-text-color: #4a4842 !important;
  --block-title-text-color: #1c1b19 !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #d4d0c6 !important;
  --input-placeholder-color: #9a968c !important;
  --border-color-primary: #ddd9d0 !important;
  --button-primary-background-fill: #2c2a26 !important;
  --button-primary-background-fill-hover: #1a1916 !important;
  --button-primary-text-color: #faf9f6 !important;
  --button-secondary-background-fill: #ebe8e1 !important;
  --button-secondary-text-color: #1c1b19 !important;
  --neutral-950: #1c1b19 !important;
  --neutral-900: #2c2a26 !important;
  --neutral-800: #4a4842 !important;
  --neutral-700: #6b6860 !important;
  --neutral-600: #9a968c !important;
  --neutral-200: #ddd9d0 !important;
  --neutral-100: #ebe8e1 !important;
  --neutral-50: #f0eee9 !important;
  --primary-500: #2c2a26 !important;
  --primary-600: #1a1916 !important;
  --table-odd-background-fill: #ebe8e1 !important;
  --table-even-background-fill: #f5f3ee !important;
  --link-text-color: #1c1b19 !important;
  --link-text-color-hover: #000000 !important;
  --link-text-color-visited: #2c2a26 !important;
  --link-text-color-active: #000000 !important;
  --body-text-color-subdued: #6b6860 !important;
}
html, body {
  background: #f0eee9 !important;
  overflow-x: hidden !important;
}
.gradio-container {
  max-width: min(1840px, 98vw) !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 10px 20px 24px !important;
  color: #1c1b19 !important;
  font-family: "IBM Plex Sans", "Source Han Sans SC", "Noto Sans SC",
    "PingFang SC", "Microsoft YaHei", system-ui, sans-serif !important;
  overflow-x: hidden !important;
}
#work-row, #col-input, #col-output,
#col-input > *, #col-output > *,
#tpl-box, #tpl-box * {
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}
/* 顶栏：标题左 + 领域开关右，不再叠两排标签 */
#chrome-row {
  align-items: center !important;
  justify-content: space-between !important;
  flex-wrap: nowrap !important;
  gap: 12px 20px !important;
  margin: 0 0 2px !important;
}
#chrome-row > * {
  min-width: 0 !important;
}
#chrome-row > *:first-child {
  flex: 1 1 auto !important;
  width: auto !important;
  max-width: none !important;
}
#chrome-row > #chrome-controls {
  flex: 0 0 auto !important;
  flex-basis: auto !important;
  width: auto !important;
  max-width: none !important;
  display: flex !important;
  align-items: center !important;
  justify-content: flex-end !important;
  gap: 10px !important;
  min-width: 0 !important;
}
#chrome-controls > #domain-switch,
#chrome-controls > #monitor-switch {
  flex: 0 0 auto !important;
  width: auto !important;
}
#app-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin: 0;
  padding: 2px 0;
  border-bottom: none;
  text-align: left;
}
#app-header .brand {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: auto;
}
#app-header h1 {
  margin: 0;
  font-size: 1.18rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: #1c1b19;
  line-height: 1.2;
  text-align: left;
  width: auto;
}
#domain-switch {
  margin: 0 !important;
  padding: 0 !important;
}
#domain-switch .label-wrap,
#domain-switch > label,
#domain-switch span[data-testid="block-info"] {
  display: none !important;
}
#domain-switch .form,
#domain-switch .wrap,
#domain-switch .wrap-inner,
#domain-switch fieldset,
#domain-switch [class*="radio"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#domain-switch .wrap,
#domain-switch .form,
#domain-switch fieldset,
#domain-switch [class*="radio"] {
  display: inline-flex !important;
  flex-wrap: nowrap !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 5px !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 999px !important;
  background: #e8e4db !important;
}
#domain-switch label,
#domain-switch label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 132px !important;
  margin: 0 !important;
  padding: 10px 36px !important;
  border: none !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #6b6860 !important;
  font-size: 1.05rem !important;
  font-weight: 650 !important;
  letter-spacing: 0.08em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: static !important;
  top: auto !important;
}
#domain-switch label:has(input[type="radio"]:checked) {
  background: #2c2a26 !important;
  border: none !important;
  color: #faf9f6 !important;
  font-weight: 700 !important;
}
#domain-switch input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
#monitor-switch {
  margin: 0 !important;
  padding: 0 !important;
}
#monitor-switch .label-wrap,
#monitor-switch > label,
#monitor-switch span[data-testid="block-info"] {
  display: none !important;
}
#monitor-switch .form,
#monitor-switch .wrap,
#monitor-switch .wrap-inner,
#monitor-switch fieldset,
#monitor-switch [class*="radio"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#monitor-switch .wrap,
#monitor-switch .form,
#monitor-switch fieldset,
#monitor-switch [class*="radio"] {
  display: inline-flex !important;
  flex-wrap: nowrap !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 5px !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 999px !important;
  background: #e8e4db !important;
}
#monitor-switch label,
#monitor-switch label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 72px !important;
  margin: 0 !important;
  padding: 10px 22px !important;
  border: none !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #6b6860 !important;
  font-size: 1.05rem !important;
  font-weight: 650 !important;
  letter-spacing: 0.08em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: static !important;
  top: auto !important;
}
#monitor-switch label:has(input[type="radio"]:checked) {
  background: #2c2a26 !important;
  border: none !important;
  color: #faf9f6 !important;
  font-weight: 700 !important;
}
#monitor-switch input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
/* 任务标签 + 轻量操作同一行 */
#nav-row {
  align-items: flex-end !important;
  justify-content: space-between !important;
  gap: 10px 16px !important;
  margin: 0 0 10px !important;
}
#nav-row > div {
  min-width: 0 !important;
}
#nav-tasks {
  flex: 1 1 auto !important;
}
#nav-actions {
  flex: 0 0 auto !important;
  width: auto !important;
  max-width: none !important;
  display: flex !important;
  align-items: center !important;
  justify-content: flex-end !important;
  gap: 8px !important;
  padding: 0 0 6px !important;
}
#nav-actions > div {
  width: auto !important;
  flex: 0 0 auto !important;
}
#task-tabs {
  margin: 0 !important;
  padding: 0 !important;
}
#task-tabs .label-wrap,
#task-tabs > label,
#task-tabs span[data-testid="block-info"] {
  display: none !important;
}
#task-tabs .form,
#task-tabs .wrap,
#task-tabs .wrap-inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#task-tabs .wrap,
#task-tabs .form,
#task-tabs fieldset,
#task-tabs [class*="radio"] {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: flex-end !important;
  gap: 0 !important;
  border: none !important;
  border-bottom: 1px solid #d4d0c6 !important;
  padding: 0 2px !important;
  background: transparent !important;
}
#task-tabs label,
#task-tabs label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 72px !important;
  margin: 0 4px 0 0 !important;
  padding: 7px 14px 8px !important;
  border: 1px solid #d4d0c6 !important;
  border-bottom: none !important;
  border-radius: 8px 8px 0 0 !important;
  background: #e8e4db !important;
  color: #6b6860 !important;
  font-size: 0.86rem !important;
  font-weight: 550 !important;
  letter-spacing: 0.02em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: relative !important;
  top: 1px !important;
}
#task-tabs label:has(input[type="radio"]:checked) {
  background: #faf9f6 !important;
  color: #1c1b19 !important;
  font-weight: 650 !important;
  z-index: 1 !important;
}
#task-tabs input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
#task-brief {
  margin: 0 0 12px !important;
  padding: 0 !important;
}
#task-brief .task-brief {
  padding: 12px 14px;
  background: #ffffff;
  border: 1px solid #e0dcd2;
  border-radius: 6px;
}
#task-brief .task-brief p {
  margin: 0 0 8px;
  font-size: 1.05rem;
  line-height: 1.6;
  color: #1c1b19;
}
#task-brief .task-brief p:last-child {
  margin-bottom: 0;
}
#task-brief .k {
  font-size: 1.05rem;
  font-weight: 700;
  color: #2c2a26;
}
#monitor-panel {
  margin: 0 0 8px !important;
  padding: 0 !important;
}
#monitor-panel .prose,
#monitor-panel > .wrap,
#monitor-panel > div {
  padding: 0 !important;
  margin: 0 !important;
  background: transparent !important;
  border: none !important;
}
.mon-sheet {
  background: #faf8f3;
  border: 1px solid #d8d3c8;
  border-radius: 8px;
  padding: 8px 12px 8px 11px;
  box-shadow: inset 3px 0 0 #2c2a26;
}
.mon-sheet.mon-warn {
  box-shadow: inset 3px 0 0 #8a5a2b;
}
.mon-sheet.mon-bad {
  box-shadow: inset 3px 0 0 #7a2e24;
}
.mon-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
}
.mon-stamp {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  line-height: 1;
  background: #2c2a26;
  color: #faf8f3;
}
.mon-warn .mon-stamp {
  background: #8a5a2b;
}
.mon-bad .mon-stamp {
  background: #7a2e24;
}
.mon-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 14px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.mon-stats li {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.mon-stats strong {
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: 0.98rem;
  font-weight: 650;
  color: #1c1b19;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.mon-stats span {
  font-size: 0.68rem;
  color: #9a968c;
}
.mon-pipe {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: auto;
}
.mon-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 0.7rem;
  color: #4a4842;
  background: #efece4;
  border: 1px solid transparent;
}
.mon-chip-ok {
  background: #ebe7dc;
}
.mon-chip-warn {
  background: #f3ead8;
  color: #6b4a22;
}
.mon-meta {
  flex: 1 1 100%;
  margin: 0;
  font-size: 0.7rem;
  color: #9a968c;
  letter-spacing: 0.02em;
}
.mon-note {
  margin: 6px 0 0;
  font-size: 0.76rem;
  color: #6b4a22;
}
.mon-note.mon-error {
  color: #7a2e24;
}
.mon-io {
  margin: 7px 0 0;
  padding-top: 6px;
  border-top: 1px solid #e6e1d6;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mon-io-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin: 0;
  font-size: 0.74rem;
  color: #3f3d38;
  line-height: 1.3;
}
.mon-io-row em {
  flex: 0 0 3.2em;
  font-style: normal;
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  color: #9a968c;
}
.mon-plain {
  flex: 1 1 12em;
  min-width: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: #3f3d38;
}
.mon-layers {
  margin: 7px 0 0;
  padding-top: 6px;
  border-top: 1px solid #e6e1d6;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.mon-layers-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 14px;
  row-gap: 3px;
}
.mon-layer {
  display: grid;
  grid-template-columns: minmax(4.5em, 7.5em) 1fr auto;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.mon-layer-name {
  font-size: 0.7rem;
  color: #5c5a54;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mon-track {
  display: block;
  height: 3px;
  background: #e6e1d6;
  border-radius: 99px;
  overflow: hidden;
}
.mon-track i {
  display: block;
  height: 100%;
  background: #2c2a26;
  border-radius: 99px;
}
.mon-layer em {
  font-style: normal;
  font-family: "IBM Plex Mono", ui-monospace, Consolas, monospace;
  font-size: 0.68rem;
  color: #9a968c;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
@media (max-width: 720px) {
  .mon-layers-2 {
    grid-template-columns: 1fr;
  }
  .mon-pipe {
    margin-left: 0;
  }
}
#clear-results-btn,
#reset-form-btn {
  min-height: 30px !important;
  width: auto !important;
  min-width: 88px !important;
  padding: 0 12px !important;
  border-radius: 6px !important;
  font-weight: 550 !important;
  font-size: 0.8rem !important;
}
.btn-hint {
  margin: 0 !important;
  padding: 0 4px !important;
  font-size: 0.72rem !important;
  color: #9a968c !important;
  line-height: 1.3 !important;
  text-align: center !important;
  max-width: none !important;
  white-space: nowrap !important;
}
/* 紧跟顶栏两按钮：一行模板说明 */
.tpl-guide {
  margin: 0 0 8px !important;
  padding: 6px 10px !important;
  background: #ffffff;
  border: 1px solid #e0dcd2;
  border-radius: 6px;
  font-size: 0.76rem;
  color: #4a4842;
  line-height: 1.4;
}
.tpl-guide strong {
  color: #1c1b19;
  font-weight: 650;
}
.tpl-guide p {
  margin: 0 !important;
}
/* 主工作区 */
#work-row {
  gap: 10px !important;
  align-items: stretch !important;
}
#col-input, #col-output {
  border: 1px solid #d4d0c6;
  background: #faf9f6;
  border-radius: 8px;
  padding: 10px 12px 12px !important;
  box-shadow: none !important;
}
/* 与任务选项「graph - 知识图谱」同字号 */
.panel-label {
  margin: 0 0 6px;
  padding: 0 0 4px;
  border-bottom: 1px solid #e6e2d8;
  font-size: 0.95rem;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  color: #1c1b19;
  font-family: inherit;
  line-height: 1.4;
}
.panel-label.spaced {
  margin-top: 8px;
}
#run-btn[disabled],
#run-btn:disabled,
button.primary:disabled {
  opacity: 0.65 !important;
  cursor: not-allowed !important;
}
/* 控件 */
.gradio-container .block {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin-bottom: 4px !important;
}
.gradio-container .form,
.gradio-container .wrap,
.gradio-container .wrap-inner,
.gradio-container .secondary-wrap,
.gradio-container .padded,
.gradio-container .block > .wrap {
  background: transparent !important;
}
.gradio-container label,
.gradio-container .label-wrap span,
.gradio-container .block > label,
.gradio-container span[data-testid="block-info"] {
  color: #1c1b19 !important;
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  background: transparent !important;
  line-height: 1.4 !important;
  font-family: inherit !important;
}
.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input:not([type="radio"]):not([type="checkbox"]),
.gradio-container select {
  color: #1c1b19 !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
.gradio-container textarea:focus,
.gradio-container input:focus {
  border-color: #8a867c !important;
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(44, 42, 38, 0.06) !important;
}
.gradio-container .dropdown-arrow,
.gradio-container [class*="container"] > .wrap {
  background: #ffffff !important;
}
.gradio-container .checkbox-label,
.gradio-container .radio-label,
.gradio-container label:has(input[type="radio"]),
.gradio-container label:has(input[type="checkbox"]),
.gradio-container .wrap label {
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  color: #1c1b19 !important;
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  line-height: 1.4 !important;
  box-shadow: none !important;
  transition: border-color 0.12s ease, background 0.12s ease;
}
/* 下拉（领域 meeting - 会议 等）与任务选项同字号 */
.gradio-container .wrap .single-select,
.gradio-container [class*="secondary-wrap"] span,
.gradio-container .dropdown-arrow + div,
.gradio-container input[type="text"],
.gradio-container [role="listbox"],
.gradio-container [role="option"],
.gradio-container [role="listbox"] *,
.gradio-container [role="option"] *,
.gradio-container .wrap.svelte-select-input,
.gradio-container .wrap .token,
.gradio-container .wrap .token > *,
.gradio-container .wrap input,
.gradio-container .secondary-wrap,
.gradio-container .secondary-wrap * {
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  line-height: 1.4 !important;
  color: #1c1b19 !important;
  font-family: inherit !important;
}
.gradio-container .checkbox-label:has(input:checked),
.gradio-container .radio-label:has(input:checked),
.gradio-container label:has(input[type="radio"]:checked),
.gradio-container label:has(input[type="checkbox"]:checked) {
  background: #f3f1eb !important;
  border-color: #8a867c !important;
  color: #1c1b19 !important;
}
.gradio-container input[type="radio"],
.gradio-container input[type="checkbox"] {
  accent-color: #2c2a26 !important;
}
#task-tabs label:has(input[type="radio"]) {
  box-shadow: none !important;
}
#domain-switch label:has(input[type="radio"]) {
  background: transparent !important;
  border: none !important;
  border-radius: 999px !important;
  color: #6b6860 !important;
}
#domain-switch label:has(input[type="radio"]:checked),
#monitor-switch label:has(input[type="radio"]:checked) {
  background: #2c2a26 !important;
  border: none !important;
  color: #faf9f6 !important;
}
#monitor-switch label:has(input[type="radio"]) {
  background: transparent !important;
  border: none !important;
  border-radius: 999px !important;
  color: #6b6860 !important;
}
#task-tabs label:has(input[type="radio"]) {
  background: #e8e4db !important;
  border: 1px solid #d4d0c6 !important;
  border-bottom: none !important;
  border-radius: 8px 8px 0 0 !important;
  color: #6b6860 !important;
}
#task-tabs label:has(input[type="radio"]:checked) {
  background: #faf9f6 !important;
  border-color: #d4d0c6 !important;
  color: #1c1b19 !important;
}
/* 按钮 */
#run-btn,
button.primary,
.primary {
  background: #2c2a26 !important;
  color: #faf9f6 !important;
  border: 1px solid #2c2a26 !important;
  border-radius: 6px !important;
  min-height: 34px !important;
  font-weight: 550 !important;
  letter-spacing: 0.03em !important;
  box-shadow: none !important;
  margin-top: 4px !important;
}
#run-btn:hover,
button.primary:hover {
  background: #1a1916 !important;
}
#clear-results-btn,
#reset-form-btn,
button.secondary {
  background: #ffffff !important;
  color: #1c1b19 !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  min-height: 34px !important;
}
#clear-results-btn:hover,
#reset-form-btn:hover,
button.secondary:hover {
  background: #f3f1eb !important;
  border-color: #8a867c !important;
}
/* 下拉 */
.gradio-container [role="listbox"],
.gradio-container [role="option"] {
  background: #ffffff !important;
  color: #1c1b19 !important;
  border-color: #d4d0c6 !important;
}
.gradio-container [role="option"][aria-selected="true"],
.gradio-container [role="option"]:hover {
  background: #ebe8e1 !important;
  color: #1c1b19 !important;
}
/* 图库 */
.gradio-container .gallery {
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
/* 上传：勿裁切文案；固定 height 容易遮挡，统一用 min-height */
#col-input .block,
#tpl-box .block {
  max-width: 100% !important;
  overflow: visible !important;
}
#col-input .block:has([data-testid="file"]),
#tpl-box .block:has([data-testid="file"]),
#col-input .block:has(.upload-container),
#tpl-box .block:has(.upload-container) {
  overflow: visible !important;
  min-height: 88px !important;
  height: auto !important;
  max-height: none !important;
}
.gradio-container [data-testid="file"],
.gradio-container [data-testid="file"] > .wrap,
.gradio-container [data-testid="file"] .upload-container,
.gradio-container .upload-container,
#col-input .upload-container,
#tpl-box .upload-container,
#tpl-file .upload-container {
  background: #ffffff !important;
  border: 1px dashed #c8c4b8 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  color: #1c1b19 !important;
  min-height: 96px !important;
  height: auto !important;
  max-height: none !important;
  padding: 16px 12px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  overflow: visible !important;
  box-sizing: border-box !important;
}
/* 覆盖 Gradio 可能写入的固定高度 */
.gradio-container [data-testid="file"][style*="height"],
.gradio-container .upload-container[style*="height"] {
  height: auto !important;
  min-height: 96px !important;
  max-height: none !important;
}
.gradio-container .upload-container .wrap,
.gradio-container .upload-container .center,
.gradio-container .upload-container .wrap.center,
.gradio-container .upload-container .wrap.default,
.gradio-container .upload-container .wrap.full,
.gradio-container .upload-container > div {
  min-height: 56px !important;
  max-height: none !important;
  height: auto !important;
  padding: 6px 8px !important;
  margin: 0 !important;
  overflow: visible !important;
  white-space: normal !important;
  text-overflow: clip !important;
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  line-height: 1.45 !important;
}
.gradio-container .upload-container svg,
.gradio-container .upload-container img {
  width: 16px !important;
  height: 16px !important;
  flex-shrink: 0 !important;
  margin: 0 !important;
}
.gradio-container .upload-container span,
.gradio-container .upload-container p,
.gradio-container .upload-container button,
.gradio-container .upload-container label,
.gradio-container .upload-container .or {
  font-size: 0.72rem !important;
  line-height: 1.45 !important;
  margin: 0 !important;
  padding: 0 !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  word-break: keep-all !important;
  max-width: none !important;
  height: auto !important;
  max-height: none !important;
  color: #1c1b19 !important;
  opacity: 1 !important;
  visibility: visible !important;
}
/* 文本框可纵向拉伸；左侧「文本」与右侧「日志」初始同高对齐 */
#col-input textarea,
#log-box textarea,
#compiled-tpl textarea {
  resize: vertical !important;
  overflow: auto !important;
}
#input-text textarea,
#log-box textarea {
  min-height: 20rem !important;
  height: 20rem !important;
  max-height: none !important;
  font-size: 0.9rem !important;
  line-height: 1.45 !important;
  box-sizing: border-box !important;
}
#tpl-box textarea {
  min-height: 6rem !important;
}
.gradio-container .file-preview-holder {
  overflow-x: hidden !important;
  overflow-y: auto !important;
  max-width: 100% !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  margin-top: 4px !important;
}
.gradio-container table.file-preview {
  width: 100% !important;
  max-width: 100% !important;
  table-layout: fixed !important;
  color: #1c1b19 !important;
  margin: 0 !important;
}
.gradio-container tr.file,
.gradio-container table.file-preview tbody > tr,
.gradio-container table.file-preview tbody > tr:nth-child(odd),
.gradio-container table.file-preview tbody > tr:nth-child(even) {
  display: flex !important;
  width: 100% !important;
  max-width: 100% !important;
  background: #f0eee9 !important;
  border-bottom: 1px solid #ddd9d0 !important;
  color: #1c1b19 !important;
}
.gradio-container tr.file:hover {
  background: #e6e2d8 !important;
}
.gradio-container td.filename,
.gradio-container td.filename .stem,
.gradio-container td.filename .ext,
.gradio-container .file-preview-holder span {
  color: #1c1b19 !important;
  opacity: 1 !important;
  font-weight: 500 !important;
}
.gradio-container td.filename {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  overflow: hidden !important;
}
.gradio-container td.filename .stem {
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
.gradio-container td.download {
  flex: 0 0 auto !important;
  min-width: 0 !important;
  width: auto !important;
  max-width: 7rem !important;
  color: #4a4842 !important;
}
.gradio-container td.download a {
  color: #1c1b19 !important;
  text-decoration: none !important;
  font-weight: 500 !important;
}
.gradio-container td.download a:hover {
  text-decoration: underline !important;
  color: #000000 !important;
}
.gradio-container .label-clear-button {
  color: #4a4842 !important;
}
#col-input,
#tpl-box,
#tpl-box > *,
#tpl-box .block {
  overflow-x: hidden !important;
  max-width: 100% !important;
}
#col-input,
#tpl-box,
.gradio-container .file-preview-holder {
  scrollbar-width: thin;
}
#col-input::-webkit-scrollbar:horizontal,
#tpl-box::-webkit-scrollbar:horizontal,
.gradio-container .file-preview-holder::-webkit-scrollbar:horizontal {
  height: 0 !important;
  display: none !important;
}
#tpl-box textarea,
#tpl-box input,
#col-input textarea,
#col-output textarea {
  max-width: 100% !important;
  overflow-x: hidden !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
/* 可编辑模板 */
#compiled-wrap {
  margin-top: 10px;
  padding: 10px 10px 6px;
  border: 1px solid #c8c4b8;
  background: #ffffff;
  border-radius: 8px;
}
#compiled-wrap .step-banner {
  margin: 0 0 8px;
  font-size: 0.78rem;
  color: #4a4842;
  line-height: 1.45;
}
#compiled-wrap .step-banner strong {
  color: #1c1b19;
  font-weight: 650;
}
#compiled-tpl textarea {
  background: #faf9f6 !important;
  border: 1px solid #d4d0c6 !important;
  min-height: 9rem !important;
  color: #1c1b19 !important;
  border-radius: 6px !important;
}
#friendly-template textarea {
  background: #fbfaf7 !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 6px !important;
  color: #1c1b19 !important;
  min-height: 14rem !important;
  line-height: 1.55 !important;
  font-size: 0.9rem !important;
  font-family: inherit !important;
}
#clear-tpl-btn {
  margin-top: 2px !important;
}
/* 下载列表 */
.dl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid #d4d0c6;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}
.dl-item {
  border-bottom: 1px solid #ebe8e1;
}
.dl-item:last-child {
  border-bottom: none;
}
.dl-item a {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 12px 14px;
  text-decoration: none !important;
  color: #1c1b19 !important;
}
.dl-item a:hover {
  background: #f3f1eb;
}
.dl-name {
  font-size: 0.9rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dl-meta {
  flex: 0 0 auto;
  font-size: 0.75rem;
  color: #9a968c;
  font-variant-numeric: tabular-nums;
}
.dl-empty {
  margin: 0;
  padding: 12px 10px;
  border: 1px solid #e6e2d8;
  background: #ffffff;
  color: #9a968c;
  font-size: 0.82rem;
  border-radius: 6px;
  text-align: center;
}
#log-box textarea {
  font-family: "IBM Plex Mono", "Cascadia Mono", "Consolas", monospace !important;
}
/* Markdown 预览区 */
#md-preview {
  margin: 8px 0 10px !important;
  padding: 12px 14px !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  max-height: 28rem !important;
  overflow-y: auto !important;
  font-size: 0.9rem !important;
  line-height: 1.55 !important;
  color: #1c1b19 !important;
}
#md-preview h1, #md-preview h2, #md-preview h3 {
  margin: 0.6em 0 0.35em !important;
  font-weight: 650 !important;
}
#md-preview table {
  border-collapse: collapse !important;
  width: 100% !important;
  font-size: 0.85rem !important;
  margin: 0.5em 0 !important;
}
#md-preview th, #md-preview td {
  border: 1px solid #d4d0c6 !important;
  padding: 4px 8px !important;
}
#md-preview pre, #md-preview code {
  font-size: 0.82rem !important;
}
#memory-review {
  margin: 8px 0 10px !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
}
.lc-standalone-frame {
  display: block;
  width: 100%;
  min-height: 78vh;
  height: 82vh;
  border: 1px solid #d4d0c6;
  border-radius: 8px;
  background: #fff;
}
.memory-review {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid #d4d0c6;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}
.review-heading {
  padding: 12px 16px 8px;
  font-weight: 650;
  color: #1c1b19;
  background: #faf9f6;
  border-bottom: 1px solid #ebe8e1;
}
.review-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 1px minmax(210px, 32%);
  gap: 0;
  border-bottom: 1px solid #ebe8e1;
}
.review-row:last-child {
  border-bottom: none;
}
.review-left {
  padding: 11px 14px;
  line-height: 1.65;
  color: #1c1b19;
  word-break: break-word;
}
.review-rule {
  background: #c8c4b8;
}
.review-right {
  padding: 9px 10px;
  background: #faf9f6;
}
.mem-mark {
  text-decoration: underline;
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
  background: #fff6c7;
  color: #1c1b19;
}
.mem-card {
  display: block;
  padding: 9px 10px;
  border-left: 3px solid #6b6860;
  background: #ffffff;
  color: #1c1b19 !important;
  text-decoration: none !important;
  border-radius: 4px;
}
.mem-card + .mem-card {
  margin-top: 8px;
}
.mem-card-title {
  font-size: 0.82rem;
  font-weight: 650;
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mem-card-meta {
  font-size: 0.74rem;
  color: #6b6860;
  line-height: 1.35;
  margin-bottom: 4px;
}
.mem-card-source {
  font-size: 0.72rem;
  color: #9a968c;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mem-empty {
  min-height: 1px;
}
.review-analysis {
  font-size: 0.8rem;
  color: #3a3832;
  line-height: 1.5;
  margin-top: 4px;
  white-space: pre-wrap;
}
.review-fix {
  font-size: 0.78rem;
  color: #6b6860;
  line-height: 1.45;
  margin-top: 4px;
}
.review-cite {
  font-size: 0.78rem;
  color: #3a3832;
  margin-top: 6px;
  font-weight: 650;
}
.review-excerpt {
  font-size: 0.76rem;
  color: #6b6860;
  margin-top: 4px;
  line-height: 1.45;
}
.quiz-hint {
  font-size: 0.78rem;
  font-weight: 400;
  color: #6b6860;
  margin-top: 4px;
}
.quiz-item {
  padding: 12px 16px;
  border-bottom: 1px solid #ebe8e1;
}
.quiz-item:last-child {
  border-bottom: none;
}
.quiz-q {
  font-weight: 650;
  line-height: 1.55;
  margin-bottom: 6px;
}
.quiz-dim {
  font-size: 0.76rem;
  color: #6b6860;
  margin-bottom: 8px;
}
.quiz-answer summary {
  cursor: pointer;
  color: #3a3832;
  font-size: 0.86rem;
  user-select: none;
}
.quiz-answer ol {
  margin: 8px 0 0 1.2em;
  padding: 0;
  line-height: 1.55;
}
.quiz-empty {
  padding: 14px 16px;
  color: #6b6860;
}
.quiz-section {
  padding: 12px 16px 4px;
  font-weight: 700;
  font-size: 0.92rem;
  color: #2c2a26;
  background: #f7f5f0;
  border-bottom: 1px solid #ebe8e1;
}
.quiz-bank-query {
  padding: 6px 16px 10px;
  font-size: 0.78rem;
  color: #6b6860;
}
.quiz-stem {
  line-height: 1.85;
  margin: 6px 0 8px;
  word-break: keep-all;
  overflow-wrap: anywhere;
}
.quiz-stem p {
  margin: 0 0 0.45em;
  text-indent: 0 !important;
}
.quiz-stem p:last-child {
  margin-bottom: 0;
}
.quiz-stem img.quiz-formula,
.quiz-opts img.quiz-formula,
.quiz-analysis img.quiz-formula,
#memory-review img.quiz-formula {
  display: inline !important;
  vertical-align: middle !important;
  height: 1.45em;
  width: auto !important;
  max-width: none !important;
  max-height: 2.6em;
  margin: 0 1px;
}
.quiz-stem img.quiz-figure,
.quiz-analysis img.quiz-figure {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 8px 0;
}
.quiz-blank {
  display: inline-block;
  min-width: 4em;
  border-bottom: 1px solid #1c1b19;
  line-height: 1;
  margin: 0 0.15em;
}
.quiz-opts {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  line-height: 1.8;
}
.quiz-opts li {
  margin: 4px 0;
}
.quiz-key {
  margin: 8px 0 6px;
  font-weight: 650;
}
.quiz-analysis {
  line-height: 1.55;
}
.quiz-analysis img {
  max-width: 100%;
  height: auto;
}
.quiz-match-hint {
  margin: 4px 2px 2px;
  padding: 8px 10px;
  font-size: 0.8rem;
  line-height: 1.45;
  color: #3a3832;
  background: #f4f1ea;
  border-radius: 8px;
}
.library-hero {
  padding: 28px 20px 22px;
  text-align: center;
  background: #faf9f6;
  border-bottom: 1px solid #ebe8e1;
}
.library-caption {
  margin: 0;
  font-size: 0.86rem;
  color: #6b6860;
}
.library-count {
  margin: 6px 0 0;
  font-size: 0.95rem;
  color: #1c1b19;
}
.library-count strong {
  display: block;
  font-size: 2.6rem;
  font-weight: 650;
  letter-spacing: -0.04em;
  line-height: 1.05;
}
.library-files, .library-items, .library-conflicts, .library-peace {
  padding: 12px 16px 16px;
}
.library-files ul, .library-items ul {
  margin: 0;
  padding-left: 1.2em;
  line-height: 1.6;
}
.library-items span {
  color: #9a968c;
  font-size: 0.78rem;
  margin-left: 8px;
}
.library-verdict {
  margin: 12px 0 0;
  padding: 12px 14px;
  border: 1px solid #ebe8e1;
  border-radius: 8px;
  background: #ffffff;
}
.library-verdict blockquote {
  margin: 8px 0;
  padding-left: 10px;
  border-left: 3px solid #c8c4b8;
  color: #4a4842;
  font-size: 0.86rem;
}
.library-ask {
  margin: 10px 0 8px;
  font-weight: 650;
}
.library-verdict button {
  margin: 0 8px 0 0;
  padding: 6px 12px;
  border: 1px solid #d4d0c6;
  border-radius: 6px;
  background: #faf9f6;
  color: #1c1b19;
  cursor: pointer;
}
.library-verdict button.is-on {
  background: #2c2a26;
  color: #faf9f6;
  border-color: #2c2a26;
}
.library-picked {
  min-height: 1.2em;
  font-size: 0.8rem;
  color: #6b6860;
  margin: 8px 0 0;
}
.library-peace {
  color: #6b6860;
}
@media (max-width: 820px) {
  .review-row {
    grid-template-columns: 1fr;
  }
  .review-rule {
    height: 1px;
  }
}
#img-gallery {
  margin: 0 0 10px !important;
}
@media (max-width: 1100px) {
  .gradio-container {
    max-width: 100% !important;
    padding: 12px 12px 24px !important;
  }
  #col-input, #col-output {
    padding: 10px !important;
  }
}
@media (max-width: 820px) {
  #chrome-row,
  #nav-row {
    flex-wrap: wrap !important;
  }
  #chrome-row > #chrome-controls,
  #chrome-row > #domain-switch,
  #nav-actions {
    width: 100% !important;
  }
  #chrome-controls {
    justify-content: space-between !important;
  }
  #domain-switch .wrap,
  #domain-switch .form,
  #domain-switch fieldset,
  #monitor-switch .wrap,
  #monitor-switch .form,
  #monitor-switch fieldset {
    width: 100% !important;
  }
  #domain-switch label,
  #domain-switch label:has(input[type="radio"]),
  #monitor-switch label,
  #monitor-switch label:has(input[type="radio"]) {
    flex: 1 1 0 !important;
  }
  #nav-actions {
    justify-content: flex-start !important;
    padding-bottom: 0 !important;
  }
  #work-row {
    flex-direction: column !important;
    flex-wrap: nowrap !important;
  }
  #col-input,
  #col-output {
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 auto !important;
  }
}
#ocr-timer {
  position: fixed !important;
  right: 18px !important;
  bottom: 16px !important;
  z-index: 90 !important;
  width: auto !important;
  max-width: 240px !important;
  padding: 0 !important;
  margin: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
#ocr-timer .label-wrap,
#ocr-timer .icon-wrap {
  display: none !important;
}
.ocr-clock {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  pointer-events: none;
  background: rgba(44, 42, 38, 0.92);
  color: #faf9f6;
  border-radius: 8px;
  padding: 8px 12px 7px;
  box-shadow: 0 6px 18px rgba(28, 27, 25, 0.18);
}
.ocr-clock em {
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  color: #c8c4b8;
  font-style: normal;
}
.ocr-clock strong {
  font-size: 1.08rem;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
  line-height: 1.15;
}
.ocr-clock-done {
  background: #2c2a26;
}
"""
