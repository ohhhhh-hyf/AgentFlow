# Visual Minutes 通用图文纪要生成执行清单

> 目标：
>
> ```text
> 纪要 Markdown + 会议原文
> → Visual Agents
> → 通用语义视觉 IR
> → 确定性 SVG / HTML 渲染
> → 最终完整 HTML
> ```
>
> 约束：
>
> - 图文纪要不是多模态生成图片；
> - 图由语义数据 + 确定性 HTML/SVG 渲染产生；
> - 纪要正文一字不改，只做视觉增强；
> - 开篇必须有一张整体纪要通览图；
> - 每个 section 都要经过视觉必要性判断；
> - 不允许在 Prompt 中放具体业务示例或内容软引导；
> - 不使用固定业务模板；
> - 不使用 visual_minutes 自有 API Key，统一走 `infra.llm.LLMClient`。

---

## 〇、本次范围

本次只允许修改：

```text
domains/shared/visual_minutes/
```

明确不做：

- 不接入 `minutes` 任务线；
- 不修改 `domains/meeting`；
- 不修改 `app`；
- 不修改 `core`；
- 不修改 actions / calendar；
- 不改变纪要生成流程；
- 不改变纪要展示时机；
- 不新增 API 路由；
- 不新增后台任务；
- 不接入会议运行态。

visual_minutes 只提供一个独立能力：

```text
输入：
  minutes_markdown
  meeting_transcript

输出：
  final_html
  visual_ir
  warnings
```

调用方什么时候调用、如何展示、是否异步，都由调用方决定。

本包不关心：

- 纪要是否已经展示；
- 是否在会议任务中；
- 是否走 SSE；
- 是否存数据库；
- 是否作为独立接口暴露。

---

## 实施状态（2026-10-30）

已完成：

- `models/ir.py`：5 个通用视觉原语 + discriminated union + master/section IR；
- `parsing/parser.py`：Markdown section tree、稳定 `section_id`、标题路径；
- `parsing/retrieval.py`：section 级原文检索与预算控制；
- `llm.py`：统一走 `infra.llm.LLMClient`；HTTP / WebSocket / vLLM、API Key、模型、max_tokens 全部由根目录 `.env` 决定，不保存任何 Key；视觉温度默认 0.2，可用 `VISUAL_LLM_TEMPERATURE` 覆盖；
- `agents/planner.py` / `agents/extractor.py` / `agents/master.py`：三个 LLM Agent；
- `validation/validator.py`：section 覆盖、evidence、密度、table/flow/tree/stats 完整性校验；
- `rendering/renderer/`：master + 5 个通用原语，确定性 HTML/CSS + inline SVG；
- `rendering/compositor.py`：按 `section_id` 精确插入，正文不变性已验证；
- `pipeline.py`：`VisualMinutesResult(html, ir)`，`warnings` 从 `ir.warnings` 读取；
- `agent.py`：保留旧 `VisualMinutesAgent` 调用方式。

已验证：

- 五种原语的渲染、转义、移动端布局；
- master 覆盖失败 → 程序 fallback；
- planner / extractor / master 单点失败隔离与 warning；
- 空纪要、无 heading、非法 section_id、非法 visual、重复决策；
- 纪要正文 HTML 不变性（含 GFM 表格）；
- fake LLM 全链路。

未做：

- 未接入 `minutes` / `app` / `domains/meeting` / `core` / actions / calendar；
- 缓存未实现（清单中为可选项）；
- 真实模型的视觉规划质量与多种纪要回归尚未验收，当前验证均使用 fake LLM。

---

## 一、当前实现的主要问题

### 1. 单 Agent 承担全部职责

当前 `domains/shared/visual_minutes/agent.py`：

```text
markdown + transcript
→ 一次大 Prompt
→ 一个 SemanticVisualIR
```

同一个 Agent 同时负责：

- 理解整篇纪要；
- 判断每段是否需要图；
- 选择图类型；
- 抽取图数据；
- 生成开篇大图；
- 控制正文图数量；
- 保证 JSON 合法。

职责过多，导致：

- 图表选择不稳定；
- 容易套固定模板；
- 某些段落被漏掉；
- 某些段落被强行配图；
- 数据密度不一致。

### 2. 固定业务组件，不通用

当前固定类型：

```text
master_infographic
timeline_flow
comparison_matrix
problem_solution
closed_loop
```

问题：

- `comparison_matrix` 只支持两方对比；
- `problem_solution` 只适合痛点解法；
- `closed_loop` 只适合闭环；
- 没有通用表格、树、流程、指标卡等原语；
- 模型只能往现有类型里硬套。

### 3. 正文图最多 3 个

当前 `body_widgets[:3]` 是硬截断。

问题：

- 第 4 个之后的 section 没有机会；
- 不是按视觉必要性筛选；
- 不是按 section 遍历。

### 4. 开篇大图限制过强

当前 master 只允许 2～5 个 blocks。

问题：

- 无法覆盖较多一级栏目；
- 会强制合并或截断；
- 与“整体纪要通览”目标冲突。

### 5. 正则锚点注入不稳定

当前 `compositor.py` 通过标题文本正则匹配插入图。

问题：

- 同名标题会错位；
- 标题格式不同会失败；
- 匹配失败会追加到文末；
- 没有稳定 section ID。

### 6. 没有 evidence

当前视觉 IR 没有逐条事实依据。

问题：

- 图表可能补出原文没有的数据；
- 表格可能出现原文没有的维度；
- 无法判断图是否忠实。

### 7. 没有 section 级规划

当前不是“逐段判断”，而是一次性让模型决定 0～3 个图。

目标应该是：

```text
每个 section 都判断
→ 多数 section 返回 none
→ 只有满足数据形态阈值的 section 才出图
```

### 8. 没有接入 infra.llm

`domains/shared/visual_minutes/config.py` 仍维护自己的 Key 与 HTTP 客户端。

应统一：

```text
infra.llm.LLMClient
→ .env
→ 部署版 DeepSeek
```

---

## 二、目标架构

### 2.1 三个 LLM Agent

```text
Agent 1：Section Planner
Agent 2：Visual Extractor
Agent 3：Master Visual Planner
```

不是每种图一个 Agent。

### 2.2 程序模块

```text
Section Parser
Transcript Retriever
IR Validator
Renderer
Compositor
Pipeline
```

### 2.3 总流程

```text
纪要 Markdown + 原文
→ Section Parser
→ Section Planner
→ 并行：
   → Visual Extractor（按 section）
   → Master Visual Planner
→ IR Validator
→ Renderer
→ Compositor
→ 最终 HTML
```

---

## 三、Agent 1：Section Planner

### 3.1 职责

只负责判断：

```text
每个 section 是否需要视觉
适合哪种通用视觉原语
视觉必要性有多高
需要哪些数据字段
```

不负责抽取图表数据。

### 3.2 输入

- 全部 section 的 `section_id`；
- 标题；
- 标题路径；
- 正文摘要；
- 章节顺序；
- 会议主题；
- 可选：极少量相关原文片段。

不发送整篇 transcript。

### 3.3 输出

```json
{
  "sections": [
    {
      "section_id": "string",
      "visual": "none | timeline | table | flow | tree | stats",
      "necessity": 0.0,
      "rationale": "string",
      "required_data": ["string"]
    }
  ]
}
```

### 3.4 硬性规则

- 每个 section 必须出现且只出现一次；
- 默认 `none`；
- 不要求每个 section 都有图；
- 不需要图时 `necessity` 必须低；
- 不根据标题关键词直接决定图类型；
- 根据正文实际数据形态判断；
- 没有足够数据时返回 `none`；
- 不输出示例，不引用任何具体业务模板；
- 不输出 Markdown；
- 不输出 Emoji。

### 3.5 视觉必要性阈值

| 类型 | 最低条件 |
|---|---|
| `timeline` | 至少 3 个明确时间节点 |
| `table` | 至少 2 个对象 × 2 个维度 |
| `flow` | 至少 3 个节点且至少 2 条关系 |
| `tree` | 至少 2 层且至少 3 个节点 |
| `stats` | 至少 2 个硬指标 |
| `none` | 未达到上述条件 |

阈值只用于判断，不在 Prompt 里放具体内容示例。

---

## 四、Agent 2：Visual Extractor

### 4.1 职责

根据 Section Planner 的决定，只抽取一个 section 的视觉数据。

一个 Agent 类，按 section 调用，不是每种图一个 Agent。

### 4.2 输入

- 单个 section；
- 相关原文片段；
- Planner 指定的视觉类型；
- 该类型的强类型 schema；
- section_id。

### 4.3 输出

```json
{
  "section_id": "string",
  "kind": "timeline | table | flow | tree | stats",
  "title": "string",
  "data": {},
  "evidence": ["string"],
  "confidence": 0.0
}
```

### 4.4 硬性规则

- 只处理当前 section；
- 不跨 section 合并；
- 不生成 master；
- 不做排版；
- 数据不足时返回 `none`；
- 每个节点、行、边尽量带 evidence；
- 没有证据的数值不输出；
- 不编造维度、对象、指标；
- 不输出示例；
- 不输出 Markdown/Emoji。

### 4.5 失败处理

单 section 失败：

```text
丢弃该 section 的视觉
保留纪要正文
记录 warning
```

不影响其他 section。

---

## 五、Agent 3：Master Visual Planner

### 5.1 定位

开篇整体纪要通览图是重中之重。

它必须：

- 始终存在；
- 全篇唯一；
- 置于正文最前；
- 覆盖所有一级 section；
- 不替代纪要正文；
- 不重复正文细节；
- 不使用固定业务模板；
- 不出现内容示例软引导。

### 5.2 输入

- Section Planner 的全部输出；
- 每个一级 section 的标题；
- 每个一级 section 的核心摘要；
- 关键指标；
- 会议主题；
- 不发送整篇 transcript。

### 5.3 输出

```json
{
  "headline": "string",
  "thesis": "string",
  "layout": "grid | timeline | flow | matrix",
  "blocks": [
    {
      "section_ids": ["string"],
      "title": "string",
      "summary": "string",
      "key_points": ["string"]
    }
  ],
  "metrics": [
    {
      "label": "string",
      "value": "string",
      "evidence": "string"
    }
  ]
}
```

### 5.4 覆盖规则

- 所有一级 section 必须被覆盖；
- 每个一级 section 至少进入一个 block；
- 同一个一级 section 不得重复出现；
- block 数量不写死；
- section 过多时允许分组；
- 分组必须通过 `section_ids` 明确列出；
- 不得静默截断；
- 不得遗漏 section；
- 没有指标时 `metrics` 为空数组；
- 不强行凑指标。

### 5.5 布局决策

```text
section 是独立并列主题 → grid
section 是连续阶段/历史推进 → timeline
section 是因果/流程推进 → flow
section 是对比关系 → matrix
无法判断 → grid
```

布局由 section 关系决定，不根据标题关键词。

### 5.6 内容规则

- `headline` 必须是全篇主题；
- `thesis` 必须是全篇核心结论；
- block `summary` 必须来自对应 section；
- `key_points` 必须来自对应 section；
- 不引入纪要之外的事实；
- 不出现正文没有的数字；
- 不使用固定“板块 01”等模板词；
- 不输出 Emoji。

### 5.7 Master 兜底

如果 Master Planner 失败：

```text
用程序从 section tree 生成 fallback master
```

fallback 规则：

- 每个一级 section 一个 block；
- `section_ids` 精确对应；
- `title` 使用 section 标题；
- `summary` 使用 section 首句或摘要；
- `key_points` 为空数组；
- `layout` 默认 grid；
- `metrics` 为空数组。
- 保证 master 永远存在。

---

## 六、通用视觉原语

不再使用业务化组件类型。

统一为 5 个原语：

```text
timeline
table
flow
tree
stats
```

### 6.1 timeline

```text
events[]
  time_label
  title
  detail
  evidence
```

适用：

- 时间演进；
- 阶段推进；
- 事件序列。

### 6.2 table

```text
columns[]
rows[]
  cells[]
  evidence
```

适用：

- 多对象对比；
- 决策矩阵；
- 风险矩阵；
- 待办表；
- 字段化信息。

支持任意列数，不再限制 A/B 两方。

### 6.3 flow

```text
nodes[]
  node_id
  title
  detail
  evidence
edges[]
  from
  to
  label
```

适用：

- 流程；
- 因果；
- 闭环；
- 系统流转。

### 6.4 tree

```text
nodes[]
  node_id
  parent_id
  title
  detail
  evidence
```

适用：

- 层级；
- 分类；
- 组织；
- 结构拆解。

### 6.5 stats

```text
metrics[]
  label
  value
  evidence
```

适用：

- 硬指标；
- 关键数字；
- 量化结论。

### 6.6 删除类型

删除：

```text
comparison_matrix
problem_solution
closed_loop
```

它们分别用：

```text
table
table / flow
flow
```

表达。

---

## 七、通用 IR

```json
{
  "master": {},
  "sections": [
    {
      "section_id": "string",
      "visual": {
        "kind": "timeline | table | flow | tree | stats",
        "title": "string",
        "data": {},
        "evidence": [],
        "confidence": 0.0
      }
    }
  ]
}
```

要求：

- Pydantic discriminated union；
- `kind` 与 data schema 强绑定；
- 每个 visual 绑定稳定 `section_id`；
- `sections` 中一个 section 最多一个 visual；
- 没有 visual 的 section 不出现或 `visual=null`；
- `master` 必填且唯一；
- 所有字段强类型；
- 所有节点/行/指标尽量带 evidence。

---

## 八、Section Parser

### 8.1 职责

把 Markdown 解析成稳定 section tree。

### 8.2 输出

```json
{
  "section_id": "string",
  "heading": "string",
  "level": 1,
  "path": ["string"],
  "order": 0,
  "markdown": "string",
  "plain_text": "string"
}
```

### 8.3 要求

- 使用 Markdown AST；
- 不靠正则猜标题；
- section_id 稳定；
- 同级标题按出现顺序编号；
- 保留原始 Markdown；
- 支持 h1/h2/h3；
- 后续图只绑定 section_id；
- 不修改纪要原文。

---

## 九、原文检索

### 9.1 目的

避免把整篇 transcript 塞给每个 section。

### 9.2 规则

- 每个 section 只取相关原文片段；
- 优先使用纪要中的 evidence / 时间戳 / 关键词；
- 可用关键词、BM25 或 embedding；
- 有 token 预算上限；
- 检索不到时只使用 section 文本；
- 不把其他 section 的原文混入当前 section。

### 9.3 输出

```text
section_id → related_transcript_blocks[]
```

---

## 十、IR Validator

### 10.1 结构校验

- master 必须存在且唯一；
- master 覆盖全部一级 section；
- 每个 section_id 必须存在；
- 同一 section 不重复；
- visual kind 与 data schema 匹配；
- table 行列非空；
- timeline 节点数量达标；
- flow 的边必须引用有效节点；
- tree 不能有环；
- stats 至少两个指标。

### 10.2 事实校验

- evidence 非空；
- 关键数字必须能在 evidence 或原文定位；
- 不允许多个 section 引用同一段无关证据；
- 没有依据的内容丢弃。

### 10.3 视觉密度

- 每个 section 最多一个主视觉；
- 全局数量可配置；
- 超过预算按 necessity 排序；
- 不静默截断；
- 被丢弃的图记录 warning。

### 10.4 失败策略

- 单个 visual 校验失败 → 丢弃该 visual；
- master 校验失败 → 使用程序 fallback master；
- 纪要正文永远保留；
- 不因单个图失败导致整个 HTML 失败。

---

## 十一、渲染器

### 11.1 原则

```text
HTML/CSS 负责布局与文字
inline SVG 负责箭头、连线、轴、流程边
```

不要用纯 SVG 渲染长中文正文。

### 11.2 渲染器清单

```text
master_renderer
timeline_renderer
table_renderer
flow_renderer
tree_renderer
stats_renderer
```

全部确定性，不调用 LLM。

### 11.3 要求

- 自包含；
- 无外部 CDN；
- 响应式；
- 移动端可读；
- 文本可换行；
- 所有文本 escape；
- 无 Emoji；
- 无固定业务文案；
- 无示例内容；
- SVG 仅作连接与图形辅助；
- 表格支持横向滚动；
- 长列表支持分段；
- 深色/浅色至少保证浅色可用。

---

## 十二、Compositor

### 12.1 原则

- 纪要正文 100% 保留；
- 图只作为兄弟块插入；
- 不重写 Markdown；
- 不修改段落；
- 不改变标题层级；
- 不依赖模糊标题匹配。

### 12.2 插入规则

1. 渲染 Markdown 为 HTML；
2. 给每个 heading 写入稳定 `id="section_id"`；
3. 按 section_id 定位；
4. 将 visual HTML 插到该 section 内容之后；
5. 如果 section_id 不存在，丢弃该 visual 并记录 warning；
6. 不把匹配失败的图追加到文末；
7. master 永远置顶；
8. 同一 section 多个 visual 时保持顺序。

### 12.3 纪要不变性

验收时必须校验：

- 去除 visual 节点后，正文 HTML 与原始 Markdown 渲染结果一致；
- 标题、段落、列表、引用、代码块未改变；
- 只新增 visual 容器。

---

## 十三、独立流水线

### 13.1 调用方式

visual_minutes 只提供独立流水线：

```text
generate_visual_minutes(
  minutes_markdown,
  meeting_transcript,
  output_path=None
) -> VisualMinutesResult(
  html,
  ir,
  warnings,  # result.warnings
)
```

本包不负责：

- 何时调用；
- 是否后台执行；
- 是否阻塞纪要展示；
- 是否写数据库；
- 是否暴露 API。

调用方可以同步调用，也可以自行放到后台任务中。

### 13.2 输入

```text
minutes_markdown
meeting_transcript
meeting_metadata
```

### 13.3 输出

```text
final_html
visual_ir
warnings
```

### 13.4 缓存

- 以 minutes + transcript + config hash 为 key；
- 相同输入复用结果；
- 纪要变更时失效；
- 生成失败不缓存坏结果。

### 13.5 失败隔离

- Planner 失败 → 全部 section `none`，仍生成 fallback master；
- Extractor 失败 → 丢弃该图；
- Master 失败 → fallback master；
- Validator 失败 → 丢弃坏图；
- Renderer 失败 → 保留纪要正文；
- 整个 visual pipeline 失败 → 返回纪要-only HTML。

---

## 十四、Prompt 规则

### 14.1 不允许内容示例软引导

Prompt 中禁止出现：

- 具体业务案例；
- 具体公司/人名；
- 具体行业术语示例；
- 具体图表填充示例；
- few-shot 内容样例；
- “类似某某会议”式引导；
- 固定模板标题。

只允许：

- 角色；
- 任务；
- 字段 schema；
- 数据类型定义；
- 决策阈值；
- 输出格式；
- 事实约束。

### 14.2 Section Planner Prompt

包含：

- section 列表；
- section 摘要；
- 原语定义；
- 阈值；
- 输出 schema；
- 每个 section 必须返回。

不包含：

- 任何内容示例；
- 任何固定业务模板；
- 任何图表填充样例。

### 14.3 Extractor Prompt

包含：

- 单个 section；
- 相关原文；
- 指定 kind；
- 对应 data schema；
- evidence 规则；
- `none` 规则。

不包含：

- 其他 section；
- master 规则；
- 排版规则；
- 内容示例。

### 14.4 Master Prompt

包含：

- section plan；
- 一级 section 列表；
- 覆盖规则；
- layout 决策规则；
- 输出 schema；
- fallback 不需要模型处理。

不包含：

- 正文图规则；
- 具体内容示例；
- 固定栏目名。

---

## 十五、代码结构建议

```text
domains/shared/visual_minutes/
├── __init__.py            # 公共 API
├── agent.py               # 兼容执行入口
├── config.py              # 仅保留视觉参数，不保存 Key
├── llm.py                 # infra.llm.LLMClient 适配
├── pipeline.py            # 独立端到端入口
├── models/
│   ├── __init__.py        # 兼容 re-export
│   └── ir.py              # 通用视觉 IR
├── parsing/
│   ├── __init__.py
│   ├── parser.py          # Markdown → section tree
│   └── retrieval.py       # section → transcript 片段
├── agents/
│   ├── __init__.py
│   ├── planner.py         # Agent 1
│   ├── extractor.py       # Agent 2
│   ├── master.py          # Agent 3
│   └── prompts.py         # 三个 Agent 的 Prompt
├── validation/
│   ├── __init__.py
│   └── validator.py       # schema / evidence / coverage
├── rendering/
│   ├── __init__.py
│   ├── compositor.py      # section_id 精确合成
│   └── renderer/
│       ├── __init__.py
│       ├── base.py
│       ├── master.py
│       ├── timeline.py
│       ├── table.py
│       ├── flow.py
│       ├── tree.py
│       └── stats.py
└── docs/
    └── VISUAL_MINUTES_AGENT_REBUILD_CHECKLIST.md
```

旧文件处理：

- `agent.py`：保留兼容入口，内部调用 `pipeline`；
- `models.py`：改为 `models/__init__.py` 兼容 re-export，实际模型在 `models/ir.py`；
- `prompts.py`：移入 `agents/prompts.py`；
- `renderer/*`：移入 `rendering/renderer/*`，用通用原语渲染器替换固定业务渲染器；
- `config.py`：删除 API Key；
- `pipeline.py`：改为独立入口，保留可缓存与失败隔离，但不接入会议流程。

包导入路径：

```python
from domains.shared.visual_minutes import generate_visual_minutes
```

---

## 十六、执行顺序

### Phase 0：基线

- [ ] 记录当前 visual_minutes 输出；
- [ ] 确认现有 renderer / CSS 可复用部分；
- [ ] 确认 `infra.llm.LLMClient` 配置；
- [ ] 确认 `.env` 部署版模型可用。

### Phase 1：IR 与 Parser

- [ ] 定义 5 个通用视觉原语；
- [ ] 定义 `VisualDocumentIR`；
- [ ] 定义 master schema；
- [ ] 实现 Markdown section parser；
- [ ] 为 heading 生成稳定 section_id。

### Phase 2：LLM 接入

- [ ] 新增 `domains/shared/visual_minutes/llm.py`；
- [ ] 删除自有 API Key / DeepSeekClient；
- [ ] 统一走 `infra.llm.LLMClient.text(json_mode=True)`；
- [ ] 增加 JSON 解析与校验。

### Phase 3：Section Planner

- [ ] 编写无示例 Prompt；
- [ ] 输入全部 section；
- [ ] 输出每段视觉决策；
- [ ] 校验 section 全覆盖；
- [ ] 默认 `none`。

### Phase 4：Visual Extractor

- [ ] 按 section 调用；
- [ ] 支持 5 个原语 schema；
- [ ] 强制 evidence；
- [ ] 数据不足返回 none；
- [ ] 单 section 失败隔离；
- [ ] 控制并发。

### Phase 5：Master Planner

- [ ] 输入 section plan；
- [ ] 输出全局通览图；
- [ ] 覆盖全部一级 section；
- [ ] 分组不截断；
- [ ] 程序 fallback master；
- [ ] 校验 master 唯一且置顶。

### Phase 6：Validator

- [ ] schema 校验；
- [ ] section_id 校验；
- [ ] evidence 校验；
- [ ] 图数据完整性校验；
- [ ] 全局密度控制；
- [ ] 丢弃坏图不丢正文。

### Phase 7：Renderer / Compositor

- [ ] 通用原语渲染器；
- [ ] master 渲染器；
- [ ] HTML/CSS + inline SVG；
- [ ] section_id 精确插入；
- [ ] 纪要正文不变性测试；
- [ ] 响应式与转义。

### Phase 8：Standalone Pipeline

- [ ] 提供 `generate_visual_minutes(minutes_markdown, meeting_transcript)`；
- [ ] 提供可选异步版本；
- [ ] 输出 final_html / visual_ir / warnings；
- [ ] 失败降级；
- [ ] 可选缓存；
- [ ] 不接入 minutes / app / domains / core；
- [ ] 不新增路由、后台任务或会议运行态依赖。

---

## 十七、验收标准

### 17.1 Master

- [ ] 每篇纪要都有且只有一个 master；
- [ ] master 置顶；
- [ ] 覆盖全部一级 section；
- [ ] 不重复 section；
- [ ] 不静默截断；
- [ ] 分组有明确 section_ids；
- [ ] 无编造指标；
- [ ] layout 与 section 关系一致；
- [ ] 移动端可读。

### 17.2 Section 视觉

- [ ] 每个 section 都被 Planner 判断；
- [ ] 没有数据不足却强行出图；
- [ ] table / timeline / flow / tree / stats 数据完整；
- [ ] 节点/行/边有 evidence；
- [ ] 不跨 section 混数据；
- [ ] 同一 section 最多一个视觉。

### 17.3 纪要正文

- [ ] 正文文字不变；
- [ ] 标题层级不变；
- [ ] 列表/引用/代码块不变；
- [ ] 只新增 visual 节点；
- [ ] 没有图被追加到文末兜底。

### 17.4 通用性

- [ ] Prompt 中无具体内容示例；
- [ ] 无固定业务组件类型；
- [ ] 无固定栏目名；
- [ ] 无固定 section 数量；
- [ ] 无固定 block 数量；
- [ ] 无固定图表数量硬截断；
- [ ] 不同类型纪要都能生成合理 master。

### 17.5 稳定性

- [ ] 单图失败不影响正文；
- [ ] master 失败有程序 fallback；
- [ ] LLM 配置统一；
- [ ] 无硬编码 Key；
- [ ] 缓存可复用；
- [ ] 失败可定位、可日志追踪。

### 17.6 改动边界

- [ ] 只修改 `domains/shared/visual_minutes/`；
- [ ] 不修改 `minutes`；
- [ ] 不修改 `app`；
- [ ] 不修改 `domains/meeting`；
- [ ] 不修改 `core`；
- [ ] 不新增 API 路由；
- [ ] 不新增后台任务；
- [ ] 不依赖会议运行态；
- [ ] 仅保留 `minutes_markdown + meeting_transcript` 输入契约。

---

## 十八、最终原则

```text
纪要正文是唯一不可变内容
视觉只是增强层
Planner 负责判断
Extractor 负责抽取
Master 负责全局通览
Validator 负责保真
Renderer 负责确定性呈现
Compositor 负责精确插入
```

核心要求：

> **LLM 只产出语义视觉 IR，不产出最终排版；每个 section 独立判断；没有足够数据和证据就不出图；开篇通览图必须存在且覆盖全部一级栏目；纪要正文一字不改。**

> **visual_minutes 保持独立能力：只接收 minutes_markdown + meeting_transcript，只输出 HTML / IR / warnings；不接入 minutes，不修改任何外部代码。**
