// ==========================================================================
// AgentFlow Front-end · Constants & Formatting Utilities
// ==========================================================================
"use strict";

// API Base URL (auto-detects local / remote host)
const API = window.location.origin.includes("http")
  ? `${window.location.origin}/api`
  : "http://127.0.0.1:8000/api";

// Task Localization & Domain Metadata
const TASK_META = {
  ocr: { name: "OCR 图片识别", desc: "识别图片文字与公式并转换成标准 Markdown", domain: "notes" },
  library: { name: "知识资料结构化入库", desc: "处理源文档并提取知识点录入知识库", domain: "notes" },
  catalog: { name: "核心知识目录构建", desc: "基于知识库自动生成树状知识大纲", domain: "notes" },
  checklist: { name: "考点复习清单", desc: "提取核心考点、高频重点与复习问答", domain: "notes" },
  quiz: { name: "智能自测题生成", desc: "根据笔记与资料生成单选、多选与思考题", domain: "notes" },
  knowledge_graph: { name: "知识图谱构建", desc: "分析知识实体关联并生成 Graphviz 拓扑", domain: "notes" },
  review: { name: "笔记审查与核校", desc: "检测笔记事实错误、逻辑漏洞与格式问题", domain: "notes" },
  minutes_generation: { name: "会议纪要生成", desc: "多视角（客观/职业）会议精要提炼与跨会话记忆", domain: "meeting" },
  minutes_trace: { name: "纪要事实溯源", desc: "将纪要要点与会议发言原文进行对齐验证", domain: "meeting" },
  risk: { name: "会议风险分析", desc: "识别会议讨论中潜在的风险点与阻碍", domain: "meeting" },
  multi_styles: { name: "多风格纪要", desc: "生成不同详略度与排版的纪要版本", domain: "meeting" },
  action_items: { name: "待办事项提取", desc: "提取责任人、截止时间与行动事项 (TODO)", domain: "meeting" },
  mindmap: { name: "思维导图导出", desc: "提炼核心大纲并导出交互式 Markmap 导图", domain: "meeting" },
  chat: { name: "知识库对话", desc: "基于知识库与会话记忆进行精准问答", domain: "chat" }
};

// Safe lightweight Markdown Renderer
function renderMarkdown(md) {
  if (!md) return "";
  let html = escapeHtml(md);

  // Headers
  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/gim, "<em>$1</em>");

  // Code Blocks
  html = html.replace(/```([\s\S]*?)```/gim, "<pre><code>$1</code></pre>");
  html = html.replace(/`([^`]+)`/gim, "<code>$1</code>");

  // Blockquotes
  html = html.replace(/^\> (.*$)/gim, "<blockquote>$1</blockquote>");

  // Unordered Lists
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");

  // Paragraphs
  html = html.replace(/\n\n/gim, "</p><p>");
  html = `<p>${html}</p>`;
  html = html.replace(/<p><\/p>/gim, "");

  return html;
}

// Safe HTML Escaping
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// File Size Formatter
function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// Relative Timestamp Formatter
function formatRelativeTime(ts) {
  if (!ts) return "";
  const now = Date.now();
  const diff = Math.floor((now - ts) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
