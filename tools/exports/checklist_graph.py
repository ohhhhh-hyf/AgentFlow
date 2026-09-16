"""tools/exports/checklist_graph.py —— checklist 内嵌的学术风格考点知识图谱组件。

设计原则（参考 knowledge_graph.py）：
- 纯平级知识点圆形节点（无复合簇、无嵌套框，杜绝挤压重叠）；
- 外接圆几何尺寸精准包裹多行居中文字；
- 确定性初始章节空间排布 + Cytoscape cose 力导向布局，章节聚集有序、舒展透气；
- 核心前置主线（Prerequisites DAG）优先，大幅剪枝冗余连线，适合学生掌握学习脉络；
- 移除「考点详情检查器」，精简侧栏为章节图例与关系图例，给画布最大横向空间；
- 图例与工具栏去除所有括号和数字计数，界面清晰洗练。
"""
from __future__ import annotations

from html import escape
from json import dumps

__all__ = ["build_checklist_graph_embed"]

_STYLE = """<style>
.lc-kg {
  margin: 14px 0 28px;
  border: 1px solid #d4d0c7;
  border-radius: 4px;
  overflow: hidden;
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02);
  font-family: "Latin Modern Roman", "Computer Modern Roman", "CMU Serif", "Times New Roman", Times, "Songti SC", "SimSun", "STSong", serif;
  box-sizing: border-box;
}
.lc-kg-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1.5px solid #222222;
  background: #faf9f6;
  flex-wrap: wrap;
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
  padding: 5px 12px;
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
  min-width: 130px;
  transition: all 0.18s ease;
}
.lc-kg-search:focus {
  border-color: #0047ab;
  box-shadow: 0 0 0 2px rgba(0, 71, 171, 0.12);
  min-width: 170px;
}

/* 主体分栏：画布 + 右侧图例栏 */
.lc-kg-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 210px;
  min-height: 650px;
  height: 650px;
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

/* 右侧图例栏 */
.lc-kg-aside {
  border-left: 1.5px solid #d4d0c7;
  background: #ffffff;
  padding: 16px 16px;
  overflow-y: auto;
  box-shadow: -3px 0 14px rgba(0, 0, 0, 0.03);
  display: flex;
  flex-direction: column;
  gap: 12px;
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

/* 图例项列表 */
.lc-kg-legend {
  display: grid;
  gap: 3px;
}
.lc-kg-legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #333333;
  font-size: 11.5px;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 2px;
  transition: background 0.15s ease;
  user-select: none;
}
.lc-kg-legend-item:hover {
  background: #f0ede6;
}
.lc-kg-swatch {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: 0 0 auto;
  border: 1px solid rgba(0, 0, 0, 0.18);
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
    view: 'all',          // 'all' | 'dag' | 'core'
    chapter: '',
    search: '',
    selectedId: ''
  };

  // 构建 Cytoscape 元素（平级节点 + 语义边）
  const elements = [];
  NODES.forEach((node) => {
    const chColor = chapterColors[node.chapter] ? chapterColors[node.chapter][0] : '#f1f5f9';
    const typeColor = TYPE_CONFIG[node.knowledge_type] ? TYPE_CONFIG[node.knowledge_type].color : '#1d4ed8';
    const ele = {
      data: {
        ...node,
        bgColor: chColor,
        borderColor: typeColor,
        label: node.label || node.name
      }
    };
    if (node.position) {
      ele.position = node.position;
    }
    elements.push(ele);
  });

  EDGES.forEach((edge, idx) => {
    const relConf = RELATION_CONFIG[edge.type] || RELATION_CONFIG.related;
    elements.push({
      data: {
        id: 'e-' + idx,
        source: edge.source,
        target: edge.target,
        type: edge.type || 'related',
        label: edge.label || relConf.label || '',
        evidence: edge.evidence || ''
      }
    });
  });

  const cyEl = document.getElementById('lc-cy');
  if (!cyEl || typeof cytoscape === 'undefined') {
    if (cyEl) cyEl.innerHTML = '<p style="padding:20px;color:#666;font-style:italic;">图谱引擎未加载，请确保联网或脚本可用。</p>';
    return;
  }

  const cy = cytoscape({
    container: cyEl,
    elements: elements,
    wheelSensitivity: 0.18,
    minZoom: 0.25,
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
          'text-max-width': (ele) => ele.data('text_max_width') || (ele.data('size') * 0.8),
          'font-size': (ele) => ele.data('font_size') || 11.5,
          'font-family': '"Latin Modern Roman", "Computer Modern Roman", "CMU Serif", "Times New Roman", Times, "Songti SC", "SimSun", serif',
          'font-weight': 700,
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': 'data(bgColor)',
          'background-opacity': 0.95,
          'border-color': 'data(borderColor)',
          'border-width': (ele) => {
            const g = ele.data('grade');
            return g === 'S' ? 3.2 : (g === 'A' ? 2.4 : 1.8);
          },
          'color': '#111111',
          'shadow-blur': 4,
          'shadow-color': '#000000',
          'shadow-opacity': 0.06,
          'shadow-offset-y': 1,
          'transition-property': 'border-width, border-color, shadow-blur, shadow-color, opacity',
          'transition-duration': '0.18s'
        }
      },
      {
        selector: 'edge',
        style: {
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.1,
          'width': (ele) => ele.data('type') === 'prerequisite' ? 2.2 : 1.4,
          'line-color': (ele) => (RELATION_CONFIG[ele.data('type')] || RELATION_CONFIG.related).color,
          'target-arrow-color': (ele) => (RELATION_CONFIG[ele.data('type')] || RELATION_CONFIG.related).color,
          'line-style': (ele) => ele.data('type') === 'related' ? 'dashed' : 'solid',
          'line-opacity': 0.65,
          'label': 'data(label)',
          'font-size': 10,
          'font-family': '"Latin Modern Roman", "Times New Roman", serif',
          'font-weight': 600,
          'color': '#333333',
          'text-background-color': '#faf9f6',
          'text-background-opacity': 0.9,
          'text-background-padding': 2.5,
          'text-rotation': 'autorotate'
        }
      },
      {
        selector: '.faded',
        style: {
          'opacity': 0.1,
          'text-opacity': 0.1
        }
      },
      {
        selector: 'node.selected',
        style: {
          'border-color': '#0047ab',
          'border-width': 4.5,
          'shadow-blur': 14,
          'shadow-color': '#0047ab',
          'shadow-opacity': 0.35,
          'z-index': 99
        }
      },
      {
        selector: 'edge.selected',
        style: {
          'width': 3.6,
          'line-color': '#0047ab',
          'target-arrow-color': '#0047ab',
          'line-opacity': 1,
          'z-index': 90
        }
      }
    ],
    layout: {
      name: 'cose',
      animate: false,
      randomize: false,
      componentSpacing: 135,
      nodeRepulsion: 18000,
      idealEdgeLength: (edge) => edge.data('type') === 'prerequisite' ? 120 : 155,
      edgeElasticity: 70,
      nestingFactor: 0.9,
      gravity: 0.28,
      numIter: 2500,
      padding: 48
    }
  });

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
      componentSpacing: 135,
      nodeRepulsion: 18000,
      idealEdgeLength: (edge) => edge.data('type') === 'prerequisite' ? 120 : 155,
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

  // 过滤应用逻辑
  function applyFilters() {
    const q = (state.search || '').trim().toLowerCase();
    let visibleCount = 0;

    cy.nodes().forEach((node) => {
      const g = String(node.data('grade') || '').toUpperCase();
      const ch = String(node.data('chapter') || '').trim();
      const inDeg = Number(node.data('in_degree')) || 0;
      const outDeg = Number(node.data('out_degree')) || 0;
      const name = String(node.data('name') || '').toLowerCase();

      let visible = true;
      if (state.view === 'core' && g !== 'S' && g !== 'A') visible = false;
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

  // 事件监听：点击节点（高亮一跳邻域，淡化其余）
  cy.on('tap', 'node', (evt) => {
    const node = evt.target;
    cy.elements().removeClass('selected');
    node.addClass('selected');
    state.selectedId = node.id();

    cy.elements().addClass('faded');
    node.removeClass('faded');
    node.closedNeighborhood().removeClass('faded');
  });

  // 点击边
  cy.on('tap', 'edge', (evt) => {
    const edge = evt.target;
    cy.elements().removeClass('selected');
    edge.addClass('selected');
    edge.connectedNodes().addClass('selected');

    cy.elements().addClass('faded');
    edge.removeClass('faded');
    edge.connectedNodes().removeClass('faded');
  });

  // 点击空白还原
  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass('faded selected');
      state.selectedId = '';
    }
  });

  // 悬停高亮一跳邻居（未固定选中时生效）
  cy.on('mouseover', 'node', (evt) => {
    if (state.selectedId) return;
    const node = evt.target;
    cy.elements().addClass('faded');
    node.closedNeighborhood().removeClass('faded');
    node.removeClass('faded');
  });

  cy.on('mouseout', 'node', () => {
    if (state.selectedId) return;
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

  // 图例绑定（去除括号和数字计数，纯净章节名称）
  const legendBox = document.getElementById('lc-kg-legend');
  if (legendBox) {
    legendBox.innerHTML = chapters.map((ch) => {
      const colorPair = chapterColors[ch] || ['#e0f2fe', '#0284c7'];
      return `
        <div class="lc-kg-legend-item" onclick="document.getElementById('lc-kg-chapter-select').value='${esc(ch)}'; document.getElementById('lc-kg-chapter-select').dispatchEvent(new Event('change'));">
          <span class="lc-kg-swatch" style="background:${colorPair[0]}; border-color:${colorPair[1]};"></span>
          <span>${esc(ch)}</span>
        </div>
      `;
    }).join('');
  }

  // 核心关系图例
  const relLegendBox = document.getElementById('lc-kg-rel-legend');
  if (relLegendBox) {
    relLegendBox.innerHTML = Object.entries(RELATION_CONFIG).slice(0, 4).map(([key, conf]) => {
      return `
        <div class="lc-kg-legend-item" style="cursor:default;">
          <span style="display:inline-block;width:15px;height:2.5px;background:${conf.color};margin-right:4px;border-radius:1px;"></span>
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
    """checklist 内嵌的高级知识图谱组件（学术风格 + 力导向布局 + 纯净图例）。"""
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
        <button type="button" class="lc-kg-tool-btn" data-view="dag">前置主干</button>
        <button type="button" class="lc-kg-tool-btn" data-view="core">核心考点</button>
      </div>
      <select id="lc-kg-chapter-select" class="lc-kg-select">
        <option value="">全部章节</option>
      </select>
      <button type="button" class="lc-kg-btn-single" onclick="window.lcFitCanvas && window.lcFitCanvas()" title="视口居中自适应">居中自适应</button>
      <button type="button" class="lc-kg-btn-single" onclick="window.lcRelayout && window.lcRelayout()" title="重新排列图谱">重新排版</button>
      <input type="search" id="lc-kg-search" class="lc-kg-search" placeholder="搜索考点…">
    </div>
  </div>
  <div class="lc-kg-shell">
    <div class="lc-kg-canvas-container">
      <div id="lc-cy"></div>
    </div>
    <aside class="lc-kg-aside">
      <div class="lc-kg-panel-head">
        <span>章节分类</span>
      </div>
      <div id="lc-kg-legend" class="lc-kg-legend"></div>
      <div class="lc-kg-panel-head" style="margin-top: 10px;">
        <span>核心关系</span>
      </div>
      <div id="lc-kg-rel-legend" class="lc-kg-legend"></div>
    </aside>
  </div>
</div>
{script}"""
