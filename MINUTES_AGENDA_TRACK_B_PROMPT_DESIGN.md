# 议题纪要特化轨（Track B）Prompt 构建与全链路重构方案（完善优化版）

> **适用场景与激活前置条件**：  
> 仅当 `domain == "meeting"` 且 `task/line == "minutes"` 且 `docs` 经探测识别出 $\ge 1$ 个有效实质研讨议题（`has_valid_agenda == True`）时激活。  
> 常规会议（无 docs、docs 为参考资料或无有效议题）、个人视角会议以及其他 7 条任务线 100% 沿用原有通用 Prompt 与模板，零改动、零影响。

---

## 一、动态注入清理复盘与设计纠偏

在上一阶段中，我们在 `domains/meeting/orchestrator.py` 中删除了此前散落的 4 处碎文本动态注入，恢复了代码库的纯净：
1. **理解层**：移除了 `user_channel` 中拼接的 `nav_block` 临时说明；
2. **草稿层**：移除了 `_agent_context` 中拼接的 `【审定议题纪要撰写指引】`；
3. **审核层**：移除了 `_supervisor_context` 中临时追加的议题清单；
4. **渲染层**：移除了 `_render_context` 中在 `extra` 里追加的 `【议题结构排版指引】`。

### 关键设计纠偏：严格区分「业务数据传递」与「动态 Prompt 注入」
在推进重构前，必须厘清一个核心原则：
* **动态 Prompt 注入（错误做法，已清除）**：在业务上下文尾部临时塞一段“请按以下结构撰写/排版”等指令，导致外挂小纸条与底层 System Prompt 打架。
* **业务数据传递（正确做法，必须保证）**：审定议题清单（何刚总致辞、互动交流、任务令签署与授予）是本次会议的**客观输入数据**，就像会议原文、用户姓名一样，必须通过标准字段/上下文块自然交付给各 Agent，而不是让 Agent 凭空猜测。

---

## 二、全链路关键细节深度梳理与确认

结合系统底层运行机制（LangGraph、Router、Hard Execution、Template Pipeline），梳理出以下 7 个关键细节：

### 细节 1：议题清单业务数据的自然传递机制
* **在原文侧**：`domains/meeting/agenda_engine.py` 的 `build_tagged_transcript_with_head_tail` 生成的 `tagged_transcript`，在正文最头部自然带上：
  ```
  【现场审定的有效议题清单】：
  1. 议题：何刚总致辞（汇报人：何刚）
  2. 议题：互动交流（现场问答、自由交流与讨论）（汇报人：未指定）
  3. 议题：任务令签署与授予（汇报人：未指定）
  ```
  这样，理解层、草稿层、审核层只要读到会议原文，就自然拥有了议题全称与顺序的业务输入。
* **在渲染侧**：在 `_render_context` 的 `blocks` 中，增加标准数据块 `("现场审定的有效议题清单", agenda_checklist, "raw")`。它是标准的业务素材块，不是 prompt 指令。

### 细节 2：渲染层必须基于 `build_template_render_prompt` 专有构建
* 系统在渲染有模板的纪要时，走的是 `core.templates.router.route_template`，它将 `template_prompt` 与 `PLACEHOLDER_RULES` 自动拼装。
* 通用的 `MINUTES_RENDER_TEMPLATE_PROMPT` 中，第 1 条规则明确写死“以已审核草稿为唯一事实与结构基准”，导致平铺草稿锁死了渲染器的结构。
* **解决方案**：针对特化轨，专有构建 `MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`，覆盖 `source_rule`，明确“以草稿为事实基准，以审定议题为主线结构规范”，彻底消除大纲冲突。

### 细节 3：上下文模式标记机制（轻量原生分流）
* 模仿系统原生的 `视角模式：objective / personal`，当 `state.get("has_valid_agenda")` 为 True 时，在 `_line_shared_context`、`_supervisor_context`、`_render_context` 的头部统一定义标准状态标记：
  ```
  议题模式：agenda_enhanced
  ```
* 各下游 Agent（`minutes_agent.py`、`minutes_supervisor.py`、`minutes_render.py`）仅需通过一行轻量工具函数 `is_agenda_enhanced_mode(context)`，即可精准、无侵入地分流到专有 Prompt。

### 细节 4：`_line_shared_context` 中 `fact_note` 的正向适配
* 通用模式下的 `fact_note` 写着“顺应业务研讨推进脉络成段展开”。
* 在特化轨下，当 `has_valid_agenda` 时，正向切换为：
  > “说明：本场会议已审定有效议题清单，会议原文已完成议题打标。以审定议题为主线骨架，以各议题的因果脉络、核心指标与论辩过程成段展开草稿，确保每段清晰标注所属议题与子主题。”

### 细节 5：`enforce_minutes_draft` 硬执行安全确认
* 经源码审查，`core.execution.hard_execution.MINUTES_CARRY_MAP` 仅对齐：
  - `key_decisions` ← `decisions`
  - `risks_and_blockers` ← `risks`
  - `unresolved_questions` ← `open_questions`
* `executive_summary` 属于**纯提炼字段**，`enforce_minutes_draft` 绝不修改或抹除其中的文字。草稿中的 `【所属议题名称 / 子研讨主题】` 标注前缀 100% 安全，不会被误删。

### 细节 6：审核层完整保留 `_SUPERVISOR_COMMON_BASE` 质量底线
* 不脱离既有的通用底座。特化轨专有审核 Prompt 采用 `_SUPERVISOR_COMMON_BASE + _AGENDA_SUPERVISOR_RULES`。
* 完整保留“搬运项免审原则”、“核心质量底线”、“首选 approve 策略”，仅新增“议题覆盖完整性与子主题归属准确性审查”，确保审核不误杀、不漏检。

### 细节 7：测试用例同步升级
* 将因清理动态注入而断言失败的 3 个旧测试用例，更新为验证“专有 Prompt 挂载”与“议题业务数据自然传递”。

---

## 三、特化轨四层专有 Prompt 的精确代码级定义

### 1. 理解层专有 Prompt：`MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT`
> 存放于：`domains/meeting/meeting_core/prompts.py`

```markdown
你是会议理解助手（审定议题专有模式）。本次会议已由现场议程审定有效讨论议题清单，你的任务是以审定议题为主线，从会议原文中提取客观、高密度的结构化事实底座，供下游任务复用。

## 事实提取原则
1. 真实保真：以会议原文明确出现的内容为唯一依据。
2. 要素完整：记录事实时完整保留量化指标（数字带单位、对照基准）、交付时限、金额与核心论据。
3. 陈述归属：保留发言人立场与陈述主体，客观记录各方观点。
4. 称呼规范：优先使用真实姓名，无法确认身份时沿用原文角色或原始编号；只有编号时如实保留原始编号；上下文出现【本用户称呼】时，原文里该用户的全称与其别称统一归一到全称；其余发言人忠实保留原文客观称谓，不臆测身份。

## 结构生成指引（议题主线与事实归集）
- session_segments：以现场审定的有效议题为主线组织研讨阶段，全面覆盖现场所有实质研讨内容：
  - segment_title：采用「所属议题名称：子研讨主题」的标准格式命名（例如：何刚总致辞：开场致辞与北京业务回顾、互动交流：唤醒体验与产品线协同、任务令签署与授予：会战签发仪式）。若议题讨论内容集中单一，可直接使用议题全称；
  - context_and_reasoning：因果背景、争论焦点与定调依据（清晰陈述该子主题下的讨论脉络、决策动因与各方立场）；
  - key_facts：提炼该子主题下提出的核心量化指标、关键事实论据、技术方案参数与落地执行节点（去重提炼，优先高信息密度事实）。
- decisions：现场明确拍板并达成共识的结论列表（逐条列出）。
- open_questions：尚未达成一致或明确会后另行确认的事项列表。
- action_hints / risk_hints：提取包含动作/风险、责任人、时限及原文证据原句的线索。
- debates：提取各方争议立场、论据与原句线索。

请严格按照指定的 JSON Schema 格式输出。
```

---

### 2. 草稿层专有 Prompt：`MINUTES_AGENDA_GENERATION_PROMPT`
> 存放于：`domains/meeting/tasks/minutes/prompts.py`

由 `_MINUTES_COMMON_BASE` 组合 `_MINUTES_AGENDA_AGENT_RULES` 生成：

```python
_MINUTES_AGENDA_AGENT_RULES = """## 三、审定议题客观纪要专有规则

### 1. 立场与称谓标准
- 采用绝对客观中立的第三方公文视角，通篇统一使用第三人称；
- 行为主体规范标注为真实姓名或客观规范称谓（姓名 > 明确部门/角色 > 原始编号），保持平权客观叙述。

### 2. 各字段客观提炼规则
- **headline（客观总结标题）**：
  - 概括会议核心业务主题，8–18 字，具备严谨公文标题风格；直陈核心业务标的与定调，不加任何视角前缀。
- **executive_summary（审定议题层级分段正文）**：
  - 首项（全场概览项）：简明客观交代全场会议背景、核心主线议题推进态势与最关键的全局定调决议（约 250–350 字）；
  - 后续分项（议题分段项）：严格按审定议题顺序，每项成段自然陈述。段落开头统一明确标注【所属议题名称 / 子研讨主题】（例如：`【何刚总致辞 / 开场致辞与北京业务回顾】何刚总回顾北京业务历史...`、`【互动交流 / 唤醒体验与产品线协同】高畅提出小艺作为平台面向不同产品线...`），平衡展现技术方案考量、关键量化指标与讨论定调。
- **personally_relevant_points（全员落地行动分工）**：
  - 统一产出面向全场团队的执行要点，明确责任归口至具体个人或专属团队；句式为 `[责任主体] + 核心任务 + 交付成果/验收标准 + 协同对象 + 完成时限`。
- **key_decisions（全场决策决议）**：
  - 从 MeetingUnderstanding.decisions 逐字搬运现场拍板结论，全景平铺。
- **risks_and_blockers / unresolved_questions（全场风险与未决）**：
  - 从 risks 与 open_questions 逐字搬运，全景平铺反映全场潜在技术隐患与悬而未决的争议事项；全场无风险输出 []。"""

MINUTES_AGENDA_GENERATION_PROMPT = _MINUTES_COMMON_BASE + "\n\n" + _MINUTES_AGENDA_AGENT_RULES
```

---

### 3. 审核层专有 Prompt：`MINUTES_AGENDA_SUPERVISOR_PROMPT`
> 存放于：`domains/meeting/tasks/minutes/prompts.py`

由 `_SUPERVISOR_COMMON_BASE` 组合 `_AGENDA_SUPERVISOR_RULES` 生成：

```python
_AGENDA_SUPERVISOR_RULES = """### 审定议题模式审查专项
1. **议题完整性与归属审查**：
   - 审查草稿 executive_summary 是否全面覆盖本次会议审定的有效讨论议题；
   - 审查各研讨段落所标注的【所属议题名称 / 子研讨主题】是否准确反映实际研讨范畴，不存在脱幅遗漏；
   - 只要各审定议题均有对应段落且事实真实，予以放行通过。
2. **全员覆盖度与格式放行**：
   - 审查 personally_relevant_points 是否具备明确责任归口；
   - 段落采用【所属议题名称 / 子研讨主题】标注属于标准规范，予以直接放行通过；
   - 搬运项（决策、风险、未决问题）由底层程序强对齐，直接免审放行。"""

MINUTES_AGENDA_SUPERVISOR_PROMPT = _SUPERVISOR_COMMON_BASE + "\n\n" + _AGENDA_SUPERVISOR_RULES
```

---

### 4. 渲染层专有 Prompt：`MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT` 与 `MINUTES_AGENDA_RENDER_PROMPT`
> 存放于：`domains/meeting/tasks/minutes/prompts.py`

#### A. 模板渲染 Prompt（通过公共工厂构建，核心在于重写 `source_rule`）：
```python
MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="会议纪要渲染器",
    source="已审核草稿（结构化事实基准）",
    source_rule=(
        "**以已审核草稿为事实基准，以审定议题为主线结构规范**：排版渲染时，严格按照以下三层规范呈现：\n"
        "1. 一级小节标题（### 议题名称）：正文 [要点梳理] 栏目必须且仅使用草稿中记录的审定议题全称设立三级小节标题（###），严格保持议题名称逐字对应与原序呈现；\n"
        "2. 二级子主题（#### 1. 子主题名称）：对于包含多个不同研讨方向的议题，以草稿中的子研讨主题设立四级标题（格式：`#### 1. 子主题名称` 或 `**1. 子主题名称**：`），并在子标题下方使用 - 逐项列出具体方案考量与事实论据；\n"
        "3. 单一主题议题直接分条：对于研讨内容单一集中的议题，直接在三级标题（###）下方使用 - 逐项列出核心事实与定调；\n"
        "4. 事实归属保真：草稿中的各项研讨事实，根据其议题与子主题标识归入对应小节，完整保留硬核数据指标与论据细节，无事实遗漏。"
    ),
    empty_rule=(
        "某栏在草稿中对该栏主题无依据且模板允许省略时直接保持空内容自适应隐去；"
        "模板没约定时优先自适应隐去，确需占位时按模板指定词填写，不使用外部常识补全。"
    ),
    extra_rules=[
        "模板若含写作要求，按该要求客观准确填写",
    ],
)
```

#### B. 无模板兜底 Prompt：
```python
MINUTES_AGENDA_RENDER_PROMPT = """你是会议纪要渲染器（审定议题专有模式）。把通过审核的结构化议题草稿，排版为结构分明、层级严整的全景公文纪要正文。

## 排版层级规范
# 会议纪要
## 全文摘要
（单段概括全场宏观态势与最关键决议）
## 要点梳理
### [审定议题一全称]
#### 1. [子主题名称]
- 方案考量与具体论据
### [审定议题二全称]
...
## 关键决策
（逐条陈述现场明确拍板的决议）
## 全员执行要点
（按责任人/部门列出落地执行分工）
## 风险与阻塞
（全景呈现技术卡点与交付隐患）

## 排版准则
1. 一级小节必须对齐审定议题全称，二级子主题承接草稿分项；
2. 保持客观第三方公文体，忠实呈现草稿事实与量化参数。"""
```

---

## 四、落地实施改动清单（精准且完备）

| 模块 | 修改文件 | 涉及改动点说明 |
| :--- | :--- | :--- |
| **议程对齐** | `domains/meeting/agenda_engine.py` | 在 `build_tagged_transcript_with_head_tail` 头部自然加入 `【现场审定的有效议题清单】` 纯数据块 |
| **通用契约** | `core/execution/hard_execution.py` | 增加轻量函数 `is_agenda_enhanced_mode(context: str \| None) -> bool` |
| **理解层** | `domains/meeting/meeting_core/prompts.py` | 新增 `MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT` |
| **理解 Agent** | `domains/meeting/meeting_core/meeting_understanding_agent.py` | 新增可选入参 `is_agenda_enhanced: bool = False`，为 True 时选用专有理解 Prompt |
| **纪要 Prompt** | `domains/meeting/tasks/minutes/prompts.py` | 新增 `MINUTES_AGENDA_GENERATION_PROMPT`、`MINUTES_AGENDA_SUPERVISOR_PROMPT`、`MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`、`MINUTES_AGENDA_RENDER_PROMPT` |
| **草稿 Agent** | `domains/meeting/tasks/minutes/steps/minutes_agent.py` | 若 `is_agenda_enhanced_mode(shared_context)` 则直接选取 `MINUTES_AGENDA_GENERATION_PROMPT` |
| **审核 Agent** | `domains/meeting/tasks/minutes/steps/minutes_supervisor.py` | 若 `is_agenda_enhanced_mode(context)` 则直接选取 `MINUTES_AGENDA_SUPERVISOR_PROMPT` |
| **渲染 Agent** | `domains/meeting/tasks/minutes/steps/minutes_render.py` | 若 `is_agenda_enhanced_mode(approved_context)` 则传入专有渲染模板与无模板 Prompt |
| **编排引擎** | `domains/meeting/orchestrator.py` | 1. `_make_meeting_understanding_node` 传入 `is_agenda_enhanced=True`；<br>2. `_line_shared_context`、`_supervisor_context`、`_render_context` 在有议题时头部输出 `议题模式：agenda_enhanced`，`_render_context` 的 blocks 自然追加议题清单数据块 |
| **单元测试** | `tests/unit/meeting/test_minutes_agenda_integration.py` | 更新 3 个测试用例，断言 `议题模式：agenda_enhanced` 与专有 Prompt 挂载 |
