# 英文/多语种普通模板纪要落地行动清单 (ACTION PLAN)

> **目标**：在不破坏现有中文任何功能的前提下，为普通模板纪要（`domain="meeting"`, `task="minutes"`）引入请求级语种控制 `lang: "zh" | "en"`，完成参数全链路穿透与全流程（会议理解 → 篇幅预算 → 草稿生成 → 审核监督 → 模板渲染与门禁）英文微调，实现英文会议原文的高质量地道英文纪要输出。
> **核心原则**：
> 1. `lang` 字段直接放在请求体第一层顶层，取值严格为 `"zh"` 或 `"en"`，不触碰 `_compat_task_request`。
> 2. 严格聚焦普通模板纪要（议题模板纪要暂不涉及）。
> 3. 中英文模板物理目录严格隔离（`resources/templates/zh/` 与 `resources/templates/en/`），严禁跨语言静默回退。
> 4. **Prompt 工程核心范式（统一首尾语言插槽装配）**：
>    - 将各 Agent 原 Prompt 首句（`你是...`）拆分抽象；
>    - **头部**统一注入：`【核心人设与交付目标】\n你是专职的【{role_prefix}】{角色名称}，本次任务必须全程直接产出标准规范的{role_prefix}内容。`；
>    - 中间保留原有结构化抽取/提炼规则主体；
>    - **尾部**统一注入：`## 语言红线\n1. 所有字段必须严格使用【{role_prefix}】输出，严禁夹杂中文字符；\n2. 专业术语、专有名词与人名保留英文原文写法。`。

---

## 阶段一：请求体验证、模板隔离与全局参数穿透 (Schema, Templates & Pipeline) [x] 已全部完成

### 1.1 请求体顶层增加 `lang` 字段 [x] 已完成
- **文件**：[app/schemas.py](file:///D:/study/demo/app/schemas.py)
- **落地内容**：
  - `TaskRequest` 新增顶层字段：`lang: str = "zh"`。
  - `@field_validator("lang")` 校验器：归一化为小写，仅接受 `"zh"` 与 `"en"`，非法输入抛出 422 校验异常。
  - 不触碰 `_compat_task_request`。

### 1.2 模板目录物理隔离与语种注册表 [x] 已完成
- **文件**：
  - [app/config.py](file:///D:/study/demo/app/config.py)
  - [resources/templates/zh/](file:///D:/study/demo/resources/templates/zh/) (29 个中文模板)
  - [resources/templates/en/](file:///D:/study/demo/resources/templates/en/) (试点 `general_minutes.md`)
- **落地内容**：
  - `template_dir(lang="zh")` / `template_registry(lang="zh")` / `resolve_template_format(key, lang="zh")` 全面支持语种隔离。
  - 英文请求暂未翻译模板严格返回 400，不搞静默跨语言回退。
  - 清理废弃模板 `admission_briefing.md`。

### 1.3 画像别名映射表收敛 [x] 已完成
- **文件**：
  - [resources/profiles/role_mapping.json](file:///D:/study/demo/resources/profiles/role_mapping.json)
  - [core/runner/profiles.py](file:///D:/study/demo/core/runner/profiles.py)
  - [README.md](file:///D:/study/demo/README.md)
- **落地内容**：
  - `role_mapping.json` 平移入 `resources/profiles/`，高内聚管理。
  - `load_role_mapping()` 优化首候选探测位为 `profiles/` 目录并更新 docstring。

### 1.4 任务准备与 Runner 参数透传 [x] 已完成
- **文件**：
  - [app/tasks.py](file:///D:/study/demo/app/tasks.py)
  - [core/runner/runner.py](file:///D:/study/demo/core/runner/runner.py)
  - [core/graph/nodes.py](file:///D:/study/demo/core/graph/nodes.py)
  - [domains/meeting/models.py](file:///D:/study/demo/domains/meeting/models.py)
- **落地内容**：
  - [app/tasks.py](file:///D:/study/demo/app/tasks.py)：`_Prepared(lang=req.lang)`、`_runner_args["lang"] = p.lang`。
  - [core/runner/runner.py](file:///D:/study/demo/core/runner/runner.py)：`prepare_run(lang=...)` 和 `run(lang=...)` 接收并在调用 `system.run_streaming` 时显式传入 `lang=prep.lang`。
  - [core/graph/nodes.py](file:///D:/study/demo/core/graph/nodes.py)：`run_streaming` 签名接收 `lang: str = "zh"`，并在 `initial_state` 中注入 `"lang": lang`。在 `_make_agent_node` 与 `_make_supervisor_node` 中动态反射检测并在支持时透传 `lang` 实参。
  - [domains/meeting/models.py](file:///D:/study/demo/domains/meeting/models.py)：在 `MeetingState(TypedDict)` 中显式声明 `lang: str`，防止 LangGraph 裁剪丢弃。

---

## 阶段二：会议理解 Agent 英文抽取微调 (Meeting Understanding) [x] 已完成

下游 `enforce_minutes_draft` 具有硬性约束逻辑，会直接将 `meeting_understanding` 中的 `decisions` 和 `risks` 强制覆盖到草稿中。如果理解层输出中文，草稿必遭中文事实污染。

### 2.1 Agent 执行签名与统一插槽 Prompt 装配 [x] 已完成
- **文件**：[domains/meeting/meeting_core/meeting_understanding_agent.py](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py)
- **落地内容**：
  - `MeetingUnderstandingAgent.run(...)` 增加 `lang: str = "zh"` 参数。
  - 剥离原 prompt 首句，当 `lang == "en"` 时在运行时动态装配：
    ```python
    role_prefix = "英文（English）" if lang == "en" else "中文"
    system_prompt = (
        f"【核心人设与交付目标】\n"
        f"你是专职的【{role_prefix}】会议理解助手，本次任务必须全程直接提取并产出客观、高密度的结构化{role_prefix}事实底座，供下游任务复用。\n\n"
        f"{body_prompt}\n\n"
        f"## 语言红线\n"
        f"1. 所有字段必须严格使用【{role_prefix}】输出，严禁夹杂中文字符；\n"
        f"2. 专业术语、项目简称、人名保留英文原文写法，不得翻译或脑补。"
    )
    ```
  - 当 `lang == "zh"` 时原样使用原始中文 Prompt，100% 零退化。

### 2.2 编排节点图调用穿透 [x] 已完成
- **文件**：[domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py)
- **落地内容**：
  - `_make_meeting_understanding_node` 与 `_meeting_understanding_node` 调用 `meeting_understanding_agent.run` 时，通过 `state.get("lang", "zh")` 传入 `lang` 实参。

---

## 阶段三：篇幅预算机制英文适配 (Length Budget) [x] 已完成

### 3.1 单词计数与英文档位预算 [x] 已完成
- **文件**：
  - [core/templates/length_budget.py](file:///D:/study/demo/core/templates/length_budget.py)
  - [domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py)
- **落地内容**：
  - 在 `length_budget.py` 中新增 `word_count(text: str) -> int`（基于 `[a-zA-Z0-9_'\-]+` 统计英文单词数）。
  - 新增英文预算档位常量 `ENGLISH_TIERS` 与预算计算函数 `english_budget_line(source_words: int, columns: int = 0) -> str`：
    - `< 1500 words`：正文参考 400–1000 词；
    - `1500–4000 words`：正文参考 600–1800 词；
    - `4000–10000 words`：正文参考 1000–3000 词；
    - `≥ 10000 words`：正文参考 1500–4500 词。
    - 生成纯英文提示：`【Length Budget】Source text ~{source_words} words... Target body word count guideline: {lo}–{hi} words.`
  - `_length_budget_line(state, line_name)` 判定 `state.get("lang") == "en"` 时自动分发英文预算逻辑。

---

## 阶段四：纪要草稿 Agent 英文生成微调 (Minutes Draft Generation) [x] 已完成

### 4.1 上下文构造与引导词英文适配 [x] 已完成
- **文件**：[domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py) (`_line_shared_context`)
- **落地内容**：
  - 当 `state.get("lang") == "en"` 时，在上下文中注入明确的 `输出语种要求：英文（English）` 提示块。
  - 在 `core/execution/hard_execution.py` 中新增 `parse_lang_mode(context)`，支持从上下文（单行或双行）可靠解析语种模式。

### 4.2 草稿生成 Prompt 统一插槽装配 [x] 已完成
- **文件**：[domains/meeting/tasks/minutes/steps/minutes_agent.py](file:///D:/study/demo/domains/meeting/tasks/minutes/steps/minutes_agent.py)
- **落地内容**：
  - `MinutesGenerationAgent.run(..., lang=None)` 增加语种识别与首尾插槽装配：
    ```python
    role_prefix = "英文（English）" if lang == "en" else "中文"
    system_prompt = (
        f"【核心人设与交付目标】\n"
        f"你是专职的【{role_prefix}】会议纪要草稿 Agent，本次任务必须全程直接提炼并输出标准、专业、精炼的商务{role_prefix}结构化草稿。\n\n"
        f"{body_prompt}\n\n"
        f"## 语言红线\n"
        f"1. 所有字段必须严格使用【{role_prefix}】输出，严禁夹杂中文字符与全角标点；\n"
        f"2. 待定/未决统一使用 [TBD] 或 [Pending Confirmation]，严禁输出 [待确认]；\n"
        f"3. 专业术语、专有名词与人名保留英文原文写法；\n"
        f"4. 执行要点统一采用 `[Owner] Action + Deliverable + Deadline` 结构清晰陈述。"
    )
    ```

### 4.3 草稿硬对齐规则兼容 [x] 已完成
- **文件**：[core/execution/hard_execution.py](file:///D:/study/demo/core/execution/hard_execution.py) (`enforce_upstream_carry`, `enforce_minutes_draft`)
- **落地内容**：
  - `enforce_upstream_carry` 与 `enforce_minutes_draft` 接收 `lang` 参数。
  - 草稿空标题默认值根据语种自动分发：`"Meeting Minutes"`（英文）/ `"会议纪要"`（中文）。

---

## 阶段五：审核监督机制英文微调与规则门禁 (Minutes Supervisor & Guardrails) [x] 已完成

### 5.1 审核上下文与统一插槽 Prompt 装配 [x] 已完成
- **文件**：[domains/meeting/tasks/minutes/steps/minutes_supervisor.py](file:///D:/study/demo/domains/meeting/tasks/minutes/steps/minutes_supervisor.py)
- **落地内容**：
  - `MinutesGenerationSupervisor.review(..., lang=None)` 增加语种识别与首尾插槽装配：
    ```python
    role_prefix = "英文（English）" if lang == "en" else "中文"
    domain_prompt = (
        f"【核心人设与交付目标】\n"
        f"你是专职的【{role_prefix}】纪要质量监督者，本次任务基于统一标准严格审核{role_prefix}纪要草稿并决定放行或返工。\n\n"
        f"{body_prompt}\n\n"
        f"## 语言红线与审核准则\n"
        f"1. 严格拦截任何未翻译的中文残留段落；\n"
        f"2. 半角标点、[TBD] 状态标签与标准英文缩写属于标准公文规范，一律 approve 放行。"
    )
    ```

### 5.2 规则门禁英文适配 (Guardrails) [x] 已完成
- **文件**：[core/execution/guardrails.py](file:///D:/study/demo/core/execution/guardrails.py) / [core/graph/nodes.py](file:///D:/study/demo/core/graph/nodes.py)
- **落地内容**：
  - 核查短路逻辑与发言人校验，`quick_facts_guardrail` 仅检查 `history_comparison` 确定性契约，人名已彻底剥离粗暴中文正则比对，完全语言中立。

---

## 阶段六：模板渲染、门禁拦截与兜底机制 (Render, Gate & Fallback) [x] 已完成

### 6.1 模板渲染 Prompt 统一插槽装配 [x] 已完成
- **文件**：[domains/meeting/tasks/minutes/steps/minutes_render.py](file:///D:/study/demo/domains/meeting/tasks/minutes/steps/minutes_render.py)
- **落地内容**：
  - 在 `_prompt_and_user` 中通过 `lang or parse_lang_mode(context)` 检测语种，并动态包裹首尾插槽：
    ```python
    role_prefix = "英文（English）" if lang == "en" else "中文"
    system_prompt = (
        f"【核心人设与交付目标】\n"
        f"你是专职的【{role_prefix}】会议纪要渲染器，本次任务严格依据已审核的{role_prefix}草稿填充模板，直接排版最终 Markdown 正文。\n\n"
        f"{body}\n\n"
        f"## 语言红线\n"
        f"1. 严格保持草稿的{role_prefix}原貌，严禁翻译为中文，严禁夹杂中文字符；\n"
        f"2. 标点符号统一使用标准半角英文标点（逗号后带空格）。"
    )
    ```
  - `compact_untemplated_minutes` 兼容中英文记忆附录标记：`"## 历史记忆引用"` 与 `"## Historical Memory References"`。

### 6.2 渲染输出门禁校验兼容 (Render Gate Tag Whitelist) [x] 已完成
- **文件**：
  - [core/templates/router/_gate.py](file:///D:/study/demo/core/templates/router/_gate.py)
  - [core/templates/router/_detect.py](file:///D:/study/demo/core/templates/router/_detect.py)
- **落地内容**：
  - 扩展 `_gate.py` 中的 `_KNOWN_TAGS`，加入常用英文状态标签：`"TBD"`, `"PENDING"`, `"PENDING CONFIRMATION"`, `"HIGH RISK"`, `"MEDIUM RISK"`, `"LOW RISK"`, `"BLOCKER"`, `"APPROVED"`, `"PASSED"`, `"REJECTED"`, `"IN PROGRESS"`, `"COMPLETED"`, `"OPEN"`, `"ACTION"`, `"DECISION"`, `"FYI"`, `"N/A"`, `"DONE"`。
  - 兼容忽略大小写与前缀匹配（如 `[Pending...]` 与 `[TBD...]` 不误报）。
  - 在 `_detect.py` 的 `_looks_like_placeholder` 中增加英文占位识别（`re.search(r"[a-zA-Z]{2,}", content)`），使英文模板如 `general_minutes.md` 准确被判为 `placeholder` 类型并路由。

### 6.3 零 LLM 确定性兜底渲染英文适配 (Fallback Render) [x] 已完成
- **文件**：[domains/meeting/tasks/minutes/steps/minutes_render.py](file:///D:/study/demo/domains/meeting/tasks/minutes/steps/minutes_render.py) (`render_draft`)
- **落地内容**：
  - 根据 `state.get("lang") == "en"` 自动分发纯地道英文骨架：
    - 标题：`Meeting Minutes`（客观）/ `{name}'s Meeting Minutes`（个人）；
    - 章节小节：
      - `## Executive Summary`
      - `## Key Decisions`
      - `## Action Items` / `## Individual Action Items`
      - `## Risks & Blockers`
      - `## Open Questions`
      - `## Historical Comparison`
    - 空草稿提示：`"Please refer directly to the meeting transcript."`
  - 英文模式产出确保 0 个汉字字符。

---

## 阶段七：全流程验证与回归测试清单 (Verification Checklist) [x] 已全部通过

| 序号 | 验证模块 | 测试方法 | 预期结果 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **参数穿透测试** | 单元测试验证 `runner.run(..., lang="en")` 到 `state["lang"] == "en"` | `state` 与工作流全程持有并流转 `"en"` 状态 | [x] 已通过 |
| 2 | **篇幅预算英文测试** | 构造 2500 词纯英文转写，测试 `_length_budget_line` | 输出包含 `【Length Budget】` 及合理单词区间（600–1800 words） | [x] 已通过 |
| 3 | **会议理解英文微调** | 使用英文会议片段调用 `MeetingUnderstandingAgent.run(..., lang="en")` | 输出挂载【核心人设】与【语言红线】，无中文翻译污染 | [x] 已通过 |
| 4 | **草稿生成英文微调** | 使用英文会议理解 + 英文原文调用 `MinutesGenerationAgent.run` | Prompt 挂载首尾英文插槽，待确认项约束为 `[TBD]`，空标题为 `Meeting Minutes` | [x] 已通过 |
| 5 | **审核监督英文放行** | 使用英文草稿调用 `MinutesGenerationSupervisor.review` | Prompt 挂载英文准则，明确半角标点与 [TBD] 放行 | [x] 已通过 |
| 6 | **渲染门禁防误判** | 用含 `[TBD]`、`[Approved]` 的英文 Markdown 调用 `validate_rendered_output` | 放行通过，不误报占位符残留错误；真实残留占位符准确拦截 | [x] 已通过 |
| 7 | **确定性兜底渲染** | 构造 `degraded=True` 的英文 `state`，调用 `MinutesGenerationRender.render_draft` | 产出纯英文骨架（`## Executive Summary` 等），无中文字符 | [x] 已通过 |
| 8 | **中文老功能回归** | 执行现有全量中文单测套件 `pytest tests/unit/meeting/ tests/unit/core/templates/test_template_gate.py` | 100% 通过，现有中文逻辑完全零破坏零退化 | [x] 已通过 |
| 9 | **端到端英文普通纪要集成** | 构造全英文会议完整请求跑通流水线 `test_end_to_end_english_minutes_pipeline` | 产出结构完备、格式标准、语言地道的全英文 Markdown 会议纪要流式事件 | [x] 已通过 |
