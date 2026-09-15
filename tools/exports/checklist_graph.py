"""checklist 内嵌的分层知识图谱组件（自包含 HTML/CSS/JS）。

与"整站图谱页"（`knowledge_graph.py`）的分工：这里是按**"图的价值在关系、不在罗列"**
设计的清单内嵌版——

- **三层复合簇**：章 → 主题 → 知识点；层次用 cytoscape 复合节点（``parent``）表达，不占视觉线；
- **四个视图**：概览（只看簇）/ 主题（展开所选主题的 KP）/ 关系（只看有边的 KP）/ 全量；
- **边分型**：语义边（前置/关联/组合）、结构边（同节/顺序）、共现边分色分线型，结构边可一键关掉；
- **交互**：档位过滤、搜索定位、点簇进主题视图、点 KP 看侧栏摘要并「在清单中定位」到卡片，
  悬停只高亮邻接；视图/过滤/开关状态存 localStorage，刷新不丢；
- **不丢内容**：始终显示 ``已显示 X / 共 Y``，被折叠的节点只是"没画"，
  切"全量"或点主题即可看到全部。
"""
from __future__ import annotations

from html import escape
from json import dumps

__all__ = ["build_checklist_graph_embed"]

_STYLE = """<style>
.lc-kg-bar{display:flex;align-items:center;gap:10px;padding:8px 14px;border-bottom:1px solid #222222;background:#faf9f6;flex-wrap:wrap;}
.lc-kg-bar .lc-kg-group{display:flex;align-items:center;gap:6px;}
.lc-kg-bar strong{font-size:.95rem;font-weight:700;color:#111;margin-right:4px;}
.lc-kg-bar button{border:1px solid #333333;background:#ffffff;border-radius:2px;padding:4px 10px;font-size:.8rem;font-family:inherit;font-weight:600;cursor:pointer;transition:all .15s;}
.lc-kg-bar button:hover{background:#eeebe3;}
.lc-kg-bar button.is-on{background:#111111;color:#ffffff;border-color:#111111;}
.lc-kg-bar label{font-size:.78rem;color:#333;display:inline-flex;align-items:center;gap:4px;cursor:pointer;}
.lc-kg-bar input[type="search"]{border:1px solid #d4d0c7;border-radius:2px;padding:3px 8px;font-size:.8rem;font-family:inherit;min-width:150px;}
.lc-kg-bar .lc-kg-count{margin-left:auto;font-size:.78rem;color:#555555;font-variant-numeric:tabular-nums;}
.lc-kg-bar .lc-kg-count b{color:#111;}
.lc-kg-detail ul{margin:4px 0 0 1.1em;padding:0;}
.lc-kg-detail li{margin:2px 0;}
</style>
"""

_SCRIPT = """<script>
(function () {
  const NODES = __NODES__;
  const EDGES = __EDGES__;
  const STATE_KEY = 'lc-kg-state-v1';
  const GRADE_COLOR = {S: '#b45309', A: '#1d4ed8', B: '#0f766e', C: '#6b7280'};
  const EDGE_STYLE = {
    prerequisite: {color: '#1d4ed8', style: 'solid', width: 2.0},
    related: {color: '#0f766e', style: 'solid', width: 1.4},
    order: {color: '#b45309', style: 'dashed', width: 1.4},
    same_topic: {color: '#9ca3af', style: 'dotted', width: 1.1},
    cooccur: {color: '#d1d5db', style: 'dotted', width: 1.0},
  };
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const state = {view: 'overview', grades: {S: 1, A: 1, B: 1, C: 1}, structure: true, topic: ''};
  try {
    const saved = JSON.parse(localStorage.getItem(STATE_KEY) || '{}');
    if (saved && typeof saved === 'object') {
      if (['overview', 'topic', 'relations', 'all'].indexOf(saved.view) >= 0) state.view = saved.view;
      if (saved.grades) Object.keys(state.grades).forEach((g) => {
        if (saved.grades[g] !== undefined) state.grades[g] = saved.grades[g] ? 1 : 0;
      });
      if (saved.structure !== undefined) state.structure = !!saved.structure;
    }
  } catch (err) { /* 存储不可用时用默认状态 */ }

  const elements = [];
  const clusterNames = {};
  NODES.forEach((node) => {
    const data = Object.assign({}, node);
    if (node.kind === 'kp') {
      data.label = node.label || node.name;
    } else {
      clusterNames[node.id] = node.name;
      data.label = node.name + (node.count ? ' (' + node.count + ')' : '');
    }
    elements.push({data: data});
  });
  EDGES.forEach((edge, index) => {
    const style = EDGE_STYLE[edge.type] || EDGE_STYLE.related;
    elements.push({data: {
      id: 'e' + index,
      source: edge.source,
      target: edge.target,
      label: edge.label || '',
      type: edge.type || 'related',
      evidence: edge.evidence || '',
      lineColor: style.color,
      lineStyle: style.style,
      lineWidth: style.width,
    }});
  });

  const cy = cytoscape({
    container: document.getElementById('lc-cy'),
    elements: elements,
    wheelSensitivity: 0.2,
    style: [
      {selector: 'node', style: {
        'label': 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 96,
        'font-family': '"Latin Modern Roman", "Songti SC", "SimSun", serif',
        'font-size': 11, 'font-weight': 600, 'color': '#111111',
        'text-valign': 'center', 'text-halign': 'center',
        'shape': 'round-rectangle', 'padding': '7px',
        'background-color': '#ffffff', 'border-width': 1.6, 'border-color': '#9ca3af',
      }},
      {selector: 'node[kind = "chapter"]', style: {
        'background-color': '#f3f0e8', 'background-opacity': 0.85,
        'border-color': '#222222', 'border-width': 2, 'font-size': 13.5, 'font-weight': 800,
        'padding': '12px', 'text-valign': 'top', 'text-margin-y': -4,
      }},
      {selector: 'node[kind = "topic"]', style: {
        'background-color': '#faf9f6', 'background-opacity': 0.9,
        'border-color': '#b9b3a6', 'border-width': 1.4, 'font-size': 11.5, 'color': '#333333',
        'padding': '9px', 'text-valign': 'top', 'text-margin-y': -3,
      }},
      {selector: 'node.g-s', style: {'border-color': '#b45309', 'border-width': 2.2}},
      {selector: 'node.g-a', style: {'border-color': '#1d4ed8'}},
      {selector: 'node.g-b', style: {'border-color': '#0f766e'}},
      {selector: 'node.g-c', style: {'border-color': '#9ca3af', 'background-color': '#fbfbfa'}},
      {selector: 'node[tier = "hub"]', style: {'font-size': 13, 'font-weight': 800, 'border-width': 3}},
      {selector: 'node[tier = "leaf"]', style: {'background-opacity': 0.55, 'font-size': 10.5}},
      {selector: 'edge', style: {
        'width': 'data(lineWidth)', 'line-color': 'data(lineColor)', 'line-style': 'data(lineStyle)',
        'target-arrow-shape': 'none', 'curve-style': 'bezier', 'opacity': 0.85,
        'label': 'data(label)', 'font-size': 8.5, 'color': '#555555',
        'text-background-color': '#ffffff', 'text-background-opacity': 0.8, 'text-background-padding': 2,
      }},
      {selector: 'edge[type = "prerequisite"]', style: {'target-arrow-shape': 'triangle'}},
      {selector: 'edge[type = "order"]', style: {'target-arrow-shape': 'triangle'}},
      {selector: '.faded', style: {'opacity': 0.12}},
      {selector: 'node.picked', style: {'border-color': '#111111', 'border-width': 3.2, 'background-color': '#fff8e1'}},
    ],
    layout: {name: 'breadthfirst', directed: true, circle: false, spacingFactor: 1.15,
             padding: 24, roots: '[kind = "chapter"]', animate: false},
  });

  const kpNodes = cy.nodes('[kind = "kp"]');
  const clusterNodes = cy.nodes('[kind = "chapter"], [kind = "topic"]');
  const totalKp = kpNodes.length;

  function matchesQuery(node) {
    const box = $('#lc-kg-search');
    const q = String((box && box.value) || '').trim().toLowerCase();
    if (!q) return true;
    return (node.data('name') + ' ' + (node.data('label') || '')).toLowerCase().indexOf(q) >= 0;
  }

  function visibleKp() {
    const visible = {};
    kpNodes.forEach((node) => {
      const grade = String(node.data('grade') || 'B').toUpperCase();
      if (!state.grades[grade]) return;
      if (!matchesQuery(node)) return;
      if (state.view === 'overview') return;                       // 概览：只画簇
      if (state.view === 'relations' && (node.data('degree') || 0) === 0) return;
      if (state.view === 'topic' && state.topic) {
        const parentId = node.data('parent');
        if (!parentId || clusterNames[parentId] !== state.topic) return;
      }
      visible[node.id()] = 1;
    });
    return visible;
  }

  function applyView() {
    const visible = visibleKp();
    kpNodes.forEach((n) => n.style('display', visible[n.id()] ? 'element' : 'none'));
    const counts = {};
    kpNodes.forEach((n) => {
      if (!visible[n.id()]) return;
      const parent = n.data('parent');
      counts[parent] = (counts[parent] || 0) + 1;
    });
    clusterNodes.forEach((n) => {
      const label = n.data('kind') === 'topic'
        ? n.data('name') + ' (' + (counts[n.id()] || 0) + ')'
        : n.data('name') + (n.data('count') ? ' (' + n.data('count') + ')' : '');
      n.data('label', label);
    });
    cy.edges().forEach((edge) => {
      const structural = edge.data('type') === 'same_topic' || edge.data('type') === 'order';
      const keep = visible[edge.data('source')] && visible[edge.data('target')]
        && (!structural || state.structure);
      edge.style('display', keep ? 'element' : 'none');
    });
    const countEl = $('#lc-kg-count');
    if (countEl) {
      countEl.innerHTML = '已显示 <b>' + Object.keys(visible).length + '</b> / 共 ' + totalKp + ' 个知识点';
    }
    document.querySelectorAll('#lc-kg-views button').forEach((btn) => {
      btn.classList.toggle('is-on', btn.getAttribute('data-view') === state.view);
    });
    document.querySelectorAll('#lc-kg-grades input').forEach((box) => {
      box.checked = !!state.grades[box.getAttribute('data-grade')];
    });
    const structureBox = $('#lc-kg-structure');
    if (structureBox) structureBox.checked = !!state.structure;
    try { localStorage.setItem(STATE_KEY, JSON.stringify(state)); } catch (err) { /* 忽略 */ }
  }

  function showDetail(node) {
    const box = $('#lc-kg-detail');
    if (!box) return;
    if (!node) { box.innerHTML = ''; return; }
    if (node.data('kind') !== 'kp') {
      box.innerHTML = '<div class="lc-kg-name">' + esc(node.data('name')) + '</div>'
        + '<div class="lc-kg-k">点击进入该主题视图（只看这一节的卡片）</div>';
      return;
    }
    const kpId = String(node.data('kp_id') || '');
    const anchor = kpId ? ' <a class="lc-kg-chip" href="#ck-card-' + esc(kpId) + '">在清单中定位 ↓</a>' : '';
    const facts = (node.data('facts') || []).map((x) => '<li>' + esc(x) + '</li>').join('');
    const pits = (node.data('pitfalls') || []).map((x) => '<li>' + esc(x) + '</li>').join('');
    const links = cy.edges().filter((e) => e.data('source') === node.id() || e.data('target') === node.id())
      .map((e) => {
        const otherId = e.data('source') === node.id() ? e.data('target') : e.data('source');
        const other = cy.getElementById(otherId);
        const ev = e.data('evidence') ? '（' + esc(e.data('evidence')) + '）' : '';
        return '<div class="lc-kg-rel">' + esc(e.data('label') || e.data('type')) + '：'
          + esc(other.data('name') || '') + ev + '</div>';
      }).join('');
    box.innerHTML = '<div class="lc-kg-name">' + esc(node.data('name')) + '</div>'
      + '<div class="lc-kg-k">' + esc(node.data('grade') || '') + ' 档 · 关联 ' + (node.data('degree') || 0)
      + ' 条 · ' + esc(node.data('topic') || '') + anchor + '</div>'
      + (node.data('definition')
        ? '<div class="lc-kg-block"><div class="lc-kg-k">一句话</div>' + esc(node.data('definition')) + '</div>' : '')
      + (facts ? '<div class="lc-kg-block"><div class="lc-kg-k">必须先会</div><ul>' + facts + '</ul></div>' : '')
      + (pits ? '<div class="lc-kg-block"><div class="lc-kg-k">易错</div><ul>' + pits + '</ul></div>' : '')
      + (links ? '<div class="lc-kg-block"><div class="lc-kg-k">关联</div>' + links + '</div>' : '');
  }

  const byTopic = {};
  kpNodes.forEach((n) => {
    const topic = String(n.data('topic') || '未分组');
    const grade = String(n.data('grade') || 'B').toUpperCase();
    byTopic[topic] = byTopic[topic] || {total: 0, color: GRADE_COLOR[grade] || GRADE_COLOR.B};
    byTopic[topic].total += 1;
  });
  const legend = Object.keys(byTopic).slice(0, 40).map((topic) => {
    const info = byTopic[topic];
    return '<div class="lc-kg-legend-item"><span class="lc-kg-swatch" style="background:'
      + info.color + '"></span><span>' + esc(topic) + ' · ' + info.total + '</span></div>';
  }).join('');
  const legendBox = $('#lc-kg-legend');
  if (legendBox) legendBox.innerHTML = legend;

  cy.on('tap', 'node', (event) => {
    const node = event.target;
    cy.nodes().removeClass('picked');
    node.addClass('picked');
    if (node.data('kind') !== 'kp') {
      state.topic = String(node.data('name') || '');
      state.view = 'topic';
      showDetail(node);
      applyView();
      return;
    }
    showDetail(node);
  });
  cy.on('tap', (event) => {
    if (event.target === cy) { cy.nodes().removeClass('picked'); showDetail(null); }
  });
  cy.on('mouseover', 'node', (event) => {
    const node = event.target;
    cy.elements().addClass('faded');
    node.closedNeighborhood().removeClass('faded');
    node.removeClass('faded');
  });
  cy.on('mouseout', 'node', () => { cy.elements().removeClass('faded'); });

  document.querySelectorAll('#lc-kg-views button').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.view = btn.getAttribute('data-view') || 'overview';
      if (state.view !== 'topic') state.topic = '';
      applyView();
    });
  });
  document.querySelectorAll('#lc-kg-grades input').forEach((box) => {
    box.addEventListener('change', () => {
      state.grades[box.getAttribute('data-grade')] = box.checked ? 1 : 0;
      applyView();
    });
  });
  const structureBox = $('#lc-kg-structure');
  if (structureBox) {
    structureBox.addEventListener('change', (event) => {
      state.structure = !!event.target.checked;
      applyView();
    });
  }
  const searchBox = $('#lc-kg-search');
  if (searchBox) searchBox.addEventListener('input', () => { applyView(); });

  applyView();
})();
</script>
"""


def build_checklist_graph_embed(nodes: list[dict], edges: list[dict], title: str = "") -> str:
    """checklist 内嵌的分层知识图谱组件（自包含 HTML/CSS/JS）。"""
    heading = (title or "").strip() or "知识图谱"
    script = _SCRIPT.replace("__NODES__", dumps(nodes, ensure_ascii=False)).replace(
        "__EDGES__", dumps(edges, ensure_ascii=False)
    )
    return f"""{_STYLE}<div class="lc-kg">
  <div class="lc-kg-bar">
    <strong>{escape(heading)}</strong>
    <div class="lc-kg-group" id="lc-kg-views">
      <button type="button" data-view="overview">概览</button>
      <button type="button" data-view="topic">主题</button>
      <button type="button" data-view="relations">关系</button>
      <button type="button" data-view="all">全量</button>
    </div>
    <div class="lc-kg-group" id="lc-kg-grades">
      <label><input type="checkbox" data-grade="S" checked>核心</label>
      <label><input type="checkbox" data-grade="A" checked>重点</label>
      <label><input type="checkbox" data-grade="B" checked>简要</label>
      <label><input type="checkbox" data-grade="C" checked>补充</label>
    </div>
    <div class="lc-kg-group">
      <label><input type="checkbox" id="lc-kg-structure" checked>结构边</label>
    </div>
    <input type="search" id="lc-kg-search" placeholder="搜索知识点…">
    <span class="lc-kg-count" id="lc-kg-count"></span>
  </div>
  <div class="lc-kg-shell">
    <div id="lc-cy"></div>
    <aside class="lc-kg-aside">
      <div class="lc-kg-label">当前选中</div>
      <div id="lc-kg-detail" class="lc-kg-detail"></div>
      <div class="lc-kg-label">分组</div>
      <div id="lc-kg-legend" class="lc-kg-legend"></div>
    </aside>
  </div>
</div>
{script}"""
