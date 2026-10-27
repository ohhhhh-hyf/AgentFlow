# 英文议程 Parser + Transcript Alignment 执行清单

> 状态：待执行。本文件只定方案与步骤，不改代码。
>
> 范围：`lang=en` 时，英文文本议程单（txt/md）能被解析成 `AgendaPlan`，英文转写能被正确换场、归属、过滤，最终 `has_valid_agenda=True`，不静默退回普通纪要。
>
> 不在本次范围：19 套英文议程模板、OCR 重构 prompt 英文化、会议类型关键词英文化、VLM `promptId` 服务侧确认。

---

## 0. 结论

你的判断是对的：这两项不是“中文翻英文”，而是**英文原生内容的识别规则缺失**。

当前 parser / alignment 的骨架是中文关键词驱动的。英文内容进来后：

1. 英文表格可能连表头门禁都过不了；
2. 英文行列表的 Presenter 标签不认；
3. 英文姓名被空格切碎；
4. 英文换场、开场、收尾、后勤项、仪式项信号全不认；
5. 最后 `probe_valid_agendas` 返回空 → `has_valid_agenda=False` → **静默退回普通纪要**。

所以正确做法不是加翻译层，而是：

- 用 `lang` 选择规则集；
- 中文规则原样保留；
- 英文规则按英文原生表达补齐；
- 结构性别名（表头、列名、元数据标签）中英共享；
- 自然语言信号（换场、开场、收尾、仪式）按语种隔离；
- 所有缓存 key 带 `lang`，避免中英结果串味。

---

## 1. 分支原则

先把“哪些共享、哪些按语种隔离”定死，后面所有步骤照此执行。

| 层 | 策略 | 理由 |
|---|---|---|
| 表格表头、列名、元数据标签 | **中英共享的超集** | 这些是结构别名，不是自然语言；中英都认不会误伤，还能兼容 OCR 兜底产出的中文表头 |
| Presenter 角色前缀 | **中英共享的超集** | `Presenter:` 和 `汇报人：` 都是标签，不会互相误伤 |
| 姓名拆分 | **按语种分支** | 中文按空格拆；英文绝不能按单空格拆，否则 `Alice Chen` 变两个人 |
| 姓名匹配 | **共享 + ASCII 归一** | 大小写、空格、连字符归一；中文原有拼音/异体逻辑不动 |
| 换场、开场、收尾、设备噪声、仪式过滤 | **按语种隔离** | 这些是自然语言短语；中英混跑会带来误判 |
| 时间戳、发言块聚合、评分阈值、缓存结构 | **共享** | 与语种无关 |
| 缓存 key | **必须带 `lang`** | 同一段文本在 zh/en 下可能解析结果不同 |
| 默认值 | **统一 `lang="zh"`** | 所有新增参数 keyword-only 追加在末尾；现有调用不传不受影响 |
| 内部协议标记 | **不改** | `议题模式：agenda_enhanced` 是协议标记，不是输出内容，不能翻译 |

**语种来源：**

- HTTP 请求：`req.lang`
- orchestrator：`state.get("lang")`
- `AgendaMinutesAgent`：`parse_lang_mode(shared_context)`
- 空值/未知值：一律按 `zh`
- **不做自动语种检测**，以请求 `lang` 为准

---

## 2. 缺口清单

### 2.1 Parser

| 位置 | 现状 | 英文后果 |
|---|---|---|
| `agenda_parser.py:451` `has_seq_and_role` | 只认「序号/编号/汇报/主讲/时长/内容」 | 纯英文表头 `# / Agenda Item / Presenter / Duration` 识别不到表头 |
| `agenda_parser.py:103` `_resolve_columns` | 英文只零散支持 `no/seq/reporter/duration/attendees` | `Presenter/Speaker/Owner/Title/Subject` 列全部落空 |
| `agenda_parser.py:120` seq 别名 | `any("no" in name ...)` | `Notes` 列会被误判成序号列 |
| `agenda_parser.py:478` 标题行跳过 | 标题含 `Topic` 就跳过 | 合法议题 `Topic Modeling` 可能被误跳过 |
| `agenda_parser.py:545` 行列表 Presenter | 只认中文标签 | `Presenter: Alice Chen` 提取不到汇报人 |
| `agenda_parser.py:200` 角色前缀 | 只剥离中文前缀 | `Presenter: Alice Chen` 清洗后仍带前缀 |
| `agenda_parser.py:206` 姓名拆分 | 按 `\s` 拆 | `Alice Chen` 被拆成 `Alice`、`Chen` |
| `agenda_parser.py:257` `match_presenter_name` | 大小写敏感；任意子串命中 | `alice chen` 匹配不上 `Alice Chen`；`Ann` 可能误中 `Joanne` |
| `agenda_parser.py:287` `extract_speakers_from_transcript` | 只支持中文方括号；长度上限 12 | `[Alice Chen]` 不认；长英文名被丢弃 |
| `agenda_parser.py:429` 元数据 | 英文只认 `Subject/Time/Attendees` | `Date/Chair/Host/Moderator/Participants` 不认 |

补充：现有行列表正则其实已经能匹配 `1. Opening Remarks`（数字序号分支），主要缺的是 `Item 1:`、`Agenda Item 1 -`、`Session 1:` 和英文 Presenter 标签。

### 2.2 Alignment

| 位置 | 现状 | 英文后果 |
|---|---|---|
| `alignment_engine.py:133` 主持人换场 | 只认中文路标 | `Moving on to the next item`、`Please welcome Alice` 不触发换场 |
| `alignment_engine.py:148` 收尾 | 只认中文收尾语 | `That's all for today` 不触发收尾 |
| `alignment_engine.py:162` 开场 | 只认中文开场语 | `Can you see my screen` 不识别 |
| `alignment_engine.py:171` 设备噪声 | 只认中文试音 | `Can you hear me`、`You're on mute` 不隔离 |
| `alignment_engine.py:434` 枢纽人物 | 只认中文角色 | `Host/Moderator/Chair/Facilitator` 不进枢纽池 |
| `alignment_engine.py:545` 点名 | 中文姓氏+尊称 | `Dr. Chen` 不加分 |
| `alignment_engine.py:647` 内容轨路标 | 只认中文转场词 | `next / moving on / up next` 不触发 |
| `alignment_engine.py:1034` 仪式过滤 | 只认中文仪式词 | `Group Photo`、`Lunch Break`、`Video Playback` 不被剔除 |
| `alignment_engine.py:981` `has_team` | `p in b.speaker` 大小写敏感 | `alice chen` 匹配不上 `Alice Chen` |
| `alignment_engine.py:690` 内容轨信号 | `sig in content` 大小写敏感 | 标题 `Architecture Review` 匹配不上正文 `architecture review` |

### 2.3 调用链

| 位置 | 问题 |
|---|---|
| `app/tasks.py:696` | `agenda_minutes` 线没有把 `lang=req.lang` 传给 VLM |
| `app/tasks.py:747` | `probe_valid_agendas` 没有传 `lang` |
| `orchestrator.py:1375` | `process_agenda_for_minutes` 没有传 `lang` |
| `agenda_minutes_agent.py:740` | `parse_agenda_text` 没有传 `lang` |
| `agenda_minutes_agent.py:747` | `align_agenda_with_transcript` 没有传 `lang` |
| `agenda_vision.py:199` | OCR 兜底没有 `lang`，`parse_agenda_text` 按中文跑 |
| `agenda_vision.py:321` | `_PARSED_AGENDA_RAW_CACHE` 只按文本做 key，中英可能串味 |

### 2.4 缓存

| 缓存 | 现状 | 需要 |
|---|---|---|
| `_PARSED_AGENDA_CACHE` | `(text, speakers)` | 加 `lang` |
| `_PARSED_AGENDA_RAW_CACHE` | `text` | 改成 `(text, lang)` |
| `_PROCESS_AGENDA_CACHE` | 文本 hash/长度/前缀 | 加 `lang` |
| `_ALIGNMENT_CACHE` | `(hash, len, item_count, plan_sig)` | 加 `lang` |

---

## 3. 执行步骤

### Step 1：`lang` 贯通 + 缓存隔离（前置，必须先做）

**目标：** 让所有 parser/alignment 入口都能拿到 `lang`，并保证 zh/en 缓存不互相污染。

#### 1.1 统一语种归一

在 `agenda_parser.py` 增加一个内部函数：

```text
normalize_lang(lang: str | None) -> str
  只有明确等于 "en" 才返回 "en"，其余（空、zh、未知）一律 "zh"
```

`alignment_engine.py`、`agenda_engine.py`、`agenda_vision.py` 复用这个函数，避免各写一套。

#### 1.2 Parser 签名

全部新增 `lang` 参数，**keyword-only，默认 `"zh"`，追加在参数末尾**：

- `parse_agenda_text(..., *, lang: str = "zh")`
- `clean_presenter_names(..., *, lang: str = "zh")`
- `extract_speakers_from_transcript(..., *, lang: str = "zh")`
- `reconcile_presenter_names(..., *, lang: str = "zh")`

#### 1.3 Alignment 签名

- `align_agenda_with_transcript(plan, transcript, *, lang: str = "zh")`
- `_align_agenda_with_transcript_impl(..., *, lang: str = "zh")`
- `_align_by_topics_and_roadsigns(..., *, lang: str = "zh")`
- `_detect_host_roadsign(..., *, lang: str = "zh")`
- `_is_session_closing(content, *, lang: str = "zh")`
- `_is_opening_signal(content, *, lang: str = "zh")`
- `_is_equipment_or_chitchat(content, *, lang: str = "zh")`
- `_identify_hub_speakers(..., *, lang: str = "zh")`
- `_score_block_for_item(..., *, lang: str = "zh")`
- `_build_item_signals_for_content_track(it, *, lang: str = "zh")`
- `is_trivial_ceremonial_item(align, *, lang: str = "zh")`

#### 1.4 Engine 签名

- `process_agenda_for_minutes(transcript, agenda_text, *, lang: str = "zh")`
- `probe_valid_agendas(transcript, agenda_text, *, lang: str = "zh")`
- `_extract_valid_agendas_from_alignment(alignment_res, *, lang: str = "zh")`

#### 1.5 Vision 签名

- `clean_person_names(raw_val, *, lang: str = "zh")`
- `vision_json_to_agenda_plan(data, transcript="", candidate_speakers=None, *, lang: str = "zh")`
- `ocr_fallback_single_agenda_doc(image_paths, candidate_speakers=None, *, lang: str = "zh")`

#### 1.6 调用点全部补齐

| 调用点 | 传值 |
|---|---|
| `app/tasks.py:747` `probe_valid_agendas(...)` | `lang=req.lang` |
| `app/tasks.py:696` `extract_agenda_from_image_docs(...)` | `lang=req.lang` |
| `orchestrator.py:1375` `process_agenda_for_minutes(...)` | `lang=state.get("lang") or "zh"` |
| `agenda_minutes_agent.py:740` `parse_agenda_text(...)` | `lang=parse_lang_mode(shared_context)` |
| `agenda_minutes_agent.py:747` `align_agenda_with_transcript(...)` | `lang=parse_lang_mode(shared_context)` |
| `agenda_vision.py:234` `parse_agenda_text(...)` | `lang=lang` |
| `agenda_vision.py:288` `vision_json_to_agenda_plan(...)` | `lang=lang` |
| `agenda_vision.py:334` `ocr_fallback_single_agenda_doc(...)` | `lang=lang` |
| `agenda_engine.py:164` `parse_agenda_text(...)` | `lang=lang` |
| `agenda_engine.py:176` `align_agenda_with_transcript(...)` | `lang=lang` |

> 注意：`app/tasks.py:696` 这条覆盖此前 VLM 清单里“agenda_minutes 调用点保持不变”的结论。现在 `agenda_minutes` 也要支持英文图片议程，必须传 `lang`。

#### 1.7 缓存 key 改造

| 缓存 | 新 key |
|---|---|
| `_PARSED_AGENDA_CACHE` | `(normalized_text, spk_tuple, lang_key)` |
| `_PARSED_AGENDA_RAW_CACHE` | `(normalized_text, lang_key)` |
| `_PROCESS_AGENDA_CACHE` | `(hash(t), hash(a), len(t), len(a), t[:128], a[:128], lang_key)` |
| `_ALIGNMENT_CACHE` | `(hash(t), len(t), len(plan.items), plan_sig, lang_key)` |

同步修改：

- `agenda_vision.py:321` 写入 `_PARSED_AGENDA_RAW_CACHE[(agenda_md, lang_key)]`
- `tests/unit/meeting/test_agenda_vision.py:102` 断言改为 `(md, "zh") in _PARSED_AGENDA_RAW_CACHE`

#### 1.8 完成标准

- `grep` 所有 `parse_agenda_text` / `align_agenda_with_transcript` / `process_agenda_for_minutes` / `probe_valid_agendas` 调用点，无遗漏；
- 不传 `lang` 的旧调用全部走 `zh`，中文行为不变；
- 同一段英文议程分别用 `zh`、`en` 调用，结果不串缓存。

---

### Step 2：Parser 表格与列解析

**目标：** 英文 Markdown / 管道表格能识别表头、解析出议题。

#### 2.1 表头门禁

`agenda_parser.py:451` 的 `has_topic` / `has_seq_and_role` 改成中英共享超集：

**has_topic 增加：**

- `agenda item`
- `subject`
- `title`
- `session`
- `discussion item`
- `item`

**has_seq_and_role 增加：**

- 序号侧：`#`、`no.`、`no`、`seq`、`sequence`、`order`、`item no`、`item #`
- 角色/时长/内容侧：`presenter`、`speaker`、`reporter`、`owner`、`duration`、`time`、`content`、`description`

保留原来的 `has_topic or has_seq_and_role` 逻辑。

#### 2.2 列别名

`_resolve_columns` 按现有优先级补英文别名，**顺序不变**：

| 列 | 新增英文别名 |
|---|---|
| seq | `#`、`no.`、`no`、`seq`、`sequence`、`order`、`item no`、`item #` |
| duration | `duration`、`length`、`allocated time`、`minutes`、`time (min)` |
| time | `time`、`time slot`、`schedule`、`date & time` |
| category | `category`、`type`、`track` |
| presenter | `presenter`、`presenters`、`speaker`、`speakers`、`reporter`、`owner`、`host`、`facilitator`、`presented by`、`lead` |
| recorder | `recorder`、`note taker`、`minutes taker`、`secretary` |
| members | `attendees`、`participants`、`members`、`team` |
| description | `content`、`description`、`notes`、`remarks`、`details`、`objective`、`purpose` |
| title | `topic`、`title`、`subject`、`agenda item`、`session`、`discussion`、`item` |

#### 2.3 ASCII 别名必须整词匹配

当前 `any(k in name)` 有两个英文坑：

- `"no" in "notes"` → `Notes` 被误判成序号列；
- `"item"` 同时可能命中标题列和序号列。

改成一个统一判断：

- 中文别名：保持子串匹配；
- 英文/ASCII 别名：用整词边界匹配，例如 `(?<![a-z0-9])no\.?(?![a-z0-9])`；
- 大小写不敏感。

#### 2.4 标题行保护

`agenda_parser.py:478` 当前是“标题含 `Topic` 就跳过”。改为：

- 只有整行看起来像表头时才跳过；
- 或只当标题单元格**整词等于**已知表头别名时才跳过；
- 不允许 `Topic Modeling` 这种合法议题被误杀。

#### 2.5 完成标准

以下三种表头都能解析出 2–3 条议题，且标题、汇报人、时长正确：

```text
| # | Agenda Item | Presenter | Duration |
| No. | Topic | Speaker | Time |
| Seq | Subject | Owner | Length |
```

---

### Step 3：Parser 行列表、Presenter 标签与元数据

**目标：** 英文纯文本议程（无表格）也能解析。

#### 3.1 行列表

保留现有中文数字/「议题一」正则，增加英文形态：

- `1. Opening Remarks`
- `1) Opening Remarks`
- `Item 1: Opening Remarks`
- `Agenda Item 1 - Opening Remarks`
- `Topic 1: Opening Remarks`
- `Session 1: Opening Remarks`
- `Part 1 - Opening Remarks`

建议：

- 数字序号继续复用现有分支；
- 新增 `Item / Agenda Item / Topic / Session / Part + 数字或罗马数字 + 分隔符` 分支；
- 不支持裸 `-` / `*` 项目符号，避免把普通说明行吞成议题。

#### 3.2 Presenter 标签

行列表 body 中增加英文提取：

- `Presenter: Alice Chen`
- `Presenters: Alice Chen, Bob Lee`
- `Speaker: Alice Chen`
- `Reporter: Alice Chen`
- `Owner: Alice Chen`
- `Presented by Alice Chen`
- `Lead: Alice Chen`
- 括号内联：`(Presenter: Alice Chen)`、`[Speaker: Alice Chen]`

提取后：

- 从标题中移除该片段；
- 去掉尾部的 `-`、`—`、`|`；
- 可选提取 `(15 min)` / `[15 min]` 到 `duration`。

#### 3.3 元数据

`agenda_parser.py:429` 增加英文标签：

- 主题：`Subject`、`Meeting Subject`、`Title`
- 时间：`Date`、`Meeting Date`、`Time`、`Date & Time`、`Date and Time`
- 人员：`Attendees`、`Participants`、`Present`、`Chair`、`Host`、`Moderator`、`Facilitator`、`Organizer`

继续排除表格行（含 `|`）和列名行。

#### 3.4 完成标准

以下 5 种写法都能解析出正确标题和汇报人：

```text
1. Opening Remarks — Presenter: Alice Chen
2) Architecture Review (Speaker: Bob Lee, 20 min)
Item 3: Release Plan - Owner: Carol Wu
Agenda Item 4 - Q&A
Topic 5: Security Update | Presenters: Alice Chen, Bob Lee
```

---

### Step 4：姓名清洗与匹配

**目标：** 英文姓名不被切碎，大小写/空格/连字符差异不影响匹配。

#### 4.1 `clean_presenter_names` 按语种拆分

**共享部分：**

- 剥离中文角色前缀；
- 新增英文角色前缀：`Presenter(s)`、`Speaker(s)`、`Reporter`、`Owner`、`Host`、`Facilitator`、`Presented by`、`Lead`、`Minutes Taker`、`Note Taker`；
- 剥离 5–8 位工号；
- 剥离中英文括号及内容；
- 过滤标签：`公开`、`非公开`、`汇报类`、`审议类`、`TBD`、`TBC`、`N/A`、`None`、`All`、`Presenter`、`Speaker`。

**按语种分支：**

- `zh`：保持现有 `[;；,/，\s、]+` 拆分；
- `en`：
  - 按 `;`、`,`、`/`、`|`、换行拆分；
  - 按 `\s+and\s+`、`\s+&\s+` 拆分；
  - 按两个及以上空格拆分；
  - **绝不按单个空格拆分**；
  - 保留 `Alice Chen`、`Anne-Marie Dubois`、`O'Connor` 为完整姓名。

#### 4.2 `match_presenter_name` 增加 ASCII 归一

- 英文姓名先做：`casefold()`，去掉空格、连字符、撇号、点号；
- 归一后完全相等 → `1.0`；
- 整词边界包含（例如 `Alice Chen` 出现在 `Alice Chen (PM)` 中）→ `0.95`；
- **英文不再用任意子串匹配**，避免 `Ann` 误中 `Joanne`；
- 拼音同音逻辑只对中文姓名启用。

#### 4.3 `extract_speakers_from_transcript`

- 增加英文方括号：`[Alice Chen]`；
- 英文姓名长度上限从 12 放宽到 32；
- 角色过滤增加：`Host`、`Moderator`、`Chair`、`Chairperson`、`Facilitator`、`MC`、`Organizer`、`Session Chair`；
- 传 `lang` 给 `reconcile_presenter_names` 内部的候选人提取。

#### 4.4 VLM JSON 姓名清洗

`agenda_vision.clean_person_names` 当前也按空格拆，会把英文 `Alice Chen` 拆开。

- 增加 `lang` 参数；
- 字符串型 `presenters` / `attendees` 复用同一套语种拆分规则；
- 列表型保持原样。

#### 4.5 完成标准

```text
clean_presenter_names("Presenter: Alice Chen", lang="en") -> ["Alice Chen"]
clean_presenter_names("Alice Chen and Bob Lee", lang="en") -> ["Alice Chen", "Bob Lee"]
clean_presenter_names("Alice Chen, Bob Lee", lang="en") -> ["Alice Chen", "Bob Lee"]
clean_presenter_names("Dr. Alice Chen", lang="en") -> ["Dr. Alice Chen"]
clean_presenter_names("TBD", lang="en") -> []
match_presenter_name("Alice Chen", "alice chen") >= 0.8
match_presenter_name("Anne-Marie", "Anne Marie") >= 0.8
match_presenter_name("Ann", "Joanne") == 0.0
```

---

### Step 5：Alignment 换场、开场、收尾、设备噪声

**目标：** 英文转写能识别转场，不把开场/收尾/试音误算进议题。

所有新增信号只在 `lang="en"` 时启用；`lang="zh"` 继续跑现有中文列表。

#### 5.1 主持人换场

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

姓名捕获规则：

- 只捕获 1–3 个首字母大写的连续词；
- 过滤 `The`、`Next`、`Our`、`This`、`That` 等停用词；
- 整词匹配姓名，不用任意子串。

#### 5.2 收尾信号

英文收尾要**从严**，避免 `Thank you` 这种高频词误判：

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

#### 5.3 开场信号

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

#### 5.4 设备噪声与闲聊

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

#### 5.5 完成标准

- 英文会议开场段不进入任何议题；
- `Moving on to ...` 能触发换场；
- `That's all for today` 能触发收尾；
- `Thank you for the question` 不触发收尾；
- `Can you hear me` 被隔离，不污染上一议题。

---

### Step 6：Alignment 评分、内容轨与仪式过滤

**目标：** 英文换场后，议题归属、Track B 内容轨、会务项过滤都正确。

#### 6.1 评分中的姓名匹配

`_score_block_for_item`：

- `name in content` → 改成语言感知的姓名查找：
  - `zh`：保持现有子串；
  - `en`：大小写不敏感 + 整词边界；
- `name[0] + 工/老师/总/经理/博士/专家` → 中文分支保留；
- 英文分支增加：
  - `Mr. Chen`
  - `Ms. Chen`
  - `Mrs. Chen`
  - `Dr. Chen`
  - `Prof. Chen`
- 英文 `is_presenter` 使用 Step 4 改进后的 `match_presenter_name`。

#### 6.2 枢纽人物识别

`_identify_hub_speakers`：

- `clean_presenter_names(..., lang=lang)`；
- `plan.meta.attendees` 角色前缀增加：
  - `Host`、`Moderator`、`Chair`、`Chairperson`、`Facilitator`、`Organizer`、`MC`、`Session Chair`；
- 转写发言人原生角色嗅探增加同样英文角色；
- `"现场发言人"` 的移除逻辑保留；英文 `"Speaker"` 也要从枢纽池移除。

#### 6.3 Track B 内容轨

`_build_item_signals_for_content_track`：

- 英文标题/描述继续走 `extract_distinctive_tokens`，英文 token 已有支持；
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
- 英文角色/尊称提取：
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
- `_HIGH_CONFIDENCE_SIGNALS` 增加英文对应项。
- `_find_transition_candidate` 中 `sig in content` 改为语言感知：
  - `zh`：子串；
  - `en`：大小写不敏感整词匹配。

#### 6.4 仪式/后勤项过滤

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
- 英文关键词匹配统一用 `lower()` + 整词边界，避免 `read` 命中 `already` 这类误伤。
- 字符阈值先保持不变；用英文夹具验证后，只有确有必要才调英文分支阈值。

#### 6.5 完成标准

- 英文 `has_team` 大小写不敏感；
- `Dr. Chen` 能加分；
- `Group Photo` / `Lunch Break` / `Video Playback` 被剔除；
- `Architecture Review` / `Release Plan` 被保留；
- 英文 Track B（无汇报人议程）能靠 `next / moving on` 和标题词切换。

---

### Step 7：测试

#### 7.1 Parser 单测

文件：`tests/unit/meeting/test_agenda_parser.py`

新增：

- `test_agenda_parser_english_markdown_table`
- `test_agenda_parser_english_header_variants`
- `test_agenda_parser_english_line_list`
- `test_agenda_parser_english_meta`
- `test_clean_presenter_names_english`
- `test_match_presenter_name_english`
- `test_parse_agenda_text_lang_cache_isolation`
- `test_parse_agenda_text_english_does_not_split_full_name`

#### 7.2 Alignment 单测

文件：`tests/unit/meeting/test_agenda_alignment.py`

新增：

- `test_english_session_closing_signals`
- `test_english_closing_exclusion`
- `test_english_opening_signals`
- `test_english_equipment_chitchat`
- `test_english_host_roadsign`
- `test_align_english_transcript_named_track`
- `test_align_english_transcript_content_track`
- `test_english_ceremonial_filtering`
- `test_align_agenda_with_transcript_lang_cache_isolation`

#### 7.3 Engine 单测

文件：`tests/unit/meeting/test_agenda_engine.py`

新增：

- `test_probe_valid_agendas_english`
- `test_process_agenda_for_minutes_english`
- `test_process_agenda_for_minutes_english_cache_key`
- `test_english_ceremonial_and_skipped_filtering`

#### 7.4 Vision 单测

文件：`tests/unit/meeting/test_agenda_vision.py`

- 更新 `test_agenda_vision_raw_cache` 的 key 断言为 `(md, "zh")`；
- 新增 `test_vision_json_english_presenters_not_split`；
- 新增 `test_ocr_fallback_passes_lang_to_parser`。

#### 7.5 调用链测试

文件：`tests/unit/meeting/test_minutes_agenda_integration.py`

新增：

- `test_probe_valid_agendas_passes_lang`
- `test_process_agenda_passes_lang`
- `test_agenda_minutes_agent_passes_lang`
- `test_agenda_minutes_vlm_passes_lang`（覆盖 `app/tasks.py:696`）

#### 7.6 集成测试

文件：`tests/integration/meeting/test_agenda_pipeline.py`

新增一条纯 Python 英文链路（不调 LLM）：

```text
英文 agenda 文本
  -> parse_agenda_text(lang="en")
  -> align_agenda_with_transcript(lang="en")
  -> process_agenda_for_minutes(lang="en")
  -> 断言 has_valid_agenda=True、议题顺序、tagged_transcript 含英文议题内容
```

#### 7.7 回归

```powershell
python -m pytest tests/unit/meeting/test_agenda_parser.py tests/unit/meeting/test_agenda_alignment.py tests/unit/meeting/test_agenda_engine.py tests/unit/meeting/test_agenda_vision.py -q
python -m pytest tests/unit/meeting -q
python -m pytest tests/unit/core -q
python -m pytest tests/integration/meeting/test_agenda_pipeline.py -q
```

以改动前基线为准：

- `tests/unit/meeting`：157 passed / 9 skipped；
- `tests/unit/core`：101 passed / 4 pre-existing failures。

新增用例必须全绿，既有失败不能增加。

#### 7.8 Lint

```powershell
python -m ruff check domains/meeting/tasks/agenda_minutes/agenda_parser.py domains/meeting/tasks/agenda_minutes/alignment_engine.py domains/meeting/agenda_engine.py domains/meeting/agenda_vision.py app/tasks.py domains/meeting/orchestrator.py domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py
```

允许既有 RUF022 等历史问题，但不能新增错误。

---

### Step 8：验收标准

逐项确认：

- [ ] 英文 Markdown 表格议程能解析出议题、汇报人、时长；
- [ ] 英文行列表议程能解析出议题、汇报人；
- [ ] 英文姓名不被单空格拆碎；
- [ ] 英文姓名大小写/连字符差异能匹配；
- [ ] `probe_valid_agendas(english_transcript, english_agenda, lang="en")` 非空；
- [ ] `process_agenda_for_minutes(..., lang="en")` 返回 `has_valid_agenda=True`；
- [ ] 英文换场、开场、收尾、设备噪声识别正确；
- [ ] 英文仪式/后勤项被剔除，实质议题保留；
- [ ] 英文 Track B（无汇报人）能靠路标和标题词切换；
- [ ] `lang` 从 `app/tasks.py`、`orchestrator.py`、`agenda_minutes_agent.py` 全部贯通；
- [ ] `agenda_minutes` 图片议程 VLM 也收到 `lang=req.lang`；
- [ ] 四个缓存 key 都带 `lang`，中英不串味；
- [ ] 中文 parser/alignment 结果与改动前一致；
- [ ] 既有中文测试全绿，既有失败不增加；
- [ ] 无新增 lint 错误。

---

## 4. 明确不做

以下项目不在本次范围，避免顺手改出大 regression：

1. **19 套英文议程模板**：仍只有 `en/general_minutes.md`，其余回退普通英文模板。
2. **OCR 重构 prompt 英文化**：`agenda_extractor.reconstruct_agenda_markdown` 仍以中文表格为目标；本次只把 `lang` 传给 parser。
3. **会议类型关键词英文化**：`detect_agenda_type` 的 `spec.keywords` 仍以中文为主；英文会更多落回 `decision_approval`，不影响分块正确性。
4. **英文打标脚手架本地化**：见第 5 节待确认项。
5. **VLM 服务 `promptId` 行为确认**：上线前与服务方确认，不在代码范围。
6. **`_ocr_single_agenda_doc`**：当前无调用，不处理。

---

## 5. 待确认决策

以下 4 个点建议在开工前确认。清单已给推荐值，未确认也可按推荐值执行。

### 5.1 英文打标脚手架是否本地化？

当前 `agenda_engine.build_tagged_transcript_with_head_tail` 输出：

```text
【现场审定的有效议题清单】
【会议开场背景与主线脉络】
【议题 02：Architecture Review】（汇报人：Alice Chen）
【会末收尾与全场定调】
```

**推荐：本期保留中文脚手架。**

理由：

- 英文 prompt 的正文仍是中文指令，且显式引用这些中文标签；
- 如果只把标签改成英文，prompt 正文会引用不存在的标签；
- 要彻底英文化，必须同时改 `agenda_engine` 标签、`orchestrator` 清单标签、以及 `prompts.py` 中的标签引用，属于独立工程；
- 脚手架是内部控制标签，不是最终交付正文，英文正文仍然全英文。

如果确认要英文化，另开一份清单，不塞进本次 parser/alignment。

### 5.2 英文仪式过滤阈值是否调整？

**推荐：先保持现有字符阈值不变。**

用英文夹具验证：

- `Group Photo`、`Lunch Break`、`Video Playback` 应剔除；
- `Architecture Review`、`Release Plan` 应保留；
- 只有出现明确误杀/漏杀时，才调英文分支阈值。

### 5.3 英文行列表是否支持裸项目符号？

**推荐：不支持。**

`- Alice will present...` 这类普通说明行风险太高，容易把元数据、备注吞成议题。只支持数字序号和 `Item/Topic/Session` 标签。

### 5.4 `lang` 为空时是否自动检测语种？

**推荐：不自动检测。**

以请求 `lang` 为准，空值按 `zh`。自动检测会改变现有中文行为，且英文内容里的中文专名会造成误判。

---

## 6. 变更文件清单

| 文件 | 改动 |
|---|---|
| `domains/meeting/tasks/agenda_minutes/agenda_parser.py` | `lang` 参数、表格/行列表/元数据英文别名、姓名清洗与匹配 |
| `domains/meeting/tasks/agenda_minutes/alignment_engine.py` | `lang` 参数、英文换场/开场/收尾/设备/仪式信号、评分与内容轨英文支持 |
| `domains/meeting/agenda_engine.py` | `lang` 贯通、缓存 key、仪式过滤传参 |
| `domains/meeting/agenda_vision.py` | `lang` 贯通、VLM JSON 姓名清洗、OCR 兜底 parser 传参、raw cache key |
| `app/tasks.py` | `agenda_minutes` VLM、`probe_valid_agendas` 传 `lang` |
| `domains/meeting/orchestrator.py` | `process_agenda_for_minutes` 传 `lang` |
| `domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py` | `parse_agenda_text` / `align_agenda_with_transcript` 传 `lang` |
| `tests/unit/meeting/test_agenda_parser.py` | 英文 parser / 姓名测试 |
| `tests/unit/meeting/test_agenda_alignment.py` | 英文 alignment 测试 |
| `tests/unit/meeting/test_agenda_engine.py` | 英文 engine / 缓存测试 |
| `tests/unit/meeting/test_agenda_vision.py` | raw cache key、英文姓名、lang 传参测试 |
| `tests/unit/meeting/test_minutes_agenda_integration.py` | 调用链 lang 测试 |
| `tests/integration/meeting/test_agenda_pipeline.py` | 英文端到端纯 Python 链路 |

---

## 7. 风险与回滚

| 风险 | 处理 |
|---|---|
| 英文短语误判，改变换场 | 英文信号从严；每条信号配单测；中文列表完全不动 |
| 英文姓名被拆碎 | 英文分支禁止单空格拆分；用 `Alice Chen`、`Anne-Marie`、`O'Connor` 夹具覆盖 |
| 缓存 key 改动导致旧测试失败 | 只改四处 key，同步改 `test_agenda_vision.py`；`clear_*` 不受影响 |
| 英文表格别名误伤中文 | 结构别名共享，但 ASCII 整词匹配；中文别名逻辑不变 |
| 英文仪式阈值不合适 | 先不调阈值，用夹具验证后再定 |
| 调用点漏传 `lang` | Step 1 用 `grep` 全量核对；调用链测试兜底 |

**回滚策略：**

- 所有新增参数默认 `lang="zh"`，中文路径不受影响；
- 如英文信号引发问题，可只回滚对应英文 pattern 列表，不动骨架；
- 缓存 key 改动无法“半回滚”，但与业务逻辑解耦，风险可控。
