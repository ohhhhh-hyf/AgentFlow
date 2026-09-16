"""checklist 内嵌的分层知识图谱组件（学术风格 + 复合簇 + 多视图交互）。

数据由 ``domain/notes/tasks/checklist/display._graph_payload`` 提供，三层结构：

    chapter（章簇，cluster-ch-*）→ topic（主题簇，cluster-tp-*）→ kp（知识点，kp-*）

KP 用 ``parent`` 挂到主题簇上，层次由**复合簇**表达（不指望力导向自行聚类）；
边分两类：``prerequisite`` / ``related``（语义，来自 catalog）与 ``same_topic`` /
``order``（结构，就地推导，关系为空的老目录也有骨架）。

交互（离线，除 cytoscape CDN 无外部依赖）：

- 四视图：概览（章/主题 + hub 点）、主题（聚焦某个簇）、关系（只留有语义边的点）、全量；
- 等级筛选 S/A/B/C、结构边开关、搜索、实时计数"已显示 X / 共 Y 个知识点"；
- 点主题簇 → 聚焦该主题；点章簇 → 聚焦该章；点知识点 → 右侧详情
  （含"在清单中定位"跳卡片锚点 ``#ck-card-{kp_id}``）；
- 视图状态存 localStorage；"折叠"只是没画，计数仍可见、随时可切全量。
"""
from __future__ import annotations

from html import escape
from json import dumps

__all__ = ["build_checklist_graph_embed"]

_STYLE = """<style>
.lc-kg{margin:14px 0 28px;border:1px solid #d4d0c7;border-radius:4px;overflow:hidden;background:#ffffff;
  box-shadow:0 4px 20px rgba(0,0,0,0.05),0 1px 3px rgba(0,0,0,0.02);
  font-family:"Latin Modern Roman","Computer Modern Roman","Times New Roman",Times,"Songti SC","SimSun",serif;box-sizing:border-box;}
.lc-kg-bar{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1.5px solid #222222;background:#faf9f6;flex-wrap:wrap;}
.lc-kg-bar strong{font-size:.95rem;font-weight:700;color:#111;margin-right:2px;}
.lc-kg-group{display:flex;align-items:center;gap:6px;}
.lc-kg-group>span{font-size:.76rem;color:#555555;letter-spacing:.2px;}
.lc-kg-bar button{border:1px solid #333333;background:#ffffff;border-radius:2px;padding:4px 10px;font-size:.79rem;
  font-family:inherit;font-weight:600;cursor:pointer;transition:all .15s;color:#222222;}
.lc-kg-bar button:hover{background:#eeebe3;}
.lc-kg-bar button.is-on{background:#111111;color:#ffffff;border-color:#111111;}
.lc-kg-bar label{font-size:.78rem;color:#333333;display:inline-flex;align-items:center;gap:3px;cursor:pointer;}
.lc-kg-bar input[type="search"]{border:1px solid #d4d0c7;border-radius:2px;padding:3px 8px;font-size:.79rem;
  font-family:inherit;min-width:150px;color:#222222;}
.lc-kg-count{margin-left:auto;font-size:.78rem;color:#555555;font-variant-numeric:tabular-nums;}
.lc-kg-count b{color:#111111;}
.lc-kg-shell{display:grid;grid-template-columns:minmax(0,1fr) minmax(250px,28%);min-height:560px;}
#lc-cy{width:100%;height:560px;background:#ffffff;}
.lc-kg-aside{border-left:1px solid #d4d0c7;background:#faf9f6;padding:14px 13px;overflow:auto;font-size:.85rem;line-height:1.6;}
.lc-kg-aside h3{margin:0 0 10px;font-size:1rem;font-weight:700;color:#111111;}
.lc-kg-label{font-size:.74rem;color:#222222;margin:12px 0 5px;font-weight:700;text-transform:uppercase;letter-spacing:.3px;}
.lc-kg-detail{border:1px solid #d4d0c7;border-radius:2px;padding:10px 11px;background:#ffffff;min-height:46px;}
.lc-kg-name{font-weight:700;margin-bottom:6px;font-size:.95rem;color:#111111;}
.lc-kg-k{color:#555555;font-size:.72rem;margin-bottom:3px;font-weight:700;}
.lc-kg-block{margin-top:8px;}
.lc-kg-block ul{margin:3px 0 0 1.05em;padding:0;}
.lc-kg-block li{margin:2px 0;}
.lc-kg-chip{display:inline-block;padding:1px 7px;margin:0 4px 4px 0;border-radius:2px;background:#ede9e1;
  border:1px solid #d4d0c7;font-size:.73rem;color:#333333;}
.lc-kg-src{display:inline-block;margin-top:9px;font-size:.8rem;color:#0047ab;text-decoration:none;border-bottom:1px dotted #0047ab;}
.lc-kg-src:hover{color:#111111;border-bottom-color:#111111;}
.lc-kg-legend{display:grid;gap:5px;}
.lc-kg-legend-item{display:flex;align-items:center;gap:7px;font-size:.79rem;color:#333333;}
.lc-kg-swatch{width:10px;height:10px;border-radius:2px;border:1px solid rgba(0,0,0,.15);}
.lc-kg-ev{color:#555555;font-size:.78rem;font-style:italic;}
@media(max-width:860px){.lc-kg-shell{grid-template-columns:1fr}#lc-cy{height:420px}}
</style>"""

_SCRIPT = """<script>
(function () {
  const NODES = {nodes};
  const EDGES = {edges};
  const STATE_KEY = "lc-kg-state-v1";
  const GRADE_COLOR = {S: "#b45309", A: "#1d4ed8", B: "#047857", C: "#6b7280"};
  const cyEl = document.getElementById("lc-cy");
  const detailEl = document.getElementById("lc-kg-detail");
  const countEl = document.getElementById("lc-kg-count");
  const legendEl = document.getElementById("lc-kg-legend");
  const searchEl = document.getElementById("lc-kg-search");
  const structureEl = document.getElementById("lc-kg-structure-on");
  const fitEl = document.getElementById("lc-kg-fit");
  const root = cyEl ? cyEl.closest(".lc-kg") : null;
  if (!cyEl || !root || typeof cytoscape === "undefined") {
    if (cyEl) cyEl.innerHTML = '<p style="padding:14px;color:#555;font-style:italic;">图谱脚本未加载，已跳过本图。</p>';
    return;
  }

  const N = {};
  NODES.forEach((n) => { N[n.id] = n; });
  const kpNodes = NODES.filter((n) => n.kind === "kp");
  const clusterOf = (n) => (n && n.parent ? N[n.parent] : null);
  const isUnder = (n, clusterId) => {
    let cur = n;
    while (cur) {
      if (cur.id === clusterId) return true;
      cur = clusterOf(cur);
    }
    return false;
  };

  const defaultState = () => ({
    view: "overview", grades: {S: true, A: true, B: true, C: true},
    structure: true, focus: "", query: "",
  });
  let state = defaultState();
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_KEY) || "null");
    if (saved && typeof saved === "object") state = Object.assign(defaultState(), saved);
  } catch (e) {}
  const persist = () => {
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (e) {}
  };

  const elements = [];
  NODES.forEach((n) => { elements.push({ data: Object.assign({}, n) }); });
  EDGES.forEach((e, i) => {
    elements.push({ data: {
      id: "e" + i, source: e.source, target: e.target,
      type: e.type, label: e.label || "", evidence: e.evidence || "",
    } });
  });

  const layoutOptions = () => ({
    name: "breadthfirst", directed: true, roots: '[kind = "chapter"]',
    padding: 18, spacingFactor: 1.15, animate: false,
  });

  const cy = cytoscape({
    container: cyEl,
    elements: elements,
    wheelSensitivity: 0.18,
    style: [
      { selector: "node", style: {
          "background-color": "#ffffff", "border-width": 1.6, "border-color": "#333333",
          "label": "data(label)", "font-family": "inherit", "color": "#222222",
          "text-valign": "center", "text-halign": "center", "text-wrap": "wrap",
          "text-max-width": "data(text_max_width)", "font-size": "data(font_size)",
          "width": "data(size)", "height": "data(size)",
      } },
      { selector: 'node[kind = "chapter"]', style: {
          "shape": "round-rectangle", "background-color": "#f1efe9", "background-opacity": .9,
          "border-color": "#8a8378", "border-width": 1.4, "font-size": 13, "font-weight": "bold",
          "color": "#111111", "padding": 12, "width": "label", "height": "label",
          "text-max-width": 150, "text-wrap": "wrap",
      } },
      { selector: 'node[kind = "topic"]', style: {
          "shape": "round-rectangle", "background-color": "#f8f7f3", "background-opacity": .95,
          "border-color": "#b9b2a6", "border-style": "dashed", "font-size": 12,
          "color": "#333333", "padding": 9, "width": "label", "height": "label",
          "text-max-width": 130, "text-wrap": "wrap",
      } },
      { selector: 'node[grade = "S"]', style: { "border-color": "#b45309", "border-width": 2.2 } },
      { selector: 'node[grade = "A"]', style: { "border-color": "#1d4ed8" } },
      { selector: 'node[grade = "B"]', style: { "border-color": "#047857" } },
      { selector: 'node[grade = "C"]', style: { "border-color": "#9ca3af", "border-style": "dotted" } },
      { selector: 'node[tier = "leaf"]', style: { "background-color": "#fbfbfa", "opacity": .85 } },
      { selector: "edge", style: {
          "width": 1.2, "line-color": "#9aa0a6", "target-arrow-color": "#9aa0a6",
          "target-arrow-shape": "triangle", "curve-style": "bezier",
          "arrow-scale": .8, "label": "data(label)", "font-size": 9.5, "color": "#555555",
          "text-background-color": "#ffffff", "text-background-opacity": .82, "text-background-padding": 1.5,
      } },
      { selector: 'edge[type = "prerequisite"]', style: { "line-color": "#ea580c", "target-arrow-color": "#ea580c", "width": 1.8 } },
      { selector: 'edge[type = "related"]', style: { "line-color": "#9333ea", "target-arrow-color": "#9333ea", "line-style": "dashed" } },
      { selector: 'edge[type = "same_topic"]', style: { "line-color": "#c7c2b8", "target-arrow-shape": "none" } },
      { selector: 'edge[type = "order"]', style: { "line-color": "#b9b2a6", "line-style": "dotted", "target-arrow-shape": "none" } },
      { selector: ".is-hidden", style: { "display": "none" } },
      { selector: ".is-faded", style: { "opacity": .18 } },
      { selector: ".is-hot", style: { "border-color": "#111111", "border-width": 2.6 } },
    ],
    layout: layoutOptions(),
  });

  const key = (s) => String(s || "").replace(/[\\s:：,，。；;、（）()\\[\\]【】《》“”"'·\\-—_]+/g, "").toLowerCase();
  const text = (n) => (String(n.name || "") + String(n.label || "")).replace(/\\n/g, "");

  function visibleIds() {
    const q = key(state.query);
    const keep = new Set();
    const focusId = state.focus;
    const inFocus = (n) => (focusId ? isUnder(n, focusId) : true);
    kpNodes.forEach((n) => {
      if (!state.grades[n.grade || "B"]) return;
      if (!inFocus(n)) return;
      if (state.view === "relations" && !(n.degree > 0)) return;
      if (state.view === "overview" && !q && n.tier === "leaf") return;
      if (q) {
        const blob = key(text(n) + " " + (clusterOf(n) ? clusterOf(n).name : "")
          + " " + (clusterOf(clusterOf(n)) ? clusterOf(clusterOf(n)).name : ""));
        if (blob.indexOf(q) < 0) return;
      }
      keep.add(n.id);
    });
    NODES.filter((n) => n.kind !== "kp").forEach((c) => {
      const kids = kpNodes.filter((n) => isUnder(n, c.id));
      if (kids.some((k) => keep.has(k.id))) keep.add(c.id);
    });
    return keep;
  }

  function apply() {
    const keep = visibleIds();
    let shown = 0;
    cy.nodes().forEach((node) => {
      const d = node.data();
      if (d.kind === "kp") {
        const ok = keep.has(d.id);
        if (ok) shown += 1;
        node.toggleClass("is-hidden", !ok);
      } else {
        const kids = kpNodes.filter((n) => isUnder(n, d.id));
        const visibleKids = kids.filter((k) => keep.has(k.id)).length;
        node.data("label", d.name + " (" + visibleKids + "/" + kids.length + ")");
        node.toggleClass("is-hidden", !(keep.has(d.id) || visibleKids > 0));
      }
    });
    cy.edges().forEach((edge) => {
      const d = edge.data();
      const structural = d.type === "same_topic" || d.type === "order";
      const ok = (!structural || !!state.structure)
        && !cy.getElementById(d.source).hasClass("is-hidden")
        && !cy.getElementById(d.target).hasClass("is-hidden");
      edge.toggleClass("is-hidden", !ok);
    });
    if (countEl) countEl.innerHTML = "已显示 <b>" + shown + "</b> / 共 " + kpNodes.length + " 个知识点";
    root.querySelectorAll("#lc-kg-views button").forEach((btn) => {
      btn.classList.toggle("is-on", btn.getAttribute("data-view") === state.view);
    });
    if (structureEl) structureEl.checked = !!state.structure;
    if (searchEl && searchEl.value !== state.query) searchEl.value = state.query;
    persist();
  }

  function relayout() {
    cy.layout(layoutOptions()).run();
    cy.fit(cy.elements(":visible"), 26);
  }

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (ch) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[ch]);

  const stars = (n) => {
    const v = Math.max(0, Math.min(5, parseInt(n.importance || 3, 10) || 3));
    return "★".repeat(v) + "☆".repeat(5 - v);
  };

  function block(title, items, limit) {
    const list = (items || []).slice(0, limit || 4);
    if (!list.length) return "";
    return '<div class="lc-kg-block"><div class="lc-kg-k">' + title + "</div><ul>"
      + list.map((x) => "<li>" + escapeHtml(x) + "</li>").join("") + "</ul></div>";
  }

  function neighbors(set) {
    const names = set.filter((x) => x.data("kind") === "kp")
      .map((x) => '<span class="lc-kg-chip">' + escapeHtml(x.data("name")) + "</span>");
    return names.length ? names.join("") : '<span class="lc-kg-ev">无</span>';
  }

  function showDetail(id) {
    const n = N[id];
    if (!n || !detailEl) return;
    if (n.kind !== "kp") {
      const kids = kpNodes.filter((x) => isUnder(x, n.id));
      detailEl.innerHTML = '<div class="lc-kg-name">' + escapeHtml(n.name) + "</div>"
        + '<div class="lc-kg-block"><div class="lc-kg-k">'
        + (n.kind === "chapter" ? "本章知识点" : "本节知识点") + "（" + kids.length + "）</div><div>"
        + kids.map((k) => '<span class="lc-kg-chip">' + escapeHtml(k.name) + "</span>").join("")
        + "</div></div>";
      return;
    }
    const node = cy.getElementById(id);
    detailEl.innerHTML = '<div class="lc-kg-name">' + escapeHtml(n.name) + "</div>"
      + '<div class="lc-kg-k">' + escapeHtml(String(n.grade || "B")) + " 档 · " + stars(n)
      + " · 难度 " + escapeHtml(String(n.difficulty || 3)) + " · 关联度 " + escapeHtml(String(n.degree || 0))
      + "</div>"
      + (n.explain ? "<div>" + escapeHtml(n.explain) + "</div>" : "")
      + block("知识要点", n.knowledge_items, 5)
      + block("易错提醒", n.pitfalls, 3)
      + '<div class="lc-kg-block"><div class="lc-kg-k">前置</div><div>' + neighbors(node.incomers("node")) + "</div></div>"
      + '<div class="lc-kg-block"><div class="lc-kg-k">关联</div><div>' + neighbors(node.outgoers("node")) + "</div></div>"
      + (n.kp_id
        ? '<a class="lc-kg-src" href="#ck-card-' + encodeURIComponent(n.kp_id) + '">在清单中定位 ↓</a>'
        : "");
  }

  function highlight(id) {
    cy.elements().removeClass("is-faded is-hot");
    if (!id) return;
    const node = cy.getElementById(id);
    if (!node || node.empty()) return;
    const hood = node.closedNeighborhood();
    cy.elements().not(hood).addClass("is-faded");
    hood.addClass("is-hot");
  }

  function focusCluster(id) {
    state.focus = state.focus === id ? "" : id;
    state.view = state.focus ? "topic" : "overview";
    apply();
    if (state.focus) {
      cy.fit(cy.elements(":visible"), 30);
      showDetail(id);
    } else {
      relayout();
    }
  }

  root.querySelectorAll("#lc-kg-views button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.getAttribute("data-view") || "overview";
      if (state.view !== "topic") state.focus = "";
      apply();
      relayout();
    });
  });
  if (structureEl) {
    structureEl.addEventListener("change", () => { state.structure = !!structureEl.checked; apply(); });
  }
  if (fitEl) {
    fitEl.addEventListener("click", () => relayout());
  }
  root.querySelectorAll("#lc-kg-grades input").forEach((box) => {
    box.checked = state.grades[box.value] !== false;
    box.addEventListener("change", () => { state.grades[box.value] = !!box.checked; apply(); });
  });
  if (searchEl) {
    searchEl.addEventListener("input", () => { state.query = searchEl.value.trim(); apply(); });
  }

  cy.on("tap", "node", (evt) => {
    const d = evt.target.data();
    if (d.kind === "kp") { highlight(d.id); showDetail(d.id); }
    else focusCluster(d.id);
  });
  cy.on("tap", (evt) => { if (evt.target === cy) highlight(""); });
  cy.on("mouseover", "node", (evt) => highlight(evt.target.data("id")));
  cy.on("mouseout", "node", () => highlight(""));

  if (legendEl) {
    const rows = [["S 档", GRADE_COLOR.S], ["A 档", GRADE_COLOR.A], ["B 档", GRADE_COLOR.B],
                  ["C 档", GRADE_COLOR.C], ["前置边", "#ea580c"], ["关联边", "#9333ea"],
                  ["同节边", "#c7c2b8"], ["章内顺序", "#b9b2a6"]];
    legendEl.innerHTML = rows.map(([name, color]) =>
      '<div class="lc-kg-legend-item"><span class="lc-kg-swatch" style="background:' + color + '"></span>'
      + name + "</div>").join("");
  }

  apply();
  cy.ready(() => cy.fit(cy.elements(":visible"), 26));
})();
</script>"""


def build_checklist_graph_embed(
    nodes: list[dict],
    edges: list[dict],
    title: str = "",
) -> str:
    """把 ``(nodes, edges)`` 渲染成自包含的图谱区块（工具栏 + 画布 + 详情栏）。

    ``nodes`` 需带 ``kind``（chapter / topic / kp）与 KP 的 ``parent``；``edges``
    的 ``type`` 为 prerequisite / related / same_topic / order。缺字段按空值渲染，
    不抛错——图是展示层，不能因为一个字段缺失就打断清单生成。
    """
    heading = (title or "").strip() or "考点知识图谱"
    payload_nodes = dumps(nodes or [], ensure_ascii=False).replace("<", "\\u003c")
    payload_edges = dumps(edges or [], ensure_ascii=False).replace("<", "\\u003c")
    script = _SCRIPT.replace("{nodes}", payload_nodes).replace("{edges}", payload_edges)
    return (
        _STYLE
        + '<div class="lc-kg">\n'
        + '  <div class="lc-kg-bar">\n'
        + f'    <strong>{escape(heading)}</strong>\n'
        + '    <span class="lc-kg-group" id="lc-kg-views">\n'
        + '      <button type="button" data-view="overview" class="is-on">概览</button>\n'
        + '      <button type="button" data-view="topic">主题</button>\n'
        + '      <button type="button" data-view="relations">关系</button>\n'
        + '      <button type="button" data-view="all">全量</button>\n'
        + "    </span>\n"
        + '    <span class="lc-kg-group" id="lc-kg-grades">\n'
        + "      <span>等级</span>\n"
        + '      <label><input type="checkbox" value="S" checked>S</label>\n'
        + '      <label><input type="checkbox" value="A" checked>A</label>\n'
        + '      <label><input type="checkbox" value="B" checked>B</label>\n'
        + '      <label><input type="checkbox" value="C" checked>C</label>\n'
        + "    </span>\n"
        + '    <span class="lc-kg-group" id="lc-kg-structure">\n'
        + '      <label><input type="checkbox" id="lc-kg-structure-on" checked>结构边</label>\n'
        + "    </span>\n"
        + '    <input type="search" id="lc-kg-search" placeholder="搜索知识点/主题…">\n'
        + '    <button type="button" id="lc-kg-fit">重新排版</button>\n'
        + '    <span class="lc-kg-count" id="lc-kg-count"></span>\n'
        + "  </div>\n"
        + '  <div class="lc-kg-shell">\n'
        + '    <div id="lc-cy"></div>\n'
        + '    <aside class="lc-kg-aside">\n'
        + f"      <h3>{escape(heading)}</h3>\n"
        + '      <div class="lc-kg-label">当前选中</div>\n'
        + '      <div id="lc-kg-detail" class="lc-kg-detail"></div>\n'
        + '      <div class="lc-kg-label">图例</div>\n'
        + '      <div id="lc-kg-legend" class="lc-kg-legend"></div>\n'
        + "    </aside>\n"
        + "  </div>\n"
        + "</div>\n"
        + script
    )
