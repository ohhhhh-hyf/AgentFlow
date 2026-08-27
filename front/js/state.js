// ==========================================================================
// AgentFlow Front-end · Global State & DOM Element Bindings
// ==========================================================================
"use strict";

// DOM Selector Helper
const $ = (id) => document.getElementById(id);

// DOM Elements: Chat & Form
const messagesContainer = $("messages");
const chatWelcome = $("chat-welcome");
const chatForm = $("chat-form");
const chatText = $("chat-text");
const btnSend = $("btn-send");
const btnNewChat = $("btn-new-chat");
const serviceStatus = $("service-status");

// Global Context Inputs & Lock Elements
const ctxUser = $("ctx-user");
const ctxUserLocked = $("ctx-user-locked");
const lockedUserName = $("locked-user-name");
const btnUnlockUser = $("btn-unlock-user");
const ctxSubject = $("ctx-subject");
const ctxProject = $("ctx-project");
const ctxSubjectWrap = $("ctx-subject-wrap");
const ctxProjectWrap = $("ctx-project-wrap");
const subjectReqStar = $("subject-req-star");

// Workbench Tabs & Badges
const tabBtns = document.querySelectorAll(".tab-btn");
const tabContents = document.querySelectorAll(".tab-content");
const planCountBadge = $("plan-count-badge");
const taskStatusPill = $("task-status-pill");
const outputCountBadge = $("output-count-badge");

// Tab 1: Plan Workbench
const planEmpty = $("plan-empty");
const workbenchPipelineHeader = $("workbench-pipeline-header");
const planContainer = $("plan-container");
const planList = $("plan-list");
const pipelineVisual = $("pipeline-visual");
const pipelineStagesText = $("pipeline-stages-text");
const btnExecutePlan = $("btn-execute-plan");
const btnExecuteText = $("btn-execute-text");
const validationTip = $("validation-tip");
const validationTipText = $("validation-tip-text");

// Tab 2: Logs
const execSpinner = $("exec-spinner");
const execStatusTitle = $("exec-status-title");
const execStatusSub = $("exec-status-sub");
const execProgressBar = $("exec-progress-bar");
const consoleLogs = $("console-logs");

// Tab 3: Outputs Center
const outputsEmpty = $("outputs-empty");
const outputsContainer = $("outputs-container");
const outputsFileList = $("outputs-file-list");
const viewerFilename = $("viewer-filename");
const viewerBody = $("viewer-body");
const btnDownloadArtifact = $("btn-download-artifact");
const btnFullscreenPreview = $("btn-fullscreen-preview");

// Application Runtime State
let currentPlan = null;            // Parsed plan object
let currentActiveStep = 0;         // Current focused stage index (0-based)
let uploadsMap = new Map();        // Key: `${task}:${param}` -> Array of File objects
let completedTasks = new Set();    // Set of finished task IDs
let activeTaskId = null;           // Currently running/completed backend task ID
let activeOutputName = null;       // Currently previewed artifact filename
let pollTimer = null;              // Polling timer ID
let cachedPerspectives = null;     // Cached perspectives list
let currentUserContext = { subjects: [], projects: [] }; // Discovered user subjects & projects
let isUserLocked = false;          // Whether user ID is currently locked in session

// Helper to get or generate persistent session ID
function getSessionId() {
  let sid = "";
  try { sid = localStorage.getItem("agentflow_session") || ""; } catch (e) { /* noop */ }
  if (!sid) {
    sid = "web_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    try { localStorage.setItem("agentflow_session", sid); } catch (e) { /* noop */ }
  }
  return sid;
}

let activeSessionId = getSessionId();

// Get user input context without artificial default values
function getCtx() {
  return {
    user_id: ctxUser ? ctxUser.value.trim() : "",
    subject: ctxSubject ? ctxSubject.value.trim() : "",
    project: ctxProject ? ctxProject.value.trim() : "",
  };
}

// Reset entire workspace to initial state (Chat, Pipeline Plan, Execution Monitor, Outputs)
function resetWorkspace() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;

  // 1. 重置所有执行状态变量与任务映射
  currentPlan = null;
  uploadsMap.clear();
  completedTasks.clear();
  activeTaskId = null;
  activeOutputName = null;
  currentActiveStep = 0;

  // 2. 彻底重置中间聊天对话流与欢迎区域
  const messagesEl = document.getElementById("messages");
  if (messagesEl) {
    messagesEl.innerHTML = `
      <div id="chat-welcome" class="chat-welcome">
        <div class="welcome-icon-large">
          <img src="img.png" alt="AgentFlow" class="welcome-logo-img">
        </div>
        <h2 class="welcome-title">任务编排智能体上线，今天有什么需求？</h2>
      </div>
    `;
    messagesEl.scrollTop = 0;
  }
  const quickCardsWrap = document.getElementById("quick-prompt-cards-wrap");
  if (quickCardsWrap) quickCardsWrap.classList.remove("hidden");

  const chatInput = document.getElementById("chat-text");
  if (chatInput) {
    chatInput.value = "";
    chatInput.style.height = "auto";
  }
  if (typeof autoResizeTextarea === "function") autoResizeTextarea();

  const modeBadge = document.getElementById("mode-badge");
  if (modeBadge) modeBadge.classList.add("hidden");
  const modeText = document.getElementById("mode-text");
  if (modeText) modeText.textContent = "";

  const domainBadge = document.getElementById("domain-badge");
  if (domainBadge) domainBadge.classList.add("hidden");
  const domainText = document.getElementById("domain-text");
  if (domainText) domainText.textContent = "";

  const userAlert = document.getElementById("user-id-required-alert");
  if (userAlert) userAlert.classList.add("hidden");

  const btnSendEl = document.getElementById("btn-send");
  if (btnSendEl) {
    btnSendEl.classList.add("hidden");
    btnSendEl.disabled = false;
  }
  if (typeof updateSendButtonVisibility === "function") updateSendButtonVisibility();

  // 3. 重置随任务动态生成的上下文参数（保留用户 ID）
  if (ctxSubject) ctxSubject.value = "";
  if (ctxProject) ctxProject.value = "";
  if (ctxUser) ctxUser.classList.remove("input-error");
  if (ctxSubject) ctxSubject.classList.remove("input-error");
  if (ctxProject) ctxProject.classList.remove("input-error");
  if (typeof updateContextBarVisibility === "function") updateContextBarVisibility(null);

  // 4. 彻底重置右侧置顶流水线编排与 Tab 1 任务计划
  if (workbenchPipelineHeader) workbenchPipelineHeader.classList.add("hidden");
  if (pipelineVisual) pipelineVisual.innerHTML = "";
  if (pipelineStagesText) pipelineStagesText.textContent = "串行 / 并行组";

  if (planList) planList.innerHTML = "";
  const completionBanner = document.getElementById("pipeline-completion-banner");
  if (completionBanner) completionBanner.remove();

  if (planContainer) planContainer.classList.add("hidden");
  if (planEmpty) planEmpty.classList.remove("hidden");
  if (planCountBadge) {
    planCountBadge.textContent = "0";
    planCountBadge.classList.add("hidden");
  }

  const btnSkipStage = $("btn-skip-stage");
  if (btnSkipStage) btnSkipStage.classList.add("hidden");

  if (validationTip) validationTip.classList.add("hidden");
  if (btnExecutePlan) {
    btnExecutePlan.disabled = false;
    if (btnExecuteText) btnExecuteText.textContent = "执行 ➔";
  }

  // 5. 彻底重置右侧 Tab 2：执行监控与实时日志
  if (taskStatusPill) {
    taskStatusPill.className = "status-pill hidden";
    taskStatusPill.textContent = "待执行";
  }
  if (execSpinner) execSpinner.classList.remove("active");
  if (execStatusTitle) execStatusTitle.textContent = "等待执行任务";
  if (execStatusSub) execStatusSub.textContent = "提交任务后可实时查看执行进度";
  if (execProgressBar) execProgressBar.style.width = "0%";
  if (consoleLogs) consoleLogs.textContent = "暂无日志输出...";

  // 6. 彻底重置右侧 Tab 3：产物中心
  if (outputsContainer) outputsContainer.classList.add("hidden");
  if (outputsEmpty) outputsEmpty.classList.remove("hidden");
  if (outputCountBadge) {
    outputCountBadge.textContent = "0";
    outputCountBadge.classList.add("hidden");
  }
  const rowsWrap = $("outputs-rows-wrap");
  if (rowsWrap) rowsWrap.innerHTML = "";
  if (viewerFilename) viewerFilename.textContent = "选择文件以预览";
  if (viewerBody) viewerBody.innerHTML = '<div class="viewer-placeholder">成果生成后将在此处进行大面积全景预览</div>';
  if (btnDownloadArtifact) btnDownloadArtifact.disabled = true;
  if (btnFullscreenPreview) btnFullscreenPreview.disabled = true;

  // 7. 切换回任务计划 Tab
  if (typeof switchTab === "function") switchTab("tab-plan");
}

/**
 * 实时更新对话框上方的领域标识（与职业视角并排排列，采用一致的浅蓝色背景与字体规格）
 * @param {string|object} domain 领域名称（如 "会议域" / "笔记域"）或包含 plan 数组的对象
 */
function updateDomainBadge(domain) {
  const domainBadge = document.getElementById("domain-badge");
  const domainText = document.getElementById("domain-text");
  if (!domainBadge || !domainText) return;

  let label = "";
  if (typeof domain === "string") {
    const d = domain.trim().toLowerCase();
    if (d.includes("meeting") || d.includes("会议") || d.includes("纪要")) {
      label = "会议域";
    } else if (d.includes("note") || d.includes("笔记") || d.includes("学科") || d.includes("课程")) {
      label = "笔记域";
    }
  } else if (domain && Array.isArray(domain.plan)) {
    const tasks = domain.plan.map((t) => (t.task || "").toLowerCase());
    const hasNotes = tasks.some((t) => ["library", "catalog", "checklist", "quiz", "knowledge_graph"].includes(t));
    const hasMeeting = tasks.some((t) => ["minutes_generation", "action_items", "risk", "mindmap", "minutes_trace", "multi_styles"].includes(t));
    if (hasMeeting) {
      label = "会议域";
    } else if (hasNotes) {
      label = "笔记域";
    }
  } else if (domain && typeof domain === "object") {
    const d = String(domain.domain || "").toLowerCase();
    if (d.includes("meeting") || d.includes("会议")) {
      label = "会议域";
    } else if (d.includes("notes") || d.includes("笔记")) {
      label = "笔记域";
    }
  }

  if (label) {
    domainText.textContent = label;
    domainBadge.classList.remove("hidden");
  } else {
    domainBadge.classList.add("hidden");
  }
}
