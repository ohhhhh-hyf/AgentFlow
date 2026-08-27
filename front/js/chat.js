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
    if (typeof updateDomainBadge === "function") updateDomainBadge("会议域");
  } else if (isNotes && !isMeeting) {
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
    if (ctxProjectWrap) ctxProjectWrap.classList.add("hidden-ctx");
    if (typeof updateDomainBadge === "function") updateDomainBadge("笔记域");
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
  if (/测试人员|做测试|测试工程师|测试开发|测开|自动化测试|性能测试|软件测试|质量保障|测试组|测试同学|QA\b/i.test(text)) {
    res.perspective = "测试工程师";
  } else if (/算法工程师|做算法|AI算法|机器学习|深度学习|大模型|大模型算法|NLP|CV|算法研究员|模型工程师/i.test(text)) {
    res.perspective = "算法工程师";
  } else if (/产品经理|做产品|产品策划|产品总监|需求分析|产品专家|产品顾问|PM\b/i.test(text)) {
    res.perspective = "产品经理";
  } else if (/项目经理|做项目|项目管理|PMP\b|Scrum|敏捷教练|项目总监|项目主管|项目推进/i.test(text)) {
    res.perspective = "项目经理";
  } else if (/客户经理|商务经理|客户管理|做商务|做销售|客户代表|商务代表|BD\b|大客户/i.test(text)) {
    res.perspective = "客户经理";
  } else if (/开发人员|做开发|做研发|研发人员|做技术|程序员|码农|前端开发|后端开发|全栈开发|软件工程师|架构师|技术人员|写代码|前端|后端|全栈|开发工程师|研发工程师|开发\b/i.test(text)) {
    res.perspective = "开发人员";
  } else if (/客观全员|全员视角|客观视角|通用视角/i.test(text)) {
    res.perspective = "客观全员";
  }

  // 4. Chapter (章节)
  const chapMatch = text.match(/(第[一二三四五六七八九十0-9]+[章节]|第[0-9]+节|力学篇|电磁篇|热学篇)/);
  if (chapMatch) {
    res.chapter = chapMatch[1];
  }

  return res;
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

function appendIntentSummaryMessage(data, userQuery = "", replaceTargetElement = null) {
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

  const detected = detectParameters(userQuery);
  let suggestionHtml = "";
  if (detected.perspective) {
    const roleLabel = (detected.perspective.split("·")[1] || detected.perspective).trim();
    suggestionHtml = `
      <div class="msg-suggestion-card">
        <span class="suggestion-header">识别到职业信息，点击应用：</span>
        <div class="suggestion-actions">
          <button type="button" class="btn-suggestion-action btn-msg-param-action" data-type="perspective" data-val="${escapeHtml(detected.perspective)}">视角: ${escapeHtml(roleLabel)}</button>
        </div>
      </div>
    `;
  }

  const html = suggestionHtml + `
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

  bubble.innerHTML = html;

  bubble.querySelectorAll(".btn-msg-param-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      const val = btn.getAttribute("data-val");
      const ctx = typeof getCtx === "function" ? getCtx() : { user_id: ctxUser ? ctxUser.value.trim() : "" };
      if (ctx.user_id) {
        fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/profile`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role: val }),
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
      btn.classList.add("applied");
      btn.textContent = `已应用 视角: ${val}`;
      btn.disabled = true;
    });
  });

  group.appendChild(senderLine);
  group.appendChild(bubble);

  if (replaceTargetElement && replaceTargetElement.parentNode) {
    replaceTargetElement.replaceWith(group);
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  } else if (messagesContainer) {
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
      if (subText) subText.innerHTML = `已选择知识库已有学科「<strong>${escapeHtml(selectedSub)}</strong>」，正在为您编排流水线...`;

      btn.id = "active-planning-btn";
      btn.disabled = true;
      btn.innerHTML = `<span>正在规划流水线...</span>`;

      // 通用构造：基于选中的学科和用户的原始需求
      const cleanOriginal = (originalQuery || "").trim();
      const query = cleanOriginal ? `基于${selectedSub}学科，${cleanOriginal}` : `基于${selectedSub}学科生成核心知识大纲与复习清单`;
      handleChatSubmit(query, selectedSub, true, group, true);
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
      if (subText) subText.innerHTML = `已选择建立新学科「<strong>${escapeHtml(targetSub)}</strong>」，正在为您编排流水线...`;

      btnNewSubmit.id = "active-planning-btn";
      btnNewSubmit.disabled = true;
      btnNewSubmit.innerHTML = `<span>正在规划流水线...</span>`;

      // 通用构造：入库到新学科并完成用户的原始需求
      const cleanOriginal = (originalQuery || "").trim();
      const query = cleanOriginal ? `把上传的资料入库到${targetSub}学科，并${cleanOriginal}` : `把上传的资料入库到${targetSub}学科，并生成核心知识大纲与复习清单`;
      handleChatSubmit(query, targetSub, true, group, true);
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

// Render Interactive Meeting Role & Persona Decision Card
function appendMeetingRoleDecisionMessage(originalQuery) {
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

  bubble.innerHTML = `
    <div class="delivery-card" id="chat-role-decision-card-active">
      <div class="delivery-header">
        <div class="delivery-check-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4M12 16h.01"/>
          </svg>
        </div>
        <div class="delivery-header-text">
          <div class="delivery-title" style="font-size: 14px; font-weight: 600;">会议任务 · 职业视角关联</div>
          <div class="delivery-sub" style="font-size: 13px; display: none;"></div>
        </div>
      </div>

      <div class="role-decision-body">
        <!-- 两个淡蓝色背景主操作按钮 -->
        <div class="role-decision-btn-row">
          <button type="button" class="btn-role-action btn-toggle-preset-role" id="btn-toggle-preset-role">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            <span>内置视角 ▾</span>
          </button>

          <button type="button" class="btn-role-action btn-toggle-custom-role" id="btn-toggle-custom-role">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            <span>新建视角 ▾</span>
          </button>

          <button type="button" class="btn-role-action btn-skip-objective" id="btn-skip-objective" title="使用默认客观视角直接建立流水线">
            <span>默认客观视角 ➔</span>
          </button>
        </div>

        <!-- 面板 1：选择已有职业面板 (点击展开) -->
        <div class="role-sub-panel preset-roles-panel hidden" id="preset-roles-panel">
          <div class="preset-role-chips-grid">
            <button type="button" class="btn-preset-role-chip" data-role="developer" data-name="开发人员">
              <strong>开发人员</strong>
              <span>(技术实现/架构/排期)</span>
            </button>
            <button type="button" class="btn-preset-role-chip" data-role="tester" data-name="测试工程师">
              <strong>测试工程师</strong>
              <span>(质量保障/用例/风险)</span>
            </button>
            <button type="button" class="btn-preset-role-chip" data-role="product_manager" data-name="产品经理">
              <strong>产品经理</strong>
              <span>(需求边界/验收/规划)</span>
            </button>
            <button type="button" class="btn-preset-role-chip" data-role="project_manager" data-name="项目经理">
              <strong>项目经理</strong>
              <span>(里程碑/依赖/推进)</span>
            </button>
            <button type="button" class="btn-preset-role-chip" data-role="algorithm_engineer" data-name="算法工程师">
              <strong>算法工程师</strong>
              <span>(模型/调优/算力评估)</span>
            </button>
            <button type="button" class="btn-preset-role-chip" data-role="client_manager" data-name="客户经理">
              <strong>客户经理</strong>
              <span>(商业诉求/合同/商务)</span>
            </button>
          </div>
        </div>

        <!-- 面板 2：自定义新职业表单 (点击展开) -->
        <div class="role-sub-panel custom-role-panel hidden" id="custom-role-panel">
          <div class="custom-role-form-grid">
            <div class="custom-form-field">
              <label>职业名称 <span style="color:#d32f2f;">*</span></label>
              <input type="text" class="custom-input" id="custom-role-name-input" placeholder="如：运维工程师 / 安全专家 / HRBP" />
            </div>
            <div class="custom-form-field">
              <label>所属部门</label>
              <input type="text" class="custom-input" id="custom-role-dept-input" placeholder="如：技术运营部 / 业务协同部" />
            </div>
            <div class="custom-form-field full-width">
              <label>关注重点 / 做事风格</label>
              <input type="text" class="custom-input" id="custom-role-style-input" placeholder="如：注重服务高可用、部署发布、应急排期与稳定性" />
            </div>
            <div class="custom-form-actions full-width">
              <button type="button" class="btn-submit-custom-role" id="btn-submit-custom-role">
                <span>保存</span>
              </button>
              <span class="custom-role-status" id="custom-role-status"></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  const presetBtn = bubble.querySelector("#btn-toggle-preset-role");
  const customBtn = bubble.querySelector("#btn-toggle-custom-role");
  const skipBtn = bubble.querySelector("#btn-skip-objective");
  const presetPanel = bubble.querySelector("#preset-roles-panel");
  const customPanel = bubble.querySelector("#custom-role-panel");
  const subText = bubble.querySelector(".delivery-sub");

  if (presetBtn && presetPanel) {
    presetBtn.addEventListener("click", () => {
      presetPanel.classList.toggle("hidden");
      if (customPanel) customPanel.classList.add("hidden");
    });
  }

  if (customBtn && customPanel) {
    customBtn.addEventListener("click", () => {
      customPanel.classList.toggle("hidden");
      if (presetPanel) presetPanel.classList.add("hidden");
    });
  }

  // 1. 选择已有职业
  bubble.querySelectorAll(".btn-preset-role-chip").forEach((chip) => {
    chip.addEventListener("click", async () => {
      const targetRole = chip.getAttribute("data-role");
      const targetName = chip.getAttribute("data-name");
      const ctxNow = getCtx();

      chip.disabled = true;
      if (subText) {
        subText.style.display = "block";
        subText.innerHTML = `已选择关联职业「<strong>${escapeHtml(targetName)}</strong>」，正在写入画像并编排流水线...`;
      }

      if (ctxNow.user_id) {
        try {
          const res = await fetch(`${API}/user/${encodeURIComponent(ctxNow.user_id)}/profile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ role: targetRole }),
          });
          if (res.ok) {
            const d = await res.json();
            if (d.profile) {
              currentUserContext.profile = d.profile;
              if (typeof updateUserProfilePill === "function") {
                updateUserProfilePill(d.profile);
              }
            }
          }
        } catch (err) {
          console.warn("Failed to update profile:", err);
        }
      }

      handleChatSubmit(originalQuery, null, true, group, true);
    });
  });

  // 2. 提交自定义新职业
  const btnSubmitCustom = bubble.querySelector("#btn-submit-custom-role");
  const inputRoleName = bubble.querySelector("#custom-role-name-input");
  const inputDept = bubble.querySelector("#custom-role-dept-input");
  const inputStyle = bubble.querySelector("#custom-role-style-input");
  const customStatus = bubble.querySelector("#custom-role-status");

  if (btnSubmitCustom && inputRoleName) {
    btnSubmitCustom.addEventListener("click", async () => {
      const roleName = inputRoleName.value.trim();
      if (!roleName) {
        if (customStatus) {
          customStatus.style.color = "#d32f2f";
          customStatus.textContent = "请先输入职业名称";
        }
        inputRoleName.focus();
        return;
      }

      const dept = inputDept ? inputDept.value.trim() : "";
      const style = inputStyle ? inputStyle.value.trim() : "";
      const ctxNow = getCtx();

      btnSubmitCustom.disabled = true;
      if (customStatus) {
        customStatus.style.color = "var(--ink-700)";
        customStatus.textContent = "正在保存至 user/profile/role.json...";
      }

      if (ctxNow.user_id) {
        try {
          const res = await fetch(`${API}/user/${encodeURIComponent(ctxNow.user_id)}/custom_role`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              role_name: roleName,
              department: dept,
              output_style: style,
              traits: style ? { "做事风格": style } : {},
            }),
          });
          if (res.ok) {
            const d = await res.json();
            if (d.profile) {
              currentUserContext.profile = d.profile;
              if (typeof updateUserProfilePill === "function") {
                updateUserProfilePill(d.profile);
              }
            }
            if (subText) {
              subText.style.display = "block";
              subText.innerHTML = `已创建并关联自定义职业「<strong>${escapeHtml(roleName)}</strong>」，正在为您编排流水线...`;
            }
            handleChatSubmit(originalQuery, null, true, group, true);
            return;
          }
        } catch (err) {
          console.warn("Failed to create custom role:", err);
        }
      }

      handleChatSubmit(originalQuery, null, true, group, true);
    });
  }

  // 3. 跳过并使用默认客观视角
  if (skipBtn) {
    skipBtn.addEventListener("click", () => {
      if (subText) {
        subText.style.display = "block";
        subText.innerHTML = `已选择「默认客观视角」，正在为您编排流水线...`;
      }
      handleChatSubmit(originalQuery, null, true, group, true);
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
async function handleChatSubmit(
  customText = null,
  customSubject = null,
  isDirect = false,
  replaceTargetElement = null,
  hideUserEcho = false
) {
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

  // Append user message (only if not hidden / not a background direct planning submission)
  if (!hideUserEcho) {
    appendMessage("user", text);
    if (ctx.user_id && activeSessionId) {
      saveSessionMessage(ctx.user_id, activeSessionId, "user", text);
    }
  }

  // 3. Smart Subject & Workflow Branching Interceptor:
  if (ctx.user_id && (!currentUserContext.subjects || !currentUserContext.subjects.length || !currentUserContext.profile)) {
    await fetchUserContext(ctx.user_id);
  }

  const detectedParams = detectParameters(text);
  const detectedSub = customSubject || detectedParams.subject || ctx.subject || "";
  const knownSubjects = currentUserContext.subjects || [];

  const isDownstreamNotesTask =
    /清单|复习|大纲|目录|自测|出题|图谱|资料/i.test(text) &&
    !/入库|建库|保存进|整理进|识别/i.test(text);

  if (isDownstreamNotesTask && !isDirect) {
    if (typeof updateDomainBadge === "function") updateDomainBadge("笔记域");
    appendTaskBranchDecisionMessage(text, detectedSub, knownSubjects);
    return;
  }

  // 4. Meeting Domain Role Association Interceptor:
  const curProf = (currentUserContext && currentUserContext.profile) || {};
  const curBaseTpl = (curProf.base_template || "").trim().toLowerCase();
  const curRole = (curProf.role || "").trim();
  const hasSpecificRole =
    curBaseTpl &&
    curBaseTpl !== "object" &&
    curRole &&
    curRole !== "客观全员" &&
    curRole !== "客观" &&
    !curRole.includes("客观");

  const isMeetingTask = /会议|纪要|例会|讨论|待办|复盘|站会|周会|月会|述职|评审|沟通|访谈/i.test(text);

  if (isMeetingTask && !hasSpecificRole && !detectedParams.perspective && !isDirect) {
    if (typeof updateDomainBadge === "function") updateDomainBadge("会议域");
    appendMeetingRoleDecisionMessage(text);
    return;
  }

  // Append bot loading state (if not replacing an existing decision element)
  let loadingMsgId = null;
  if (!replaceTargetElement) {
    loadingMsgId = appendLoadingMessage();
  }
  if (btnSend) btnSend.disabled = true;

  try {
    ctx = getCtx();
    const res = await fetch(`${API}/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        ...ctx,
        session_id: activeSessionId,
        hide_history: Boolean(hideUserEcho)
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      if (replaceTargetElement) {
        replaceTargetElement.remove();
      }
      await fallbackToChat(text, loadingMsgId);
      return;
    }

    if (data.profile) {
      currentUserContext.profile = data.profile;
      if (typeof updateUserProfilePill === "function") {
        updateUserProfilePill(data.profile);
      }
    }

    if (typeof updateDomainBadge === "function") {
      updateDomainBadge(data);
    }

    if (loadingMsgId) {
      removeMessage(loadingMsgId);
    }
    appendIntentSummaryMessage(data, text, replaceTargetElement);
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
    if (loadingMsgId) {
      updateLoadingMessage(loadingMsgId, `意图解析请求失败：${err.message}`, "err");
    } else if (replaceTargetElement) {
      const bubble = replaceTargetElement.querySelector(".msg-bubble-card");
      if (bubble) {
        bubble.innerHTML = `<div class="delivery-card" style="border-color:#ef4444;"><div style="color:#dc2626; padding:12px;">意图解析请求失败：${escapeHtml(err.message)}</div></div>`;
      }
    }
  } finally {
    if (btnSend) btnSend.disabled = false;
  }
}

/**
 * 确认用户身份后在对话框中展示已识别的画像与记忆概况
 */
function appendUserIdentityConfirmedMessage(userId, profile = {}, subjects = []) {
  const welcomeEl = $("chat-welcome");
  if (welcomeEl) welcomeEl.remove();

  const group = document.createElement("div");
  group.className = "msg-group bot";

  const senderLine = document.createElement("div");
  senderLine.className = "msg-sender-line";
  senderLine.innerHTML = `
    <div class="msg-avatar bot">
      <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z"/>
      </svg>
    </div>
    <span class="msg-sender-name">用户记忆 Agent</span>
  `;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble-card";

  const roleName = profile.role || "客观全员";
  const subCount = subjects.length;
  const subNames = subCount > 0 ? subjects.map((s) => s.name || s).join("、") : "暂未入库学科";

  bubble.innerHTML = `
    <div class="delivery-card">
      <div class="delivery-header">
        <div class="delivery-check-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
        <div class="delivery-header-text">
          <div class="delivery-title">信息识别完成</div>
        </div>
      </div>

      <div class="delivery-inner-card">
        <div style="display: flex; flex-direction: column; gap: 5px; font-size: 13px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: var(--ink-500); width: 68px; flex-shrink: 0;">用户 ID：</span>
            <strong style="color: var(--ink-900); font-family: var(--font-mono);">${escapeHtml(userId)}</strong>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: var(--ink-500); width: 68px; flex-shrink: 0;">职业视角：</span>
            <span class="mode-badge" style="display: inline-flex;">
              <span class="badge-dot"></span>
              <span>${escapeHtml(roleName)}</span>
            </span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: var(--ink-500); width: 68px; flex-shrink: 0;">知识学科：</span>
            <span style="color: var(--ink-800);">${escapeHtml(subNames)}</span>
          </div>
        </div>
      </div>
    </div>
  `;

  group.appendChild(senderLine);
  group.appendChild(bubble);
  if (messagesContainer) {
    messagesContainer.appendChild(group);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}
