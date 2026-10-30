# Actions Agent 一体化重构执行清单

> 本文件是 actions 任务重构的唯一执行清单。
>
> 已合并并替代：
>
> - `ACTIONS_MULTI_SOURCE_AGENT_CHECKLIST.md`
> - `ACTIONS_AGENT_FLAT_CONTRACT_CHECKLIST.md`
>
> 范围：
>
> - actions 输出 contract 改为扁平 `actions[]`
> - 每条待办 8 字段：`title/item/owner/deadline/collaborators/acceptance_criteria/dependency/evidence`
> - 接入 `texts.actions_text`
> - 支持 transcript 必传，keypoints / notes / vision_info 选传
> - actions 仍跳过会议理解与视角建模

---

## 〇、结论先行：最佳落地路线

不要按“contract → model → prompt → render”逐层横切。

最佳路线是：

```text
Phase 0  冻结 contract 与字段语义
Phase 1  低风险接入 actions_text 输入层（不改输出）
Phase 2  原子切换 contract + prompt + model + supervisor + render
Phase 3  清理旧字段 / 旧测试 / 旧兼容分支
Phase 4  真实 LLM 验收与 Prompt 调优
Phase 5  文档收口
```

### 为什么这样排

1. **输入层可以独立先做**
   - `actions_text` 只是 API / 准备层 / 上下文变化；
   - 不改 contract 时，旧 actions 逻辑仍可运行；
   - 可以先验证 API、多线隔离、`minutes_auxiliary` 不受污染。

2. **contract、prompt、model、supervisor、render 必须一起切**
   - 只改 contract，旧 Prompt 会输出旧字段；
   - 只改 Prompt，结构化校验会拒绝新字段；
   - 只改 Render，草稿仍是旧结构；
   - 因此 Phase 2 必须是一个原子纵向切片。

3. **清理必须放在行为稳定之后**
   - 先把新链路跑通；
   - 再删除 `assigned_actions` / `unassigned_actions` / `category` / `task` 的旧引用；
   - 避免边改边删导致无法定位问题。

4. **真实 LLM 验收必须最后做**
   - FakeLLM 只能验证结构和拼装；
   - title 质量、deadline 剥离、actions_text 覆盖、误标处理只能靠真实模型验证。

---

## 一、目标 Contract

### 1.1 最终输出

```json
{
  "actions": [
    {
      "title": "涡轮机运行确认",
      "item": "EPC需提供合同确认函，确认涡轮机可运行",
      "owner": "EPC",
      "deadline": "周五",
      "collaborators": ["李四"],
      "acceptance_criteria": "涡轮机可运行",
      "dependency": "等待测试环境就绪",
      "evidence": "EPC需提供合同确认函，确认涡轮机可运行"
    }
  ]
}
```

### 1.2 顶层结构

```text
ActionItems
└── actions: ActionItem[]
```

要求：

- [ ] 顶层只有一个 `actions` 字段
- [ ] `actions` 必须是数组
- [ ] 没有待办时输出 `{"actions": []}`
- [ ] 不再输出 `assigned_actions` / `unassigned_actions`
- [ ] 不再输出 `category`
- [ ] 不输出任何额外字段
- [ ] 不输出 Markdown / 解释 / 代码块包裹

### 1.3 字段定义

| 字段 | 类型 | 必填 | 空值 | 说明 |
|---|---|---|---|---|
| `title` | string | 是 | 不允许空 | 展示用小标题，概括 `item` |
| `item` | string | 是 | 不允许空 | 剥离 deadline 后的待办正文 |
| `owner` | string \| null | 否 | null | 明确负责人；未明确为 null |
| `deadline` | string \| null | 否 | null | 原文时间表达；未明确为 null |
| `collaborators` | string[] | 否 | [] | 协同方数组；每个元素一个对象 |
| `acceptance_criteria` | string \| null | 否 | null | 明确验收标准；未明确为 null |
| `dependency` | string \| null | 否 | null | 明确前置依赖；未明确为 null |
| `evidence` | string | 是 | 不允许空 | 原文或 actions_text 的可定位摘录 |

### 1.4 字段顺序

固定为：

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

### 1.5 空值规范

- 可选字段无内容时统一 `null`
- 不要输出 `""`、`"无"`、`"未提及"`、`"未明确"`、`"待定"`、`"待确认"`、`"-"`
- `owner = null` 表示未分配
- `collaborators` 使用数组 `["李四", "王五"]`，无协同方为 `[]`
- `actions` 为空时输出 `[]`

### 1.6 assigned / unassigned 的派生

模型不再输出两组数组。

```text
owner != null → 已分配
owner == null → 未分配
```

渲染层或消费方需要时自行派生：

```python
assigned = [a for a in actions if a.get("owner")]
unassigned = [a for a in actions if not a.get("owner")]
```

---

## 二、字段语义

### 2.1 `title`

- 是 `item` 的展示小标题
- 优先使用“对象 + 动作/结果”的短语
- 建议 4～12 个汉字，不强制长度
- 不包含 deadline
- 不包含“待办”“事项”“任务”等无信息前缀
- 不使用序号、引号、Markdown 符号
- 不重复整句 `item`
- 不引入 `item` / 原文没有的新事实

示例：

```text
item: EPC需提供合同确认函，确认涡轮机可运行
title: 涡轮机运行确认

item: 完成回归测试并提交测试报告
title: 回归测试与报告提交
```

### 2.2 `item`

- 是可独立执行、可复核的动作句
- 保留动作、对象、关键条件和必要的责任主体
- 将 deadline 时间表达剥离到 `deadline`
- 不把 `title` 当作 `item`
- 不因为剥离时间而丢掉动作语义
- 多个动作 / 负责人 / deadline 时先拆条，再分别剥离时间
- 时间表达不是 deadline 时不要剥离

示例：

```text
原文：EPC需在周五前提供合同确认函，确认涡轮机可运行。
item：EPC需提供合同确认函，确认涡轮机可运行
deadline：周五前
```

### 2.3 `deadline`

- 只放截止时间、完成时间、时间锚点
- 保留原文表达，不在 actions 阶段转绝对日期
- 原文是“周五前”就保留“周五前”
- 原文是“下周一”就保留“下周一”
- 没有明确时间节点时为 `null`
- 不把会议时间、文档创建时间、无关日期放入
- 同一事项多个 deadline 时拆条，不要堆叠

### 2.4 `owner`

- 只记录原文明示的人名、团队、部门、角色
- 未明确为 `null`
- 不从 title、常识或会议角色推断
- 不把“大家”“相关人员”“待确认”“待定”当作 owner

### 2.5 `collaborators`

- 只记录原文明示的协同对象、配合方
- 输出字符串数组，每个元素一个对象
- 没有则为 `[]`
- 不从 owner 推断协同方
- 不把整个团队默认写成协同方
- 渲染时再用“、”连接

### 2.6 `acceptance_criteria`

- 只记录原文明示的验收标准、完成判定、交付物要求
- 没有则为 `null`
- 不用常识补“完成后通知”“按时交付”等通用标准
- 可以与 `item` 有语义重叠，但不得凭空增加新要求

### 2.7 `dependency`

- 只记录原文明示的前置条件、前置动作、外部依赖
- 没有明确前后制约则为 `null`
- 不把普通背景、风险、假设写成依赖
- 不把 deadline 重复写入 dependency

### 2.8 `evidence`

- 必填，非空
- 必须是会议原文或 `actions_text` 中可定位的摘录
- 可以是包含 deadline、owner 的完整原句
- 不能是模型自己总结、改写后的句子
- 每条待办至少有一条可定位证据
- 如果 `actions_text` 本身是可定位的用户标记原文，可以作为 evidence

### 2.9 拆条、去重、排序

#### 拆条

一条 `ActionItem` 对应一个独立动作。出现以下情况必须拆条：

- 多个不同动作
- 多个不同负责人
- 多个不同 deadline
- 多个独立交付物
- 条件触发后各自执行的不同任务

#### 去重

- 同一事项在 transcript 与 `actions_text` 中重复出现 → 合并为一条
- 合并时保留用户标记的行动意图
- `owner` / `deadline` / `acceptance_criteria` 优先采用原文明确事实
- 不得输出两条语义相同的待办

#### 排序

- 按事项在会议原文中首次出现的先后顺序排列
- `actions_text` 补充的事项，按其在 `actions_text` 中出现的位置或原文对应位置插入
- 不按 category、owner、deadline 重新排序

---

## 三、输入契约

### 3.1 `texts` 字段

```text
actions 任务：
  texts.transcript    必传
  texts.keypoints     选传
  texts.notes         选传
  texts.vision_info   选传
  texts.actions_text  选传
```

### 3.2 `actions_text` 语义

`actions_text` 是用户直接标记的待办文本，可能是：

```text
会议原文中的一段摘录
用户整理后的待办片段
用户关注的候选事项
```

它不是结构化 JSON，不是必填，也不要求逐条覆盖。用户可能误标、重复标记、只标关键词。

### 3.3 来源优先级

| 来源 | 定位 | 对最终待办的影响 |
|---|---|---|
| `transcript` | 主事实底座 | 所有事实字段的最终依据 |
| `actions_text` | 用户标记的待办候选 | 尽可能覆盖；不强制逐条出现 |
| `keypoints` | 用户关注点 | 提升召回优先级，不单独证明事实 |
| `notes` | 划线原话 / 笔记 | 划线原话辅助召回；主观批注不得入待办 |
| `vision_info` | OCR 文本 | 补充术语、参数、数字、时间；不脱离原文发散 |

统一规则：

```text
transcript 决定事实。
actions_text 决定“用户希望重点关注什么”。
keypoints / notes / vision_info 只帮助召回与补全。
任何辅助材料都不能单独推断 owner / deadline / acceptance_criteria / dependency。
actions_text 明确写出的字段，且与原文不冲突时，可以采用。
```

### 3.4 上下文格式

`_line_shared_context("actions")` 目标：

```text
【会议原文】
{transcript}

【用户标记待办原文】
{actions_text}

【用户核心关键点】
{keypoints}

【用户划线原话与笔记】
{notes}

【视觉信息参考(OCR)】
{vision_info}
```

要求：

- [ ] 只拼接非空块
- [ ] 不拼接会议理解、视角模型、用户画像、命中表、雷达
- [ ] `actions_text` 只进入 actions 线
- [ ] `actions_text` 不进入 minutes 的 `minutes_auxiliary`
- [ ] actions + minutes 多线时，actions 仍只使用自己的输入

### 3.5 Actions-only 约束

- [ ] actions-only 不构建 `meeting_understanding`
- [ ] actions-only 不构建 `perspective_modeling`
- [ ] actions Agent 不读取会议理解 / 画像 / 视角
- [ ] Supervisor 不读取会议理解 / 画像 / 视角
- [ ] Render 只读草稿与审核结论

---

## 四、Prompt 总体结构

```text
ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
+ ACTIONS_AUX_PROMPT_BLOCK              # 出现任一辅助标签时
+ ACTIONS_TEXT_PROMPT_BLOCK             # 出现【用户标记待办原文】时
+ ACTIONS_KEYPOINTS_PROMPT_BLOCK        # 出现【用户核心关键点】时
+ ACTIONS_NOTES_PROMPT_BLOCK            # 出现【用户划线原话与笔记】时
+ ACTIONS_VISION_PROMPT_BLOCK           # 出现【视觉信息参考(OCR)】时
```

要求：

- [ ] 基础 Prompt 永远存在
- [ ] 辅助块按标签动态追加
- [ ] 无辅助材料时，Prompt 与基础版本一致
- [ ] 不引入 minutes 的 `AGENDA_AUX_PROMPT_BLOCK`
- [ ] 不允许辅助块覆盖基础合同
- [ ] 不允许在 Prompt 中出现 `category` / `assigned_actions` / `unassigned_actions` 的旧口径

---

## 五、基础 Prompt

建议将现有 `ACTION_ITEMS_GENERATION_SYSTEM_PROMPT` 整体替换为：

```text
你是「全员待办事项提取 Agent」。你的任务是从会议材料中提取所有尚未执行完毕、可独立执行、可复核的行动项，并输出扁平的 actions 数组。

你只负责抽取，不负责按业务议题分组，不负责输出“已分配/未分配”两套数组。

## 一、输入与事实优先级

1. 【会议原文】必传，是主事实底座。
2. 【用户标记待办原文】选传，是用户明确关注的候选待办。应尽可能体现在最终 actions 中，但不要求逐条覆盖。
3. 【用户核心关键点】选传，用于提升待办召回率。
4. 【用户划线原话与笔记】选传；划线原话可辅助召回，个人批注不得作为事实。
5. 【视觉信息参考(OCR)】选传，只用于补充术语、参数、数字、时间。
6. 辅助材料与会议原文冲突时，以会议原文为准。
7. 不得从辅助材料单独推断 owner、deadline、acceptance_criteria、dependency；actions_text 明确写出的字段，与原文不冲突时可以采用。
8. 用户标记可能误标、重复或只含关键词；非待办、无行动语义、无原文依据的标记可以不输出。

## 二、什么算待办

应当提取：

- 明确认领与承诺：我来做、我负责、我会在 XX 前完成；
- 明确分配与分工：XX 由 YY 负责、建议由 XX 牵头；
- 明确交付截止：本周五前完成、上线前必须产出；
- 制度与规范落地：建立流程、完善资料、审查规范；
- 资源协同与对接：跨团队沟通、资源协调、向上汇报、方案同步；
- 交付成果准备：编写文档、汇总报表、技术方案、代码修复、环境部署；
- 复核与闭环：组织验收、跟进排查、确认进展、下发通知；
- 条件触发任务：前置条件达成后需执行的具体动作。

不应提取：

- 纯观点、背景介绍、评价、态度倡导；
- 没有具体动作对象的泛泛要求；
- 已完成且无需后续动作的汇报；
- 重复的会议寒暄、流程性表述；
- 无法定位到原文或 actions_text 的想象任务。

边界：

- 带有明确对象和落地举措的要求，即使没有负责人，也应作为 owner=null 的待办保留；
- 只有“要重视”“要关注”而没有动作的表述，不提取；
- 任务明确但属性不完整时，保留任务并将缺失字段设为 null。

## 三、原子化拆解

一条待办只对应一个独立动作。

出现以下情况必须拆成多条：

- 多个不同动作；
- 多个不同负责人；
- 多个不同 deadline；
- 多个独立交付物；
- 条件触发后各自执行的不同任务。

不得把多个动作塞进一个 item，也不得把多个 deadline 塞进一个 deadline。

## 四、字段规则

1. title
   - 是 item 的展示小标题；
   - 优先使用“对象 + 动作/结果”的短语；
   - 建议 4～12 个汉字；
   - 不包含 deadline；
   - 不重复整句 item；
   - 不引入 item 和原文没有的新事实。

2. item
   - 是可独立执行、可复核的动作正文；
   - 保留动作、对象、关键条件和必要的责任主体；
   - 将 deadline 时间表达剥离到 deadline 字段；
   - 不把 title 当作 item；
   - 不因为剥离时间而丢掉动作语义。

3. owner
   - 只记录原文明示的人名、团队、部门、角色；
   - 未明确为 null；
   - 不从 title、常识或会议角色推断；
   - 不写“大家”“相关人员”“待定”“待确认”。

4. deadline
   - 只放截止时间、完成时间、时间锚点；
   - 保留原文表达，不转绝对日期；
   - 未明确为 null；
   - 不把会议时间、文档时间、无关日期放入；
   - 同一事项多个 deadline 时先拆条。

5. collaborators
   - 只记录原文明示的协同对象、配合方；
   - 多个用“、”连接；
   - 未明确为 null。

6. acceptance_criteria
   - 只记录原文明示的验收标准、完成判定、交付物要求；
   - 未明确为 null；
   - 不用常识补通用标准。

7. dependency
   - 只记录原文明示的前置条件、前置动作、外部依赖；
   - 无明确前后制约为 null；
   - 不把背景、风险、假设写成依赖。

8. evidence
   - 必填，非空；
   - 必须是会议原文或 actions_text 中可定位的摘录；
   - 可以是包含 deadline、owner 的完整原句；
   - 不能是模型总结或改写句；
   - 每条待办至少有一条证据。

## 五、title / item / deadline 特别规则

### 1. title

- title 是展示标题，不是事实字段；
- title 不包含时间；
- title 不包含“待办”“事项”“任务”等无信息前缀；
- title 不重复 item；
- title 可以使用名词短语或动宾短语。

示例：

原文：EPC需在周五前提供合同确认函，确认涡轮机可运行。
title：涡轮机运行确认
item：EPC需提供合同确认函，确认涡轮机可运行
deadline：周五前

### 2. item

- item 中不要再出现已剥离到 deadline 的时间表达；
- 如果时间表达是专有名词或非截止语义，不要剥离；
- item 要能独立看懂，不依赖 title 补全语义。

### 3. deadline

- deadline 保留原文说法；
- 不在这里做日期计算；
- 没有明确截止时间就写 null，不猜测。

## 六、去重与合并

1. 同一事项在 transcript 与 actions_text 中重复出现时，合并为一条。
2. 合并时保留用户标记的行动意图。
3. owner、deadline、acceptance_criteria 优先采用原文明确事实。
4. 不得输出两条语义相同的待办。
5. actions_text 中明确、可执行、与原文不冲突的事项，应尽可能保留。
6. actions_text 中误标、重复、非待办、无依据的事项，可以不输出。
7. 不得为了覆盖 actions_text 而编造原文没有的事实。

## 七、输出格式

只输出 JSON，不要输出 Markdown、解释、前后缀或代码块。

结构必须是：

{
  "actions": [
    {
      "title": "...",
      "item": "...",
      "owner": "...",
      "deadline": "...",
      "collaborators": ["..."],
      "acceptance_criteria": "...",
      "dependency": "...",
      "evidence": "..."
    }
  ]
}

规则：

- 没有待办时输出 {"actions": []}；
- 每条必须包含 8 个字段；
- 可选字段无内容时写 null；
- 不输出 category；
- 不输出 assigned_actions / unassigned_actions；
- 不输出任何额外字段；
- 按事项首次出现顺序排列。
```

---

## 六、动态辅助 Prompt 块

### 6.1 `ACTIONS_AUX_PROMPT_BLOCK`

```text
## 辅助材料使用规约

1. 会议原文是主事实底座。
2. 用户标记待办原文是用户明确关注的候选待办，应尽可能体现在最终 actions 中，但不要求逐条覆盖。
3. 用户可能误标、重复标记或只标记关键词；非待办、无行动语义、无原文依据的标记可以不输出。
4. keypoints / notes / vision_info 只用于提升召回、补充术语、参数、数字与时间。
5. 辅助材料不得单独推断 owner、deadline、acceptance_criteria、dependency。
6. 同一事项在多个来源出现时，合并为一条，不重复输出。
7. 辅助材料与会议原文冲突时，以会议原文为准。
8. 不得为了覆盖用户标记而编造原文没有的事实。
```

### 6.2 `ACTIONS_TEXT_PROMPT_BLOCK`

```text
## 用户标记待办原文

以下内容是用户标记的待办候选，可能来自会议原文，也可能是用户整理后的片段。
它不是必须逐条输出的硬性清单。

1. 尽可能保留用户标记事项的行动意图，并在最终 actions 中体现。
2. 可以在会议原文中寻找对应事实，补齐 owner、deadline、collaborators、acceptance_criteria、dependency、evidence。
3. 如果标记事项与原文中的待办重复，合并为一条。
4. 如果标记事项不是可执行动作、没有原文依据、与原文冲突，或明显是误标，可以不输出。
5. 不得为了覆盖 actions_text 而编造原文没有的责任人、时间或验收标准。
6. 如果 actions_text 明确给出某个字段，且与原文不冲突，可以采用该明确表述。
7. evidence 优先引用会议原文；如果标记内容本身是可定位的原文摘录，也可以引用 actions_text。
8. title / item 仍按统一规则生成，不因为来自 actions_text 就降低质量。
```

### 6.3 `ACTIONS_KEYPOINTS_PROMPT_BLOCK`

```text
## 用户关键点参考

1. 关键点用于提升待办召回率，优先关注其中出现明确动作、承诺、责任或节点的内容。
2. 关键点中出现的事项，应回到会议原文核对后再生成待办。
3. 关键点本身不能单独证明 owner / deadline / 验收标准。
4. 不得把关键点中的观点、评价、背景描述直接写成待办。
```

### 6.4 `ACTIONS_NOTES_PROMPT_BLOCK`

```text
## 用户划线原话与笔记参考

1. 划线原话可以作为待办召回线索，也可以辅助定位 evidence。
2. 笔记中的个人批注、主观评论、随手标记不得作为待办事实。
3. 不得仅凭个人笔记新增 owner、deadline、验收标准或依赖关系。
4. 如果笔记内容能在会议原文中找到对应事实，可按原文事实生成待办。
```

### 6.5 `ACTIONS_VISION_PROMPT_BLOCK`

```text
## 视觉信息参考(OCR)

1. OCR 文本可用于补充术语拼写、技术参数、指标数值、时间节点。
2. 只在与会议实际讨论相关时使用。
3. 不得从无关 OCR 内容单独创造待办。
4. OCR 中的数字、日期与会议原文冲突时，以会议原文为准。
```

### 6.6 动态拼装

```python
def build_actions_system_prompt(shared_context: str) -> str:
    prompt = ACTION_ITEMS_GENERATION_SYSTEM_PROMPT

    if any(
        label in shared_context
        for label in (
            "【用户标记待办原文】",
            "【用户核心关键点】",
            "【用户划线原话与笔记】",
            "【视觉信息参考(OCR)】",
        )
    ):
        prompt += "\n\n" + ACTIONS_AUX_PROMPT_BLOCK

    if "【用户标记待办原文】" in shared_context:
        prompt += "\n\n" + ACTIONS_TEXT_PROMPT_BLOCK
    if "【用户核心关键点】" in shared_context:
        prompt += "\n\n" + ACTIONS_KEYPOINTS_PROMPT_BLOCK
    if "【用户划线原话与笔记】" in shared_context:
        prompt += "\n\n" + ACTIONS_NOTES_PROMPT_BLOCK
    if "【视觉信息参考(OCR)】" in shared_context:
        prompt += "\n\n" + ACTIONS_VISION_PROMPT_BLOCK

    return prompt
```

---

## 七、Contract 代码形态

### 7.1 字段常量

```python
ACTIONS_OUTPUT_FIELDS = ("actions",)

ACTIONS_ITEM_FIELD_NAMES = (
    "title",
    "item",
    "owner",
    "deadline",
    "collaborators",
    "acceptance_criteria",
    "dependency",
    "evidence",
)
```

### 7.2 `ACTION_ITEM_FIELDS`

```python
ACTION_ITEM_FIELDS = [
    StrField("title", "item 的展示小标题；不包含 deadline，不引入新事实"),
    StrField("item", "剥离 deadline 后的可执行待办正文"),
    StrField("owner", "原文明示的负责人；未明示为 null"),
    StrField("deadline", "原文明示的时间表达；未明示为 null"),
    StrListField("collaborators", "原文明示的协同方数组；每个元素一个对象；未明示为 []"),
    StrField("acceptance_criteria", "原文明示的验收标准；未明示为 null"),
    StrField("dependency", "原文明示的前置依赖；未明示为 null"),
    StrField("evidence", "原文或 actions_text 中可定位的证据摘录"),
]
```

### 7.3 生成契约

```python
class ObjectiveActionItemsGenerationContract(GenerationContract):
    fields = [
        ObjListField("actions", ACTION_ITEM_FIELDS),
    ]
```

### 7.4 模型

由 codegen 生成：

```python
@dataclass
class ActionItems(ModelMixin):
    actions: list[dict[str, Any]] = field(default_factory=list)
```

校验至少要求：

- `actions` 存在且为数组
- 每条是对象
- 不再接受 `assigned_actions` / `unassigned_actions`

### 7.5 Fallback

```python
class ActionItemsFallbackRules(FallbackRules):
    sections = [Lines("actions")]
    empty_text = "暂无明确待办事项"
    structured = {"merge": ["actions"]}
```

### 7.6 空结构

```python
_EMPTY_ACTION_ITEMS = {
    "actions": [],
}
```

---

## 八、Agent / Supervisor / Render

### 8.1 ActionItemsAgent

```python
async def run(self, shared_context: str) -> ActionItems:
    system_prompt = build_actions_system_prompt(shared_context)
    return await self.client.structured(
        system_prompt,
        shared_context,
        self.output_model,
        self.output_contract,
        label="actions/agent",
        **self.extra_kwargs,
    )
```

要求：

- [ ] `output_model = ActionItems`
- [ ] `output_contract = ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT`
- [ ] 不再使用固定 `ACTION_ITEMS_GENERATION_SYSTEM_PROMPT`
- [ ] 日志标签仍为 `actions/agent`

### 8.2 Supervisor

`ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT` 改为扁平合同审核。

核心规则：

```text
## 结构检查

1. 顶层只能是 actions 数组；
2. 不得出现 assigned_actions / unassigned_actions；
3. 不得出现 category；
4. 每条必须包含 8 个字段；
5. 可选字段无内容时必须为 null。

## 语义检查

1. title 是 item 的短标题，不引入新事实；
2. title 不包含 deadline；
3. item 是剥离 deadline 后的可执行动作；
4. deadline 保留原文表达；
5. owner 必明确，否则 null；
6. evidence 必须可定位，不能是总结；
7. 同一事项不得重复输出；
8. 不得遗漏原文中明确、重大的刚性承诺。

## actions_text 规则

1. actions_text 是用户候选清单，可能误标；
2. 漏掉非待办、无依据的标记，不单独判 revise；
3. actions_text 中明确、可定位的重大事项被完全遗漏，可以提示 revise；
4. 为了覆盖 actions_text 而编造 owner/deadline/验收标准，必须 revise。
```

Supervisor 上下文：

```text
原文（最高事实来源）
起草稿（actions 数组）
用户标记待办原文（存在时）
```

不注入会议理解 / 用户画像 / 视角模型。

### 8.3 Render

**当前生产策略：actions 不使用 LLM 渲染 Agent。**

```python
"actions": {"kind": LLM_EXTRACT, "llm_render": "never"}
```

保留 `ActionItemsRender` 类，供未来手工接入；生产路径直接调用
`ActionItemsRender.render_draft()` / `render_items()` 程序生成 Markdown。

固定格式：

```text
**涡轮机运行确认**： EPC需提供合同确认函，确认涡轮机可运行（责任方：EPC）
 - 协同配合：李四、王五
 - 时间节点：周五
 - 前置依赖：等待测试环境就绪
 - 交付验收：涡轮机可运行
```

规则：

- [x] 无待办输出「暂无明确待办事项」
- [x] `title` 加粗，后接中文冒号和空格，再接 `item`
- [x] `owner` 放在第一行末尾括号内，标签为「责任方」
- [x] 属性行顺序固定：协同配合 → 时间节点 → 前置依赖 → 交付验收
- [x] 可选字段有值才输出对应属性行
- [x] `collaborators` 用“、”连接
- [x] 不输出序号
- [x] 多条待办之间空一行
- [x] 不按 category 分组
- [x] 不输出 assigned/unassigned 两段
- [x] 顺序与 `actions` 数组一致
- [x] 不使用 emoji

`ACTION_ITEMS_RENDER_TEMPLATE_PROMPT` 的 extra_rules 同步改为：

```text
title / item / owner / deadline 忠实反映草稿内容
title 作为条目标题，item 作为动作正文
不再使用 category / task 旧字段
可选字段缺省时优雅留白
```

### 8.4 Render 代码

- [x] `extract_actions()` 读取 `draft["actions"]`
- [x] 不合并 assigned/unassigned
- [x] `render_items()` 不再按 category 分组
- [x] `render_draft()` 读取 `draft["actions"]`
- [x] `format_action()` 使用 title/item
- [x] `validate_action_roster()` 不再依赖 `meeting_understanding.participants`
- [x] 旧 `category` / `task` 兼容分支删除
- [x] 生产路径 `llm_render="never"`，保留 Render 类供未来接入

### 8.5 Report

`ActionItemsReport` 已有 `actions` 字段，方向正确。

确认：

- [ ] `ActionItemsReportValidation` 仍允许 `{"actions", "quality_warning", "personalized_text"}`
- [ ] `actions` 逐条 `_action` 校验通过
- [ ] 不要求旧 `assigned_actions` / `unassigned_actions`
- [ ] 兼容空 `actions`

---

## 九、文件级改动清单

| 文件 | 改动 |
|---|---|
| `domains/meeting/tasks/actions/contracts.py` | `ACTION_ITEM_FIELDS` 改为 8 个新字段；顶层改为 `actions`；Fallback 改为扁平 |
| `domains/meeting/tasks/actions/prompts.py` | 重写生成 Prompt、Supervisor Prompt、Render Prompt；新增 5 个动态块 |
| `domains/meeting/tasks/actions/steps/actions_agent.py` | 动态拼装 `build_actions_system_prompt()` |
| `domains/meeting/tasks/actions/steps/actions_supervisor.py` | 引用新 Supervisor Prompt，确认审核合同 |
| `domains/meeting/tasks/actions/steps/actions_render.py` | 扁平读取、扁平渲染、去掉 category 分组 |
| `domains/meeting/models_generated.py` | 由 codegen 重新生成 `ActionItems`，改为 `actions` |
| `domains/meeting/reports.py` | 确认 `ActionItemsReport.actions` 不变；更新注释 |
| `domains/meeting/orchestrator.py` | `_EMPTY_ACTION_ITEMS`；actions 上下文；Supervisor 上下文 |
| `domains/meeting/memory/render.py` | 旧 `assigned_actions` / `category` 兼容分支改为扁平 actions |
| `app/schemas.py` | `TEXT_KEYS` 增加 `actions_text` |
| `app/requirements.py` | actions 必填只保留 transcript |
| `app/tasks.py` | `_collect_texts()`、`_pack_actions_auxiliary()`、`line_extra` |
| `tests/...` | 旧 contract 断言全部迁移到新结构 |

注意：

- `models_generated.py` 标注“勿手改”，应先改 contract/codegen 源，再运行 codegen；
- 不要只改 Prompt 不改 contract，否则结构化校验会拒绝新字段；
- 不要只改 contract 不改 Render，否则最终展示仍按旧 category 分组；
- 不要保留旧 `assigned_actions` 兼容分支作为主路径，避免双轨。

---

## 十、最佳执行路线

### Phase 0：冻结 contract 与字段语义

目标：不写代码，先把口径定死。

- [x] 确认顶层只有 `actions`
- [x] 确认 8 字段及顺序
- [x] 确认 `title` 为必填短标题
- [x] 确认 `item` 剥离 deadline
- [x] 确认 `owner = null` 表示未分配
- [x] 确认 `collaborators` 用字符串数组，无协同方为 `[]`
- [x] 确认 `deadline` 保留原文表达
- [x] 确认 `actions_text` 只做输入，不做输出字段
- [x] 确认 `actions_text` 只要求“尽可能覆盖”，不做硬门禁
- [x] 用用户样例建立 golden fixture

Gate：

```text
Phase 0 已冻结；用户样例作为 golden fixture 进入后续测试。
```

---

### Phase 1：接入 actions_text 输入层（不改输出）

目标：低风险完成 API / 准备层 / 上下文输入，不改变旧 actions 输出。

改动：

- [x] `app/schemas.py`：`TEXT_KEYS` 增加 `"actions_text"`
- [x] `app/requirements.py`：actions 仍只要求 `texts.transcript`
- [x] `app/tasks.py::_collect_texts()`：增加 `actions_text`
- [x] 更新 `_collect_texts()` 的所有调用点
- [x] 新增 `_pack_actions_auxiliary()`
- [x] `prepare_run`：`line == "actions"` 时写 `line_extra["actions_auxiliary"]`
- [x] 此时先不把 `actions_auxiliary` 注入 actions 生成上下文
- [x] 确认 `actions_text` 不进入 `minutes_auxiliary`

测试：

- [x] `texts.actions_text` 可以通过 API 校验
- [x] 未知 texts key 仍然 422
- [x] transcript 缺失仍然 400
- [x] 不传 actions_text 时行为不变
- [x] minutes 的辅助材料不受影响
- [x] 旧 actions 测试全部通过

Gate：

```text
Phase 1 已完成：45 passed（multi-source + actions 回归）。
actions 输出未改变，actions_text 仅写入 actions_auxiliary。
```

建议提交：

```text
feat(actions): accept actions_text input without behavior change
```

---

### Phase 2：原子切换 contract + prompt + model + supervisor + render

目标：一次性完成新 contract 的纵向切片。

> 这是核心阶段。不要只切一半。

#### 2.1 Contract 与模型

- [x] 更新 `ACTIONS_OUTPUT_FIELDS`
- [x] 更新 `ACTIONS_ITEM_FIELD_NAMES`
- [x] 更新 `ACTION_ITEM_FIELDS`
- [x] 更新 `ObjectiveActionItemsGenerationContract`
- [x] 更新 `ActionItemsFallbackRules`
- [x] 更新 `_EMPTY_ACTION_ITEMS`
- [x] 运行：

```bash
python tools/codegen/sync_domain.py --domain meeting --model
```

已修复 `sync_domain._load_module_file()`：对带相对导入的 `contracts.py`
建立最小 synthetic package，不再触发
`attempted relative import with no known parent package`。

- [x] 检查 `models_generated.py` 中 `ActionItems.actions`
- [x] 检查 `ActionItemsReportValidation` 不再要求旧字段

#### 2.2 Prompt

- [x] 替换 `ACTION_ITEMS_GENERATION_SYSTEM_PROMPT`
- [x] 新增 5 个动态 Prompt 块
- [x] 新增 `build_actions_system_prompt()`
- [x] 确认 Prompt 中不再出现 `category` / `assigned_actions` / `unassigned_actions`
- [x] 确认 Prompt 不再要求“先分组再分点”

#### 2.3 Agent / Supervisor

- [x] `ActionItemsAgent` 使用动态 Prompt
- [x] `ActionItemsAgent.output_model` 指向新 `ActionItems`
- [x] `ActionItemsAgent.output_contract` 指向新契约
- [x] 重写 `ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT`
- [x] Supervisor 上下文加入 actions_text / 辅助材料
- [x] Supervisor 仍不读取会议理解 / 画像 / 视角

#### 2.4 Render / Fallback / Orchestrator

- [x] 重写 `ACTION_ITEMS_RENDER_PROMPT`
- [x] 更新 `ACTION_ITEMS_RENDER_TEMPLATE_PROMPT`
- [x] 重写 `ActionItemsRender.extract_actions()`
- [x] 重写 `ActionItemsRender.render_items()`
- [x] 重写 `ActionItemsRender.render_draft()`
- [x] 更新 `format_action()`
- [x] 更新 `_supervisor_context("actions")`
- [x] 更新 `_render_context("actions")`（如需要）
- [x] 确认 `_EMPTY_ACTION_ITEMS` 已切换

#### 2.5 打开多源上下文

- [x] `_line_shared_context("actions")` 拼接 `【会议原文】`
- [x] 拼接 `line_extra["actions_auxiliary"]`
- [x] 不拼接会议理解 / 画像 / 视角
- [x] 确认 actions-only 仍跳过 meeting understanding / perspective

#### 2.6 更新 actions 专项测试

- [x] contract 测试改为 `actions`
- [x] FakeLLM 返回扁平 actions
- [x] 渲染测试改为扁平 title/item
- [x] actions-only E2E 改为新结构
- [x] 删除旧 `assigned_actions` / `unassigned_actions` fixture

Gate：

```text
Phase 2 已完成：56 passed（actions 专项 + core + multi-source + HTML roundtrip）。
actions-only E2E / FakeLLM / Supervisor / Render 均已切到扁平 contract。
```

建议提交：

```text
refactor(actions): switch to flat actions contract
```

---

### Phase 3：清理旧字段与兼容分支

目标：消除双轨，防止旧结构回流。

- [x] 全局搜索 actions 作用域内的 `assigned_actions`
- [x] 全局搜索 actions 作用域内的 `unassigned_actions`
- [x] 全局搜索 actions 作用域内的 `category`
- [x] 全局搜索 actions 作用域内的 `task`
- [x] 更新 `domains/meeting/memory/render.py`
- [x] 删除 `ActionItemsRender` 旧 category 兼容分支
- [x] 删除 `validate_action_roster` 对 `meeting_understanding.participants` 的依赖
- [x] 更新 `tests/core/test_core.py`
- [x] 更新 `tests/meeting/test_actions_risks.py`
- [x] 更新 `tests/unit/meeting/test_actions_objective_contract_freeze.py`
- [x] 更新 `tests/unit/meeting/test_actions_context_cleanup.py`
- [x] 更新 `tests/meeting/test_actions_only_e2e.py`
- [x] 运行：

```bash
python tools/codegen/sync_domain.py --domain meeting --check
```

已通过：`SUCCESS! domain/meeting 生成区检查通过。`

- [x] 运行全量 actions 相关测试（64 passed）
- [!] 运行全量会议域回归：500 passed / 9 failed，失败项均在 minutes 相关既有测试（缺失 `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md`、旧 prompt 断言），与 actions 改动无关

Gate：

```text
actions 主路径已无旧字段；codegen 已恢复并通过 check。
剩余仅为 minutes 既有失败。
```

建议提交：

```text
chore(actions): remove legacy fields and update consumers
```

---

### Phase 4：真实 LLM 验收与 Prompt 调优

目标：验证真实模型能稳定填充新 contract。

样例至少覆盖：

- [ ] 有负责人 + 有 deadline
- [ ] 无负责人 + 有 deadline
- [ ] 有负责人 + 无 deadline
- [ ] 一个动作多个协作者
- [ ] 多个动作需要拆条
- [ ] 时间不是 deadline 的干扰句
- [ ] actions_text 中明确待办
- [ ] actions_text 中误标 / 非待办
- [ ] transcript 与 actions_text 重复
- [ ] keypoints / notes / vision_info 同时存在
- [ ] 完全没有待办

人工检查：

- [ ] title 是否短、准、不重复 item
- [ ] item 是否已剥离 deadline
- [ ] deadline 是否保留原文表达
- [ ] owner 是否只来自原文
- [ ] evidence 是否可定位
- [ ] 是否出现 category / assigned / unassigned
- [ ] actions_text 覆盖是否“尽可能”
- [ ] 误标项是否被合理忽略
- [ ] 是否有重复待办

Gate：

```text
真实 LLM 输出全部通过 contract 校验；
人工抽查无编造 owner / deadline / 验收标准；
actions_text 覆盖达到“尽可能”而非硬性逐条。
```

建议提交：

```text
test(actions): real llm acceptance for flat contract
```

---

### Phase 5：文档收口

- [ ] 删除旧 actions 清单，只保留本文件
- [ ] 更新 README / 任务说明中的 actions 输出示例
- [ ] 更新 API 文档中的 `texts.actions_text`
- [ ] 更新前端 / 消费方的 `actions` 结构说明
- [ ] 记录 deadline 归一化仍由 calendar 工具负责

---

## 十一、测试清单

### 11.1 Contract

- [ ] 顶层只接受 `actions`
- [ ] `actions` 必须是数组
- [ ] 每条字段严格为 8 个
- [ ] 缺少 `title` / `item` / `evidence` 时报错
- [ ] 可选字段为 `null` 时通过
- [ ] `owner=null` 可表示未分配
- [ ] 旧 `assigned_actions` / `unassigned_actions` 不再被接受
- [ ] 旧 `category` / `task` 不再被接受

### 11.2 Prompt

- [ ] 基础 Prompt 包含 `title`、`item`、`actions`
- [ ] 基础 Prompt 不包含 `category`、`assigned_actions`、`unassigned_actions`
- [ ] 无辅助标签时只使用基础 Prompt
- [ ] 有 actions_text 时追加通用块 + actions_text 块
- [ ] keypoints / notes / vision 各自只触发对应块
- [ ] 多辅助来源同时存在时顺序稳定
- [ ] 不出现 minutes 专属辅助块

### 11.3 Agent

- [ ] FakeLLM 返回扁平 actions 可解析
- [ ] Agent 使用动态 Prompt
- [ ] `actions_text` 出现在 shared context
- [ ] 不读取 meeting_understanding / perspective
- [ ] actions-only 不构建会议理解 / 视角建模

### 11.4 字段行为

- [ ] `周五前提交报告` → `item=提交报告`，`deadline=周五前`
- [ ] `周五的例会` → 时间不是 deadline 时不被错误剥离
- [ ] 多个 deadline 拆成多条
- [ ] `title` 不包含 deadline
- [ ] `title` 不等于 `item`
- [ ] 无 owner 时 `owner=null`
- [ ] 无 deadline 时 `deadline=null`
- [ ] 多个协作用“、”连接
- [ ] evidence 是原文摘录而非总结
- [ ] `actions_text` 明确事项尽可能出现
- [ ] `actions_text` 误标项允许不输出
- [ ] 重复事项只输出一条
- [ ] 不输出 category 分组

### 11.5 Render / Fallback

- [ ] 扁平渲染不按 category 分组
- [ ] title 作为小标题，item 作为正文
- [ ] 可选字段为空时不输出属性行
- [ ] 空 actions 输出「暂无明确待办事项」
- [ ] fallback structured 为扁平 actions
- [ ] report `actions` 正常校验

### 11.6 多线与真实 LLM

- [ ] actions + minutes 时 minutes 不受 actions 新 contract 影响
- [ ] actions_text 不进入 minutes auxiliary
- [ ] 真实 LLM 样例：有负责人 + 无负责人
- [ ] 真实 LLM 样例：有 deadline + 无 deadline
- [ ] 真实 LLM 样例：带 actions_text / keypoints / notes / vision
- [ ] 真实 LLM 输出通过 contract 校验和 Supervisor

### 11.7 回归

需要更新的现有测试：

- [ ] `tests/unit/meeting/test_actions_objective_contract_freeze.py`
- [ ] `tests/unit/meeting/test_actions_context_cleanup.py`
- [ ] `tests/meeting/test_actions_only_e2e.py`
- [ ] `tests/meeting/test_actions_risks.py`
- [ ] `tests/core/test_core.py` 中 actions fixture
- [ ] 所有断言 `assigned_actions` / `unassigned_actions` / `category` / `task` 的 actions 测试

---

## 十二、验收标准

```text
输出结构：
  {"actions": [...]}
  每条 8 字段
  title / item / owner / deadline /
  collaborators / acceptance_criteria / dependency / evidence
```

```text
不再出现：
  assigned_actions
  unassigned_actions
  category
  task
```

```text
字段语义：
  title 是 item 的短标题
  item 已剥离 deadline
  owner=null 表示未分配
  deadline 保留原文表达
  evidence 必填且可定位
```

```text
输入：
  transcript 必传
  keypoints / notes / vision_info / actions_text 选传
  actions_text 尽可能覆盖，但不强制逐条覆盖
```

```text
渲染：
  扁平列表
  title 作为小标题
  item 作为正文
  不再按 category 分组
```

```text
测试：
  contract / prompt / agent / render / fallback /
  supervisor / actions-only / multi-line / real LLM 全部通过
```

---

## 十三、风险与决策

### 13.1 输出是破坏性变更

`assigned_actions` / `unassigned_actions` / `category` / `task` 都是旧契约字段，改成 `actions` + `title/item` 会破坏旧消费方。

要求：

- 同步更新 API 消费方与测试
- 不保留双轨主路径
- 如需兼容旧客户端，在版本层处理，不要让 Prompt 同时输出两套结构

### 13.2 title 与 item 容易重复

Prompt 必须明确：

- title 是短标题，不是 item 的复制
- title 不包含 deadline
- title 不引入新事实
- Supervisor 对 `title == item` 或 title 含 deadline 的情况给出 revise

### 13.3 deadline 剥离可能误伤

只剥离“截止/完成时间”语义：

- “周五前提交” → 剥离
- “周五的例会” → 不剥离
- 专有名词、活动名中的日期不剥离

### 13.4 collaborators 使用字符串数组

当前使用 `["李四"]` / `["李四", "王五"]`，无协同方为 `[]`。

不要在同一 contract 中混用字符串和数组；渲染时统一用“、”连接。

### 13.5 category 删除后的展示

如果未来 UI 需要按业务议题筛选：

- 新增可选 `tag` 字段
- 由程序分类或单独 Agent 生成
- 不要恢复嵌套 category 分组
- 不要让 actions Agent 重新承担分组职责

### 13.6 actions_text 覆盖不是硬门禁

- 尽可能覆盖
- 误标、重复、无依据可不输出
- Supervisor 不因普通遗漏自动 revise
- 不得为了覆盖率编造字段

### 13.7 deadline 不在此阶段转日期

contract 中保留原文表达；绝对时间转换继续由 calendar 工具/Agent 负责，不在 actions Agent 内完成。

### 13.8 最危险的错误顺序

不要这样排：

```text
先改 contract
→ 再改 prompt
→ 再改 render
```

中间任何一步都会让链路不可运行。

正确方式是：

```text
先冻结
→ 输入层低风险接入
→ contract + prompt + model + supervisor + render 原子切换
→ 清理
→ 真实 LLM 验收
```

---

## 十四、执行检查表（速查）

```text
[ ] Phase 0 冻结 contract
[ ] Phase 1 actions_text 输入层
[ ] Phase 2 原子切换 contract/prompt/model/supervisor/render
[ ] Phase 3 清理旧字段与测试
[ ] Phase 4 真实 LLM 验收
[ ] Phase 5 文档收口
```
