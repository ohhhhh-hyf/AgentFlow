// ==========================================================================
// AgentFlow Front-end · Sidebar Drawer, User Persona & Navigation
// ==========================================================================
"use strict";

// Lock User ID into Session Pill
function lockUserId(userId) {
  if (!userId) return;
  isUserLocked = true;
  if (ctxUser) ctxUser.classList.add("hidden");
  if (ctxUserLocked) ctxUserLocked.classList.remove("hidden");
  if (lockedUserName) lockedUserName.textContent = userId;
  if (ctxUser) ctxUser.classList.remove("input-error");
  fetchUserContext(userId);
}

// Unlock User ID
function unlockUserId() {
  isUserLocked = false;
  if (ctxUser) ctxUser.classList.remove("hidden");
  if (ctxUserLocked) ctxUserLocked.classList.add("hidden");
  if (ctxUser) ctxUser.focus();
}

// Update Persona Badges across workspace (Chat Box & Workbench)
function updateUserProfilePill(profile) {
  const modeBadge = $("mode-badge");
  const modeText = $("mode-text");

  if (!profile) {
    if (modeBadge) modeBadge.classList.add("hidden");
    return;
  }

  const baseTpl = (profile.base_template || "").trim().toLowerCase();
  const roleName = profile.role || (profile.template_label ? profile.template_label.split("·").pop().trim() : "客观全员");

  // 如果是客观视角，不用展示；如果是具体职业，展示浅蓝色背景的职业名称
  const isObject = baseTpl === "object" || roleName === "客观全员" || roleName === "客观" || roleName.includes("客观");
  if (isObject || !roleName) {
    if (modeBadge) modeBadge.classList.add("hidden");
  } else {
    if (modeBadge) {
      modeBadge.classList.remove("hidden");
      if (modeText) modeText.textContent = roleName;
    }
  }

  // 同步工作台上的任务视角卡片徽章
  const taskBadge = $("task-persona-badge");
  if (taskBadge) {
    taskBadge.textContent = profile.template_label || roleName;
  }
}

// Open User Profile & Persona Modal
function openUserProfileModal() {
  const modal = $("user-profile-modal");
  if (!modal) return;
  const ctx = getCtx();
  const uid = ctx.user_id || "未指定";

  if (!ctx.user_id) {
    if (ctxUser) {
      ctxUser.classList.add("input-error");
      ctxUser.focus();
    }
    alert("请先输入您的「用户 ID」");
    return;
  }

  const modalUid = $("modal-profile-uid");
  const modalPath = $("modal-profile-path");
  if (modalUid) modalUid.textContent = uid;
  if (modalPath) modalPath.textContent = `data/${uid}/profile/${uid}.json`;

  const prof = (currentUserContext && currentUserContext.profile) || {};
  const selectRole = $("modal-profile-role-select");
  if (selectRole) {
    selectRole.value = prof.base_template || "object";
  }

  const traits = prof.traits || {};
  const inputStyle = $("modal-trait-style");
  const inputComm = $("modal-trait-comm");
  const inputChar = $("modal-trait-char");

  if (inputStyle) inputStyle.value = traits["做事风格"] || "";
  if (inputComm) inputComm.value = traits["沟通偏好"] || "";
  if (inputChar) inputChar.value = traits["性格"] || "";

  const saveStatus = $("modal-save-status");
  if (saveStatus) saveStatus.textContent = "";

  modal.classList.remove("hidden");
}

// Close Modal
function closeUserProfileModal() {
  const modal = $("user-profile-modal");
  if (modal) modal.classList.add("hidden");
}

// Save User Profile to Backend and Refresh
async function saveUserProfileModal() {
  const ctx = getCtx();
  if (!ctx.user_id) {
    alert("请先输入用户 ID");
    return;
  }

  const selectRole = $("modal-profile-role-select");
  const inputStyle = $("modal-trait-style");
  const inputComm = $("modal-trait-comm");
  const inputChar = $("modal-trait-char");
  const saveStatus = $("modal-save-status");

  const baseTemplate = selectRole ? selectRole.value : "object";
  const traits = {};
  if (inputStyle && inputStyle.value.trim()) traits["做事风格"] = inputStyle.value.trim();
  if (inputComm && inputComm.value.trim()) traits["沟通偏好"] = inputComm.value.trim();
  if (inputChar && inputChar.value.trim()) traits["性格"] = inputChar.value.trim();

  if (saveStatus) {
    saveStatus.style.color = "var(--ink-700)";
    saveStatus.textContent = "正在保存并刷盘...";
  }

  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_template: baseTemplate,
        traits: traits,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      if (data.profile) {
        currentUserContext.profile = data.profile;
        updateUserProfilePill(data.profile);
      }
      if (saveStatus) {
        saveStatus.style.color = "#2e7d32";
        saveStatus.textContent = "✓ 已成功保存并同步刷盘！";
      }
      setTimeout(() => {
        closeUserProfileModal();
      }, 600);
    } else {
      throw new Error("保存失败");
    }
  } catch (err) {
    if (saveStatus) {
      saveStatus.style.color = "#c62828";
      saveStatus.textContent = `保存异常：${err.message}`;
    }
  }
}

// Update Knowledge Base Drawer with Discovered Subjects
function updateKnowledgeBaseDrawer(ctxData) {
  const subjectsList = $("kb-subjects-list");
  const totalBadge = $("sidebar-kb-total-count");

  const subjects = (ctxData && ctxData.subjects) || [];

  if (totalBadge) {
    totalBadge.textContent = subjects.length;
  }

  if (subjectsList) {
    subjectsList.innerHTML = "";
    if (subjects.length === 0) {
      subjectsList.innerHTML = '<span class="kb-empty-text">暂无知识库学科</span>';
    } else {
      subjects.forEach((s) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "kb-chip-item";
        chip.innerHTML = `<span>${escapeHtml(s.name)}</span><span class="kb-chip-count">(${s.count || 0}条)</span>`;
        chip.title = `点击填入所属学科：${s.name}`;
        chip.addEventListener("click", () => {
          applyParam("subject", s.name);
          if (chatText) chatText.focus();
        });
        subjectsList.appendChild(chip);
      });
    }
  }
}

// Render Sidebar Sessions List
function renderSidebarSessions(sessions) {
  const list = $("sidebar-sessions-list");
  if (!list) return;
  list.innerHTML = "";

  if (!sessions || !sessions.length) {
    list.innerHTML = `<div class="sidebar-empty-sessions">暂无历史会话<br>在右侧输入开启交流</div>`;
    return;
  }

  sessions.forEach((s) => {
    const item = document.createElement("div");
    item.className = `session-item ${s.session_id === activeSessionId ? "active" : ""}`;
    item.dataset.sessionId = s.session_id;

    const timeStr = formatRelativeTime(s.updated_at);

    item.innerHTML = `
      <div class="session-item-title" title="${escapeHtml(s.title)}">${escapeHtml(s.title)}</div>
      <div class="session-item-meta">
        <span class="session-item-time">${escapeHtml(timeStr)}</span>
        <button class="session-item-del" title="删除此会话">&times;</button>
      </div>
    `;

    item.addEventListener("click", (e) => {
      if (e.target.closest(".session-item-del")) return;
      switchSession(s.session_id);
    });

    const delBtn = item.querySelector(".session-item-del");
    if (delBtn) {
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        await deleteSession(s.session_id);
      });
    }

    list.appendChild(item);
  });
}

// Render Sidebar Outputs Cloud Drawer
function renderSidebarOutputsDrawer(outputs) {
  const badge = $("sidebar-outputs-count");
  if (badge) badge.textContent = outputs ? outputs.length : 0;

  const miniList = $("sidebar-outputs-mini-list");
  if (!miniList) return;
  miniList.innerHTML = "";

  if (!outputs || !outputs.length) {
    miniList.innerHTML = '<span class="kb-empty-text">暂无产物文件</span>';
    return;
  }

  outputs.forEach((file) => {
    const item = document.createElement("div");
    item.className = "sidebar-mini-file-item";
    item.title = `点击在右侧查看/下载 ${file.name} (${file.task_type})`;
    item.innerHTML = `
      <span class="sidebar-mini-file-type">${escapeHtml(file.ext.toUpperCase())}</span>
      <span class="sidebar-mini-file-name">${escapeHtml(file.name)}</span>
      <span class="sidebar-mini-file-tag">${escapeHtml(file.task_type)}</span>
    `;
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      switchTab("tab-outputs");
      previewHistoricalOutput(file.rel_path, file.name);
    });
    miniList.appendChild(item);
  });
}
