// ==========================================================================
// AgentFlow Front-end · Sidebar Drawer & Navigation
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
