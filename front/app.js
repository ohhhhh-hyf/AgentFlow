
// ==========================================================================
// AgentFlow Front-end · Google Material 3 / Gemini Aesthetic Client
// ==========================================================================
"use strict";

// API Base URL (auto-detects local / remote host)
const API = window.location.origin.includes("http")
  ? `${window.location.origin}/api`
  : "http://127.0.0.1:8000/api";

// DOM Elements
const $ = (id) => document.getElementById(id);
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

// Tab 1: Plan
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
// const btnCopyLogs = $("btn-copy-logs");

// Tab 3: Outputs
const outputsEmpty = $("outputs-empty");
const outputsContainer = $("outputs-container");
const outputsFileList = $("outputs-file-list");
const viewerFilename = $("viewer-filename");
const viewerBody = $("viewer-body");
const btnDownloadArtifact = $("btn-download-artifact");
const btnFullscreenPreview = $("btn-fullscreen-preview");

// Application State
let currentPlan = null;            // Parsed plan object
let currentActiveStep = 0;         // Current focused stage index (0-based)
let uploadsMap = new Map();        // Key: `${task}:${param}` -> Array of File objects
let activeTaskId = null;           // Currently running/completed backend task ID
let activeOutputName = null;       // Currently previewed artifact filename
let pollTimer = null;              // Polling timer ID
let cachedPerspectives = null;     // Cached perspectives list
let currentUserContext = { subjects: [], projects: [] }; // Discovered user subjects & projects
let isUserLocked = false;          // Whether user ID is currently locked in session

// Task Names Localization & Domain Metadata
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

// ==========================================================================
// 1. Initialization & Global Events
// ==========================================================================

async function init() {
  checkBackendHealth();
  preloadPerspectives();
  setupEventListeners();
  autoResizeTextarea();
  updateContextBarVisibility(null);

  // 默认进入保持用户 ID 为空，由用户主动输入
  ctxUser.value = "";
  try {
    localStorage.removeItem("agentflow_user_id");
  } catch (e) {}
}

// Check Backend Health
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API}/health`);
    if (res.ok) {
      serviceStatus.className = "status-indicator online";
      serviceStatus.querySelector(".status-text").textContent = "服务正常";
    } else {
      throw new Error();
    }
  } catch {
    serviceStatus.className = "status-indicator offline";
    serviceStatus.querySelector(".status-text").textContent = "服务离线";
  }
}

// Preload Meeting Perspectives
async function preloadPerspectives() {
  try {
    const res = await fetch(`${API}/perspectives`);
    if (res.ok) {
      const data = await res.json();
      cachedPerspectives = (data.perspectives || []).map((p) => p.label);
    }
  } catch {
    cachedPerspectives = ["客观 · 客观全员"];
  }
}

// Fetch discovered subjects and projects for a given user ID
async function fetchUserContext(userId) {
  if (!userId) return;
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(userId)}/context`);
    if (res.ok) {
      const data = await res.json();
      currentUserContext = data || { subjects: [], projects: [] };
    }
  } catch {
    currentUserContext = { subjects: [], projects: [] };
  }
  updateKnowledgeBaseDrawer(currentUserContext);
}

// Persist a single session turn immediately to guarantee sidebar title is accurate
async function saveSessionMessage(userId, sessionId, role, content) {
  if (!userId || !sessionId || !content) return;
  try {
    await fetch(`${API}/user/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, content }),
    });
    loadUserSessions();
  } catch (e) {
    console.warn("Failed to persist session message:", e);
  }
}

// Lock User ID into Session Pill
function lockUserId(userId) {
  if (!userId) return;
  isUserLocked = true;
  ctxUser.classList.add("hidden");
  ctxUserLocked.classList.remove("hidden");
  lockedUserName.textContent = userId;
  ctxUser.classList.remove("input-error");
  fetchUserContext(userId);
}

// Unlock User ID
function unlockUserId() {
  isUserLocked = false;
  ctxUser.classList.remove("hidden");
  ctxUserLocked.classList.add("hidden");
  ctxUser.focus();
}

// ==========================================================================
// Smart Parameter Extraction & One-Click Application Engine
// ==========================================================================

function detectParameters(text) {
  if (!text) return {};
  const res = {};

  // 1. Subject (学科)
  // Match explicit patterns: "我想建立我的数学知识库", "创建物理库", "入库到高等数学", "数学学科"
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

  // 3. Perspective (视角)
  if (/产品经理|PM/i.test(text)) {
    res.perspective = "职业 · 产品经理";
  } else if (/开发人员|程序员|工程师|技术人员|研发/i.test(text)) {
    res.perspective = "职业 · 开发人员";
  } else if (/项目经理/i.test(text)) {
    res.perspective = "职业 · 项目经理";
  } else if (/客观全员|全员视角/i.test(text)) {
    res.perspective = "客观 · 客观全员";
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
    ctxSubject.value = value;
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
    ctxSubject.classList.add("input-highlight-pulse");
    setTimeout(() => ctxSubject.classList.remove("input-highlight-pulse"), 2500);
    syncContextToPlan();
    validatePlanParams();
  } else if (type === "project") {
    ctxProject.value = value;
    if (ctxProjectWrap) ctxProjectWrap.classList.remove("hidden-ctx");
    ctxProject.classList.add("input-highlight-pulse");
    setTimeout(() => ctxProject.classList.remove("input-highlight-pulse"), 2500);
    syncContextToPlan();
    validatePlanParams();
  } else if (type === "perspective") {
    if (currentPlan && currentPlan.plan) {
      const mg = currentPlan.plan.find((t) => t.task === "minutes_generation");
      if (mg) {
        mg.params = mg.params || {};
        mg.params.perspective = value;
        const sel = document.querySelector("#task-card-minutes_generation .param-select");
        if (sel) sel.value = value;
      }
    }
  }

  if (buttonEl) {
    buttonEl.classList.add("applied");
    buttonEl.innerHTML = `已应用: ${escapeHtml(value)}`;
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

  if (detected.subject && ctxSubject.value !== detected.subject) {
    items.push({
      type: "subject",
      label: `学科: ${detected.subject}`,
      val: detected.subject
    });
  }
  if (detected.project && ctxProject.value !== detected.project) {
    items.push({
      type: "project",
      label: `项目: ${detected.project}`,
      val: detected.project
    });
  }
  if (detected.perspective) {
    items.push({
      type: "perspective",
      label: `视角: ${(detected.perspective.split("·")[1] || detected.perspective).trim()}`,
      val: detected.perspective
    });
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

function setupEventListeners() {
  // Tab Switching
  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      switchTab(targetId);
    });
  });

  // Chat Form Submission
  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleChatSubmit();
  });

  // Textarea Auto-expand, Enter Key handler & real-time intent keyword detection
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
      // Adapt context bar based on text heuristic before submit
      heuristicContextVisibility(chatText.value.trim());
    }
  });

  // New Chat / Start Fresh Round (Sending current chat to history)
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
        chatText.value = prompt;
        autoResizeTextarea();
        heuristicContextVisibility(prompt);
        handleChatSubmit();
      }
    });
  });

  // Global Context input changes: re-validate immediately
  [ctxUser, ctxSubject, ctxProject].forEach((input) => {
    input.addEventListener("input", () => {
      syncContextToPlan();
      validatePlanParams();
    });
  });

  // User ID input blur & Enter: fetch context and reload sessions
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

  // Execute Plan Button (Agree and Execute Stage)
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
        ctxUser.classList.add("input-error");
        ctxUser.focus();
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

function autoResizeTextarea() {
  chatText.style.height = "auto";
  chatText.style.height = `${Math.min(chatText.scrollHeight, 120)}px`;
}

function switchTab(tabId) {
  tabBtns.forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === tabId));
  tabContents.forEach((c) => c.classList.toggle("active", c.id === tabId));
}

// Get user input context without artificial default values
function getCtx() {
  return {
    user_id: ctxUser.value.trim(),
    subject: ctxSubject.value.trim(),
    project: ctxProject.value.trim(),
  };
}

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

// Dynamically update Context Bar visibility based on Plan tasks
function updateContextBarVisibility(plan) {
  if (!plan || !plan.length) {
    // Initial state: hide project and subject, keep user ID visible
    if (ctxProjectWrap) ctxProjectWrap.classList.add("hidden-ctx");
    if (ctxSubjectWrap) ctxSubjectWrap.classList.add("hidden-ctx");
    if (subjectReqStar) subjectReqStar.classList.add("hidden");
    return;
  }

  let hasMeeting = false;
  let hasNotes = false;
  let subjectRequired = false;

  plan.forEach((t) => {
    const domain = t.domain || (TASK_META[t.task] ? TASK_META[t.task].domain : "");
    if (domain === "meeting") hasMeeting = true;
    if (domain === "notes") hasNotes = true;

    // Check if subject is explicitly required
    const missing = t.missing || [];
    if (missing.includes("subject")) {
      subjectRequired = true;
    }
  });

  // Meeting domain: needs project (for memory binding), does NOT need subject
  // Notes domain: needs subject, does NOT need project
  if (hasMeeting && !hasNotes) {
    if (ctxProjectWrap) ctxProjectWrap.classList.remove("hidden-ctx");
    if (ctxSubjectWrap) ctxSubjectWrap.classList.add("hidden-ctx");
  } else if (hasNotes && !hasMeeting) {
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
    if (ctxProjectWrap) ctxProjectWrap.classList.add("hidden-ctx");
  } else if (hasMeeting && hasNotes) {
    if (ctxProjectWrap) ctxProjectWrap.classList.remove("hidden-ctx");
    if (ctxSubjectWrap) ctxSubjectWrap.classList.remove("hidden-ctx");
  }

  if (subjectReqStar) {
    subjectReqStar.classList.toggle("hidden", !subjectRequired);
  }
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
  stages = [];
  currentStageIndex = 0;
  currentActiveStep = 0;

  // 2. 重置中间聊天对话流
  messagesContainer.innerHTML = "";
  if (chatWelcome) messagesContainer.appendChild(chatWelcome);
  chatText.value = "";
  autoResizeTextarea();

  // 3. 重置随任务动态生成的上下文参数（保留用户 ID）
  ctxSubject.value = "";
  ctxProject.value = "";
  ctxUser.classList.remove("input-error");
  ctxSubject.classList.remove("input-error");
  ctxProject.classList.remove("input-error");
  updateContextBarVisibility(null);

  // 4. 彻底重置右侧 Tab 1：任务计划与流水线展示
  if (planList) planList.innerHTML = "";
  const completionBanner = document.getElementById("pipeline-completion-banner");
  if (completionBanner) completionBanner.remove();

  planContainer.classList.add("hidden");
  planEmpty.classList.remove("hidden");
  planCountBadge.textContent = "0";
  planCountBadge.classList.add("hidden");

  if (validationTip) validationTip.classList.add("hidden");
  if (btnExecutePlan) {
    btnExecutePlan.disabled = false;
    if (btnExecuteText) btnExecuteText.textContent = "执行 ➔";
  }

  // 5. 彻底重置右侧 Tab 2：执行监控与实时日志
  taskStatusPill.className = "status-pill hidden";
  taskStatusPill.textContent = "待执行";
  execSpinner.classList.remove("active");
  execStatusTitle.textContent = "等待执行任务";
  if (execStatusSub) execStatusSub.textContent = "提交任务后可实时查看执行进度";
  execProgressBar.style.width = "0%";
  consoleLogs.textContent = "暂无日志输出...";

  // 6. 彻底重置右侧 Tab 3：产物中心
  outputsContainer.classList.add("hidden");
  outputsEmpty.classList.remove("hidden");
  outputCountBadge.textContent = "0";
  outputCountBadge.classList.add("hidden");
  const rowsWrap = $("outputs-rows-wrap");
  if (rowsWrap) rowsWrap.innerHTML = "";
  if (viewerFilename) viewerFilename.textContent = "选择文件以预览";
  if (viewerBody) viewerBody.innerHTML = '<div class="viewer-placeholder">成果生成后将在此处进行大面积全景预览</div>';
  btnDownloadArtifact.disabled = true;
  btnFullscreenPreview.disabled = true;

  // 7. 切换回任务计划 Tab
  switchTab("tab-plan");
}

// ==========================================================================
// 2. Chat & Intent Engine Dispatcher
// ==========================================================================

async function handleChatSubmit(customText = null, customSubject = null, isDirect = false) {
  const text = (customText !== null ? customText : chatText.value).trim();
  if (!text) return;

  if (customSubject) {
    ctxSubject.value = customSubject;
  }

  // 1. Strict Validation on User ID: must be filled before conversation starts
  let ctx = getCtx();
  if (!ctx.user_id) {
    ctxUser.classList.add("input-error");
    ctxUser.focus();
    appendMessage(
      "bot",
      "您好！在开启对话前，请先在左侧栏下方输入您的「用户 ID」（用于隔离个人知识库与跨会话记忆）。"
    );
    return;
  }
  ctxUser.classList.remove("input-error");
  try {
    localStorage.setItem("agentflow_user_id", ctx.user_id);
  } catch (e) {}

  // Clear input box
  chatText.value = "";
  autoResizeTextarea();

  // Hide welcome hero on first message
  if (chatWelcome && chatWelcome.parentNode === messagesContainer) {
    chatWelcome.remove();
  }

  // Append user message
  appendMessage("user", text);
  if (ctx.user_id && activeSessionId) {
    saveSessionMessage(ctx.user_id, activeSessionId, "user", text);
  }

  // 3. Smart Subject & Workflow Branching Interceptor:
  // Ensure user context is up to date before checking knowledge base subjects
  if (ctx.user_id && (!currentUserContext.subjects || !currentUserContext.subjects.length)) {
    await fetchUserContext(ctx.user_id);
  }

  const detectedParams = detectParameters(text);
  const detectedSub = customSubject || detectedParams.subject || ctx.subject || "";
  const knownSubjects = currentUserContext.subjects || [];

  // If user is requesting a downstream notes task (e.g. 复习资料 / 复习清单 / 大纲 / 自测 / 图谱)
  // Check if we need to let user choose between (1) Existing Knowledge Base vs (2) Fresh Ingest Pipeline:
  const isDownstreamNotesTask =
    /清单|复习|大纲|目录|自测|出题|图谱|资料/i.test(text) &&
    !/入库|建库|保存进|整理进|识别/i.test(text);

  // If not explicitly triggered directly, offer the clean Studio Dual-Branch Card
  if (isDownstreamNotesTask && !isDirect) {
    appendTaskBranchDecisionMessage(text, detectedSub, knownSubjects);
    return;
  }

  // Append bot loading state
  const loadingMsgId = appendLoadingMessage();
  btnSend.disabled = true;

  try {
    ctx = getCtx();
    const res = await fetch(`${API}/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, ...ctx, session_id: activeSessionId }),
    });

    const data = await res.json();

    if (!res.ok) {
      // 422 or Intent unrecognized -> fallback to RAG / Chat Q&A
      updateLoadingMessage(loadingMsgId, "此问题适合直接问答，正在为您检索知识库...");
      await fallbackToChat(text, loadingMsgId);
      return;
    }

    // Success: Intent Plan recognized
    removeMessage(loadingMsgId);
    appendIntentSummaryMessage(data, text);
    renderPlanWorkbench(data);
    loadUserSessions();

    // If currently watching running logs, keep logs tab active and notify via badge
    const isRunningTask = taskStatusPill && taskStatusPill.classList.contains("running");
    if (!isRunningTask) {
      switchTab("tab-plan");
    }
  } catch (err) {
    updateLoadingMessage(loadingMsgId, `意图解析请求失败：${err.message}`, "err");
  } finally {
    btnSend.disabled = false;
  }
}

// Helper to create clean Google Studio avatars
function createAvatar(role) {
  const avatar = document.createElement("div");
  avatar.className = `msg-avatar ${role}`;
  if (role === "user") {
    avatar.textContent = "U";
  } else {
    avatar.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M12 2L9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5z"/></svg>`;
  }
  return avatar;
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

      // 仅展示新学科，隐藏已有学科列表
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
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Render Guidance Card when no subjects are in knowledge base
function appendNoSubjectGuidanceMessage(originalQuery) {
  const group = document.createElement("div");
  group.className = "msg-group bot";

  const avatar = createAvatar("bot");
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  bubble.innerHTML = `
    <p><strong>知识库建设建议</strong></p>
    <p>当前用户知识库中暂未收录资料。生成考点清单与大纲需要先有笔记或课件作为知识源。</p>
    <div class="msg-suggestion-card">
      <div class="suggestion-header">推荐执行方案：</div>
      <div class="suggestion-actions">
        <button class="btn-suggestion-action" id="btn-suggest-ingest">
          <span>导入新课件 / 笔记（自动 OCR 识别入库并生成大纲）</span>
        </button>
      </div>
    </div>
  `;

  bubble.querySelector("#btn-suggest-ingest").addEventListener("click", () => {
    const ingestPrompt = "我想上传资料并创建物理学科知识库";
    chatText.value = ingestPrompt;
    handleChatSubmit(ingestPrompt, "物理");
  });

  group.appendChild(senderLine);
  group.appendChild(bubble);
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// 会话 ID：页面级持久化（localStorage），保证多轮问答用同一会话（历史/画像连续）
function getSessionId() {
  let sid = "";
  try { sid = localStorage.getItem("agentflow_session") || ""; } catch (e) { /* noop */ }
  if (!sid) {
    sid = "web_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    try { localStorage.setItem("agentflow_session", sid); } catch (e) { /* noop */ }
  }
  return sid;
}

// Fallback to Knowledge Base Q&A
async function fallbackToChat(question, loadingMsgId) {
  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, ...getCtx(), session_id: activeSessionId }),
    });
    const data = await res.json();

    if (!res.ok) {
      updateLoadingMessage(loadingMsgId, `问答失败：${data.detail || "未知错误"}`, "err");
      return;
    }

    removeMessage(loadingMsgId);
    appendChatMessage(data);
    loadUserSessions();
  } catch (err) {
    updateLoadingMessage(loadingMsgId, `问答请求异常：${err.message}`, "err");
  }
}

// Append Messages in Chat Stream
function appendMessage(role, content) {
  const group = document.createElement("div");
  group.className = `msg-group ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.textContent = content;

  group.appendChild(bubble);
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return group;
}

function appendLoadingMessage() {
  const id = `loading-${Date.now()}`;
  const group = document.createElement("div");
  group.id = id;
  group.className = "msg-group bot";

  const avatar = createAvatar("bot");
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = '<span class="status-dot" style="display:inline-block;background:var(--google-blue);animation:spin 1s infinite;"></span> 正在解析需求并规划任务流水线...';

  group.appendChild(avatar);
  group.appendChild(bubble);
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
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

  const explanation = data.explanation || "好的。已按您的需求规划任务流水线，上游资料将按依赖关系自动结构化流转。";
  const tasks = data.plan || [];
  const execution = data.execution || [[...tasks.map((p) => p.task)]];

  const targetTask = tasks.length ? tasks[tasks.length - 1].task : "";
  const targetMeta = TASK_META[targetTask] || { name: "目标产物", domain: "通用" };
  const targetDocName = `${targetMeta.name.split(" ")[0]}.md`;

  let html = `
    <div class="msg-text-lead">${escapeHtml(explanation)}</div>

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
              <th style="width: 120px; text-align: right; white-space: nowrap;">状态</th>
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

  // Detect parameters from user's sentence to offer smart click-to-apply buttons
  const detected = detectParameters(userQuery);
  const paramButtons = [];

  if (detected.subject && ctxSubject.value !== detected.subject) {
    paramButtons.push({
      type: "subject",
      label: `学科: ${detected.subject}`,
      val: detected.subject
    });
  }
  if (detected.project && ctxProject.value !== detected.project) {
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

  // Bind click events on the parameter action buttons
  bubble.querySelectorAll(".btn-msg-param-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.getAttribute("data-type");
      const val = btn.getAttribute("data-val");
      applyParam(type, val, btn);
    });
  });

  group.appendChild(senderLine);
  group.appendChild(bubble);
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
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
  messagesContainer.appendChild(group);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ==========================================================================
// 3. Plan & Workbench Rendering
// ==========================================================================

function renderPlanWorkbench(data) {
  currentPlan = data;
  uploadsMap.clear();
  completedTasks.clear();
  activeTaskId = null;

  if (taskStatusPill) {
    taskStatusPill.className = "status-pill hidden";
    taskStatusPill.textContent = "待执行";
  }

  // Update any active planning branch button in chat to "流水线规划完成"
  const activePlanningBtns = document.querySelectorAll("#active-planning-btn, .btn-existing-pipeline:disabled, #btn-branch-new-submit:disabled");
  activePlanningBtns.forEach((btn) => {
    btn.id = "";
    btn.classList.add("done");
    btn.innerHTML = `<span>流水线规划完成 ✓</span>`;
  });

  const plan = data.plan || [];
  const execution = data.execution || [[...plan.map((p) => p.task)]];

  planCountBadge.textContent = plan.length;
  planCountBadge.classList.toggle("hidden", plan.length === 0);

  if (workbenchPipelineHeader) workbenchPipelineHeader.classList.remove("hidden");
  planEmpty.classList.add("hidden");
  planContainer.classList.remove("hidden");

  // Dynamic context visibility based on plan tasks
  updateContextBarVisibility(plan);

  // Default to step 0
  currentActiveStep = 0;

  // Render Visual Pipeline Stage DAG
  renderPipelineVisual(execution);

  // Render Task Cards
  planList.innerHTML = "";
  plan.forEach((item, idx) => {
    const card = createTaskCard(item, idx);
    planList.appendChild(card);
  });

  // Switch to Stage 1
  setActiveStep(0);

  // Sync Global Context to Task parameters
  syncContextToPlan();

  // Validate parameters
  validatePlanParams();
}

function renderPipelineVisual(execution) {
  pipelineVisual.innerHTML = "";
  const hasParallel = execution.some((g) => g.length > 1);
  pipelineStagesText.textContent = `共 ${execution.length} 个执行阶段${hasParallel ? " (含多任务并发加速)" : ""}`;

  execution.forEach((group, gIdx) => {
    const pill = document.createElement("div");
    pill.className = "stage-pill";
    pill.dataset.step = gIdx;
    if (gIdx === currentActiveStep) {
      pill.classList.add("active");
    }

    const isParallel = group.length > 1;
    const taskNames = group
      .map((t) => (TASK_META[t] ? TASK_META[t].name.split(" ")[0] : t))
      .join(" ‖ ");

    const parallelTag = isParallel
      ? `<span class="badge-parallel">${group.length}项并行</span>`
      : "";

    pill.innerHTML = `<strong>阶段 ${gIdx + 1}</strong>${parallelTag}: ${escapeHtml(taskNames)}`;

    // Click to switch stage
    pill.addEventListener("click", () => {
      setActiveStep(gIdx);
    });

    pipelineVisual.appendChild(pill);

    if (gIdx < execution.length - 1) {
      const arrow = document.createElement("span");
      arrow.className = "stage-arrow";
      arrow.textContent = "➔";
      pipelineVisual.appendChild(arrow);
    }
  });
}

// Helper to sync chat table rows with right-hand execution progress
function syncChatTableStatus(runningTaskId = "") {
  if (!currentPlan || !currentPlan.plan) return;

  const deliveryCards = messagesContainer.querySelectorAll(".delivery-card");
  const latestCard = deliveryCards.length ? deliveryCards[deliveryCards.length - 1] : null;
  if (!latestCard) return;

  currentPlan.plan.forEach((t) => {
    const statusCell = latestCard.querySelector(`[data-task-status="${t.task}"]`) ||
                       latestCard.querySelector(`#chat-task-status-${t.task}`);
    if (!statusCell) return;

    if (completedTasks.has(t.task)) {
      statusCell.className = "col-status status-done";
      statusCell.textContent = "已完成 ✓";
    } else if (t.task === runningTaskId) {
      statusCell.className = "col-status status-running";
      statusCell.textContent = "运行中...";
    } else if (
      currentPlan.execution &&
      currentPlan.execution[currentActiveStep] &&
      currentPlan.execution[currentActiveStep].includes(t.task)
    ) {
      statusCell.className = "col-status status-ready";
      statusCell.textContent = "已就绪";
    } else {
      statusCell.className = "col-status status-queued";
      statusCell.textContent = "待执行";
    }
  });
}

function setActiveStep(stepIdx) {
  if (!currentPlan || !currentPlan.execution) return;
  const totalStages = currentPlan.execution.length;
  currentActiveStep = Math.max(0, Math.min(stepIdx, totalStages - 1));

  // 1. Update visual stage pills active state
  const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
  stagePills.forEach((pill, idx) => {
    if (idx === currentActiveStep) {
      pill.classList.add("active");
    } else {
      pill.classList.remove("active");
    }
  });

  // 2. Filter task cards in #plan-list to show only tasks belonging to this stage
  const currentStageTasks = new Set(currentPlan.execution[currentActiveStep] || []);
  const allCards = planList.querySelectorAll(".task-card");
  allCards.forEach((card) => {
    const taskId = card.id.replace("task-card-", "");
    if (currentStageTasks.has(taskId)) {
      card.style.display = "block";
    } else {
      card.style.display = "none";
    }
  });

  // 3. Update Single Primary Execute/Approval Button text
  if (btnExecuteText) {
    btnExecuteText.textContent = "执行 ➔";
  }

  // 4. Synchronize Left-Hand Chat Table with this Active Stage
  syncChatTableStatus();
}

// Determine if a task's input (e.g. file / input) is automatically supplied by an upstream task
function getUpstreamProvider(taskName, plan, execution) {
  if (!plan || !plan.length) return null;

  const planTasks = plan.map((t) => t.task);
  const taskEntry = plan.find((t) => t.task === taskName);
  const needs = taskEntry ? (taskEntry.needs || []) : [];

  // 1. Library after OCR: OCR generates the Markdown file for library
  if (taskName === "library" && (needs.includes("ocr") || planTasks.includes("ocr"))) {
    return {
      param: "file",
      upstreamTask: "ocr",
      upstreamName: "OCR 图片识别",
      desc: "无需手动上传文件。将直接使用前序「OCR 图片识别」生成的结构化 Markdown 产物作为入库文件。"
    };
  }

  // 2. Catalog / Checklist after Library: uses knowledge base created by library
  if ((taskName === "catalog" || taskName === "checklist") && (needs.includes("library") || planTasks.includes("library"))) {
    return {
      param: "file",
      upstreamTask: "library",
      upstreamName: "知识资料结构化入库",
      desc: "无需上传附件。将直接基于上游入库构建的向量知识库生成知识目录与考点清单。"
    };
  }

  // 3. Meeting subtasks after Minutes Generation: reuse meeting transcript and minutes
  const meetingSubtasks = ["action_items", "mindmap", "risk", "minutes_trace", "multi_styles"];
  if (meetingSubtasks.includes(taskName) && planTasks.includes("minutes_generation") && taskName !== "minutes_generation") {
    return {
      param: "file",
      upstreamTask: "minutes_generation",
      upstreamName: "会议纪要生成",
      desc: "无需重复上传。将直接复用上游「会议纪要生成」上传的会议原文与提炼的纪要数据。"
    };
  }

  // 4. Quiz / Review after OCR
  if ((taskName === "quiz" || taskName === "review") && (needs.includes("ocr") || planTasks.includes("ocr"))) {
    return {
      param: "file",
      upstreamTask: "ocr",
      upstreamName: "OCR 图片识别",
      desc: "无需手动上传。将直接基于前序「OCR 图片识别」的笔记文本进行出题或审校。"
    };
  }

  // 5. Generic needs lookup in upstream stages
  if (needs.length) {
    const upstreamTask = needs[0];
    if (planTasks.includes(upstreamTask)) {
      const meta = TASK_META[upstreamTask] || { name: upstreamTask };
      return {
        param: "file",
        upstreamTask,
        upstreamName: meta.name,
        desc: `无需提前上传。将直接衔接前置任务【${meta.name}】的执行产物作为本任务输入。`
      };
    }
  }

  return null;
}

function createUpstreamFlowCard(upstreamInfo) {
  const wrap = document.createElement("div");
  wrap.className = "upstream-flow-wrapper";
  wrap.style.marginTop = "8px";

  wrap.innerHTML = `
    <div class="param-group-title auto-flow">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      </svg>
      <span>输入依赖自动供给</span>
    </div>
    <div class="upstream-flow-card">
      <div class="upstream-flow-icon">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
          <polyline points="13 2 13 9 20 9" />
        </svg>
      </div>
      <div class="upstream-flow-info">
        <span class="upstream-flow-label">由上游「${escapeHtml(upstreamInfo.upstreamName)}」自动供给</span>
        <span class="upstream-flow-desc">${escapeHtml(upstreamInfo.desc)}</span>
      </div>
    </div>
  `;
  return wrap;
}

function createTaskCard(item, idx) {
  const card = document.createElement("div");
  card.className = "task-card";
  card.id = `task-card-${item.task}`;

  const meta = TASK_META[item.task] || {
    name: item.task,
    desc: item.note || "",
    domain: item.domain || "notes",
  };

  item._pendingMissing = [...(item.missing || [])];
  item.params = item.params || {};

  // Check if input file/attachment is automatically supplied by an upstream task
  const upstreamInfo = getUpstreamProvider(item.task, currentPlan.plan, currentPlan.execution);
  if (upstreamInfo && upstreamInfo.param) {
    item._pendingMissing = item._pendingMissing.filter((p) => p !== upstreamInfo.param);
  }

  // Card Header
  const header = document.createElement("div");
  header.className = "task-card-header";

  const titleWrap = document.createElement("div");
  titleWrap.className = "task-card-title-wrap";
  titleWrap.innerHTML = `
    <span class="task-step-num">${idx + 1}</span>
    <span class="task-name-text">${escapeHtml(meta.name)}</span>
  `;

  const tags = document.createElement("div");
  tags.className = "task-tags";

  const domainClass = item.domain === "meeting" ? "tag-domain-meeting" : "tag-domain-notes";
  const domainLabel = item.domain === "meeting" ? "会议域" : "笔记域";
  tags.innerHTML = `<span class="tag-badge ${domainClass}">${domainLabel}</span>`;

  if (item.needs && item.needs.length) {
    tags.innerHTML += `<span class="tag-badge tag-dep">依赖: ${escapeHtml(item.needs.join(","))}</span>`;
  }

  header.appendChild(titleWrap);
  header.appendChild(tags);

  const statusWrap = document.createElement("div");
  statusWrap.className = "task-status-wrap";
  statusWrap.id = `task-status-badge-${item.task}`;
  header.appendChild(statusWrap);

  card.appendChild(header);

  // Description / Note
  const desc = document.createElement("div");
  desc.className = "task-note-text";
  desc.textContent = item.note || meta.desc || "待执行流水线任务节点";
  card.appendChild(desc);

  // Parameters Section
  const paramsSec = document.createElement("div");
  paramsSec.className = "params-section";

  // 1. Required Parameters / Input Flow Section
  const missing = item.missing || [];
  if (missing.length || upstreamInfo) {
    const reqGroup = document.createElement("div");
    reqGroup.className = "req-params-group";

    // If input is supplied by upstream task, show Auto-flow badge instead of dropzone
    if (upstreamInfo) {
      const flowCard = createUpstreamFlowCard(upstreamInfo);
      reqGroup.appendChild(flowCard);
    }

    // For missing params that are NOT supplied by upstream
    missing.forEach((param) => {
      if ((param === "file" || param === "input") && (!upstreamInfo || upstreamInfo.param !== param)) {
        // File Upload Dropzone
        const dropzoneWrap = createDropzone(item, param);
        reqGroup.appendChild(dropzoneWrap);
      }
    });

    paramsSec.appendChild(reqGroup);
  }

  // 1.5 For Catalog & Checklist: Prominent Teacher Keypoints input with Upload button directly visible
  if (item.task === "catalog" || item.task === "checklist") {
    const isCatalog = item.task === "catalog";
    const kpSection = document.createElement("div");
    kpSection.className = "direct-keypoints-section";
    kpSection.style.marginTop = "12px";
    kpSection.style.padding = "12px 14px";
    kpSection.style.background = "var(--surface-canvas)";
    kpSection.style.borderRadius = "var(--radius-sm)";
    kpSection.style.border = "1px dashed var(--border-strong)";

    kpSection.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span style="font-size:0.86rem; font-weight:600; color:var(--text-primary);">
          ${isCatalog ? "可选：上传 / 粘贴老师划重点文本" : "可选：上传 / 粘贴考前复习重点与强调"}
        </span>
        <span style="font-size:0.75rem; color:var(--text-muted);">选填（不填则纯基于上游知识库生成）</span>
      </div>
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap;">
        <label class="btn-upload-keypoints">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
          </svg>
          <span>上传重点文档 / 文件</span>
          <input type="file" class="kp-file-input" style="display:none;" accept=".txt,.md,.markdown,.docx,.pdf,.png,.jpg,.jpeg" />
        </label>
        <span class="kp-file-status" style="font-size:0.8rem; color:var(--ink-500);">支持直接上传 .txt, .md, .docx, .pdf 或重点图片</span>
      </div>
    `;

    const fileInput = kpSection.querySelector(".kp-file-input");
    const fileStatus = kpSection.querySelector(".kp-file-status");
    const kpInput = document.createElement("textarea");
    kpInput.className = "param-text-input";
    kpInput.rows = 3;
    kpInput.style.resize = "vertical";
    kpInput.placeholder = isCatalog
      ? "选填：可直接粘贴或上传老师课堂点名强调的大纲、核心章节或考前重点..."
      : "选填：可直接粘贴或上传老师点名必考/常考题型、重点公式与答题要点...";
    kpInput.value = item.params.keypoints || "";

    if (fileInput) {
      fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) return;

        const ext = (file.name.split(".").pop() || "").toLowerCase();
        if (["txt", "md", "markdown"].includes(ext)) {
          const reader = new FileReader();
          reader.onload = (e) => {
            const content = (e.target.result || "").trim();
            kpInput.value = content;
            item.params.keypoints = content;
            if (fileStatus) {
              fileStatus.innerHTML = `<span style="color:#2e7d32; font-weight:600;">✓ 已自动解析载入：${escapeHtml(file.name)}</span>`;
            }
          };
          reader.readAsText(file, "utf-8");
        } else {
          const key = `${item.task}:keypoints_file`;
          uploadsMap.set(key, [file]);
          item.params.keypoints_file = [file.name];
          if (fileStatus) {
            fileStatus.innerHTML = `<span style="color:#2e7d32; font-weight:600;">✓ 已挂载重点附件：${escapeHtml(file.name)} (${formatFileSize(file.size)})</span>`;
          }
        }
      });
    }

    kpInput.addEventListener("input", () => {
      const val = kpInput.value.trim();
      if (val) item.params.keypoints = val;
      else delete item.params.keypoints;
    });

    kpSection.appendChild(kpInput);
    paramsSec.appendChild(kpSection);
  }

  // 2. Optional Parameters Accordion (可选项)
  const optAccordion = createOptionalAccordion(item);
  if (optAccordion) {
    paramsSec.appendChild(optAccordion);
  }

  card.appendChild(paramsSec);
  return card;
}

// Create Drag-and-Drop File Upload Zone
function createDropzone(item, param) {
  const wrap = document.createElement("div");
  wrap.className = "dropzone-wrapper";
  wrap.style.marginTop = "8px";

  const isLibrary = item.task === "library";
  const isOCR = item.task === "ocr";

  let titleText = "源文档 / 会议录音文本";
  let subText = "支持常见格式文件 / 图片";
  if (isLibrary) {
    titleText = "课程资料 / 笔记 (支持 PDF/PPTX/Word/TXT/MD 及图片混传)";
    subText = "文档直接结构化解析入库；笔记/公式图片将自动通过本地 OCR 识别并合并为 Markdown 后入库";
  } else if (isOCR) {
    titleText = "待识别图片 / 手写公式笔记 (支持多选)";
    subText = "支持 .jpg, .png, .jpeg, .bmp, .webp 图片";
  }

  const title = document.createElement("div");
  title.className = "param-group-title required";
  title.innerHTML = `
    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
    </svg>
    <span>必填附件: ${escapeHtml(titleText)}</span>
  `;
  wrap.appendChild(title);

  const dropzone = document.createElement("div");
  dropzone.className = "dropzone-area";

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.className = "dropzone-file-input";
  fileInput.multiple = true;

  dropzone.innerHTML = `
    <div class="dropzone-content">
      <div class="dropzone-icon">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="dropzone-title"><strong>点击上传</strong> 或将文件拖拽至此处 (支持一次全选多个文件)</div>
      <div class="dropzone-sub">${escapeHtml(subText)}</div>
    </div>
  `;
  dropzone.appendChild(fileInput);

  const filesList = document.createElement("div");
  filesList.className = "uploaded-files-list";

  const smartTip = document.createElement("div");
  smartTip.className = "dropzone-smart-tip";
  smartTip.style.display = "none";
  smartTip.style.fontSize = "0.76rem";
  smartTip.style.color = "var(--google-blue-text)";
  smartTip.style.background = "var(--google-blue-subtle)";
  smartTip.style.padding = "6px 10px";
  smartTip.style.borderRadius = "var(--radius-xs)";
  smartTip.style.marginTop = "6px";
  smartTip.style.lineHeight = "1.4";

  // Drag & Drop visual feedback
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("drag-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("drag-over");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files.length) {
      handleFiles(Array.from(dt.files));
    }
  });

  fileInput.addEventListener("change", () => {
    handleFiles(Array.from(fileInput.files || []));
  });

  function handleFiles(newFiles) {
    if (!newFiles.length) return;
    const key = `${item.task}:${param}`;
    let existing = uploadsMap.get(key) || [];
    existing = [...existing, ...newFiles];
    uploadsMap.set(key, existing);

    // Update item params & pending missing list
    item.params[param] = existing.map((f) => f.name);
    item._pendingMissing = (item._pendingMissing || []).filter((p) => p !== param);

    renderFileChips();
    validatePlanParams();
  }

  function renderFileChips() {
    filesList.innerHTML = "";
    const key = `${item.task}:${param}`;
    const files = uploadsMap.get(key) || [];

    let imgCount = 0;
    let docCount = 0;

    files.forEach((f, fIdx) => {
      const ext = (f.name.split(".").pop() || "").toLowerCase();
      const isImg = ["jpg", "jpeg", "png", "bmp", "webp"].includes(ext);
      if (isImg) imgCount++;
      else docCount++;

      const chip = document.createElement("div");
      chip.className = "file-chip";
      chip.innerHTML = `
        <span class="file-chip-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
        <span class="file-chip-size">(${formatFileSize(f.size)})</span>
        <button class="file-chip-remove" title="移除此文件">&times;</button>
      `;

      chip.querySelector(".file-chip-remove").addEventListener("click", (e) => {
        e.stopPropagation();
        files.splice(fIdx, 1);
        uploadsMap.set(key, files);
        item.params[param] = files.map((file) => file.name);
        if (files.length === 0) {
          if (!item._pendingMissing.includes(param)) {
            item._pendingMissing.push(param);
          }
        }
        renderFileChips();
        validatePlanParams();
      });

      filesList.appendChild(chip);
    });

    // Smart OCR hint if images are detected in library uploads
    if (isLibrary && imgCount > 0) {
      smartTip.style.display = "block";
      smartTip.innerHTML = `<strong>已包含 ${imgCount} 个图像文件</strong>：系统将在入库时自动通过本地 OCR 引擎进行公式与手写文字提取，并与 ${docCount} 份文档一并结构化入库。`;
    } else {
      smartTip.style.display = "none";
    }
  }

  wrap.appendChild(dropzone);
  wrap.appendChild(filesList);
  wrap.appendChild(smartTip);
  return wrap;
}

// Optional Parameters Accordion
function createOptionalAccordion(item) {
  const isMeetingMinutes = item.task === "minutes_generation";
  const optionalParams = (item.optional || []).filter((p) => p !== "user_id" && p !== "project" && p !== "subject");

  if (!isMeetingMinutes && !optionalParams.length) return null;

  const accordion = document.createElement("details");
  accordion.className = "optional-accordion";
  accordion.open = true; // 默认展开

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span>高级可选配置 (选填)</span>
    <span style="font-size: 0.72rem; color: var(--text-muted);">收起 ▴</span>
  `;
  accordion.appendChild(summary);

  const content = document.createElement("div");
  content.className = "optional-content";

  // 1. Meeting Perspective Selection
  if (isMeetingMinutes) {
    const pRow = document.createElement("div");
    pRow.className = "param-input-row";
    pRow.innerHTML = '<span class="param-input-label">纪要生成视角</span>';

    const select = document.createElement("select");
    select.className = "param-select";

    const perspectives = cachedPerspectives && cachedPerspectives.length
      ? cachedPerspectives
      : ["客观 · 客观全员", "职业 · 开发人员", "职业 · 产品经理", "职业 · 项目经理"];

    perspectives.forEach((label) => {
      const opt = document.createElement("option");
      opt.value = label;
      opt.textContent = label;
      select.appendChild(opt);
    });

    if (item.params.perspective) select.value = item.params.perspective;

    select.addEventListener("change", () => {
      if (select.value && select.value !== "客观 · 客观全员") {
        item.params.perspective = select.value;
      } else {
        delete item.params.perspective;
      }
    });

    pRow.appendChild(select);
    content.appendChild(pRow);
  }

  // 2. 老师划重点 / 考前大纲文本（可选，针对 catalog 与 checklist）
  if (item.task === "catalog" || item.task === "checklist") {
    const kpRow = document.createElement("div");
    kpRow.className = "param-input-row";
    kpRow.style.flexDirection = "column";
    kpRow.style.alignItems = "stretch";
    kpRow.style.gap = "6px";
    kpRow.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span class="param-input-label" style="font-weight:600; color:var(--text-primary);">
          老师划重点 / 考前强调文本 (选填)
        </span>
        <span style="font-size:0.72rem; color:var(--text-muted);">不填则纯基于知识库生成，不强加考点假设</span>
      </div>
    `;
    const kpInput = document.createElement("textarea");
    kpInput.className = "param-text-input";
    kpInput.rows = 2;
    kpInput.style.resize = "vertical";
    kpInput.placeholder = "选填：粘贴老师课堂点名划重点的要点文本、大题考向或考前提示...";
    kpInput.value = item.params.keypoints || "";
    kpInput.addEventListener("input", () => {
      const val = kpInput.value.trim();
      if (val) item.params.keypoints = val;
      else delete item.params.keypoints;
    });
    kpRow.appendChild(kpInput);
    content.appendChild(kpRow);
  }

  // 3. 输出模板上传（可选，md/txt）：写进 params.template，backend 传给 runner
  const tplSection = document.createElement("div");
  tplSection.className = "template-upload-section";

  tplSection.innerHTML = `
    <div class="template-section-header">
      <div class="template-title-wrap">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <span class="template-section-title">输出模板 (可选)</span>
      </div>
      <span class="template-badge">选填</span>
    </div>
    <div class="template-section-desc">
      支持上传自定义 Markdown / 文本模板（.md / .txt），产物将严格依循您的章节结构排版。
    </div>

    <div class="template-action-row">
      <label class="btn-template-upload" id="btn-tpl-upload-${item.task}">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
        </svg>
        <span>上传模板文件 (.md / .txt)</span>
        <input type="file" class="template-file-input" accept=".md,.txt,.markdown" style="display:none;" />
      </label>
      <div class="template-file-chip hidden" id="tpl-chip-${item.task}"></div>
      <span class="template-default-hint" id="tpl-hint-${item.task}">未上传时采用系统标准模版</span>
    </div>
  `;

  const btnUpload = tplSection.querySelector(`#btn-tpl-upload-${item.task}`);
  const tplInput = tplSection.querySelector(".template-file-input");
  const tplChip = tplSection.querySelector(`#tpl-chip-${item.task}`);
  const tplHint = tplSection.querySelector(`#tpl-hint-${item.task}`);

  function updateTemplateChip(file) {
    if (!file) {
      tplChip.classList.add("hidden");
      tplChip.innerHTML = "";
      btnUpload.classList.remove("hidden");
      tplHint.classList.remove("hidden");
      return;
    }

    btnUpload.classList.add("hidden");
    tplHint.classList.add("hidden");
    tplChip.classList.remove("hidden");
    tplChip.innerHTML = `
      <div class="template-chip-left">
        <span class="template-chip-icon">📄</span>
        <div class="template-chip-info">
          <span class="template-chip-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
          <span class="template-chip-size">${formatFileSize(file.size)} · 模板已挂载</span>
        </div>
      </div>
      <button class="template-chip-remove" title="移除模板">&times;</button>
    `;

    const removeBtn = tplChip.querySelector(".template-chip-remove");
    if (removeBtn) {
      removeBtn.addEventListener("click", () => {
        const key = `${item.task}:template`;
        uploadsMap.delete(key);
        if (item.params) delete item.params.template;
        tplInput.value = "";
        updateTemplateChip(null);
      });
    }
  }

  // Restore if already selected in uploadsMap
  const existingKey = `${item.task}:template`;
  const existingFiles = uploadsMap.get(existingKey);
  if (existingFiles && existingFiles.length) {
    updateTemplateChip(existingFiles[0]);
  }

  if (tplInput) {
    tplInput.addEventListener("change", () => {
      const file = tplInput.files && tplInput.files[0];
      if (!file) return;

      const key = `${item.task}:template`;
      uploadsMap.set(key, [file]);
      item.params = item.params || {};
      item.params.template = [file.name];
      updateTemplateChip(file);
    });
  }

  content.appendChild(tplSection);

  // 4. Other Optional Inputs
  optionalParams.forEach((param) => {
    if (param === "file" || param === "input") return;
    const optRow = document.createElement("div");
    optRow.className = "param-input-row";
    optRow.innerHTML = `<span class="param-input-label">可选: ${escapeHtml(param)}</span>`;

    const optInput = document.createElement("input");
    optInput.type = "text";
    optInput.className = "param-text-input";
    optInput.placeholder = `选填 (默认自动推断)`;
    optInput.value = item.params[param] || "";

    optInput.addEventListener("input", () => {
      const val = optInput.value.trim();
      if (val) item.params[param] = val;
      else delete item.params[param];
    });

    optRow.appendChild(optInput);
    content.appendChild(optRow);
  });

  accordion.appendChild(content);
  return accordion;
}

// Sync Global Context to Task parameters strictly
function syncContextToPlan() {
  if (!currentPlan || !currentPlan.plan) return;
  const ctx = getCtx();

  currentPlan.plan.forEach((t) => {
    t.params = t.params || {};

    // user_id is universal and enables memory
    if (ctx.user_id) {
      t.params.user_id = ctx.user_id;
    } else {
      delete t.params.user_id;
    }

    const domain = t.domain || (TASK_META[t.task] ? TASK_META[t.task].domain : "");

    // Meeting domain: project only (no subject)
    if (domain === "meeting") {
      delete t.params.subject;
      if (ctx.project) {
        t.params.project = ctx.project;
      } else {
        delete t.params.project;
      }
    }

    // Notes domain: subject only (no project)
    if (domain === "notes") {
      delete t.params.project;
      if (ctx.subject) {
        t.params.subject = ctx.subject;
      } else {
        delete t.params.subject;
      }
    }

    // Update missing list
    if (t._pendingMissing) {
      if (ctx.user_id) t._pendingMissing = t._pendingMissing.filter((p) => p !== "user_id" && p !== "user");
      if (ctx.subject) t._pendingMissing = t._pendingMissing.filter((p) => p !== "subject");
      if (ctx.project) t._pendingMissing = t._pendingMissing.filter((p) => p !== "project");
    }
  });
}

// Parameter Validation Engine
function validatePlanParams() {
  if (!currentPlan || !currentPlan.plan) return;

  syncContextToPlan();
  const ctx = getCtx();
  const pending = [];

  // Check 1: user_id is strictly mandatory ("id必传")
  if (!ctx.user_id) {
    pending.push("用户 ID (必填)");
    ctxUser.classList.add("input-error");
  } else {
    ctxUser.classList.remove("input-error");
  }

  // Check 2: Task-level required parameters for CURRENT stage tasks
  const currentStageTasks = new Set(
    (currentPlan.execution && currentPlan.execution[currentActiveStep]) || []
  );

  let hasSubjectError = false;
  currentPlan.plan.forEach((t) => {
    // Only validate tasks belonging to current active stage and not already finished
    if (!currentStageTasks.has(t.task) || completedTasks.has(t.task)) {
      return;
    }

    const meta = TASK_META[t.task] || { name: t.task };
    const missing = t.missing || [];
    const upstreamInfo = getUpstreamProvider(t.task, currentPlan.plan, currentPlan.execution);

    // If task requires subject and subject is empty
    if (missing.includes("subject") && !ctx.subject) {
      if (!hasSubjectError) {
        pending.push("所属学科 (必填)");
        hasSubjectError = true;
      }
    }

    // Check file uploads (skip if auto-supplied by upstream task)
    if (missing.includes("file") || missing.includes("input")) {
      const fileParam = missing.includes("file") ? "file" : "input";
      if (!upstreamInfo || upstreamInfo.param !== fileParam) {
        const key = `${t.task}:${fileParam}`;
        const uploaded = uploadsMap.get(key) || [];
        if (!uploaded.length) {
          pending.push(`${meta.name} 缺少附件`);
        }
      }
    }
  });

  if (hasSubjectError) {
    ctxSubject.classList.add("input-error");
  } else {
    ctxSubject.classList.remove("input-error");
  }

  const currentSub = (ctx.subject || "").trim();
  const isExistingSubject = Boolean(
    currentUserContext.subjects &&
    currentUserContext.subjects.some((s) => s.name === currentSub && (s.count || 0) > 0)
  );

  const totalStages = currentPlan.execution ? currentPlan.execution.length : 1;
  const btnSkipStage = $("btn-skip-stage");

  const isFileStep = Array.from(currentStageTasks).some((task) => {
    const t = currentPlan.plan.find((item) => item.task === task);
    return t && (t.missing || []).some((m) => m === "file" || m === "input");
  });

  // 1. 只有知识库已有该学科数据时，才允许出现「无需新增知识」跳过逻辑；新建学科必须上传资料，严禁跳过！
  const canSkipIngest = isExistingSubject && isFileStep && currentActiveStep < totalStages - 1;

  if (btnSkipStage) {
    if (canSkipIngest) {
      btnSkipStage.classList.remove("hidden");
    } else {
      btnSkipStage.classList.add("hidden");
    }
  }

  // 2. 如果支持跳过入库，则无需显示打扰用户的“缺少附件”报警（用户可跳过或上传）
  let displayPending = [...pending];
  if (canSkipIngest) {
    displayPending = displayPending.filter((item) => !item.includes("缺少附件"));
  }

  if (pending.length) {
    btnExecutePlan.disabled = true;
  } else {
    btnExecutePlan.disabled = false;
  }

  if (displayPending.length) {
    validationTip.classList.remove("hidden");
    validationTipText.textContent = `待补全项：${displayPending.join("；")}`;
  } else {
    validationTip.classList.add("hidden");
  }
}

// ==========================================================================
// 4. Task Execution & Polling Engine
// ==========================================================================

let completedTasks = new Set();

async function executeCurrentPlan(isAllStages = false) {
  if (!currentPlan) return;

  validatePlanParams();
  if (btnExecutePlan.disabled) return;

  btnExecutePlan.disabled = true;
  if (btnExecuteText) {
    btnExecuteText.textContent = "正在执行...";
  }

  // 默认切换到执行监控界面，实时查看流式日志
  switchTab("tab-logs");
  taskStatusPill.className = "status-pill running";
  taskStatusPill.textContent = `阶段 ${currentActiveStep + 1} 执行中`;
  taskStatusPill.classList.remove("hidden");
  execSpinner.classList.add("active");
  if (execStatusTitle) {
    execStatusTitle.textContent = `正在执行第 ${currentActiveStep + 1} 阶段...`;
  }
  consoleLogs.textContent = "";

  const totalStages = currentPlan.execution ? currentPlan.execution.length : 1;
  const currentStageTasks = (currentPlan.execution && currentPlan.execution[currentActiveStep]) || [];

  let stagePayload = null;
  if (isAllStages) {
    const remainingStages = currentPlan.execution.slice(currentActiveStep);
    const remainingTaskNames = new Set(remainingStages.flat());
    const remainingPlanTasks = currentPlan.plan.filter((t) => remainingTaskNames.has(t.task));
    stagePayload = {
      ...currentPlan,
      plan: remainingPlanTasks,
      execution: remainingStages,
    };
  } else {
    const currentPlanTasks = currentPlan.plan.filter((t) => currentStageTasks.includes(t.task));
    stagePayload = {
      ...currentPlan,
      plan: currentPlanTasks,
      execution: [currentStageTasks],
    };
  }

  const ctx = getCtx();
  stagePayload.user_id = ctx.user_id || "default_user";

  // Mark current stage cards and pills as running
  currentStageTasks.forEach((task) => {
    const card = document.getElementById(`task-card-${task}`);
    const badge = document.getElementById(`task-status-badge-${task}`);
    if (card) card.classList.add("running");
    if (badge) badge.innerHTML = `<span class="task-state-badge running"><span class="spinner-tiny"></span> 执行中...</span>`;
    syncChatTableStatus(task);
  });

  const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
  if (stagePills[currentActiveStep]) {
    stagePills[currentActiveStep].classList.add("running");
  }

  // Prepare FormData
  const fd = new FormData();
  fd.append("plan_json", JSON.stringify(stagePayload));

  uploadsMap.forEach((files) => {
    files.forEach((f) => fd.append("files", f, f.name));
  });

  try {
    const res = await fetch(`${API}/tasks`, { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "后端拒绝执行任务");
    }

    activeTaskId = data.task_id;
    consoleLogs.textContent += `>>> 阶段任务提交成功！Task ID: ${activeTaskId}\n>>> 开始执行...\n\n`;
    startPolling(activeTaskId, isAllStages);
  } catch (err) {
    execSpinner.classList.remove("active");
    taskStatusPill.className = "status-pill failed";
    taskStatusPill.textContent = "执行失败";
    btnExecutePlan.disabled = false;
        setActiveStep(currentActiveStep);
    alert(`执行失败：${err.message}`);
  }
}

function startPolling(taskId, isAllStages = false) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  let isFinished = false;
  let pollCount = 0;
  pollTimer = setInterval(async () => {
    if (isFinished) return;
    pollCount++;
    try {
      const res = await fetch(`${API}/tasks/${taskId}`);
      if (!res.ok) {
        throw new Error("查询任务状态失败");
      }
      const st = await res.json();
      updateExecutionUI(st, pollCount);

      if ((st.status === "done" || st.status === "failed") && !isFinished) {
        isFinished = true;
        clearInterval(pollTimer);
        pollTimer = null;
        finishExecution(st, isAllStages);
      }
    } catch (err) {
      consoleLogs.textContent += `[WARN] 状态轮询异常: ${err.message}\n`;
    }
  }, 1000);
}

function updateExecutionUI(st, pollCount) {
  const currentMeta = st.current && TASK_META[st.current] ? TASK_META[st.current] : null;
  const currentTaskName = currentMeta ? currentMeta.name.split(" ")[0] : (st.current || "");
  const currentTask = currentTaskName ? ` · ${currentTaskName}` : "";

  if (execStatusTitle) {
    if (st.status === "running") {
      execStatusTitle.textContent = `运行中${currentTask}`;
    } else if (st.status === "done") {
      execStatusTitle.textContent = `阶段执行完成${currentTask}`;
    } else if (st.status === "failed") {
      execStatusTitle.textContent = "执行失败";
    }
  }

  // Real Progress percentage from backend
  let progressVal = 15;
  if (typeof st.progress === "number" && st.progress > 0) {
    progressVal = st.progress;
  } else {
    progressVal = Math.min(15 + pollCount * 6, 92);
  }
  execProgressBar.style.width = `${progressVal}%`;

  // Update Console Logs with real-time stream
  if (st.logs && st.logs.length) {
    consoleLogs.textContent = st.logs.join("\n");
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
  }

  // ── Sync Left Chat Table ──
  syncChatTableStatus(st.current || "");

  // ── Sync Visual Pipeline Stages & Task Cards ──
  const doneTasks = new Set((st.results || []).map((r) => r.task));
  const runningTask = st.current || "";

  // 1. Update Stage Pills in Pipeline visual header for CURRENT executed group
  if (currentPlan && currentPlan.execution) {
    const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
    currentPlan.execution.forEach((group, gIdx) => {
      const pill = stagePills[gIdx];
      if (!pill) return;
      const allGroupDone = group.every((t) => doneTasks.has(t) || completedTasks.has(t));
      const isGroupRunning = group.some((t) => t === runningTask);

      if (allGroupDone) {
        pill.classList.remove("running");
        pill.classList.add("done");
      } else if (isGroupRunning) {
        pill.classList.remove("done");
        pill.classList.add("running");
      }
    });
  }

  // 2. Update Task Cards in Plan list
  if (currentPlan && currentPlan.plan) {
    currentPlan.plan.forEach((t) => {
      const card = document.getElementById(`task-card-${t.task}`);
      const badge = document.getElementById(`task-status-badge-${t.task}`);
      if (!card || !badge) return;

      const isDone = doneTasks.has(t.task) || completedTasks.has(t.task);
      const isRunning = t.task === runningTask && st.status === "running";

      if (isDone) {
        card.classList.remove("running");
        card.classList.add("done");
        badge.innerHTML = `<span class="task-state-badge done">已完成</span>`;
      } else if (isRunning) {
        card.classList.add("running");
        badge.innerHTML = `<span class="task-state-badge running"><span class="spinner-tiny"></span> 执行中...</span>`;
      }
    });
  }
}

function finishExecution(st, isAllStages = false) {
  execSpinner.classList.remove("active");

  if (st.status === "done") {
    // 1. Record completed tasks from this execution
    (st.results || []).forEach((r) => {
      if (r.task) completedTasks.add(r.task);
    });

    const totalStages = currentPlan && currentPlan.execution ? currentPlan.execution.length : 1;
    const currentStageTasks = (currentPlan && currentPlan.execution && currentPlan.execution[currentActiveStep]) || [];
    currentStageTasks.forEach((task) => completedTasks.add(task));

    // Mark current stage pill as done
    const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
    if (stagePills[currentActiveStep]) {
      stagePills[currentActiveStep].classList.remove("running", "active");
      stagePills[currentActiveStep].classList.add("done");
    }

    // Mark current stage card as done
    currentStageTasks.forEach((task) => {
      const card = document.getElementById(`task-card-${task}`);
      const badge = document.getElementById(`task-status-badge-${task}`);
      if (card) {
        card.classList.remove("running");
        card.classList.add("done");
      }
      if (badge) {
        badge.innerHTML = `<span class="task-state-badge done">已完成</span>`;
      }
    });

    // 2. Check if there are next stages in the pipeline
    const isLastStage = currentActiveStep >= totalStages - 1;

    if (!isLastStage && !isAllStages) {
      // ════════════════════════════════════════════════════════════════════════
      // [STEP-BY-STEP PROGRESSION]: Smoothly advance to NEXT stage workbench
      // ════════════════════════════════════════════════════════════════════════
      currentActiveStep += 1;
      setActiveStep(currentActiveStep);

      taskStatusPill.className = "status-pill done";
      taskStatusPill.textContent = `阶段 ${currentActiveStep} 已完成 · 阶段 ${currentActiveStep + 1} 就绪`;
      if (execStatusTitle) {
        execStatusTitle.textContent = `阶段 ${currentActiveStep} 已完成 · 阶段 ${currentActiveStep + 1} 就绪`;
      }
      execProgressBar.style.width = "100%";

      btnExecutePlan.disabled = false;
      
      // Automatically switch back to Tab 1 (Task Plan) to show the next step card!
      switchTab("tab-plan");
      return;
    }

    // ════════════════════════════════════════════════════════════════════════
    // [FULL PIPELINE COMPLETED]: Terminal Target Artifact Delivery
    // ════════════════════════════════════════════════════════════════════════
    taskStatusPill.className = "status-pill done";
    taskStatusPill.textContent = "全部已完成";
    execStatusTitle.textContent = "流水线全部执行完成";
    if (execStatusSub) execStatusSub.textContent = "所有阶段任务已全部成功完成，最终目标产物已交付。";
    execProgressBar.style.width = "100%";

    btnExecutePlan.disabled = true;
        if (btnExecuteText) btnExecuteText.textContent = "全部阶段已执行完成 ✓";

    // Mark all stage pills as done
    stagePills.forEach((p) => {
      p.classList.remove("running", "active");
      p.classList.add("done");
    });

    // Reveal all cards now for complete review
    const allCards = planList.querySelectorAll(".task-card");
    allCards.forEach((card) => {
      card.style.display = "block";
    });

    // Re-fetch user context
    const ctx = getCtx();
    if (ctx.user_id) fetchUserContext(ctx.user_id);

    // Determine final target task
    const targetTask =
      currentPlan && currentPlan.plan && currentPlan.plan.length
        ? currentPlan.plan[currentPlan.plan.length - 1].task
        : "";
    const targetMeta = TASK_META[targetTask] || { name: "最终目标成果" };
    const targetOutputs = (st.outputs || []).filter((f) => isTargetTaskOutput(f, targetTask));
    const displayOuts = targetOutputs.length ? targetOutputs : st.outputs || [];
    const outCount = displayOuts.length;

    // ── Update Chat Delivery Card to clean 2-line format ──
    const deliveryCards = messagesContainer.querySelectorAll(".delivery-card");
    const deliveryCard = deliveryCards.length ? deliveryCards[deliveryCards.length - 1] : null;
    if (deliveryCard) {
      const primaryOutput = targetOutputs.length ? targetOutputs[0] : (st.outputs && st.outputs[0]) || targetDocName;
      const fileName = primaryOutput.split(/[\\/]/).pop();
      const cleanTaskName = targetMeta.name ? targetMeta.name.split(" ")[0] : "任务成果";

      deliveryCard.innerHTML = `
        <div class="delivery-header">
          <div class="delivery-check-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="16 9 10 15 7 12"/>
            </svg>
          </div>
          <div class="delivery-header-text">
            <div class="delivery-title" style="font-size: 14px; font-weight: 600;">成果已交付</div>
            <div class="delivery-body-two-lines">
              <div class="delivery-line-1" style="font-size: 13.5px;">【${escapeHtml(cleanTaskName)}】已经生成</div>
              <div class="delivery-line-2">
                <a class="delivery-action-link" id="btn-delivery-jump-output" href="javascript:void(0)">点击查看 ➔</a>
              </div>
            </div>
          </div>
        </div>
      `;

      const jumpLink = deliveryCard.querySelector("#btn-delivery-jump-output");
      if (jumpLink) {
        jumpLink.addEventListener("click", () => {
          switchTab("tab-outputs");
        });
      }
    }

    // Render Top Completion Banner on Task Plan Workbench
    const oldBanner = document.getElementById("pipeline-completion-banner");
    if (oldBanner) oldBanner.remove();

    const banner = document.createElement("div");
    banner.className = "pipeline-success-card";
    banner.id = "pipeline-completion-banner";
    banner.innerHTML = `
      <div class="success-icon-wrap">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="16 9 10 15 7 12"/></svg>
      </div>
      <div class="success-body">
        <div class="success-title">流水线全部执行完成 · 目标成果「${escapeHtml(targetMeta.name.split(" ")[0])}」已就绪</div>
        <div class="success-desc">前序所有中间资料已安全持久化存储；您可直接查阅最终生成的 ${outCount} 份核心成果。</div>
        <div class="success-actions">
          ${outCount > 0 ? `<button class="btn-success-action primary" id="btn-banner-view-outputs"><span>查看最终目标产物 ➔</span></button>` : ""}
          <button class="btn-success-action secondary" id="btn-banner-continue-chat"><span>在左侧继续问答 / 开启新任务</span></button>
        </div>
      </div>
    `;

    const btnViewOut = banner.querySelector("#btn-banner-view-outputs");
    if (btnViewOut) {
      btnViewOut.addEventListener("click", () => switchTab("tab-outputs"));
    }
    const btnContinue = banner.querySelector("#btn-banner-continue-chat");
    if (btnContinue) {
      btnContinue.addEventListener("click", () => {
        chatText.focus();
        chatText.placeholder = "针对已生成的资料向知识库提问，或输入新任务需求...";
      });
    }

    if (planList && planList.firstChild) {
      planList.insertBefore(banner, planList.firstChild);
    }

    // Render into Outputs Center ONLY when terminal target is reached
    if (st.outputs && st.outputs.length) {
      renderOutputsCenter(activeTaskId, st.outputs);
    }

    // 终态任务或单任务执行完毕后：直接切换至【产物中心】展示最终产物！
    switchTab("tab-outputs");
  } else {
    taskStatusPill.className = "status-pill failed";
    taskStatusPill.textContent = "执行失败";
    execStatusTitle.textContent = "任务执行出现异常";
    if (execStatusSub) execStatusSub.textContent = st.message || "请查看执行日志了解详情。";
    execProgressBar.style.width = "100%";
    btnExecutePlan.disabled = false;
        setActiveStep(currentActiveStep);
    alert(st.message || "执行失败，请检查参数与日志。");
  }
}

// ==========================================================================
// 5. Outputs Center & Online Artifact Viewer
// ==========================================================================

// Helper to determine if an output file belongs to the user's terminal target task
function isTargetTaskOutput(filePath, targetTask) {
  if (!targetTask) return true;
  const pathNorm = filePath.toLowerCase().replace(/\\/g, "/");
  const task = targetTask.toLowerCase();

  // 1. Strictly match directory path (e.g. /output/.../checklist/result_...)
  if (pathNorm.includes(`/${task}/`) || pathNorm.includes(`/${task}_`)) return true;

  // 2. Match patterns across full path
  const patterns = {
    checklist: ["checklist", "复习清单", "考点清单"],
    catalog: ["catalog", "知识大纲", "大纲", "目录"],
    quiz: ["quiz", "自测题", "试卷", "题目"],
    knowledge_graph: ["graph", "知识图谱", "图谱"],
    minutes_generation: ["minutes", "纪要", "会议纪要"],
    action_items: ["action", "待办", "行动项"],
    mindmap: ["mindmap", "思维导图", "导图"],
    risk: ["risk", "风险", "风险分析"],
    multi_styles: ["style", "多风格", "风格"],
    minutes_trace: ["trace", "溯源", "发言对齐"],
    ocr: ["ocr", "识别笔记"],
    library: ["library", "入库报告"],
  };

  const matches = patterns[task] || [task];
  return matches.some((keyword) => pathNorm.includes(keyword));
}

function renderOutputsCenter(taskId, outputs) {
  if (!outputs || !outputs.length) return;

  // Find the terminal target task of this pipeline
  const targetTask =
    currentPlan && currentPlan.plan && currentPlan.plan.length
      ? currentPlan.plan[currentPlan.plan.length - 1].task
      : "";

  // Collect target outputs (including both HTML and MD)
  let targetOutputs = outputs.filter((f) => isTargetTaskOutput(f, targetTask));
  if (!targetOutputs.length) {
    targetOutputs = outputs;
  }

  outputsEmpty.classList.add("hidden");
  outputsContainer.classList.remove("hidden");
  outputCountBadge.textContent = targetOutputs.length;
  outputCountBadge.classList.remove("hidden");

  const rowsWrap = $("outputs-rows-wrap");
  if (rowsWrap) {
    rowsWrap.innerHTML = "";

    targetOutputs.forEach((filePath) => {
      const name = filePath.split(/[\\/]/).pop();
      const ext = name.split(".").pop().toLowerCase();

      const item = document.createElement("div");
      item.className = "output-file-link-item";
      item.dataset.filename = name;
      item.title = `点击直接下载 ${name}`;

      item.innerHTML = `
        <span class="file-icon-badge">${escapeHtml(ext.toUpperCase())}</span>
        <span class="output-file-link-name">${escapeHtml(name)}</span>
        <span class="output-file-dl-hint">（点击直接下载）</span>
        <span class="output-row-state-chip">✓ 已就绪</span>
      `;

      // Click anywhere on the row / filename to trigger direct download
      item.addEventListener("click", () => {
        const url = `${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`;
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
      });

      rowsWrap.appendChild(item);
    });
  }

  // Find HTML output specifically for preview (or first item)
  const htmlFile = targetOutputs.find((f) => f.toLowerCase().endsWith(".html")) || targetOutputs[0];
  const htmlName = htmlFile.split(/[\\/]/).pop();
  previewHtmlArtifact(taskId, htmlName);
}

async function previewHtmlArtifact(taskId, name) {
  activeTaskId = taskId;
  activeOutputName = name;
  if (viewerFilename) viewerFilename.textContent = `成果预览 · ${name}`;

  viewerBody.innerHTML = '<div class="viewer-placeholder"><span class="spinner-ring active" style="display:inline-block; margin-right:8px;"></span> 正在加载产物预览...</div>';

  try {
    const res = await fetch(`${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error("获取产物失败");

    const text = await res.text();
    viewerBody.innerHTML = "";

    if (name.endsWith(".html")) {
      const iframe = document.createElement("iframe");
      iframe.className = "viewer-iframe";
      iframe.sandbox = "allow-scripts allow-same-origin allow-popups";
      // Inject 14px base font styling into HTML iframe
      const injectedHtml = text.replace(
        "<head>",
        "<head><style>body { font-size: 14px !important; line-height: 1.6 !important; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif !important; } h1 { font-size: 1.3rem !important; } h2 { font-size: 1.15rem !important; } h3 { font-size: 1.05rem !important; } p, li, td, th { font-size: 14px !important; }</style>"
      );
      iframe.srcdoc = injectedHtml;
      viewerBody.appendChild(iframe);
    } else {
      const mdDiv = document.createElement("div");
      mdDiv.className = "viewer-markdown";
      mdDiv.innerHTML = renderMarkdown(text);
      viewerBody.appendChild(mdDiv);
    }
  } catch (err) {
    viewerBody.innerHTML = `<div class="viewer-placeholder" style="color: var(--terra-600);">加载预览失败：${escapeHtml(err.message)}</div>`;
  }
}

async function previewArtifact(taskId, name) {
  activeTaskId = taskId;
  activeOutputName = name;
  viewerFilename.textContent = name;
  btnDownloadArtifact.disabled = false;
  btnFullscreenPreview.disabled = false;

  viewerBody.innerHTML = '<div class="viewer-placeholder"><span class="spinner-ring active" style="display:inline-block; margin-right:8px;"></span> 正在加载产物...</div>';

  try {
    const res = await fetch(`${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error("获取产物失败");

    const text = await res.text();
    viewerBody.innerHTML = "";

    if (name.endsWith(".html")) {
      // Sandboxed HTML preview for Meeting Minutes, Mindmaps, etc.
      const iframe = document.createElement("iframe");
      iframe.className = "viewer-iframe";
      iframe.sandbox = "allow-scripts allow-same-origin allow-popups";
      iframe.srcdoc = text;
      viewerBody.appendChild(iframe);
    } else if (name.endsWith(".md")) {
      // Rich Markdown Viewer
      const mdDiv = document.createElement("div");
      mdDiv.className = "viewer-markdown";
      mdDiv.innerHTML = renderMarkdown(text);
      viewerBody.appendChild(mdDiv);
    } else {
      // Raw Code / Text Viewer
      const pre = document.createElement("pre");
      pre.className = "console-content";
      pre.style.background = "#fff";
      pre.style.color = "#1f1f1f";
      pre.style.border = "1px solid var(--border-subtle)";
      pre.textContent = text;
      viewerBody.appendChild(pre);
    }
  } catch (err) {
    viewerBody.innerHTML = `<div class="viewer-placeholder" style="color: var(--google-red);">加载产物失败：${escapeHtml(err.message)}</div>`;
  }
}

// ==========================================================================
// 6. Markdown Parser & Helpers
// ==========================================================================

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

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatFileSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// Boot application
window.addEventListener("DOMContentLoaded", init);





// ==========================================================================
// User Sessions & History Engine (Matching img.png)
// ==========================================================================

let activeSessionId = getSessionId();

async function loadUserSessions() {
  const ctx = getCtx();
  if (!ctx.user_id) return;
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/sessions`);
    if (!res.ok) return;
    const data = await res.json();
    renderSidebarSessions(data.sessions || []);
  } catch (e) {
    console.warn("Failed to load user sessions:", e);
  }
}

function renderSidebarSessions(sessions) {
  const list = $("sidebar-sessions-list");
  if (!list) return;
  list.innerHTML = "";

  if (!sessions.length) {
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

async function switchSession(sessionId) {
  activeSessionId = sessionId;
  try {
    localStorage.setItem("agentflow_session", sessionId);
  } catch (e) {}

  const ctx = getCtx();
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/sessions/${sessionId}`);
    if (!res.ok) return;
    const data = await res.json();

    messagesContainer.innerHTML = "";
    if (chatWelcome && chatWelcome.parentNode === messagesContainer) {
      chatWelcome.remove();
    }

    (data.history || []).forEach((msg) => {
      if (msg.role === "user") {
        appendMessage("user", msg.content);
      } else {
        appendChatMessage({ answer: msg.content });
      }
    });

    loadUserSessions();
  } catch (e) {
    console.warn("Failed to switch session:", e);
  }
}

async function deleteSession(sessionId) {
  const ctx = getCtx();
  try {
    await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/sessions/${sessionId}`, { method: "DELETE" });
    if (activeSessionId === sessionId) {
      activeSessionId = "web_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      try { localStorage.setItem("agentflow_session", activeSessionId); } catch (e) {}
      resetWorkspace();
    }
    loadUserSessions();
  } catch (e) {
    console.warn("Failed to delete session:", e);
  }
}

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



// ==========================================================================
// Knowledge Base Assets & Outputs Cloud Disk Engine
// ==========================================================================

async function loadUserOutputsDisk() {
  const ctx = getCtx();
  if (!ctx.user_id) return;
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/outputs`);
    if (!res.ok) return;
    const data = await res.json();
    const outputs = data.outputs || [];

    renderSidebarOutputsDrawer(outputs);
  } catch (e) {
    console.warn("Failed to load user outputs disk:", e);
  }
}

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

async function previewHistoricalOutput(relPath, name) {
  outputsEmpty.classList.add("hidden");
  outputsContainer.classList.remove("hidden");

  if (viewerFilename) viewerFilename.textContent = `云盘成果 · ${name}`;
  viewerBody.innerHTML = '<div class="viewer-placeholder"><span class="spinner-ring active" style="display:inline-block; margin-right:8px;"></span> 正在加载产物预览...</div>';

  if (btnDownloadArtifact) {
    btnDownloadArtifact.disabled = false;
    btnDownloadArtifact.onclick = () => {
      const url = `${API}/outputs/file/${encodeURIComponent(relPath)}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    };
  }

  try {
    const res = await fetch(`${API}/outputs/file/${encodeURIComponent(relPath)}`);
    if (!res.ok) throw new Error("获取产物失败");

    const text = await res.text();
    viewerBody.innerHTML = "";

    if (name.endsWith(".html")) {
      const iframe = document.createElement("iframe");
      iframe.className = "viewer-iframe";
      iframe.sandbox = "allow-scripts allow-same-origin allow-popups";
      const injectedHtml = text.replace(
        "<head>",
        "<head><style>body { font-size: 14px !important; line-height: 1.6 !important; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important; } h1 { font-size: 1.25rem !important; } h2 { font-size: 1.12rem !important; } h3 { font-size: 1.02rem !important; } p, li, td, th { font-size: 14px !important; }</style>"
      );
      iframe.srcdoc = injectedHtml;
      viewerBody.appendChild(iframe);
    } else {
      const mdDiv = document.createElement("div");
      mdDiv.className = "viewer-markdown";
      mdDiv.innerHTML = renderMarkdown(text);
      viewerBody.appendChild(mdDiv);
    }
  } catch (err) {
    viewerBody.innerHTML = `<div class="viewer-placeholder" style="color: var(--terra-600);">加载预览失败：${escapeHtml(err.message)}</div>`;
  }
}

function updateKnowledgeBaseDrawer(ctxData) {
  const subjectsList = $("kb-subjects-list");
  const totalBadge = $("sidebar-kb-total-count");

  const subjects = ctxData.subjects || [];

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
          chatText.focus();
        });
        subjectsList.appendChild(chip);
      });
    }
  }
}

