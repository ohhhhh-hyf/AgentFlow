# 英文 `minutes` 议题纪要 Alignment 执行清单

> 状态：待执行。
>
> 范围：**只做 `minutes` 任务线**，包括普通纪要与议题增强纪要两种模式。
>
> 明确不碰：独立 `agenda_minutes` 任务线、英文文本议程 parser、英文 OCR 兜底、19 套英文模板（已完成）、VLM `promptId`（已确认与 `prompt` 字段无关）。
>
> 目标：`minutes` 线在英文图片议程 + 英文转写下，能正确识别有效议题、完成议题分块，并进入议题增强纪要流程，而不是静默退回普通纪要。

---

## 0. 结论与范围

### 0.1 普通纪要

普通纪要的英文链路已经完成：

- `MinutesGenerationAgent.run(..., lang=...)` 已有；
- `MinutesGenerationSupervisor.review(..., lang=...)` 已有；
- `MinutesGenerationRender` 的英文壳已有；
- 英文模板块、`### I.` 议程标题、supervisor 比对口径均已完成。

普通纪要**不使用** agenda parser / alignment，因此本次剩余改动理论上不会触碰普通纪要。

本次对普通纪要只做两件事：

1. 回归确认；
2. 隔离确认：agenda parser / alignment 的改动不能泄漏到普通纪要。

### 0.2 议题增强纪要

`minutes` 线的议题增强模式链路：

```text
图片议程
  → VLM 识别
  → 结构化 JSON
  → vision_json_to_agenda_plan()
  → AgendaPlan
  → agenda_plan_to_markdown()
  → probe_valid_agendas()
  → process_agenda_for_minutes()
  → parse_agenda_text()（缓存命中或中文表头兜底）
  → align_agenda_with_transcript()
  → tagged_transcript + valid_agendas
  → MinutesGenerationAgent（英文 prompt 已完成）
  → MinutesGenerationSupervisor / Render（英文壳已完成）
```

当前缺口：

1. VLM JSON 里的英文姓名被空格拆碎；
2. 英文转写进入 alignment 后，中文信号全部不命中；
3. `probe_valid_agendas()` 和 `process_agenda_for_minutes()` 没有接收 `lang`；
4. `_ALIGNMENT_CACHE` / `_PROCESS_AGENDA_CACHE` 没有按语种隔离。

最终后果：

```text
probe_valid_agendas() 返回空
  → agenda_from_docs 为空
  → has_valid_agenda=False
  → minutes 静默退回普通纪要
```

---

## 1. `minutes` 线两条路径的边界

### 1.1 普通纪要路径

触发条件：

- `line == "minutes"`；
- docs 中没有被探测为有效议程的内容；
- 或 `probe_valid_agendas()` 返回空。

链路：

```text
meeting_understanding（可跳过）
  → MinutesGenerationAgent
  → MinutesGenerationSupervisor
  → MinutesGenerationRender
```

本次不改：

- `MinutesGenerationAgent`；
- `MinutesGenerationSupervisor`；
- `MinutesGenerationRender`；
- 普通纪要 prompt；
- 普通纪要模板。

只回归：

- 中文普通纪要；
- 英文普通纪要；
- docs 未命中议程时的静默回退。

### 1.2 议题增强纪要路径

触发条件：

- `line == "minutes"`；
- docs 中有图片议程或文本议程；
- `probe_valid_agendas()` 返回非空。

链路：

```text
app/tasks.py：docs 探测
  → probe_valid_agendas()
  → agenda_from_docs
  → extra_line_inputs["agenda_text"]
  → orchestrator：process_agenda_for_minutes()
  → valid_agendas + tagged_transcript
  → state["has_valid_agenda"] = True
  → MinutesGenerationAgent(source_transcript=tagged_transcript)
  → MinutesGenerationSupervisor
  → MinutesGenerationRender
```

本次要改：

- `probe_valid_agendas()` 传 `lang`；
- `process_agenda_for_minutes()` 传 `lang`；
- alignment / 仪式过滤按 `lang` 分支；
- VLM JSON 姓名清洗；
- 两个缓存 key 加 `lang`。

本次不改：

- `orchestrator._line_shared_context()` 的 `议题模式：agenda_enhanced` 标记；
- `orchestrator._supervisor_context()` 的清单顺序；
- `MinutesGenerationAgent` 的 `source_transcript` 接线；
- `MinutesGenerationSupervisor` / `Render`；
- 英文生成 / 审核 / 渲染 prompt；
- 中文打标脚手架。

### 1.3 关键代码入口

| 位置 | 作用 | 本次是否改 |
|---|---|---|
| `app/tasks.py:713-762` | `minutes` 线 docs 议程探测 | 改 `probe_valid_agendas` 传 `lang` |
| `app/tasks.py:725-731` | 图片议程 VLM | **已传 `lang=req.lang`，不改** |
| `app/tasks.py:901-906` | `agenda_text` 注入 | 不改 |
| `orchestrator.py:1368-1394` | `process_agenda_for_minutes` | 改传 `lang` |
| `orchestrator.py:752-759` | `议题模式：agenda_enhanced` + 语种标记 | 不改 |
| `orchestrator.py:833-847` | supervisor 议程清单 | 不改 |
| `agenda_engine.py:144` | `process_agenda_for_minutes` | 加 `lang` |
| `agenda_engine.py:220` | `probe_valid_agendas` | 加 `lang` |
| `alignment_engine.py:784` | `align_agenda_with_transcript` | 加 `lang` |
| `minutes_agent.py:91` | `MinutesGenerationAgent.run` | **已接收 `lang` / `source_transcript`，不改** |
| `minutes_supervisor.py:34` | `review(..., lang=...)` | **已完成，不改** |
| `minutes_render.py:158` | render 英文壳 / `### I.` | **已完成，不改** |

---

## 2. 剩余工作总览

| 优先级 | 事项 | 说明 |
|---|---|---|
| **P0** | VLM JSON 英文姓名清洗 | `Alice Chen` 不能拆成 `Alice`、`Chen` |
| **P0** | `probe_valid_agendas` 传 `lang` | 不传的话，英文议程在入口就探测失败 |
| **P0** | `process_agenda_for_minutes` 传 `lang` | 不传的话，二次处理仍按中文跑 |
| **P0** | 英文 alignment 信号 | 换场、开场、收尾、设备噪声 |
| **P0** | 英文评分 / Track B / 仪式过滤 | 归属与过滤 |
| **P0** | 两个缓存 key 加 `lang` | 防止中英串味 |
| **P1** | 英文议题纪要端到端测试 | 图片议程 → plan → alignment → tagged transcript |
| **P1** | 普通纪要中英文回归 | 确保本次改动不泄漏 |
| **已完成** | 20 套英文议程模板 | `zh/` 与 `en/` 均 20 套 |
| **已确认** | VLM `promptId` | 与 `prompt` 字段无关 |

---

## 3. 分支原则

| 层 | 策略 | 理由 |
|---|---|---|
| VLM JSON 姓名 | **共享、内容自适应** | 不按 `lang` 拆，按字符串内容判断中英文，避免中英混排名单出错 |
| 姓名匹配 | **共享 + ASCII 归一** | 大小写、空格、连字符归一；中文拼音/异体逻辑不动 |
| transcript 分块 | **共享** | 时间戳、`Name:`、`Speaker 1` 等与语种无关 |
| 换场、开场、收尾、设备噪声 | **按语种隔离** | 自然语言短语，中英混跑会误判 |
| 枢纽人物、评分、仪式过滤 | **按语种隔离** | 角色名和仪式词是自然语言 |
| 缓存 key | **alignment / process 加 `lang`** | 同一转写在 zh/en 下信号不同，结果可能不同 |
| parser 缓存 | **不加 `lang`** | parser 仍是语言无关的结构解析 + 姓名清洗 |
| 普通纪要 | **不改** | 不经过 agenda parser / alignment |
| 内部协议标记 | **不改** | `议题模式：agenda_enhanced` 是协议，不是输出 |

**语种来源：**

- HTTP：`req.lang`
- orchestrator：`state.get("lang")`
- `MinutesGenerationAgent`：通用节点自动传 `lang`
- 空值/未知：按 `zh`
- 不做自动语种检测

---

## 4. 执行步骤

### Step 1：VLM JSON 与姓名清洗（无 `lang` 参数）

**目标：** VLM 返回的英文姓名在任何后续解析中都不被拆碎，英文姓名匹配大小写不敏感。

这一步不引入 `lang`，因为姓名拆分按内容自适应，parser 缓存保持不变。

#### 1.1 统一姓名拆分规则

涉及两个函数：

- `agenda_vision.clean_person_names`
- `agenda_parser.clean_presenter_names`

统一改成下面的规则：

1. 去掉 Markdown 符号；
2. 剥离角色前缀：
   - 中文：`汇报人`、`主讲人`、`报告人`、`分享人`、`责任人`、`发言人`、`主持人`、`会议主持`、`全程与会人`、`与会人`、`列席人`、`分段列席人`
   - 英文：`Presenter(s)`、`Speaker(s)`、`Reporter`、`Owner`、`Host`、`Facilitator`、`Presented by`、`Lead`、`Minutes Taker`、`Note Taker`
3. 剥离 5–8 位工号；
4. 剥离中英文括号及内容；
5. 按强分隔符拆分：
   - `;`、`；`、`,`、`，`、`/`、`|`、`、`
   - `\s+and\s+`
   - `\s+&\s+`
   - 两个及以上空格
   - 换行
6. 对每个拆分后的片段：
   - **含中文且内部有空格** → 按空格继续拆（保留中文多人名单行为）；
   - **不含中文** → 保留完整片段，不再按单空格拆（保住 `Alice Chen`）。
7. 过滤空值、纯数字、`TBD`、`TBC`、`N/A`、`None`、`All`、`公开`、`非公开`、`汇报类`、`审议类`；
8. 英文姓名长度上限 64，中文 20。

#### 1.2 必须覆盖的样例

| 输入 | 期望 |
|---|---|
| `Presenter: Alice Chen` | `["Alice Chen"]` |
| `Alice Chen；Bob Lee` | `["Alice Chen", "Bob Lee"]` |
| `Alice Chen, Bob Lee` | `["Alice Chen", "Bob Lee"]` |
| `Alice Chen and Bob Lee` | `["Alice Chen", "Bob Lee"]` |
| `张三 李四` | `["张三", "李四"]` |
| `张三；Alice Chen` | `["张三", "Alice Chen"]` |
| `Dr. Alice Chen` | `["Dr. Alice Chen"]` |
| `TBD` | `[]` |

#### 1.3 `match_presenter_name` 增加 ASCII 归一

- 英文姓名先做 `casefold()`；
- 去掉空格、连字符、撇号、点号；
- 归一后完全相等 → `1.0`；
- 原文整词边界包含（如 `Alice Chen` 出现在 `Alice Chen (PM)`）→ `0.95`；
- **英文不再用任意子串匹配**，避免 `Ann` 误中 `Joanne`；
- 中文的异体字、拼音同音、子串逻辑保持原样。

样例：

```text
match_presenter_name("Alice Chen", "alice chen") >= 0.8
match_presenter_name("Anne-Marie", "Anne Marie") >= 0.8
match_presenter_name("O'Connor", "OConnor") >= 0.8
match_presenter_name("Ann", "Joanne") == 0.0
```

#### 1.4 英文 speaker 提取

`extract_speakers_from_transcript`：

- 增加 `[Alice Chen]` 方括号形态；
- 增加英文姓名形态：1–3 个首字母大写的连续词；
- **不要简单把通用 `{1,16}` 放宽到 `{1,32}`**，避免跨句吞词；英文姓名单独一个分支；
- 姓名长度上限放宽到 32；
- 角色过滤增加 `Host`、`Moderator`、`Chair`、`Chairperson`、`Facilitator`、`MC`、`Organizer`、`Session Chair`。

这批改动对中文转写是超集，不改变原有行为。

#### 1.5 枢纽人物角色前缀

`_identify_hub_speakers`：

- `clean_presenter_names` 使用 Step 1.1 的统一规则；
- `plan.meta.attendees` 角色前缀增加：
  - `Host`、`Moderator`、`Chair`、`Chairperson`、`Facilitator`、`Organizer`、`MC`、`Session Chair`；
- 转写发言人原生角色嗅探增加同样英文角色；
- `"现场发言人"` 和英文 `"Speaker"` 都从枢纽池移除。

#### 1.6 标题行误杀（顺带修）

`parse_agenda_text` 当前逻辑：

```python
any(k in title for k in ("议题名称", "Topic", "序号", "编号"))
```

VLM Markdown 缓存未命中时，合法标题 `Topic Modeling` 可能被跳过。

改为：

- 只有整行/整个单元格是表头别名时才跳过；
- 不因标题包含 `Topic` 就跳过。

#### 1.7 完成标准

- VLM JSON 字符串型 `presenters` / `attendees` 不再拆碎英文姓名；
- VLM Markdown 缓存未命中时，`Alice Chen；Bob Lee` 仍解析为两个人；
- 中文多人名单行为不变；
- 英文姓名匹配大小写、连字符、撇号不敏感；
- 普通纪要路径不使用这些函数，行为不变。

---

### Step 2：`lang` 贯通到 `minutes` 议题增强链路

**目标：** 让 `minutes` 线在入口探测和二次处理时都使用正确语种。

#### 2.1 `probe_valid_agendas` 必须传 `lang`

`app/tasks.py:746-750` 当前：

```python
valid_agendas = (
    probe_valid_agendas(transcript, candidate_agenda_text)
    if (candidate_agenda_text and transcript)
    else []
)
```

改为：

```python
valid_agendas = (
    probe_valid_agendas(transcript, candidate_agenda_text, lang=req.lang)
    if (candidate_agenda_text and transcript)
    else []
)
```

这是**入口门禁**：

- 这里不传 `lang`，英文 alignment 再正确也没用；
- `valid_agendas` 为空 → `agenda_from_docs` 不赋值；
- 后续 `has_valid_agenda=False`，直接退回普通纪要。

#### 2.2 `process_agenda_for_minutes` 必须传 `lang`

`orchestrator.py:1372-1375` 当前：

```python
if "minutes" in selected and agenda_text and transcript_input:
    from domains.meeting.agenda_engine import process_agenda_for_minutes

    agenda_res = process_agenda_for_minutes(transcript_input, agenda_text)
```

改为：

```python
agenda_res = process_agenda_for_minutes(
    transcript_input,
    agenda_text,
    lang=state.get("lang") or "zh",
)
```

这是**二次处理门禁**：

- `probe_valid_agendas()` 只是探测；
- 真正生成 `valid_agendas` 和 `tagged_transcript` 的是这里；
- 这里不传 `lang`，会按中文重跑一遍 alignment。

#### 2.3 Alignment / Engine 签名

新增 `lang`，keyword-only，默认 `"zh"`：

- `probe_valid_agendas(transcript, agenda_text, *, lang="zh")`
- `process_agenda_for_minutes(transcript, agenda_text, *, lang="zh")`
- `_extract_valid_agendas_from_alignment(alignment_res, *, lang="zh")`
- `align_agenda_with_transcript(plan, transcript, *, lang="zh")`
- `_align_agenda_with_transcript_impl(..., *, lang="zh")`
- `_align_by_topics_and_roadsigns(..., *, lang="zh")`
- `_detect_host_roadsign(..., *, lang="zh")`
- `_is_session_closing(content, *, lang="zh")`
- `_is_opening_signal(content, *, lang="zh")`
- `_is_equipment_or_chitchat(content, *, lang="zh")`
- `_build_item_signals_for_content_track(it, *, lang="zh")`
- `is_trivial_ceremonial_item(align, *, lang="zh")`

不新增 `lang` 的函数：

- `parse_agenda_text`；
- `clean_presenter_names`；
- `match_presenter_name`；
- `extract_speakers_from_transcript`；
- `reconcile_presenter_names`；
- `group_transcript_blocks`；
- `_identify_hub_speakers`；
- `_score_block_for_item`。

内部传递必须落实：

- `probe_valid_agendas` 内部调用 `process_agenda_for_minutes(..., lang=lang)`；
- `process_agenda_for_minutes` 内部调用 `align_agenda_with_transcript(..., lang=lang)`；
- `_extract_valid_agendas_from_alignment(alignment_res, lang=lang)`；
- `parse_agenda_text` 不传 `lang`。

否则会出现“入口传了 `lang`，内部又退回中文”的假贯通。

#### 2.4 缓存 key

| 缓存 | 处理 |
|---|---|
| `_PROCESS_AGENDA_CACHE` | 加 `lang` |
| `_ALIGNMENT_CACHE` | 加 `lang` |
| `_PARSED_AGENDA_CACHE` | **不变** |
| `_PARSED_AGENDA_RAW_CACHE` | **不变**（VLM 写入的原始 plan 与语种无关） |

`_PROCESS_AGENDA_CACHE` 当前 key：

```python
(hash(t), hash(a), len(t), len(a), t[:128], a[:128])
```

改为：

```python
(hash(t), hash(a), len(t), len(a), t[:128], a[:128], lang_key)
```

`_ALIGNMENT_CACHE` 当前 key：

```python
(hash(t), len(t), len(plan.items), plan_sig)
```

改为：

```python
(hash(t), len(t), len(plan.items), plan_sig, lang_key)
```

#### 2.5 不改的部分

- `app/tasks.py:725-731` 图片 VLM 已经传 `lang=req.lang`；
- `MinutesGenerationAgent` 已经接收 `lang` 和 `source_transcript`；
- `MinutesGenerationSupervisor` / `Render` 已经支持英文；
- `_line_shared_context()` / `_supervisor_context()` 的标记与清单顺序不动。

#### 2.6 完成标准

- `probe_valid_agendas(..., lang="en")` 能返回非空；
- `process_agenda_for_minutes(..., lang="en")` 返回 `has_valid_agenda=True`；
- 同一段英文转写分别用 `zh`、`en` 调用，不串缓存；
- 中文 `minutes` 议题纪要结果不变；
- 普通纪要路径完全不受影响。

---

### Step 3：英文 alignment 信号

**目标：** 英文转写能识别开场、换场、收尾、设备噪声。

所有英文信号只在 `lang="en"` 时启用；`lang="zh"` 继续跑现有中文列表，中文列表完全不动。

#### 3.1 主持人换场

`_detect_host_roadsign` 增加英文：

- 直接邀请：
  - `Next up, Alice Chen`
  - `Moving on to the next item, Alice`
  - `Let's move on to the release plan`
  - `Please welcome Alice Chen`
  - `I'd like to invite Bob Lee`
  - `Over to Alice`
  - `Now we'll hear from Carol Wu`
- 泛指串场：
  - `Next item`
  - `Next one`
  - `Moving on`
  - `Let's move on`
  - `Up next`
  - `Next topic`
- 角色识别增加：
  - `host`、`moderator`、`chair`、`chairperson`、`facilitator`、`mc`、`organizer`、`session chair`

姓名捕获：

- 只捕获 1–3 个首字母大写的连续词；
- 过滤 `The`、`Next`、`Our`、`This`、`That` 等停用词；
- 英文姓名查找用整词边界，大小写不敏感。

#### 3.2 收尾信号

英文收尾从严，避免 `Thank you` 误判：

- `That's all for today`
- `That concludes the meeting`
- `Let's call it a day`
- `We're done`
- `I'll stop here`
- `To wrap up`
- `Thanks everyone`
- `Thank you all`
- `See you next time`
- `Bye`

排除（不算收尾）：

- `Thank you for the question`
- `Thanks for the feedback`
- `Thanks for pointing that out`
- `Good question`
- `Let me clarify`
- `I'll explain`

#### 3.3 开场信号

- `Can you see my screen`
- `I'm sharing my screen`
- `Let me share`
- `Let's get started`
- `Let's begin`
- `Good morning everyone`
- `Good afternoon everyone`
- `I'll start with`
- `Today I'll walk you through`
- `Here's the agenda`

#### 3.4 设备噪声与闲聊

- `Can you hear me`
- `Can everyone hear me`
- `You're on mute`
- `Microphone`
- `Connection`
- `Reconnecting`
- `Lagging`
- `Screen share`
- `One moment`
- `Give me a second`
- `Coffee`
- `Bathroom`
- `Break`

#### 3.5 完成标准

- 英文开场段不进入任何议题；
- `Moving on to ...` 能触发换场；
- `That's all for today` 能触发收尾；
- `Thank you for the question` 不触发收尾；
- `Can you hear me` 被隔离，不污染上一议题。

---

### Step 4：英文评分、内容轨与仪式过滤

**目标：** 换场识别之后，议题归属和会务项过滤也正确。

#### 4.1 评分中的姓名匹配

`_score_block_for_item`：

- `name in content` → 改成语言感知的姓名查找：
  - `zh`：保持现有子串；
  - `en`：大小写不敏感 + 整词边界；
- 中文 `姓氏 + 工/老师/总/经理/博士/专家` 分支保留；
- 英文增加：
  - `Mr. Chen`
  - `Ms. Chen`
  - `Mrs. Chen`
  - `Dr. Chen`
  - `Prof. Chen`
- `is_presenter` 使用 Step 1 改进后的 `match_presenter_name`。

#### 4.2 `has_team` 修复

`_align_agenda_with_transcript_impl` 阶段 2：

```python
has_team = any(any(p in b.speaker for p in all_team) for b in it_blocks)
```

改为：

```text
any(match_presenter_name(p, b.speaker) >= NAME_MATCH_ACCEPT ...)
```

中文行为等价，英文大小写不敏感。

#### 4.3 Track B 内容轨

`_build_item_signals_for_content_track`：

- 英文标题/描述继续走 `extract_distinctive_tokens`；
- 增加英文事件关键词：
  - `keynote`
  - `opening remarks`
  - `speech`
  - `address`
  - `panel`
  - `Q&A`
  - `discussion`
  - `signing ceremony`
  - `award`
  - `group photo`
  - `video`
  - `break`
  - `lunch`
  - `tour`
  - `demo`
- 英文角色/尊称：
  - `CEO`、`CTO`、`CFO`、`COO`、`VP`、`Director`、`Manager`、`Lead`、`Head`
  - `Dr.`、`Prof.`
- `_TRANSITION_ROADSIGN_PATTERN` 增加英文：
  - `next`
  - `moving on`
  - `let's move`
  - `up next`
  - `switching to`
  - `going to`
  - `start with`
  - `begin with`
  - `wrap up`
- `_HIGH_CONFIDENCE_SIGNALS` 增加英文对应项；
- `_find_transition_candidate` 中 `sig in content` 改为：
  - `zh`：子串；
  - `en`：大小写不敏感整词匹配。

#### 4.4 仪式/后勤项过滤

`is_trivial_ceremonial_item` 增加英文：

- 仪式/后勤：
  - `group photo`
  - `photo`
  - `video`
  - `warm-up video`
  - `promo`
  - `break`
  - `coffee break`
  - `lunch`
  - `dinner`
  - `refreshments`
  - `tour`
  - `visit`
  - `walk`
  - `gather`
  - `sign in`
  - `registration`
  - `collect materials`
  - `departure`
  - `check out`
- 强业务词：
  - `review`
  - `release`
  - `architecture`
  - `optimization`
  - `evolution`
  - `algorithm`
  - `model`
  - `system`
  - `insight`
  - `workshop`
  - `defense`
  - `proposal`
  - `technical`
  - `code`
  - `metric`
  - `latency`
  - `version`
  - `launch`
  - `roadmap`
  - `speech`
  - `remarks`
  - `report`
  - `presentation`
  - `share`
  - `interaction`
  - `exchange`
  - `Q&A`
  - `signing`
  - `award`
  - `design`
  - `planning`
  - `summary`
  - `progress`
  - `alignment`
  - `testing`
  - `deployment`
  - `commercial`
- 英文关键词统一 `lower()` + 整词边界，避免 `read` 命中 `already`；
- 字符阈值先保持不变，用英文夹具验证后再决定是否调整。

#### 4.5 完成标准

- 英文 `has_team` 大小写不敏感；
- `Dr. Chen` 能加分；
- `Group Photo` / `Lunch Break` / `Video Playback` 被剔除；
- `Architecture Review` / `Release Plan` 被保留；
- 英文 Track B（VLM 没识别到汇报人）能靠 `next / moving on` 和标题词切换。

---

### Step 5：测试

#### 5.1 VLM JSON 与姓名

文件：`tests/unit/meeting/test_agenda_vision.py`

- `test_vision_json_english_presenters_not_split`
- `test_vision_json_english_attendees_not_split`
- `test_vision_json_mixed_cn_en_names`
- 保留并确认现有 raw cache 断言不变。

文件：`tests/unit/meeting/test_agenda_parser.py`

- `test_clean_presenter_names_english`
- `test_clean_presenter_names_mixed_cn_en`
- `test_match_presenter_name_english`
- `test_parse_agenda_markdown_with_english_names`

#### 5.2 Alignment 单测

文件：`tests/unit/meeting/test_agenda_alignment.py`

- `test_english_session_closing_signals`
- `test_english_closing_exclusion`
- `test_english_opening_signals`
- `test_english_equipment_chitchat`
- `test_english_host_roadsign`
- `test_align_english_transcript_named_track`
- `test_align_english_transcript_content_track`
- `test_english_ceremonial_filtering`
- `test_align_agenda_with_transcript_lang_cache_isolation`

#### 5.3 Engine 单测

文件：`tests/unit/meeting/test_agenda_engine.py`

- `test_probe_valid_agendas_english`
- `test_process_agenda_for_minutes_english`
- `test_process_agenda_for_minutes_english_cache_key`
- `test_english_ceremonial_and_skipped_filtering`

#### 5.4 `minutes` 线调用链

文件：`tests/unit/meeting/test_minutes_agenda_integration.py`

- `test_probe_valid_agendas_passes_lang`
- `test_process_agenda_passes_lang`
- `test_minutes_agenda_en_pipeline`
- `test_minutes_agenda_zh_unchanged`
- `test_minutes_normal_en_does_not_enter_agenda_mode`
- `test_minutes_normal_zh_unchanged`

#### 5.5 端到端（纯 Python）

文件：`tests/integration/meeting/test_agenda_pipeline.py`

新增一条英文链路（不调 LLM）：

```text
英文 VLM JSON
  -> vision_json_to_agenda_plan()
  -> probe_valid_agendas(lang="en")
  -> process_agenda_for_minutes(lang="en")
  -> align_agenda_with_transcript(lang="en")
  -> 断言 has_valid_agenda=True、议题顺序、tagged_transcript 含英文议题内容
```

再新增一条反向链路：

```text
同一份英文议程 + 英文转写
  -> probe_valid_agendas(lang="zh")
  -> 允许返回空（证明 lang 分支真实生效）
```

#### 5.6 普通纪要回归

必须确认以下内容不变：

- `tests/unit/meeting/test_multi_source_minutes.py` 中的普通纪要辅助材料测试；
- `tests/unit/meeting/test_template_i18n.py` 中的普通纪要英文 prompt 测试；
- `tests/unit/meeting/test_minutes_agenda_integration.py` 中的普通纪要路由测试；
- 中文普通纪要草稿字段与渲染结构。

新增：

- `test_normal_minutes_english_unchanged`
- `test_normal_minutes_zh_unchanged`
- `test_normal_minutes_with_non_agenda_docs_falls_back`

#### 5.7 回归命令

```powershell
python -m pytest tests/unit/meeting/test_agenda_vision.py tests/unit/meeting/test_agenda_parser.py tests/unit/meeting/test_agenda_alignment.py tests/unit/meeting/test_agenda_engine.py -q
python -m pytest tests/unit/meeting/test_minutes_agenda_integration.py tests/unit/meeting/test_multi_source_minutes.py tests/unit/meeting/test_template_i18n.py -q
python -m pytest tests/unit/meeting -q
python -m pytest tests/unit/core -q
python -m pytest tests/integration/meeting/test_agenda_pipeline.py -q
```

基线：

- `tests/unit/meeting`：157 passed / 9 skipped；
- `tests/unit/core`：101 passed / 4 pre-existing failures。

新增用例必须全绿，既有失败不能增加。

#### 5.8 Lint

```powershell
python -m ruff check domains/meeting/tasks/agenda_minutes/agenda_parser.py domains/meeting/tasks/agenda_minutes/alignment_engine.py domains/meeting/agenda_engine.py domains/meeting/agenda_vision.py app/tasks.py domains/meeting/orchestrator.py
```

允许既有 RUF022 等历史问题，但不能新增错误。

---

### Step 6：验收矩阵

| 场景 | `lang` | 期望 |
|---|---|---|
| 中文普通纪要，无议程 docs | `zh` | 普通纪要，行为与改动前一致 |
| 英文普通纪要，无议程 docs | `en` | 普通纪要，英文输出，不进入议程模式 |
| 中文图片议程 + 中文转写 | `zh` | `has_valid_agenda=True`，中文议题纪要行为不变 |
| 英文图片议程 + 英文转写 | `en` | `has_valid_agenda=True`，议题正确归属，英文正文 |
| 英文图片议程 + 英文转写，但用 `lang=zh` | `zh` | 允许探测失败并回退普通纪要，证明 `lang` 分支生效 |
| docs 不是议程（参考材料） | `en` / `zh` | 静默回退普通纪要，不误报议题 |

逐项确认：

- [ ] VLM JSON 字符串型英文姓名不被空格拆碎；
- [ ] 英文姓名匹配大小写、连字符、撇号不敏感；
- [ ] `probe_valid_agendas(..., lang="en")` 非空；
- [ ] `process_agenda_for_minutes(..., lang="en")` 返回 `has_valid_agenda=True`；
- [ ] 英文换场、开场、收尾、设备噪声识别正确；
- [ ] 英文仪式/后勤项被剔除，实质议题保留；
- [ ] 英文 Track B 能靠路标和标题词切换；
- [ ] `_ALIGNMENT_CACHE`、`_PROCESS_AGENDA_CACHE` 带 `lang`，中英不串味；
- [ ] parser 缓存 key 不变，中文解析结果与改动前一致；
- [ ] 普通纪要中英文路径完全不变；
- [ ] `agenda_minutes` 独立任务线完全未触碰；
- [ ] 既有中文测试全绿，既有失败不增加；
- [ ] 无新增 lint 错误。

---

## 5. 普通纪要隔离清单

为了确保本次改动不泄漏到普通纪要，明确以下文件/函数**不修改**：

| 文件 | 原因 |
|---|---|
| `domains/meeting/tasks/minutes/steps/minutes_agent.py` | 普通纪要生成；已支持英文 |
| `domains/meeting/tasks/minutes/steps/minutes_supervisor.py` | 普通纪要审核；已支持英文 |
| `domains/meeting/tasks/minutes/steps/minutes_render.py` | 普通纪要渲染；已支持英文 |
| `domains/meeting/tasks/minutes/prompts.py` | 普通纪要 prompt；已完成 |
| `domains/meeting/tasks/minutes/prompt_map.py` | 视角路由；已完成 |
| `domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py` | 独立任务线生成，不改 |
| `domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_supervisor.py` | 独立任务线审核，不改 |
| `domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_render.py` | 独立任务线渲染，不改 |
| `domains/meeting/tasks/agenda_minutes/prompts.py` | 独立任务线 prompt，不改 |
| `app/tasks.py` 的 `line == "agenda_minutes"` 分支 | 独立任务线，不改 |

> 注意：`domains/meeting/tasks/agenda_minutes/agenda_parser.py` 和 `alignment_engine.py`
> 虽然位于 `agenda_minutes/` 目录下，但它们是 `minutes` 议题增强模式**共享**的
> parser / alignment 模块，本次允许修改。独立 `agenda_minutes` 任务线只不改
> `steps/agenda_minutes_*.py` 与 `prompts.py`。
| `orchestrator._line_shared_context()` | 普通纪要上下文；不改 |
| `orchestrator._supervisor_context()` | 普通纪要审核上下文；不改 |

只允许改：

- `agenda_vision.py`；
- `agenda_parser.py`；
- `alignment_engine.py`；
- `agenda_engine.py`；
- `app/tasks.py` 的 `line == "minutes"` 分支；
- `orchestrator.py` 的 `process_agenda_for_minutes` 调用点；
- 对应测试。

---

## 6. 明确不做

1. **独立 `agenda_minutes` 任务线**：不传 lang、不改 prompt、不改 agent；
2. **英文文本议程 parser**：不补英文表头、列名、行列表、元数据；
3. **英文 OCR 兜底**：VLM 失败后的 OCR + 中文重构链路不做英文化；
4. **19 套英文议程模板**：已完成，不在本次范围；
5. **VLM `promptId`**：已确认与 `prompt` 字段无关；
6. **会议类型关键词英文化**：`detect_agenda_type` 的 `spec.keywords` 仍以中文为主，只影响独立 `agenda_minutes` 线；
7. **英文打标脚手架本地化**：默认保留中文标签，见第 7 节；
8. **`_ocr_single_agenda_doc`**：当前无调用，不处理。

---

## 7. 待确认决策

### 7.1 英文打标脚手架是否本地化？

当前 `agenda_engine.build_tagged_transcript_with_head_tail` 输出：

```text
【现场审定的有效议题清单】
【会议开场背景与主线脉络】
【议题 02：Architecture Review】（汇报人：Alice Chen）
【会末收尾与全场定调】
```

**推荐：保留中文脚手架。**

理由：

- 英文 `minutes` prompt 正文仍是中文指令，且显式引用这些中文标签；
- 只改标签会让 prompt 引用不存在的标签；
- 彻底英文化要同时改 `agenda_engine`、`orchestrator`、`prompts.py`，属于独立工程；
- 脚手架是内部控制标签，最终交付正文仍是全英文。

### 7.2 英文仪式过滤阈值是否调整？

**推荐：先保持现有字符阈值不变。**

用英文夹具验证：

- `Group Photo`、`Lunch Break`、`Video Playback` 应剔除；
- `Architecture Review`、`Release Plan` 应保留；
- 只有明确误杀/漏杀时，才调英文分支阈值。

### 7.3 `lang` 为空时是否自动检测语种？

**推荐：不自动检测。**

以请求 `lang` 为准，空值按 `zh`。自动检测会改变现有中文行为。

---

## 8. 变更文件清单

| 文件 | 改动 |
|---|---|
| `domains/meeting/agenda_vision.py` | VLM JSON 英文姓名清洗、标题行误杀修复 |
| `domains/meeting/tasks/agenda_minutes/agenda_parser.py` | 姓名拆分、ASCII 匹配、英文 speaker 提取、标题守卫 |
| `domains/meeting/tasks/agenda_minutes/alignment_engine.py` | `lang` 参数、英文换场/开场/收尾/设备/仪式信号、评分与内容轨 |
| `domains/meeting/agenda_engine.py` | `lang` 贯通、`_PROCESS_AGENDA_CACHE` key、仪式过滤传参 |
| `app/tasks.py` | `line == "minutes"` 的 `probe_valid_agendas` 传 `lang` |
| `domains/meeting/orchestrator.py` | `process_agenda_for_minutes` 传 `lang` |
| `tests/unit/meeting/test_agenda_vision.py` | VLM JSON 英文姓名测试 |
| `tests/unit/meeting/test_agenda_parser.py` | 姓名清洗/匹配/英文字段测试 |
| `tests/unit/meeting/test_agenda_alignment.py` | 英文 alignment 测试 |
| `tests/unit/meeting/test_agenda_engine.py` | 英文 engine / 缓存测试 |
| `tests/unit/meeting/test_minutes_agenda_integration.py` | `minutes` 线中英文调用链测试 |
| `tests/integration/meeting/test_agenda_pipeline.py` | 英文端到端纯 Python 链路 |

已完成、不在本次改动范围：

- `resources/agenda_templates/en/*.md`：20 套英文议程模板；
- VLM `promptId`：已确认与 `prompt` 字段无关。

---

## 9. 风险与回滚

| 风险 | 处理 |
|---|---|
| 英文短语误判，改变换场 | 英文信号从严；每条信号配单测；中文列表完全不动 |
| 英文姓名被拆碎 | 内容自适应拆分；用 `Alice Chen`、`Anne-Marie`、`O'Connor`、中英混排夹具覆盖 |
| 英文姓名子串误匹配 | 英文取消任意子串，改用整词边界 |
| 英文仪式阈值不合适 | 先不调阈值，用夹具验证后再定 |
| `probe_valid_agendas` 漏传 `lang` | 入口门禁测试 `test_probe_valid_agendas_passes_lang` |
| `process_agenda_for_minutes` 漏传 `lang` | 二次处理测试 `test_process_agenda_passes_lang` |
| 缓存串味 | `_ALIGNMENT_CACHE`、`_PROCESS_AGENDA_CACHE` 加 `lang`；parser 缓存不变 |
| 普通纪要回归 | 独立回归测试 + 明确隔离清单 |

**回滚策略：**

- 所有新增参数默认 `lang="zh"`，中文路径不受影响；
- 姓名清洗是超集，中文夹具回归通过即可；
- 如果英文信号引发问题，只回滚对应英文 pattern 列表，不动骨架；
- 普通纪要链路未改动，回滚范围只限 agenda 相关文件。
