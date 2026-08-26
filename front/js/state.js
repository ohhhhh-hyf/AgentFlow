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
const liveParamSuggestions = $("live-param-suggestions");

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

  // 2. 重置中间聊天对话流
  if (messagesContainer) messagesContainer.innerHTML = "";
  if (chatWelcome && messagesContainer) messagesContainer.appendChild(chatWelcome);
  if (chatText) chatText.value = "";
  if (typeof autoResizeTextarea === "function") autoResizeTextarea();

  // 3. 重置随任务动态生成的上下文参数（保留用户 ID）
  if (ctxSubject) ctxSubject.value = "";
  if (ctxProject) ctxProject.value = "";
  if (ctxUser) ctxUser.classList.remove("input-error");
  if (ctxSubject) ctxSubject.classList.remove("input-error");
  if (ctxProject) ctxProject.classList.remove("input-error");
  if (typeof updateContextBarVisibility === "function") updateContextBarVisibility(null);

  // 4. 彻底重置右侧 Tab 1：任务计划与流水线展示
  if (planList) planList.innerHTML = "";
  const completionBanner = document.getElementById("pipeline-completion-banner");
  if (completionBanner) completionBanner.remove();

  if (planContainer) planContainer.classList.add("hidden");
  if (planEmpty) planEmpty.classList.remove("hidden");
  if (planCountBadge) {
    planCountBadge.textContent = "0";
    planCountBadge.classList.add("hidden");
  }

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
