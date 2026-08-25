// AgentFlow front —— 意图识别 → Plan → 上传缺失 → 执行 → 轮询 → 产物
"use strict";

const API = "http://127.0.0.1:8000/api";
const $ = (id) => document.getElementById(id);

const messages = $("messages");
const planBox = $("plan-box");
const planList = $("plan-list");
const planActions = $("plan-actions");
const progressBox = $("progress-box");
const outputBox = $("output-box");
const outputList = $("output-list");

let currentPlan = null;   // {explanation, plan:[...], execution:[...]}
let uploads = [];          // {task, param, file}

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function ctxParams() {
  const p = { user_id: $("ctx-user").value.trim() };
  const subj = $("ctx-subject");
  const proj = $("ctx-project");
  if (subj && !subj.closest(".hidden-ctx")) p.subject = subj.value.trim();
  if (proj && !proj.closest(".hidden-ctx")) p.project = proj.value.trim();
  return p;
}

// 根据 plan 任务集合，动态显示顶部栏字段（meeting→项目，notes→学科）
function updateTopbar(plan) {
  const scalarNeeded = new Set();
  (plan || []).forEach((t) => {
    (t.missing || []).forEach((pm) => { if (pm !== "file" && pm !== "input") scalarNeeded.add(pm); });
    (t.optional || []).forEach((pm) => scalarNeeded.add(pm));
  });
  const showSubject = scalarNeeded.has("subject");
  const showProject = scalarNeeded.has("project");
  const sw = $("ctx-subject-wrap");
  const pw = $("ctx-project-wrap");
  if (sw) sw.classList.toggle("hidden-ctx", !showSubject);
  if (pw) pw.classList.toggle("hidden-ctx", !showProject);
}

// ── 意图识别 ──
async function recognize(text) {
  addMsg("user", text);
  addMsg("bot", "识别中…");
  const res = await fetch(`${API}/intent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, ...ctxParams() }),
  });
  const data = await res.json();
  if (!res.ok) {
    // 识别不出任务（如闲聊/提问）→ 走问答
    messages.lastChild.textContent = "这个问题更像是问答，正在回答…";
    await askChat(text);
    return;
  }
  messages.lastChild.textContent = data.explanation || "已识别任务";
  renderPlan(data);
}

// ── 问答（intent 识别不出任务时的兜底）──
async function askChat(text) {
  const res = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: text, ...ctxParams() }),
  });
  const data = await res.json();
  if (!res.ok) {
    addMsg("err", "问答失败：" + (data.detail || "未知错误"));
    return;
  }
  let answer = data.answer || "（没有回答）";
  if (data.sources && data.sources.length) {
    answer += "\n\n参考来源：\n" + data.sources.map((s) => "· " + s).join("\n");
  }
  addMsg("bot", answer);
}

// ── 渲染 Plan ──
function renderPlan(data) {
  currentPlan = data;
  uploads = [];
  updateTopbar(data.plan || []);
  planList.innerHTML = "";
  (data.plan || []).forEach((item, idx) => {
    const card = document.createElement("div");
    card.className = "task-card";
    // 待补的必填参数（前端维护，填好一项移除一项；执行前校验）
    item._pendingMissing = [...(item.missing || [])];

    const head = document.createElement("div");
    head.className = "task-head";
    head.innerHTML = `<span class="task-name">${idx + 1}. ${item.task}</span>
      <span class="tag-domain">${item.domain}</span>`;
    if ((item.needs || []).length) head.innerHTML +=
      `<span class="tag-dep">依赖: ${item.needs.join(",")}</span>`;
    card.appendChild(head);

    if (item.note) {
      const note = document.createElement("div");
      note.className = "task-note";
      note.textContent = item.note;
      card.appendChild(note);
    }
    const params = item.params || {};
    const hasParams = Object.keys(params).length > 0;
    if (hasParams) {
      const p = document.createElement("div");
      p.className = "task-params";
      p.textContent = "参数: " + JSON.stringify(params);
      card.appendChild(p);
    }

    // 会议纪要：视角选择（默认客观全员，可选职业视角）
    if (item.task === "minutes_generation") {
      renderPerspectiveSelect(item, params, card);
    }

    // 可选标量参数（user_id/project/subject 等）：顶部栏填写，右侧不再给输入框

    (item.missing || []).forEach((param) => {
      const m = document.createElement("div");
      m.className = "task-missing";
      const isUpload = param === "file" || param === "input";
      if (isUpload) {
        m.textContent = `⚠ 缺 ${param} — 请上传`;
        card.appendChild(m);
        const up = document.createElement("div");
        up.className = "task-upload";
        const input = document.createElement("input");
        input.type = "file";
        if (param === "input") input.multiple = true;
        input.addEventListener("change", () => {
          const files = Array.from(input.files || []);
          uploads = uploads.filter((u) => !(u.task === item.task && u.param === param));
          files.forEach((f) => uploads.push({ task: item.task, param, file: f }));
          // 文件名写回 plan 对应任务参数，backend 按文件名映射
          item.params = item.params || {};
          item.params[param] = files.map((f) => f.name);
          item._pendingMissing = (item._pendingMissing || []).filter((x) => x !== param);
          p.textContent = "参数: " + JSON.stringify(item.params);
        });
        up.appendChild(input);
        card.appendChild(up);
      } else {
        // user_id/subject 等标量参数：顶部栏填写，右侧只提示（仍计入必填校验）
        const label = (param === "user_id" || param === "user") ? "用户ID" : param;
        m.textContent = `⚠ 缺 ${param} — 请在上方「${label}」栏填写`;
        card.appendChild(m);
      }
    });
    planList.appendChild(card);
  });

  // 执行按钮
  planActions.innerHTML = "";
  const row = document.createElement("div");
  row.className = "exec-row";
  const btn = document.createElement("button");
  btn.className = "exec-btn";
  btn.textContent = "执行 Plan";
  btn.addEventListener("click", () => executePlan(btn));
  row.appendChild(btn);
  const seq = document.createElement("span");
  seq.className = "task-note";
  seq.textContent = "顺序: " + ((data.execution || []).map((g) => g.join("‖")).join(" → "));
  row.appendChild(seq);
  planActions.appendChild(row);
  planBox.classList.remove("hidden");
  outputBox.classList.add("hidden");
}

// ── 会议纪要视角选择 ──
async function renderPerspectiveSelect(item, params, card) {
  const row = document.createElement("div");
  row.className = "task-upload";
  row.innerHTML = '<span class="task-note">视角</span>';
  const select = document.createElement("select");
  select.innerHTML = '<option value="">加载中…</option>';
  row.appendChild(select);
  card.appendChild(row);
  try {
    const res = await fetch(`${API}/perspectives`);
    const data = await res.json();
    const list = (data.perspectives || []).map((p) => p.label);
    select.innerHTML = "";
    (list.length ? list : ["客观 · 客观全员"]).forEach((label) => {
      const opt = document.createElement("option");
      opt.value = label;
      opt.textContent = label;
      select.appendChild(opt);
    });
    if (params.perspective) select.value = params.perspective;
    select.addEventListener("change", () => {
      item.params = item.params || {};
      if (select.value && select.value !== "客观 · 客观全员") {
        item.params.perspective = select.value;
      } else {
        delete item.params.perspective;
      }
      const p = card.querySelector(".task-params");
      if (p) p.textContent = "参数: " + JSON.stringify(item.params);
    });
  } catch (e) {
    select.innerHTML = '<option value="">客观 · 客观全员</option>';
  }
}

// ── 执行 ──
async function executePlan(btn) {
  if (!currentPlan) return;
  // 必填校验：还有缺失参数的任务不能执行，提示填写
  const pending = (currentPlan.plan || [])
    .map((t) => ({ task: t.task, missing: t._pendingMissing || [] }))
    .filter((t) => t.missing.length);
  if (pending.length) {
    const tip = pending.map((t) => `${t.task} 缺 ${t.missing.join("/")}`).join("；");
    addMsg("err", `还有必填项没填：${tip}。请先在任务卡片上填写/上传后再执行。`);
    return;
  }
  btn.disabled = true;
  // 把顶部栏当前值补进各任务 params（用户可能识别后才填 user_id/学科）
  const ctx = ctxParams();
  (currentPlan.plan || []).forEach((t) => {
    t.params = t.params || {};
    if (ctx.user_id && !t.params.user_id) t.params.user_id = ctx.user_id;
    if (ctx.subject && !t.params.subject) t.params.subject = ctx.subject;
    if (ctx.project && !t.params.project) t.params.project = ctx.project;
  });
  progressBox.classList.remove("hidden");
  outputBox.classList.add("hidden");
  progressBox.innerHTML = '<span class="spin">⟳</span> 提交任务…';

  const fd = new FormData();
  fd.append("plan_json", JSON.stringify(currentPlan));
  uploads.forEach((u) => fd.append("files", u.file, u.file.name));

  let res;
  try {
    res = await fetch(`${API}/tasks`, { method: "POST", body: fd });
  } catch (e) {
    progressBox.textContent = "提交失败：" + e.message;
    btn.disabled = false;
    return;
  }
  const data = await res.json();
  if (!res.ok) {
    progressBox.textContent = "执行失败：" + (data.detail || "未知错误");
    btn.disabled = false;
    return;
  }
  pollTask(data.task_id, btn);
}

function pollTask(taskId, btn) {
  let timer = setInterval(async () => {
    const res = await fetch(`${API}/tasks/${taskId}`);
    if (!res.ok) {
      clearInterval(timer);
      progressBox.textContent = "查询任务状态失败";
      btn.disabled = false;
      return;
    }
    const st = await res.json();
    progressBox.innerHTML =
      `<span class="spin">⟳</span> 状态: ${st.status}${st.current ? " · 当前: " + st.current : ""}<br>` +
      (st.message ? `消息: ${st.message}` : "");
    if (st.status === "done" || st.status === "failed") {
      clearInterval(timer);
      progressBox.textContent = st.status === "done" ? "✅ " + st.message : "❌ " + st.message;
      btn.disabled = false;
      if (st.outputs && st.outputs.length) renderOutputs(taskId, st.outputs);
    }
  }, 1500);
}

function renderOutputs(taskId, outputs) {
  outputList.innerHTML = "";
  let preview = document.getElementById("output-preview");
  if (!preview) {
    preview = document.createElement("div");
    preview.id = "output-preview";
    preview.className = "output-preview";
    outputBox.appendChild(preview);
  }
  preview.innerHTML = "";
  outputs.forEach((path) => {
    const name = path.split(/[\\/]/).pop();
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`;
    a.target = "_blank";
    a.textContent = name;
    a.addEventListener("click", (e) => {
      e.preventDefault();
      previewOutput(taskId, name);
    });
    li.appendChild(a);
    const b = document.createElement("button");
    b.className = "preview-btn";
    b.textContent = "预览";
    b.addEventListener("click", () => previewOutput(taskId, name));
    li.appendChild(b);
    outputList.appendChild(li);
  });
  outputBox.classList.remove("hidden");
}

async function previewOutput(taskId, name) {
  const preview = document.getElementById("output-preview");
  if (!preview) return;
  preview.innerHTML = '<span class="spin">⟳</span> 加载中…';
  const res = await fetch(`${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`);
  if (!res.ok) {
    preview.textContent = "加载失败";
    return;
  }
  const text = await res.text();
  preview.innerHTML = "";
  if (name.endsWith(".html")) {
    // HTML 产物（含会议纪要/目录/清单的完整渲染）用 iframe 展示
    const iframe = document.createElement("iframe");
    iframe.srcdoc = text;
    iframe.className = "preview-iframe";
    preview.appendChild(iframe);
  } else {
    const pre = document.createElement("pre");
    pre.className = "preview-text";
    pre.textContent = text;
    preview.appendChild(pre);
  }
}

// ── 聊天提交 ──
$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("chat-text").value.trim();
  if (!text) return;
  $("chat-text").value = "";
  recognize(text);
});
