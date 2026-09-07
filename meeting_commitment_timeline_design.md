# meeting 新增任务线深度设计：会议承诺时间线

## 1. 一句话结论

建议在 `meeting` 域新增任务线：

```text
commitment_timeline
```

中文名：

```text
会议承诺时间线
```

它的定位不是“待办事项”，也不是“甘特图”，而是：

```text
从带说话人识别的会议文本中，抽取每个说话人在会上形成的行动承诺、时间表达和条件依赖，并用一个简约的时间确定性泳道展示出来。
```

这条线最有价值的地方，是保留会议口语里的三种证据：

```text
谁说的
说了要做什么
什么时候 / 在什么条件下做
```

普通待办只保留“要做什么”；这条线保留“会议当场形成的责任和时间证据链”。

## 2. 推荐任务名

### 2.1 首选

```text
commitment_timeline
```

理由：

- `commitment` 比 `task` 更贴近会议语境，包含承诺、安排、要求、指令、整改、跟进。
- `timeline` 表示它关注时间关系，但不强行等同于日历或甘特图。
- 不把能力限制在“冲突检测”上。
- 能覆盖时间明确和时间模糊的会议。

### 2.2 中文显示名

```text
会议承诺时间线
```

比下面几个名字更稳：

| 名称 | 问题 |
|---|---|
| 排期冲突检测 | 太窄，要求会议必须有冲突 |
| 会议排期 | 容易让用户期待完整项目管理甘特图 |
| 待办时间线 | 太像 actions 的可视化版本 |
| 责任时间表 | 可以用，但少了“口头承诺”的会议特征 |
| 行动轨迹 | 太抽象，不够产品化 |

## 3. 这到底和待办有什么区别

现有 `meeting/actions` 已经做待办提取，字段是：

```text
task / owner / deadline / priority / status / evidence / confidence
```

`commitment_timeline` 不应重复这个能力。它的差异必须体现在结构和问题意识上。

| 维度 | actions | commitment_timeline |
|---|---|---|
| 回答的问题 | 会后要做哪些事 | 会议里形成了哪些带时间语义的承诺 |
| 组织方式 | 清单 | 说话人泳道 + 时间确定性列 |
| 时间处理 | 只有 deadline 字段 | 分类展示明确时间、截止时间、相对时间、条件时间、无时间 |
| 说话人 | 辅助证据 | 第一组织维度 |
| 负责人 | 执行责任人 | 与 speaker 分开，避免“谁说的”和“谁负责”混淆 |
| 输出价值 | 执行跟进 | 会议后快速复盘排期、识别模糊时间、看责任是否被接住 |
| 主要风险 | 漏待办 | 编造时间、混淆说话人、把弱表达硬变成排期 |

关键原则：

```text
actions 是行动清单。
commitment_timeline 是责任-时间证据图。
```

如果最终页面看起来只是“待办列表加了截止时间”，说明这条任务线设计失败。

## 4. 是否对所有会议都适用

这里要区分三个层次：

```text
可运行：几乎所有带文本的会议都能运行
可产出：有行动/安排/要求的会议才有内容
高价值：有时间表达、说话人、责任转移或条件依赖的会议价值最高
```

所以答案不是“所有会议都能有效提取排期”，而是：

```text
所有会议都可以跑这条线，但不是所有会议都应该被画成排期图。
```

一个通用任务线必须允许空态和降级态。

## 5. 会议类型适配性

### 5.1 项目例会

适配性：高。

常见表达：

```text
我明天补一下
周五前给版本
后端接口好了前端再联调
下周一评审
```

推荐展示：

```text
日期/阶段混合时间线 + 说话人泳道
```

价值：

- 抽承诺
- 看时间顺序
- 识别依赖冲突
- 发现无截止任务

### 5.2 验收会 / 整改会

适配性：高。

`meeting_all.txt` 就属于这一类。

常见表达：

```text
会后安排现场验收
出报告之前完成整改
验收完成第一时间汇总资料
整改之后验收组复核
交付之前做好成品保护
```

推荐展示：

```text
时间确定性泳道
```

价值：

- 把“会后、尽快、报告前、交付前”这种模糊但重要的时间表达保留下来
- 不强行生成具体日期
- 非常适合发现“谁提出要求，但谁负责不明确”

### 5.3 客户沟通会

适配性：中高。

常见表达：

```text
客户确认后我们再发合同
你们这边下周给反馈
我们月底前补报价
```

价值：

- 区分己方承诺和客户承诺
- 展示条件触发
- 把“等客户确认”从普通待办里单独凸显出来

### 5.4 需求评审会

适配性：中高。

常见表达：

```text
设计这周出稿
研发下周评估
等法务确认后再上线
```

价值：

- 展示跨角色依赖
- 发现缺 owner 的要求
- 将“评估/确认/上线”拆成阶段

### 5.5 管理层会议

适配性：中。

常见表达偏抽象：

```text
要加强管理
后续持续关注
尽快形成方案
相关部门抓紧落实
```

能产出，但必须降级：

- 多数 owner 是角色或组织
- 时间多为模糊词
- 不应给出精确排期

推荐展示：

```text
相对时间 + 待确认为主
```

### 5.6 脑暴会

适配性：低到中。

如果只是发散想法，没有承诺，就不应产出排期。

可展示：

```text
暂无明确时间承诺
发现若干待确认想法，但未形成执行安排
```

### 5.7 培训 / 分享会

适配性：低。

通常没有承诺和时间安排，除非结尾有：

```text
会后完成测试
下周提交作业
```

否则应空态。

### 5.8 访谈 / 对话

适配性：低到中。

只有当访谈后有明确跟进事项时才有效。

## 6. 通用性设计原则

最通用的表现形式不是“周一到周五”，而是：

```text
按说话人分行
按时间确定性分列
每个格子放承诺卡片
```

推荐默认五列：

```text
明确时间 | 截止前 | 相对时间 | 条件触发 | 待补时间
```

为什么是五列：

- 明确时间：承载“周三、明天上午、9月12日”。
- 截止前：承载“报告前、交付前、月底前”。
- 相对时间：承载“会后、尽快、近期、第一时间”。
- 条件触发：承载“整改后、接口好了后、客户确认后”。
- 待补时间：承载有行动但没有时间的承诺。

这五列几乎覆盖所有会议时间表达。

不要把所有内容都挤到真实日历上，因为真实会议大部分时间表达并不是日历时间。

## 7. HTML 最终形态

### 7.1 页面气质

目标风格：

```text
简约、大气、像产品中的一张分析结果页
```

不要像：

- 会议报告
- 待办列表
- 复杂项目管理系统
- PPT 流程图
- 带大量说明文字的 demo 页

页面只保留用户真正需要看的东西：

```text
标题
提取数量
说话人泳道
时间确定性列
任务卡片
```

### 7.2 桌面端布局

推荐结构：

```text
┌───────────────────────────────────────────────────────────────┐
│ 会议承诺时间线                                  13 条承诺       │
│ 按说话人整理任务与时间表达                                      │
├──────────────┬────────────┬────────────┬────────────┬──────────┤
│ 说话人/责任方 │ 明确时间     │ 截止前       │ 相对时间     │ 条件触发 │ 待补时间
├──────────────┼────────────┼────────────┼────────────┼──────────┤
│ 发言者 1      │ 交付前排查   │ 报告前完善   │ 会后安排验收 │ 验收后补充 │
│ 验收组        │              │              │ 后续跟踪费用 │            │
├──────────────┼────────────┼────────────┼────────────┼──────────┤
│ 发言者 4      │              │              │ 第一时间汇总 │ 其后整改   │
│ 技术组        │              │              │ 护照证书收集 │            │
├──────────────┼────────────┼────────────┼────────────┼──────────┤
│ 发言者 6      │              │ 报告前整改   │ 尽快研究原因 │ 整改后复核 │
│ 合作局领导    │              │              │              │            │
└──────────────┴────────────┴────────────┴────────────┴──────────┘
```

注意：

- 这不是普通表格，而是视觉上像一张干净的任务泳道。
- 每个任务是小卡片。
- 卡片不需要大阴影，不需要大色块。
- 五列标题要短。
- 说话人列固定在左侧，右边承诺随列分布。

### 7.3 卡片结构

每张卡片最多三层：

```text
任务短语
时间标签
证据短句
```

示例：

```text
完成整改闭环
出报告之前
“最迟要在出报告之前完成整改”
```

卡片 HTML 结构建议：

```html
<article class="commitment-card type-deadline">
  <strong>完成整改闭环</strong>
  <span class="time-chip">出报告之前</span>
  <p>“最迟要在出报告之前要完成整改”</p>
</article>
```

卡片规则：

- `strong` 只放任务，不放负责人和时间。
- `time-chip` 放原文时间表达，不编造。
- `p` 放短证据，最长一行到两行。
- 如果 owner 和 speaker 不一致，卡片角落显示 `责任：施工单位`。
- 如果没有时间，进入“待补时间”列，不要在卡片里写假 deadline。

### 7.4 视觉语言

推荐颜色：

| 类型 | 色彩建议 | 使用方式 |
|---|---|---|
| 明确时间 | 低饱和绿 | 小标签 |
| 截止前 | 深灰或墨绿 | 小标签 |
| 相对时间 | 低饱和蓝 | 小标签 |
| 条件触发 | 低饱和琥珀 | 小标签 |
| 待补时间 | 低饱和红 | 小标签 |

整体页面：

- 背景用浅灰或暖白。
- 主容器用纯白或接近白。
- 边框细，阴影轻。
- 不使用大面积红色。
- 不使用强渐变。
- 不使用头像花色。
- 不使用大段解释。

### 7.5 信息密度

一屏最多展示：

```text
4 到 6 个说话人
每人每列最多 2 张卡片
超过部分显示 +N
```

原因：

- 这个页面的第一价值是“看时间分布”，不是读完所有证据。
- 证据可以放在 hover、展开或二级详情里。
- 第一屏不要塞满。

### 7.6 移动端布局

移动端不要横向压缩五列，否则会难看。

推荐降级为：

```text
说话人卡片
  明确时间：...
  截止前：...
  相对时间：...
  条件触发：...
  待补时间：...
```

也就是按说话人纵向堆叠，每个人内部显示时间分组。

移动端示意：

```text
发言者 6 / 合作局领导

截止前
完成整改闭环 · 出报告之前

相对时间
研究开裂原因 · 尽快

条件触发
验收组复核 · 整改之后
```

## 8. 自适应展示策略

不要只有一种 HTML。

应根据结构化结果选择展示模式。

### 8.1 默认模式：时间确定性泳道

触发条件：

```text
commitments >= 1
并且绝对日期占比不足 60%
```

这是最通用模式，适合大多数会议。

### 8.2 日期轴模式：明确排期会议

触发条件：

```text
有 meeting_time
absolute/deadline 类型 commitments 占比 >= 60%
并且可解析出至少 3 个不同日期或半天时间块
```

展示方式：

```text
说话人 | 9/8 上午 | 9/8 下午 | 9/9 上午 | 9/9 下午 | 9/12 前
```

适合项目会、发布会、执行冲刺会。

注意：

- 没有 `meeting_time` 时，不能把“明天/后天”转成绝对日期。
- 可以显示“明天/后天”，但不要显示具体年月日。

### 8.3 空态模式：无承诺会议

触发条件：

```text
commitments = []
```

展示：

```text
暂无明确时间承诺
```

可以补一行：

```text
本次会议更接近信息同步/讨论，没有形成可追踪的时间安排。
```

但不要生成任务卡。

### 8.4 弱信号模式：只有行动，没有时间

触发条件：

```text
commitments > 0
且 70% 以上为 unspecified
```

展示重点：

```text
待补时间
```

而不是强行排期。

## 9. 对 meeting_all.txt 的判断

`data/1/docs/meeting_all.txt` 非常适合验证这条任务线，但它验证的是“弱排期会议”，不是“强日期会议”。

它有：

- 清晰的发言者分段
- 多个整改、完善、跟踪、复核动作
- 大量相对时间和截止型时间
- 一些条件触发关系

它没有：

- 真实姓名稳定映射
- 精确日期
- 上午/下午
- 明确任务持续时长

所以它应该进入：

```text
默认模式：时间确定性泳道
```

不应该画成周一到周五。

适合抽取的示例：

| speaker | owner | task | time_type | time_text |
|---|---|---|---|---|
| 发言者 1 | 验收组 | 安排剩下一个点的现场验收工作 | relative | 会后 |
| 发言者 1 | 施工部和管理组 | 完善人员履约资料 | deadline | 形成验收报告之前 |
| 发言者 1 | 执行单位 | 汇总资料到卢萨卡并分类成册 | relative | 验收后或者验收这段时间以后 |
| 发言者 1 | 施工方 | 检查局部损伤、卫生和排水 | deadline | 正式交付之前 |
| 发言者 4 | 技术组 | 收集人员护照证书 | relative | 现在已经在开展 |
| 发言者 4 | 技术组 | 汇总三个厂区资料和竣工图 | relative | 验收完成第一时间 |
| 发言者 4 | 技术组 | 编制整改方案并逐一整改落实 | condition | 其后 |
| 发言者 6 | 管理组和总包单位 | 分析路面开裂原因并制定整改方案 | relative | 尽快 |
| 发言者 6 | 管理组和总包单位 | 完成整改并形成闭环 | deadline | 出报告之前 |
| 发言者 6 | 验收组 | 进行复核 | condition | 完成整改之后 |
| 发言者 7 | 验收组 | 注意交通安全和防疫 | condition | 如果要下去的话 |
| 发言者 1 | 验收组 | 跟踪和完善不可预见费资料 | relative | 接下来/后续 |

这批信息做成普通待办不新鲜；做成“发言者 1/4/6/7 在不同时间确定性上的承诺分布”才有差异。

## 10. meeting_understanding 是否要加字段

正式做这条线时，建议给 `meeting_understanding.action_hints` 增加 `speaker` 字段。

但这个改动要分成两个层面判断：

```text
技术兼容性：低风险
语义行为风险：中等，需要配套 prompt 约束
```

### 10.1 现有 action_hints 的使用情况

当前 `action_hints` 在代码里的主要消费路径是：

```text
meeting_core 生成 action_hints
orchestrator._meeting_pack() 把 action_hints 原样传给 actions/risks/默认任务包
actions Agent 把 action_hints 当待办候选索引
supervisor_slice.summarize_understanding() 摘要 action_hints 的 action/owner
models_generated.MeetingUnderstanding 对 action_hints 只做 list 类型浅校验
```

也就是说，现有模型层并没有严格校验 `action_hints` 内部只能有哪些字段。`action_hints` 是：

```python
list[dict[str, Any]]
```

因此从结构上看，新增：

```text
action_hints[].speaker
```

不会破坏现有 dataclass 校验，也不会让 `actions` 的确定性渲染报错。

### 10.2 为什么正式版仍然应该加 speaker

`commitment_timeline` 的核心价值是“带说话人识别的时间承诺”。如果不加 `speaker`，下游只能从 `evidence` 或完整原文里回扫发言块来判断“谁说的”。

这会带来三个问题：

1. 同一句 evidence 被截短后，可能丢失发言者。
2. 领导提出要求和执行方承诺容易混在一起。
3. HTML 的第一组织维度是说话人，没有 `speaker` 会让页面不稳定。

例如：

```text
发言者 6：请管理组和总包单位尽快制定整改方案。
```

这里：

```text
speaker = 发言者 6
owner = 管理组和总包单位
```

这里 `speaker` 和 `owner` 必须分开。如果只有 `owner`，页面只能展示“管理组和总包单位要制定方案”，但丢了“这个要求是发言者 6 提出的”。

这正是它区别于普通待办的地方。

### 10.3 加 speaker 会不会影响现有逻辑

结论：

```text
不会造成明显代码层破坏，但会引入下游语义误用风险。
```

#### 10.3.1 不太会影响的部分

`models_generated.MeetingUnderstanding`：

- 只校验 `action_hints` 是数组。
- 不校验数组内部 dict 的固定字段。
- 新增 `speaker` 不会触发字段错误。

`orchestrator._meeting_pack()`：

- 当前用 `u.get("action_hints") or []` 原样透传。
- 新字段会自然传到下游。
- 不需要改打包逻辑才能让新 task 用到 speaker。

`supervisor_slice._review_compact()`：

- `action_hints` 属于保留完整列表的 key。
- dict 内新增字段会被保留，只是长字符串会被压缩。
- 审核链路不会因为新增字段坏掉。

`actions_render.py`：

- 只读取 actions 任务线自己的 `task/owner/deadline/priority`。
- 不读取 `meeting_understanding.action_hints`。
- 不会受 `speaker` 影响。

#### 10.3.2 真正有风险的部分

风险主要在 LLM prompt 行为，而不是 Python 类型。

当前 `actions` prompt 写的是：

```text
以 action_hints 为主索引逐条核对 action/owner/timing/condition/topic/evidence
owner：原文姓名原样，否则 null；禁止角色推断；「发言者 N」→ null
```

如果 `action_hints` 新增 `speaker`，`actions` Agent 可能看到：

```json
{
  "speaker": "发言者 6",
  "owner": "管理组和总包单位",
  "action": "制定整改方案"
}
```

这一般没问题。

但如果原文是：

```text
发言者 6：这个问题要尽快处理一下。
```

结构可能是：

```json
{
  "speaker": "发言者 6",
  "owner": null,
  "action": "尽快处理这个问题"
}
```

这时 `actions` Agent 可能误把 `speaker` 当成负责人，生成：

```text
owner = 发言者 6
```

这会破坏现有 actions 的归属规则。

因此，加 `speaker` 本身不是问题，问题是必须同步告诉现有下游：

```text
speaker 只表示谁说出该行动线索，不等于 owner。
actions 任务不得把 speaker 用作负责人。
```

### 10.4 正式实施建议

推荐对 `action_hints` 做最小追加，不改旧字段、不改字段语义、不删除任何字段：

```python
ObjListField("action_hints", [
    StrField("speaker", "说出该行动线索的发言者；有真实姓名写真实姓名，只有发言者编号则保留编号"),
    StrField("action", "原文动作短语（谁+做什么，逐字可截取，可清语气词）"),
    StrField("owner", "原文明示的负责人/承诺人姓名或组织；无明确负责人时为null"),
    StrField("timing", "原文时间约束，保留原文表达；无时为null"),
    StrField("condition", "触发条件，保留原文；无时为null"),
    StrField("topic", "所属议题标题；无对应时为null"),
    EnumField("kind", ACTION_HINT_KINDS),
    StrField("evidence", "原文中支撑此行动线索的一句话"),
])
```

同时需要配套三处文案/规则调整：

#### A. meeting_core prompt

增加规则：

```text
action_hints.speaker：记录说出该行动线索的人；只有发言者编号时保留编号；不得把发言者编号替换成真实姓名。
action_hints.owner：只记录原文明示负责执行的人、角色或组织；speaker 不等于 owner。
```

#### B. actions prompt

增加规则：

```text
如果 action_hints 含 speaker，speaker 只能用于定位证据和理解语境，不能填入 owner。
只有原文明确“speaker 自己负责/我来做/我们这边负责”时，speaker 才可与 owner 一致。
「发言者 N」仍不能作为 owner，除非原文明确把任务分配给该编号身份且用户接受编号负责人。
```

#### C. commitment_timeline prompt

增加规则：

```text
优先使用 action_hints.speaker 作为 speaker。
speaker 缺失时，允许从 evidence 所在发言块回溯；仍缺失则填 null 或“未识别说话人”。
owner 不得由 speaker 自动继承。
```

### 10.5 是否要增加 time_hints

不建议第一版在 core 里增加完整 `time_hints`。

原因：

- 时间归一化是 `commitment_timeline` 的专属能力。
- 加入 core 会增加所有任务线成本。
- `actions`、`minutes`、`risks` 不一定需要完整时间解析。
- 归一化规则复杂，适合在新 task 内独立迭代。

推荐策略：

```text
core 只给 action_hints 补 speaker
commitment_timeline 自己做 time_type / time_bucket / normalized_time
```

### 10.6 可选增加 source_ref

如果后续要做可点击溯源，可增加：

```text
source_ref：原文发言块位置，如 34:33 或 turn_index
```

但这不是 MVP 必需。

### 10.7 最终判断

正式做 `commitment_timeline` 时，`speaker` 值得加。

风险可控，但不能只改 contract。建议作为一个小型兼容改动提交：

```text
1. action_hints contract 增加 speaker
2. meeting_core prompt 说明 speaker/owner 区别
3. actions prompt 明确禁止 speaker 自动变 owner
4. 新 commitment_timeline 任务消费 speaker
5. 用 meeting_all.txt 回归 actions 输出，确认 owner 没被发言者编号污染
```

## 11. 结构化输出契约

推荐新增：

```text
domain/meeting/tasks/commitment_timeline/contracts.py
```

核心字段：

```python
class CommitmentTimelineGenerationContract(GenerationContract):
    fields = [
        ObjListField("commitments", [
            StrField("id", "稳定短ID，如 C1/C2；按原文顺序"),
            StrField("speaker", "说出该承诺/要求/安排的人或发言者编号"),
            StrField("owner", "实际负责执行的人、角色或组织；无明确负责方时为null"),
            StrField("task", "原文动作短语，最小清理口语"),
            StrField("time_text", "原文时间表达；无时为null"),
            EnumField("time_type", [
                "absolute",
                "deadline",
                "relative",
                "condition",
                "unspecified",
            ]),
            StrField("time_bucket", "展示分列：明确时间/截止前/相对时间/条件触发/待补时间"),
            StrField("normalized_time", "有会议日期且可安全归一化时填写；否则为null"),
            StrField("condition", "触发条件或依赖；无时为null"),
            StrField("topic", "所属议题；无时为null"),
            EnumField("source_kind", [
                "commitment",
                "assignment",
                "directive",
                "rectification",
                "followup",
            ]),
            StrField("evidence", "原文证据句"),
            EnumField("confidence", ["high", "medium", "low"]),
        ]),
        ObjListField("time_gaps", [
            StrField("commitment_id", "对应 commitments.id"),
            StrField("reason", "为什么需要补时间"),
            StrField("suggested_question", "可追问的一句话"),
        ]),
        ObjListField("sequence_risks", [
            StrField("title", "顺序风险标题"),
            StrField("commitment_ids", "相关 commitment id，逗号分隔"),
            StrField("reason", "为什么存在顺序风险，必须有证据"),
            StrField("evidence", "原文证据"),
        ]),
        StrField("display_mode", "timeline_board/date_axis/empty/weak_signal"),
    ]
```

字段说明：

- `speaker` 是说话人。
- `owner` 是责任人。
- `time_text` 永远保留原文。
- `normalized_time` 只在安全时填写。
- `time_type` 用于逻辑。
- `time_bucket` 用于渲染。
- `display_mode` 让 HTML 渲染器选择合适页面。

## 12. 时间分类规则

### 12.1 absolute：明确时间

包括：

```text
周三
明天上午
后天下午
9月12日
下周一
```

注意：

- 有 `meeting_time` 时，可把“明天”转成绝对日期。
- 没有 `meeting_time` 时，保留“明天”，不编日期。

### 12.2 deadline：截止前

包括：

```text
出报告之前
正式交付之前
月底前
9月12日前
最迟周五
截至本周五
```

deadline 不是任务持续时间，而是截止点。

### 12.3 relative：相对时间

包括：

```text
会后
下来
接下来
后续
近期
马上
尽快
第一时间
这几天
```

这些词很重要，但不能被伪造成具体日期。

### 12.4 condition：条件触发

包括：

```text
整改完成之后
验收完成后
等接口到位后
客户确认后
如果要下去的话
方案确定后
```

它不是时间，而是前置条件。

### 12.5 unspecified：待补时间

有行动，没有时间。

包括：

```text
资料要完善
这个问题处理一下
相关单位落实
```

这类事项的价值是提示“需要补时间”，不是排期。

## 13. Agent 职责

### 13.1 CommitmentTimelineAgent

输入：

```text
会议原文
meeting_understanding
用户视角信息，可选
meeting_time，可选
```

优先使用：

```text
meeting_understanding.action_hints
meeting_understanding.dependencies
meeting_understanding.decisions
meeting_understanding.open_questions
```

但不能只依赖 `actions` 输出。

原因：

- `actions.deadline` 会排除“尽快”等模糊时间。
- `commitment_timeline` 需要保留模糊时间。
- `actions` 可能按个人视角过滤，丢掉全员承诺。

Agent 要做：

1. 从 action_hints 中确认行动候选。
2. 回看证据句和原文发言块，确定 speaker。
3. 区分 speaker 和 owner。
4. 提取 time_text。
5. 分类 time_type。
6. 安全时生成 normalized_time。
7. 生成 time_bucket。
8. 对缺时间项生成 time_gaps。
9. 仅在证据充分时生成 sequence_risks。
10. 选择 display_mode。

Agent 不做：

- 不做优先级排序。
- 不做个人视角过滤。
- 不把“尽快”换成日期。
- 不把“我们/大家”拆成具体人。
- 不为了好看制造冲突。

### 13.2 CommitmentTimelineSupervisor

重点审核：

- 编造 speaker。
- 编造 owner。
- speaker 和 owner 混淆。
- 把普通讨论当承诺。
- 把已完成事项当未来任务。
- 把模糊时间改成具体日期。
- 遗漏有明确时间表达的 action_hints。
- sequence_risks 没有证据。
- HTML 所需字段缺失过多。

审核标准：

```text
宁可保留模糊时间，也不要制造精确感。
宁可进入待补时间，也不要编 deadline。
```

### 13.3 CommitmentTimelineRender

建议 Markdown 可以由 LLM 渲染，但 HTML 最好用确定性模板生成。

原因：

- HTML 需要视觉稳定。
- LLM 容易多写解释。
- 结构化 JSON 到卡片网格很适合模板渲染。

Render 要做：

1. 根据 `display_mode` 选择布局。
2. 按 speaker 分组。
3. 按 time_bucket 分列。
4. 每列最多展示固定数量卡片。
5. 保留 evidence 的短句展示。
6. 对空态/弱信号态选择克制页面。

## 14. Prompt 核心草案

### 14.1 Generation prompt

```text
你是会议承诺时间线 Agent。

你的任务不是提取普通待办，而是把会议口语中的行动承诺、安排、要求、整改、跟进事项，按说话人和时间确定性组织成可视化数据。

必须区分：
- speaker：谁说出这句话
- owner：原文明确谁负责执行

时间表达必须保留原文：
- 明确时间：周三、明天上午、9月12日
- 截止前：出报告之前、交付前、月底前
- 相对时间：会后、接下来、尽快、第一时间
- 条件触发：整改后、客户确认后、接口到位后
- 待补时间：有行动但没有时间

禁止：
- 编造日期
- 编造负责人
- 把发言者编号替换成真实姓名
- 把普通讨论写成承诺
- 把已完成事项写成后续排期
- 为了生成好看的图而制造冲突

每条 commitment 必须有 evidence。
```

### 14.2 Supervisor prompt

```text
只拦严重问题：
- speaker/owner/time 编造
- 模糊时间被硬转成日期
- speaker 与 owner 混淆
- 已完成事项误入后续排期
- 明确时间承诺遗漏
- 无证据 sequence_risks

不因时间模糊而要求返工；时间模糊是会议事实，应保留。
```

### 14.3 HTML render prompt / template规则

如果使用模板渲染，LLM 只需要输出结构化 JSON。

HTML 模板规则：

```text
标题不超过 12 字
副标题不超过 18 字
顶部只显示承诺数量和待补时间数量
默认五列：明确时间/截止前/相对时间/条件触发/待补时间
每张卡最多 2 行正文 + 1 个时间标签
证据句超过 32 字截断
owner 与 speaker 不同时显示“责任：X”
```

## 15. Markdown 产出

建议输出：

```text
commitment_timeline.md
```

内容结构：

```markdown
# 会议承诺时间线

## 承诺概览

| 说话人 | 责任方 | 任务 | 时间表达 | 时间类型 | 条件/依赖 | 证据 |
|---|---|---|---|---|---|---|

## 待补时间

- ...

## 顺序风险

- ...
```

Markdown 是给人复核用的，不是主要视觉产物。

## 16. HTML 产出

建议输出：

```text
commitment_timeline.html
```

### 16.1 推荐页面骨架

```html
<main class="page">
  <header class="hero">
    <div>
      <h1>会议承诺时间线</h1>
      <p>按说话人整理任务与时间表达</p>
    </div>
    <div class="summary">
      <span>13 条承诺</span>
      <span>3 条待补时间</span>
    </div>
  </header>

  <section class="board">
    <div class="board-head speaker-col">说话人/责任方</div>
    <div class="board-head">明确时间</div>
    <div class="board-head">截止前</div>
    <div class="board-head">相对时间</div>
    <div class="board-head">条件触发</div>
    <div class="board-head">待补时间</div>

    <section class="speaker-cell">发言者 6<br><small>合作局领导</small></section>
    <section class="bucket"></section>
    <section class="bucket">
      <article class="commitment-card deadline">
        <strong>完成整改闭环</strong>
        <span>出报告之前</span>
        <p>最迟要在出报告之前完成整改</p>
      </article>
    </section>
    <section class="bucket">
      <article class="commitment-card relative">
        <strong>研究开裂原因</strong>
        <span>尽快</span>
        <p>还是要尽快整改</p>
      </article>
    </section>
    <section class="bucket">
      <article class="commitment-card condition">
        <strong>验收组复核</strong>
        <span>整改之后</span>
        <p>完成整改之后验收组还要复核</p>
      </article>
    </section>
    <section class="bucket"></section>
  </section>
</main>
```

### 16.2 样式方向

关键不是炫，而是“干净、可信、有层次”。

建议：

```css
body {
  background: #f6f3ee;
  color: #202522;
}

.page {
  max-width: 1180px;
  margin: 40px auto;
  padding: 32px;
  background: #fffdf8;
  border-radius: 24px;
  box-shadow: 0 24px 64px rgba(40, 36, 30, .12);
}

.board {
  display: grid;
  grid-template-columns: 180px repeat(5, minmax(130px, 1fr));
  border-top: 1px solid #d8ddd9;
  border-left: 1px solid #d8ddd9;
}

.board > * {
  border-right: 1px solid #d8ddd9;
  border-bottom: 1px solid #d8ddd9;
}

.commitment-card {
  background: #fff;
  border: 1px solid rgba(32, 37, 34, .10);
  border-radius: 10px;
  padding: 10px;
}
```

注意：

- 表格边框可以有，但要轻。
- 卡片圆角不要过大。
- 不要使用浓重阴影。
- 不要用红色作为主色，只在待补时间或风险中轻量使用。
- HTML 中不要出现大段产品说明。

## 17. 数据到页面的映射

### 17.1 分组

```text
row_key = speaker + owner
```

如果 speaker 和 owner 相同：

```text
显示：李
```

如果不同：

```text
显示：发言者 6
副行：责任：管理组和总包单位
```

如果只有发言者编号：

```text
显示：发言者 6
```

不能凭上下文猜姓名。

### 17.2 分列

```text
absolute -> 明确时间
deadline -> 截止前
relative -> 相对时间
condition -> 条件触发
unspecified -> 待补时间
```

### 17.3 排序

```text
第一排序：原文出现顺序
第二排序：time_type 固定顺序
第三排序：同一格内保持原文顺序
```

不要按模型推断的重要程度排序。

### 17.4 卡片压缩

任务名过长时：

- 去掉口语填充词。
- 保留动词和对象。
- 不改事实。

例如：

```text
我们在验收完成第一时间将三个厂区的资料全部汇总于卢萨卡，包括竣工图进行分类汇总、分类组卷及编码
```

卡片标题可压缩为：

```text
汇总资料并组卷编码
```

证据保留原句短摘。

## 18. API 和落盘

建议接口：

```text
POST /api/v1/meeting/commitment_timeline
GET  /api/v1/meeting/commitment_timeline/file/{request_id}/{file_name}
GET  /api/v1/meeting/commitment_timeline/preview?request_id=...
```

产物：

```text
data/{user_id}/output/{request_id}/commitment_timeline.md
data/{user_id}/output/{request_id}/commitment_timeline.html
```

如果当前运行时仍使用 `result.md + {task}.html`，则兼容：

```text
result.md
commitment_timeline.html
```

## 19. 实现路径

### 19.1 注册任务

```bash
python tools/scripts/register_task.py --domain meeting --task commitment_timeline --name "会议承诺时间线" --with-report
python tools/scripts/sync_domain.py --domain meeting
```

### 19.2 修改 core

正式实现建议修改 core，但只做最小字段追加：

```text
action_hints[].speaker
```

不做：

```text
不删除旧字段
不改 owner 语义
不把 timing 改名
不增加完整 time_hints
不把时间归一化塞进 meeting_core
```

建议修改点：

```text
domain/meeting/meeting_core/contracts.py
domain/meeting/meeting_core/prompts.py
domain/meeting/tasks/actions/prompts.py
```

其中 `actions/prompts.py` 的改动不是为了让 actions 使用 `speaker`，而是为了明确：

```text
speaker 不是 owner，不得因为 speaker 存在就把发言者写成负责人。
```

### 19.3 新增 task 文件

```text
domain/meeting/tasks/commitment_timeline/contracts.py
domain/meeting/tasks/commitment_timeline/prompts.py
domain/meeting/tasks/commitment_timeline/steps/commitment_timeline_agent.py
domain/meeting/tasks/commitment_timeline/steps/commitment_timeline_supervisor.py
domain/meeting/tasks/commitment_timeline/steps/commitment_timeline_render.py
```

### 19.4 渲染建议

优先确定性模板。

流程：

```text
LLM 生成结构化 commitments
Supervisor 审核
Render 生成 Markdown
模板函数生成 HTML
```

不要让 LLM 自由写 HTML。

### 19.5 兼容性回归

新增 `speaker` 后，必须至少跑一次现有 actions 任务回归。

重点检查：

```text
发言者 6 提出要求，但 owner 应是管理组/总包单位，不应变成发言者 6
发言者 1 主持安排，但没有明确自领的任务，不应全部归到发言者 1
只有“请你们/相关单位/大家”的事项，不应编造成具体个人 owner
```

如果发现 actions 结果里 `owner` 出现大量 `发言者 N`，说明 `speaker` 已经污染负责人判断，需要继续收紧 actions prompt。

## 20. 验收标准

### 20.1 对 meeting_all.txt

必须满足：

- 至少抽出 8 条后续承诺/安排/要求。
- 不把已完成验收工作当成未来任务。
- 保留 `会后`、`尽快`、`验收完成第一时间`、`出报告之前`、`交付之前` 这类原文时间。
- `发言者 4` 的资料汇总事项必须出现。
- `发言者 6` 的整改和复核事项必须出现。
- 默认展示五列时间确定性泳道。
- 不展示周一到周五。
- speaker 和 owner 不混淆。
- 新增 `speaker` 后，原有 actions 输出不能把提出要求的人误写成负责人。
- `action_hints[].speaker` 可以是发言者编号，但 `actions[].owner` 仍应遵守原规则。

### 20.2 对强排期会议

必须满足：

- 能识别“明天上午/后天下午/周五前”。
- 有 `meeting_time` 时才能归一化日期。
- 能进入日期轴模式。
- 无 `meeting_time` 时保留相对表达。

### 20.3 对无排期会议

必须满足：

- 不硬画任务卡。
- 不编造后续安排。
- 输出空态或弱信号态。

### 20.4 对 HTML

必须满足：

- 首屏没有大段说明。
- 用户一眼能看到谁、什么事、什么时间类型。
- 卡片不超过三层信息。
- 每张卡有证据。
- 移动端不横向挤压五列。
- 不像普通待办列表。

## 21. 最终产品判断

这条任务线值得做，但要坚持一个边界：

```text
它不是让所有会议都产生排期，而是让所有会议都被诚实地判断是否形成了时间承诺。
```

因此它对所有会议的“有效性”不是同一种：

| 会议情况 | 有效输出 |
|---|---|
| 有明确日期和负责人 | 日期轴/时间线 |
| 有模糊时间和后续动作 | 时间确定性泳道 |
| 有动作但无时间 | 待补时间面板 |
| 只有讨论无行动 | 空态 |

这才是真正通用。

最终建议：

```text
任务名：commitment_timeline
中文名：会议承诺时间线
默认 HTML：按说话人分行 + 五列时间确定性泳道
核心字段：speaker / owner / task / time_text / time_type / condition / evidence
core 改动：正式版建议只给 action_hints 增加 speaker
不要做：待办列表换皮、固定周历、强行冲突检测、编造精确日期
```

如果做得克制，它会比普通待办更有辨识度：用户打开页面时，不是在看“还有哪些事”，而是在看“这场会议刚刚形成了怎样的时间承诺”。
