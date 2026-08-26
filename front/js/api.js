// ==========================================================================
// AgentFlow Front-end · Backend API Network Client
// ==========================================================================
"use strict";

// Check Backend Health
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API}/health`);
    if (res.ok) {
      if (serviceStatus) {
        serviceStatus.className = "status-indicator online";
        serviceStatus.querySelector(".status-text").textContent = "服务正常";
      }
    } else {
      throw new Error();
    }
  } catch {
    if (serviceStatus) {
      serviceStatus.className = "status-indicator offline";
      serviceStatus.querySelector(".status-text").textContent = "服务离线";
    }
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
  if (typeof updateKnowledgeBaseDrawer === "function") {
    updateKnowledgeBaseDrawer(currentUserContext);
  }
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

// Load user sessions list
async function loadUserSessions() {
  const ctx = getCtx();
  if (!ctx.user_id) return;
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/sessions`);
    if (!res.ok) return;
    const data = await res.json();
    if (typeof renderSidebarSessions === "function") {
      renderSidebarSessions(data.sessions || []);
    }
  } catch (e) {
    console.warn("Failed to load user sessions:", e);
  }
}

// Switch to a history session
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

    if (messagesContainer) messagesContainer.innerHTML = "";
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

// Delete a session
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

// Load user historical generated outputs from disk
async function loadUserOutputsDisk() {
  const ctx = getCtx();
  if (!ctx.user_id) return;
  try {
    const res = await fetch(`${API}/user/${encodeURIComponent(ctx.user_id)}/outputs`);
    if (!res.ok) return;
    const data = await res.json();
    const outputs = data.outputs || [];
    if (typeof renderSidebarOutputsDrawer === "function") {
      renderSidebarOutputsDrawer(outputs);
    }
  } catch (e) {
    console.warn("Failed to load user outputs disk:", e);
  }
}

// Preview historical output from Cloud Disk
async function previewHistoricalOutput(relPath, name) {
  if (outputsEmpty) outputsEmpty.classList.add("hidden");
  if (outputsContainer) outputsContainer.classList.remove("hidden");

  if (viewerFilename) viewerFilename.textContent = `云盘成果 · ${name}`;
  if (viewerBody) {
    viewerBody.innerHTML = '<div class="viewer-placeholder"><span class="spinner-ring active" style="display:inline-block; margin-right:8px;"></span> 正在加载产物预览...</div>';
  }

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
    if (!viewerBody) return;
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
    if (viewerBody) {
      viewerBody.innerHTML = `<div class="viewer-placeholder" style="color: var(--terra-600);">加载预览失败：${escapeHtml(err.message)}</div>`;
    }
  }
}

// Preview newly generated HTML artifact in workbench
async function previewHtmlArtifact(taskId, name) {
  activeTaskId = taskId;
  activeOutputName = name;
  if (viewerFilename) viewerFilename.textContent = `成果预览 · ${name}`;
  if (viewerBody) {
    viewerBody.innerHTML = '<div class="viewer-placeholder"><span class="spinner-ring active" style="display:inline-block; margin-right:8px;"></span> 正在加载产物预览...</div>';
  }

  try {
    const res = await fetch(`${API}/tasks/${taskId}/output/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error("获取产物失败");

    const text = await res.text();
    if (!viewerBody) return;
    viewerBody.innerHTML = "";

    if (name.endsWith(".html")) {
      const iframe = document.createElement("iframe");
      iframe.className = "viewer-iframe";
      iframe.sandbox = "allow-scripts allow-same-origin allow-popups";
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
    if (viewerBody) {
      viewerBody.innerHTML = `<div class="viewer-placeholder" style="color: var(--terra-600);">加载预览失败：${escapeHtml(err.message)}</div>`;
    }
  }
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
