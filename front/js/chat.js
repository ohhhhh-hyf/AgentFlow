// ==========================================================================
// AgentFlow Front-end · Chat, Intent Dispatcher & Parameter Intelligence
// ==========================================================================
"use strict";

// Heuristic keyword matching for context bar before plan is finalized
function heuristicContextVisibility(text) {
  if (!text) return;
  const isMeeting = /会议|纪要|待办|风险|发言|议题|mins|meeting/i.test(text);
  const isNotes = /笔记|学科|复习|目录|清单|自测|入库|知识图谱|ocr|图片/i.test(text);

  if (isMeeting && !isNotes) {
    if (ctxProjectWrap) ctxProjectWrap.classList.remove("hidden-ctx");
    if (ctxSubjectWrap) ctxSubjectWrap.classList.add("hidden-ctx");
  } else if (isNotes && !isMeeting) {
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
    if (ctxProjectWrap) ctxProjectWrap.classList.add("hidden-ctx");
  }
}

// Smart Parameter Extraction
function detectParameters(text) {
  if (!text) return {};
  const res = {};

  // 1. Subject (学科)
  const subMatch = text.match(/(?:建立|创建|整理进|入库到|保存到|我的|学科[：:\s]*)\s*([a-zA-Z0-9_\u4e00-\u9fa5]{2,10}?)(?:知识库|学科|大纲|清单|笔记|资料)/);
  if (subMatch && subMatch[1]) {
    const raw = subMatch[1].trim();
    if (!/知识|复习|考点|考试|备考|会议|图片|照片|待办|导图|风险/.test(raw)) {
      res.subject = raw;
    }
  }
  if (!res.subject) {
    const commonSubjects = [
      "数学", "物理", "化学", "英语", "语文", "计算机", "生物", "地理", "历史", "政治",
      "高等数学", "高数", "线性代数", "线代", "概率论", "数据结构", "操作系统", "计算机网络",
      "微积分", "电磁学", "离散数学", "力学", "热力学", "光学", "近代物理", "宏观经济", "微观经济"
    ];
    for (const sub of commonSubjects) {
      if (text.includes(sub)) {
        res.subject = sub;
        break;
      }
    }
  }

  // 2. Project (会议项目)
  const projMatch = text.match(/(?:关于|项目[：:\s]*)\s*([a-zA-Z0-9_\u4e00-\u9fa5]{2,12}?)(?:的会议|项目|例会)/);
  if (projMatch && projMatch[1]) {
    res.project = projMatch[1].trim();
  }
  if (!res.project) {
    const commonProjects = [
      "晨会", "周会", "月会", "年终总结", "述职会", "复盘会", "敏捷站会", "评审会",
      "例会", "双周会", "董事会", "AgentFlow", "技术分享会", "产品讨论会"
    ];
    for (const proj of commonProjects) {
      if (text.includes(proj)) {
        res.project = proj;
        break;
      }
    }
  }

  // 3. Perspective / Role (用户职业视角)
  if (/产品经理|PM/i.test(text)) {
    res.perspective = "产品经理";
  } else if (/开发人员|程序员|工程师|技术人员|研发|前端|后端|全栈/i.test(text)) {
    res.perspective = "开发人员";
  } else if (/项目经理|PMP|Scrum/i.test(text)) {
    res.perspective = "项目经理";
  } else if (/测试|QA|质量保障/i.test(text)) {
    res.perspective = "测试工程师";
  } else if (/算法|AI算法|机器学习|深度学习/i.test(text)) {
    res.perspective = "算法工程师";
  } else if (/客户经理|业务经理|商务|BD/i.test(text)) {
    res.perspective = "客户经理";
  } else if (/客观全员|全员视角|客观视角/i.test(text)) {
    res.perspective = "客观全员";
  }

  // 4. Chapter (章节)
  const chapMatch = text.match(/(第[一二三四五六七八九十0-9]+[章节]|第[0-9]+节|力学篇|电磁篇|热学篇)/);
  if (chapMatch) {
    res.chapter = chapMatch[1];
  }

  return res;
}

// One-click Apply Detected Parameter to Global Topbar / Task Config
function applyParam(type, value, buttonEl = null) {
  if (!value) return;

  if (type === "subject") {
    if (ctxSubject) {
      ctxSubject.value = value;
      ctxSubject.classList.add("input-highlight-pulse");
      setTimeout(() => ctxSubject.classList.remove("input-highlight-pulse"), 2500);
    }
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
    if (typeof syncContextToPlan === "function") syncContextToPlan();
    if (typeof validatePlanParams === "function") validatePlanParams();
  } else if (type === "project") {
    if (ctxProject) {
      ctxProject.value = value;
      ctxProject.classList.add("input-highlight-pulse");
      setTimeout(() => ctxProject.classList.remove("input-highlight-pulse"), 2500);
    }
    if (ctxProjectWrap) ctxProjectWrap.classList.remove("hidden-ctx");
    if (typeof syncContextToPlan === "function") syncContextToPlan();
    if (typeof validatePlanParams === "function") validatePlanParams();
  } else if (type === "perspective" || type === "role") {
    const ctx = getCtx();
    if (ctx.user_id) {
      fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/profile`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: value }),
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.profile) {
            currentUserContext.profile = d.profile;
            if (typeof updateUserProfilePill === "function") {
              updateUserProfilePill(d.profile);
            }
          }
        })
        .catch(() => {});
    }
  }

  if (buttonEl) {
    buttonEl.remove();
    if (liveParamSuggestions && !liveParamSuggestions.children.length) {
      liveParamSuggestions.classList.add("hidden");
      liveParamSuggestions.innerHTML = "";
    }
  }
}

// Real-time Parameter Suggestion Bar above Input Box
function updateLiveParamSuggestions(text) {
  if (!liveParamSuggestions) return;
  if (!text || !text.trim()) {
    liveParamSuggestions.classList.add("hidden");
    liveParamSuggestions.innerHTML = "";
    return;
  }

  const detected = detectParameters(text);
  const items = [];

  if (detected.subject && ctxSubject && ctxSubject.value !== detected.subject) {
    items.push({
      type: "subject",
      label: `学科: ${detected.subject}`,
      val: detected.subject
    });
  }
  if (detected.project && ctxProject && ctxProject.value !== detected.project) {
    items.push({
      type: "project",
      label: `项目: ${detected.project}`,
      val: detected.project
    });
  }
  if (detected.perspective) {
    const curRole = (currentUserContext && currentUserContext.profile && (currentUserContext.profile.role || currentUserContext.profile.base_template)) || "";
    if (!curRole.includes(detected.perspective) && !detected.perspective.includes(curRole)) {
      items.push({
        type: "perspective",
        label: `切换职业: ${detected.perspective}`,
        val: detected.perspective
      });
    }
  }

  if (items.length) {
    liveParamSuggestions.innerHTML = items
      .map(
        (it) =>
          `<button type="button" class="live-param-chip" data-type="${it.type}" data-val="${escapeHtml(it.val)}">${escapeHtml(it.label)}</button>`
      )
      .join("");
    liveParamSuggestions.classList.remove("hidden");

    liveParamSuggestions.querySelectorAll(".live-param-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const type = btn.getAttribute("data-type");
        const val = btn.getAttribute("data-val");
        applyParam(type, val, btn);
      });
    });
  } else {
    liveParamSuggestions.classList.add("hidden");
    liveParamSuggestions.innerHTML = "";
  }
}

// Helper to create clean Google Studio avatars
function createAvatar(role) {
  const avatar = document.createElement("div");
  avatar.className = `msg-avatar ${role}`;
  if (role === "user") {
    avatar.textContent = "U";
  } else {
    avatar.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12 2C12 7.52 7.52 12 2 12C7.52 12 12 16.48 12 22C12 16.48 16.48 12 22 12C16.48 12 12 7.52 12 2Z"/><path d="M18.5 2.5C18.5 4.71 16.71 6.5 14.5 6.5C16.71 6.5 18.5 8.29 18.5 10.5C18.5 8.29 20.29 6.5 22.5 6.5C20.29 6.5 18.5 4.71 18.5 2.5Z" opacity="0.85"/></svg>`;
  }
  return avatar;
}

// Append Messages in Chat Stream
function appendMessage(role, content) {
  const group = document.createElement("div");
  group.className = `msg-group ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.textContent = content;

  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
  return group;
}

function appendLoadingMessage() {
  const id = `loading-${Date.now()}`;
  const group = document.createElement("div");
  group.id = id;
  group.className = "msg-group bot";

  const senderLine = document.createElement("div");
  senderLine.className = "msg-sender-line";
  senderLine.innerHTML = `
    <div class="msg-avatar bot">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
        <path d="M12 2C12 7.52 7.52 12 2 12C7.52 12 12 16.48 12 22C12 16.48 16.48 12 22 12C16.48 12 12 7.52 12 2Z"/>
      </svg>
    </div>
    <span class="msg-sender-name">AgentFlow</span>
  `;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble-thinking";
  bubble.innerHTML = `
    <div class="thinking-dots">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;

  group.appendChild(senderLine);
  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
  return id;
}

function updateLoadingMessage(id, text, type = "bot") {
  const el = $(id);
  if (!el) return;
  el.className = `msg-group ${type}`;
  const bubble = el.querySelector(".msg-bubble");
  if (bubble) bubble.textContent = text;
}

function removeMessage(id) {
  const el = $(id);
  if (el) el.remove();
}

function appendIntentSummaryMessage(data, userQuery = "") {
  const group = document.createElement("div");
  group.className = "msg-group bot";

  const senderLine = document.createElement("div");
  senderLine.className = "msg-sender-line";
  senderLine.innerHTML = `
    <div class="msg-avatar bot">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
        <path d="M6 17h3l2-4V7H5v6h3zm8 0h3l2-4V7h-6v6h3z"/>
      </svg>
    </div>
    <span class="msg-sender-name">规划 Agent</span>
  `;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble-card";

  const tasks = data.plan || [];
  const execution = data.execution || [[...tasks.map((p) => p.task)]];

  let html = `
    <div class="delivery-card">
      <div class="delivery-header">
        <div class="delivery-check-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="16 9 10 15 7 12"/>
          </svg>
        </div>
        <div class="delivery-header-text">
          <div class="delivery-title">任务规划已就绪</div>
          <div class="delivery-sub">已编排 ${execution.length} 个执行阶段，右侧工作台已就绪。</div>
        </div>
      </div>

      <div class="delivery-inner-card">
        <div class="doc-card-head">
          <span class="doc-type-badge">TABLE</span>
          <span class="doc-card-main-title">全链路任务与依赖状态拆解</span>
        </div>

        <table class="delivery-table">
          <thead>
            <tr>
              <th style="width: 44px;">#</th>
              <th>检查项 / 阶段任务</th>
              <th style="width: 120px; text-align: center; white-space: nowrap;">状态</th>
            </tr>
          </thead>
          <tbody>
            ${tasks
              .map(
                (t, idx) => `
              <tr>
                <td class="col-num">${String(idx + 1).padStart(2, "0")}</td>
                <td class="col-task">${escapeHtml(TASK_META[t.task] ? TASK_META[t.task].name : t.task)}</td>
                <td class="col-status ${idx === 0 ? "status-ready" : "status-queued"}" id="chat-task-status-${t.task}" data-task-status="${t.task}">
                  ${idx === 0 ? "已就绪" : "待执行"}
                </td>
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;

  const detected = detectParameters(userQuery);
  const paramButtons = [];

  if (detected.subject && ctxSubject && ctxSubject.value !== detected.subject) {
    paramButtons.push({
      type: "subject",
      label: `学科: ${detected.subject}`,
      val: detected.subject
    });
  }
  if (detected.project && ctxProject && ctxProject.value !== detected.project) {
    paramButtons.push({
      type: "project",
      label: `项目: ${detected.project}`,
      val: detected.project
    });
  }
  if (detected.perspective) {
    paramButtons.push({
      type: "perspective",
      label: `视角: ${(detected.perspective.split("·")[1] || detected.perspective).trim()}`,
      val: detected.perspective
    });
  }

  if (paramButtons.length) {
    html += `
      <div class="msg-suggestion-card" style="margin-top: 10px;">
        <div class="suggestion-header">参数建议（点击快速应用至全局配置）：</div>
        <div class="suggestion-actions">
          ${paramButtons
            .map(
              (btn) =>
                `<button type="button" class="btn-suggestion-action btn-msg-param-action" data-type="${btn.type}" data-val="${escapeHtml(btn.val)}">${escapeHtml(btn.label)}</button>`
            )
            .join("")}
        </div>
      </div>
    `;
  }

  bubble.innerHTML = html;

  bubble.querySelectorAll(".btn-msg-param-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.getAttribute("data-type");
      const val = btn.getAttribute("data-val");
      applyParam(type, val, btn);
    });
  });

  group.appendChild(senderLine);
  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

function appendChatMessage(data) {
  const group = document.createElement("div");
  group.className = "msg-group bot";

  const senderLine = document.createElement("div");
  senderLine.className = "msg-sender-line";
  senderLine.innerHTML = `
    <div class="msg-avatar bot">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
        <path d="M6 17h3l2-4V7H5v6h3zm8 0h3l2-4V7h-6v6h3z"/>
      </svg>
    </div>
    <span class="msg-sender-name">问答 Agent</span>
  `;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble-card";

  const answer = data.answer || "（未检索到相关内容）";
  let html = `<div class="msg-text-lead">${renderMarkdown(answer)}</div>`;

  if (data.sources && data.sources.length) {
    html += `
      <div class="msg-sources">
        <div class="sources-header">参考资料出处 (${data.sources.length})</div>
        <ul class="sources-list">
          ${data.sources.map((s) => `<li>• ${escapeHtml(s)}</li>`).join("")}
        </ul>
      </div>
    `;
  }

  bubble.innerHTML = html;

  group.appendChild(senderLine);
  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

// Render Studio Subject & Knowledge Base Decision Card
function appendTaskBranchDecisionMessage(originalQuery, detectedSubject, knownSubjects) {
  const group = document.createElement("div");
  group.className = "msg-group bot";

  const senderLine = document.createElement("div");
  senderLine.className = "msg-sender-line";
  senderLine.innerHTML = `
    <div class="msg-avatar bot">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
        <path d="M6 17h3l2-4V7H5v6h3zm8 0h3l2-4V7h-6v6h3z"/>
      </svg>
    </div>
    <span class="msg-sender-name">规划 Agent</span>
  `;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble-card";

  const relevantSubjects = knownSubjects || [];
  const hasDetected = Boolean(detectedSubject && detectedSubject.trim());
  const defaultSub = hasDetected ? detectedSubject.trim() : (ctxSubject ? ctxSubject.value.trim() : "");

  bubble.innerHTML = `
    <div class="delivery-card" id="chat-delivery-card-active">
      <div class="delivery-header">
        <div class="delivery-check-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="16 9 10 15 7 12"/>
          </svg>
        </div>
        <div class="delivery-header-text">
          <div class="delivery-title" style="font-size: 14px; font-weight: 600;">任务规划 · 学科确认</div>
          <div class="delivery-sub" style="font-size: 13px;">请选择知识库已有学科或建立新学科以规划流水线：</div>
        </div>
      </div>

      <div class="branch-decision-body">
        ${
          relevantSubjects.length > 0
            ? `
          <div class="branch-decision-section">
            <div class="branch-section-heading">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
              <span>知识库已有学科：</span>
            </div>
            <div class="branch-subject-card-list">
              ${relevantSubjects
                .map(
                  (s) => `
                <div class="branch-subject-row-item">
                  <div class="branch-subject-pill">
                    <span class="branch-subject-name">${escapeHtml(s.name)}</span>
                    <span class="branch-subject-count">(${s.count || 0}条切块)</span>
                  </div>
                  <button type="button" class="btn-build-pipeline btn-existing-pipeline" data-subject="${escapeHtml(s.name)}">
                    <span>建立流水线 ➔</span>
                  </button>
                </div>
              `
                )
                .join("")}
            </div>
          </div>
        `
            : ""
        }

        <div class="branch-decision-section new-subject-section">
          <div class="branch-section-heading">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
            <span>建立新学科：</span>
          </div>
          <div class="branch-new-subject-form">
            <input type="text" class="custom-subject-input branch-compact-input" id="branch-new-subject-input" value="${escapeHtml(defaultSub && !relevantSubjects.some(s => s.name === defaultSub) ? defaultSub : "")}" placeholder="学科名称 (如 物理 / 高数)" />
            <button type="button" class="btn-build-pipeline" id="btn-branch-new-submit">
              <span>建立流水线 ➔</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;

  // 1. Existing subject: build pipeline
  bubble.querySelectorAll(".btn-existing-pipeline").forEach((btn) => {
    btn.addEventListener("click", () => {
      const selectedSub = btn.getAttribute("data-subject");
      applyParam("subject", selectedSub, btn);

      // 仅展示选中的学科，隐藏新学科输入和其它已有学科
      const newSec = bubble.querySelector(".new-subject-section");
      if (newSec) newSec.style.display = "none";

      const allRowItems = bubble.querySelectorAll(".branch-subject-row-item");
      allRowItems.forEach((row) => {
        if (!row.contains(btn)) {
          row.style.display = "none";
        }
      });

      const subText = bubble.querySelector(".delivery-sub");
      if (subText) subText.innerHTML = `已选择知识库已有学科「<strong>${escapeHtml(selectedSub)}</strong>」：`;

      btn.id = "active-planning-btn";
      btn.disabled = true;
      btn.innerHTML = `<span>正在规划流水线...</span>`;

      const query = `把上传的资料入库到${selectedSub}学科，并生成${selectedSub}考点复习清单与核心知识大纲`;
      handleChatSubmit(query, selectedSub, true);
    });
  });

  // 2. New subject input submit
  const newSubInput = bubble.querySelector("#branch-new-subject-input");
  const btnNewSubmit = bubble.querySelector("#btn-branch-new-submit");
  if (btnNewSubmit && newSubInput) {
    const handleNewSubmit = () => {
      const targetSub = newSubInput.value.trim() || defaultSub || "综合学科";
      applyParam("subject", targetSub);

      const existingSec = bubble.querySelector(".branch-decision-section:not(.new-subject-section)");
      if (existingSec) existingSec.style.display = "none";

      newSubInput.disabled = true;

      const subText = bubble.querySelector(".delivery-sub");
      if (subText) subText.innerHTML = `已选择建立新学科「<strong>${escapeHtml(targetSub)}</strong>」：`;

      btnNewSubmit.id = "active-planning-btn";
      btnNewSubmit.disabled = true;
      btnNewSubmit.innerHTML = `<span>正在规划流水线...</span>`;

      const query = `把上传的资料入库到${targetSub}学科，并生成${targetSub}考点复习清单与核心知识大纲`;
      handleChatSubmit(query, targetSub, true);
    };

    btnNewSubmit.addEventListener("click", handleNewSubmit);
    newSubInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleNewSubmit();
      }
    });
  }

  group.appendChild(senderLine);
  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

// Dispatch User Input & Chat Actions
async function handleChatSubmit(customText = null, customSubject = null, isDirect = false) {
  const text = (customText !== null ? customText : (chatText ? chatText.value : "")).trim();
  if (!text) return;

  if (customSubject && ctxSubject) {
    ctxSubject.value = customSubject;
  }

  // 1. Strict Validation on User ID: show inline light red alert without running logic
  let ctx = getCtx();
  const alertEl = $("user-id-required-alert");
  if (!ctx.user_id) {
    if (alertEl) {
      alertEl.classList.remove("hidden");
    }
    if (ctxUser) {
      ctxUser.classList.add("input-error", "input-highlight-pulse");
      ctxUser.focus();
      setTimeout(() => ctxUser.classList.remove("input-highlight-pulse"), 2500);
    }
    return;
  }
  if (alertEl) {
    alertEl.classList.add("hidden");
  }
  if (ctxUser) ctxUser.classList.remove("input-error");
  try {
    localStorage.setItem("agentflow_user_id", ctx.user_id);
  } catch (e) {}

  // Clear input box
  if (chatText) chatText.value = "";
  if (typeof autoResizeTextarea === "function") autoResizeTextarea();

  // Hide welcome hero & quick prompt cards on first message
  const welcomeEl = $("chat-welcome");
  if (welcomeEl) welcomeEl.remove();
  const quickCardsWrap = $("quick-prompt-cards-wrap");
  if (quickCardsWrap) quickCardsWrap.classList.add("hidden");

  // Append user message
  appendMessage("user", text);
  if (ctx.user_id && activeSessionId) {
    saveSessionMessage(ctx.user_id, activeSessionId, "user", text);
  }

  // 3. Smart Subject & Workflow Branching Interceptor:
  if (ctx.user_id && (!currentUserContext.subjects || !currentUserContext.subjects.length)) {
    await fetchUserContext(ctx.user_id);
  }

  const detectedParams = detectParameters(text);
  const detectedSub = customSubject || detectedParams.subject || ctx.subject || "";
  const knownSubjects = currentUserContext.subjects || [];

  const isDownstreamNotesTask =
    /清单|复习|大纲|目录|自测|出题|图谱|资料/i.test(text) &&
    !/入库|建库|保存进|整理进|识别/i.test(text);

  if (isDownstreamNotesTask && !isDirect) {
    appendTaskBranchDecisionMessage(text, detectedSub, knownSubjects);
    return;
  }

  // Append bot loading state
  const loadingMsgId = appendLoadingMessage();
  if (btnSend) btnSend.disabled = true;

  try {
    ctx = getCtx();
    const res = await fetch(`${API}/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, ...ctx, session_id: activeSessionId }),
    });

    const data = await res.json();

    if (!res.ok) {
      await fallbackToChat(text, loadingMsgId);
      return;
    }

    removeMessage(loadingMsgId);
    appendIntentSummaryMessage(data, text);
    if (typeof renderPlanWorkbench === "function") {
      renderPlanWorkbench(data);
    }

    // 意图解析/任务规划完成，持久化并触发左侧历史会话卡片实时刷新
    if (ctx.user_id && activeSessionId) {
      const taskNames = (data.plan || []).map((t) => (TASK_META[t.task] || {}).name || t.task).join("、");
      saveSessionMessage(ctx.user_id, activeSessionId, "assistant", `已为您规划任务流水线：${taskNames}`);
    }
    loadUserSessions();

    const isRunningTask = taskStatusPill && taskStatusPill.classList.contains("running");
    if (!isRunningTask && typeof switchTab === "function") {
      switchTab("tab-plan");
    }
  } catch (err) {
    updateLoadingMessage(loadingMsgId, `意图解析请求失败：${err.message}`, "err");
  } finally {
    if (btnSend) btnSend.disabled = false;
  }
}
