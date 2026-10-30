# Actions 审核后 Calendar 回填与最终渲染执行清单

> 目标：
>
> ```text
> actions Agent
> → Supervisor 审核通过
> → [开关 on] calendar 批量回填
> → 程序渲染 Markdown
> ```
>
> 本次改造只涉及 actions 线的**后处理与渲染**，不改变 actions Agent 的抽取规则，也不改变 Supervisor 的审核规则。

---

## 一、最终目标

### 开关关闭

```text
不调用 calendar
不生成 deadline_time
渲染使用原始 deadline
时间节点展示会议中的原始说法
```

例如：

```text
 - 时间节点：这周或下周初
```

### 开关开启

```text
调用 calendar 批量解析
回填 deadline_time / range 字段
渲染优先使用绝对时间
```

例如：

```text
 - 时间节点：2026/10/30 ~ 2026/11/04
```

如果 calendar 解析失败：

```text
回退原始 deadline
```

---

## 二、执行位置

### 2.1 当前链路

```text
actions_agent
→ actions_supervisor
→ END
→ 图外程序渲染
```

### 2.2 目标链路

```text
actions_agent
→ actions_supervisor 审核通过
→ actions 异步 pre-render hook
   → 前处理：收集 raw deadline
   → 调用 calendar：一次批量
   → 后处理：按索引回填
→ 程序 render_items() 输出 Markdown
```

### 2.3 不建议的位置

不要放在：

- actions Agent 内部
- Supervisor 内部
- 同步的 `render_draft()`
- 全局 graph 结束后统一执行

推荐：

```text
在 render producer 中增加 actions 专用异步 pre-render hook
```

原因：

- actions 需要 `await calendar`
- 其他线不应等待 calendar
- 多线 actions + minutes 时，minutes 不能被 calendar 阻塞
- hook 发生在图执行完成、审核通过之后

---

## 三、`.env` 开关

### 3.1 开关名

```text
ACTIONS_CALENDAR_BACKFILL
```

### 3.2 取值

```text
off / on
```

可选兼容：

```text
false / true
0 / 1
no / yes
```

建议默认：

```text
ACTIONS_CALENDAR_BACKFILL=off
```

### 3.3 行为

| 开关 | calendar | 输出字段 | 渲染时间 |
|---|---|---|---|
| `off` | 不调用 | 不输出派生字段 | 原始 `deadline` |
| `on` | 批量调用 | 输出派生字段 | 绝对时间优先，失败回退 raw |

### 3.4 开关读取

建议在 `domains/meeting/domain_config.py` 增加：

```python
def actions_calendar_backfill_enabled() -> bool:
    value = (os.getenv("ACTIONS_CALENDAR_BACKFILL") or "off").strip().lower()
    return value in {"1", "true", "on", "yes"}
```

非法值按 `off` 处理，并记录日志。

---

## 四、会议开始时间

calendar 必须基于准确的会议开始时间，不能用系统当前时间。

### 4.1 当前状态

`App` 层已经有：

```text
extra.time → _Prepared.time → runner meeting_time
```

但 `run_streaming` 没有把 `meeting_time` 放进 `MeetingState`。

### 4.2 需要改造

- [ ] `MeetingState` 增加：

```python
meeting_time: str
```

- [ ] `DomainNodes.run_streaming()` 增加参数：

```python
meeting_time: str = ""
```

- [ ] `initial_state` 写入：

```python
"meeting_time": meeting_time
```

- [ ] `core/runner/runner.py` 的 `streaming_kwargs` 传入：

```python
"meeting_time": meeting_time
```

### 4.3 缺失会议时间

如果 `meeting_time` 为空：

```text
不调用 calendar
deadline_time = null
保留 raw deadline
记录 warning
```

不能使用 `datetime.now()` 代替会议时间。

---

## 五、前处理

### 5.1 输入

Supervisor 审核通过后的 actions 草稿：

```json
{
  "actions": [
    {"title": "A", "deadline": "周五"},
    {"title": "B", "deadline": null},
    {"title": "C", "deadline": "这周或下周初"}
  ]
}
```

### 5.2 收集规则

- 只收集非空 `deadline`
- 保留原始 actions 索引
- 不因为 null 项而错位
- `deadline` 为 `""` 时视为空
- 全部为空时直接跳过 calendar

组装：

```json
{
  "pending": [
    {"batch_index": 0, "action_index": 0, "deadline": "周五"},
    {"batch_index": 1, "action_index": 2, "deadline": "这周或下周初"}
  ],
  "texts": ["周五", "这周或下周初"]
}
```

必须保存：

```text
batch_index → action_index
```

不能直接使用过滤后的数组下标回填。

---

## 六、调用 calendar

### 6.1 调用方式

```python
from infra.calendar import CalendarLLM, run_deadline_agent

result = await run_deadline_agent(
    meeting_start_time=state["meeting_time"],
    texts=texts,
    client=CalendarLLM(self.client),
)
```

要求：

- 只调用一次
- 复用当前 `LLMClient`
- 不新建 API Key
- calendar 内部先 Fast-Path，复杂项才走部署版 LLM
- `CalendarLLM` 走 `infra.llm.LLMClient.text(json_mode=True)`

### 6.2 不调用的情况

- 开关关闭
- 草稿降级
- actions 为空
- 所有 deadline 为空
- 会议时间为空

### 6.3 调用结果

calendar 返回：

```json
{
  "index": 1,
  "raw": "这周或下周初",
  "deadline": "2026/11/04",
  "deadline_start": "2026/10/30",
  "deadline_end": "2026/11/04",
  "time_slot": null,
  "kind": "range",
  "error": null
}
```

---

## 七、后处理回填

### 7.1 字段映射

| calendar 字段 | action 字段 |
|---|---|
| `deadline` | `deadline_time` |
| `deadline_start` | `deadline_start` |
| `deadline_end` | `deadline_end` |
| `time_slot` | `deadline_time_slot` |
| `kind` | `deadline_kind` |

### 7.2 回填规则

按：

```text
batch_index → action_index
```

回填。

原始 `deadline` 永远保留。

单点：

```json
{
  "deadline": "周五",
  "deadline_time": "2026/10/31",
  "deadline_start": null,
  "deadline_end": null,
  "deadline_time_slot": null,
  "deadline_kind": "date"
}
```

范围：

```json
{
  "deadline": "这周或下周初",
  "deadline_time": "2026/11/04",
  "deadline_start": "2026/10/30",
  "deadline_end": "2026/11/04",
  "deadline_time_slot": null,
  "deadline_kind": "range"
}
```

模糊时段：

```json
{
  "deadline": "明天下午",
  "deadline_time": "2026/10/31",
  "deadline_start": null,
  "deadline_end": null,
  "deadline_time_slot": "下午",
  "deadline_kind": "date"
}
```

### 7.3 失败处理

单条失败：

```text
deadline_time = null
deadline_start = null
deadline_end = null
deadline_time_slot = null
deadline_kind = "none"
保留 raw deadline
```

整批失败：

```text
所有 pending 项同样回填 null
保留 raw deadline
记录 warning
不阻断 actions 渲染
```

### 7.4 不回填的情况

- raw deadline 为 null：不送 calendar，不写派生字段或写 null
- actions 审核未通过 / 降级：跳过
- 开关关闭：完全不写派生字段

### 7.5 是否需要重新审核

不需要。

原因：

- calendar 只生成派生时间
- 不改变 raw deadline
- 不改变 title / item / owner / evidence
- 不重新走 Supervisor

---

## 八、Contract 修改

### 8.1 生成契约不变

Actions Agent 仍然只输出 8 字段：

```text
title
item
owner
deadline
collaborators
acceptance_criteria
dependency
evidence
```

不要把：

```text
deadline_time
deadline_start
deadline_end
deadline_time_slot
deadline_kind
```

加入 actions Agent 的生成契约。

这些字段是后处理派生字段。

### 8.2 最终 action 可选字段

开关开启时，最终 action 可以包含：

```json
{
  "deadline": "这周或下周初",
  "deadline_time": "2026/11/04",
  "deadline_start": "2026/10/30",
  "deadline_end": "2026/11/04",
  "deadline_time_slot": null,
  "deadline_kind": "range"
}
```

字段定义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `deadline_time` | string \| null | 绝对时间；range 时为结束日 |
| `deadline_start` | string \| null | range 开始 |
| `deadline_end` | string \| null | range 结束 |
| `deadline_time_slot` | string \| null | 上午/中午/下午/晚上/下班前 |
| `deadline_kind` | string \| null | date / datetime / range / none |

### 8.3 开关关闭

按你的要求：

```text
不输出任何派生字段
只保留原始 deadline
```

最终仍是 8 字段。

### 8.4 校验器修改

`ActionItemsReport` 的 `_action` 当前严格限制字段。

需要把派生字段加入 allowed：

```text
deadline_time
deadline_start
deadline_end
deadline_time_slot
deadline_kind
```

但不要把它们设为 required。

### 8.5 不改动

- `ActionItems` 模型仍是浅校验的 `actions: list[dict]`
- `ActionItemsReport.actions` 仍是 list[dict]
- 不需要 codegen
- 不需要修改 actions generation contract
- 不需要修改 Supervisor 契约

---

## 九、渲染优先级

程序渲染使用一个统一函数：

```text
format_time_node(action, backfill_enabled)
```

优先级：

```text
1. 开关关闭 → raw deadline
2. kind == range 且有 start/end → start ~ end
3. 有 deadline_time → 单点绝对时间
4. 有 raw deadline → raw
5. 都没有 → 不输出时间节点行
```

---

## 十、渲染分支

### 10.1 开关关闭

```json
{"deadline": "周五"}
```

输出：

```text
 - 时间节点：周五
```

如果 `deadline` 为 null，整行不输出。

---

### 10.2 单点日期

```json
{
  "deadline_time": "2026/10/31",
  "deadline_kind": "date"
}
```

输出：

```text
 - 时间节点：2026/10/31
```

---

### 10.3 单点日期时间

```json
{
  "deadline_time": "2026/10/31 15:00",
  "deadline_kind": "datetime"
}
```

输出：

```text
 - 时间节点：2026/10/31 15:00
```

---

### 10.4 模糊时段

```json
{
  "deadline_time": "2026/10/31",
  "deadline_time_slot": "下午",
  "deadline_kind": "date"
}
```

输出：

```text
 - 时间节点：2026/10/31 下午
```

如果 `deadline_time` 已经带具体时间：

```text
2026/10/31 15:00
```

则忽略 `deadline_time_slot`，避免重复。

---

### 10.5 范围

```json
{
  "deadline_start": "2026/10/30",
  "deadline_end": "2026/11/04",
  "deadline_kind": "range"
}
```

输出：

```text
 - 时间节点：2026/10/30 ~ 2026/11/04
```

推荐分隔符：

```text
~
```

不建议用 `-`，避免和日期格式混淆。

---

### 10.6 范围起止同一天

```json
{
  "deadline_start": "2026/10/31",
  "deadline_end": "2026/10/31"
}
```

输出：

```text
 - 时间节点：2026/10/31
```

不要输出：

```text
2026/10/31 ~ 2026/10/31
```

---

### 10.7 范围只有一端

只有 start：

```text
 - 时间节点：2026/10/30
```

只有 end：

```text
 - 时间节点：2026/11/04
```

不要输出：

```text
2026/10/30 ~ null
```

---

### 10.8 calendar 失败

```json
{
  "deadline": "预计三天",
  "deadline_time": null,
  "deadline_kind": "none"
}
```

输出：

```text
 - 时间节点：预计三天
```

---

### 10.9 完全没有时间

```json
{
  "deadline": null,
  "deadline_time": null
}
```

不输出：

```text
 - 时间节点：
```

直接省略整行。

---

### 10.10 字段不完整或旧数据

兼容规则：

```text
有 start/end → 按 range
只有 deadline_time → 按单点
没有绝对时间 → 回退 raw
都没有 → 省略
```

`deadline_kind` 只作为优先判断，不是唯一依据。

---

## 十一、完整 Markdown 示例

### 单点

```text
**涡轮机运行确认**： EPC需提供合同确认函，确认涡轮机可运行（责任方：EPC 配合方：李四、王五）
 - 时间节点：2026/10/31
 - 前置依赖：等待测试环境就绪
 - 验收交付：涡轮机可运行
```

### 范围

```text
**确认微服务测试负责人**： 确认微服务接口的测试负责人，并跟进测试安排（责任方：武思华）
 - 时间节点：2026/10/30 ~ 2026/11/04
 - 前置依赖：等待测试环境就绪
 - 验收交付：测试负责人确认
```

### 时段

```text
**查看标题报告**： 查看子浩出的标题相关报告（责任方：申家坤）
 - 时间节点：2026/10/31 下午
 - 验收交付：报告已查看
```

### 回退

```text
**完成博客数据标注**： 完成博客数据的千问三中达标（责任方：郭镨岳）
 - 时间节点：预计三天
 - 验收交付：千问三中达标
```

---

## 十二、代码改动点

| 文件 | 改动 |
|---|---|
| `.env` | 增加 `ACTIONS_CALENDAR_BACKFILL=off` |
| `domains/meeting/domain_config.py` | 增加开关读取函数 |
| `domains/meeting/models.py` | `MeetingState` 增加 `meeting_time` |
| `core/graph/nodes.py` | `run_streaming` 增加 `meeting_time`；initial_state 写入；增加异步 pre-render hook 默认实现 |
| `core/runtime/render.py` | `produce_line` 在渲染前 await actions pre-render hook |
| `core/runner/runner.py` | `streaming_kwargs` 传入 `meeting_time` |
| `domains/meeting/orchestrator.py` | actions 异步 pre-render hook：前处理、调用 calendar、后处理回填 |
| `domains/meeting/tasks/actions/steps/actions_render.py` | 增加时间节点格式化优先级 |
| `core/schema/validation.py` | `_action` allowed 增加派生字段 |
| `infra/calendar/` | 复用现有 `CalendarLLM` / `run_deadline_agent` |

---

## 十三、执行顺序

### Phase 0：开关与时间

- [ ] `.env` 增加 `ACTIONS_CALENDAR_BACKFILL=off`
- [ ] 增加开关读取函数
- [ ] `MeetingState` 增加 `meeting_time`
- [ ] `run_streaming` / runner 传递 `meeting_time`

### Phase 1：pre-render hook

- [ ] `DomainNodes` 增加异步 pre-render hook 默认 no-op
- [ ] `produce_line` 在渲染前 await hook
- [ ] `MeetingAgentSystem` 覆盖 actions hook
- [ ] 其他线不受影响

### Phase 2：前处理

- [ ] 读取审核通过后的 `draft["actions"]`
- [ ] 收集非空 deadline
- [ ] 建立 `batch_index → action_index`
- [ ] 无 pending / 无会议时间时跳过

### Phase 3：calendar 调用

- [ ] 使用 `CalendarLLM(self.client)`
- [ ] 一次批量调用
- [ ] 保留 raw deadline
- [ ] 处理 top-level error

### Phase 4：后处理

- [ ] 按 batch index 回填
- [ ] 单点 / datetime / slot / range 字段
- [ ] 失败回填 null
- [ ] 不重新审核
- [ ] 不阻断渲染

### Phase 5：渲染

- [ ] 开关关闭走 raw
- [ ] 开关开启优先绝对时间
- [ ] range 输出 `start ~ end`
- [ ] 同日 range 退化为单日
- [ ] 单端 range 只输出可用端
- [ ] slot 拼接
- [ ] 无绝对时间回退 raw
- [ ] 全空省略时间节点行

### Phase 6：校验

- [ ] `ActionItemsReport` 允许派生字段
- [ ] 原始 8 字段生成契约不变
- [ ] 开关关闭最终输出仍为 8 字段
- [ ] 开关开启输出包含派生字段
- [ ] actions-only / actions + minutes 均验证
- [ ] 多线时 minutes 不被 calendar 阻塞

---

## 十四、验收用例

### 开关关闭

- [ ] 不调用 calendar
- [ ] 不产生 `deadline_time`
- [ ] Markdown 使用 raw deadline
- [ ] raw 为 null 时省略时间行

### 开关开启

- [ ] 只调用一次 calendar
- [ ] 非空 deadline 才发送
- [ ] null deadline 不发送
- [ ] batch index 回填正确
- [ ] 单点日期正确
- [ ] 单点 datetime 正确
- [ ] 模糊时段正确
- [ ] range 正确
- [ ] 同日 range 正确
- [ ] 单端 range 正确
- [ ] calendar 失败回退 raw
- [ ] 全部失败不阻断渲染
- [ ] 会议时间为空时跳过并保留 raw
- [ ] 多线 actions + minutes 时 minutes 不等待 calendar

---

## 十五、最终验收标准

```text
开关 off：
  不调用 calendar
  不新增派生字段
  时间节点 = 原始 deadline
```

```text
开关 on：
  一次 calendar 批量调用
  deadline_time / start / end / slot / kind 回填
  时间节点优先绝对时间
  range 显示 start ~ end
  失败回退 raw
```

```text
渲染：
  单点：2026/10/31
  datetime：2026/10/31 15:00
  时段：2026/10/31 下午
  range：2026/10/30 ~ 2026/11/04
  空：省略时间节点行
  失败：原始 deadline
```

```text
职责边界：
  actions Agent 只输出 8 字段
  Supervisor 只审核原始内容
  calendar 只做时间派生
  renderer 只做展示
  不重新审核 calendar 结果
```
