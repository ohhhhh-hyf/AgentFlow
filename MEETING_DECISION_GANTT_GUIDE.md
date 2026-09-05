# 会议决策碰撞与时空交互甘特流（Decision Collision & Temporal Gantt Waterfall）实施与交付规范指南

> **版本**：v1.0.0  
> **定位**：AgentFlow 会议领域高阶战略级任务线  
> **核心哲学**：**上篇断决策之因果（WHY & SACRIFICE），下篇定工程之交割（WHO & WHEN）**。将传统扁平、枯燥的流水账纪要，升维为极具商业价值与管理穿透力的**“企业决策与交付作战室”**。  
> **成本控制原则**：**严格坚守单次 LLM 抽取（单场增量 Token $\le$ 450）+ Python 确定性拓扑计算（关键路径与零缓冲分析）+ 纯前端 CSS/SVG 交互渲染（0 额外后端延迟）**。

---

## 目录
1. [一、 业务定位与核心价值矩阵](#一-业务定位与核心价值矩阵)
2. [二、 全流程技术架构与数据模型 (How-To-Do)](#二-全流程技术架构与数据模型-how-to-do)
   - 2.1 结构化契约定义（Contracts）
   - 2.2 抽取提示词工程（Prompt Engineering）
   - 2.3 Python 确定性拓扑与关键路径引擎（Deterministic Topo Math）
3. [三、 最终生成的 Markdown 交付物标准规范](#三-最终生成的-markdown-交付物标准规范)
4. [四、 最终生成的 HTML 交互页面设计全景（LaTeX Academic Showcase）](#四-最终生成的-html-交互页面设计全景latex-academic-showcase)
   - 4.1 视觉调性与样式规范
   - 4.2 模块一：决策碰撞辩论卡与得失天平
   - 4.3 模块二：流式交付甘特瀑布与关键路径高亮
   - 4.4 跨模块“因果-排期”双向联动引擎
5. [五、 分步实施路线图（三步走规划）](#五-分步实施路线图三步走规划)

---

## 一、 业务定位与核心价值矩阵

### 1.1 为什么需要这个任务线？
市面上现有的会议 AI 产品均停留在**“录音整理员”**阶段，产出的纪要存在致命硬伤：
- **抹杀了决策内幕**：只记录最终结论，抹去了会上的激烈拉扯与方案对比。半年后项目出事故，没人知道当初为什么选了方案 B 放弃了方案 A；
- **遗漏了妥协代价**：任何决策都是妥协，缺乏对“付出了什么隐性代价（技术债/体验损伤）”的权衡记录；
- **割裂了排期因果**：待办事项只是一堆冰冷的截止时间，完全看不出**“谁在卡谁”**、**“哪项任务延期会导致全盘崩盘”**。

### 1.2 双螺旋价值模型
```
┌────────────────────────────────────────────────────────────────────────┐
│                      决策与交付作战室 (Decision Hub)                    │
├───────────────────────────────────┬────────────────────────────────────┤
│   上篇 · 决策博弈法庭 (Strategic)  │   下篇 · 时空交付甘特流 (Tactical) │
├───────────────────────────────────┼────────────────────────────────────┤
│ • 还原双方核心争议与交锋论点       │ • 厘清任务前置依赖与交接时序       │
│ • 沉淀破局妥协公约 (Accord)       │ • 算法自动标出【关键路径】(Critical)│
│ • 刻画得失天平 (Trade-Off)        │ • 毫秒级探测【零缓冲高危阻塞】      │
│ • 设立翻盘回滚红线 (Rollback)     │ • 鼠标悬停实时追踪前置下游链路     │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 二、 全流程技术架构与数据模型 (How-To-Do)

### 2.1 结构化契约定义（Contracts）
在 `domain/meeting/tasks/decision_gantt/contracts.py` 中定义极简、高密度的 Pydantic 模型：

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class ArgumentSide(BaseModel):
    speaker: str = Field(description="立论发言人")
    stance: str = Field(description="核心立场或主张")
    argument: str = Field(description="支撑事实或主要论据")

class DecisionCollisionItem(BaseModel):
    case_id: str = Field(description="决议案唯一编号，如 D1, D2")
    topic: str = Field(description="争议焦点议题")
    archetype: Literal["data_driven", "authority_fiat", "quid_pro_quo", "consensus"] = Field(
        description="裁决形态：数据迫降 / 权威强推 / 利益妥协交换 / 自然充分共识"
    )
    pro_side: ArgumentSide = Field(description="正面/保留/原有主张方")
    con_side: ArgumentSide = Field(description="反对/变革/重构主张方")
    accord: str = Field(description="破局妥协公约：各方各让一步后的终局共识")
    gain: str = Field(description="本决策换取的核心价值或收益")
    sacrifice: str = Field(description="本决策主动放弃的权益、灵活性或承受的代价")
    rollback_trigger: str = Field(description="触发重新讨论或回滚方案的客观红线条件（若无则填'无明确回滚预警'）")
    evidence_quote: str = Field(description="会议原文中最具冲突或最终拍板的引句")

class TemporalActionItem(BaseModel):
    action_id: str = Field(description="行动项编号，如 A1, A2")
    case_id: str = Field(description="关联的决议案编号，如 D1；若无明确关联填'general'")
    task: str = Field(description="具体交付任务名称")
    owner: str = Field(description="责任人")
    start_time: str = Field(description="开始或启动时间（如 8-19 或 immediate）")
    deadline: str = Field(description="截止交付时间（如 8-20 12:00）")
    depends_on: list[str] = Field(default_factory=list, description="前置强依赖的 action_id 列表，如 ['A1']")
    deliverable: str = Field(description="可验收的具体产物形式，如 PRD/测试报告/接口")

class DecisionGanttReport(BaseModel):
    title: str = Field(description="会议研讨主题")
    decisions: list[DecisionCollisionItem] = Field(description="重大决策博弈清单（通常 1~3 项）")
    actions: list[TemporalActionItem] = Field(description="带有时间依赖关系的交付任务链")
```

### 2.2 抽取提示词工程（Prompt Engineering）
采用**高密度公理式 Prompt**，单次提取，禁止冗余发散：

```markdown
你是一个顶尖的商业战略与工程交付决策分析专家。请阅读会议转写，提取会议中的【决策碰撞案】与【时空交付链】。

【抽取原则】：
1. 决策碰撞（Decisions）：只提取存在观点拉扯、方案对比或妥协的议题（不超过3个）。普通一致通知不计入。必须提炼“得（换取了什么）”与“失（付出了什么代价）”。
2. 时空依赖（Actions）：提炼有明确交付责任人与时间节点的行动项，关键是推导出行动项之间的前后依赖关系（depends_on）。若 B 的开始依赖 A 的产出，必须明确标记。
3. 契约匹配：严禁编造时间；无明确依赖的填空列表。
```

### 2.3 Python 确定性拓扑与关键路径引擎（0 Token）
在 Python 侧编写计算函数 `calculate_critical_path(actions)`，无需 LLM 计算：
1. **DAG 依赖图构建**：基于 action_id 与 depends_on 构建有向无环图；
2. **关键路径（Critical Path）识别**：计算从起点到终点耗时最长、无缓冲（Slack Time = 0）的任务链路；
3. **零缓冲警报（Zero-Slack Alert）**：当下游任务的开始时间与上游任务的截止时间间隔 $\le 0.5$ 天时，打上高危阻塞标记；
4. **决策-行动双向交叉索引**：为每个 Action 自动注入其所属的 Decision 元数据。

---

## 三、 最终生成的 Markdown 交付物标准规范

导出的 `decision_gantt.md` 应具备如同高端咨询公司战略报告与交付说明书般的高级质感：

```markdown
# 小艺慧记内测准入冲刺会 · 决策碰撞与时空交付报告

> **会议时间**：2026年9月1日 14:00 - 15:30  
> **主持人**：周宁（技术负责人） | **参会人**：林夏、赵衡、钱屿、陈澄、许安  
> **战略定调**：收敛内测前阻塞项，取消自定义模板，锁定8月20日内测回归底线。

---

## 第一部分：决策碰撞与妥协推演 (The Decision Arena)

### CASE #01 · 架构定夺：剥离 minutes_trace 用户自定义模板入口
- **裁决形态**：`[数据迫降型 · Data-Driven]`
- **争议议题**：是否在即将开启的内测版本中保留用户自定义纪要模板？
- **交锋实况**：
  - **[立论派 · 维持现状] 林夏**：销售复盘与技术会议差异极大，需要用户自行贴入框架，避免通用模板无法满足诉求。
  - **[质询派 · 彻底剥离] 周宁、陈澄**：测试表明用户随意粘贴无效模板会导致纪要结构变形、关键结论丢失，且引发 40% 的排版乱码。
- **破局妥协公约 (Accord)**：
  > 林夏同意剥离自定义上传入口；周宁在架构上补偿“首选会议场景自动识别，未识别则无缝降级为通用标准兜底模板”。
- **⚖️ 得失天平 (Trade-Off Balance)**：
  - **▲ 换取的核心价值 (Gain)**：纪要生成结构稳定性提升 40%，研发无需编写容错规则，测试回归面彻底收敛。
  - **▼ 承受的隐性代价 (Sacrifice)**：剥夺了特殊个性化行业客户的定制自由度，需承担早期种子用户的习惯适应成本。
- **⚠️ 翻盘回滚红线 (Rollback Trigger)**：
  若 8 月 20 日前场景自动匹配准确率低于 80%，或出现超过 3 种未被兜底的常规会议场景，重新评估恢复自定义入口。
- **🔗 原文对决证据**：
  > “林夏：场景模板不再依赖用户自定义上传，而是先做会议场景匹配，匹配不到就走通用兜底模板...”

---

### CASE #02 · 交互定夺：历史会议记忆引用的正文呈现范式
- **裁决形态**：`[充分共识型 · Consensus]`
- **争议议题**：记忆来源是作为正文段落展示，还是做成学术下划线跳转？
- **破局公约**：采纳赵衡方案，正文受记忆影响处统一加淡蓝下划线，底部呈现来源；采纳许安建议，隐去“记忆1、记忆2”等工程代号，改为“参考过的历史会议”，展示长度限制在 3 行内。
- **得失天平**：
  - **▲ 得**：兼顾了正文阅读流畅度与学术溯源严谨性。
  - **▼ 失**：前端需额外编写下划线点击脉冲动画与折叠展示组件。

---

## 第二部分：时空依赖与交付甘特流 (Temporal Waterfall)

### 2.1 交付拓扑指标看板
- **计划交付节点**：2026-08-20 24:00 (内测评审)
- **总交付工项**：5 项核心行动项
- **关键路径耗时**：36 小时（无宽限缓冲）
- **🔴 脆弱链路警报**：**A1/A2 (林夏/赵衡) ➔ A4 (钱屿) ➔ A5 (陈澄) ➔ 交付门禁**
  > **排期健康度警示**：陈澄的回归依赖钱屿前端改动，钱屿只有半个工作日开发窗口，前置任何环节延误半天，8月20日内测将全线延期！

### 2.2 交付时空瀑布流水表

| 编号 | 交付行动项 | 责任人 | 起始时刻 | 截止时刻 | 强依赖前置 | 关键路径 | 关联决议 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **A1** | 批注情绪化降噪与提示词语气平抑 | 林夏 | 即刻 | 08-19 18:00 | — | ★ 关键路径 | CASE #01 |
| **A2** | 引用文案重塑为“参考历史会议”及限长 | 赵衡 | 即刻 | 08-19 18:00 | — | ★ 关键路径 | CASE #02 |
| **A3** | 场景自动匹配与兜底模板规则入库 | 周宁 | 即刻 | 08-19 20:00 | — | 次要路径 | CASE #01 |
| **A4** | 移除模板入口 + 来源下划线 Hover 提示 | 钱屿 | 08-19 18:00 | 08-20 12:00 | **A1, A2** | ★ 关键路径 | CASE #01, #02 |
| **A5** | 纪要记忆、溯源纪要、笔记图谱全量回归报告 | 陈澄 | 08-20 12:00 | 08-20 24:00 | **A3, A4** | ★ 关键路径 | 全局门禁 |

```
【交付时空拓扑图 (ASCII Stream)】
[8/19 18:00]                 [8/20 12:00]                 [8/20 24:00]
A1 (林夏·提示词) ──┐
                  ├──────▶ A4 (钱屿·前端控件) ───┐
A2 (赵衡·文案)   ──┘                             ├──▶ A5 (陈澄·全量回归) ──▶ [🏁 内测门禁]
                                                 │
A3 (周宁·规则兜底) ──────────────────────────────┘
```
```

---

## 四、 最终生成的 HTML 交互页面设计全景（LaTeX Academic Showcase）

HTML 采用与会议纪要、风险清单一致的 **LaTeX Paper 学术研讨（Academic Showcase）** 风格：
- 全局底色：`#f6f5f0`（温暖米纸质感）；
- 容器：`.ck-doc`（白色纸张卡片，`border: 1px solid #d4d0c7`，柔和纸张微阴影）；
- 排版：Latin Modern Roman 衬线体、双黑线标题栏、小写小型大写字母（`small-caps`）；
- 主强调色：经典 LaTeX 引用蓝 `#0047ab`、警示砖红 `#cf1322`、稳妥森林绿 `#237804`。

### 4.1 页面交互全景架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🏛️  MEETING DECISION & TEMPORAL WATERFALL REPORT          [LaTeX Paper]   │
│ 小艺慧记内测准入冲刺会 · 决策碰撞与时空交付作战室                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 📊 【全局作战看板】 2件重大博弈决议 | 5项交割任务 | 关键路径: 36h | ⚠️缓冲: 0天  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌─ 模块一：决策碰撞博弈法庭 (The Decision Arena) ─────────────────────────┐  │
│ │                                                                         │  │
│ │  CASE #01  关于「剥离 minutes_trace 用户自定义模板」的决议   [数据迫降型] │  │
│ │  ┌─────────────────────────────────┬─────────────────────────────────┐  │  │
│ │  │ [立论派 · 林夏]                 │ [反驳派 · 周宁、陈澄]           │  │  │
│ │  │ 必须保留灵活性以应对复杂场景    │ 随意贴模板导致结构坍塌40%       │  │  │
│ │  └─────────────────────────────────┴─────────────────────────────────┘  │  │
│ │  【破局妥协公约】 林夏同意取消自定义，周宁承诺“场景匹配+通用兜底”补偿     │  │
│ │  ┌─ ⚖️ 得失天平 ───────────────────────────────────────────────────┐  │  │
│ │  │ [▲ 获得] 结构强稳定性+40%   │   [▼ 牺牲] 特殊客户自由定制空间  │  │  │
│ │  └─────────────────────────────┴───────────────────────────────────┘  │  │
│ │  ⚠️ 翻盘回滚红线：若 8/20 前场景匹配准确率低于 80%，恢复自定义入口       │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│ ┌─ 模块二：时空交付甘特瀑布 (Temporal Waterfall Stream) ──────────────────┐  │
│ │                                                                         │  │
│ │ 时间轴 ────▶ 8月19日 18:00 ──────▶ 8月20日 12:00 ──────▶ 8月20日 24:00   │  │
│ │ 林夏 (A1) ─────┐                                                       │  │
│ │ 赵衡 (A2) ─────┼─────────▶ 钱屿 (A4) ────────┐                         │  │
│ │ 周宁 (A3) ─────┼──────────────────────────────┼───▶ 陈澄 (A5) ──▶ [门禁]│  │
│ │                                               │     ★ 关键路径          │  │
│ │ 🔴 关键路径 (Critical Path): A1/A2 ➔ A4 ➔ A5 (全程无宽限，盯防重点)      │  │
│ └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 模块一核心 HTML 结构示例（决策碰撞与得失天平）

```html
<!-- 决策博弈卡片 -->
<div class="decision-case-card" id="case-D1">
  <div class="case-header">
    <div class="case-title-row">
      <span class="case-tag">CASE 01</span>
      <h3>关于「剥离 minutes_trace 用户自定义模板」的决议案</h3>
    </div>
    <span class="archetype-badge badge-data">数据迫降型 · Data-Driven</span>
  </div>

  <div class="dispute-box">
    <strong>【争议焦点】</strong>内测版本是否允许用户自主上传会议纪要骨架模板？
  </div>

  <div class="clash-grid">
    <div class="clash-side side-pro">
      <div class="side-title">立论主张 · 维持现状</div>
      <div class="side-speaker">林夏（产品经理）</div>
      <p class="side-arg">“销售复盘与常规会议差异大，必须给用户自由度，否则遇到特殊会议纪要无法贴合。”</p>
    </div>
    <div class="clash-vs">VS</div>
    <div class="clash-side side-con">
      <div class="side-title">质询主张 · 彻底剥离</div>
      <div class="side-speaker">周宁（架构师）、陈澄（测试）</div>
      <p class="side-arg">“测试侧数据显示自定义模板导致 40% 的排版变形与乱码，且回归测试面完全无法收敛。”</p>
    </div>
  </div>

  <div class="accord-box">
    <div class="accord-title">✦ 破局妥协公约 (Accord)</div>
    <div class="accord-content">
      林夏同意剥离自定义模板上传能力；作为补偿，周宁承诺“架构上优先进行会议场景智能匹配，未命中则自动降级为通用兜底模板”。
    </div>
  </div>

  <!-- ⚖️ 得失天平 -->
  <div class="tradeoff-container">
    <div class="tradeoff-bar">
      <div class="tradeoff-gain">
        <span class="to-label">▲ 换取价值 (Gain)</span>
        <span class="to-desc">纪要格式稳定性提升 40%，测试回归范围大幅收敛</span>
      </div>
      <div class="tradeoff-pivot">⚖️</div>
      <div class="tradeoff-sacrifice">
        <span class="to-label">▼ 隐性代价 (Sacrifice)</span>
        <span class="to-desc">牺牲了个性化灵活度，种子用户需建立适应预期</span>
      </div>
    </div>
  </div>

  <div class="rollback-warning">
    <span class="rb-icon">⚠</span>
    <strong>翻盘回滚红线：</strong>若 8 月 20 日前场景自动匹配准确率低于 80%，重新评估开放自定义入口。
  </div>
</div>
```

### 4.3 模块二核心 HTML & SVG 甘特瀑布结构示例

```html
<!-- 时空甘特瀑布流 -->
<div class="gantt-waterfall-card">
  <div class="gantt-header">
    <div class="gantt-title">时空交付甘特流 (Temporal Waterfall)</div>
    <div class="critical-indicator">🔴 关键路径：A1/A2 ➔ A4 ➔ A5 · 缓冲时间: 0 天</div>
  </div>

  <div class="gantt-body">
    <!-- SVG 绘制连线层（前置依赖折线由纯前端 JS 计算坐标后绘制） -->
    <svg id="gantt-links" class="gantt-svg-layer"></svg>

    <!-- 甘特时间坐标刻度 -->
    <div class="gantt-timeline-axis">
      <div class="time-col">8/19 12:00</div>
      <div class="time-col">8/19 18:00</div>
      <div class="time-col">8/20 12:00</div>
      <div class="time-col">8/20 24:00</div>
      <div class="time-col deadline-col">🏁 8/20 准入门禁</div>
    </div>

    <!-- 任务条渲染轨 -->
    <div class="gantt-tracks">
      <div class="gantt-track-row" data-action="A1" data-case="D1">
        <div class="owner-cell">林夏</div>
        <div class="bar-container">
          <div class="task-bar is-critical" style="left: 0%; width: 25%;">
            <span class="task-name">A1. 批注情绪化语气平抑</span>
            <span class="time-tag">8/19 18:00</span>
          </div>
        </div>
      </div>

      <div class="gantt-track-row" data-action="A2" data-case="D2">
        <div class="owner-cell">赵衡</div>
        <div class="bar-container">
          <div class="task-bar is-critical" style="left: 0%; width: 25%;">
            <span class="task-name">A2. 来源文案重塑为“参考历史会议”</span>
            <span class="time-tag">8/19 18:00</span>
          </div>
        </div>
      </div>

      <div class="gantt-track-row" data-action="A4" data-case="D1">
        <div class="owner-cell">钱屿</div>
        <div class="bar-container">
          <div class="task-bar is-critical" style="left: 25%; width: 25%;">
            <span class="task-name">A4. 下划线悬浮提示 + 移除旧入口</span>
            <span class="time-tag">8/20 12:00</span>
          </div>
        </div>
      </div>

      <div class="gantt-track-row" data-action="A5" data-case="general">
        <div class="owner-cell">陈澄</div>
        <div class="bar-container">
          <div class="task-bar is-critical" style="left: 50%; width: 50%;">
            <span class="task-name">A5. 纪要/记忆/图谱三类全量回归报告 ★</span>
            <span class="time-tag">8/20 24:00</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

### 4.4 跨模块“因果-排期”双向联动机制（纯 JS 实现，0 Token）

在页面内嵌轻量 JavaScript，实现令人惊艳的穿梭交互：
```javascript
// 1. 点击上方的决策案，高亮下方甘特图中承接该决策的具体工项
document.querySelectorAll('.decision-case-card').forEach(card => {
  card.addEventListener('click', () => {
    const caseId = card.id.replace('case-', '');
    document.querySelectorAll('.task-bar').forEach(bar => bar.classList.remove('is-targeted'));
    document.querySelectorAll(`[data-case*="${caseId}"] .task-bar`).forEach(bar => {
      bar.classList.add('is-targeted');
      bar.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
});

// 2. 鼠标悬停甘特图某任务，高亮其全部前置依赖任务，并显示阻塞阻断线
document.querySelectorAll('.gantt-track-row').forEach(row => {
  row.addEventListener('mouseenter', () => {
    const actionId = row.getAttribute('data-action');
    highlightUpstreamDependencies(actionId);
  });
  row.addEventListener('mouseleave', () => {
    resetHighlight();
  });
});
```

---

## 五、 分步实施路线图（三步走规划）

为确保项目稳定交付与代码质量，建议分阶段实施：

### 阶段一（P0：数据契约与精准抽取内核）
- **交付目标**：
  1. 在 `domain/meeting/tasks/` 下新建 `decision_gantt/` 任务目录；
  2. 实现契约模型 `contracts.py`（Pydantic Schema）；
  3. 编写紧凑型 `prompts.py` 与 Agent 节点，完成单次高保真抽取；
  4. 编写拓扑引擎：计算拓扑图、关键路径与零缓冲预警；
  5. 编写单元测试，验证 JSON 抽取准确率与 DAG 算法无环稳定性。

### 阶段二（P1：Markdown 报告与 LaTeX 静态排版生成）
- **交付目标**：
  1. 实现 `decision_gantt.md` 的导出序列化；
  2. 实现 LaTeX Paper 风格的 HTML 模板构建器 `build_decision_gantt_html`；
  3. 实现辩论天平卡片（Trade-off Box）与回滚红线徽章渲染；
  4. 实现学术流式甘特图布局结构与状态样式。

### 阶段三（P2：动态连线渲染、穿梭联动与 API 路由挂载）
- **交付目标**：
  1. 嵌入 SVG 贝塞尔曲线算法，动态绘制甘特图前置依赖箭头连线；
  2. 落地上篇（决策）与下篇（排期）的双向点击穿梭脉冲动画；
  3. 在 FastAPI 路由注册 `POST /api/v1/meeting/decision_gantt`；
  4. 在根目录下编写与 `minutes.py` 相同规范的测试调用脚本 `decision_gantt.py`。

---

> 💡 **总结**：本指南定义了一套完全脱离市面平庸总结的**新物种级任务线**。无论是面对企业高管做战略汇报，还是面对技术研发做工程交付把控，该方案都具备极强的说服力与震撼度。
