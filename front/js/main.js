// ==========================================================================
// AgentFlow Front-end · Application Bootstrap & Global Events
// ==========================================================================
"use strict";

function autoResizeTextarea() {
  if (!chatText) return;
  chatText.style.height = "auto";
  chatText.style.height = `${Math.min(chatText.scrollHeight, 120)}px`;
}

function switchTab(tabId) {
  tabBtns.forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));
  tabContents.forEach((c) => c.classList.toggle("active", c.id === tabId));
}

// Handle '+' or New Chat click from left sidebar
function handleNewChatClick() {
  const ctx = getCtx();

  // 1. 将当前已有会话送入历史会话并刷新左侧列表展示
  loadUserSessions();

  // 2. 实时刷新产物云盘与知识库学科资产
  loadUserOutputsDisk();
  if (ctx.user_id) {
    fetchUserContext(ctx.user_id);
  }

  // 3. 生成全新 Session ID 开启新一轮对话
  activeSessionId = "web_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  try {
    localStorage.setItem("agentflow_session", activeSessionId);
  } catch (e) {}

  // 4. 彻底刷新工作台、右侧流水线、监控日志与产物中心
  resetWorkspace();

  // 5. 移除历史会话中的高亮选中状态
  document.querySelectorAll(".session-item").forEach((el) => el.classList.remove("active"));
}

function setupEventListeners() {
  // Tab Switching
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      switchTab(targetId);
    });
  });

  // Chat Form Submission
  if (chatForm) {
    chatForm.addEventListener("submit", (e) => {
      e.preventDefault();
      handleChatSubmit();
    });
  }

  // Textarea Auto-expand, Enter Key handler & real-time intent keyword detection
  if (chatText) {
    chatText.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleChatSubmit();
      }
    });

    chatText.addEventListener("input", () => {
      autoResizeTextarea();
      updateLiveParamSuggestions(chatText.value);
      if (!currentPlan) {
        heuristicContextVisibility(chatText.value.trim());
      }
    });
  }

  // New Chat / Start Fresh Round
  if (btnNewChat) {
    btnNewChat.addEventListener("click", handleNewChatClick);
  }
  const btnSidebarNew = $("btn-sidebar-new-chat");
  if (btnSidebarNew) {
    btnSidebarNew.addEventListener("click", handleNewChatClick);
  }

  // Unlock User Button
  if (btnUnlockUser) {
    btnUnlockUser.addEventListener("click", unlockUserId);
  }

  // Quick Prompt Chips
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      if (prompt) {
        if (chatText) {
          chatText.value = prompt;
          autoResizeTextarea();
        }
        heuristicContextVisibility(prompt);
        handleChatSubmit();
      }
    });
  });

  // Global Context input changes: re-validate immediately
  [ctxUser, ctxSubject, ctxProject].forEach((input) => {
    if (input) {
      input.addEventListener("input", () => {
        syncContextToPlan();
        validatePlanParams();
      });
    }
  });

  // User ID input blur & Enter: fetch context and reload sessions
  if (ctxUser) {
    ctxUser.addEventListener("blur", () => {
      const val = ctxUser.value.trim();
      if (val) {
        try { localStorage.setItem("agentflow_user_id", val); } catch (e) {}
        fetchUserContext(val);
        loadUserSessions();
      }
    });
    ctxUser.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        ctxUser.blur();
      }
    });
  }

  // Execute Plan Button
  if (btnExecutePlan) {
    btnExecutePlan.addEventListener("click", () => executeCurrentPlan(false));
  }

  // Skip Stage Button (Skip upload/library and proceed to catalog/checklist)
  const btnSkipStage = $("btn-skip-stage");
  if (btnSkipStage) {
    btnSkipStage.addEventListener("click", () => {
      if (!currentPlan) return;
      const totalStages = currentPlan.execution ? currentPlan.execution.length : 1;
      const currentStageTasks = (currentPlan.execution && currentPlan.execution[currentActiveStep]) || [];
      currentStageTasks.forEach((task) => completedTasks.add(task));
      if (currentActiveStep < totalStages - 1) {
        currentActiveStep += 1;
        setActiveStep(currentActiveStep);
        validatePlanParams();
      }
    });
  }

  // Download Artifact
  if (btnDownloadArtifact) {
    btnDownloadArtifact.addEventListener("click", () => {
      if (activeTaskId && activeOutputName) {
        const url = `${API}/tasks/${activeTaskId}/output/${encodeURIComponent(activeOutputName)}`;
        const a = document.createElement("a");
        a.href = url;
        a.download = activeOutputName;
        a.target = "_blank";
        a.click();
      }
    });
  }

  // Fullscreen Artifact Preview
  if (btnFullscreenPreview) {
    btnFullscreenPreview.addEventListener("click", () => {
      if (activeTaskId && activeOutputName) {
        const url = `${API}/tasks/${activeTaskId}/output/${encodeURIComponent(activeOutputName)}`;
        window.open(url, "_blank");
      }
    });
  }

  // 1. Sidebar Knowledge Base Accordion & Refresh
  const navKnowledgeToggle = $("nav-knowledge-toggle");
  const groupKnowledge = $("group-knowledge");
  const drawerKnowledge = $("sidebar-kb-drawer");
  if (navKnowledgeToggle && drawerKnowledge) {
    navKnowledgeToggle.addEventListener("click", () => {
      const isHidden = drawerKnowledge.classList.toggle("hidden");
      if (groupKnowledge) groupKnowledge.classList.toggle("open", !isHidden);
      if (!isHidden) {
        const ctx = getCtx();
        if (ctx.user_id) fetchUserContext(ctx.user_id);
      }
    });
  }

  const btnRefreshKb = $("btn-refresh-kb");
  if (btnRefreshKb) {
    btnRefreshKb.addEventListener("click", async (e) => {
      e.stopPropagation();
      btnRefreshKb.classList.add("spinning");
      const ctx = getCtx();
      if (ctx.user_id) {
        await fetchUserContext(ctx.user_id);
      } else {
        if (ctxUser) {
          ctxUser.classList.add("input-error");
          ctxUser.focus();
        }
      }
      if (drawerKnowledge && drawerKnowledge.classList.contains("hidden")) {
        drawerKnowledge.classList.remove("hidden");
        if (groupKnowledge) groupKnowledge.classList.add("open");
      }
      setTimeout(() => btnRefreshKb.classList.remove("spinning"), 500);
    });
  }

  // 2. Sidebar Outputs Cloud Accordion & Refresh
  const navOutputsToggle = $("nav-outputs-toggle");
  const groupOutputs = $("group-outputs");
  const drawerOutputs = $("sidebar-outputs-drawer");
  if (navOutputsToggle && drawerOutputs) {
    navOutputsToggle.addEventListener("click", () => {
      const isHidden = drawerOutputs.classList.toggle("hidden");
      if (groupOutputs) groupOutputs.classList.toggle("open", !isHidden);
      switchTab("tab-outputs");
      loadUserOutputsDisk();
    });
  }

  const btnRefreshOutputs = $("btn-refresh-outputs");
  if (btnRefreshOutputs) {
    btnRefreshOutputs.addEventListener("click", async (e) => {
      e.stopPropagation();
      btnRefreshOutputs.classList.add("spinning");
      switchTab("tab-outputs");
      await loadUserOutputsDisk();
      if (drawerOutputs && drawerOutputs.classList.contains("hidden")) {
        drawerOutputs.classList.remove("hidden");
        if (groupOutputs) groupOutputs.classList.add("open");
      }
      setTimeout(() => btnRefreshOutputs.classList.remove("spinning"), 500);
    });
  }
}

// App Initialization
async function init() {
  checkBackendHealth();
  preloadPerspectives();
  setupEventListeners();
  autoResizeTextarea();
  updateContextBarVisibility(null);

  // 默认进入保持用户 ID 为空，由用户主动输入
  if (ctxUser) ctxUser.value = "";
  try {
    localStorage.removeItem("agentflow_user_id");
  } catch (e) {}
}

// Boot application
window.addEventListener("DOMContentLoaded", init);
