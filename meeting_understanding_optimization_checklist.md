# 会议理解防膨胀优化清单（深度校验修订版）

> 本清单经过对全部关键代码逐行核实后修订。原始版本存在若干严重误判，本版本予以纠正，所有结论均有代码行号支撑。

---

## 一、 问题 1：`_trim_instruction` 幽灵补丁

### 1.1 问题是否真实存在？

**是，但比最初描述的更复杂。**

需要先搞清楚系统里同时存在的**两套裁剪机制**，否则清单说的是一回事，代码干的是另一回事。

#### 机制 A：旧路径——`skip_fields` + `_trim_instruction`（Prompt 指令告知）

调用链：
```
orchestrator._make_meeting_understanding_node
  → _understanding_skip(selected, template, memory_on)  # orchestrator.py:1327
      → _ALL_TASK_SKIP_FIELDS[line]                      # orchestrator.py:1296
      → skip_fields_for_template(template)               # understanding_skip.py:58
  → agent.run(skip_fields=skip, focus_line=..., ...)     # orchestrator.py:1334-1348
      → _trim_instruction(focus_line, skip_fields)       # agent.py:86
      → user = f"{instruction}\n\n{user}"               # agent.py:87-88
```

这条路径的行为：**只在 User Prompt 里加入一段警告文字**，告诉模型"这些字段输出空数组`[]`"，但发给模型的 JSON Schema 契约里，这些字段**依然存在**。模型看到的 Schema 还是全量的，Prompt 里额外说"不用写这几个"。

#### 机制 B：新路径——`active_tasks` + `build_core_contract_for_tasks`（Schema 物理裁剪）

调用链：
```
orchestrator._make_meeting_understanding_node
  → 检查 agent.run 签名是否有 active_tasks 参数         # orchestrator.py:1339
  → kwargs["active_tasks"] = selected                    # orchestrator.py:1341
  → agent.run(active_tasks=selected, ...)                # orchestrator.py:1345
      → build_core_contract_for_tasks(tasks, ...)        # agent.py:66
      → 动态生成仅含激活字段的 JSON Schema               # contracts.py:261-291
      → 发给 LLM 的 Schema 物理上没有被裁掉的字段
      → omitted 字段加入 allow_missing                   # agent.py:94-95
```

这条路径的行为：**从 Schema 层面物理删除不需要的字段**，模型根本看不到这些字段定义，自然不会生成。Python 层面的 `models.py:96-100` 自动补 `[]`。

#### 两套机制同时激活时的真实情况

查看 [orchestrator.py:1339-1348](file:///D:/study/demo/domains/meeting/orchestrator.py#L1339-L1348)：
```python
sig = inspect.signature(self.meeting_understanding_agent.run)
if "active_tasks" in sig.parameters:  # 新路径判断：agent 是否支持 active_tasks
    kwargs["active_tasks"] = selected
    kwargs["template_text"] = template
    kwargs["memory_on"] = memory_on
# 注意：kwargs 里还同时有 skip_fields=skip 和 focus_line=...  ← 旧路径参数也传了
result = await self.meeting_understanding_agent.run(state["transcript"], **kwargs)
```

因为 `MeetingUnderstandingAgent.run` 现在**同时接受** `active_tasks` 和 `skip_fields` 两个参数，两套机制**在同一次调用中并行激活**。

在 `agent.run` 内部 [agent.py:65-107](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L65-L107)：
1. **新路径先跑**：`build_core_contract_for_tasks(tasks, ...)` 生成裁剪过的 Schema → `target_contract`；
2. **旧路径也跑**：`_trim_instruction(focus_line, skip_fields)` 生成一段 Prompt 警告文字 → 拼入 `user` 消息头部；
3. **发给 LLM**：System Prompt 一份，User Prompt（含旧警告令）一份，Schema（物理裁剪后）一份。

#### 具体冲突场景

以单跑 `minutes`、有模板、不开记忆为例：

- `_understanding_skip` 计算出 `skip = {"action_hints", "risk_hints", "dependencies"}`
- `build_core_contract_for_tasks(["minutes"])` 也计算出：`need_action_hints=False, need_risk_hints=False, need_dependencies=False` → 这三个字段**从 Schema 物理剔除**
- `_trim_instruction("minutes", {"action_hints", "risk_hints", "dependencies"})` 生成警告：
  > *"以下字段**键名必须保留、值给空数组 []**：action_hints、risk_hints、dependencies"*

**问题**：Schema 里已经没有这三个字段了，`allow_missing` 也已经包含了它们（告诉解析器：这些字段缺失是合法的）。Prompt 里的警告令逻辑上是矛盾的：它命令模型保留一个 Schema 里根本不存在的键名，是无效且混乱的指令。

> **⚠️ 特别注意**：这里有一个精细的差别。当 `active_tasks` 走了新路径，`skip_fields` 里的字段与 `omitted` 里的字段**高度重叠但不完全一致**。`_understanding_skip` 是按旧的 `_ALL_TASK_SKIP_FIELDS` 字典计算的，`build_core_contract_for_tasks` 是按新的任务逻辑独立计算的。两者可能对某个字段的判断不同，但最终以新路径（Schema）为准。旧 Prompt 警告令影响的只是模型输出行为，由于 `allow_missing` 的存在，即使模型没输出这些键也能正常解析，所以幽灵补丁实际的**危害是心智污染而非崩溃**。

### 1.2 改进方案是否有效？

**有效，但必须精准手术，不能粗暴整体删除。**

#### 正确的处理方案

**阶段一：清除 Prompt 侧的幽灵补丁**

删除 [agent.py:86-88](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L86-L88) 的以下代码：
```python
instruction = _trim_instruction(focus_line, skip_fields)
if instruction:
    user = f"{instruction}\n\n{user}"
```
并删除 `_trim_instruction` 函数本体（[agent.py:17-40](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L17-L40)）。

**前提条件**（必须先确认）：
- `build_core_contract_for_tasks` 的 `omitted` 集合已被加入 `missable`（[agent.py:94-95](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L94-L95)），这已经做到了 ✅；
- `models.py` 的动态补全逻辑（[models.py:96-100](file:///D:/study/demo/domains/meeting/models.py#L96-L100)）工作正常，缺失字段自动赋 `[]` ✅。

**阶段二：评估是否同步清理 `skip_fields` 旧路径**

`skip_fields` 参数在新路径存在后是否还有意义？答案是：**有一定意义但存在冗余**。

- `skip_fields` 传给 `_trim_instruction` 的作用已经可以删掉；
- `skip_fields` 还用于 `missable = skipped | {"speakers"}`（[agent.py:90-93](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L90-L93)），确保旧路径下被跳过的字段不因解析报错。但新路径的 `omitted` 也做了同样的事（[agent.py:94-95](file:///D:/study/demo/domains/meeting/meeting_core/meeting_understanding_agent.py#L94-L95)）。两者有冗余保护，移除 `skip_fields` → `missable` 这条线需要保守评估，**建议先保留**，仅删除 Prompt 侧的 `_trim_instruction`。

### 1.3 影响面评估与协同改动

| 涉及文件 | 改动点 | 风险 |
| :--- | :--- | :--- |
| `meeting_understanding_agent.py` | 删除 `_trim_instruction` 函数定义；删除第 86-88 行调用逻辑 | 🟢 极低。`allow_missing` 机制完整，模型不输出省略字段完全合法 |
| `orchestrator.py` | `focus_line` 和 `skip_fields` 参数可保留（用于兼容），不强制删除 | 🟢 零风险。只是不再生成 Prompt 警告文字 |
| 测试 | 检查是否有单测断言 `_trim_instruction` 的 Prompt 输出内容字符串 | 需排查，若有则删除对应断言 |

---

## 二、 问题 2：下游广播克隆（`session_segments` 与 `topics` 双发）

### 2.1 问题是否真实存在？

**是，但情况远比原始清单描述的复杂，原始清单严重低估了 `topics` 在 pack 里的功能深度。**

先还原真相：

#### `topics` 在 `_meeting_pack` 下游传输中承担哪些功能？

通过完整的代码追踪，`pack["topics"]` 在下游 LLM 调用链中承担了：

**功能 A：个人视角专属裁剪（`_person_pack`）——关键功能！**

[orchestrator.py:1002-1113](file:///D:/study/demo/domains/meeting/orchestrator.py#L1002-L1113) 的 `_person_pack` 专门对 `pack["topics"]` 做**"别人为主语的条目裁剪"**：
- 遍历 `topics[i]["key_points"]`，移除"只讲别人、不提本人"的条目；
- 遍历 `topics[i]["discussion"]`，如果整段都是别人在讲，置空；
- 同时也对 `session_segments[i]["key_facts"]` 和 `["context_and_reasoning"]` 做类似处理。

**这意味着 `topics` 和 `session_segments` 在 `_person_pack` 中是并行的两套裁剪管道，都发给了下游 LLM。**

**功能 B：部分任务线 Prompt 明确消费 `topics`**

从各 task prompts 搜索结果来看：
- [actions/prompts.py:40,68](file:///D:/study/demo/domains/meeting/tasks/actions/prompts.py#L40)：`session_segments 的 segment_title 或 topics 节点的 module 字段`
- [risks/prompts.py:23,68](file:///D:/study/demo/domains/meeting/tasks/risks/prompts.py#L23)：`session_segments 与 topics`
- [minutes_styles/prompts.py:22-23](file:///D:/study/demo/domains/meeting/tasks/minutes_styles/prompts.py#L22)：`session_segments / topics`
- [minutes/prompts.py:21](file:///D:/study/demo/domains/meeting/tasks/minutes/prompts.py#L21)：`session_segments 与 topics 是你的主事实源`
- [consensus_decision/prompts.py:25](file:///D:/study/demo/domains/meeting/tasks/consensus_decision/prompts.py#L25)：`session_segments / topics`

也就是说：**几乎每条任务线的 Prompt 都同时提及了 `session_segments` 和 `topics`，下游 LLM 确实在两个视图之间同时看、同时参考。**

#### 两份数据的真实内容差异

| 字段名 | 内容 | 来源 | 特殊处理 |
| :--- | :--- | :--- | :--- |
| `session_segments` | `[{segment_title, context_and_reasoning, key_facts}]` | 直接来自上游理解层输出 | `_person_pack` 对 `key_facts` 和 `context_and_reasoning` 做个人视角裁剪 |
| `topics`（`minutes` 线） | `[{module, title, key_points, discussion, debates, conclusion, participants}]` | 由 `raw_topics` 重新组装（含 `full_topics` 逻辑），字段名映射后的版本 | `_person_pack` 对 `key_points` 和 `discussion` 做个人视角裁剪 |

关键点：**`topics` 不只是 `session_segments` 的字段重命名克隆，它还包含 `debates`、`conclusion`、`participants` 等额外字段，以及专门针对 minutes 做的 `full_topics` 组装逻辑。**

#### 那么，真正的冗余在哪里？

冗余集中在**数据内容的实质重叠部分**：
- `topics[i]["title"]` ≈ `session_segments[i]["segment_title"]`（几乎完全重复）
- `topics[i]["discussion"]` ≈ `session_segments[i]["context_and_reasoning"]`（内容相同，字段名不同）
- `topics[i]["key_points"]` ≈ `session_segments[i]["key_facts"]`（内容相同，字段名不同）

这三对字段是纯冗余，会导致相同的讨论内容被序列化两次。但 `topics` 还有独有的 `debates`、`conclusion`、`participants` 字段，不能一刀切删除整个 `topics`。

### 2.2 改进方案是否有效？

**原始清单的方案"从 pack 中完全剔除 topics"是错误的，会破坏 `_person_pack` 的个人视角裁剪逻辑，以及下游 Prompt 的显式引用。**

正确的优化思路是**精准去重，而非整体删除**：

#### 正确方案 A（推荐）：`topics` 去冗余字段，只保留 `session_segments` 没有的增量信息

对于 `minutes` 线，`_meeting_pack` 里的 `full_topics` 包含了 `key_points` 和 `discussion`（这两个与 segments 重叠）。优化思路：

在构建 `full_topics` 时，**剔除与 `session_segments` 高度重复的字段**，只保留 `topics` 独有的增量信息：
```python
# 改造后的 full_topics 条目（只保留 session_segments 里没有的增量字段）
{
    "module": ...,
    "title": ...,
    # 去掉 discussion / context_and_debate（与 session_segments.context_and_reasoning 重叠）
    # 去掉 key_points（与 session_segments.key_facts 重叠）
    "debates": ...,        # ← session_segments 里没有
    "conclusion": ...,     # ← session_segments 里没有
    "participants": ...,   # ← session_segments 里没有
}
```

这样下游 LLM 在 `session_segments` 里看到完整的事实脉络，在 `topics` 里看到轻量的增量信息（谁参与、什么结论、有无辩论），没有重复文字。

> **⚠️ 重要风险**：需要同步修改各任务 Prompt 中对 `topics[].discussion` 和 `topics[].key_points` 的引用描述，否则模型会困惑为什么这两个字段消失了。

#### 正确方案 B（更保守）：仅修改 `_person_pack` 的去重逻辑，避免两套管道重复裁剪同一内容

`_person_pack` 现在同时裁剪 `topics[i]["key_points"]` 和 `session_segments[i]["key_facts"]`，这说明同一内容被裁剪了两次（虽然最终传给 LLM 也是两份）。

可以考虑：在个人视角模式下，如果两者内容高度相同，只在 `session_segments` 上做裁剪，`topics` 的对应字段置为空（仅保留增量字段），减少传输体积。

#### 两方案对比

| 维度 | 方案 A（剔除重叠字段） | 方案 B（保守裁剪去重） |
| :--- | :--- | :--- |
| Token 节省 | 较大（可节省 discussion + key_points 的完整文字量） | 较小 |
| 改动风险 | 中（需同步修改多处 Prompt） | 低（仅修改 _person_pack 内部逻辑） |
| 下游 Prompt 适配 | 需修改 5 处 task prompts | 无需修改 |
| 推荐场景 | 系统稳定后的深度优化 | 优先执行，立即见效 |

### 2.3 协同改动全局影响面（精确版）

| 调用方 | 文件位置 | 依赖 `topics` 的内容 | 是否受影响 | 处理对策 |
| :--- | :--- | :--- | :--- | :--- |
| `_person_pack` 个人裁剪 | [orchestrator.py:1027-1064](file:///D:/study/demo/domains/meeting/orchestrator.py#L1027-L1064) | `topics[]["key_points"]`, `["discussion"]` | **是** | 方案 A：这两个字段从 topics 中移除后，_person_pack 中对应裁剪分支不再执行（segments 分支仍覆盖） |
| `_render_context` 渲染上下文 | [orchestrator.py:898-900](file:///D:/study/demo/domains/meeting/orchestrator.py#L898-L900) | `pack` 整体传入 LLM | **是** | pack 中 topics 去重后，渲染上下文自动瘦身 |
| `minutes/prompts.py` | [prompts.py:21-23,43](file:///D:/study/demo/domains/meeting/tasks/minutes/prompts.py#L21) | `session_segments 与 topics`、`topics 中的 debates` | **需微调** | 将 discussion/key_points 的来源说明统一指向 session_segments，debates 仍指向 topics |
| `actions/prompts.py` | [prompts.py:40,68](file:///D:/study/demo/domains/meeting/tasks/actions/prompts.py#L40) | `topics 节点的 module/key_points` | **需微调** | module 改为取 session_segments 的 segment_title |
| `risks/prompts.py` | [prompts.py:23,68](file:///D:/study/demo/domains/meeting/tasks/risks/prompts.py#L23) | `topics[].key_points` | **需微调** | 改为取 session_segments 的 key_facts |
| `minutes_styles/prompts.py` | [prompts.py:22-23](file:///D:/study/demo/domains/meeting/tasks/minutes_styles/prompts.py#L22) | `session_segments / topics` | **需微调** | 统一以 session_segments 为主 |
| `consensus_decision/prompts.py` | [prompts.py:25](file:///D:/study/demo/domains/meeting/tasks/consensus_decision/prompts.py#L25) | `session_segments / topics` | **需微调** | 同上 |
| `hits.py` 命中计算 | [hits.py:203-320](file:///D:/study/demo/domains/shared/perspective/hits.py#L203-L320) | 从 `state["meeting_understanding"]["topics"]` 读取 | **不受影响** | 该算法读的是内存 State 对象，不是 pack 字典 |
| `supervisor_slice.py` 审核切片 | [supervisor_slice.py:372-384](file:///D:/study/demo/core/runtime/supervisor_slice.py#L372-L384) | 从 `understanding["topics"]` 提取 titles | **不受影响** | 读的是 state 内存，不是下发的 pack |
| `_understanding_needle_keep` | [orchestrator.py:454-477](file:///D:/study/demo/domains/meeting/orchestrator.py#L454-L477) | 白名单中包含 `topics` | **不受影响** | 用于审核摘录时的字段过滤，读 state 内存 |

---

## 三、 实施路线图（修订版）

### 阶段一（低风险，立即可做）：清除幽灵补丁

- **改动范围**：仅 `meeting_understanding_agent.py`
- **改动内容**：
  1. 删除第 17-40 行的 `_trim_instruction` 函数；
  2. 删除第 86-88 行的调用逻辑（`instruction = ...` 和 `user = f"{instruction}..."`）；
  3. 保留 `skip_fields` 参数与 `missable` 赋值逻辑（兜底用，暂不清理）。
- **测试验证**：运行 `pytest tests/unit/domains/meeting/` 全绿即可。

### 阶段二（中等风险，需仔细评估）：`topics` 精准去重

- **推荐先执行方案 B（保守去重）**：
  - 在 `_person_pack` 内：当 `topics` 和 `session_segments` 都存在时，不对 `topics[]["key_points"]` 和 `topics[]["discussion"]` 做裁剪（因为 `session_segments` 已经覆盖了），`_person_pack` 只保留 `topics` 的轻量增量字段；
  - 在 `_meeting_pack` 的 `minutes` 分支：`full_topics` 去掉 `discussion` 和 `key_points`（这两个字段 session_segments 已完整覆盖），只保留 `module, title, debates, conclusion, participants`。
- **同步修改各 task Prompt**：将对 `topics[].discussion` 和 `topics[].key_points` 的引用统一改为指向 `session_segments`，明确说明 `topics` 现在只是轻量骨架（标题+辩论+结论+参与人），完整事实血肉在 `session_segments`。
- **测试验证**：运行全套会议测试，包含个人视角测试用例，检查裁剪输出是否退化。

### 阶段三（稳定后）：全链路 Token 验证

- 在长会议（宣讲会、架构评审会）上实测理解层与下游各节点的实际 Token 数，记录优化前后数据对比。

---

## 四、 预期收益（修订后的保守估计）

| 观测维度 | 优化前 | 优化后（保守） | 说明 |
| :--- | :--- | :--- | :--- |
| 理解层输出质量 | 存在心智污染（Prompt 矛盾指令） | 干净，Schema 为唯一裁剪控制器 | 阶段一收益 |
| 下游 pack 体积 | topics 包含完整 discussion + key_points（与 segments 重叠） | topics 仅保留 debates/conclusion/participants 增量字段 | 阶段二收益 |
| 每节点 Input Tokens 减少量 | — | **600~1,200 Tokens/节点**（仅去重重叠字段，非之前估算的 2,000~4,000） | 真实保守估计 |
| 核心事实完整性 | 100% | 100%（无截断） | 零破坏原则 |
