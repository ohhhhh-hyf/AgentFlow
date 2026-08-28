# 会议领域 Prompt 与上下文优化指导文档

## 1. 背景与目标

当前 AgentFlow 后端已经完成从 CLI 调用到统一 HTTP 服务的改造，会议领域任务可以通过 `/api/v1/meeting/*` 接口稳定运行。下一阶段的重点不是新增接口，而是提升会议领域产出质量，并减少无效 token 消耗和任务运行时间。

会议领域重点优化对象：

- `minutes`：会议纪要
- `actions`：待办提取
- `risks`：风险提取
- `minutes_trace`：溯源纪要

总体目标：

- 减少无效 token：避免每个任务重复读取完整原文、完整会议理解、完整画像和完整视角模型。
- 缩短运行时间：让任务 Agent 少做重复理解，多做本任务的判断和整理。
- 提升内容质量：会议理解 Agent 提供更准的事实索引，各任务 Agent 聚焦自己的任务目标。
- 保持事实可靠：所有产出必须有会议原文或上游结构化字段支撑，禁止编造、扩写、主观推断。

## 2. 当前主要问题

### 2.1 会议理解 Agent 过重

当前会议理解 Agent 同时承担：

- 会议目的判断
- 会议场景判断
- 议题切分
- 决策提取
- 风险提取
- 未决问题提取
- 行动线索提取
- 风险线索提取
- 依赖关系提取
- 下游预检

这让会议理解层的 prompt 很长，输出字段也偏重。质量上有利于召回，但会带来两个问题：

- 单任务调用也要为其他任务字段付费。
- 下游任务拿到的信息太多，容易重复理解和重复筛选。

### 2.2 所有任务共享同一份大上下文

当前会议领域的共享上下文大致包含：

- 视角模式说明
- 用户画像完整 JSON
- 会议理解完整 JSON
- 用户视角模型完整 JSON
- 会议原文全文

这对多任务并行时比较稳，但对单任务接口来说非常浪费。例如：

- `actions` 主要需要行动线索、执行指令、依赖条件和证据句。
- `risks` 主要需要风险线索、依赖风险、强度证据和应对信息。
- `minutes` 需要会议概览、议题、决策、风险和未决问题，但不一定需要完整原文。
- `minutes_trace` 需要事实结构和可对齐证据，但不应被待办/风险的完整候选干扰。

### 2.3 上游与下游重复劳动

当前会议理解层已经提取了 `action_hints`、`risk_hints`、`decisions` 等字段，但下游任务仍然会读取完整原文和完整 topics，再重新做一遍事实发现。

更理想的方式是：

- 会议理解 Agent 负责高召回、低推断的事实候选。
- 任务 Agent 负责精筛、分类、字段补齐和表达。
- 渲染 Agent 只负责自然输出，不新增事实。

### 2.4 `topics.discussion` 容易变成压缩版原文

当前 `topics.discussion` 被要求保留事实、数字、日期、人名、承诺、整改、范围边界、对照数字等信息。这个字段一旦过长，会带来两层浪费：

- 它本身是对原文的重复压缩。
- 下游任务又会同时读取 discussion 和原文。

建议将 `topics.discussion` 改造成更短、更结构化的 `key_points` 或 `facts`。

### 2.5 Prompt 规则重复

会议理解、纪要、待办、风险、溯源纪要中反复出现类似规则：

- 不编造
- 原文锚定
- 保持原文顺序
- 不把讨论升级为决策
- 清除转写占位符
- 拿不准不提取

这些规则必须保留，但可以上移为统一纪律或压缩表达。各任务 prompt 应减少通用规则，保留本任务的专业规则。

## 3. 推荐总体架构

建议将会议领域改造成三层：

```text
会议原文
  ↓
会议理解 Agent
  输出短而准的事实索引
  ↓
任务上下文裁剪器
  minutes_pack / actions_pack / risks_pack / minutes_trace_pack
  ↓
任务 Agent
  基于专属上下文做专业判断
  ↓
Render
  只负责自然表达，不新增事实
```

核心原则：

- 会议理解层追求高召回，但输出要短。
- 任务层只消费自己的字段，不吃完整大上下文。
- 原文只作为必要证据，不默认全文传给所有任务。
- 各任务 Agent 不再重复做全局会议理解。

## 4. 会议理解 Agent 改造建议

### 4.1 新定位

会议理解 Agent 应从“全景纪要预生成器”调整为“事实索引器”。

它的目标不是写得完整漂亮，而是提取可被下游直接消费的短事实、候选线索和证据。

### 4.2 建议输出结构

建议目标结构如下：

```json
{
  "meeting_brief": "",
  "meeting_purpose": "",
  "scene": "通用",
  "topics": [
    {
      "title": "",
      "key_points": [],
      "conclusion": null,
      "participants": []
    }
  ],
  "decisions": [
    {
      "decision": "",
      "type": "decision",
      "owner": null,
      "timing": null,
      "condition": null,
      "topic": null,
      "evidence": ""
    }
  ],
  "action_hints": [
    {
      "action": "",
      "owner": null,
      "timing": null,
      "condition": null,
      "topic": null,
      "kind": "assignment",
      "evidence": ""
    }
  ],
  "risk_hints": [
    {
      "risk": "",
      "topic": null,
      "signal_type": "time",
      "severity_evidence": null,
      "impact": null,
      "mitigation": null,
      "owner": null,
      "evidence": ""
    }
  ],
  "open_questions": [],
  "dependencies": []
}
```

### 4.3 字段说明

`meeting_brief`

- 一句话概括整场会议。
- 用于纪要摘要、渲染标题、溯源纪要开头。
- 应短，不超过 80 字。

`meeting_purpose`

- 会议目的。
- 优先沿用原文明确表述。
- 没有明确目的时，用核心议题概括。

`scene`

- 会议场景。
- 保留当前枚举即可：通用、团队例会、脑暴/讨论、项目决策与评审、专项讨论会、研讨会、采访/对话。
- 场景只影响组织侧重，不改变事实判断。

`topics`

- 从长 discussion 改为短 `key_points`。
- 每个议题只保留关键事实，不承担待办、风险、依赖的完整承载。
- `key_points` 建议每个 topic 3-8 条，过多时优先保留数字、时间、人名、明确结论、争议点。

`decisions`

- 建议由字符串列表改为结构化对象。
- `type` 可选：
  - `decision`：明确拍板
  - `directive`：明确要求、指令
  - `scope_inclusion`：明确纳入
  - `scope_exclusion`：明确排除
- 必须包含 `evidence`，减少下游回查原文成本。

`action_hints`

- 这是待办候选，不是最终待办。
- 必须高召回，宁可多给候选，但每条必须有证据。
- `kind` 保留当前枚举：commitment、assignment、directive、rectification、followup。
- 增加 `evidence` 是关键优化点。

`risk_hints`

- 这是风险候选，不是最终风险报告。
- 必须带 `evidence`。
- `severity_evidence` 只保留原文强度词，不做模型判断。
- 风险 Agent 再负责最终 severity。

`open_questions`

- 保留未决问题。
- 建议后续可结构化，但第一阶段可以仍用字符串。

`dependencies`

- 保留依赖关系。
- 建议后续结构化：

```json
{
  "dependency": "",
  "blocks": "",
  "evidence": ""
}
```

第一阶段可以先保持字符串，避免改动过大。

## 5. 任务级上下文裁剪

这是优先级最高的优化。

当前任务 Agent 都消费同一个 `_shared_context`。建议改成按任务构造上下文包。

### 5.1 `minutes_pack`

会议纪要需要的是会议主线和已确认事实。

建议输入：

```json
{
  "mode": "",
  "user_focus": {},
  "meeting_brief": "",
  "meeting_purpose": "",
  "scene": "",
  "topics": [],
  "decisions": [],
  "risks": [],
  "open_questions": [],
  "key_action_hints": [],
  "history_context": ""
}
```

说明：

- `topics` 使用短 key_points，不传长 discussion。
- `key_action_hints` 只传与明确分工、下一步、整改相关的少量线索。
- 不默认传完整原文。
- 如需纠错，可以传相关证据句，而不是全文。

### 5.2 `actions_pack`

待办提取最适合候选驱动。

建议输入：

```json
{
  "mode": "",
  "user_focus": {},
  "action_hints": [],
  "directive_decisions": [],
  "dependencies": [],
  "relevant_evidence": []
}
```

说明：

- `action_hints` 是主输入。
- `directive_decisions` 从 decisions 中筛出 `type=directive` 或含执行要求的决策。
- `dependencies` 用于条件型任务。
- `relevant_evidence` 是 action_hints 和 directive_decisions 的证据句集合。
- 不再默认传完整原文和完整 topics。

### 5.3 `risks_pack`

风险提取也应候选驱动。

建议输入：

```json
{
  "mode": "",
  "user_focus": {},
  "risk_hints": [],
  "dependencies": [],
  "risk_related_open_questions": [],
  "relevant_evidence": []
}
```

说明：

- `risk_hints` 是主输入。
- `dependencies` 中未确认、受限、卡点类依赖可作为风险候选。
- `risk_related_open_questions` 只保留具有风险属性的未决问题。
- high 风险必须由 `severity_evidence` 支撑。

### 5.4 `minutes_trace_pack`

溯源纪要需要事实结构和对齐证据。

建议输入：

```json
{
  "scene": "",
  "meeting_brief": "",
  "topics": [],
  "decisions": [],
  "risks": [],
  "open_questions": [],
  "supported_user_focus": [],
  "transcript_evidence": []
}
```

说明：

- 正文生成只处理会议事实结构。
- 用户关键点、用户笔记先做支持性判断。
- 能被会议原文支持的内容进入 `supported_user_focus`。
- 不支持的用户批注不得进入正文。

`supported_user_focus` 建议结构：

```json
{
  "kind": "keypoint",
  "source": "",
  "supported": true,
  "matched_evidence": "",
  "related_topic": ""
}
```

## 6. 各任务 Prompt 修改建议

### 6.1 会议纪要 `minutes`

目标：让纪要 Agent 专注于结构化草稿，不重新发现事实。

建议规则：

- 只基于 `minutes_pack` 写草稿。
- `key_decisions` 只搬运 `decisions`。
- `risks_and_blockers` 只搬运上游 `risks` 或 `risk_hints` 中确认的风险。
- `unresolved_questions` 只搬运 `open_questions`。
- `executive_summary` 基于 `meeting_brief + topics + decisions` 提炼。
- 不从完整原文中新增上游没有的决策、风险、未决问题。
- 原文只用于修正明显错字、归属和数字，不作为新增事实来源。

建议删减：

- 大量关于“如何判断决策、风险、未决”的规则可从 minutes prompt 移出，因为应由会议理解层完成。
- 关于 action_hints/risk_hints 的细节不用在 minutes prompt 中展开。

建议保留：

- 摘要槽位规则。
- 视角裁剪规则。
- 搬运字段不改写规则。
- 历史记忆误用拦截规则。
- 去重和篇幅收紧规则。

质量验收：

- 决策条数与上游一致，或视角裁剪后可解释。
- 摘要不空泛，包含会议主线、关键结论和下一步。
- 不把讨论、建议、评估写成决策。
- 不重复堆砌同一事实。

### 6.2 待办提取 `actions`

目标：从候选线索中精筛出可执行待办。

建议规则：

- 主输入为 `action_hints`。
- 每条 action_hint 必须带 evidence。
- 待办 Agent 不再通读完整原文，只核查 evidence。
- `directive_decisions` 中的执行指令必须进入候选。
- `dependencies` 用于条件型待办。
- 仍保留“宁缺毋滥”。

待办 Agent 只做五件事：

- 判断是否是真待办。
- 原子化拆分。
- 判断负责人。
- 判断 deadline/priority/status/confidence。
- 按视角分类。

建议保留的专业规则：

- 培训/学习/倡导类建议不提取，除非有责任主体和时点。
- 负责人只认原文姓名，不用画像推断。
- 无负责人但任务明确，进入 unassigned。
- high/low priority 必须有证据词。

建议减少：

- “通读原文补漏”的描述应弱化。补漏可以交给会议理解层，或只在 action_hints 为空时触发。

质量验收：

- 明确承诺、明确分配、明确整改不遗漏。
- 不把普通建议写成待办。
- owner/deadline 不编造。
- evidence 能支撑 task。

### 6.3 风险提取 `risks`

目标：从风险候选中稳定生成风险清单。

建议规则：

- 主输入为 `risk_hints`。
- 每条 risk_hint 必须带 evidence。
- high 风险必须有 `severity_evidence`。
- 无 evidence 的风险候选直接丢弃。
- impact/mitigation/owner 只取上游结构化字段或 evidence 明示内容。

风险 Agent 只做四件事：

- 判断是否是真风险。
- 判断 severity。
- 整理 impact/mitigation/owner。
- 去重并保持原文顺序。

建议保留：

- 不编造风险。
- 不夸大严重程度。
- 拿不准不提取。
- 风险顺序按原文出现顺序。

建议减少：

- 不再让风险 Agent 大量扫描完整 topics 和完整原文。
- 不重复解释风险与未决问题的全部判定规则，保留简版即可。

质量验收：

- severity 稳定，high 有强证据。
- mitigation 不推断建议，只写原文已有措施。
- owner 不推断。
- 不把普通未决问题都升级成风险。

### 6.4 溯源纪要 `minutes_trace`

目标：生成事实可靠、按问题组织、能与用户重点/笔记对齐的纪要。

建议拆成两类输入：

- 会议事实：scene、meeting_brief、topics、decisions、risks、open_questions。
- 用户关注：supported_user_focus。

正文生成规则：

- 只写会议原文和会议理解支持的事实。
- 用户关键点/笔记不是会议事实。
- supported_user_focus 中有证据支持的内容，可写入对应议题。
- unsupported 用户内容不得进入正文。
- 按问题组织，不按人组织。
- 保留不确定语气：可能、预计、考虑、待确认。

对齐规则：

- 对齐阶段单独执行。
- sentence 必须来自已批准正文。
- source 来自用户关键点或用户笔记的原文片段。
- evidence 必须来自会议原文。
- 不为对齐补造正文。

建议减少：

- 正文生成 prompt 不要同时承担大量对齐规则。
- 对齐规则放到 align prompt 中。
- “按问题重切”规则保留，但压缩表达。

质量验收：

- 主要议题不是按人分章。
- 用户批注不进入会议事实正文。
- 每条对齐都有 evidence。
- 对不上不强行挂。

## 7. Prompt 精简原则

### 7.1 会议理解 Prompt 压缩为四块

第一块：事实边界

- 只提取原文明确出现的信息。
- 不编造、不推断、不引入会外常识。
- 清除转写占位符。
- 保持原文首次出现顺序。

第二块：字段抽取规则

- 每个字段只写必要规则。
- 不在上游 prompt 里长篇解释下游如何使用。
- 关键字段必须带 evidence。

第三块：判定规则

- 决策 vs 讨论。
- 风险 vs 未决问题。
- 待办线索 vs 普通建议。
- 依赖关系识别。

第四块：输出纪律

- 严格 JSON。
- 空字符串用 null，空列表用 []。
- evidence 必须可回到原文。
- 不输出解释、Markdown 或多余文本。

### 7.2 任务 Prompt 只保留专业规则

任务 prompt 不应再重复完整会议理解规则。

例如：

- `minutes` 只管摘要、搬运、视角裁剪、历史记忆。
- `actions` 只管待办真伪、原子化、归属、优先级、分类。
- `risks` 只管风险真伪、severity、impact、mitigation。
- `minutes_trace` 只管事实正文、问题组织、用户关注对齐。

### 7.3 Render Prompt 继续保持轻量

Render 只负责表达：

- 不新增事实。
- 不改变字段含义。
- 不重复。
- 输出自然可读。

Render 不应承担事实判断。

## 8. 分阶段落地建议

### 阶段一：上下文裁剪

目标：不大改契约，先减少每个任务拿到的上下文。

改动范围：

- 新增任务级上下文构造逻辑。
- `minutes/actions/risks/minutes_trace` 分别使用自己的 pack。
- 暂时保留原有 `MeetingUnderstanding` 字段。

收益：

- token 明显下降。
- 任务运行时间下降。
- 风险较小，不影响 API 返回结构。

验收：

- 四个重点任务输出字段不变。
- 输出质量不低于当前版本。
- 单任务调用时 prompt 输入明显变短。

### 阶段二：给候选字段增加证据

目标：提升待办和风险质量。

改动范围：

- `action_hints` 增加 `evidence`。
- `risk_hints` 增加 `evidence`。
- 下游 prompt 改为优先核查 evidence。

收益：

- 待办少漏、少误判。
- 风险 severity 更稳定。
- 下游减少回查原文。

验收：

- 所有 action_hints/risk_hints 都有 evidence。
- 待办 owner/deadline 不编造。
- high 风险必须能在 evidence 或 severity_evidence 中找到强信号。

### 阶段三：压缩 topics

目标：避免 `topics.discussion` 成为第二份原文。

改动范围：

- 将 `discussion` 改为 `key_points`。
- 下游 prompt 改为消费 key_points。
- 如果兼容旧结构，可先同时保留 `discussion` 和 `key_points`，后续再删除 discussion。

收益：

- 会议理解输出更短。
- 下游输入更干净。
- 纪要摘要更不容易重复。

验收：

- topics 能覆盖主要议题。
- 每个 topic 的 key_points 足够支撑纪要。
- 不因压缩 topics 而漏掉待办和风险，因为它们应进入专门字段。

### 阶段四：结构化 decisions

目标：让决策成为可复用事实对象。

改动范围：

- `decisions` 从字符串列表改为对象列表。
- 更新 minutes/actions/minutes_trace 消费逻辑。
- Render 层需要从对象中取 `decision` 字段输出。

收益：

- 纪要决策更稳定。
- 待办能直接消费 directive 类型决策。
- 溯源纪要能更好处理范围纳入/排除、时间、条件。

验收：

- 决策不丢 owner/timing/condition。
- 指令类决策能进入待办候选。
- 摘要不把讨论误写成决策。

### 阶段五：动态会议理解 Schema

目标：进一步压缩单任务请求成本。

方案：

- 跑 `minutes` 时，会议理解只产纪要需要的 schema。
- 跑 `actions` 时，只产行动线索 schema。
- 跑 `risks` 时，只产风险线索 schema。
- 跑 `minutes_trace` 时，只产事实结构和溯源所需 schema。

收益：

- token 降幅最大。
- 单接口响应更快。

风险：

- 工程改动较大。
- 多任务并行时需要合并不同 schema。
- 需要更多回归样例。

建议等前四阶段稳定后再做。

## 9. 质量评估指标

### 9.1 Token 与耗时

每条任务记录：

- prompt token
- completion token
- total token
- cache_hit_tokens
- cost_time

目标：

- 单任务调用输入 token 明显下降。
- `actions` 和 `risks` 的运行时间优先下降。
- `minutes_trace` 在保持质量的前提下降低上下文长度。

### 9.2 会议纪要质量

检查项：

- 摘要是否覆盖会议主线。
- 决策是否只来自上游结构化字段。
- 风险和未决是否不丢关键项。
- 是否减少重复表达。
- 是否避免空泛句。
- 是否保留关键数字、日期、责任人和范围边界。

### 9.3 待办质量

检查项：

- 明确承诺是否被提取。
- 明确分配是否被提取。
- 明确整改是否被提取。
- owner 是否只来自原文。
- deadline 是否只来自原文。
- 是否过滤普通建议、倡导表态和学习要求。
- evidence 是否能支撑 task。

### 9.4 风险质量

检查项：

- 明确风险是否覆盖。
- severity 是否稳定。
- high 是否有强证据。
- impact/mitigation 是否不推断。
- owner 是否不推断。
- 未决问题是否没有被过度升级为风险。

### 9.5 溯源纪要质量

检查项：

- 正文是否按问题组织，而不是按人组织。
- 用户关键点/笔记是否没有被当作会议事实。
- 对齐条目是否都有原文 evidence。
- 对不上时是否不强行挂。
- 不确定语气是否保留。

## 10. 推荐优先级

优先级从高到低：

1. 任务级上下文裁剪。
2. `action_hints` 和 `risk_hints` 增加 evidence。
3. `topics.discussion` 改为短 `key_points`。
4. `decisions` 结构化。
5. 溯源纪要增加 `supported_user_focus`。
6. 动态会议理解 schema。

最推荐先做前两项：

- 改动相对可控。
- 对 token、时间、质量都有直接收益。
- 不需要马上重构所有下游模型。

## 11. 最终目标

会议领域最终应该形成这样的能力边界：

- 会议理解 Agent：高召回事实索引，短字段，强证据。
- 会议纪要 Agent：基于事实索引写摘要和结构化纪要，不重新抽取事实。
- 待办 Agent：基于 action_hints 精筛待办。
- 风险 Agent：基于 risk_hints 精筛风险。
- 溯源纪要 Agent：基于事实结构写正文，基于证据做对齐。
- Render：只负责表达，不负责事实判断。

一句话原则：

> 质量提升靠字段更准，速度提升靠上下文更窄，token 降低靠任务分工更硬。
