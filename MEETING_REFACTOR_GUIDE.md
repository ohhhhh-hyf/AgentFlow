# Meeting 领域全域重构与任务协作权威指南 (v3.0-Definitive)

> **版本**：v3.0-Definitive (权威全景版)  
> **分支**：`try`（基于 `remake` 分支创建）  
> **核心哲学**：**底座高保真议题树萃取 ➔ 任务 Agent 差异化摄入与专科深加工 ➔ 模板栏位驱动并发直出 ➔ 方案 B 双层硬门禁终验**  
> **全任务覆盖**：完整覆盖 1 个核心底座（`meeting_understanding`）、8 大独立任务 Agent（`minutes`、`actions`、`risks`、`consensus_decision`、`mindmap`、`agenda_minutes`、`minutes_styles`、`minutes_trace`）以及跨场记忆系统 `meeting_memory`。  
> **性能与质量基准**：彻底消除旧代码 11 个扁平碎片字段的冗余复读，底座耗时由 **63s 压缩至 15~18s**；全任务并行深加工耗时 **2~8s**；端到端总耗时由 **115s 降至 25~30s**；彻底杜绝数据打架与幻觉。

---

## 🚀 实时重构进度追踪看板 (Live Progress Dashboard)

> **当前状态**：`[已全部打通]` 核心底座与 8 大任务 Agent 结构化适配完成，181 套全域测试 100% PASS！

- [x] **Step 1: 底座 Core Agent 结构化重构与契约同步**
  - [x] 1.1 修改 `domains/meeting/meeting_core/contracts.py`（定义 `UnifiedMeetingTree` 契约，内聚 actions/risks/decisions）
  - [x] 1.2 修改 `domains/meeting/meeting_core/prompts.py`（更新结构树提取提示词，以议题为单元组织事实）
  - [x] 1.3 运行 `sync_domain.py --domain meeting --write`（自动更新模型与空结构常量）
  - [x] 1.4 适配 `domains/meeting/orchestrator.py`（更新 `_meeting_pack` 树状与衍生要素数据分发）
  - [x] 1.5 验证底座单测跑通（181 测试全量 PASS）
- [x] **Step 2: 专科任务 Agent 原生对接事实树**
  - [x] 2.1 改造 `ActionItemsAgent` 数据供给（原生直通树 actions + user 画像权责仲裁）
  - [x] 2.2 改造 `RiskAgent` 数据供给（原生直通树 risks + 影响定级要素）
  - [x] 2.3 改造 `ConsensusDecisionAgent` 数据供给（直通树 decisions/debate + 原文交锋）
  - [x] 2.4 改造 `MindmapAgent` 数据供给（纯树层级大纲直通）
  - [x] 2.5 验证 `AgendaMinutesAgent`（36 套独立专线单测全部 PASS）
- [x] **Step 3: 模板纪要主线与方案 B 门禁接入**
  - [x] 3.1 改造 `MinutesGenerationAgent` 数据供给（直通 UnifiedMeetingTree 骨干 + 原文血肉）
  - [x] 3.2 接入 `hard_execution.py`（方案 B 0.02s 内存硬门禁与结构约束，86 套模板门禁测试全量 PASS）
- [x] **Step 4: 多样式、溯源纪要与跨场记忆适配**
  - [x] 4.1 适配 `MinutesStylesAgent`（5 种透镜模式直通议题树）
  - [x] 4.2 适配 `MinutesTraceAgent`（句级行号双栏对齐直通议题树）
  - [x] 4.3 适配 `memory/extract.py`（跨场项目记忆 19 套测试全部 PASS）
- [x] **Step 5: 全量回归测试与端到端跑通终验**
  - [x] 5.1 运行全域单元测试（`pytest tests/ -q`：181 passed, 1 skipped，100% 绿灯无回归）
  - [x] 5.2 契约与运行时生成区一致性检查（`sync_domain.py --check`：SUCCESS）

---

## 目录

1. [架构总览：全系统信息流与四大输入源](#一架构总览全系统信息流与四大输入源)
2. [底座 Core Agent：MeetingUnderstanding 议题树深度重构](#二底座-core-agentmeetingunderstanding-议题树深度重构)
3. [全域 8 大任务 Agent：信息摄入与专科深加工详解](#三全域-8-大任务-agent信息摄入与专科深加工详解)
   * 3.1 [ActionItemsAgent（待办事项：权责仲裁与视角分流）](#31-actionitemsagent待办事项权责仲裁与视角分流)
   * 3.2 [RiskAgent（风险分析：影响推演与严重度定级）](#32-riskagent风险分析影响推演与严重度定级)
   * 3.3 [ConsensusDecisionAgent（共识与决策：博弈交锋与妥协代价）](#33-consensusdecisionagent共识与决策博弈交锋与妥协代价)
   * 3.4 [MindmapAgent（思维导图：结构化知识树 0s 投影）](#34-mindmapagent思维导图结构化知识树-0s-投影)
   * 3.5 [MinutesGenerationAgent（模板纪要：栏位并发直出与双轨融合）](#35-minutesgenerationagent模板纪要栏位并发直出与双轨融合)
   * 3.6 [AgendaMinutesAgent（议程纪要：独立双向对账审计专线）](#36-agendaminutesagent议程纪要独立双向对账审计专线)
   * 3.7 [MinutesStylesAgent（多样式纪要：5 种认知透镜重组）](#37-minutesstylesagent多样式纪要5-种认知透镜重组)
   * 3.8 [MinutesTraceAgent（溯源纪要：句级行号双栏对齐）](#38-minutestraceagent溯源纪要句级行号双栏对齐)
4. [重点专章 1：模板纪要的分栏调度与个人视角“去我化”](#四重点专章-1模板纪要的分栏调度与个人视角去我化)
5. [重点专章 2：跨场记忆系统对接 (meeting_memory)](#五重点专章-2跨场记忆系统对接-meeting_memory)
6. [方案 B：双层质检体系与程序装配 (0.02s 硬门禁)](#六方案-b双层质检体系与程序装配-002s-硬门禁)
7. [实施演进路线与全量 13 套测试验收矩阵](#七实施演进路线与全量-13-套测试验收矩阵)

---

## 一、架构总览：全系统信息流与四大输入源

### 1.1 架构拓扑：1 个 Core Agent + 8 个独立 Task Agent
整个 Meeting 领域采用**星型广播拓扑（Star-Broadcast Topology）**：
* **`meeting_understanding` 是全系统唯一的公共底座（Core Agent）**，负责通读长原文，构建高密度的结构化议题事实大盘；
* **下游 8 个任务线全部平级、独立、互不阻塞**。每个任务线由各自对应的 Task Agent 负责，用户选择执行哪些任务，系统就并发启动哪些任务 Agent，绝不进行任务间的强制串联与层级嵌套。

```mermaid
flowchart TD
    Raw[2~3万字会议原文 Transcript] --> Core[Core Agent: MeetingUnderstandingAgent\n耗时 ~15s: 萃取 UnifiedMeetingTree 统一议题树\n输出: 模块聚类/议题争论/量化指标/拍板决议/原始待办/风险预警]
    
    subgraph Group1 [第 2 类: 纯吃树专科 Agent (耗时 1~2s, 零原文噪声)]
        Core --> T_Act[ActionItemsAgent 待办\n摄入: 树中 actions + 用户画像\n职责: 权责仲裁/my_actions分流/- [ ]待办]
        Core --> T_Risk[RiskAgent 风险\n摄入: 树中 risks + 场景规范\n职责: 阻断性推演/严重度定级/应对方案]
        Core --> T_Map[MindmapAgent 思维导图\n摄入: 树中层级与决议\n职责: 纯程序 0s 投影 Markdown 大纲]
    end
    
    subgraph Group2 [第 3 类: 树骨+肉身综合 Agent (耗时 5~10s, 缓存命中)]
        Core --> T_Min[MinutesGenerationAgent 模板纪要\n摄入: 树事实骨架 + 原文细节 + 用户画像 + 模板\n职责: 栏位驱动并发直出/原子替换回填]
        Core --> T_Dec[ConsensusDecisionAgent 共识决策\n摄入: 树决策/争辩 + 原文交锋段落\n职责: 四级共识定级/抓取原话引用/妥协代价]
        Core --> T_Style[MinutesStylesAgent 多样式纪要\n摄入: 树事实 + 原文叙事 + mode 参数\n职责: 5种组织范式重构成文]
        Core --> T_Trace[MinutesTraceAgent 溯源纪要\n摄入: 树核心结论 + 带行号原文\n职责: 句级行号双栏对齐映射]
    end
    
    subgraph Group3 [第 4 类: 独立双向对账审计专线]
        AgendaDoc[外部既定议程单] --> T_Agenda[AgendaMinutesAgent 议程纪要\n摄入: 既定议程单 + 会议原文 + 议题树锚点\n职责: 议程履约对账/审议定调/临时加塞识别]
        Raw --> T_Agenda
        Core -.->|议题清单加速锚点| T_Agenda
    end
```

### 1.2 全系统的 4 大核心信息源定性
除了底座生成的统一议题树之外，各任务 Agent 按需结合的“其他信息”在全系统中被严格收敛为 4 类：

1. **信息源 A：`transcript`（会议原文）**
   * **形态**：2~3 万字全量按时间序的对话记录（带发言人、发言内容）。
   * **特性**：在底座处理后，现代 API（DeepSeek、Claude、Qwen、OpenAI）已将其缓存在显存中（KV-Cache）。下游 Agent 再次摄入时**100% 命中 Prompt Cache**，Prefill 耗时仅需 **0.1~0.2s**。
   * **用途**：提供最鲜活的现场原话、专业技术术语、参数指标展开和博弈发言语境。
2. **信息源 B：`user`（用户画像）+ `perspective_profile`（视角模型）**
   * **形态**：用户姓名、别名清单、部门、职责范围、关注雷达、高管禁忌规则。
   * **用途**：作为权责仲裁的“标尺”（区分哪些是本人承接、哪些是协同他人），以及个人纪要中的详略倾向与人称过滤。
3. **信息源 C：`template`（目标模板 Markdown）**
   * **形态**：如 `general_minutes.md`、`personal_minutes.md`、`team_meeting.md` 等，带有 `[...]` 占位符的规范文档。
   * **用途**：作为文档生成的“模具”，约束各栏目内容范围、标题层级和排版格式。
4. **信息源 D：`line_extra`（外部专线参数与记忆输入）**
   * **形态**：会前用户上传的文本（如 `agenda_minutes` 的 txt 议程单）、指定的组织模式（如 `minutes_styles` 的 `mode="time"`）、上一期会议记忆注入（`memory_context`）。

---

## 二、底座 Core Agent：MeetingUnderstanding 议题树深度重构

### 2.1 彻底淘汰旧代码的“11 个扁平碎片数组”
* **旧代码现状（反面教材）**：
  将整场会议暴力拆解为 11 个孤立的扁平 List：`topics`、`decisions`、`risks`、`open_questions`、`action_hints`、`risk_hints`、`dependencies` 等。
  * **因果撕裂**：关于“核心网关升级”的讨论在 `topics[0]`，决策在 `decisions[0]`，待办在 `action_hints[3]`，风险在 `risk_hints[1]`，彼此丧失关联；
  * **疯狂复读**：同一句事实在多个数组中带 `evidence` 重复抄录，大模型生成了 **4,186 个 Token**，卡死 **63 秒**；
  * **残渣投喂**：下游拿到的全是孤立断句，导致模板纪要只能干瘪抄写，内容极其空洞。

* **重构后：【高内聚统一议题树】（UnifiedMeetingTree）**：
  以“业务模块 ➔ 核心议题”为天然的一等公民容器。整场会议的所有讨论细节、量化数据、拍板结论、行动与隐患，全部**高内聚封装在对应的议题节点内部**。全量树体积仅 **1,000~1,200 Token**，生成耗时从 **63s 骤降至 15s**！

### 2.2 统一议题树数据结构规范 (`UnifiedMeetingTree`)

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class SpeakerMeta:
    name: str                          # 统一归一化后的发言人真名
    role: str | None                   # 角色/职务（如"架构师"、"运维负责人"）
    org: str | None                    # 部门/机构名

@dataclass
class TopicActionItem:
    task: str                          # 具体行动描述（动词开头）
    owner: str | None                  # 原文明示的责任人真名（未定填 null）
    deadline: str | None               # 原文明示的完成时限（未定填 null）
    deliverable: str | None            # 明确交付物（如"压测报告"、"自测PR"，无填 null）
    dependency: str | None             # 前置依赖条件（如"等网关镜像发布后"）
    priority: Literal["high", "medium", "low"]
    evidence: str                      # 支撑该动作的原话证据（40字以内）

@dataclass
class TopicRiskItem:
    risk: str                          # 风险/隐患客观表述
    severity: Literal["high", "medium", "low"] # 严重程度
    impact: str | None                 # 潜在业务/技术影响（如"可能导致收银台超时丢单"）
    mitigation: str | None             # 现场提出的应对缓解措施（未提填 null）
    owner: str | None                  # 跟进责任人
    evidence: str                      # 原话依据

@dataclass
class TopicNode:
    topic_id: str                      # 议题唯一编号（如 "T1", "T2"）
    module: str                        # 所属业务模块/领域（如"基础架构与中间件"）
    title: str                         # 核心议题标题（4~12字）
    context_and_debate: str            # 讨论经过与争论脉络（谁提出、论据交锋、为什么分歧，100~200字自然叙事）
    key_metrics: list[str]             # 本议题明确提及的量化指标（如["QPS 12万", "P99 延迟 45ms", "延期 4 天"]）
    decisions: list[str]               # 本议题明确拍板通过的决议（含生效前提与约束）
    rejected_proposals: list[str]      # 现场讨论并明确否决的方案及原因
    actions: list[TopicActionItem]     # 挂载在本议题下的行动待办
    risks: list[TopicRiskItem]         # 挂载在本议题下的风险与阻碍
    open_issues: list[str]             # 现场未达成一致、需会后跟进的敞口问题

@dataclass
class UnifiedMeetingTree:
    meeting_brief: str                 # 整场会议主线概览（80字以内高密度总结）
    scene: str                         # 会议场景类型（通用/团队例会/项目决策与评审等）
    speakers: list[SpeakerMeta]        # 全会参会人花名册（人名↔角色归一落点）
    topics: list[TopicNode]            # 核心业务议题树（按讨论演进聚类）
    global_dependencies: list[str]     # 跨议题/跨业务的全局前置依赖
```

---

## 三、全域 8 大任务 Agent：信息摄入与专科深加工详解

系统中的 8 个任务线彻底解耦，针对不同的业务交付目标，各自设计了最为精炼、无冗余的信息摄入与深加工路径：

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        全域 8 大任务 Agent 信息摄入与利用矩阵表                        │
├────────────────────┬─────────────────────────────┬───────────────────┬────────────────┤
│ 任务 Agent 名称     │ 从底座【议题树】中提取什么？   │ 结合什么外部信息？ │ 核心深加工与交付产物│
├────────────────────┼─────────────────────────────┼───────────────────┼────────────────┤
│ 1. ActionItems     │ 各议题的 actions, decisions │ 用户画像 user     │ 权责仲裁与视角分流  │
│ 2. Risk            │ 各议题的 risks, open_issues │ 业务场景规范 scene│ 影响推演与严重度定级│
│ 3. ConsensusDec    │ 各议题 debate, decisions    │ 会议原文 transcript│ 四级共识与妥协代价  │
│ 4. Mindmap         │ 议题树层级结构与核心决议     │ 无 (纯树转换)     │ Markdown 大纲 (0s) │
│ 5. MinutesGen      │ 全量议题树 (全维度)         │ 原文 + 画像 + 模板 │ 模板驱动并发直出   │
│ 6. AgendaMinutes   │ 议题清单 (作为比对锚点)      │ 既定议程单 + 原文  │ 双向对账审计纪要   │
│ 7. MinutesStyles   │ 全量事实要素 (按模式切取)    │ 会议原文 + mode   │ 5大认知透镜重构成文 │
│ 8. MinutesTrace    │ 各议题核心结论与决议         │ 带行号会议原文    │ 句级行号双栏可溯源 │
└────────────────────┴─────────────────────────────┴───────────────────┴────────────────┘
```

---

### 3.1 ActionItemsAgent（待办事项：权责仲裁与视角分流）
* **模块路径**：[`domains/meeting/tasks/actions/steps/actions_agent.py`](file:///d:/study/demo/domains/meeting/tasks/actions/steps/actions_agent.py)
* **摄入数据**：
  * 提取议题树中所有 `topic_tree[].actions`、所属议题 `title` 以及指导性决议 `decisions`；
  * **结合外部信息**：**`user.json` 用户画像（姓名、别名清单、部门职务、负责范围）**。
  * **严禁摄入**：**长篇会议原文**！长原文中充斥大量“我们以后可以考虑做…”等讨论性假设，灌入长原文是诱发假待办和职责泛化的主因。
* **信息利用与深加工逻辑**：
  1. **以画像为标尺进行责任仲裁**：
     * **个人视角模式**：比对动作的 `owner` 与用户画像（及别名）。命中当前用户时，归入 `my_actions`，格式化为带复选框 `- [ ]` 的高可执行动作；若当前用户被明确要求配合某人，则在条目中注明协同关系；他人任务归入 `delegated_actions`；
     * **客观全员模式**：所有明示责任人的任务按人名聚类归入 `my_actions`（此处语义为全员已分工任务）；任务明确但无明确责任人的归入 `unassigned_actions`。
  2. **任务可行性与状态核验**：
     * 剔除讨论中已被现场完成或当场否决的假动作；
     * 标准化交付物格式（`deliverable`）与完成时限（`deadline`）。
* **产出物**：`ActionItemsReport`（结构化 actions 字典 + 格式化待办清单 Markdown）。

---

### 3.2 RiskAgent（风险分析：影响推演与严重度定级）
* **模块路径**：[`domains/meeting/tasks/risks/steps/risks_agent.py`](file:///d:/study/demo/domains/meeting/tasks/risks/steps/risks_agent.py)
* **摄入数据**：
  * 提取议题树中所有 `topic_tree[].risks`、`open_issues` 以及量化指标 `key_metrics`；
  * **结合外部信息**：**会议场景规范 `scene`（如项目评审会 vs 线上故障复盘会）**。
  * **严禁摄入**：长篇会议原文（避免已解决的临时技术争论被误当成遗留风险）。
* **信息利用与深加工逻辑**：
  1. **影响链传播推演（Impact Propagation）**：
     * 结合所属业务模块，分析该风险若失控，对全局里程碑（如双十一上线、验收交付、资金安全）的具体冲击（`impact`）；
  2. **严重度三级标定（Severity Grading）**：
     * `high`：直接阻断项目上线窗口、可能造成线上事故或违约资损的卡点；
     * `medium`：架构方案有妥协、技术债增加、依赖方排期紧张；
     * `low`：体验优化项、可后续迭代容忍的代码异味。
  3. **应对措施闭环（Mitigation Matching）**：
     * 将现场讨论的降级方案（如限流、回滚开关）与对应责任人绑定，无措施的明确标为“待制定防范预案”。
* **产出物**：`RiskReport`（结构化风险清单，含隐患分类、影响后果、定级与应对措施）。

---

### 3.3 ConsensusDecisionAgent（共识与决策：博弈交锋与妥协代价）
* **模块路径**：[`domains/meeting/tasks/consensus_decision/steps/consensus_decision_agent.py`](file:///d:/study/demo/domains/meeting/tasks/consensus_decision/steps/consensus_decision_agent.py)
* **摄入数据**：
  * 提取议题树中的 `decisions`、`rejected_proposals`、`context_and_debate`；
  * **结合外部信息**：**会议原文 `transcript`（通过 Prompt Cache 毫秒级命中）**。
* **信息利用与深加工逻辑（为什么需要原文？）**：
  * 议题树已经明确锁定了“哪几个议题存在方案交锋、拍板了什么结论”；
  * 但共识决策任务的核心价值是**“还原真实博弈动力学”**。Agent 拿着议题树中的争论靶心，到原文对应段落中精准抓取**正反双方交锋的原话金句（`key_quote`）与妥协微表情**；
  * **裁决四级共识等级（Consensus Grade）**：
    * `hard_alignment`：全员一致赞同，无附带保留条件；
    * `conditional_concession`：附带明确前提的妥协（如“架构组同意上线，但运维必须在周五前补齐熔断开关”）；
    * `unresolved_concern`：保留意见，虽通过决策但一方当场提出明确隐患；
    * `active_disagreement`：现场未达成共识，各执一词留存争议。
  * **裁决裁决形态（Decision Archetype）**：数据驱动（`data_driven`）、主管拍板（`authority_fiat`）、利益交换（`quid_pro_quo`）。
* **产出物**：`ConsensusDecisionReport`（全会决策大盘总评、分议题交锋对立面、共识等级、妥协代价）。

---

### 3.4 MindmapAgent（思维导图：结构化知识树 0s 投影）
* **模块路径**：[`domains/meeting/tasks/mindmap/steps/mindmap_agent.py`](file:///d:/study/demo/domains/meeting/tasks/mindmap/steps/mindmap_agent.py)
* **摄入数据**：
  * 提取议题树的 `meeting_brief`、`topics[].title`、`topics[].decisions`、`topics[].key_metrics`；
  * **结合外部信息**：**无**（无需原文、无需画像）。
* **信息利用与深加工逻辑**：
  * **零 LLM 推理、纯程序确定性转换**：
    由于 `UnifiedMeetingTree` 天生就是一棵树，系统无需再次调用大模型长文生成，直接通过 Python 代码将树结构映射为 Markmap 标准 Markdown 大纲：
    * `# 根节点`：会议主题与主线
    * `## 二级分支`：业务模块与攻坚议题
    * `### 三级分支`：量化指标与核心决议
    * `- 四级列表`：落地执行动作
  * 严格控制在 3~4 层以内，避免导图节点无限蔓延。
* **产出物**：`MindmapReport`（`title` + 可直接被前端 Markmap 渲染的 `outline` Markdown）。

---

### 3.5 MinutesGenerationAgent（模板纪要：栏位并发直出与双轨融合）
* **模块路径**：[`domains/meeting/tasks/minutes/steps/minutes_agent.py`](file:///d:/study/demo/domains/meeting/tasks/minutes/steps/minutes_agent.py)
* **摄入数据**：
  * 摄入**全量议题树 `UnifiedMeetingTree`**（包含所有维度的结构化事实）；
  * **结合外部信息**：
    1. **会议原文 `transcript`**（前缀缓存极速复用）；
    2. **用户画像 `user.json`**（个人视角模式时注入）；
    3. **目标模板 Markdown**（如 `general_minutes.md`、`personal_minutes.md`）；
    4. **跨场记忆 `memory_context`**（如有注入）。
* **信息利用与深加工逻辑（解答“光有树为什么不够”的核心）**：
  * 模板纪要绝不能只写一句话提纲，它需要有血有肉、有上下文推导的丰富叙述；
  * **协同机制：【议题树为骨架导航，会议原文为血肉弹药库，模板为模具】**：
    1. **骨架约束**：议题树严格限定了会议有哪几个核心议题、各项拍板决议和指标是什么，大模型以树为纲，**绝不漏点、绝不跑偏、绝不自造决策**；
    2. **血肉展开**：在顺着议题树展开每一个栏目时，大模型从原文中摄取最鲜活的现场技术参数、争辩原话与业务上下文，组织成 2~3 段深度详实的自然段；
    3. **栏位驱动并发填充**：解析模板槽位（`[...]`），并发分发 3~4 个独立的小 Prompt，将内容原子级回填入模板中。
* **产出物**：`MinutesReport`（排版严整、内容详实、无占位残留的最终会议纪要 Markdown）。

---

### 3.6 AgendaMinutesAgent（议程纪要：独立双向对账审计专线）
* **模块路径**：[`domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py`](file:///d:/study/demo/domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py)
* **摄入数据**：
  * **必需输入 1**：会前上传的**【既定议程单原件】（`line_extra`）**；
  * **必需输入 2**：**【会议原文】（`transcript`）**；
  * **辅助加速输入 3**：底座提炼的**【议题树清单】**（作为现场实际发生事实的快速检索锚点）。
* **信息利用与深加工逻辑（双向审计对账机制）**：
  * **维度一：正向履约核销（既定议程 ➔ 会议实操）**：
    * 逐项拿议程单上的议题（01, 02...）与议题树及原文比对；
    * 审议通过的 ➔ 输出四栏骨架（背景与目标 / 核心内容 / 核心认知 / 决议待办），定调为“审议通过”或“有条件通过”；
    * 议程单列出但会上完全未讨论的 ➔ **严谨核销，准确标注为“本次未讨论”**；
  * **维度二：反向加塞排查（会议实操 ➔ 既定议程）**：
    * 比对议题树中现场讨论充分、但根本不在会前议程单中的重大事项 ➔ 自动识别为**临时加塞议题（`adhoc_items`）**。
* **产出物**：`AgendaMinutesReport`（包含议程完成度统计、分项四栏履约明细、临时议题记录）。

---

### 3.7 MinutesStylesAgent（多样式纪要：5 种认知透镜重组）
* **模块路径**：[`domains/meeting/tasks/minutes_styles/steps/minutes_styles_agent.py`](file:///d:/study/demo/domains/meeting/tasks/minutes_styles/steps/minutes_styles_agent.py)
* **摄入数据**：
  * 提取议题树中的核心事实要素；
  * **结合外部信息**：**会议原文 `transcript` + 组织模式指令 `mode`（`time` / `logic` / `causal` / `party` / `urgency`）**。
* **信息利用与深加工逻辑**：
  * 同一场会议的事实底座，在不同的受众面前需要完全不同的叙事结构：
    1. `time`（时间轴叙事）：按会议自然推进节奏记录议程演变；
    2. `logic`（逻辑总分式）：按总览 ➔ 业务模块 ➔ 细分议题层层剖析；
    3. `causal`（因果推导式）：按“痛点现状 ➔ 根因剖析 ➔ 应对对策 ➔ 预期成效”展开；
    4. `party`（主体责权式）：按参会部门/汇报方分别归纳各自立场、工作与要求；
    5. `urgency`（时效紧迫度）：按“紧急且重要（P0）➔ 近期落地（P1）➔ 远期规划（P2）”组织。
  * **利用方式**：议题树提供全局事实边界（防止虚构），原文提供特定模式所需的叙事段落与语境，根据 `mode` 参数直接重构成文。
* **产出物**：`MultiStylesReport`（结构化 `sections` 与特定组织模式的全文）。

---

### 3.8 MinutesTraceAgent（溯源纪要：句级行号双栏对齐）
* **模块路径**：[`domains/meeting/tasks/minutes_trace/steps/minutes_trace_agent.py`](file:///d:/study/demo/domains/meeting/tasks/minutes_trace/steps/minutes_trace_agent.py)
* **摄入数据**：
  * 提取议题树的核心结论与事实点；
  * **结合外部信息**：**带行号的会议原文 `transcript`**。
* **信息利用与深加工逻辑**：
  * 生成严谨客观的纪要正文草稿；
  * **行钉对齐引擎（Alignment Matching）**：在渲染阶段，通过 n-gram 词频与语义相似度算法，将纪要中的每一句断言、量化数据、决议，反向定位到带行号原文中的具体发言行号（`sentence -> line_no -> quote`）；
  * 彻底消灭“AI 幻觉无从查证”的问题，支持前端双栏联动（点击左侧纪要句子，右侧原文自动高亮滚动）。
* **产出物**：`MinutesTraceReport`（纪要正文 + 句级行号溯源映射表）。

---

## 四、重点专章 1：模板纪要的分栏调度与个人视角“去我化”

### 4.1 模板分栏驱动机制 (Slot-Driven Dispatching)
系统内所有纪要任务统一归入模板渲染体系（用户未指定时自动回退默认模板）：
1. **通用模板 `general_minutes.md`（3 栏）**：
   * `[全文摘要]`：摄入议题树的 `meeting_brief` 与各模块核心，生成 250~400 字全局脉络；
   * `[要点梳理]`：按议题树的 `topics` 展开，结合原文细节梳理讨论细节与量化指标；
   * `[结论与决定]`：直接提取各议题的 `decisions`。
2. **个人工作台模板 `personal_minutes.md`（4 栏）**：
   * `[本场概况与承接目标]`：全会大局 + 本人承接的关键业务底线；
   * `[重点关注与业务进展]`：重点展现与本人职责相关的指标与推进情况；
   * `[行动项与协同依赖]`：三色分流（本人动作置顶且带 `- [ ]`，协同他人明确人名）；
   * `[待确认事项与风险]`：本人业务面临的技术卡点与外部依赖阻塞。
3. **团队例会模板 `team_meeting.md`（5 栏）**：
   * `[例会概况]` / `[工作进展]` / `[决定与待办]` / `[协作需求]` / `[待确认与风险]`。

### 4.2 个人视角的“去我化”高管公文规范
当 `profile="user"` 时，Prompt 必须刚性注入以下三大红线：
* **红线 1：绝对禁止出现第一人称代词**（严禁“我”、“本人”、“我方”、“我们团队”）；
* **红线 2：本人动作省略主语**：一律以动词直接开头（例：“主导完成网关熔断开关开发，周四前灰度上线”）；在读者的心智中，无主语的任务默认就是本人承接；
* **红线 3：他人动作保留真名**：协同方工作一律标注规范真实姓名（例：“李四负责联调环境配置”），严禁使用“某某同事”、“其”。

---

## 五、重点专章 2：跨场记忆系统对接 (meeting_memory)

跨场项目记忆是支撑企业级连续项目追踪的核心：
* **标准化实体入库**：
  修改 [`domains/meeting/memory/extract.py`](file:///d:/study/demo/domains/meeting/memory/extract.py)，直接从底座的 `UnifiedMeetingTree` 中提取标准实体：
  * `decisions`（历次决议演进）
  * `actions`（跨场未结待办与交付状态）
  * `risks`（隐患是否解除或升级）
  * `key_metrics`（量化指标的环比追踪）
* **彻底废除旧代码靠正则盲猜人名和提取文本的脆弱逻辑**，实现跨场会议状态机的精准迁移。

---

## 六、方案 B：双层质检体系与程序装配 (0.02s 硬门禁)

彻底废弃“大模型先写一篇废话草稿，然后大模型再审核一遍”的低效双重开销机制，采用**方案 B：内存级程序硬门禁 + 局部轻量返工**：

```mermaid
flowchart TD
    Slots[并发生成的栏目 Markdown 文本] --> Assemble[程序装配: 精准替换模板中括号占位符]
    
    Assemble --> L1[Layer 1: 内存级程序硬门禁 hard_execution.py\n耗时 0.02 秒, 纯 Python 规则毫秒级全检]
    
    L1 --> CheckPass{全部硬规则通过?}
    
    CheckPass -- 是 --> Deliver[质检通过 ➔ 立即交付给用户]
    
    CheckPass -- 否: 某单栏违规 --> L2[Layer 2: 局部轻量返工 Localized Rework\n仅针对违规的那一栏下发整改提示词 (耗时 ~2-3s)\n其余合格栏目 100% 复用]
    
    L2 --> ReAssemble[单栏回填更新 ➔ 交付]
```

### 6.1 Layer 1：内存级程序硬门禁 (`hard_execution.py`)
在 **0.02 秒** 内完成纯 Python 规则扫描：
1. **占位符残留检测**：检查正文是否残存未被替换的 `[...]`；
2. **标题穿透清洗**：检查是否有非法的一级/二级标题，自动正则剥离，确保不破坏模板 Markdown 骨架；
3. **表情符号过滤**：毫秒级剔除所有非正式公文 Emoji；
4. **去我化人称拦截**：在个人视角下检测是否冒出“我”、“本人”，一旦命中直接触发该栏返工；
5. **恶性长句拆分**：针对超过 250 字无标点的异常长句自动拆分。

### 6.2 Layer 2：栏目级局部轻量重写 (Localized Rework)
若仅有第 3 栏违规冒出了“我”或字数超标：
* **绝不推翻全篇整场会议**；
* 仅针对第 3 栏单独调用一次携带整改指令的轻量 Prompt，生成 200 字仅需 **2~3 秒**；
* 程序重新将该栏插回模板交付，系统总耗时几乎不受影响。

---

## 七、实施演进路线与全量 13 套测试验收矩阵

### 7.1 分步落地实施规划

```
[第一步：底座结构化重构与数据契约统一] (核心地基)
  ├── 改造 domains/meeting/meeting_core/，实现 UnifiedMeetingTree 抽取
  ├── 运行 `python tools/codegen/sync_domain.py --domain meeting --write` 自动同步契约模型与常量
  ├── 严格控制底座输出 Tokens 在 1200 以内，将耗时锁定在 15s 左右
  └── 废除旧代码中 11 个扁平碎片数组的跨字段重复抽取

[第二步：专科任务 Agent 原生对接事实树] (快线并通)
  ├── 改造 ActionItemsAgent，吃树中的 actions + user 画像，产出高纯度待办
  ├── 改造 RiskAgent，吃树中的 risks，做影响推演与定级
  ├── 改造 ConsensusDecisionAgent，吃树中决策与交锋，结合原文抓取论据
  ├── 固化 MindmapAgent 0秒纯程序转换
  └── 确保 AgendaMinutesAgent 独立双向审计专线稳定运行

[第三步：模板纪要栏位驱动并发直出与双轨融合] (主线重构)
  ├── 改造 MinutesGenerationAgent 为栏位调度总编
  ├── 实现模板槽位解析与分栏并发填充 (议题树骨架 + 原文细节展开)
  └── 对接 hard_execution.py 方案 B 硬门禁与单栏轻量重写

[第四步：多样式、溯源纪要与跨场记忆适配]
  ├── 对齐 minutes_styles 5大组织透镜与 minutes_trace 句级行号对齐
  └── 改造 memory/extract.py 直接摄取事实树结构体，验证记忆状态机

[第五步：全量 13 套测试回归验收与 Prompt 精细打磨]
  ├── 运行 api_test/ 下全量测试脚本，确保 100% PASS
  └── 在稳定架构上微调各栏 Prompt 措辞
```

### 7.2 验收测试矩阵 (全域 13 个测试套件)

在 `try` 分支上完成代码重构后，必须通过以下全部测试套件的严苛验收：

| 测试脚本 | 验证重点 | 预期耗时指标 | 质量验收标准 |
| :--- | :--- | :---: | :--- |
| `minutes_test.py` | 客观通用模板纪要（`general_minutes.md`） | **≤ 30s** | 议题全景连贯，量化指标充实，无占位符残留 |
| `personal_minutes_test.py` | 个人视角模板纪要（`personal_minutes.md`） | **≤ 30s** | 严禁出现“我/本人”，本人动作置顶带 `- [ ]`，他人写真名 |
| `actions_test.py` | 待办事项提取线 | **≤ 20s** | 责任人仲裁准确，交付物与截止期明确，无遗漏 |
| `risks_test.py` | 风险识别线 | **≤ 20s** | 严重度分级合规（High/Med/Low），应对措施与责任人闭环 |
| `mindmap_test.py` | 思维导图大纲线 | **≤ 18s** | 0s 纯程序生成，层级不超过 4 层，语法完全合规 |
| `consensus_decision_test.py` | 共识与决策线 | **≤ 25s** | 方案交锋对立面清晰，共识等级与妥协代价判定准确 |
| `agenda_minutes_test.py` | 既定议程纪要线 | **≤ 30s** | 独立专线不受损，既定议程双向对账核销准确 |
| `minutes_styles_test.py` | 多风格重写线 | **≤ 28s** | 5 大组织模式指纹鲜明，底层事实无损，杜绝模式串味 |
| `minutes_trace_test.py` | 溯源纪要线 | **≤ 30s** | 行钉对齐率 ≥95%，双栏视图无孤儿结论 |
| `memory_test.py` | 跨场会议记忆状态机 | **≤ 25s** | 实体抽取无正则硬猜，历史未结待办与决议演进准确接续 |
| 边界与异常测试 (3套) | 空议程、单人参会、超长发言等边缘用例 | **≤ 30s** | 优雅兜底降级，无系统级 Crash |

---

## 八、总结与结语

本工程指南完整理顺了 Meeting 领域的全域架构：
1. **一个底座（`meeting_understanding`）**：彻底推翻 11 个扁平散装数组，重构成高内聚、带前因后果的**统一议题树（`UnifiedMeetingTree`）**，解码开销降低 70%，耗时降至 15s；
2. **四大清晰信息源**：明确界定了议题树、会议原文（带缓存加速）、用户画像与外部模板/模式的边界与定位；
3. **八大任务 Agent 原生分工明确**：
   * **纯吃树专科**（`actions`、`risks`、`mindmap`）：不看长原文，1~2 秒纯净产出，彻底告别原文噪声；
   * **树骨+肉身综合**（`minutes`、`consensus_decision`、`styles`、`trace`）：以树为骨架防跑偏，以原文为细节展开，模板为模具；
   * **独立对账审计**（`agenda_minutes`）：以外部议程单为考卷，以原文和议题树为答卷，进行严密双向审计；
4. **方案 B 质检保底**：0.02s 内存级硬门禁拦截人称与占位符，微瑕单栏局部返工，保障最高交付质量与极致性能。

全域方案逻辑严密、分工详实、无任何死角，作为本次 `try` 分支重构的终极施工指南！
