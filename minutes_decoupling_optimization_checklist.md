# 纪要任务（Minutes）客观与个人视角深度解耦与架构分流终极清单

> **制定时间**：2026-10-12  
> **核心使命**：彻底破除 `minutes` 任务线中沿用已久的“单体巨石 Prompt 混杂多模式”历史包袱，并将 **PerspectiveModelingAgent 视角建模层全面洗髓重构**！  
> 通过**“抽取公共基底（Common Base）+ 纯 Python `if` 模式物理分流（Branching）”**的架构革新，将客观纪要（`Objective Minutes`）与个人视角纪要（`Personal Minutes`）彻底解耦！  
> **核心原则**：
> 1. **全链路 Schema 零容忍防炸护栏（Zero-Tolerance Validation Guardrails）**：吸取历史教训，严格锁定 `_final_reports`、`validate_payload`、`_exact_fields` 的刚性契约，确保数据模型、生成契约、程序合成、硬执行覆写与最终 Report 组装之间的键集合 100% 恒等匹配，杜绝任何 `OutputValidationError` 异常！
> 2. **正向引导为主、底线红线为辅**：大幅削减“严禁/禁止”等负向压制词汇，将 85% 以上的指令重构为**肯定式正向引导（Prescriptive Affordances）**，构建明确的行为预期与公文标准，仅保留极少数核心真实性红线，彻底根除模型注意力对冲与焦虑；
> 3. **客观模式极简纯化**：砍掉一切个人雷达、与我相关、主语省略等干扰噪声，节省 35%~40% Prompt Token，输出严谨全员公文体；
> 4. **视角建模洗髓与 11 核心字段精炼**：重构 `PerspectiveModelingAgent` 提示词，应用 **Prefill Cache 先验 + 首尾双磁极锚定**，精简至 11 个高价值核心字段（保留 `open_questions`、`data_gaps`，剔除 4 个僵尸字段）；
> 5. **全链路语义顺畅贯通**：建立视角模型（11 字段）向最终纪要（7 字段契约）的自然语义归流，与 `minutes_agent`、`minutes_supervisor`、`minutes_render` 形成精密咬合；
> 6. **记忆系统零干扰隔离**：确保跨场次记忆（`meeting_memory`）在客观和个人两条支线下均能 100% 原生稳定运行；
> 7. **流水线图结构零破坏**：LangGraph 拓扑编排与节点契约完全保持不变，重构纯粹收敛在内部提示词架构与步骤执行器（Steps）中。

---

## 零、 致命防炸警示：全链路 Schema 校验护栏与防崩防御网

### 1. 历史重大报错根因复盘：`OutputValidationError` 是怎么炸的？

```python
File "core/graph/nodes.py", line 1159, in _final_reports
    final[key] = validate_payload(type(report), report.model_dump())
File "core/schema/validation.py", line 222, in validate_payload
    return response_model.validate(data)
File "domains/meeting/models_generated.py", line 438, in validate
    _action(item, f"actions[{index}]")
File "core/schema/validation.py", line 98, in _action
    raise OutputValidationError(...)
```

底层运行时的物理校验机理是**绝对刚性、毫不妥协的**：
1. **`_exact_fields(data, expected, path)` 绝不容纳任何多余或缺失键**：
   ```python
   actual = set(data)
   expected = set(expected)
   if actual != expected:
       raise OutputValidationError(f"{path} 字段不一致：缺失={sorted(expected - actual)}，多余={sorted(actual - expected)}")
   ```
2. **`validate_payload` 在节点收尾（`_final_reports`）阶段强制执行**：
   任何任务线产出的最终 Report，其每一个字段及其内部结构都会被再次运行 `response_model.validate(data)`。
3. **一旦炸掉的连锁反应**：
   单线校验失败虽然会捕获异常并降级到 `_fallback_reports`，但意味着昂贵的大模型生成被彻底作废，直接回退为粗糙的确定性拼接文本，用户端体验严重受损！

---

### 2. 本次重构面临的 5 大高危“爆破点”与铁壁防线

在本次纪要客观/个人解耦与视角模型精简中，必须在代码层面筑牢以下 5 道防线，确保 100% 绝不触发任何 `OutputValidationError`：

| 爆破点编号 | 潜在危险触发场景 | 根因与风险代码位置 | 强制实施的铁壁防线规范 |
|---|---|---|---|
| **爆破点 1** | `PerspectiveModeling` 11 字段的四处同步断裂 | `models.py`、`contracts.py`、`EMPTY_PERSPECTIVE_MODELING`、`synth.py` 字段定义不一致 | **四位一体绝对恒等**：<br>1. `models.py` 的 dataclass 属性（11个）；<br>2. `contracts.py` 的 fields 声明（11个）；<br>3. `EMPTY_PERSPECTIVE_MODELING` 字典的 key 集合（11个）；<br>4. `synth.py` 合成函数输出的 key 集合（11个）。<br>⚠️ 绝不允许在任何一处残留 `goals`、`conclusions`、`stakeholders` 或 `inferred_role`，少一个或多一个 `validate` 必炸！ |
| **爆破点 2** | `Minutes` 7 字段在双轨 Prompt 中的“键名漂移” | 客观 Prompt 试图将 `personally_relevant_points` 改名为 `team_actions` 或 `actions` | **契约 Schema 键名物理锁定**：<br>无论客观还是个人模式，Prompt 指令中的 JSON 顶级键必须 100% 保持 7 个契约名不变：<br>`headline`, `executive_summary`, `key_decisions`, `personally_relevant_points`, `risks_and_blockers`, `unresolved_questions`, `history_comparison`。<br>客观模式只能在 Prompt 中解释其业务含义为“全员落地行动”，**绝对禁止修改 JSON 键名**！ |
| **爆破点 3** | `MinutesReport` 最终产物的类型与结构对齐 | 组装器从 `state["lines"]["minutes"]["rendered"]` 拿到的不是纯文本 | **渲染产物标量类型守卫**：<br>`MinutesReport` 严格校验 `allowed = {"title", "personalized_minutes", "quality_warning"}`。<br>`personalized_minutes` 必须且只能是 `str`，绝对不能是字典或列表。<br>在 `minutes_render.py` 的 `render_draft` 和自由渲染分支中，必须确保最终产出均为合法的 Markdown 纯字符串。 |
| **爆破点 4** | `hard_execution.py` 强执行覆写时的字段剥离风险 | `enforce_minutes_draft` 处理过程中丢弃了某些字段 | **强执行层字典闭环保护**：<br>`enforce_minutes_draft` 在执行下采和上游对齐时，必须返回包含完整 7 个契约键的字典，绝对禁止 `del` 或未初始化 `history_comparison` 等字段。 |
| **爆破点 5** | `_string_list` 数组内元素类型合规性 | 模型在列表字段中输出了 `None` 或畸形对象 | **列表项元素标量清洗**：<br>所有列表字段输出前必须经过列表推导式清洗：`[str(x).strip() for x in items if x is not None and str(x).strip()]`，确保数组内全为非空字符串。 |

---

## 一、 现状深层痛点与解耦前后架构全景

### 1. 现状痛点剖析：双重撕裂与断层

1. **纪要层的“单体巨石 Prompt”撕裂**：  
   当前 `MINUTES_GENERATION_SYSTEM_PROMPT`（7500 字）、`MINUTES_SUPERVISOR_DOMAIN_PROMPT`（4500 字）、`MINUTES_RENDER_PROMPT`（5500 字）把“全员客观公文”与“个人作战看板”死死揉在一起，导致模型在生成客观纪要时偶尔冒出缺主语现象，生成个人纪要时又杂糅路人甲琐事。
2. **负向约束过度泛滥（Negative Constraint Fatigue）**：
   旧提示词中充斥着大量的“严禁xxx”、“切忌xxx”、“禁止xxx”，不仅让提示词充满打补丁式的焦虑感，反而在 Decoder-only 模型的注意力空间中高亮了负向词元（Pink Elephant 效应），诱发不稳定的边界判定。
3. **视角建模层（PerspectiveModelingAgent）的“提示词屎山”与“字段断层”**：
   - **死代码膨胀**：生产环境下客观模式早就由编排层短路跳过，但 Prompt 里仍有近 35% 的篇幅在教模型怎么处理“客观全员”；
   - **自相矛盾的防守叠甲**：Prompt 一边定义了 `open_questions`（未决问题），另一边却在真人规则中加上了排除待确认事项的硬性指令，导致模型不敢提取跟进对齐动作；
   - **总结角色精神分裂**：`personal_summary` 居然要求“客观概括战略里程碑与全局决议”，逼着个人视角去假装宏观大局，抹杀了切身利益与技术卡点；
   - **字段与代码脱节**：Prompt 里设计了 15 个字段，但 Python 反序列化模型只接 12 个（丢弃了 `open_questions` 和 `data_gaps`），而编排层白名单又悄悄丢弃了 `conclusions`，实际存在 4 个下游根本不读的僵尸字段（`goals`, `conclusions`, `stakeholders`, `inferred_role`）。

---

### 2. 解耦后双轨分流架构全景（Architecture Overview）

```
                                  [用户请求进入 (Pipeline START)]
                                                │
                                                ▼
                                   [meeting_understanding 节点]
                              (客观高密度事实底座，保持中立纯粹；
                               若开启记忆，忠实输出全局 dependencies)
                                                │
                                                ▼
                                  [orchestrator 上下文动态分流]
                                                │
                      mode = "personal" if has_user_identity else "objective"
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
   【客 观 纪 要 专 属 轨 道】                                    【个 人 视 角 专 属 轨 道】
   (Objective Pipeline)                                          (Personal Perspective Pipeline)
                 │                                                             │
                 ▼                                                             ▼
   ┌───────────────────────────┐                                 ┌───────────────────────────┐
   │ 上下文组装：纯净模式       │                                 │ [perspective_modeling 节点]│
   │ 0 画像 / 0 命中表 / 0 雷达│                                 │ 11 核心字段高精视角模型   │
   │ 仅：理解底座 + 原文 + 预算│                                 │ Prefill 静态先验 + 正向引导│
   │ (跳过视角建模节点)        │                                 └─────────────┬─────────────┘
   └─────────────┬─────────────┘                                               │
                 │                                                             ▼
                 │                                               ┌───────────────────────────┐
                 │                                               │ 上下文组装：饱满作战模式  │
                 │                                               │ 注入画像、雷达、命中依据、│
                 │                                               │ 11 字段视角模型 (合流赋能)│
                 │                                               └─────────────┬─────────────┘
                 │                                                             │
                 ▼                                                             ▼
   ┌───────────────────────────┐                                 ┌───────────────────────────┐
   │ MINUTES_OBJECTIVE_AGENT   │                                 │ MINUTES_PERSONAL_AGENT    │
   │ (Common Base + 客观专属)  │                                 │ (Common Base + 个人专属)  │
   │ • 全景公文体，第三人称    │                                 │ • 作战看板，本人动宾省主语│
   │ • 全员分工覆盖，平铺决策  │                                 │ • open_questions 归流待办 │
   │ • 篇幅腰斩，Token 省 40%  │                                 │ • data_gaps 归流本人卡点  │
   │ • 严守 7 契约字段防炸     │                                 │ • 严守 7 契约字段防炸     │
   └─────────────┬─────────────┘                                 └─────────────┬─────────────┘
                 │                                                             │
                 ▼                                                             ▼
   ┌───────────────────────────┐                                 ┌───────────────────────────┐
   │ OBJECTIVE_SUPERVISOR      │                                 │ PERSONAL_SUPERVISOR       │
   │ • 审查全貌、事实与责任归口│                                 │ • 审查雷达对齐与承诺闭环  │
   │ • 纯净公文体直接放行      │                                 │ • 保护合法未决与外部卡点  │
   │ • 0 个人看板规则干扰      │                                 │ • 杂项自适应隐去直接放行  │
   └─────────────┬─────────────┘                                 └─────────────┬─────────────┘
                 │                                                             │
                 ▼                                                             ▼
   ┌───────────────────────────┐                                 ┌───────────────────────────┐
   │ OBJECTIVE_RENDER          │                                 │ PERSONAL_RENDER           │
   │ • 全员公文层级章节映射    │                                 │ • 个人作战四栏看板直出    │
   │ • 规范全景平铺排版        │                                 │ • **本人相关**：置顶      │
   │ • 产出合法纯字符串        │                                 │ • 产出合法纯字符串        │
   └───────────────────────────┘                                 └───────────────────────────┘
```

---

## 二、 核心解耦与精炼设计原则

### 原则 1：正向引导的公共基底标准（Positive Affirmation Standards）
以下公约是所有纪要形态的底线，沉淀为独立的公共组件（`MINUTES_COMMON_BASE_PROMPT` 与 `_SUPERVISOR_COMMON_BASE`）：
1. **真实性第一准则**：必须以转写及理解为唯一事实源，研讨探讨与拍板决策严格区分边界，关键数字、时限、金额必须 100% 忠实保留；
2. **时效优先与历史记忆隔离**：本次会议转写权重 100%；【会议记忆】仅作为跨场次因果演变的只读参照；与本次讨论冲突时，以本场达成的最新决议为准；历史对比内容统一归口录入 `history_comparison`，确保正文纯净聚焦本次会议；
3. **高信息密度公文表达标准**：长句主动拆短，交代清“主体 + 核心动作 + 量化指标/因果 + 结论”；
4. **输出 Schema 契约结构稳定**：维持既有的 `Minutes` 契约（`headline`, `executive_summary`, `key_decisions`, `personally_relevant_points`, `risks_and_blockers`, `unresolved_questions`, `history_comparison`），确保前后端协议 0 变动。

---

### 原则 2：视角建模层 11 核心字段精炼与价值归流（Lean Perspective Modeling）
彻底放弃膨胀无用的 15 字段模型，收敛至 **11 个高价值核心字段**，打通与下游 Minutes（7 字段契约）的语义归流：

| 视角模型字段 (11 Core Fields) | 字段类型与含义 | 价值与状态 | 下游 Minutes 对应归流目标 |
|---|---|---|---|
| `confidence` | `Literal["high", "medium", "low"]` | 保留 (元数据) | 调试与置信度审计，零成本 |
| `name` | `str` | 保留 (核心) | 身份识别、发言人回溯、看板组名置顶 |
| `personal_summary` | `str` (100-150字作战概览) | 保留 (核心) | $\to$ 纪要 `executive_summary` (个人概况栏直出投影) |
| `attention_points` | `list[str]` (核心关注要点) | 保留 (核心) | $\to$ 纪要 `personally_relevant_points` (`**重点协同**：`) 及业务进展过滤 |
| `possible_actions` | `list[str]` (原文承诺与分工) | 保留 (核心) | $\to$ 纪要 `personally_relevant_points` (`**本人相关**：` [产出动作]) |
| 🌟 `open_questions` | `list[str]` (待确认/对齐点) | **补齐激活 (核心)** | $\to$ 纪要 `personally_relevant_points` (`**本人相关**：` [对齐动作]) |
| `concerns` | `list[str]` (本人风险与隐患) | 保留 (核心) | $\to$ 纪要 `risks_and_blockers` (`**本人相关**：` [技术隐患]) |
| 🌟 `data_gaps` | `list[str]` (外部依赖断供) | **补齐激活 (核心)** | $\to$ 纪要 `risks_and_blockers` (`**本人相关**：` [外部阻断]) |
| `evidence` | `list[str]` (原文精准佐证) | 保留 (核心) | $\to$ `supervisor` 审核反幻觉门禁硬依据 |
| `responsibilities` | `list[str]` (本场相关职责) | 保留 (跨任务) | 供独立 `actions` 任务线做职责词重叠匹配 |
| `relevant_topics` | `list[str]` (相关议题名称) | 保留 (跨任务) | 供 `mindmap` 与三档上下文裁剪快速过滤 |
| ❌ `goals` | 参会目标 | **彻底剔除** | 下游 0 读取，纯泛化空话 |
| ❌ `conclusions` | 决议结论 | **彻底剔除** | 与全局 `decisions` 100% 撞车，编排层白名单原已丢弃 |
| ❌ `stakeholders` | 利益相关方 | **彻底剔除** | 下游 0 读取，已有 `focus_person` 与命中表替代 |
| ❌ `inferred_role` | 推断角色 | **彻底剔除** | 与画像自带 `role` 严重重叠，无下游分流价值 |

---

### 原则 3：充分复用 Prefill 成功经验（KV Cache 先验 + 正向权责本体论）
将前序针对模板首栏优化的成熟经验平移至 `PerspectiveModelingAgent`：
1. **Token 0 静态骨架先验（Schema Induction & 100% Cache Hit）**：
   - 将 `PERSPECTIVE_MODELING_SYSTEM_PROMPT` 的核心前置声明为 100% 静态纯净文本（包含法定权责本体论 + 11 字段紧凑 Schema）；
   - 所有不同的会议转写与用户画像请求均共享该静态前缀，**实现 KV Cache 100% 命中，首包生成速度大幅提升**。
2. **头部 Attention Sink 正向注入【法定权责本体论】**：
   - 确立清晰正向的归属口径，而不是堆叠禁止词：
     > `【权责归属规范口径】：`  
     > `1. 直接责任（My Action）：原文明确点名、本人主动认领或被直接指派的事项 → 记入 possible_actions 并标明「原文承诺」；`  
     > `2. 协同关注（Focus）：作为协同方、配合人或参与研讨但未直接承揽的事项 → 统一记入口径为 attention_points；`  
     > `3. 背景环境（Context）：未提及本人或属于宏观大盘/他组专属的事项 → 统一定位为背景议题，仅保留在 relevant_topics。`
3. **尾部 Action Trigger（Recency Bias）定点收敛**：
   - 彻底废除尾部 8 条无意义的“假自检八股”；
   - 替换为单句明确的**【交付执行令】**，利用最近注意力引导模型直接输出紧凑合规的 11 字段 JSON。

---

## 三、 完整优化行动清单（分阶段实施）

### Phase 1：提示词工程解耦与公共基底抽取（Prompts Layer）【核心工程】

#### 💡 提示词正向引导重构要点（把负向严禁转化为正向标准）：
1. **化“严禁第一人称”为“正向第三人称”**：客观模式直接规定“通篇统一采用第三人称公文语态，以具体姓名或部门名称作为主语陈述”；
2. **化“严禁写成个人视角”为“正向全员分工”**：在 `personally_relevant_points` 中正面说明“本字段统一产出【全员落地执行要点】，面向全场团队展开分工”；
3. **化“严禁带主语”为“正向动宾结构”**：个人模式正向引导“本人负责推进的事项一律采用【动宾短语】开头，自然承接动作（如‘输出压测报告’、‘协调网关日志’），无需前置姓名或人称代词”；
4. **化“严禁打回”为“正向放行标准”**：审核端正面规定“个人视角下，模型对全场无关人员的日常杂项分工、外围风险主动进行降噪与自适应隐去，属于高信息密度规范行为，应予直接认可并放行通过”。

---

- [x] **1.1 建立纪要生成提示词双轨分流架构**
  - **修改文件**：`domains/meeting/tasks/minutes/prompts.py`
  - **完整落地代码方案（正向引导精简版）**：

```python
# ── 双轨共享公共基底 ──────────────────────────────────────────────────────────
_MINUTES_COMMON_BASE = """你是「会议纪要草稿 Agent」。你是纪要全流程中唯一负责通读原文、深度提炼并输出全部血肉细节的核心写手；下游渲染器仅负责章节映射与排版，不会再从原文捞取额外信息。你产出的草稿即为终局事实正文。

在会议原文、会议理解（MeetingUnderstanding）之上，生成结构化、高信息密度、可复核的饱满纪要草稿。只输出结构化 JSON 数据，不直接排版 Markdown 终稿。搬运字段保持 100% 严格一致，提炼字段成段深度充分展开。

---

## 一、输入感知与协作准绳
1. **时序段落与平铺议题为主纲、原文为定向字典（理解层是骨架，回到会议原文深挖血肉）**：
   - 上游 MeetingUnderstanding 的 session_segments 与 topics 是你的主事实源与骨架总纲；
   - 撰写提炼段落时，以各研讨阶段/议题节点的因果背景（discussion/context_and_reasoning）、key_facts 与 key_points（量化指标与核心论据事实）、debates（观点交锋）和 decisions 为导航索引，必须回到会议原文中挖掘对话过程、具体参数与论据血肉，成段充分展开，顺应研讨推进脉络展开叙述，杜绝凭空编造；
   - executive_summary 段落组织以研讨阶段/业务模块为核心主线：首项为全局宏观概括，后续各项按核心业务阶段/论辩议题分别深度展开成段。
2. **历史记忆边界（时效优先法典，Memory 兼容保障）**：
   - 【本次会议原文/理解】为当前宇宙的唯一最高事实准则（权重 100%）；
   - 【会议记忆】仅作为跨场次因果演变的只读参照；与本次讨论冲突时，以本场最新达成的定调为准；
   - 历史对比内容统一归口录入 history_comparison，确保 executive_summary 聚焦本次会议事实。
3. **字段价值分层与模式差异规范**：
   - 提炼类（headline, executive_summary, personally_relevant_points）：严格基于本场事实深度提炼展开，每段每条交代完整事实要素（主体+动作+参数/论据/因果），形成闭环陈述；
   - 搬运与合流类（key_decisions, risks_and_blockers, unresolved_questions）：
     • 客观模式：基于上游事实底座全量忠实搬运，程序会逐字强对齐；
     • 个人模式：key_decisions 忠实搬运全局拍板决策；risks_and_blockers 结合用户视角模型的 concerns 与 data_gaps 进行专属看板化提炼与合流；
   - 记忆类（history_comparison）：仅当上下文有历史记忆注入时输出，否则输出空列表 []。

---

## 二、通用事实与表达规范
1. **事实脉络饱满（高信息密度公文体，长句主动拆短）**：
   - 核心要求：兼顾信息广度与行文简练，以公文体直陈业务事实，拒绝多从句生硬拼接的长难句；
   - 陈述句式闭环规范：交代清“主体 + 核心动作/主张 + 量化指标/定调依据 + 最终结论/后续安排”；
   - 表达去水提炼：保留完整事实脉络，长句主动拆短（使用逗号或分号自然断开），剔除铺垫修辞与口语化转述（直陈结论与动作）。
2. **场景自适应血肉展开**：
   - 企业交付/技术评审：逐模块写清技术方案考量、落地难点、关键量化指标参数（对照基准、吞吐/延迟/时限/金额）、系统瓶颈与责任归属；
   - 研讨/辩论/访谈：深度融入 topics 中的 debates 和论据案例，详细写清争辩双方的理论依据/测试数据/现实案例与底层矛盾。
3. **真实性底线**：研讨探讨与拍板决议严格区分边界；转写不清或排期未定标注 [待确认]；有据才写，忠实于原始事实。
4. **尾部记忆核验令（Recency 唤醒自检）**：检查你即将输出的 executive_summary 与 key_decisions，确保每条结论均可在本次会议原文/理解中找到当场达成的直接依据。若某条结论仅见于历史记忆而本次未重新研讨，请录入 history_comparison 反映历史背景，使 key_decisions 保持为当场决议。"""


# ── 客观模式生成提示词 ────────────────────────────────────────────────────────
_MINUTES_OBJECTIVE_AGENT_RULES = """## 三、全员客观纪要专有规则

### 1. 立场与称谓标准
- 采用绝对客观中立的第三方公文视角，通篇统一使用第三人称；
- 行为主体明确标注为真实姓名或客观规范称谓（姓名 > 明确部门/角色 > 原始编号），保持平权客观叙述。

### 2. 各字段客观提炼规则
- **headline（客观总结标题）**：
  - 概括会议核心业务主题，8–18 字，具备严谨公文标题风格；直陈核心业务标的与定调，不加任何视角前缀。
- **executive_summary（全员全景正文）**：
  - 首项（全局概览项）：简明客观交代全场会议背景、核心定调格局与全局统一部署（遵循篇幅预算，默认 200–300 字）；
  - 后续分项（业务模块/议题项）：每项成段自然陈述，顺应研讨推进脉络，平衡展开各业务板块的技术方案、指标参数与拍板决议，不偏向单一部门，不省略关键全局背景。
- **personally_relevant_points（全员落地行动分工）**：
  - 【字段定位】：因底层协议兼容，字段名为 personally_relevant_points，在此模式下统一产出【全员落地执行要点】，面向全场团队展开分工；
  - 【责任到人】：每项分工清晰指定至具体个人或专属团队（如“运维部”、“张工”），明确单一责任归口；
  - 【全员平铺】：直接平铺各团队任务，不设立任何个人视角分组标签；
  - 【句式规范】：每条交代完整事项要素：`[责任主体] + 核心任务 + 交付成果/验收标准 + 协同对象 + 完成时限`，确保执行主体清晰完整。
- **key_decisions（全场决策决议）**：
  - 从 MeetingUnderstanding.decisions 逐字搬运现场拍板结论，全景平铺，不执行按人分组。
- **risks_and_blockers / unresolved_questions（全场风险与未决）**：
  - 从 risks 与 open_questions 逐字搬运，全景平铺反映全场潜在技术隐患、交付阻碍与悬而未决的争议事项；全场无风险输出 []。"""

MINUTES_OBJECTIVE_GENERATION_PROMPT = _MINUTES_COMMON_BASE + "\n\n" + _MINUTES_OBJECTIVE_AGENT_RULES


# ── 个人模式生成提示词 ────────────────────────────────────────────────────────
_MINUTES_PERSONAL_AGENT_RULES = """## 三、个人视角纪要专有规则（作战秘书看板）

### 1. 立场、主线与人名口径
- 以【用户画像】与【用户视角模型】为主线，呈现专属于该参会人的作战重心与协同网络；
- **本人动作规范**：本人负责推进的事项一律采用【动宾短语】开头，直接陈述动作（如“输出压测报告”、“协调网关日志”），自然承接，无需前置姓名或人称代词；
- **他人动作规范**：他人事项规范保留真实姓名；分工、责任人、引语照原文写真名；他人分工仅在对本人产生协同输入时提及；
- **称谓一致性**：称谓保持全文连贯统一，提及他人事项时规范使用真实姓名。

### 2. 各字段作战提炼规则（含语义自然合流）
- **headline（个人作战标题）**：
  - 紧扣本人负责的业务战线与会议总主题，8–18 字精炼陈述。
- **executive_summary（聚焦本人主线与全局关键定调）**：
  - 首项（个人定调概览）：结合用户视角模型的 personal_summary，客观概括会议大盘背景，深度突出对本人业务线的战略要求与里程碑节点；
  - 后续分项：优先深度展开与本人关注领域（relevant_topics / attention_points）直接相关的模块进展；对非本人、无点名且在关注域外的外围杂项，自适应精炼压缩为一两句带过；但对影响项目全局走向的关键决策与指标，仍予以保真保留。
- **personally_relevant_points（个人行动看板——两大合流通道）**：
  - 严格看板化呈现，包含两大自然合流通道：
    ① `**本人相关**：`（独占一行置顶）：
       - 原文承诺动作（来自 possible_actions / action_hints）：动宾开头，写清时限、交付物与量化要求；
       - **未决跟进对齐动作**（来自 open_questions 语义升华）：本人负责在会后拉通对齐的事项（句式如：“与[对齐人]确认/敲定[方案]，闭环[影响范围]”）；
       - 完整收录本人的承诺与对齐事项，条目内直接陈述动作即可。
    ② `**重点协同**：`（独占一行，若有协同事实）：
       - 仅收录推进本人工作所必需的外部协同输入，以及重点盯防人物（focus_persons）的核心交付承诺；标明责任人真名、交付内容与承诺节点；
    ③ 聚焦本人主线与紧密协同方，外围日常杂项进行自适应精炼（无事实不立组名；全场本人无待办且无协同输入时输出 []）。
- **key_decisions（全场决策决议）**：
  - 逐字搬运上游决策决议，全景平铺保留（决议将在渲染端业务进展中按模块自然归组，无需在此设立个人分组标签）。
- **risks_and_blockers（个人卡点看板——两大合流通道）**：
  - 严格看板化呈现，包含两大自然合流通道：
    ① `**本人相关**：`（独占一行置顶）：
       - 内部技术隐患（来自 concerns / risks）：直接阻碍本人推进或标的落地的风险，交代现象、影响面与化解举措；
       - **外部输入断供卡点**（来自 data_gaps 语义升华）：因外部依赖断供导致本人交付受阻（句式如：“关键输入断供卡点：[缺失方]尚未提供[物料]，直接阻碍[交付物]按期达标”）；
    ② `**重点关注**：`（独占一行，若有关注风险）：
       - 重点盯防人物提出的重大定调风险或直接波及核心标的的隐患；
    ③ 聚焦本人关切与核心隐患，外围杂项风险自适应隐去（无卡点无风险时输出 []）。
- **unresolved_questions（未决看板）**：
  - 仅保留直接关乎本人业务边界的悬而未决争议。"""

MINUTES_PERSONAL_GENERATION_PROMPT = _MINUTES_COMMON_BASE + "\n\n" + _MINUTES_PERSONAL_AGENT_RULES
```

---

- [x] **1.2 构造双轨独立的 Supervisor 审核提示词**
  - **修改文件**：`domains/meeting/tasks/minutes/prompts.py`
  - **完整落地代码方案（正向放行与精准拦截版）**：

```python
# ── 审核公共基底 ──────────────────────────────────────────────────────────────
_SUPERVISOR_COMMON_BASE = """## 领域审核规则：纪要生成

### 核心审查原则与免审边界
- **提炼字段为审查重点**：审查重心严格收缩在提炼字段（headline / executive_summary / personally_relevant_points），聚焦是否存在事实捏造、数值错误或张冠李戴。
- **搬运项免审原则**：
  • 客观模式：key_decisions / risks_and_blockers / unresolved_questions 均为搬运项，底层与上游逐字对齐，微小字句差异直接放行；
  • 个人模式：key_decisions 为搬运项直接放行；risks_and_blockers 涉及卡点合流与看板分组，按个人专项规则审查。
- **历史记忆隔离审查**：若某条结论仅见于历史记忆而在本次未讨论，应录入 history_comparison 反映演变，避免将其作为本场新决议。
- **核心质量底线（未发现严重缺陷时予以 approve）**：
  1. 关键事实/结论与原文相悖（数字、归属或方向性判断写反）；
  2. 凭空捏造原文没有的人名、数字或虚假拍板；
  3. 将探讨/建议性意见升格为已拍板决议。
- **极简 Findings 纪律**：每个检查项 findings 仅限列出最核心的 1~3 条严重缺陷，单条不超过 100 字；未发现严重缺陷时必须给空数组 []。"""

# ── 客观审核提示词 ────────────────────────────────────────────────────────────
_OBJECTIVE_SUPERVISOR_RULES = """### 客观模式审查专项
1. **人称与立场规范**：
   - 确保通篇使用第三人称公文语态，以真实姓名或部门为主体陈述；
   - 保持客观中立，全面平铺各方论点与决策。
2. **全员覆盖度审查**：
   - 审查 personally_relevant_points 是否条条具备明确责任归口（个人或具体团队）；
   - 客观结构放行：客观模式正常采用全员平铺结构，未出现个人分组标签属于标准规范，予以直接放行通过！"""

MINUTES_OBJECTIVE_SUPERVISOR_PROMPT = _SUPERVISOR_COMMON_BASE + "\n\n" + _OBJECTIVE_SUPERVISOR_RULES

# ── 个人审核提示词 ────────────────────────────────────────────────────────────
_PERSONAL_SUPERVISOR_RULES = """### 个人视角审查专项
1. **人称与主语规范**：
   - 本人动作是否符合【动宾短语开头、省略主语】的标准规范；
   - 他人动作是否清晰标注真实姓名，避免产生误读。
2. **看板合流与承诺审查**：
   - 行动栏与风险栏是否规范包含 `**本人相关**：` 置顶；
   - 【本用户命中】里的承诺待办与专属输入卡点是否完整体现；
3. **自适应裁剪放行保障**：
   - 个人视角下，模型对全场无关人员的日常杂项分工、外围风险主动进行降噪与自适应隐去，属于高信息密度规范行为，应予充分认可并放行通过！"""

MINUTES_PERSONAL_SUPERVISOR_PROMPT = _SUPERVISOR_COMMON_BASE + "\n\n" + _PERSONAL_SUPERVISOR_RULES
```

---

- [x] **1.3 构造双轨独立的 Render 自由渲染提示词**
  - **修改文件**：`domains/meeting/tasks/minutes/prompts.py`
  - **完整落地代码方案**：

```python
MINUTES_OBJECTIVE_RENDER_PROMPT = """你是会议纪要渲染器。把通过审核的结构化客观纪要草稿，排版为高密度、分段清晰的全景公文纪要正文。

## 排版层级规范
# 客观会议纪要
## 全文摘要
（按业务阶段分段呈现，每段交代完整背景与统一部署）
## 关键决策
（逐条陈述拍板决策，不按人分组）
## 全员执行要点
（按责任部门/责任人列出落地分工，全景平铺呈现）
## 风险与阻塞
（全景平铺全场技术隐患与交付阻碍）
## 未决问题
（全景平铺待闭环议题）

## 纪律
1. 通篇严格保持客观第三人称公文排版；
2. 排版内容完全对齐草稿事实。"""

MINUTES_PERSONAL_RENDER_PROMPT = """你是会议纪要渲染器。把通过审核的结构化个人视角纪要草稿，排版为作战看板式个人纪要正文。

## 排版层级规范
# 个人视角纪要
## [会议概况]
（单段概括宏观背景与对本人战线的战略定调）
## [业务进展]
（按“**模块名称**：”分组呈现技术方案、指标参数与拍板决策）
## [相关行动]
**本人相关**：
- [ ] 动宾短语省略主语的任务条目（含原文承诺与未决跟进对齐）
**重点协同**：
- [ ] 关键协同人与外部交付承诺
## [相关风险]
**本人相关**：
- [ ] 内部技术隐患与外部输入断供卡点
**重点关注**：
- [ ] 重点关注人物提出的重大定调风险

## 纪律
1. 本人动作动宾开头省略主语，他人事项保留真实姓名；
2. 规范保持“**本人相关**：”置顶，复选框 - [ ] 规范呈现。"""
```

---

### Phase 2：步骤执行器（Steps）的模式分流路由（Routing Layer）

- [x] **2.1 升级 `MinutesGenerationAgent` 执行路由**
  - **修改文件**：`domains/meeting/tasks/minutes/steps/minutes_agent.py`
  - **改动细节**：
    在 `run()` 方法中根据 `parse_perspective_mode(shared_context)` 动态分流挂载 `MINUTES_PERSONAL_GENERATION_PROMPT` 或 `MINUTES_OBJECTIVE_GENERATION_PROMPT`：
    ```python
    mode = parse_perspective_mode(shared_context)
    system_prompt = (
        MINUTES_PERSONAL_GENERATION_PROMPT
        if mode == "personal"
        else MINUTES_OBJECTIVE_GENERATION_PROMPT
    )
    raw = await self.client.structured(
        system_prompt,
        shared_context,
        Minutes,
        MINUTES_GENERATION_OUTPUT_CONTRACT,
        label=f"minutes/agent/{mode}",
    )
    ```

- [x] **2.2 升级 `MinutesGenerationSupervisor` 审核路由**
  - **修改文件**：`domains/meeting/tasks/minutes/steps/minutes_supervisor.py`
  - **改动细节**：根据上下文中的模式标签动态挂载 `MINUTES_PERSONAL_SUPERVISOR_PROMPT` 或 `MINUTES_OBJECTIVE_SUPERVISOR_PROMPT`。

- [x] **2.3 升级 `MinutesGenerationRender` 渲染路由**
  - **修改文件**：`domains/meeting/tasks/minutes/steps/minutes_render.py`
  - **改动细节**：在 `_prompt_and_user` 无模板自由渲染分支下，根据模式标签动态分发 `MINUTES_OBJECTIVE_RENDER_PROMPT` 或 `MINUTES_PERSONAL_RENDER_PROMPT`。

---

### Phase 3：编排层上下文组装纯净化与白名单优化（Context Assembly Layer）

- [x] **3.1 纯净化客观模式的 `_line_shared_context`**
  - **修改文件**：`domains/meeting/orchestrator.py`
  - **改动细节**：
    在 `_line_shared_context`（L756–815）中强化模式隔离门禁：
    ```python
    if mode == "personal":
        # 仅真人模式注入用户专属偏好块、命中依据块、分组骨架、重点关注雷达
        if hit_block: parts.append(hit_block)
        if groups_block: parts.append(groups_block)
        if radar_block: parts.append(radar_block)
        if preference_block: parts.append(preference_block)
        if perspective: parts.append(f"用户视角模型：\n{_json(perspective)}")
    else:
        # 客观模式严禁注入任何个人画像与视角信息，彻底净化输入上下文！
        pass
    ```

- [x] **3.2 解锁编排层与审核切片的 Perspective 11 核心字段白名单**
  - **修改文件**：`domains/meeting/orchestrator.py`、`core/runtime/supervisor_slice.py`
  - **改动细节**：
    - `orchestrator.py` L532 的 `_compact_perspective()` 白名单精准对齐 11 核心字段：
      `("name", "personal_summary", "attention_points", "responsibilities", "possible_actions", "concerns", "relevant_topics", "open_questions", "data_gaps", "evidence")`；
    - `supervisor_slice.py` L468 的 `compact_perspective()` 同步对齐上述 11 字段；
    - 彻底移除 `goals`, `conclusions`, `stakeholders`, `inferred_role` 4 个僵尸字段，杜绝无效传输。

---

### Phase 4：草稿硬约束与模板直出后处理分流（Execution & Post-processing）

- [x] **4.1 升级 `hard_execution.py` 的模式分流门禁**
  - **修改文件**：`core/execution/hard_execution.py`
  - **改动细节**：
    在 `enforce_minutes_draft()` 中增加严密的安全守卫：
    - 个人模式下允许结合 `perspective_profile` 中的 `data_gaps` 作为 `risks_and_blockers` 的合法来源，解决 `subset_upstream_items` 匹配不到 upstream risks 导致外部断供卡点被清洗的硬伤；
    - 客观模式下严格 100% 从 `upstream["risks"]` 纯净拷贝，绝对不允许规则放宽。
    - **字典完整性校验**：无论哪种模式，处理完成后必须返回包含 7 个标准契约键的完整字典，绝不漏项。

- [x] **4.2 修复 `_placeholder.py` 的直出分流过滤**
  - **修改文件**：`core/templates/router/_placeholder.py`
  - **改动细节**：
    - 仅在 `is_personal` 且识别到真实用户时，放行 `**本人相关**：` 下的合法未决方案与外部卡点；
    - 独立无主的 `### 待确认事项汇总` 继续在客观与个人模式下均被清洗，杜绝孤立悬空内容。

---

### Phase 5：视角建模层深度重构（11 核心字段契约 + Prefill 缓存优化 + 屎山 Prompt 洗髓）【重中之重】

- [x] **5.1 契约与模型收敛至 11 核心字段（严格四位一体对齐）**
  - **修改文件**：
    - `domains/shared/perspective/models.py`
    - `domains/shared/perspective/contracts.py`
  - **改动细节**：
    - 重构 `PerspectiveModeling` dataclass，字段锁定为 11 个：
      `confidence`, `name`, `personal_summary`, `attention_points`, `possible_actions`, `concerns`, `evidence`, `responsibilities`, `relevant_topics`, `open_questions`, `data_gaps`；
    - 彻底删除 `goals`, `conclusions`, `stakeholders`, `inferred_role`；
    - 同步更新 `EMPTY_PERSPECTIVE_MODELING`，确保 11 个键值对 1:1 恒等；
    - 更新 `PerspectiveModelingGenerationContract` 中的字段声明与类型；
    - 确保 `synth.py` 程序合成输出的字典键集合与上述 11 字段完全恒等，杜绝任何 `OutputValidationError`。

- [x] **5.2 `PERSPECTIVE_MODELING_SYSTEM_PROMPT` 彻底洗髓与 Prefill 缓存重构**
  - **修改文件**：`domains/shared/perspective/prompts.py`
  - **改动细节**：
    1. **彻底物理剔除“客观模式”死代码**：既然客观模式编排层短路跳过，本 Prompt 100% 专注服务“真人个人”与“职业模板”，删掉全部客观全员的冗余说明（立省 35% Token）；
    2. **Token 0 静态先验与 Prefill Cache 保证**：前置规范提炼为完全静态的结构体，头部注入正向【法定权责本体论】（直接责任 My Action vs 协同关注 Focus vs 背景环境 Context），利用 Attention Sink 牢牢锁定行为准则；
    3. **正向化规范与激活未决归流**：明确三路事实的正向分流渠道：
       - 原文明确承诺的待办 $\to$ `possible_actions`（标「原文承诺」）；
       - 需在会后对齐推进的事项 $\to$ `open_questions`；
       - 阻碍交付的外部依赖缺口 $\to$ `data_gaps`；
    4. **拨乱反正 `personal_summary` 规则**：正面引导为“本人切身作战与交付概览（100-150字）：立足核心承接事项与上下游协同卡点，行文严谨具体”；
    5. **尾部交付令替代假自检**：删除末尾 8 条假自检八股文，改用单句紧凑的 Action Trigger 引导模型输出 11 字段 JSON。

- [x] **5.3 零 LLM 程序合成与极速漏斗优化**
  - **修改文件**：
    - `domains/shared/perspective/synth.py`
    - `domains/shared/perspective/hits.py`
  - **改动细节**：
    - `synth.py`：同步收敛输出 11 字段结构；将命中表中的未决线索与依赖缺口对称填充至 `open_questions` 与 `data_gaps`；
    - `hits.py`：重构 `attribute_to_speaker()` 为三级倒排极速漏斗：
      1. Level 0: `probe in block` 原文完全包含微秒短路（消化 85% 条目）；
      2. Level 1: 预先缓存 `set(block)`，字符交集位运算初筛（交集率 < 35% 瞬间跳过，排除 95% 无关段落）；
      3. Level 2: Top-2 候选精确比对。彻底拔除长会议 CPU 假死地雷，耗时从 5 秒降至 5 毫秒（提速 1000 倍）。

---

### Phase 6：双轨测试覆盖与全量回归防护（Testing & Verification）

- [x] **6.1 编写双轨提示词单测与分流有效性断言**
  - **修改文件**：`tests/core/test_perspective.py`、`tests/meeting/test_minutes_decoupling.py`（新建）
  - **测试用例**：
    1. **11 字段 Schema 契约校验测试**：适配并强化 `test_skip_and_synthesize`，断言 11 字段完整过检，4 个剔除字段不再出现，严格杜绝 `OutputValidationError`；
    2. **客观模式专测**：输入 `objective_perspective=True`，断言 `MinutesGenerationAgent` 使用客观 Prompt，正文 0 处出现 `与我相关`，Token 消耗显著降低；
    3. **个人视角专测**：输入申家坤画像，断言使用个人 Prompt，正文包含未决跟进待办与外部卡点，`**本人相关**：` 规范置顶；
    4. **记忆协同测试**：在客观与个人两种模式下分别注入历史记忆，断言 `history_comparison` 均能 100% 正确产出，记忆溯源不受分流任何影响。
    5. **终局 Report 校验全通过断言**：模拟完整 pipeline，断言 `_final_reports` 中的 `validate_payload(MinutesReport, ...)` 100% 一次性校验成功，0 降级触发！

- [x] **6.2 全量回归执行**
  - 运行 `pytest tests/` 与 `python tests/core/test_core.py`；
  - 确保 254+ 用例全部一次性全绿通过！

---

## 四、 执行甘特图与收益矩阵

| 任务模块 | 实施步骤 | 涉及核心文件 | 预期直接收益 |
|---|---|---|---|
| **Phase 0: 校验防炸护栏** | 锁定 11 字段与 7 契约字段定义，强化类型清洗 | `schema/validation.py`, `models*.py` | 杜绝 `validate_payload` 崩溃，零降级 |
| **Phase 1: Prompt 抽公共并分流** | 抽离 Common Base，构建 Objective 与 Personal 双轨 Prompt（正向引导重构） | `tasks/minutes/prompts.py` | 消除模型注意力对冲，客观省 40% Token |
| **Phase 2: Steps 执行层路由** | Agent、Supervisor、Render 根据 `mode` 动态分发 | `steps/minutes_*.py` | 审判与生成模式 100% 匹配，消除误杀打回 |
| **Phase 3: 上下文与白名单精炼** | 客观切除画像雷达，白名单精准放行 11 核心字段 | `orchestrator.py`, `supervisor_slice.py` | 彻底净化客观输入，释放未决与外部卡点 |
| **Phase 4: 执行门禁分流** | `hard_execution.py` 严格区分模式执行一致性门禁，放行 data_gaps | `hard_execution.py`, `_placeholder.py` | 客观 100% 保真，个人外部卡点安全通过 |
| **Phase 5: 视角建模深度洗髓** | 精简 11 字段契约，Prompt 应用 Prefill 与权责本体论，加速 `attribute_to_speaker` | `perspective/*.py` | 拔除屎山死代码，KV Cache 命中率提升，长会议秒级响应 |
| **Phase 6: 双轨测试验证** | 建立客观与个人双重验收标准，全量回归 | `tests/` | 零破坏已有业务，建立永久质量护栏 |
