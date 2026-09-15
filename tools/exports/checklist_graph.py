"""checklist 内嵌的分层知识图谱组件（学术风格 + 力导向布局 + 丰富交互）。

设计与实现完全对齐 knowledge_graph.py（LaTeX Paper 学术图谱风格）：
- 纯平级考点节点（彻底抛弃 compound 复合父容器，杜绝互相压制与挤在一团）；
- 基于 cose 高排斥力导向算法，节点宽阔舒展，连通簇与前置骨干清晰可见；
- 节点形状采用圆形/椭圆，颜色按章节自动映射柔和学术底色，边框按 Catalog 知识类型标色；
- 边采用贝塞尔曲线，带三角箭头，前置依赖加粗，附带半透明文本衬底；
- 整合顶栏快捷工具箱（居中自适应、重新排版、S/A 核心过滤、章节下拉选择、搜索实时定位）；
- 结合 Catalog 全维度字段的右侧学术抽屉卡片（重要度星级、难度等级、知识要点、前置入边/出边跳转、易错避坑、正文卡片直达定位）。
"""
from __future__ import annotations

from html import escape
from json import dumps
from typing import Any

__all__ = ["build_checklist_graph_embed"]

_STYLE = """<style>
/* 知识图谱 LaTeX 学术卡片样式容器 */
.lc-kg {
  margin: 14px 0 28px;
  border: 1px solid #d4d0c7;
  border-radius: 4px;
  overflow: hidden;
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02);
  font-family: "Latin Modern Roman", "Computer Modern Roman", "Times New Roman", Times, "Songti SC", "SimSun", serif;
  box-sizing: border-box;
}

/* 顶部交互操作栏 */
.lc-kg-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1.5px solid #222222;
  background: #faf9f6;
  flex-wrap: wrap;
  user-select: none;
}
.lc-kg-title-group {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.lc-kg-title-group strong {
  font-size: 1.05rem;
  font-weight: 700;
  color: #111111;
  letter-spacing: 0.3px;
}
.lc-kg-count {
  font-size: 0.8rem;
  color: #555555;
  font-style: italic;
  font-variant-numeric: tabular-nums;
}
.lc-kg-count b {
  color: #0047ab;
  font-style: normal;
}
.lc-kg-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.lc-kg-btn-group {
  display: inline-flex;
  border: 1px solid #d4d0c7;
  border-radius: 3px;
  overflow: hidden;
  background: #ffffff;
}
.lc-kg-tool-btn {
  appearance: none;
  border: none;
  border-right: 1px solid #d4d0c7;
  background: #faf9f6;
  color: #222222;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 11px;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.lc-kg-tool-btn:last-child {
  border-right: none;
}
.lc-kg-tool-btn:hover {
  background: #ffffff;
  color: #0047ab;
}
.lc-kg-tool-btn.is-active {
  background: #0047ab;
  color: #ffffff;
}
.lc-kg-btn-single {
  appearance: none;
  border: 1px solid #d4d0c7;
  border-radius: 3px;
  background: #faf9f6;
  color: #222222;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  padding: 5px 11px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.lc-kg-btn-single:hover {
  background: #ffffff;
  border-color: #0047ab;
  color: #0047ab;
  box-shadow: 0 1px 3px rgba(0, 71, 171, 0.12);
}
.lc-kg-select {
  padding: 4.5px 10px;
  border: 1px solid #d4d0c7;
  border-radius: 3px;
  font-size: 12px;
  background: #ffffff;
  font-family: inherit;
  color: #111111;
  outline: none;
  cursor: pointer;
}
.lc-kg-select:focus {
  border-color: #0047ab;
}
.lc-kg-search {
  padding: 4.5px 10px;
  border: 1px solid #d4d0c7;
  border-radius: 3px;
  font-size: 12px;
  background: #ffffff;
  font-family: inherit;
  color: #111111;
  outline: none;
  min-width: 140px;
  transition: all 0.18s ease;
}
.lc-kg-search:focus {
  border-color: #0047ab;
  box-shadow: 0 0 0 2px rgba(0, 71, 171, 0.12);
  min-width: 180px;
}

/* 主体分栏：画布 + 右侧详情抽屉 */
.lc-kg-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  min-height: 640px;
  height: 640px;
  position: relative;
  background: #ffffff;
}
.lc-kg-canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #fbfaf7 radial-gradient(#e5dfd5 1.2px, transparent 1.2px);
  background-size: 26px 26px;
}
#lc-cy {
  width: 100%;
  height: 100%;
}

/* 右侧抽屉 */
.lc-kg-aside {
  border-left: 1.5px solid #d4d0c7;
  background: #ffffff;
  padding: 18px 20px;
  overflow-y: auto;
  box-shadow: -3px 0 14px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-sizing: border-box;
}
.lc-kg-aside::-webkit-scrollbar {
  width: 5px;
}
.lc-kg-aside::-webkit-scrollbar-thumb {
  background: #d4d0c7;
  border-radius: 3px;
}

/* 分区标头 */
.lc-kg-panel-head {
  font-size: 11.5px;
  font-weight: 700;
  color: #333333;
  letter-spacing: 0.5px;
  border-bottom: 1px solid #e7e4dc;
  padding-bottom: 5px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.lc-kg-badge {
  display: inline-flex;
  align-items: center;
  padding: 1.5px 6.5px;
  border-radius: 2px;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1.4;
  border: 1px solid #d4d0c7;
  user-select: none;
}
.lc-kg-badge-muted { background: #faf9f6; color: #666666; }
.lc-kg-badge-s { background: #fff1f0; color: #a8071a; border-color: #cf1322; }
.lc-kg-badge-a { background: #fffbe6; color: #ad4e00; border-color: #d46b08; }
.lc-kg-badge-b { background: #e6f4ff; color: #0958d9; border-color: #1677ff; }
.lc-kg-badge-c { background: #f5f5f5; color: #595959; border-color: #8c8c8c; }
.lc-kg-badge-type { background: #f8fafc; color: #334155; border-color: #cbd5e1; }
.lc-kg-badge-diff { background: #faf8f5; color: #444444; border-color: #d4d0c7; }

/* 检查器空状态 */
.lc-kg-detail-empty {
  border: 1px dashed #dcd8cf;
  background: #faf9f6;
  border-radius: 4px;
  padding: 24px 14px;
  text-align: center;
  color: #736f66;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.lc-kg-empty-icon {
  font-size: 24px;
  color: #8c857b;
  opacity: 0.85;
}
.lc-kg-empty-title {
  font-size: 13px;
  font-weight: 700;
  color: #2b2b2b;
}
.lc-kg-empty-desc {
  font-size: 11.5px;
  line-height: 1.5;
  color: #7a756b;
}

/* 详情卡片 */
.lc-kg-detail-card {
  border: 1px solid #dcd8cf;
  border-radius: 4px;
  padding: 14px 15px;
  background: #faf9f6;
  line-height: 1.6;
  font-size: 12.5px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.lc-kg-node-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: #111111;
  line-height: 1.35;
  letter-spacing: 0.2px;
}
.lc-kg-node-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 4px;
}
.lc-kg-path {
  font-size: 11.5px;
  color: #555555;
  font-style: italic;
  display: flex;
  align-items: center;
  gap: 4px;
}
.lc-kg-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lc-kg-block-label {
  font-size: 11px;
  font-weight: 700;
  color: #333333;
  letter-spacing: 0.3px;
}
.lc-kg-def-box {
  background: #ffffff;
  border: 1px solid #dedad2;
  border-left: 3px solid #0047ab;
  border-radius: 2px;
  padding: 8px 11px;
  font-size: 12px;
  color: #222222;
  line-height: 1.6;
}
.lc-kg-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #333333;
  display: grid;
  gap: 3px;
}
.lc-kg-relation-grid {
  display: grid;
  gap: 4px;
}
.lc-kg-rel-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  background: #ffffff;
  border: 1px solid #e2ded6;
  border-radius: 2px;
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.lc-kg-rel-row:hover {
  background: #f0ede6;
  border-color: #0047ab;
}
.lc-kg-rel-left {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lc-kg-rel-badge {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 2px;
  font-weight: 700;
}
.lc-kg-rel-in { background: #e0f2fe; color: #0284c7; }
.lc-kg-rel-out { background: #fef3c7; color: #d97706; }
.lc-kg-rel-name {
  font-weight: 600;
  color: #111111;
}
.lc-kg-rel-jump {
  font-size: 11px;
  color: #0047ab;
  white-space: nowrap;
}
.lc-kg-locate-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  background: #ffffff;
  border: 1.5px solid #222222;
  border-radius: 3px;
  color: #111111;
  text-decoration: none;
  font-size: 12px;
  font-weight: 700;
  transition: all 0.15s ease;
}
.lc-kg-locate-btn:hover {
  background: #222222;
  color: #ffffff;
}

/* 图例 */
.lc-kg-legend {
  display: grid;
  gap: 4px;
}
.lc-kg-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #333333;
  font-size: 11.5px;
  cursor: pointer;
  padding: 2.5px 6px;
  border-radius: 2px;
  transition: background 0.15s ease;
}
.lc-kg-legend-item:hover {
  background: #f0ede6;
}
.lc-kg-swatch {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: 0 0 auto;
  border: 1px solid rgba(0,0,0,0.15);
}

@media (max-width: 860px) {
  .lc-kg-shell {
    grid-template-columns: 1fr;
    height: auto;
  }
  #lc-cy {
    height: 480px;
  }
}
</style>"""

_SCRIPT_TEMPLATE = """<script>
(function () {
  const NODES = __NODES__;
  const EDGES = __EDGES__;
  const STATE_KEY = 'lc-kg-state-v2';

  const SECTION_COLORS = [
    ['#e0f2fe', '#0284c7'],
    ['#dcfce7', '#16a34a'],
    ['#fef3c7', '#d97706'],
    ['#ede9fe', '#7c3aed'],
    ['#fee2e2', '#dc2626'],
    ['#ccfbf1', '#0d9488'],
    ['#ffedd5', '#ea580c'],
    ['#f3e8ff', '#9333ea']
  ];

  const TYPE_CONFIG = {
    formula: { color: '#237804', label: '公式' },
    method: { color: '#531dab', label: '方法' },
    theorem: { color: '#0047ab', label: '定理' },
    concept: { color: '#1d4ed8', label: '概念' },
    application: { color: '#d46b08', label: '应用' },
    problem: { color: '#cf1322', label: '题型' },
    pitfall: { color: '#cf1322', label: '易错' }
  };

  const RELATION_CONFIG = {
    prerequisite: { color: '#2563eb', label: '前置' },
    used_with: { color: '#0284c7', label: '配合' },
    related: { color: '#0f766e', label: '关联' },
    derived_from: { color: '#9333ea', label: '推导' },
    easily_confused: { color: '#dc2626', label: '易混' },
    alternative: { color: '#d97706', label: '替代' }
  };

  const esc = (val) => String(val == null ? '' : val)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  // 章节颜色映射
  const chapters = [];
  NODES.forEach((n) => {
    const ch = String(n.chapter || '未分章').trim();
    if (ch && chapters.indexOf(ch) < 0) chapters.push(ch);
  });
  const chapterColors = {};
  chapters.forEach((ch, idx) => {
    chapterColors[ch] = SECTION_COLORS[idx % SECTION_COLORS.length];
  });

  // 状态
  const state = {
    view: 'all',          // 'all' | 'core' | 'connected'
    chapter: '',
    search: '',
    selectedId: ''
  };

  // 构建 Cytoscape 元素
  const elements = [];
  NODES.forEach((node) => {
    const chColor = chapterColors[node.chapter] ? chapterColors[node.chapter][0] : '#f1f5f9';
    const typeColor = TYPE_CONFIG[node.knowledge_type] ? TYPE_CONFIG[node.knowledge_type].color : '#1d4ed8';
    elements.push({
      data: {
        ...node,
        bgColor: chColor,
        borderColor: typeColor,
        label: node.label || node.name
      }
    });
  });

  EDGES.forEach((edge, idx) => {
    const relConf = RELATION_CONFIG[edge.type] || RELATION_CONFIG.related;
    elements.push({
      data: {
        id: 'e_' + idx,
        source: edge.source,
        target: edge.target,
        type: edge.type || 'related',
        label: edge.label || relConf.label,
        evidence: edge.evidence || '',
        lineColor: relConf.color,
        isDashed: edge.type === 'easily_confused'
      }
    });
  });

  const cyContainer = document.getElementById('lc-cy');
  if (!cyContainer || !window.cytoscape) return;

  const cy = cytoscape({
    container: cyContainer,
    elements: elements,
    wheelSensitivity: 0.18,
    minZoom: 0.15,
    maxZoom: 2.8,
    style: [
      {
        selector: 'node',
        style: {
          'shape': 'ellipse',
          'width': 'data(size)',
          'height': 'data(size)',
          'label': 'data(label)',
          'text-wrap': 'wrap',
          'text-max-width': 'data(text_max_width)',
          'font-family': '"Latin Modern Roman", "Songti SC", "SimSun", serif',
          'font-size': 'data(font_size)',
          'font-weight': 700,
          'color': '#111111',
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': 'data(bgColor)',
          'background-opacity': (ele) => {
            const g = String(ele.data('grade') || '').toUpperCase();
            return g === 'S' ? 0.95 : (g === 'A' ? 0.85 : 0.55);
          },
          'border-color': 'data(borderColor)',
          'border-width': (ele) => {
            const g = String(ele.data('grade') || '').toUpperCase();
            return g === 'S' ? 3.6 : (g === 'A' ? 2.4 : 1.8);
          },
          'shadow-blur': (ele) => {
            const g = String(ele.data('grade') || '').toUpperCase();
            return g === 'S' ? 12 : (g === 'A' ? 5 : 2);
          },
          'shadow-color': (ele) => {
            const g = String(ele.data('grade') || '').toUpperCase();
            return g === 'S' ? '#f59e0b' : '#94a3b8';
          },
          'shadow-opacity': (ele) => {
            const g = String(ele.data('grade') || '').toUpperCase();
            return g === 'S' ? 0.45 : 0.2;
          }
        }
      },
      {
        selector: 'edge',
        style: {
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.15,
          'line-color': 'data(lineColor)',
          'target-arrow-color': 'data(lineColor)',
          'line-style': (ele) => ele.data('isDashed') ? 'dashed' : 'solid',
          'width': (ele) => ele.data('type') === 'prerequisite' ? 2.4 : 1.6,
          'label': 'data(label)',
          'font-size': 9.5,
          'font-family': '"Latin Modern Roman", "Times New Roman", serif',
          'font-weight': 600,
          'color': '#333333',
          'text-background-color': '#faf9f6',
          'text-background-opacity': 0.88,
          'text-background-padding': 3,
          'text-rotation': 'autorotate'
        }
      },
      {
        selector: '.faded',
        style: {
          'opacity': 0.12,
          'text-opacity': 0.12
        }
      },
      {
        selector: 'node.selected',
        style: {
          'border-width': 4.6,
          'border-color': '#0047ab',
          'shadow-blur': 18,
          'shadow-color': '#0047ab',
          'shadow-opacity': 0.5,
          'z-index': 20
        }
      },
      {
        selector: 'edge.selected',
        style: {
          'width': 3.6,
          'line-color': '#0047ab',
          'target-arrow-color': '#0047ab',
          'z-index': 25
        }
      }
    ],
    layout: {
      name: 'cose',
      animate: false,
      randomize: false,
      componentSpacing: 130,
      nodeRepulsion: 16000,
      nodeOverlap: 20,
      idealEdgeLength: (edge) => edge.data('type') === 'prerequisite' ? 120 : 150,
      edgeElasticity: 50,
      nestingFactor: 1.2,
      gravity: 0.28,
      numIter: 2600,
      padding: 48
    }
  });

  // 挂载全局方法供 DOM 调用
  window.lcFitCanvas = function () {
    cy.animate({
      fit: { padding: 48 },
      duration: 380,
      easing: 'ease-in-out-cubic'
    });
  };

  window.lcRelayout = function () {
    const layout = cy.layout({
      name: 'cose',
      animate: true,
      animationDuration: 500,
      componentSpacing: 130,
      nodeRepulsion: 16000,
      idealEdgeLength: (edge) => edge.data('type') === 'prerequisite' ? 120 : 150,
      gravity: 0.28,
      padding: 48
    });
    layout.run();
  };

  window.lcFocusNode = function (targetName) {
    if (!targetName) return;
    const cleanTarget = String(targetName).trim();
    const target = cy.nodes().filter((n) => {
      return String(n.data('name')).trim() === cleanTarget
        || String(n.data('label')).trim() === cleanTarget
        || String(n.id()).trim() === cleanTarget
        || String(n.data('kp_id')).trim() === cleanTarget;
    });
    if (target.length) {
      cy.animate({
        center: { eles: target },
        zoom: Math.max(cy.zoom(), 1.2),
        duration: 400,
        easing: 'ease-in-out-cubic'
      });
      target.emit('tap');
    }
  };

  // 详情检查器渲染
  const detailBox = document.getElementById('lc-kg-detail');
  const badgeBox = document.getElementById('lc-kg-status-badge');

  function renderEmptyState() {
    return `
      <div class="lc-kg-detail-empty">
        <div class="lc-kg-empty-icon">⚲</div>
        <div class="lc-kg-empty-title">未选择考点</div>
        <div class="lc-kg-empty-desc">在左侧画布中点击任意考点或连线，查看完整定义、前置依赖、掌握要点与真题考法</div>
      </div>
    `;
  }

  function showNodeDetail(node) {
    if (!detailBox) return;
    if (!node) {
      detailBox.innerHTML = renderEmptyState();
      if (badgeBox) {
        badgeBox.textContent = '未选中';
        badgeBox.className = 'lc-kg-badge lc-kg-badge-muted';
      }
      return;
    }

    const d = node.data();
    const grade = String(d.grade || 'B').toUpperCase();
    const ktype = String(d.knowledge_type || 'concept').toLowerCase();
    const typeLabel = TYPE_CONFIG[ktype] ? TYPE_CONFIG[ktype].label : ktype;
    const importance = Number(d.importance) || 3;
    const difficulty = Number(d.difficulty) || 3;
    const stars = '★'.repeat(Math.min(5, Math.max(1, importance))) + '☆'.repeat(Math.max(0, 5 - importance));

    if (badgeBox) {
      badgeBox.textContent = grade + ' 档核心';
      badgeBox.className = 'lc-kg-badge lc-kg-badge-' + grade.toLowerCase();
    }

    // 统计前置与后置
    const inEdges = node.incomers('edge');
    const outEdges = node.outgoers('edge');

    const inHtml = inEdges.length ? inEdges.map((e) => {
      const srcName = e.source().data('name');
      return `
        <div class="lc-kg-rel-row" onclick="window.lcFocusNode('${esc(srcName)}')">
          <div class="lc-kg-rel-left">
            <span class="lc-kg-rel-badge lc-kg-rel-in">${esc(e.data('label') || '前置')}</span>
            <span class="lc-kg-rel-name">${esc(srcName)}</span>
          </div>
          <span class="lc-kg-rel-jump">对焦 ↗</span>
        </div>
      `;
    }).join('') : '';

    const outHtml = outEdges.length ? outEdges.map((e) => {
      const tgtName = e.target().data('name');
      return `
        <div class="lc-kg-rel-row" onclick="window.lcFocusNode('${esc(tgtName)}')">
          <div class="lc-kg-rel-left">
            <span class="lc-kg-rel-badge lc-kg-rel-out">${esc(e.data('label') || '引出')}</span>
            <span class="lc-kg-rel-name">${esc(tgtName)}</span>
          </div>
          <span class="lc-kg-rel-jump">对焦 ↗</span>
        </div>
      `;
    }).join('') : '';

    const itemsHtml = (d.knowledge_items || []).slice(0, 5).map((item) => `<li>${esc(item)}</li>`).join('');
    const pitfallsHtml = (d.pitfalls || []).slice(0, 3).map((p) => `<li>⚠️ ${esc(p)}</li>`).join('');

    detailBox.innerHTML = `
      <div class="lc-kg-detail-card">
        <div>
          <div class="lc-kg-node-title">${esc(d.name)}</div>
          <div class="lc-kg-node-badges">
            <span class="lc-kg-badge lc-kg-badge-${grade.toLowerCase()}">${grade} 档</span>
            <span class="lc-kg-badge lc-kg-badge-type">${esc(typeLabel)}</span>
            <span class="lc-kg-badge lc-kg-badge-diff">Lv.${difficulty} 难度</span>
            <span class="lc-kg-badge" style="color:#b86a04;border-color:#ffe58f;background:#fffbe6;">${stars}</span>
            ${d.learning_role ? `<span class="lc-kg-badge lc-kg-badge-muted">${esc(d.learning_role)}</span>` : ''}
          </div>
        </div>

        <div class="lc-kg-path">
          <span>${esc(d.chapter)}</span> ❯ <span>${esc(d.topic)}</span>
        </div>

        ${d.explain ? `
          <div class="lc-kg-block">
            <div class="lc-kg-block-label">核心考查与定义</div>
            <div class="lc-kg-def-box">${esc(d.explain)}</div>
          </div>
        ` : ''}

        ${itemsHtml ? `
          <div class="lc-kg-block">
            <div class="lc-kg-block-label">必须掌握的条目</div>
            <ul class="lc-kg-list">${itemsHtml}</ul>
          </div>
        ` : ''}

        ${inHtml ? `
          <div class="lc-kg-block">
            <div class="lc-kg-block-label">前置基础依赖 (入边 · ${inEdges.length})</div>
            <div class="lc-kg-relation-grid">${inHtml}</div>
          </div>
        ` : ''}

        ${outHtml ? `
          <div class="lc-kg-block">
            <div class="lc-kg-block-label">推导与引出后置 (出边 · ${outEdges.length})</div>
            <div class="lc-kg-relation-grid">${outHtml}</div>
          </div>
        ` : ''}

        ${pitfallsHtml ? `
          <div class="lc-kg-block">
            <div class="lc-kg-block-label">易错警示</div>
            <ul class="lc-kg-list" style="color:#cf1322;">${pitfallsHtml}</ul>
          </div>
        ` : ''}

        ${d.kp_id ? `
          <div style="margin-top: 4px;">
            <a class="lc-kg-locate-btn" href="#ck-card-${esc(d.kp_id)}">
              <span>在清单正文中定位卡片</span>
              <span>↓</span>
            </a>
          </div>
        ` : ''}
      </div>
    `;
  }

  showNodeDetail(null);

  // 过滤应用逻辑
  function applyFilters() {
    const q = (state.search || '').trim().toLowerCase();
    let visibleCount = 0;

    cy.nodes().forEach((node) => {
      const g = String(node.data('grade') || '').toUpperCase();
      const ch = String(node.data('chapter') || '').trim();
      const deg = Number(node.data('degree')) || 0;
      const inDeg = Number(node.data('in_degree')) || 0;
      const outDeg = Number(node.data('out_degree')) || 0;
      const name = String(node.data('name') || '').toLowerCase();

      let visible = true;
      if (state.view === 'core' && g !== 'S' && g !== 'A') visible = false;
      if (state.view === 'connected' && deg === 0) visible = false;
      if (state.view === 'dag' && inDeg === 0 && outDeg === 0) visible = false;
      if (state.chapter && ch !== state.chapter) visible = false;
      if (q && name.indexOf(q) < 0) visible = false;

      node.style('display', visible ? 'element' : 'none');
      if (visible) visibleCount += 1;
    });

    let visibleEdgeCount = 0;
    cy.edges().forEach((edge) => {
      const srcVisible = edge.source().style('display') !== 'none';
      const tgtVisible = edge.target().style('display') !== 'none';
      let edgeVisible = srcVisible && tgtVisible;
      if (state.view === 'dag' && edge.data('type') !== 'prerequisite') {
        edgeVisible = false;
      }
      edge.style('display', edgeVisible ? 'element' : 'none');
      if (edgeVisible) visibleEdgeCount += 1;
    });

    const countBox = document.getElementById('lc-kg-count');
    if (countBox) {
      countBox.innerHTML = `已显示 <b>${visibleCount}</b> / 共 ${NODES.length} 个考点 · ${visibleEdgeCount} 条关系`;
    }
  }

  applyFilters();

  // 事件监听：点击节点
  cy.on('tap', 'node', (evt) => {
    const node = evt.target;
    cy.elements().removeClass('faded selected');
    node.addClass('selected');
    state.selectedId = node.id();
    showNodeDetail(node);
  });

  // 点击边
  cy.on('tap', 'edge', (evt) => {
    const edge = evt.target;
    cy.elements().removeClass('faded selected');
    edge.addClass('selected');
    edge.connectedNodes().addClass('selected');
  });

  // 点击空白
  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass('faded selected');
      state.selectedId = '';
      showNodeDetail(null);
    }
  });

  // 悬停高亮一跳邻居
  cy.on('mouseover', 'node', (evt) => {
    const node = evt.target;
    cy.elements().addClass('faded');
    node.closedNeighborhood().removeClass('faded');
    node.removeClass('faded');
  });

  cy.on('mouseout', 'node', () => {
    cy.elements().removeClass('faded');
  });

  // 视图切换按钮绑定
  document.querySelectorAll('#lc-kg-views button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#lc-kg-views button').forEach((b) => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      state.view = btn.getAttribute('data-view') || 'all';
      applyFilters();
      window.lcFitCanvas();
    });
  });

  // 章节下拉选择
  const chapterSelect = document.getElementById('lc-kg-chapter-select');
  if (chapterSelect) {
    chapters.forEach((ch) => {
      const opt = document.createElement('option');
      opt.value = ch;
      opt.textContent = ch;
      chapterSelect.appendChild(opt);
    });
    chapterSelect.addEventListener('change', () => {
      state.chapter = chapterSelect.value;
      applyFilters();
      window.lcFitCanvas();
    });
  }

  // 搜索框
  const searchInput = document.getElementById('lc-kg-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      state.search = searchInput.value;
      applyFilters();
    });
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = (searchInput.value || '').trim();
        if (val) window.lcFocusNode(val);
      }
    });
  }

  // 图例绑定
  const legendBox = document.getElementById('lc-kg-legend');
  if (legendBox) {
    legendBox.innerHTML = chapters.map((ch) => {
      const colorPair = chapterColors[ch] || ['#e0f2fe', '#0284c7'];
      const count = NODES.filter((n) => n.chapter === ch).length;
      return `
        <div class="lc-kg-legend-item" onclick="document.getElementById('lc-kg-chapter-select').value='${esc(ch)}'; document.getElementById('lc-kg-chapter-select').dispatchEvent(new Event('change'));">
          <span class="lc-kg-swatch" style="background:${colorPair[0]}; border-color:${colorPair[1]};"></span>
          <span>${esc(ch)} (${count})</span>
        </div>
      `;
    }).join('');
  }

  const relLegendBox = document.getElementById('lc-kg-rel-legend');
  if (relLegendBox) {
    relLegendBox.innerHTML = Object.entries(RELATION_CONFIG).slice(0, 4).map(([key, conf]) => {
      return `
        <div class="lc-kg-legend-item" style="cursor:default;">
          <span style="display:inline-block;width:16px;height:2px;background:${conf.color};margin-right:4px;"></span>
          <span>${esc(conf.label)}关系</span>
        </div>
      `;
    }).join('');
  }

  // 初始自适应视野
  cy.ready(() => {
    cy.fit(undefined, 48);
  });
})();
</script>"""


def build_checklist_graph_embed(nodes: list[dict], edges: list[dict], title: str = "") -> str:
    """checklist 内嵌的高级知识图谱组件（学术风格 + 力导向布局 + 丰富交互）。"""
    heading = (title or "").strip() or "考点知识图谱"
    script = _SCRIPT_TEMPLATE.replace(
        "__NODES__", dumps(nodes, ensure_ascii=False)
    ).replace(
        "__EDGES__", dumps(edges, ensure_ascii=False)
    )

    return f"""{_STYLE}
<div class="lc-kg">
  <div class="lc-kg-bar">
    <div class="lc-kg-title-group">
      <strong>{escape(heading)}</strong>
      <span class="lc-kg-count" id="lc-kg-count"></span>
    </div>
    <div class="lc-kg-toolbar">
      <div class="lc-kg-btn-group" id="lc-kg-views">
        <button type="button" class="lc-kg-tool-btn is-active" data-view="all">全部考点</button>
        <button type="button" class="lc-kg-tool-btn" data-view="dag">前置主干(DAG)</button>
        <button type="button" class="lc-kg-tool-btn" data-view="core">核心(S/A)</button>
      </div>
      <select id="lc-kg-chapter-select" class="lc-kg-select">
        <option value="">全部章节</option>
      </select>
      <button type="button" class="lc-kg-btn-single" onclick="window.lcFitCanvas && window.lcFitCanvas()" title="视口居中自适应">居中自适应</button>
      <button type="button" class="lc-kg-btn-single" onclick="window.lcRelayout && window.lcRelayout()" title="重新排列图谱">重新排版</button>
      <input type="search" id="lc-kg-search" class="lc-kg-search" placeholder="搜索考点 (Enter定位)…">
    </div>
  </div>
  <div class="lc-kg-shell">
    <div class="lc-kg-canvas-container">
      <div id="lc-cy"></div>
    </div>
    <aside class="lc-kg-aside">
      <div class="lc-kg-panel-head">
        <span>考点详情检查器</span>
        <span id="lc-kg-status-badge" class="lc-kg-badge lc-kg-badge-muted">未选中</span>
      </div>
      <div id="lc-kg-detail" class="detail-container"></div>
      <div class="lc-kg-panel-head" style="margin-top: 10px;">
        <span>章节分类图例 (点击过滤)</span>
      </div>
      <div id="lc-kg-legend" class="lc-kg-legend"></div>
      <div class="lc-kg-panel-head" style="margin-top: 10px;">
        <span>核心关系图例</span>
      </div>
      <div id="lc-kg-rel-legend" class="lc-kg-legend"></div>
    </aside>
  </div>
</div>
{script}"""
