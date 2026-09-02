# 会议记忆优化实施指导

本文整理会议纪要记忆链路中已发现的问题与优化方向，供后续代码修改时按步骤落地。范围包括：

- `minutes` / `minutes_styles` 的会议记忆注入、生成、渲染与引用展示。
- 传 `project` 与不传 `project` 时的项目绑定逻辑。
- 降低 token 消耗，同时提升历史会议溯源质量。

当前目标不是扩大记忆命中率，而是提升可信度：有强证据才使用历史记忆，能溯源到原始会议片段，不把历史信息误写成本场事实。

## 当前链路概览

### 传 project

请求中传入 `extra.project` 且 `memory=true` 时，会议记忆走显式绑定：

1. `app.tasks` 将 `project`、`memory`、`time` 传入 `tools.core.runner.prepare_run`。
2. `prepare_run` 对 meeting 域的 `minutes` / `minutes_styles` 写入 `__meeting_memory__` 元信息。
3. 会议理解完成后，`tools.meeting_memory.runtime.build_line_extra` 提取本场 `MeetingFact`。
4. `tools.meeting_memory.bind.bind_meeting` 使用显式 `project` 生成 `project_id`，置信度直接为 high。
5. 加载 `data/{user_id}/meeting/states/{project_id}.json`，由 `build_memory_context` 拼出 `【会议记忆】`。
6. 生成完成后，`persist_after_run` 将本场会议写回同一项目 state、`meetings.jsonl` 和 Chroma 索引。

优点是稳定、可控；风险是传错项目时仍会强行绑定。当前代码只给 warning，不阻断注入。

### 不传 project

不传 `extra.project` 时，会议记忆走自动绑定：

1. 遍历 `registry.json` 中已有项目。
2. 用本场标题、摘要、anchors、决策、风险、未决项，与项目的 `name`、`aliases`、`anchors`、`negative_anchors` 做字符串匹配。
3. 命中项目名或 alias，或命中两个以上 anchors，视为 high。
4. 如果只有一个 high 项目，则自动绑定并注入该项目 state。
5. 如果多个 high，则认为歧义，不注入。
6. 如果无命中，但能从本场标题或候选实体抽出项目名，则自动创建新项目。

当前问题是 anchors 中可能混入大量泛词或错误切片，例如 `Agent`、`memory`、`历史会议`、`复盘`、`开发进展`、`发进展第`。这些词会抬高无关项目的分数，导致不传 `project` 时误绑。

## 示例

历史第 1 场会议：

```text
会议主题：小艺慧记Agent开发进展阶段复盘

赵衡：记忆引用现在用户看不到来源，容易误以为系统凭空补充。
周宁：8月19日前赵衡补齐记忆引用的来源字段，包括历史会议时间、会议名称、类型和关联对象。
```

当前写回后，state 可能类似：

```json
{
  "risks": [
    {
      "text": "记忆引用现在用户看不到来源，容易误以为系统凭空补充。",
      "last_seen": "m_001",
      "meeting_title": "小艺慧记Agent开发进展阶段复盘",
      "quote": ""
    }
  ],
  "decisions": [
    {
      "text": "8月19日前赵衡补齐记忆引用的来源字段，包括历史会议时间、会议名称、类型和关联对象。",
      "meeting_id": "m_001",
      "meeting_title": "小艺慧记Agent开发进展阶段复盘",
      "quote": ""
    }
  ]
}
```

第 2 场会议不传 `project`：

```text
今天继续看小艺慧记Agent的内测收口，Gradio入口和minutes_trace还有两个问题。
```

当前自动绑定可能命中：

```text
项目名公共核心：小艺慧记Agent开发进展
anchors：Agent、历史会议、记忆引用、开发进展、minutes_trace、Gradio
```

这里 `minutes_trace`、`Gradio`、`小艺慧记Agent` 是有效强信号；但 `Agent`、`历史会议`、`记忆引用` 偏泛，应该弱化。

更理想的注入内容：

```text
【会议记忆】
项目：小艺慧记Agent

【相关历史】
- 风险：记忆引用现在用户看不到来源，容易误以为系统凭空补充。
  来源会议：小艺慧记Agent开发进展阶段复盘
  会议时间：2026-08-14 10:00
  原文摘录：赵衡：记忆引用现在用户看不到来源，容易误以为系统凭空补充。
```

最终输出中的溯源：

```md
相较历史记录，[记忆引用可解释性不足](#memory-1)的风险，本场通过正文下划线加底部来源方案推进缓解。

## 历史记忆引用

#### 溯源 memory-1
> 赵衡：记忆引用现在用户看不到来源，容易误以为系统凭空补充。
来源会议：小艺慧记Agent开发进展阶段复盘
会议时间：2026-08-14 10:00
```

## 三步走实施方案

## 第一步：先修溯源质量与触发稳定性

这一阶段只做低风险修正，不改变项目绑定策略，也不引入复杂检索。

### 1. 修复 quote 对齐

问题位置：

- `tools/meeting_memory/extract.py`
- `tools/meeting_memory/state.py`

当前 `_quotes()` 只保存：

```json
{"kind": "risk", "quote": "赵衡：记忆引用现在用户看不到来源..."}
```

但 `state.py` 的 `_quote()` 会用 `item.get("text")` 与目标 text 做相似匹配。由于 quote item 没有 `text`，state 里的 `quote` 经常为空。

建议改法：

- 在 `_quotes()` 中保留 `text` 字段：

```json
{
  "kind": "risk",
  "text": "记忆引用现在用户看不到来源，容易误以为系统凭空补充。",
  "quote": "赵衡：记忆引用现在用户看不到来源，容易误以为系统凭空补充。"
}
```

- 保持 `_quote()` 现有按 text 相似匹配的方式。

预期收益：

- 文末「历史记忆引用」从结构化改写句升级为历史会议原话。
- 用户能判断引用是否真实来自历史会议。
- 程序侧引用锚定更可靠。

### 2. 修复 prompt 触发词

问题位置：

- `domain/meeting/tasks/minutes/prompts.py`

当前 `history_comparison` 的触发条件包括：

```text
记忆命中 / 记忆摘录条目 / 历史项目状态 / 项目纪要素材
```

但实际注入块是：

```text
【会议记忆】
```

建议将触发条件补齐为：

```text
上下文出现【会议记忆】、记忆命中、记忆摘录条目、历史项目状态或项目纪要素材之一 → 必须产出对照；都没有 → []
```

同时把 prompt 中“上下文有历史记忆注入”的描述统一到 `【会议记忆】`，避免模型漏写 `history_comparison`。

预期收益：

- 草稿阶段更稳定地产出历史对照。
- 减少历史记忆已经注入但最终没有体现的情况。

### 3. 校验示例

用两场连续会议回归：

1. 第 1 场写入包含 `quote` 的 state。
2. 第 2 场开启 memory，不传或传正确 project。
3. 检查最终 `## 历史记忆引用` 中的 blockquote 是否优先展示历史会议原话。
4. 检查 `history_comparison` 是否非空，并且没有把历史内容写成本场新决策。

## 第二步：减少重复注入，降低 token 消耗

这一阶段优化 token，不改变最终展示效果。

### 1. 当前重复注入

会议记忆当前会进入两个 LLM 阶段：

1. 草稿生成阶段：用于生成 `history_comparison`。
2. 渲染阶段：随 render context 再次进入模型。

但最终正文下划线与文末来源不是模型生成的，而是程序侧：

- `tools.meeting_memory.render.apply_memory_citations(markdown, context)`
- `parse_memory_items(context)`
- 在正文中找可锚定片段并追加 `## 历史记忆引用`

因此渲染阶段没有必要再次把完整 `【会议记忆】` 交给模型。

### 2. 建议目标

保留草稿阶段注入：

```text
草稿 Agent 读取【会议记忆】 → 生成 history_comparison
```

渲染阶段改为：

```text
Render 只读取已审核草稿中的 history_comparison
程序侧继续使用同一份 memory_context 做引用标注
```

### 3. 实施思路

建议在运行 state 或 line_extra 中缓存一次 memory context，避免重复构建与重复注入：

```text
生成阶段：
  memory_context = build_line_extra(...)
  注入给 minutes agent
  缓存到 state 或 line_extra 的内部 key

渲染阶段：
  不把 memory_context 拼进 render LLM context
  但在保存报告时，将 memory_context 传给 apply_memory_citations
```

注意：如果当前保存逻辑依赖 `memory_on=True` 再自行从上下文拿 memory block，需要梳理 `tools.exports.outputs.save_all_reports` 中的调用点，保证程序侧引用仍能拿到 memory context。

### 4. 预期收益

- 少一次完整 `【会议记忆】` prompt 注入。
- 降低模型把历史内容改写成本场正文的概率。
- 保留程序侧可解释引用，不牺牲文末来源展示。

## 第三步：优化不传 project 的自动匹配

这一阶段提升自动绑定精度，尤其处理用户不传 `project` 的场景。

### 1. Anchor 质量分层

当前 registry 的 anchors 直接混在一个列表里。建议逻辑上分成三类，即使初期不改存储结构，也可以在打分时临时分类：

```json
{
  "identity_anchors": ["小艺慧记Agent", "minutes_trace", "Gradio"],
  "topic_anchors": ["记忆引用可解释性", "历史会议来源", "模板入口移除"],
  "generic_anchors": ["会议纪要", "风险", "复盘", "Agent", "memory"]
}
```

建议权重：

- identity anchors：高权重，决定项目身份。
- topic anchors：中权重，辅助确认同一项目阶段或同一问题域。
- generic anchors：低权重或不参与绑定。
- malformed anchors：过滤，例如 `发进展第`、`复盘小艺`、`展第一阶`。

### 2. 强信号门槛

自动 high bind 不应只靠 anchor 数量。建议要求至少一个强信号：

- 项目名或 alias 命中。
- 标题与项目名存在稳定公共核心。
- 命中专有产品名、客户名、课程名、系统名。
- 命中多个专有模块组合，例如 `小艺慧记Agent + minutes_trace + Gradio`。

没有强信号时，即使泛词很多，也只作为 medium candidate，不注入会议记忆。

### 3. Top1 与 Top2 差距校验

当前逻辑只区分一个 high 或多个 high。建议增加排名差距：

```text
top1 >= high_threshold
且 top1 / top2 >= 2
且 top1 包含至少一个强信号
=> 自动绑定
```

如果：

```text
项目 A：27
项目 B：24
```

即使 A 第一，也应视为歧义，不注入。

如果：

```text
项目 A：31
项目 B：6
```

且 A 有强身份锚，则自动绑定。

### 4. 负信号与冲突实体

使用 `negative_anchors` 或动态冲突检测，避免串项目：

```text
历史项目：小艺慧记Agent
新会议：销售Agent客户跟进风险

重叠：Agent、风险、记忆引用
冲突：销售 / 客户 / 回款 与 小艺慧记 / Gradio / minutes_trace 不一致
结论：不自动绑定
```

可作为负信号的字段：

- 不同客户名。
- 不同产品名。
- 不同课程或学科。
- 不同项目代号。
- 明确互斥业务场景。

### 5. Chroma 只做召回，不直接裁决

当前 Chroma 已写入会议记忆索引，但 `minutes` 注入不使用它。后续可以让 Chroma 参与“不传 project”的候选召回：

1. 用本场 `MeetingFact.summary + anchors + decisions + risks` 查询 Chroma。
2. 按 `project_id` 聚合 Top-K 命中。
3. 只把高召回项目交给规则层二次校验。
4. 最终绑定仍由规则决定，不让向量相似度单独决定。

这样可以提升候选召回能力，但避免纯语义相似导致串项目。

### 6. 自动创建项目名优化

当前无命中时，可能用整段会议标题作为项目名：

```text
小艺慧记Agent开发进展阶段复盘
```

更理想是抽项目核心名：

```text
小艺慧记Agent
```

建议创建项目时优先级：

1. 引号内或显式项目候选。
2. 中文 + 拉丁混合产品名，例如 `小艺慧记Agent`。
3. 标题中去掉会种词、阶段词后的核心名。
4. 实在无法抽取时才使用完整标题。

常见应剥离词：

```text
阶段复盘、内测前推进会、周会、例会、评审会、沟通会、开发进展、收口会
```

## 最终建议顺序

### Step 1：低风险质量修复

- `_quotes()` 增加 `text`，让 state 能写入真实原文摘录。
- prompt 的历史触发条件加入 `【会议记忆】`。
- 做两场会议回归，确认历史对照与文末来源都稳定。

### Step 2：token 优化

- 草稿阶段保留完整会议记忆。
- 渲染阶段不再重复注入完整会议记忆。
- 程序侧继续用缓存 memory context 做下划线与文末来源。

### Step 3：不传 project 的精确匹配

- 过滤低质量 anchors。
- 引入强信号门槛。
- 增加 top1/top2 差距校验。
- 加入冲突实体和负信号。
- 可选引入 Chroma 召回，但最终仍由规则裁决。

## 验收标准

1. 正确项目连续两场会议，不传 `project` 也能自动接上历史。
2. 两个不同项目共享泛词时，不传 `project` 不会误绑。
3. 文末来源优先展示历史会议原始摘录，而不是结构化改写句。
4. 有 `【会议记忆】` 时，`history_comparison` 稳定出现；没有记忆时不强行生成历史对照。
5. 渲染阶段 token 下降，最终下划线引用与来源区仍可正常生成。
6. 历史内容不会被写成本场新发生的决策、风险或行动项。
