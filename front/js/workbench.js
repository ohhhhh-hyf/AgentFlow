// ==========================================================================
// AgentFlow Front-end · Pipeline DAG Workbench, Execution & Outputs Engine
// ==========================================================================
"use strict";

// Dynamically update Context Bar visibility based on Plan tasks
function updateContextBarVisibility(plan) {
  if (!plan || !plan.length) {
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

    const missing = t.missing || [];
    if (missing.includes("subject")) {
      subjectRequired = true;
    }
  });

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

  if (planCountBadge) {
    planCountBadge.textContent = plan.length;
    planCountBadge.classList.toggle("hidden", plan.length === 0);
  }

  if (workbenchPipelineHeader) workbenchPipelineHeader.classList.remove("hidden");
  if (planEmpty) planEmpty.classList.add("hidden");
  if (planContainer) planContainer.classList.remove("hidden");

  updateContextBarVisibility(plan);

  currentActiveStep = 0;
  renderPipelineVisual(execution);

  if (planList) {
    planList.innerHTML = "";
    plan.forEach((item, idx) => {
      const card = createTaskCard(item, idx);
      planList.appendChild(card);
    });
  }

  setActiveStep(0);
  syncContextToPlan();
  validatePlanParams();
}

function renderPipelineVisual(execution) {
  if (!pipelineVisual) return;
  pipelineVisual.innerHTML = "";
  const hasParallel = execution.some((g) => g.length > 1);
  if (pipelineStagesText) {
    pipelineStagesText.textContent = `共 ${execution.length} 个执行阶段${hasParallel ? " (含多任务并发加速)" : ""}`;
  }

  execution.forEach((group, gIdx) => {
    const pill = document.createElement("div");
    pill.className = "stage-pill";
    pill.dataset.step = gIdx;
    if (gIdx === currentActiveStep) {
      pill.classList.add("active");
    }

    const isParallel = group.length > 1;
    const hasDynamicTask =
      currentPlan &&
      currentPlan.plan &&
      group.some((task) => {
        const item = currentPlan.plan.find((p) => p.task === task);
        return item && item.dynamic;
      });
    const taskNames = group
      .map((t) => (TASK_META[t] ? TASK_META[t].name.split(" ")[0] : t))
      .join(" ‖ ");

    const parallelTag = isParallel
      ? `<span class="badge-parallel">${group.length}项并行</span>`
      : "";
    const dynamicTag = hasDynamicTask
      ? `<span class="badge-parallel" style="background:#fff4dc;color:#8a570f;border-color:#f3d58e;">动态</span>`
      : "";

    pill.innerHTML = `<strong>阶段 ${gIdx + 1}</strong>${parallelTag}${dynamicTag}: ${escapeHtml(taskNames)}`;

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
  if (!currentPlan || !currentPlan.plan || !messagesContainer) return;

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

  if (pipelineVisual) {
    const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
    stagePills.forEach((pill, idx) => {
      if (idx === currentActiveStep) {
        pill.classList.add("active");
      } else {
        pill.classList.remove("active");
      }
    });
  }

  if (planList) {
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
  }

  if (btnExecuteText) {
    btnExecuteText.textContent = "执行 ➔";
  }

  syncChatTableStatus();
}

// Determine if a task's input is automatically supplied by an upstream task
function getUpstreamProvider(taskName, plan, execution) {
  if (!plan || !plan.length) return null;

  const planTasks = plan.map((t) => t.task);
  const taskEntry = plan.find((t) => t.task === taskName);
  const needs = taskEntry ? (taskEntry.needs || []) : [];

  if (taskName === "library" && (needs.includes("ocr") || planTasks.includes("ocr"))) {
    return {
      param: "file",
      upstreamTask: "ocr",
      upstreamName: "OCR 图片识别",
      desc: "无需手动上传文件。将直接使用前序「OCR 图片识别」生成的结构化 Markdown 产物作为入库文件。"
    };
  }

  if ((taskName === "catalog" || taskName === "checklist") && (needs.includes("library") || planTasks.includes("library"))) {
    return {
      param: "file",
      upstreamTask: "library",
      upstreamName: "知识资料结构化入库",
      desc: "无需上传附件。将直接基于上游入库构建的向量知识库生成知识目录与考点清单。"
    };
  }

  const meetingSubtasks = ["action_items", "mindmap", "risk", "minutes_trace", "multi_styles"];
  if (meetingSubtasks.includes(taskName) && planTasks.includes("minutes_generation") && taskName !== "minutes_generation") {
    return {
      param: "file",
      upstreamTask: "minutes_generation",
      upstreamName: "会议纪要生成",
      desc: "无需重复上传。将直接复用上游「会议纪要生成」上传的会议原文与提炼的纪要数据。"
    };
  }

  if ((taskName === "quiz" || taskName === "review") && (needs.includes("ocr") || planTasks.includes("ocr"))) {
    return {
      param: "file",
      upstreamTask: "ocr",
      upstreamName: "OCR 图片识别",
      desc: "无需手动上传。将直接基于前序「OCR 图片识别」的笔记文本进行出题或审校。"
    };
  }

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

  const upstreamInfo = getUpstreamProvider(item.task, currentPlan.plan, currentPlan.execution);
  if (upstreamInfo && upstreamInfo.param) {
    item._pendingMissing = item._pendingMissing.filter((p) => p !== upstreamInfo.param);
  }

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

  if (item.dynamic) {
    tags.innerHTML += `<span class="tag-badge" style="background:#fff4dc;color:#8a570f;border:1px solid #f3d58e;">Supervisor 动态插入</span>`;
  }

  header.appendChild(titleWrap);
  header.appendChild(tags);

  const statusWrap = document.createElement("div");
  statusWrap.className = "task-status-wrap";
  statusWrap.id = `task-status-badge-${item.task}`;
  header.appendChild(statusWrap);

  card.appendChild(header);

  const desc = document.createElement("div");
  desc.className = "task-note-text";
  desc.textContent = item.note || meta.desc || "待执行流水线任务节点";
  card.appendChild(desc);

  if (item.dynamic && item.dynamic_reason) {
    const dynamicTip = document.createElement("div");
    dynamicTip.className = "supervisor-task-tip";
    dynamicTip.style.cssText = "margin:10px 0 0;padding:10px 12px;border:1px solid #f3d58e;background:#fff8e8;color:#704b10;border-radius:10px;font-size:13px;line-height:1.5;";
    dynamicTip.innerHTML = `<strong>Supervisor 观察：</strong>${escapeHtml(item.dynamic_reason)}`;
    card.appendChild(dynamicTip);
  }

  const paramsSec = document.createElement("div");
  paramsSec.className = "params-section";

  const missing = item.missing || [];
  if (missing.length || upstreamInfo) {
    const reqGroup = document.createElement("div");
    reqGroup.className = "req-params-group";

    if (upstreamInfo) {
      const flowCard = createUpstreamFlowCard(upstreamInfo);
      reqGroup.appendChild(flowCard);
    }

    missing.forEach((param) => {
      if ((param === "file" || param === "input") && (!upstreamInfo || upstreamInfo.param !== param)) {
        const dropzoneWrap = createDropzone(item, param);
        reqGroup.appendChild(dropzoneWrap);
      }
    });

    paramsSec.appendChild(reqGroup);
  }

  // Optional Keypoints input for Catalog & Checklist
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

  const optAccordion = createOptionalAccordion(item);
  if (optAccordion) {
    paramsSec.appendChild(optAccordion);
  }

  // Template Customization Section for Minutes, Risk, Action Items, Mindmap, Knowledge Graph (placed below optional accordion)
  const templateSec = createTaskTemplateSection(item);
  if (templateSec) {
    paramsSec.appendChild(templateSec);
  }

  card.appendChild(paramsSec);
  return card;
}

// Tasks that support template customization
const TEMPLATE_SUPPORTED_TASKS = new Set([
  "minutes_generation",
  "risk",
  "action_items",
  "mindmap",
  "knowledge_graph"
]);

function createTaskTemplateSection(item) {
  if (!TEMPLATE_SUPPORTED_TASKS.has(item.task)) return null;

  const wrap = document.createElement("div");
  wrap.className = "task-template-section";
  wrap.id = `template-section-${item.task}`;

  wrap.innerHTML = `
    <div class="template-section-header">
      <div class="template-section-title">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10 9 9 9 8 9"/>
        </svg>
        <span>输出模板（选填）</span>
      </div>
      <span class="template-active-badge" id="tpl-badge-${item.task}" style="display:none;">已定制模板 ✓</span>
    </div>

    <!-- Mode Selector Tabs -->
    <div class="template-mode-tabs">
      <button type="button" class="tpl-tab-btn active" data-mode="preset">内置模板选择</button>
      <button type="button" class="tpl-tab-btn" data-mode="upload">上传模板文件</button>
      <button type="button" class="tpl-tab-btn" data-mode="natural">自然语言描述生成</button>
    </div>

    <!-- Mode 1: Preset Templates (Cascading Selector to Right) -->
    <div class="tpl-pane tpl-pane-preset" id="tpl-pane-preset-${item.task}">
      <div class="tpl-preset-controls">
        <div class="tpl-cascade-dropdown-wrap" id="tpl-cascade-wrap-${item.task}">
          <button type="button" class="tpl-cascade-trigger" id="tpl-cascade-trigger-${item.task}">
            <span class="tpl-cascade-trigger-text" id="tpl-cascade-text-${item.task}">不使用模板（默认）</span>
            <svg class="tpl-cascade-arrow" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>

          <!-- Cascading Menu (Flyout to Right) -->
          <div class="tpl-cascade-menu hidden" id="tpl-cascade-menu-${item.task}">
            <div class="tpl-cascade-scenarios" id="tpl-cascade-scenarios-${item.task}"></div>
            <div class="tpl-cascade-subpanel" id="tpl-cascade-subpanel-${item.task}"></div>
          </div>
        </div>
        <button type="button" class="btn-tpl-preview-preset" id="btn-tpl-preview-preset-${item.task}">查看模板内容</button>
      </div>
      <div class="tpl-preset-preview-box hidden" id="tpl-preset-preview-${item.task}">
        <pre class="tpl-code-block"></pre>
      </div>
    </div>

    <!-- Mode 2: Upload File -->
    <div class="tpl-pane tpl-pane-upload hidden" id="tpl-pane-upload-${item.task}">
      <div class="tpl-upload-row">
        <label class="btn-upload-tpl">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
          </svg>
          <span>上传自定义模板 (.md / .txt)</span>
          <input type="file" class="tpl-file-input" style="display:none;" accept=".md,.txt,.markdown" />
        </label>
        <span class="tpl-upload-status" id="tpl-upload-status-${item.task}">未选择文件</span>
      </div>
      <div class="tpl-upload-preview-box hidden" id="tpl-upload-preview-${item.task}">
        <textarea class="tpl-editable-textarea" rows="5" placeholder="模板内容预览与编辑..."></textarea>
      </div>
    </div>

    <!-- Mode 3: Natural Language Description -->
    <div class="tpl-pane tpl-pane-natural hidden" id="tpl-pane-natural-${item.task}">
      <div class="tpl-natural-input-wrap">
        <textarea class="tpl-natural-textarea" id="tpl-natural-text-${item.task}" rows="3" placeholder="请用自然语言描述您想要的版式要求（例如：包含会议基本信息、各方发言要点、主要风险与待办清单表...）"></textarea>
        <div class="tpl-natural-hint-row">
          <span class="tpl-natural-tip">已启用自然语言定制版式：填写后可直接点击执行流水线，系统将按此要求自动排版输出。</span>
        </div>
      </div>
    </div>
  `;

  // Default: no template selected (original standard minutes)
  delete item.params.template;
  delete item.params.template_content;

  const cascadeWrap = wrap.querySelector(`#tpl-cascade-wrap-${item.task}`);
  const cascadeTrigger = wrap.querySelector(`#tpl-cascade-trigger-${item.task}`);
  const cascadeText = wrap.querySelector(`#tpl-cascade-text-${item.task}`);
  const cascadeMenu = wrap.querySelector(`#tpl-cascade-menu-${item.task}`);
  const cascadeScenarios = wrap.querySelector(`#tpl-cascade-scenarios-${item.task}`);
  const cascadeSubpanel = wrap.querySelector(`#tpl-cascade-subpanel-${item.task}`);
  const presetPreviewBtn = wrap.querySelector(`#btn-tpl-preview-preset-${item.task}`);
  const presetPreviewBox = wrap.querySelector(`#tpl-preset-preview-${item.task}`);
  const badge = wrap.querySelector(`#tpl-badge-${item.task}`);

  let loadedTemplates = [];
  let scenarioGroups = {};
  let currentHoveredScenario = "";

  function renderSubpanel(scenarioName) {
    if (!cascadeSubpanel) return;
    cascadeSubpanel.innerHTML = "";
    const items = scenarioGroups[scenarioName] || [];
    if (!items.length) {
      cascadeSubpanel.innerHTML = `<div class="tpl-cascade-empty-hint">暂无可用模板</div>`;
      return;
    }
    items.forEach((tpl) => {
      const leaf = document.createElement("div");
      const isSelected = item.params.template === tpl.filename;
      leaf.className = `tpl-cascade-leaf ${isSelected ? "selected" : ""}`;
      leaf.innerHTML = `
        <span>${escapeHtml(tpl.title)}</span>
        ${isSelected ? '<span class="tpl-cascade-check">✓</span>' : ""}
      `;
      leaf.addEventListener("click", (e) => {
        e.stopPropagation();
        item.params.template = tpl.filename;
        delete item.params.template_content;
        if (cascadeText) cascadeText.textContent = tpl.title;
        if (badge) {
          badge.textContent = `已定制模板: ${tpl.title} ✓`;
          badge.style.display = "inline-flex";
        }
        if (cascadeMenu) cascadeMenu.classList.add("hidden");
        if (cascadeTrigger) cascadeTrigger.classList.remove("active");
        if (presetPreviewBox && !presetPreviewBox.classList.contains("hidden")) {
          const codeBlock = presetPreviewBox.querySelector(".tpl-code-block");
          if (codeBlock) codeBlock.textContent = tpl.content;
        }
        validatePlanParams();
      });
      cascadeSubpanel.appendChild(leaf);
    });
  }

  function renderScenarios() {
    if (!cascadeScenarios) return;
    cascadeScenarios.innerHTML = "";

    // Clear / Reset to No Template option
    const resetRow = document.createElement("div");
    const isResetSelected = !item.params.template && !item.params.template_content;
    resetRow.className = `tpl-scenario-item tpl-scenario-reset ${isResetSelected ? "selected-reset" : ""}`;
    resetRow.innerHTML = `
      <span style="font-weight:600;">不使用模板（默认）</span>
      ${isResetSelected ? '<span class="tpl-cascade-check">✓</span>' : ""}
    `;
    resetRow.addEventListener("mouseenter", () => {
      currentHoveredScenario = "";
      cascadeScenarios.querySelectorAll(".tpl-scenario-item").forEach((el) => el.classList.remove("active"));
      resetRow.classList.add("active");
      if (cascadeSubpanel) {
        cascadeSubpanel.innerHTML = `<div class="tpl-cascade-empty-hint">当前模式：不使用任何模板<br/>（使用系统标准原始纪要）</div>`;
      }
    });
    resetRow.addEventListener("click", (e) => {
      e.stopPropagation();
      delete item.params.template;
      delete item.params.template_content;
      if (cascadeText) cascadeText.textContent = "不使用模板（默认）";
      if (badge) badge.style.display = "none";
      if (cascadeMenu) cascadeMenu.classList.add("hidden");
      if (cascadeTrigger) cascadeTrigger.classList.remove("active");
      if (presetPreviewBox) presetPreviewBox.classList.add("hidden");
      validatePlanParams();
    });
    cascadeScenarios.appendChild(resetRow);

    // Scenario categories
    Object.keys(scenarioGroups).forEach((scName) => {
      const row = document.createElement("div");
      row.className = `tpl-scenario-item ${scName === currentHoveredScenario ? "active" : ""}`;
      row.innerHTML = `
        <span>${escapeHtml(scName)}场景</span>
        <span class="tpl-scenario-arrow">›</span>
      `;
      row.addEventListener("mouseenter", () => {
        currentHoveredScenario = scName;
        cascadeScenarios.querySelectorAll(".tpl-scenario-item").forEach((el) => el.classList.remove("active"));
        row.classList.add("active");
        renderSubpanel(scName);
      });
      row.addEventListener("click", (e) => {
        e.stopPropagation();
        currentHoveredScenario = scName;
        cascadeScenarios.querySelectorAll(".tpl-scenario-item").forEach((el) => el.classList.remove("active"));
        row.classList.add("active");
        renderSubpanel(scName);
      });
      cascadeScenarios.appendChild(row);
    });

    if (currentHoveredScenario) {
      renderSubpanel(currentHoveredScenario);
    } else {
      if (cascadeSubpanel) {
        cascadeSubpanel.innerHTML = `<div class="tpl-cascade-empty-hint">← 悬停左侧场景浏览对应模板<br/>（默认不使用模板）</div>`;
      }
    }
  }

  if (cascadeTrigger && cascadeMenu) {
    cascadeTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isHidden = cascadeMenu.classList.contains("hidden");
      document.querySelectorAll(".tpl-cascade-menu").forEach((m) => m.classList.add("hidden"));
      document.querySelectorAll(".tpl-cascade-trigger").forEach((t) => t.classList.remove("active"));
      if (isHidden) {
        cascadeMenu.classList.remove("hidden");
        cascadeTrigger.classList.add("active");
        const curTpl = loadedTemplates.find((t) => t.filename === item.params.template);
        if (curTpl && curTpl.scenario) {
          currentHoveredScenario = curTpl.scenario;
        } else {
          currentHoveredScenario = "";
        }
        renderScenarios();
      }
    });

    document.addEventListener("click", (e) => {
      if (cascadeWrap && !cascadeWrap.contains(e.target)) {
        cascadeMenu.classList.add("hidden");
        cascadeTrigger.classList.remove("active");
      }
    });
  }

  // Fetch preset templates on load
  fetch(`${API}/templates/${encodeURIComponent(item.task)}`)
    .then((r) => r.json())
    .then((d) => {
      if (d.templates && d.templates.length) {
        loadedTemplates = d.templates;
        scenarioGroups = {};
        d.templates.forEach((tpl) => {
          const sc = tpl.scenario || "通用";
          if (!scenarioGroups[sc]) scenarioGroups[sc] = [];
          scenarioGroups[sc].push(tpl);
        });

        if (item.params.template) {
          const curTpl = d.templates.find((t) => t.filename === item.params.template);
          if (curTpl) {
            if (cascadeText) cascadeText.textContent = curTpl.title;
            if (badge) {
              badge.textContent = `已定制模板: ${curTpl.title} ✓`;
              badge.style.display = "inline-flex";
            }
          }
        }
      }
    })
    .catch(() => {});

  // Wire up tabs
  const tabBtns = wrap.querySelectorAll(".tpl-tab-btn");
  const panes = {
    preset: wrap.querySelector(`#tpl-pane-preset-${item.task}`),
    upload: wrap.querySelector(`#tpl-pane-upload-${item.task}`),
    natural: wrap.querySelector(`#tpl-pane-natural-${item.task}`),
  };

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.mode;
      Object.entries(panes).forEach(([k, p]) => {
        if (p) p.classList.toggle("hidden", k !== mode);
      });
      validatePlanParams();
    });
  });

  if (presetPreviewBtn && presetPreviewBox) {
    presetPreviewBtn.addEventListener("click", () => {
      if (!item.params.template) {
        alert("当前为默认无模板模式（使用系统标准原始纪要）。如需使用定制模板，请先在下拉菜单中选择一个具体模板。");
        return;
      }
      const curTpl = loadedTemplates.find((t) => t.filename === item.params.template);
      const content = curTpl ? curTpl.content : "";
      if (!content) {
        alert("未能读取到所选模板内容");
        return;
      }
      const codeBlock = presetPreviewBox.querySelector(".tpl-code-block");
      if (codeBlock) codeBlock.textContent = content;
      presetPreviewBox.classList.toggle("hidden");
    });
  }

  // Upload file handling
  const fileInput = wrap.querySelector(".tpl-file-input");
  const uploadStatus = wrap.querySelector(`#tpl-upload-status-${item.task}`);
  const uploadPreviewBox = wrap.querySelector(`#tpl-upload-preview-${item.task}`);
  const uploadTextarea = uploadPreviewBox ? uploadPreviewBox.querySelector(".tpl-editable-textarea") : null;

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = (e.target.result || "").trim();
        item.params.template_content = content;
        delete item.params.template;
        if (uploadStatus) {
          uploadStatus.innerHTML = `<span style="color:#0d47a1; font-weight:600;">已加载：${escapeHtml(file.name)}</span>`;
        }
        if (uploadTextarea) uploadTextarea.value = content;
        if (uploadPreviewBox) uploadPreviewBox.classList.remove("hidden");
        if (badge) badge.style.display = "inline-flex";
        validatePlanParams();
      };
      reader.readAsText(file, "utf-8");
    });
  }

  if (uploadTextarea) {
    uploadTextarea.addEventListener("input", () => {
      item.params.template_content = uploadTextarea.value.trim();
      delete item.params.template;
      validatePlanParams();
    });
  }

  // Natural language description handling (direct input & execute)
  const naturalText = wrap.querySelector(`#tpl-natural-text-${item.task}`);
  if (naturalText) {
    naturalText.addEventListener("input", () => {
      const val = naturalText.value.trim();
      if (val) {
        item.params.template_content = val;
        delete item.params.template;
        if (badge) badge.style.display = "inline-flex";
      } else {
        delete item.params.template_content;
        if (badge && !item.params.template) badge.style.display = "none";
      }
      validatePlanParams();
    });
  }

  return wrap;
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
  accordion.open = true;

  const summary = document.createElement("summary");
  summary.innerHTML = `
    <span>高级可选配置 (选填)</span>
    <span style="font-size: 0.72rem; color: var(--text-muted);">收起 ▴</span>
  `;
  accordion.appendChild(summary);

  const content = document.createElement("div");
  content.className = "optional-content";

  // 1. Linked User Persona Profile (自动关联的用户视角画像)
  const ctx = getCtx();
  const prof = (currentUserContext && currentUserContext.profile) || {};
  const currentPersonaLabel = prof.template_label || prof.role || "客观 · 客观全员";

  const personaCard = document.createElement("div");
  personaCard.className = "linked-persona-card";
  personaCard.innerHTML = `
    <div class="linked-persona-row">
      <div class="persona-tag-wrap">
        <span class="persona-icon-circle">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
            <path d="M12 2C12 7.52 7.52 12 2 12C7.52 12 12 16.48 12 22C12 16.48 16.48 12 22 12C16.48 12 12 7.52 12 2Z"/>
          </svg>
        </span>
        <span class="persona-title">已关联视角画像：</span>
        <span class="persona-role-badge" id="task-persona-badge">${escapeHtml(currentPersonaLabel)}</span>
      </div>
      <button type="button" class="btn-switch-persona" title="快速切换或设定当前职业视角">切换职业 ▾</button>
    </div>
    <div class="persona-quick-chips hidden" id="persona-quick-chips">
      <button type="button" class="persona-chip" data-role="客观全员">客观全员</button>
      <button type="button" class="persona-chip" data-role="开发人员">开发人员</button>
      <button type="button" class="persona-chip" data-role="产品经理">产品经理</button>
      <button type="button" class="persona-chip" data-role="项目经理">项目经理</button>
      <button type="button" class="persona-chip" data-role="测试工程师">测试工程师</button>
      <button type="button" class="persona-chip" data-role="算法工程师">算法工程师</button>
      <button type="button" class="persona-chip" data-role="客户经理">客户经理</button>
    </div>
  `;

  const btnSwitch = personaCard.querySelector(".btn-switch-persona");
  const chipsWrap = personaCard.querySelector("#persona-quick-chips");
  if (btnSwitch && chipsWrap) {
    btnSwitch.addEventListener("click", (e) => {
      e.stopPropagation();
      chipsWrap.classList.toggle("hidden");
    });
  }

  personaCard.querySelectorAll(".persona-chip").forEach((chip) => {
    chip.addEventListener("click", async (e) => {
      e.stopPropagation();
      const targetRole = chip.getAttribute("data-role");
      const ctxNow = getCtx();
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
              const badge = personaCard.querySelector("#task-persona-badge");
              if (badge) badge.textContent = d.profile.template_label || targetRole;
              chipsWrap.classList.add("hidden");
            }
          }
        } catch (err) {
          console.warn("Failed to switch profile:", err);
        }
      }
    });
  });

  content.appendChild(personaCard);

  // 2. Other Optional Inputs
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

    if (ctx.user_id) {
      t.params.user_id = ctx.user_id;
    } else {
      delete t.params.user_id;
    }

    const domain = t.domain || (TASK_META[t.task] ? TASK_META[t.task].domain : "");

    if (domain === "meeting") {
      delete t.params.subject;
      if (ctx.project) {
        t.params.project = ctx.project;
      } else {
        delete t.params.project;
      }
    }

    if (domain === "notes") {
      delete t.params.project;
      if (ctx.subject) {
        t.params.subject = ctx.subject;
      } else {
        delete t.params.subject;
      }
    }

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

  if (!ctx.user_id) {
    pending.push("用户 ID (必填)");
    if (ctxUser) ctxUser.classList.add("input-error");
  } else {
    if (ctxUser) ctxUser.classList.remove("input-error");
  }

  const currentStageTasks = new Set(
    (currentPlan.execution && currentPlan.execution[currentActiveStep]) || []
  );

  let hasSubjectError = false;
  currentPlan.plan.forEach((t) => {
    if (!currentStageTasks.has(t.task) || completedTasks.has(t.task)) {
      return;
    }

    const meta = TASK_META[t.task] || { name: t.task };
    const missing = t.missing || [];
    const upstreamInfo = getUpstreamProvider(t.task, currentPlan.plan, currentPlan.execution);

    if (missing.includes("subject") && !ctx.subject) {
      if (!hasSubjectError) {
        pending.push("所属学科 (必填)");
        hasSubjectError = true;
      }
    }

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

  if (ctxSubject) {
    if (hasSubjectError) {
      ctxSubject.classList.add("input-error");
    } else {
      ctxSubject.classList.remove("input-error");
    }
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

  if (btnExecutePlan) {
    if (pending.length) {
      btnExecutePlan.disabled = true;
    } else {
      btnExecutePlan.disabled = false;
    }
  }

  if (validationTip && validationTipText) {
    if (displayPending.length) {
      validationTip.classList.remove("hidden");
      validationTipText.textContent = `待补全项：${displayPending.join("；")}`;
    } else {
      validationTip.classList.add("hidden");
    }
  }
}

function applySupervisorPlanUpdate(st) {
  if (!st || !st.plan_updated || !st.plan || !st.plan.plan || !currentPlan) return false;

  const before = (currentPlan.plan || []).map((t) => t.task).join(",");
  const after = (st.plan.plan || []).map((t) => t.task).join(",");
  if (before === after && JSON.stringify(currentPlan.execution || []) === JSON.stringify(st.plan.execution || [])) {
    return false;
  }

  currentPlan = st.plan;

  if (planCountBadge) {
    const count = (currentPlan.plan || []).length;
    planCountBadge.textContent = count;
    planCountBadge.classList.toggle("hidden", count === 0);
  }

  renderPipelineVisual(currentPlan.execution || [[...(currentPlan.plan || []).map((p) => p.task)]]);

  if (planList) {
    planList.innerHTML = "";
    if (st.replan_events && st.replan_events.length) {
      const banner = document.createElement("div");
      banner.id = "supervisor-replan-banner";
      banner.className = "pipeline-success-card";
      banner.style.cssText = "margin-bottom:14px;border:1px solid #f3d58e;background:#fff8e8;";
      const eventItems = st.replan_events
        .map((evt) => `<li>${escapeHtml(evt.reason || evt.type || "计划已调整")}</li>`)
        .join("");
      banner.innerHTML = `
        <div class="success-icon-wrap" style="background:#b7791f;color:#fff;">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M12 2v6M12 16v6M4.93 4.93l4.24 4.24M14.83 14.83l4.24 4.24M2 12h6M16 12h6M4.93 19.07l4.24-4.24M14.83 9.17l4.24-4.24"/>
          </svg>
        </div>
        <div class="success-body">
          <div class="success-title" style="color:#704b10;">Supervisor 已动态重规划</div>
          <div class="success-desc" style="color:#704b10;">系统在阶段执行后观察到后续目标需要补充步骤，已刷新右侧流水线。</div>
          <ul style="margin:8px 0 0;padding-left:18px;color:#704b10;font-size:13px;">${eventItems}</ul>
        </div>
      `;
      planList.appendChild(banner);
    }
    (currentPlan.plan || []).forEach((item, idx) => {
      const card = createTaskCard(item, idx);
      if (completedTasks.has(item.task)) {
        card.classList.add("done");
        const badge = card.querySelector(`#task-status-badge-${item.task}`);
        if (badge) badge.innerHTML = `<span class="task-state-badge done">已完成</span>`;
      }
      planList.appendChild(card);
    });
  }

  const stageIdx = (currentPlan.execution || []).findIndex((group) =>
    group.some((task) => !completedTasks.has(task))
  );
  currentActiveStep = stageIdx >= 0 ? stageIdx : Math.max(0, (currentPlan.execution || []).length - 1);
  setActiveStep(currentActiveStep);
  validatePlanParams();

  if (consoleLogs && st.replan_events && st.replan_events.length) {
    const lines = st.replan_events.map((evt) => `[Supervisor] ${evt.reason || evt.type || "计划已调整"}`);
    consoleLogs.textContent += `\n${lines.join("\n")}\n`;
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
  }
  return true;
}

async function executeCurrentPlan(isAllStages = false) {
  if (!currentPlan) return;

  validatePlanParams();
  if (btnExecutePlan && btnExecutePlan.disabled) return;

  if (btnExecutePlan) btnExecutePlan.disabled = true;
  if (btnExecuteText) btnExecuteText.textContent = "正在执行...";

  if (typeof switchTab === "function") switchTab("tab-logs");
  if (taskStatusPill) {
    taskStatusPill.className = "status-pill running";
    taskStatusPill.textContent = `阶段 ${currentActiveStep + 1} 执行中`;
    taskStatusPill.classList.remove("hidden");
  }
  if (execSpinner) execSpinner.classList.add("active");
  if (execStatusTitle) {
    execStatusTitle.textContent = `正在执行第 ${currentActiveStep + 1} 阶段...`;
  }
  if (consoleLogs) consoleLogs.textContent = "";

  const totalStages = currentPlan.execution ? currentPlan.execution.length : 1;
  const currentStageTasks = (currentPlan.execution && currentPlan.execution[currentActiveStep]) || [];

  try {
    let stagePayload = null;
    if (isAllStages) {
      const remainingStages = currentPlan.execution.slice(currentActiveStep);
      const remainingTaskNames = new Set(remainingStages.flat());
      const remainingPlanTasks = currentPlan.plan.filter((t) => remainingTaskNames.has(t.task));
      stagePayload = {
        ...currentPlan,
        plan: remainingPlanTasks,
        execution: remainingStages,
        full_plan: currentPlan,
      };
    } else {
      const currentPlanTasks = currentPlan.plan.filter((t) => currentStageTasks.includes(t.task));
      stagePayload = {
        ...currentPlan,
        plan: currentPlanTasks,
        execution: [currentStageTasks],
        full_plan: currentPlan,
      };
    }

    const ctx = getCtx();
    stagePayload.user_id = ctx.user_id || "default_user";

    currentStageTasks.forEach((task) => {
      const card = document.getElementById(`task-card-${task}`);
      const badge = document.getElementById(`task-status-badge-${task}`);
      if (card) card.classList.add("running");
      if (badge) badge.innerHTML = `<span class="task-state-badge running"><span class="spinner-tiny"></span> 执行中...</span>`;
      syncChatTableStatus(task);
    });

    if (pipelineVisual) {
      const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
      if (stagePills[currentActiveStep]) {
        stagePills[currentActiveStep].classList.add("running");
      }
    }

    const fd = new FormData();
    fd.append("plan_json", JSON.stringify(stagePayload));

    uploadsMap.forEach((files) => {
      files.forEach((f) => fd.append("files", f, f.name));
    });

    const res = await fetch(`${API}/tasks`, { method: "POST", body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "后端拒绝执行任务");
    }

    activeTaskId = data.task_id;
    if (consoleLogs) {
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
      consoleLogs.textContent = `[${timeStr}] 阶段任务已提交，Task ID: ${activeTaskId}\n[${timeStr}] 正在启动执行...\n`;
    }
    startPolling(activeTaskId, isAllStages);
  } catch (err) {
    if (execSpinner) execSpinner.classList.remove("active");
    if (taskStatusPill) {
      taskStatusPill.className = "status-pill failed";
      taskStatusPill.textContent = "执行失败";
    }
    if (btnExecutePlan) btnExecutePlan.disabled = false;
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
      if (consoleLogs) {
        consoleLogs.textContent += `[WARN] 状态轮询异常: ${err.message}\n`;
      }
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

  let progressVal = 15;
  if (typeof st.progress === "number" && st.progress > 0) {
    progressVal = st.progress;
  } else {
    progressVal = Math.min(15 + pollCount * 6, 92);
  }
  if (execProgressBar) execProgressBar.style.width = `${progressVal}%`;

  if (consoleLogs && st.logs && st.logs.length) {
    consoleLogs.textContent = st.logs.join("\n");
    if (st.replan_events && st.replan_events.length) {
      const replanLines = st.replan_events.map((evt) => `[Supervisor] ${evt.reason || evt.type || "计划已调整"}`);
      consoleLogs.textContent += `\n${replanLines.join("\n")}`;
    }
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
  }

  syncChatTableStatus(st.current || "");

  const doneTasks = new Set((st.results || []).map((r) => r.task));
  const runningTask = st.current || "";

  if (currentPlan && currentPlan.execution && pipelineVisual) {
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
  if (execSpinner) execSpinner.classList.remove("active");

  if (st.status === "done") {
    (st.results || []).forEach((r) => {
      if (r.task) completedTasks.add(r.task);
    });

    const totalStages = currentPlan && currentPlan.execution ? currentPlan.execution.length : 1;
    const currentStageTasks = (currentPlan && currentPlan.execution && currentPlan.execution[currentActiveStep]) || [];
    currentStageTasks.forEach((task) => completedTasks.add(task));

    if (pipelineVisual) {
      const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
      if (stagePills[currentActiveStep]) {
        stagePills[currentActiveStep].classList.remove("running", "active");
        stagePills[currentActiveStep].classList.add("done");
      }
    }

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

    const isLastStage = currentActiveStep >= totalStages - 1;
    const planChanged = applySupervisorPlanUpdate(st);

    if (planChanged && !isAllStages) {
      if (taskStatusPill) {
        taskStatusPill.className = "status-pill done";
        taskStatusPill.textContent = `Supervisor 已调整计划 · 阶段 ${currentActiveStep + 1} 就绪`;
      }
      if (execStatusTitle) {
        execStatusTitle.textContent = `Supervisor 已调整计划 · 阶段 ${currentActiveStep + 1} 就绪`;
      }
      if (execProgressBar) execProgressBar.style.width = "100%";
      if (btnExecutePlan) btnExecutePlan.disabled = false;
      if (typeof switchTab === "function") switchTab("tab-plan");
      return;
    }

    if (!isLastStage && !isAllStages) {
      currentActiveStep += 1;
      setActiveStep(currentActiveStep);

      if (taskStatusPill) {
        taskStatusPill.className = "status-pill done";
        taskStatusPill.textContent = `阶段 ${currentActiveStep} 已完成 · 阶段 ${currentActiveStep + 1} 就绪`;
      }
      if (execStatusTitle) {
        execStatusTitle.textContent = `阶段 ${currentActiveStep} 已完成 · 阶段 ${currentActiveStep + 1} 就绪`;
      }
      if (execProgressBar) execProgressBar.style.width = "100%";

      if (btnExecutePlan) btnExecutePlan.disabled = false;
      
      if (typeof switchTab === "function") switchTab("tab-plan");
      return;
    }

    // [FULL PIPELINE COMPLETED]
    if (taskStatusPill) {
      taskStatusPill.className = "status-pill done";
      taskStatusPill.textContent = "全部已完成";
    }
    if (execStatusTitle) execStatusTitle.textContent = "流水线全部执行完成";
    if (execStatusSub) execStatusSub.textContent = "所有阶段任务已全部成功完成，最终目标产物已交付。";
    if (execProgressBar) execProgressBar.style.width = "100%";

    if (btnExecutePlan) btnExecutePlan.disabled = true;
    if (btnExecuteText) btnExecuteText.textContent = "全部阶段已执行完成 ✓";

    if (pipelineVisual) {
      const stagePills = pipelineVisual.querySelectorAll(".stage-pill");
      stagePills.forEach((p) => {
        p.classList.remove("running", "active");
        p.classList.add("done");
      });
    }

    if (planList) {
      const allCards = planList.querySelectorAll(".task-card");
      allCards.forEach((card) => {
        card.style.display = "block";
      });
    }

    const ctx = getCtx();
    if (ctx.user_id) fetchUserContext(ctx.user_id);

    const targetTask =
      currentPlan && currentPlan.plan && currentPlan.plan.length
        ? currentPlan.plan[currentPlan.plan.length - 1].task
        : "";
    const targetMeta = TASK_META[targetTask] || { name: "最终目标成果" };
    const targetOutputs = (st.outputs || []).filter((f) => isTargetTaskOutput(f, targetTask));
    const displayOuts = targetOutputs.length ? targetOutputs : st.outputs || [];
    const outCount = displayOuts.length;

    // Update Chat Delivery Card
    if (messagesContainer) {
      const deliveryCards = messagesContainer.querySelectorAll(".delivery-card");
      const deliveryCard = deliveryCards.length ? deliveryCards[deliveryCards.length - 1] : null;
      if (deliveryCard) {
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
            if (typeof switchTab === "function") switchTab("tab-outputs");
          });
        }
      }
    }

    // 触发保存服务完成状态到会话历史，并实时刷新左侧历史会话卡片
    if (ctx.user_id && activeSessionId) {
      const doneTaskLabel = (targetMeta.name || "目标任务").split(" ")[0];
      saveSessionMessage(
        ctx.user_id,
        activeSessionId,
        "assistant",
        `流水线全部执行完成 · 目标成果【${doneTaskLabel}】已交付`
      );
      if (typeof loadUserSessions === "function") {
        loadUserSessions();
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
      btnViewOut.addEventListener("click", () => {
        if (typeof switchTab === "function") switchTab("tab-outputs");
      });
    }
    const btnContinue = banner.querySelector("#btn-banner-continue-chat");
    if (btnContinue) {
      btnContinue.addEventListener("click", () => {
        if (chatText) {
          chatText.focus();
          chatText.placeholder = "针对已生成的资料向知识库提问，或输入新任务需求...";
        }
      });
    }

    if (planList && planList.firstChild) {
      planList.insertBefore(banner, planList.firstChild);
    }

    if (st.outputs && st.outputs.length) {
      renderOutputsCenter(activeTaskId, st.outputs);
    }

    if (typeof switchTab === "function") switchTab("tab-outputs");
  } else {
    if (taskStatusPill) {
      taskStatusPill.className = "status-pill failed";
      taskStatusPill.textContent = "执行失败";
    }
    if (execStatusTitle) execStatusTitle.textContent = "任务执行出现异常";
    if (execStatusSub) execStatusSub.textContent = st.message || "请查看执行日志了解详情。";
    if (execProgressBar) execProgressBar.style.width = "100%";
    if (btnExecutePlan) btnExecutePlan.disabled = false;
    setActiveStep(currentActiveStep);
    alert(st.message || "执行失败，请检查参数与日志。");
  }
}

// Helper to determine if an output file belongs to the user's terminal target task
function isTargetTaskOutput(filePath, targetTask) {
  if (!targetTask) return true;
  const pathNorm = filePath.toLowerCase().replace(/\\/g, "/");
  const task = targetTask.toLowerCase();

  if (pathNorm.includes(`/${task}/`) || pathNorm.includes(`/${task}_`)) return true;

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

  const targetTask =
    currentPlan && currentPlan.plan && currentPlan.plan.length
      ? currentPlan.plan[currentPlan.plan.length - 1].task
      : "";

  let targetOutputs = outputs.filter((f) => isTargetTaskOutput(f, targetTask));
  if (!targetOutputs.length) {
    targetOutputs = outputs;
  }

  if (outputsEmpty) outputsEmpty.classList.add("hidden");
  if (outputsContainer) outputsContainer.classList.remove("hidden");
  if (outputCountBadge) {
    outputCountBadge.textContent = targetOutputs.length;
    outputCountBadge.classList.remove("hidden");
  }

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

  const htmlFile = targetOutputs.find((f) => f.toLowerCase().endsWith(".html")) || targetOutputs[0];
  const htmlName = htmlFile.split(/[\\/]/).pop();
  previewHtmlArtifact(taskId, htmlName);
}
