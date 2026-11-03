# minutes 任务 topic_major（议题主序）执行清单

> 目标：在现有 `minutes` 任务内新增 `topic_major` 布局，实现“先分议题，每个议题内部再按模板栏目输出”。
>
> 试点模板：`resources/agenda_templates/zh/team_meeting.md`（已完成两栏改造），其余 19 个议程模板先不动。
>
> 硬约束：**column_major（现有议题纪要）功能零影响**；不新增任务线；不给用户新增 `layout` 参数；API 返回结构不变。

---

## 执行路线（总览，先看这一节）

### 清单是否满足需求

| 需求 | 清单现状 | 结论 |
|---|---|---|
| agenda view 增加 topic layout | 已定义 `view=agenda_objective + layout=topic_major` 分支 | 满足 |
| column 逻辑和功能不受影响 | 所有新路径受 layout 门控；有 column 回归清单 | 满足；`team_meeting` 原地改造后该模板走 topic，其他模板 column 不变 |
| 只针对团队例会中文模板测试 | `team_meeting.md` 已改两栏；英文未动 | 满足 |
| 解析模板 layout | 6.1 已细化 `split_template_layout` + 剥离 + state + 测试 | 满足 |
| 重新定义 prompt | 4.1 / 4.2 / 4.3 已有草稿、审核、渲染 prompt | 满足 |
| texts 四个字段与 column 一致 | 2.1 / 4.4.1 已明确复用 column 的辅助材料与动态拼接 | 满足 |

**仍需补齐的缺口（本次清单已补入对应章节）：**

1. **Supervisor 快速短路 / 规则门禁**：topic 草稿没有旧 7 字段，`quick_facts_guardrail` / 短会 bypass 可能误判，需要禁用或适配。
2. **Memory 落库判断**：`_draft_has_fact` / `extract_meeting_fact_from_minutes_draft` 仍按旧 7 字段，topic 草稿可能被判“无事实”而不入库。
3. **程序化议题覆盖校验**：仅靠 prompt/审核不够，需要对比 `topics` 与 `valid_agendas` 的数量、标题、顺序。
4. **渲染空子栏清理**：`**工作进展**` 等加粗子栏不会被 `empty_section_issues` 当标题检查，需要程序化清理空子栏。
5. **自动分类说明**：不加开关；`team_meeting` 一旦被选中，就按模板 layout 走 topic；默认 `MINUTES_TEMPLATE_AUTO=off`，如需固定行为可保持 auto off。

### 关键决策（已定）

| 编号 | 决策 | 结论 |
|---|---|---|
| D1 | 试点模板形态 | **原地改 `team_meeting.md`**；通过模板 layout 元数据判断；不再新增变体 |
| D2 | 是否加 `MINUTES_TOPIC_MAJOR=off/on` 开关 | **不加**；模板 layout 元数据就是开关；回滚 = 移除/修改模板 layout 元数据 |
| D3 | layout 取值 | `column_major`（默认）/ `topic_major`；无 layout 或非法值回退 column_major |
| D4 | 草稿契约 | 已定：顶层 `headline/overview/topics/history_comparison`；议题内 `topic_name/topic_summary/decisions/actions/risks/open_questions` |
| D5 | texts / 辅助材料 | 与 column 完全一致；`actions_text` 不进入 minutes |
| D6 | 议题内子栏样式 | **仅针对团队例会模板**：独立加粗行 `**工作进展** / **落实安排** / **未决风险**`；其他 topic 模板可声明自己的子栏 |

### 最佳执行顺序

> 原则：先做“不改变行为”的骨架，再做契约/prompt，最后接线和试点；每一阶段都以 column 回归为门禁。

| 阶段 | 内容 | 完成门禁 |
|---|---|---|
| Phase 0 | 确认 D1–D6 已定 | 决策记录在案 |
| Phase 1 | layout 解析/剥离骨架：`split_template_layout`、state、默认回退 | 旧模板解析/column 行为零变化 |
| Phase 2 | 契约与模型：`MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT`、`TopicMajorMinutes` | 新旧模型单测通过 |
| Phase 3 | prompt 与路由：草稿/审核/渲染 prompt、`(view, layout)` 选择 | prompt 选择单测通过，column prompt 不变 |
| Phase 4 | 草稿 agent 接线：layout 分支、新模型/契约、辅助材料复用、议题覆盖校验 | topic 草稿形状正确；column 分支不变 |
| Phase 5 | 审核接线：topic scope、复用审核契约、禁用/适配快速短路与规则门禁 | topic 审核可用；column 审核不变 |
| Phase 6 | 渲染接线：topic render prompt、上下文、fallback、空子栏清理 | topic 渲染正确；column 渲染不变 |
| Phase 7 | 上下文/记忆/报告适配：red line/JSON 契约分支、memory 落库判断、topic 提取适配 | 记忆/报告不退化 |
| Phase 8 | 试点：团队例会中文模板（原地改造）显式选择 | 端到端输出符合两栏三子块 |
| Phase 9 | 回归与回滚：column 全量测试、其余 19 模板零变化、移除 layout 元数据可回滚 | 回归全绿，回滚可执行 |
| Phase 10 | 后续扩展：更多模板转 topic_major | 按模板逐个灰度 |

---

## 0. 字段定稿（v1）

topic_major 的草稿结构定为：

```json
{
  "headline": "",
  "overview": "",
  "topics": [
    {
      "topic_name": "",
      "topic_summary": [],
      "decisions": [],
      "actions": [],
      "risks": [],
      "open_questions": []
    }
  ],
  "history_comparison": []
}
```

- 顶层 4 个键：`headline / overview / topics / history_comparison`
- 每条议题记录 6 个键：
  - `topic_name`
  - `topic_summary`
  - `decisions`
  - `actions`
  - `risks`
  - `open_questions`
- 不设 global 桶。
- `history_comparison` 固定 `[]`，由程序装配。

### 字段语义

| 字段 | 类型 | 含义 |
|---|---|---|
| `headline` | string | 会议纪要标题（8–18 字，公文标题风格） |
| `overview` | string | 全场概况，单段；不承载跨议题行动/风险清单 |
| `topics` | array | 每个有效议题一条记录，N 个有效议题 → N 条 |
| `topic_name` | string | 议题全称，必须与【现场审定的有效议题清单】逐字一致 |
| `topic_summary` | string[] | 本议题正文/研讨/进展/内容要点；一条一个完整事实；不写 `### 议题名`、不写全场概况、不写决策/行动/风险/未决 |
| `decisions` | string[] | 本议题已拍板的决议/结论/定调；讨论/建议不算 |
| `actions` | string[] | 本议题的后续行动；写清责任人、交付物、时限 |
| `risks` | string[] | 本议题的风险/卡点/阻塞/外部依赖 |
| `open_questions` | string[] | 本议题的未决/待确认/遗留问题 |
| `history_comparison` | string[] | 程序装配字段，草稿固定 `[]` |

### 契约硬规则

1. 顶层只允许 `headline / overview / topics / history_comparison` 四个键；
2. 每条议题记录只允许上述六个键；
3. N 个有效议题 → `topics` 恰好 N 条，顺序与清单一致；
4. `topic_name` 逐字一致，不得改名、合并、拆分、重排；
5. 所有内容字段都是字符串数组，无内容写 `[]`；
6. `topic_summary` 不写议题标题、不写全场概况、不写决策/行动/风险/未决；
7. `decisions` 只写已拍板内容，不写讨论、建议、待定；
8. `actions` 必须交代责任人、交付物、时限；
9. `risks` 与 `open_questions` 保持区分：风险是“可能出问题/已经卡住”，未决是“还没定/待确认”；
10. 同一事实只出现一次，不得跨议题重复；
11. 不设 global 桶；跨议题/会末定调事项归入最相关议题；
12. 所有事实以打标转写为准，不得虚构。

---

## 1. 现状与不变量

- [x] `team_meeting.md` 已完成 topic_major 两栏改造：
  ```markdown
  <!-- layout
  mode: topic_major
  container: 议题梳理
  -->
  ```
  - `## [例会概况]` 保留为全局概况栏；
  - 旧的 `## [工作进展] / [落实安排] / [未决风险]` 三个顶级栏目已删除；
  - 新增唯一的 `## [议题梳理]` 议题容器；
  - 议题容器内按 `**工作进展** / **落实安排** / **未决风险**` 三个子块展开。
- [x] 模板解析验证通过：
  - `detect_template_kind` → `placeholder`；
  - `parse_placeholder_template` 识别两个标题占位：`例会概况`、`议题梳理`；
  - `plan_placeholder_fill`：`scalars = 2`，`row_templates = 0`。
- [ ] 代码尚未接入 layout 注解解析、剥离与分支（见 6.1）。

### 必须保持不变

- [ ] `view == agenda_objective` 且 `layout == column_major` 时，行为与现在完全一致。
- [ ] `MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT`、`MINUTES_AGENDA_*` prompt 不改。
- [ ] `Minutes` 生成模型不改。
- [ ] `agenda_minutes` 独立任务线不改。
- [ ] 非 agenda view（objective / personal / role_template）不改。
- [ ] `MinutesReport` / API `personalized_minutes` 输出结构不改。
- [ ] 没有 `layout` 元数据或 `layout: column_major` 的模板继续走旧逻辑。

---

## 2. 概念区分：column_major vs topic_major

| 维度 | column_major（现有） | topic_major（新增） |
|---|---|---|
| 第一层组织 | 模板栏目 | 议题 |
| 议题位置 | 某一栏内部用 `### 一. 议题名` 分段 | 每个议题是一条记录 |
| 草稿契约 | 旧 7 字段 | `headline / overview / topics[] / history_comparison` |
| 议题内字段 | 只有 `executive_summary[1:]` 是议题作用域 | `topic_summary / decisions / actions / risks / open_questions` |
| 模板形态 | `## [工作进展]`、`## [落实安排]` 等并列栏 | `## [例会概况]` + `## [议题梳理]`，议题内再分子栏 |
| 全局桶 | 有 `key_decisions / personally_relevant_points / ...` | 不设 global 桶 |

### 关键语义变化

- 旧 `executive_summary`：
  - `[0]` = 全场概况；
  - `[1:]` = 各议题正文。
- 新 `topic_major`：
  - `overview` = 全场概况；
  - `topics[].topic_summary` = **单个议题**的正文。
- 旧 `key_decisions / personally_relevant_points / risks_and_blockers / unresolved_questions` 在 topic_major 中对应：
  - `decisions / actions / risks / open_questions`。

### 2.1 texts 输入与辅助材料：topic 必须完整复用 column

`minutes` 的 `texts` 固定支持五个 key，topic_major 与 column_major 消费完全一致：

| texts key | minutes 使用方式 | topic_major |
|---|---|---|
| `transcript` | 会议原文；议题模式下使用 `tagged_transcript` | 同 column |
| `keypoints` | `【用户核心关键点】` + `KEYPOINTS_PROMPT_BLOCK` | 同 column |
| `notes` | `【用户划线原话与笔记】` + `NOTES_PROMPT_BLOCK` | 同 column |
| `vision_info` | `【视觉信息参考(OCR)】` + `VISION_PROMPT_BLOCK` | 同 column |
| `actions_text` | 仅 `actions` 任务消费，`minutes` 不使用 | 同 column，不消费 |

- [ ] 不新增 topic 专用 texts key，不改变 API schema。
- [ ] 不改变 `_pack_minutes_auxiliary(keypoints, notes, vision_info)` 的拼接格式。
- [ ] 不改变 `AGENDA_AUX_PROMPT_BLOCK`、`KEYPOINTS_PROMPT_BLOCK`、`NOTES_PROMPT_BLOCK`、`VISION_PROMPT_BLOCK` 的文本。
- [ ] topic_major 的生成、审核、渲染继续消费同一份 `minutes_auxiliary`。
- [ ] 辅助材料“只补事实、不新增/改名/重排议题”的规则与 column 完全一致。
- [ ] 不为 topic_major 新增独立的辅助材料解析、拼装、注入逻辑。

---

## 3. Step 1：定义 topic_major 契约与契约模型

### 3.1 新增生成契约

- [ ] 在 `domains/meeting/tasks/minutes/contracts.py` 新增：
  ```python
  MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
  ```
- [ ] 契约内容按第 0 节定稿落地。
- [ ] 在 `__all__` 中导出新契约。
- [ ] 不修改旧 `MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT`。

### 3.2 新增契约模型

> `models_generated.py` 是 codegen 生成文件，不要手改。建议在 `domains/meeting/models.py` 手写区新增模型，或单独新增手写模块。

- [ ] 新增模型（名字暂定 `TopicMajorMinutes`）：
  - 顶层字段：`headline: str`、`overview: str`、`topics: list[dict]`、`history_comparison: list[str]`。
  - 顶层严格字段校验：只允许这 4 个键。
  - `topics` 每项严格字段校验：只允许：
    - `topic_name`
    - `topic_summary`
    - `decisions`
    - `actions`
    - `risks`
    - `open_questions`
  - `topic_name` 必须是非空字符串。
  - 五个内容字段必须是字符串数组。
  - 空数组允许。
- [ ] 复用 `core.schema.validation` 的 `_exact_fields / _string / _string_list`，嵌套记录逐条校验。
- [ ] 不修改 `Minutes` 模型，不给 `Minutes` 加 `topics` 字段。
- [ ] 确认 `minutes_agent` 在 topic_major 下使用新模型校验，而不是 `Minutes.validate`。

### 3.3 契约/模型测试

- [ ] 合法样例通过校验。
- [ ] 顶层多键/少键被拒。
- [ ] 议题记录多键/少键被拒。
- [ ] 非字符串数组被拒。
- [ ] `topics` 为空数组时的行为明确（建议允许，但生成 prompt 要求 N:1）。
- [ ] 旧 `Minutes` 契约/模型测试保持通过。

---

## 4. Step 2：编写 topic_major 的草稿 / 审核 / 渲染 prompt

### 4.1 草稿 prompt

- [ ] 在 `domains/meeting/tasks/minutes/prompts.py` 新增：
  ```python
  MINUTES_TOPIC_MAJOR_GENERATION_PROMPT
  ```
- [ ] prompt 输入与 column_major 一致：
  - 【现场审定的有效议题清单】；
  - 各议题打标切片；
  - 开场/会末；
  - 可选辅助材料（keypoints / notes / vision）。
- [ ] prompt 明确要求：
  - N 个有效议题 → `topics` 恰好 N 条；
  - 顺序与清单一致，`topic_name` 逐字一致；
  - 不新增、不删除、不合并、不改名、不重排议题；
  - 每个议题内部按六个字段归位；
  - `topic_summary` 不写 `### 议题名`，不写全场概况，不写决策/行动/风险/未决；
  - 讨论/建议不得写成 `decisions`；
  - `actions` 必须交代责任人、交付物、时限；
  - `risks` 与 `open_questions` 保持区分；
  - 同一事实只出现一次，不跨议题重复；
  - 无内容字段写 `[]`；
  - 所有事实以打标转写为准，不得虚构。
- [ ] 明确跨议题/会末定调处理规则：
  - 归入最相关议题；
  - 不新增“全场”议题；
  - 不在 `overview` 里写行动/风险清单。
- [ ] 复用现有辅助材料规则：
  - `AGENDA_AUX_PROMPT_BLOCK`；
  - `KEYPOINTS_PROMPT_BLOCK / NOTES_PROMPT_BLOCK / VISION_PROMPT_BLOCK`。
- [ ] 英文模式：本阶段只做中文；英文模板暂不转 topic_major。
- [ ] 动态拼接完全复用 column：
  - `_pack_minutes_auxiliary(keypoints, notes, vision_info)` → `line_extra["minutes_auxiliary"]`；
  - `MinutesGenerationAgent` 继续按 shared_context 中的标签检测 `【用户核心关键点】/【用户划线原话与笔记】/【视觉信息参考(OCR)】`；
  - 命中后追加同一套 `KEYPOINTS_PROMPT_BLOCK / NOTES_PROMPT_BLOCK / VISION_PROMPT_BLOCK`；
  - agenda 模式继续追加同一个 `AGENDA_AUX_PROMPT_BLOCK`；
  - 不新增 topic 专用辅助材料 prompt 块或检测逻辑。

#### 4.1.1 草稿 prompt 正文（优化版）

说明：参考 column 的 `MINUTES_AGENDA_GENERATION_PROMPT`，只保留字段语义与真实性底线；JSON 结构由 `MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT` 提供，不在 prompt 中重复。

```text
你是「会议纪要草稿 Agent」（议题主序模式）。

上下文中的会议素材已按现场审定的议程完成结构化整理，包含【现场审定的有效议题清单】、【会议开场背景与主线脉络】、各【议题 XX：议题全称】现场研讨记录以及【会末收尾与全场定调】。

若上下文同时出现【用户核心关键点】、【用户划线原话与笔记】或【视觉信息参考(OCR)】，这些是辅助材料，按下方「辅助材料使用规约」使用。

以打标转写与【现场审定的有效议题清单】为议程骨架与事实归属的唯一底座；辅助材料仅补充事实、参数、原话与数据。

只输出结构化 JSON 数据。

---

## 一、核心输出字段提炼与格式规约

### 1. headline（客观总结标题）

- 概括会议核心业务主题，8–18 字，具备严谨公文标题风格；直接陈述核心业务事项与定调结论。

### 2. overview（全场概况）

- 单段连贯文字，约 250–350 字，客观概括全场会议背景、核心主线推进态势与最关键的全局定调决议。
- 不逐议题展开，不列行动/风险清单，不写跨议题事项明细。

### 3. topics（议题主序记录）

- 每个有效议题一条记录，N 个有效议题必须输出 N 条，顺序与【现场审定的有效议题清单】一致。
- 每条记录固定包含：
  - **topic_name**：议题全称，必须与清单逐字一致；不得改名、合并、拆分、重排。
  - **topic_summary**：本议题正文/研讨/进展/内容要点，数组；写方案、事实、参数、指标与阶段结论；不写议题标题、不写全场概况，不写 decisions/actions/risks/open_questions 的内容。
  - **decisions**：本议题已拍板的最终决议/结论/定调，数组；讨论、建议、倾向、待定不得写入；无则 []。
  - **actions**：本议题的后续行动/落实安排，数组；写清责任人（或团队）、具体任务、交付物/验收标准、时限；无则 []。
  - **risks**：本议题的风险/卡点/阻塞/外部依赖，数组；写清风险现象、影响面、受阻环节、跟进人（原文有则写）；无则 []。
  - **open_questions**：本议题的未决/待确认/遗留问题，数组；写清待确认事项、协同对象、预期结果；无则 []。
- 每个有效议题都必须保留一条记录，即使部分字段为空。
- 不得新增“全场”“会末”等合成议题。

### 4. history_comparison

- 统一输出空列表 []。

---

## 二、真实性底线

1. 所有人名、决策、议题归属以打标转写为准；研讨探讨与拍板定调严格区分；辅助材料仅补充事实、参数与原话，有据才写，忠实于原始事实。
2. 会末收尾、全场定调、跨议题事项：归入最相关议题；确实无法归属时，只把最重要的结论写入 overview，不新增议题、不列清单。
3. 字段边界：topic_summary 只写事实/方案/进展；decisions 只写已拍板；actions 只写后续动作；risks 只写风险/卡点；open_questions 只写未决/待确认；同一事实只出现一次，不得跨议题串写。
4. 无内容字段写 []，不得用“未提及/待补充/暂无”套话填充；六个字段必须全部输出，不得省略键。
```

#### 4.1.2 上下文尾部执行准绳（草案）

```text
【议题主序草稿生成执行准绳】：
1. 顶层只输出 headline / overview / topics / history_comparison；
2. topics 必须与【现场审定的有效议题清单】1:1，顺序、标题逐字一致；
3. 每个议题内部固定六个键：
   topic_name / topic_summary / decisions / actions / risks / open_questions；
4. topic_summary 不写议题标题、不写全场概况、不写决策/行动/风险/未决；
5. decisions 只写已拍板；actions 交代责任人/交付物/时限；risks 与 open_questions 严格区分；
6. 无内容写 []；不得跨议题串写；不得新增/删除/改名/重排议题。
```

### 4.2 审核 prompt

- [ ] 复用现有审核契约/模型：
  - `MinutesSupervisorContract`；
  - `MinutesSupervisorReview`；
  - 审核产物仍是 `decision / feedback / checks`。
- [ ] 在 `build_minutes_supervisor_prompt(...)` 增加 layout 维度，新增：
  ```python
  _TOPIC_MAJOR_SUPERVISOR_SCOPE
  ```
- [ ] 审核重点：
  - 有效议题覆盖是否完整；
  - 议题顺序、标题是否与清单一致；
  - 每个议题的 `topic_summary / decisions / actions / risks / open_questions` 是否有原文依据；
  - 是否跨议题串写；
  - 是否把讨论/建议写成 `decisions`；
  - `actions` 是否有责任人和时限；
  - `risks` 与 `open_questions` 是否混淆；
  - 是否把全局风险/行动硬塞进某个议题；
  - 空字段是否合理；
  - 是否虚构人名、数字、拍板。
- [ ] 审核上下文：
  - 保留【现场审定的有效议题清单】；
  - 送审稿包含 `topics` 数组；
  - 不要沿用 column_major 的 `_SUPERVISOR_CARRY_DROP` 逻辑剔除议题内字段。
- [ ] 辅助材料审查完全复用 column：
  - 输入含对应标签时，继续追加 `_SUPERVISOR_AUX_NOTES / _SUPERVISOR_AUX_KEYPOINTS / _SUPERVISOR_AUX_VISION` 审查块；
  - 不新增 topic 专用辅助材料审查规则；
  - 辅助材料仍然只能补事实，不得新增/删除/改名/重排议题。

#### 4.2.1 简化版审核 prompt 正文（草案）

说明：基底、辅助材料审查、决策块复用现有审核 prompt；下面只展示 topic_major 的简化 scope 及完整默认形态。

```text
你是会议纪要质量审核专家。依据全局监督标准和以下领域规则审核送审稿。

## 领域审核规则：纪要生成

### 本轮送审范围
只审送审稿中实际出现的内容；未出现的内容不判缺失，也不发表意见。

### 严重缺陷
只有以下情况才判 reject：
1. 关键事实、数字、归属或方向与原文相反；
2. 凭空捏造原文没有的人名、数字或拍板；
3. 把讨论/建议写成已拍板决议。

### Findings
每个检查项只列 1~3 条严重缺陷，单条不超过 100 字；无严重缺陷给 []。

### 议题主序模式审查范围
- topics 必须覆盖本轮有效议题，顺序、标题与清单一致；不得新增、删除、合并、改名、重排。
- 每个议题的 topic_summary / decisions / actions / risks / open_questions 必须能在打标原文中找到依据。
- topic_summary 只写本议题正文，不得跨议题串写，不得混入 decisions/actions/risks/open_questions。
- decisions 只认已拍板；讨论/建议/待定不得写成 decisions。
- actions 必须有责任人/交付物/时限；risks 与 open_questions 必须区分。
- 空数组属于规范；不得要求补全无依据内容。

### 辅助材料与议程骨架
- 辅助材料不得成为新增、删除、改名、重排议题或改变议题归属的依据；
- 议程骨架违规优先 revise；返工点具体到议题和字段。

### 标题一致性口径
- 忽略大小写、空白、全半角标点、连字符差异；标题序号不参与比对；
- 仅语义改写/意译/替换才算改名；英文标题保留原文。

### 决策
- 首选 approve；拿不准就选它；无严重缺陷必须 approve。
- 命中上述严重缺陷 → reject。
- 以用户消息表头给出的可选动作为准。
```

审核输出契约复用现有版本，保持不变：

```json
{
  "decision": "approve | revise | reject",
  "feedback": [],
  "facts_check": {"status": "pass", "findings": []},
  "perspective_check": {"status": "pass", "findings": []},
  "consistency_check": {"status": "pass", "findings": []}
}
```

### 4.3 渲染 prompt

- [ ] 在 `prompts.py` 新增：
  ```python
  MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT
  ```
- [ ] 仍使用 `build_template_render_prompt(...)` 生成基础规则。
- [ ] 栏目映射：
  - 概括/概况栏 ← `overview`；
  - 议题容器栏 ← `topics`，逐个议题输出 `### 序号. topic_name`；
  - 议题内子栏按模板声明的名称/顺序做语义映射：
    - 工作进展 / 进展 / 内容 / 方案 / 核心要点 / 方案陈述 / 进度追踪 → `topic_summary`
    - 结论 / 决议 / 定调 / 共识 / 最终决议 → `decisions`
    - 落实安排 / 行动 / 待办 / 分工 / 后续计划 / 改进措施 / 行动建议 → `actions`
    - 风险 / 卡点 / 阻塞 / 隐患 / 外部依赖 / 风险预警 → `risks`
    - 未决 / 待确认 / 遗留 / 疑问 / 未决后续 → `open_questions`
- [ ] 渲染规则：
  - 按模板在议题容器内声明的子栏顺序输出；
  - 无内容子栏整块隐去，不保留空标签；
  - 不得把 `actions` / `risks` 再作为顶层栏目输出；
  - 不得跨议题合并内容；
  - 不得改写 `topic_name`、不得重排议题；
  - 不使用模板外栏目。
- [ ] 模板 `<!-- requirement -->` 仍通过 `route_template` 注入；layout 元数据必须已被剥离，不能出现在渲染 prompt/终稿。
- [ ] 渲染上下文只提供：
  - 议题模式标记；
  - 有效议题清单；
  - 已审核草稿（含 topics）；
  - 篇幅预算；
  - 必要辅助材料。
- [ ] 不注入会议理解、画像、视角模型（与现有 agenda_objective 一致）。
- [ ] 辅助材料注入与 column 完全一致：
  - 继续使用 `line_extra["minutes_auxiliary"]`；
  - 继续追加到渲染上下文的 `extra`；
  - 不新增 topic 专用辅助材料拼接或模板注入逻辑。
- [ ] 渲染后空子栏清理：
  - `empty_section_issues` 只检查 `#` 标题，不检查 `**工作进展**` 等加粗标签；
  - 增加确定性清理：加粗标签后无有效内容时整块删除；
  - 不得误删有内容的子栏；
  - 与 prompt 的“无内容子栏整块隐去”形成双保险。

#### 4.3.1 渲染 prompt 正文（优化版）

说明：参考 column 的 `MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`，只写 topic_major 的差异项；通用规则由 `build_template_render_prompt(...)` 统一提供，不在本 prompt 中重复。

```python
MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="会议纪要渲染器",
    source="已审核草稿（结构化事实基准）",
    source_rule=(
        "**以已审核草稿为事实基准，严格遵循模板栏目规约与公文层级标准完成排版**：\n"
        "【栏目语义自适应映射】：\n"
        "1. 概括总述类栏目：映射草稿 overview，以连贯单段呈现；不得把议题内容塞入本栏；栏目标题必须与模板方括号内文字完全一致，不得用会议标题或草稿 headline 替换；\n"
        "2. 议题容器类栏目：映射草稿 topics，按数组顺序逐个议题输出；每个议题顶格以「### 序号. topic_name」开始；议题内部按模板在该栏占位说明中声明/列出的子栏顺序输出；议题容器以模板 layout 元数据 container 指定的栏目为准，未指定时取占位说明中声明“以有效议题清单为主线”的栏目；\n"
        "3. 议题内子栏按语义映射：工作进展/进展/内容/方案/核心要点/方案陈述/进度追踪 → topic_summary；结论/决议/定调/共识/最终决议 → decisions；落实安排/行动/待办/分工/后续计划/改进措施/行动建议 → actions；风险/卡点/阻塞/隐患/外部依赖/风险预警 → risks；未决/待确认/遗留/疑问/未决后续 → open_questions；子栏名同时包含多个语义时（如“未决风险”）按语义合并输出（risks + open_questions）；\n"
        "4. 议题内子栏无内容时整块隐去，不保留空标签；不得把 actions / risks 再作为顶层栏目输出；同一事实只出现一次；\n"
        "5. 不得改写 topic_name、不得重排议题、不得跨议题合并内容；\n"
        "6. 若模板没有总述/概况栏：overview 作为议题容器开篇总述；\n"
        "7. 不强行塞入不相关内容，不自创模板外栏目。"
    ),
    empty_rule=(
        "某栏在草稿中对该栏主题无依据且模板允许省略时直接保持空内容自适应隐去；模板没约定时优先自适应隐去，确需占位时按模板指定词填写，不使用外部常识补全。"
    ),
    extra_rules=[
        "模板若含写作要求，按该要求客观准确填写",
    ],
)
```

与 column 的关系：

- `source_rule` 只写 topic_major 的栏目差异；
- `empty_rule` 与 column 完全一致；
- `extra_rules` 只保留“模板写作要求”一条；
- 公共规则（标题层级、事实保真、篇幅优先级、冲突裁决、Markdown 输出、稳定性等）由 `build_template_render_prompt` 自动补齐，不重复书写。

### 4.4 prompt 路由

- [ ] `prompt_map.py` 增加 layout 选择：
  - `minutes_prompt_set(view, layout)`
  - `render_template_prompt(view, layout)`
  - `prompt_label(view, layout)`，日志可用 `agenda_topic`
- [ ] 选择表：

| view | layout | generation | supervisor | render |
|---|---|---|---|---|
| `agenda_objective` | `column_major` | 旧 `MINUTES_AGENDA_GENERATION_PROMPT` | 旧 agenda supervisor | 旧 agenda render |
| `agenda_objective` | `topic_major` | 新 topic prompt | 新 topic scope | 新 topic render |
| 其它 view | 不参与 layout | 现有逻辑 | 现有逻辑 | 现有逻辑 |

- [ ] 默认 `layout = column_major`，未知值回退 `column_major`。

#### 4.4.1 动态拼接一致性（重要）

topic_major 不另写一套动态拼接逻辑；除“选哪份 prompt / 契约 / 模型”外，其余全部复用 column：

| 拼接项 | column_major | topic_major |
|---|---|---|
| 草稿 system prompt | 基础 prompt + 辅助材料块 | 新基础 prompt + **同一套**辅助材料块 |
| 辅助材料检测 | 按 shared_context 标签 | 同一检测逻辑 |
| agenda 辅助边界 | `AGENDA_AUX_PROMPT_BLOCK` | 同 |
| 英文包装 | 同一 language wrapper | 同 |
| 篇幅预算 | `_length_budget_line` | 同 |
| 审核基底 / 辅助 / 历史 / 决策块 | `build_minutes_supervisor_prompt` | 同，只换 scope |
| 渲染 prompt | `build_template_render_prompt` + `route_template` + `PLACEHOLDER_RULES` | 同，只换 `source_rule` |
| 模板 requirement 注入 | `route_template` | 同 |
| 记忆注入 | `inject_line_extra` | 同 |

- [ ] 不为 topic_major 新增独立的辅助材料解析、拼装、英文包装、篇幅预算、requirement 注入逻辑。
- [ ] topic_major 与 column_major 的差异只允许出现在：
  - 草稿 prompt 的字段语义；
  - 输出契约 / 模型；
  - 审核 scope；
  - 渲染 source_rule；
  - 兜底 / 记忆适配。

---

## 5. Step 3：团队例会模板（已完成，不再作为待办）

> 已完成：`resources/agenda_templates/zh/team_meeting.md` 已改为 topic_major 两栏结构。
> 本节只记录最终形态与解析验收，不包含待办动作。

### 5.1 最终形态

```markdown
# 团队例会

<!-- layout
mode: topic_major
container: 议题梳理
-->

<!-- requirement
以现场审定的有效议题为主线，逐个议题展开；每个议题内部按工作进展、落实安排、未决风险三块陈述；聚焦事实、责任人与量化指标，篇幅充分饱满。
-->

## [例会概况]
[单段概括，约 250–350 字：交代参会成员或部门、开会背景、涵盖的审定议题业务主线、整体推进态势以及全局关键结论；聚焦主线与宏观态势，分项进展与执行细节留归议题梳理栏展开。]

## [议题梳理]
[以现场审定的有效议题清单为主线逐个议题展开：每个议题以「### 一. 议题全称」顶格列出，议题内部依次输出「**工作进展**」「**落实安排**」「**未决风险**」三个固定子块，子块内用「- 要点名称: 具体陈述」展开；无内容子块整块隐去；不同议题内容不得混写；不得把行动/风险再作为顶层栏目输出。]
```

### 5.2 解析验收结果

- [x] `detect_template_kind` → `placeholder`。
- [x] `parse_placeholder_template` 识别两个标题占位：`例会概况`、`议题梳理`。
- [x] `议题梳理` 的占位说明包含三个子块名称。
- [x] `plan_placeholder_fill`：`scalars = 2`，`row_templates = 0`。
- [x] 旧的三个顶级栏目已删除。
- [x] 中文模板已完成；`resources/agenda_templates/en/team_meeting.md` 未动。
- [x] layout 元数据已写入模板；代码尚未解析/剥离（见 6.1）。

### 5.3 模板编写规则（已确认）

- [x] `[议题梳理]` 的占位说明必须**单行**：
  - `parse_placeholder_template` / `iter_placeholders` 按行扫描；
  - 多行 `[...]` 不会被识别成字段，会退化成固定文案。
- [x] 议题内子栏使用独立加粗行：
  ```markdown
  **工作进展**
  **落实安排**
  **未决风险**
  ```
- [x] 子栏为空时整块隐去，不保留空标签。
- [ ] 如果后续改成 `#### 工作进展`，必须同步渲染 prompt 与 `empty_section_issues` 门禁（本阶段不做）。

### 5.4 D1：原地改造（已定）

- [x] `team_meeting.md` 已原地改为 topic_major；不新增变体。
- [x] 布局由模板 layout 元数据判断，不做请求级或环境级布局参数。
- [x] 其他 19 个模板的 column 逻辑与输出不受影响。
- [x] 回滚方式：移除/修改 `team_meeting.md` 的 layout 元数据，或恢复模板正文。
- [ ] 文档记录：`team_meeting` 的 column 版本不再存在，选中该模板即走 topic_major。
- [ ] auto 说明：`MINUTES_TEMPLATE_AUTO` 开启且分类器选中 `team_meeting` 时，会按 layout 走 topic；默认 `MINUTES_TEMPLATE_AUTO=off`。

---

## 6. Step 4：分支逻辑

### 6.1 模板 layout 元数据解析与剥离

> 本节是必须落地的逻辑：不仅要解析 layout，还要把 `<!-- layout ... -->` 从模板正文中剥离。

- [ ] 在 `core/templates/router/_base.py` 新增 `split_template_layout(text)`（或等价 helper）：
  - 识别块式：
    ```markdown
    <!-- layout
    mode: topic_major
    container: 议题梳理
    -->
    ```
  - 识别行内式（可选兼容）：
    ```markdown
    <!-- layout: topic_major -->
    ```
  - 返回：`(clean_template_text, layout_mode, container_name)`。
  - 默认：无 layout → `column_major`，`container_name` 为空。
  - 兼容值：`column_major` / `topic_major`；如支持 `column` / `topic` 简写，内部归一化。
  - 非法 mode：回退 `column_major` 并打 warning，不抛异常。
  - 重复 layout：以第一条识别到的为准，全部剥离，并打 warning。
- [ ] 剥离范围（必须全部覆盖）：
  - `detect_template_kind` 之前；
  - `parse_placeholder_template` / `plan_placeholder_fill` 之前；
  - `route_template` / `build_template_render_prompt` 的模板原文之前；
  - 最终渲染正文之前。
- [ ] 与 `split_template_meta` 的关系：
  - `split_template_meta` 只匹配并剥离 `<!-- requirement ... -->`，**不会**处理 `<!-- layout ... -->`；
  - 需要组合调用：分别解析/剥离 layout 与 requirement；
  - requirement 继续作为 `【模板写作要求】` 注入渲染 prompt；
  - layout 只写入 state，不进入 prompt/终稿。
- [ ] 调用时机：
  - 显式模板：初始模板加载/物化时解析；
  - 自动分类：`select_minutes_template` 替换模板后解析；
  - 自然语言模板：`maybe_compile_natural_template` **之前**解析并保存 layout，编译只处理 clean text；
  - 回退 `general_minutes`：无 layout → `column_major`。
- [ ] state 记录：
  - 写入 `line_layouts["minutes"]`；
  - 保存 `container_name`（如 `line_layouts` 旁路或 `line_extra` / 专用 state 字段）；
  - 不要依赖模板正文再次解析（正文已被剥离）；
  - `template_id` / `template_source` 保留。
- [ ] 防御与测试：
  - layout 注释若残留在模板正文，会被 `parse_placeholder_template` 当固定文案，可能进入渲染 prompt/终稿；
  - 增加断言/测试：clean text 不包含 `<!-- layout`；
  - 测试块式、行内式、无 layout、非法 mode、重复 layout；
  - 测试自然语言模板编译后 layout 不丢；
  - 测试旧模板 `detect_template_kind` / `parse_placeholder_template` 结果不变。
- [ ] `container` 缺失策略：
  - 两栏模板：可由渲染器按“以有效议题清单为主线”的占位说明推断；
  - 多栏模板：打 warning，建议模板显式写 `container`；
  - team_meeting 已显式写 `container: 议题梳理`。
- [ ] `app/config._parse_template_md` 如需返回 layout，可扩展注册表字段；本阶段最小实现可以只在 minutes 模板物化时解析。

### 6.2 layout 裁决

- [ ] 在 `MeetingState` 中显式新增：
  ```python
  line_layouts: dict[str, str]
  ```
  LangGraph 只传 TypedDict 声明过的 key，未声明会被静默丢弃。
- [ ] 裁决时机：模板选择/物化之后、生成 agent 之前。
- [ ] 裁决来源：
  - 显式模板：解析初始模板文本；
  - 自动分类：解析 `select_minutes_template` 物化后的模板；
  - 默认模板：解析 `general_minutes`（通常无 layout → column_major）；
  - 分类/物化失败回退：按回退模板的 layout；无 layout → column_major。
- [ ] 建议扩展 `minutes_view` 节点，或在 `template_classify` 后新增 `minutes_layout` 节点：
  - 写入 `line_views["minutes"]`；
  - 写入 `line_layouts["minutes"]`；
  - 生成、审核、渲染统一从 state 读取。

### 6.3 分支判断

```text
if view != agenda_objective:
    → 现有 objective / personal / role_template 路径，layout 不参与

if view == agenda_objective:
    layout = line_layouts["minutes"] or column_major

    if layout == column_major:
        → 现有 MINUTES_AGENDA_* 契约 / prompt / 模型 / 渲染

    if layout == topic_major:
        → 新 topic_major 契约 / prompt / 模型 / 渲染
```

- [ ] 只有 `view == agenda_objective && layout == topic_major` 才进入新路径。
- [ ] 其余所有组合保持现有行为。

### 6.4 agent / supervisor / render 注入

- [ ] `MinutesGenerationAgent.run` 增加 `layout` 参数：
  - `topic_major`：新 prompt + 新契约 + `TopicMajorMinutes`；
  - `column_major`：现有逻辑。
- [ ] `MinutesGenerationSupervisor.review` 增加 `layout` 参数：
  - 审核 scope 按 layout 选择；
  - 审核契约/模型复用。
- [ ] `MinutesGenerationRender._prompt_and_user / run / stream` 增加 `layout` 参数：
  - 选择 topic_major 渲染 prompt；
  - 传递到 `build_render_prompt`。
- [ ] `core/graph/nodes.py`：
  - `_make_agent_node` 通过签名注入 `layout`；
  - `_make_supervisor_node` 通过签名注入 `layout`；
  - `produce_line` / `_render_run` 传递 `layout`。
- [ ] `core/runtime/render.py`：
  - 增加 `_render_layout(state, line_name)`；
  - 渲染调用按签名传入 `layout`。
- [ ] `domains/meeting/orchestrator.py`：
  - `_minutes_view` 或 layout 节点写 `line_layouts`；
  - `_line_shared_context`、`_supervisor_context`、`_render_context` 按 layout 分支。

### 6.5 上下文拼装的关键分叉点

- [ ] `_line_shared_context`：
  - column_major：保持现有“审定议题草稿生成执行准绳”和 7 字段 JSON 契约；
  - topic_major：不要追加旧的 `### 一.` 执行准绳；改为 topic_major 专用执行准绳，或直接依赖新系统 prompt；
  - topic_major 不要追加旧的 7 字段 JSON 输出契约。
- [ ] `_supervisor_context`：
  - column_major：保持 `_SUPERVISOR_CARRY_DROP`；
  - topic_major：不要剔除 `topics` 内的字段；送审稿要包含完整议题记录。
- [ ] `_render_context`：
  - column_major：现有逻辑；
  - topic_major：确保草稿以 `headline / overview / topics[] / history_comparison` 传入，且带有效议题清单、篇幅预算。
- [ ] `minutes_auxiliary` 注入：
  - column_major / topic_major 完全一致；
  - 继续使用同一个 `line_extra["minutes_auxiliary"]`；
  - 不改变拼接位置、格式与内容；
  - topic_major 只换草稿契约，不换辅助材料块。
- [ ] `is_agenda_enhanced_mode`：
  - 确认 topic_major 不会误走 `enforce_minutes_draft` 的旧 7 字段补键逻辑。
  - 如需保留“议题模式”标记，建议新增 topic_major 专用标记或显式跳过旧 enforcement。
- [ ] Supervisor 快速短路 / 规则门禁：
  - column_major 保持现状；
  - topic_major 试点阶段禁用 `_supervisor_fast_path_chars` 短路和 `quick_facts_guardrail`，或新增 topic-aware guardrail；
  - 原因：topic 草稿没有旧 7 字段，`quick_facts_guardrail` 可能误判；短会 bypass 会直接跳过审核；
  - 确保 degraded 草稿仍然走审核/返工，不被短路。

### 6.6 草稿硬校验 / 兜底 / 记忆 / 报告

- [ ] `enforce_minutes_draft`：
  - column_major 分支保持不变；
  - topic_major 新增独立校验（或适配成旧 7 字段后再走旧逻辑，二选一，推荐独立校验）。
- [ ] `MinutesFallbackRules`：
  - column_major 保持不变；
  - topic_major 新增兜底：至少输出 `overview + topics` 的确定性 Markdown，不能因缺少旧 7 字段而崩。
- [ ] `render_fallback_minutes`：
  - column_major 保持不变；
  - topic_major 新增按 topics 迭代的兜底渲染，或先适配成旧 7 字段。
- [ ] 程序化议题覆盖校验：
  - 生成后对比 `valid_agendas` 与草稿 `topics`：
    - 数量一致；
    - `topic_name` 一致（按标题一致性口径规范化后比较）；
    - 顺序一致。
  - 不一致时记录 warning，并触发 supervisor revise 或降级；
  - 不依赖模型自觉，也不只依赖 LLM 审核。
- [ ] Memory 落库判断：
  - `_draft_has_fact` 目前只认旧 7 字段；topic 草稿有 `overview / topics`，需要加入识别，否则可能被判“无事实”而不入库；
  - `_draft_agenda_titles` 需要优先从 `topics[].topic_name` 取标题；
  - `extract_meeting_fact_from_minutes_draft` 增加 topic 分支/适配器；
  - column_major 分支保持不变。
- [ ] 记忆提取：
  - `extract_meeting_fact_from_minutes_draft` 目前按旧 7 字段；
  - 增加 topic_major 适配器：
    | topic_major | 旧字段 |
    |---|---|
    | `decisions` | `key_decisions` |
    | `actions` | `personally_relevant_points` |
    | `risks` | `risks_and_blockers` |
    | `open_questions` | `unresolved_questions` |
    | `topic_summary` | `executive_summary[1:]` 的单议题正文 |
- [ ] `MinutesReport` / API：
  - 不改结构；
  - 验证 `personalized_minutes` 正常返回。

### 6.7 日志与可观测性

- [ ] 日志中记录：
  - `view`
  - `layout`
  - `template_id`
  - 生成/审核/渲染使用的 prompt 分支
- [ ] `prompt_label` 增加 `agenda_topic`，便于和 `agenda` 区分。
- [ ] 记录 topic 数量与议题标题，便于排查 N:1 问题。

---

## 7. 不影响 column_major 的保障

- [ ] 所有新代码路径都受 `layout == topic_major` 门控。
- [ ] 默认 layout 必须是 `column_major`。
- [ ] 无 layout 元数据的模板解析结果与现在完全一致。
- [ ] 不修改 `MINUTES_AGENDA_*` 常量、旧契约、旧 prompt、旧 fallback。
- [ ] 不修改 `Minutes` 模型。
- [ ] 不修改 `agenda_minutes` 任务线。
- [ ] 不修改 objective / personal / role_template 的 prompt 与模型。
- [ ] 运行 column_major 回归测试：
  - `tests/unit/meeting/test_minutes_agenda_integration.py`
  - `tests/unit/meeting/test_minutes_prompt_map.py`
  - `tests/unit/meeting/test_minutes_template_separation.py`
  - `tests/unit/meeting/test_minutes_view_*`
  - `tests/unit/meeting/test_multi_source_minutes.py`
  - `tests/unit/core/templates/*` 相关模板解析测试
- [ ] 新增 topic_major 专项测试后，column 测试必须全绿。

### D2：不加开关（已定）

- [x] 不加 `MINUTES_TOPIC_MAJOR` 环境开关。
- [x] 模板 layout 元数据就是唯一开关。
- [x] 不新增请求级 `layout` 参数。
- [x] 回滚方式：移除/修改 `team_meeting.md` 的 layout 元数据，或恢复模板正文。

### 自动分类说明

- [x] `team_meeting` 是 agenda 候选之一；`MINUTES_TEMPLATE_AUTO` 开启且选中它时，会按模板 layout 走 topic_major。
- [x] 默认 `MINUTES_TEMPLATE_AUTO=off`，行为不变。
- [ ] 如果试点期间不希望 auto 用户被动切换，保持 auto off 即可；无需新增开关。

---

## 8. 文件改动清单

| 文件 | 改动 | 对 column 的影响 |
|---|---|---|
| `resources/agenda_templates/zh/team_meeting.md` | 已完成：layout 元数据 + 例会概况 + 议题梳理两栏；解析验证通过 | 仅该模板 |
| `app/schemas.py` | 不改 `texts` key 与校验 | 无 |
| `app/tasks.py` | 不改 `_pack_minutes_auxiliary`；topic 复用同一份 `minutes_auxiliary` | 无 |
| `domains/meeting/tasks/minutes/contracts.py` | 新增 topic_major 契约 | 无 |
| `domains/meeting/models.py` | 新增 `TopicMajorMinutes`；`MeetingState.line_layouts` | 无 |
| `domains/meeting/tasks/minutes/prompts.py` | 新增 topic 生成/审核 scope/渲染 prompt | 无 |
| `domains/meeting/tasks/minutes/prompt_map.py` | 按 `(view, layout)` 选 prompt | column 路径不变 |
| `domains/meeting/tasks/minutes/steps/minutes_agent.py` | layout 分支、新模型、新契约 | column 路径不变 |
| `domains/meeting/tasks/minutes/steps/minutes_supervisor.py` | layout 分支、scope 选择 | column 路径不变 |
| `domains/meeting/tasks/minutes/steps/minutes_render.py` | layout 分支、渲染 prompt 选择、fallback | column 路径不变 |
| `domains/meeting/orchestrator.py` | layout 裁决；上下文/执行准绳/契约/送审稿/drop keys 分支 | column 路径不变 |
| `domains/meeting/views.py` | 可放 layout 常量/辅助函数（可选） | 无 |
| `core/graph/nodes.py` | agent/supervisor/render 注入 `layout` | column 路径不变 |
| `core/runtime/render.py` | 传递 `layout` | column 路径不变 |
| `core/templates/router/_base.py` | layout 元数据解析/剥离 | 无 layout 的模板不变 |
| `core/execution/hard_execution.py` | topic_major 校验/跳过旧 enforcement | column 分支不变 |
| `domains/meeting/memory/extract.py` / `runtime.py` | topic_major 适配器 | column 路径不变 |
| `tests/*` | topic_major 新测试 + column 回归 | 保证 column 不退化 |

---

## 9. 验收标准

### 9.1 team_meeting 试点

- [ ] 传入有效议程 + `team_meeting` 模板，命中 `view=agenda_objective, layout=topic_major`。
- [ ] 生成草稿结构为：
  - `headline`
  - `overview`
  - `topics[]`（N 条，标题/顺序与有效议题清单一致）
  - `history_comparison`
- [ ] 每条议题记录包含：
  - `topic_name`
  - `topic_summary`
  - `decisions`
  - `actions`
  - `risks`
  - `open_questions`
- [ ] 渲染输出为：
  - `## 例会概况`
  - `## 议题梳理`
  - 每个议题 `### 一. 议题名` 下有 `**工作进展**`、`**落实安排**`、`**未决风险**` 三块。
- [ ] `工作进展` ← `topic_summary`
- [ ] `落实安排` ← `actions`
- [ ] `未决风险` ← `risks` + `open_questions`
- [ ] 空子栏不出现。
- [ ] 不同议题内容不混写。
- [ ] 议题标题、顺序与清单一致。
- [ ] 无虚构人名/数字/拍板。

### 9.2 column_major 回归

- [ ] `general_minutes` 走旧逻辑，输出与改造前一致。
- [ ] 其他未加 layout 的议程模板走旧逻辑。
- [ ] 无议程的 minutes 走旧逻辑。
- [ ] objective / personal / role_template 不受影响。
- [ ] `agenda_minutes` 独立任务线不受影响。
- [ ] 审核、返工、fallback、流式输出、记忆持久化均正常。

### 9.3 异常与降级

- [ ] layout 非法值 → 回退 column_major + warning。
- [ ] 模板元数据解析失败 → 回退 column_major，不阻断主流程。
- [ ] topic_major 生成失败 → fallback 可产出可读 Markdown，不崩溃。
- [ ] 审核不可用 → 保守 approve 逻辑仍生效。
- [ ] 无模板 → 现有确定性兜底仍生效。

### 9.4 测试矩阵（按风险）

| 风险 | 必测项 | 期望 |
|---|---|---|
| layout 解析 | 块式 / 行内式 / 无 layout / 非法 mode / 重复 layout | 正确归一化，非法回退 column_major |
| layout 剥离 | 解析后的 clean text | 不包含 `<!-- layout`，不进入 prompt/终稿 |
| layout 编译 | 自然语言模板先解析后编译 | layout 不丢，编译只处理 clean text |
| 分支选择 | `agenda_objective + column_major` / `+ topic_major` / 非 agenda view | 只有 topic_major 走新路径 |
| 契约/模型 | 顶层 4 键、议题记录 6 键、字符串数组 | 严格校验，旧 `Minutes` 不受影响 |
| 草稿 agent | N 议题 → N 记录、标题/顺序、六字段边界 | 无 global 桶，无跨议题串写 |
| 议题覆盖校验 | 草稿 topics 与 valid_agendas 数量/标题/顺序不一致 | 触发 warning / revise / 降级 |
| 审核 | topic scope、快速短路/规则门禁 | topic 不被旧 guardrail 误判；column 审核不变 |
| 渲染 | 两栏 + 三子块、空子栏、无顶层 actions/risks | 输出符合模板，空子栏整块消失 |
| 渲染门禁 | `**工作进展**` 空标签、layout 注释残留 | 程序化清理，不误删有内容子栏 |
| 记忆 | topic 草稿落库、标题提取、actions/risks 映射 | 不被 `_draft_has_fact` 误判为空 |
| 兜底 | topic 生成失败、审核不可用 | fallback 可读，不崩溃 |
| 流式 | `run` / `stream` 两条渲染路径 | layout 正确传递 |
| 布局开关 | 模板有/无 layout | 无 layout → column_major；有 `topic_major` → topic；不依赖环境开关 |
| auto 分类 | `MINUTES_TEMPLATE_AUTO=off/on` 且选中 team_meeting | off 行为不变；on 时按模板 layout 走 topic |
| column 回归 | general_minutes、其余 19 模板、个人/职业/无议程 | 输出与改造前一致 |

---

## 10. 实施顺序（摘要，详见「执行路线（总览）」）

> 团队例会模板改造已完成，不再列入实施步骤。

1. **Phase 0：确认 D1–D6 已定**
   - 原地改 `team_meeting.md`、不加环境开关、layout 值、契约、texts、子栏样式。
2. **Phase 1：layout 解析/剥离骨架**
   - `split_template_layout`；
   - 剥离、state、默认回退、测试；
   - 不改任何行为，column 回归全绿。
3. **Phase 2：契约与模型**
   - `MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT`；
   - `TopicMajorMinutes` 模型；
   - 单测。
4. **Phase 3：prompt 与路由**
   - 草稿/审核/渲染 prompt；
   - `(view, layout)` 选择函数；
   - 单测。
5. **Phase 4：草稿 agent 接线**
   - layout 分支、新模型/契约；
   - 辅助材料复用；
   - 程序化议题覆盖校验。
6. **Phase 5：审核接线**
   - topic scope；
   - 复用审核契约；
   - 禁用/适配快速短路与规则门禁。
7. **Phase 6：渲染接线**
   - topic render prompt / 上下文；
   - topic fallback；
   - 空子栏清理。
8. **Phase 7：上下文 / 记忆 / 报告**
   - red line / JSON 契约分支；
   - memory 落库判断与 topic 提取适配；
   - report 不变。
9. **Phase 8：试点**
   - 团队例会中文模板（原地改造）显式选择；
   - 端到端验证。
10. **Phase 9：回归与回滚**
    - column 全量测试；
    - 其余 19 模板零变化；
    - 移除/修改模板 layout 元数据可回滚。

---

## 11. 待确认项

- [ ] 跨议题 / 会末定调事项：归入最相关议题；如果无法归属，是否允许新增合成“全场”记录，还是仅写入 `overview`，或者允许丢失。
- [ ] 团队例会模板是否展示 `decisions`：当前两栏模板没有“结论定调”子栏，建议先不展示；如果团队例会经常拍板，再加第四子栏 `**结论定调**`。
- [ ] 英文模板是否后续跟进；本阶段只做中文 team_meeting。
- [ ] `overview` 是否允许写“最重要的全局结论”一句话；建议允许，但不列全局行动/风险清单。
- [ ] 后续转换哪些模板：先 team_meeting，再 project_progress / decision_review / workshop_session。

### 已确认（不再作为待确认项）

- [x] **D1 模板形态**：原地改 `team_meeting.md`；布局通过模板 layout 元数据判断；不新增变体。
- [x] **D2 开关**：不加 `MINUTES_TOPIC_MAJOR`；模板 layout 元数据就是开关；回滚 = 移除/修改 layout 元数据。
- [x] **D6 子栏样式**：`**工作进展** / **落实安排** / **未决风险**` 仅针对团队例会模板；其他 topic 模板可声明自己的子栏。
- [x] `container`：team_meeting 使用 `container: 议题梳理`；两栏模板可选，多栏 topic_major 模板建议必填。
- [x] `texts` 输入：`transcript / keypoints / notes / vision_info` 与 column 完全一致；`actions_text` 不进入 minutes。
- [x] 动态拼接：辅助材料、英文包装、篇幅预算、审核基底/辅助/历史/决策块、渲染模板路由与 requirement 注入，全部复用 column 逻辑。
- [x] `history_comparison`：草稿固定 `[]`，由程序装配。
