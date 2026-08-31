/* AgentFlow 接口调试台：接口 schema + 动态表单 + 请求体拼装 + 响应解析展示 */
"use strict";

/* ============ 固定选项（模板 / 视角） ============ */

const TEMPLATES = [
  ["meeting_minutes_team_meeting", "会议 · 团队例会"], ["meeting_minutes_project_progress", "会议 · 项目进度会"],
  ["meeting_minutes_decision_review", "会议 · 决策评审会"], ["meeting_minutes_workshop_session", "会议 · 工作研讨会"],
  ["meeting_minutes_retrospective_session", "会议 · 总结复盘会"], ["meeting_minutes_exchange_forum", "会议 · 沟通交流会"],
  ["study_notes_class_transcript", "学习 · 课堂记录"], ["study_notes_special_lecture", "学习 · 专题讲座"],
  ["study_notes_group_seminar", "学习 · 小组讨论"], ["study_notes_knowledge_memo", "学习 · 知识笔记"],
  ["study_notes_debate_forum", "学习 · 辩论会"], ["dialogue_interview_research_dialogue", "访谈 · 调研访谈"],
  ["dialogue_interview_interview_transcript", "访谈 · 采访记录"], ["job_interview_hiring_report", "面试 · 面试报告"],
  ["job_interview_interview_debrief", "面试 · 面试复盘"], ["medical_consultation_clinical_advisory", "医疗问诊 · 就医咨询"],
  ["medical_consultation_psychological_session", "医疗问诊 · 心理咨询"], ["legal_consultation_legal_advisory", "法律沟通 · 法律咨询"],
  ["legal_consultation_court_transcript", "法律沟通 · 庭审记录"], ["legal_consultation_contract_vetting", "法律沟通 · 合同审核"],
  ["press_conference_media_briefing", "新闻发布 · 新闻发布"], ["press_conference_product_launch", "新闻发布 · 产品发布"],
  ["press_conference_government_bulletin", "新闻发布 · 政府报告"], ["press_conference_media_qa_session", "新闻发布 · 媒体问答"],
  ["daily_journal_general_minutes", "日常记录 · 通用纪要"], ["daily_journal_personal_memo", "日常记录 · 个人备忘"],
  ["daily_journal_conversation_transcript", "日常记录 · 对话记录"], ["daily_journal_site_visit_tour", "日常记录 · 参观游览"],
  ["daily_journal_home_school_liaison", "日常记录 · 家校沟通"],
];

const PROFILES = [
  ["object", "客观全员（默认）"], ["developer", "开发人员"], ["algorithm_engineer", "算法人员"],
  ["tester", "测试人员"], ["product_manager", "产品经理"], ["project_manager", "项目经理"], ["client_manager", "客户经理"],
];

/* ============ 接口 Schema（字段定义 + 响应说明） ============ */

const GROUPS = [
  {
    name: "meeting", label: "会议域", listId: "list-meeting",
    apis: [
      {
        id: "minutes", domain: "meeting", label: "纪要提取", method: "POST",
        path: "/api/v1/meeting/minutes", download: true,
        desc: "把会议转写文本整理成结构化会议纪要（议题、结论、摘要、待办/风险概述）。",
        fields: [
          { key: "texts.transcript", label: "会议转写文本", type: "textarea", big: true, required: true, hint: "会议记录全文，多段用换行拼接" },
          { key: "extra.template", label: "输出模板", type: "select", options: TEMPLATES, hint: "空 = 不套模板" },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES, hint: "空 = 客观全员" },
          { key: "extra.project", label: "项目 ID", type: "text" },
          { key: "extra.memory", label: "长期记忆", type: "checkbox", hint: "开启后关联/写入跨会话记忆" },
        ],
        response: {
          file: "minutes.html + result.md",
          file_name: "minutes.html",
          text: "会议纪要 Markdown（含议题/结论/摘要等章节）",
          notes: [
            "命中历史记忆时，相关段落会带记忆溯源标注",
            "extra.memory=true 且传 X-User-Id 才关联历史会议",
          ],
        },
      },
      {
        id: "actions", domain: "meeting", label: "待办提取", method: "POST",
        path: "/api/v1/meeting/actions", download: true,
        desc: "抽出带负责人和截止时间的待办清单，只认明确分工。",
        fields: [
          { key: "texts.transcript", label: "会议转写文本", type: "textarea", big: true, required: true },
          { key: "extra.template", label: "输出模板", type: "select", options: TEMPLATES },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES },
        ],
        response: { file: "actions.md", file_name: "actions.md", text: "待办清单 Markdown（任务/负责人/截止时间/优先级/证据）" },
      },
      {
        id: "risks", domain: "meeting", label: "风险识别", method: "POST",
        path: "/api/v1/meeting/risks", download: true,
        desc: "把会上提到的风险抽成条目，标注严重度、责任人与应对提示。",
        fields: [
          { key: "texts.transcript", label: "会议转写文本", type: "textarea", big: true, required: true },
          { key: "extra.template", label: "输出模板", type: "select", options: TEMPLATES },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES },
        ],
        response: { file: "risks.md", file_name: "risks.md", text: "风险清单 Markdown（风险/严重度/责任人/应对）" },
      },
      {
        id: "minutes_styles", domain: "meeting", label: "多样式纪要", method: "POST",
        path: "/api/v1/meeting/minutes_styles", download: true,
        desc: "同一场会按指定组织模式重写纪要（时间线/总分/因果/主体责权/决策时效）。",
        fields: [
          { key: "texts.transcript", label: "会议转写文本", type: "textarea", big: true, required: true },
          { key: "extra.style", label: "组织模式", type: "select", required: true,
            options: [["time", "时间线"], ["logic", "总分结构"], ["causal", "因果"], ["party", "主体责权"], ["urgency", "决策时效"]] },
          { key: "extra.template", label: "输出模板", type: "select", options: TEMPLATES },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES },
          { key: "extra.project", label: "项目 ID", type: "text" },
          { key: "extra.memory", label: "长期记忆", type: "checkbox" },
        ],
        response: { file: "minutes_styles.md", file_name: "minutes_styles.md", text: "按所选模式重写后的纪要 Markdown" },
      },
      {
        id: "minutes_trace", domain: "meeting", label: "溯源纪要", method: "POST",
        path: "/api/v1/meeting/minutes_trace", download: true,
        desc: "生成段落回指会议原文的溯源纪要，叠上用户关键点与笔记。",
        fields: [
          { key: "texts.transcript", label: "会议转写文本", type: "textarea", big: true, required: true },
          { key: "texts.keypoints", label: "用户重点文本", type: "textarea", required: true, hint: "关键点，用于溯源挂钉" },
          { key: "texts.notes", label: "用户笔记文本", type: "textarea", required: true, hint: "笔记，用于溯源挂钉" },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES },
          { key: "extra.project", label: "项目 ID", type: "text" },
        ],
        response: { file: "minutes_trace.md", file_name: "minutes_trace.md", text: "溯源纪要 Markdown（段落带 ###[【关键点】] 溯源钉）" },
      },
    ],
  },
  {
    name: "notes", label: "笔记域", listId: "list-notes",
    apis: [
      {
        id: "graph", domain: "notes", label: "知识图谱", method: "POST",
        path: "/api/v1/notes/graph", download: true,
        desc: "把笔记概念抽成知识图谱（节点带定义/出处/关系），产出学习地图。",
        fields: [
          { key: "docs", label: "笔记文件", type: "docs", required: true, hint: "每行一个文件名（.txt/.md），放在 data/{user_id}/docs/ 下" },
          { key: "extra.subject", label: "学科", type: "text", hint: "中文自动转拼音（物理 → wuli）" },
          { key: "extra.template", label: "输出模板", type: "select", options: TEMPLATES },
          { key: "extra.profile", label: "视角", type: "select", options: PROFILES },
          { key: "extra.project", label: "项目 ID", type: "text" },
          { key: "extra.memory", label: "长期记忆", type: "checkbox", hint: "开启后按学科累积图谱增量" },
        ],
        response: { file: "graph.html（无 md）", file_name: "graph.html", text: "学习地图 Markdown（节点/边/新增标注）" },
      },
      {
        id: "library", domain: "notes", label: "资料入库", method: "POST",
        path: "/api/v1/notes/library", download: false,
        desc: "把图片（OCR）和文档（解析）入库到知识库。",
        fields: [
          { key: "docs", label: "文件/图片", type: "docs", required: true, hint: "每行一个文件名（图片/PDF/PPT/Word），放在 data/{user_id}/docs/ 下" },
          { key: "extra.subject", label: "学科", type: "text", hint: "建议填；中文自动转拼音入库（物理 → wuli）" },
        ],
        response: {
          file: "无落盘产物",
          file_name: "（空串）",
          text: "入库结果文本：入库成功，导入图片N张，文档M份，{subject}新增知识单元 X 个。",
          notes: ["入库失败时返回：入库失败：{失败原因}。", "纯程序化，token 消耗为 0"],
        },
      },
      {
        id: "catalog", domain: "notes", label: "知识目录", method: "POST",
        path: "/api/v1/notes/catalog", download: false,
        desc: "按已入库资料（+ 可选老师重点）生成知识目录。",
        fields: [
          { key: "extra.subject", label: "学科", type: "text", required: true, hint: "必填；中文自动转拼音（物理 → wuli）" },
          { key: "docs", label: "老师重点文件", type: "docs", hint: "可选；每行一个 .txt 文件名，作为老师重点参与生成" },
        ],
        response: {
          file: "目录 JSON（knowledge/catalogs/{学科拼音}/）+ result.md",
          file_name: "最新目录 JSON 文件名（如 20260831_095125_773.json），checklist 的 docs 用它",
          text: "知识目录 Markdown（章 → 主题 → 知识点三级树）",
          notes: ["目录 JSON 历史版本全保留，下次生成以最新为基线增量更新"],
        },
      },
      {
        id: "checklist", domain: "notes", label: "复习清单", method: "POST",
        path: "/api/v1/notes/checklist", download: true,
        desc: "按已有知识目录和知识库（+ 可选老师重点）生成复习清单。",
        fields: [
          { key: "extra.subject", label: "学科", type: "text", required: true, hint: "必填；中文自动转拼音（物理 → wuli）" },
          { key: "docs", label: "目录文件 + 老师重点", type: "docs", required: true,
            hint: "必填至少一个 .json（catalog 文件名）；.txt 为老师重点（可选）" },
        ],
        response: {
          file: "checklist.html + result.md",
          file_name: "checklist.html",
          text: "精简摘要：统计（N 张卡：核心 X · 重点 Y · 简要 Z）+ 卡片列表",
          notes: ["全量 Markdown 落盘 result.md，交互页落盘 checklist.html", "溯源证据来自知识库原文，不编出处"],
        },
      },
    ],
  },
  {
    name: "system", label: "系统", listId: "list-system",
    apis: [
      {
        id: "health", domain: "-", label: "健康检查", method: "GET",
        path: "/api/v1/health", download: false,
        desc: "服务状态 + 任务线清单。",
        fields: [],
        response: { file: "无", file_name: "（无）", text: "status（ok）+ task_lines（meeting/notes 的任务线清单）" },
      },
    ],
  },
];

/* ============ 通用响应字段说明 ============ */

const COMMON_FIELDS = [
  ["code", "业务码，与 HTTP 状态码一致：0=成功，400=参数缺失/非法，404=不存在，500=运行失败"],
  ["message", "成功固定为 success；失败为错误说明"],
  ["request_id", "本次调用追踪 ID（= 请求头 X-Request-Id），产物目录以它为名"],
  ["monitor.token_usage", "本次调用总 token 消耗（纯程序化接口为 0）"],
  ["monitor.cache_hit", "缓存命中 token 数"],
  ["monitor.cost_time", "耗时（秒）"],
  ["data.text", "Markdown 文本（各接口内容见上表）；无文本时为空串"],
  ["data.file_name", "产物文件名（见上表）；无产物为空串"],
];

/* ============ 页面渲染 ============ */

let currentApi = null;
const listEls = {};

function renderList() {
  for (const group of GROUPS) {
    const el = document.getElementById(group.listId);
    listEls[group.listId] = el;
    el.innerHTML = "";
    for (const api of group.apis) {
      const item = document.createElement("div");
      item.className = "api-item";
      item.dataset.id = api.id;
      item.innerHTML = `<span>${api.label}</span><span class="method ${api.method.toLowerCase()}">${api.method}</span>`;
      item.onclick = () => selectApi(api);
      el.appendChild(item);
    }
  }
}

function selectApi(api) {
  currentApi = api;
  for (const group of GROUPS) {
    const el = listEls[group.listId];
    for (const child of el.children) {
      child.classList.toggle("active", child.dataset.id === api.id);
    }
  }
  renderForm();
}

function fieldHtml(field, value) {
  const req = field.required ? '<span class="req">*必填</span>' : "";
  const hint = field.hint ? `<div class="hint">${field.hint}</div>` : "";
  const key = `<span class="key">${field.key}</span>`;
  const val = esc(value || "");
  let input = "";
  if (field.type === "docs") {
    input = `<textarea class="docs-list" data-key="${field.key}" placeholder="每行一个文件名，如：&#10;ocr_20260829_164512.md">${val}</textarea>`;
  } else if (field.type === "textarea") {
    const cls = field.big ? "big" : "";
    input = `<textarea class="${cls}" data-key="${field.key}" placeholder="">${val}</textarea>
        <div class="file-load">
          <input type="text" placeholder="文件名，如 meeting_all.txt" data-load="${field.key}">
          <button type="button" data-load-btn="${field.key}">📂 从文件加载</button>
          <span class="fl-msg" data-load-msg="${field.key}"></span>
        </div>`;
  } else if (field.type === "select") {
    const opts = (field.options || []).map(([v, l]) => `<option value="${v}" ${value === v ? "selected" : ""}>${l}</option>`).join("");
    input = `<select data-key="${field.key}"><option value="">（不选）</option>${opts}</select>`;
  } else if (field.type === "checkbox") {
    input = `<div class="checkbox-row"><input type="checkbox" data-key="${field.key}" ${value ? "checked" : ""}><span>${field.label}</span></div>`;
  } else {
    input = `<input type="text" data-key="${field.key}" value="${val}">`;
  }
  return `
    <div class="field" data-key="${field.key}">
      <label>${field.type === "checkbox" ? "" : field.label + " " + key + " " + req}</label>
      ${input}
      ${hint}
    </div>`;
}

/* 清空当前接口表单：DOM 值与 store 一起清（含之前会话记住的字段） */
function clearForm() {
  const api = currentApi;
  if (!api) return;
  stopLogPoll();
  api.__store = {};
  document.querySelectorAll("#form-area [data-key]").forEach((el) => {
    if (el.type === "checkbox") el.checked = false;
    else if (el.tagName === "SELECT") el.value = "";
    else el.value = "";
  });
  document.getElementById("send-status").innerHTML = "";
  document.getElementById("resp-area").innerHTML = "";
}

function renderForm() {
  const api = currentApi;
  if (!api) return;
  stopLogPoll();
  const area = document.getElementById("form-area");
  const store = (api.__store = api.__store || {});
  const fieldsHtml = api.fields.map((f) => fieldHtml(f, store[f.key])).join("");
  area.innerHTML = `
    <h2>${api.label}</h2>
    <div class="path">${api.method} ${api.path}</div>
    <div class="desc">${api.desc}</div>
    <div class="headers">
      <div class="field"><label>X-User-Id <span class="key">请求头</span></label>
        <input type="text" id="hdr-user" value="1"></div>
      <div class="field"><label>X-Request-Id <span class="key">请求头</span></label>
        <input type="text" id="hdr-req" value="${uuid()}"></div>
    </div>
    ${fieldsHtml}
    <div class="actions">
      <button class="btn btn-primary" id="btn-send">发送请求</button>
      <button class="btn btn-plain" id="btn-clear" title="清空本接口所有已填字段（含记住的历史内容）">清空表单</button>
      <span class="status" id="send-status"></span>
    </div>
    <div class="resp-block" id="resp-area"></div>
  `;
  document.getElementById("btn-send").onclick = sendRequest;
  document.getElementById("btn-clear").onclick = clearForm;
  // 字段值变更记录到 store（切换接口保留）
  area.querySelectorAll("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    el.addEventListener("input", () => {
      store[key] = el.type === "checkbox" ? el.checked : el.value;
      if (el.classList.contains("invalid")) el.classList.remove("invalid");
    });
  });
}

/* ============ 请求体拼装 ============ */

function buildBody(api) {
  const store = api.__store || {};
  const body = {};
  let missing = [];
  for (const field of api.fields) {
    let value = store[field.key];
    let empty;
    if (field.type === "checkbox") {
      if (!value) continue; // false 不写入（默认 false）
      empty = false;
    } else if (field.type === "docs") {
      const items = String(value || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      if (!items.length) {
        if (field.required) missing.push(field.key);
      } else {
        body.docs = items;
      }
      continue;
    } else {
      const v = String(value || "").trim();
      if (!v) empty = true; else empty = false;
    }
    if (empty) {
      if (field.required) missing.push(field.key);
      continue;
    }
    if (field.type === "checkbox") { body.extra = body.extra || {}; body.extra.memory = true; continue; }
    const parts = field.key.split(".");
    if (parts.length === 1) { body[parts[0]] = value; }
    else {
      let obj = body;
      for (let i = 0; i < parts.length - 1; i++) {
        obj[parts[i]] = obj[parts[i]] || {};
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = String(value).trim();
    }
  }
  return { body, missing };
}

function uuid() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/* ============ 发送与响应展示 ============ */

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* 轻量 Markdown 渲染（转义后处理：标题/表格/列表/粗体/行内代码） */
function mdRender(text) {
  const lines = String(text || "").split("\n");
  let html = "";
  let i = 0;
  const flushList = () => { if (listBuf.length) { html += "<ul>" + listBuf.map((x) => `<li>${x}</li>`).join("") + "</ul>"; listBuf = []; } };
  let listBuf = [];
  const inline = (s) => esc(s)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  while (i < lines.length) {
    const line = lines[i];
    const m = line.match(/^(#{1,4})\s+(.*)$/);
    if (m) { flushList(); html += `<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`; i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushList();
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      if (rows.length) {
        const head = rows[0];
        const bodyRows = rows.slice(1).filter((r) => !r.every((c) => /^:?-+:?$/.test(c)));
        html += "<table><thead><tr>" + head.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
        html += bodyRows.map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("");
        html += "</tbody></table>";
      }
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      listBuf.push(inline(line.replace(/^\s*[-*]\s+/, "")));
      i++; continue;
    }
    if (!line.trim()) { flushList(); html += "<br>"; i++; continue; }
    flushList();
    html += `<div>${inline(line)}</div>`;
    i++;
  }
  flushList();
  return html;
}

async function sendRequest() {
  const api = currentApi;
  const btn = document.getElementById("btn-send");
  const status = document.getElementById("send-status");
  btn.disabled = true;
  status.innerHTML = '<span class="loading">请求中…</span>';

  // 提交前先从 DOM 同步字段值到 store（不依赖 input 事件，粘贴/自动填充都能拿到）
  const store = (api.__store = api.__store || {});
  document.querySelectorAll("#form-area [data-key]").forEach((el) => {
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.tagName === "SELECT") {
      store[el.dataset.key] = el.type === "checkbox" ? el.checked : el.value;
    }
  });

  // 校验必填
  const { body, missing } = buildBody(api);
  if (missing.length) {
    btn.disabled = false;
    status.innerHTML = `<span class="err">缺少必填字段：${esc(missing.join("、"))}</span>`;
    document.querySelectorAll("#form-area .field").forEach((f) => {
      const key = f.dataset.key;
      if (missing.includes(key)) f.querySelector("input,textarea,select")?.classList.add("invalid");
    });
    return;
  }

  const user = document.getElementById("hdr-user").value.trim() || "1";
  const reqId = document.getElementById("hdr-req").value.trim() || uuid();
  document.getElementById("hdr-req").value = reqId;
  const t0 = Date.now() / 1000; // 日志窗口起点（提交时刻）
  const headers = { "X-User-Id": user, "X-Request-Id": reqId };
  const init = { method: api.method, headers };
  let url = api.path;
  if (api.method === "POST") {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  const session = startLogPanel(reqId, t0);
  try {
    const resp = await fetch(url, init);
    const raw = await resp.text();
    let data = null;
    try { data = JSON.parse(raw); } catch (e) { data = null; }
    await finishLogPanel(session, reqId, t0);
    renderResult(data, raw, api, user, reqId);
    status.innerHTML = `<span class="${resp.ok ? "ok" : "err"}">HTTP ${resp.status}${data && data.code !== undefined ? " · code " + data.code : ""}</span>`;
  } catch (err) {
    await finishLogPanel(session, reqId, t0);
    const result = document.getElementById("resp-result");
    if (result) result.innerHTML = `<h3>请求失败</h3><div class="json-view">${esc(err.message)}</div>`;
    status.innerHTML = `<span class="err">请求失败：${esc(err.message)}</span>`;
  } finally {
    btn.disabled = false;
  }
}

/* 拉取该请求的后端日志（提交时刻 t0 之后的窗口） */
async function fetchLogs(reqId, t0) {
  try {
    const resp = await fetch(`/api/v1/logs?request_id=${encodeURIComponent(reqId)}&after=${t0}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.logs || [];
  } catch (e) {
    return null;
  }
}

let logSession = 0;
let logTimer = null;
let logBusy = false;

function stopLogPoll() {
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  logBusy = false;
  logSession += 1;
}

function logLinesHtml(logs) {
  return logs.map((l) =>
    `<span class="lv">${esc(l.time)}</span><span class="${esc(l.level)}">${esc(l.level)}</span> ${esc(l.message)}`
  ).join("\n");
}

function paintLogs(el, logs, waiting) {
  if (!el) return;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  if (!logs) {
    el.innerHTML = '<span class="log-empty-inline">日志接口不可用</span>';
    return;
  }
  if (!logs.length) {
    el.innerHTML = waiting
      ? '<span class="log-empty-inline">（等待后端日志…）</span>'
      : '<span class="log-empty-inline">（本次请求无后端日志）</span>';
    return;
  }
  el.innerHTML = logLinesHtml(logs);
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function startLogPanel(reqId, t0) {
  stopLogPoll();
  const session = logSession;
  const area = document.getElementById("resp-area");
  area.innerHTML = `
    <h3>后端运行日志 <span class="log-live-flag" id="log-live-flag">实时拉取中…</span></h3>
    <div class="log-view" id="log-live"><span class="log-empty-inline">（等待后端日志…）</span></div>
    <div id="resp-result"></div>
  `;
  const tick = async () => {
    if (session !== logSession || logBusy) return;
    logBusy = true;
    try {
      const logs = await fetchLogs(reqId, t0);
      if (session !== logSession) return;
      paintLogs(document.getElementById("log-live"), logs, true);
    } finally {
      if (session === logSession) logBusy = false;
    }
  };
  tick();
  logTimer = setInterval(tick, 700);
  return session;
}

async function finishLogPanel(session, reqId, t0) {
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
  if (session !== logSession) return;
  const logs = await fetchLogs(reqId, t0);
  if (session !== logSession) return;
  paintLogs(document.getElementById("log-live"), logs, false);
  const flag = document.getElementById("log-live-flag");
  if (flag) flag.remove();
}

function renderResult(data, raw, api, user, reqId) {
  const result = document.getElementById("resp-result");
  if (!result) return;
  try {
    result.innerHTML = buildResultHtml(data, raw, api, user, reqId);
  } catch (e) {
    result.innerHTML = `<h3>响应解析失败：${esc(e.message)}</h3><div class="json-view">${esc(raw)}</div>`;
  }
}

function buildResultHtml(data, raw, api, user, reqId) {
  if (!data) {
    return `<h3>响应</h3><div class="json-view">${esc(raw)}</div>`;
  }
  const text = (data.data && data.data.text) || "";
  const file = (data.data && data.data.file_name) || "";

  let dl = "";
  if (api.download && file && data.code === 0) {
    dl = `<a class="dl-btn" href="#" onclick="downloadFile(event, '${api.domain}', '${api.id}', '${esc(user)}', '${esc(reqId)}', '${esc(file)}')">⬇ 下载 ${esc(file)}</a>`;
  }

  const r = api.response || {};
  const respTable = `
    <table>
      <tbody>
        <tr><th>产物文件</th><td>${esc(r.file || "—")}</td></tr>
        <tr><th>file_name</th><td>${esc(file || "（空串）")} ${dl}</td></tr>
        <tr><th>data.text</th><td>${esc(r.text || "Markdown 文本")}</td></tr>
        ${(r.notes || []).map((n) => `<tr><th>说明</th><td>${esc(n)}</td></tr>`).join("")}
      </tbody>
    </table>`;

  return `
    <h3>响应字段说明</h3>
    <div class="json-view" style="max-height:220px;">${respTable}</div>
    <h3>data.text 内容</h3>
    <div class="text-out">${text ? mdRender(text) : "（空）"}</div>
    <h3>原始 JSON <span class="hint" style="cursor:pointer" onclick="this.parentElement.nextElementSibling.style.display=this.parentElement.nextElementSibling.style.display==='none'?'block':'none'">（点击折叠/展开）</span></h3>
    <div class="json-view" id="raw-json">${esc(JSON.stringify(data, null, 2))}</div>
  `;
}

/* 带 X-User-Id 头的下载（fetch blob → 保存） */
async function downloadFile(ev, domain, task, user, reqId, fileName) {
  ev.preventDefault();
  const url = `/api/v1/${domain}/${task}/file/${encodeURIComponent(reqId)}/${encodeURIComponent(fileName)}`;
  try {
    const resp = await fetch(url, { headers: { "X-User-Id": user } });
    if (!resp.ok) { alert("下载失败：HTTP " + resp.status); return; }
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  } catch (err) {
    alert("下载失败：" + err.message);
  }
}

/* ============ 初始化 ============ */
renderList();
selectApi(GROUPS[0].apis[0]);
