# 英文议程 Alignment 执行清单（VLM 图片议程版）

> 状态：待执行。
>
> 前提：议程单基本都走图片 → VLM → 结构化 JSON。**不再为英文文本议程补表头、列名、行列表、元数据解析。**
>
> 目标：英文图片议程进入 VLM 后，英文转写能被正确换场、归属、过滤，最终 `has_valid_agenda=True`，不静默退回普通纪要。
>
> 不在本次范围：英文文本议程 parser、英文 OCR 兜底、19 套英文议程模板、会议类型关键词英文化、VLM `promptId` 服务侧确认。

---

## 0. 现在还需要做什么

| 优先级 | 事项 | 说明 |
|---|---|---|
| **P0** | VLM JSON 英文姓名清洗 | 当前 `clean_person_names` 按空格拆，`Alice Chen` 会变两个人 |
| **P0** | 英文 transcript alignment | 换场、开场、收尾、设备噪声、枢纽人物、内容轨、仪式过滤 |
| **P0** | `lang` 贯通到 alignment / engine | 只传给信号识别层，不传给 parser |
| **P0** | `agenda_minutes` 图片议程 VLM 传 `lang` | `app/tasks.py:696` 目前没传 |
| **P1** | 英文议程端到端测试 | VLM JSON → plan → alignment → tagged transcript |
| **P1** | 19 套英文议程模板 | 独立工作，不影响分块正确性 |
| **P2** | 英文打标脚手架是否本地化 | 待确认，默认保持中文 |
| **发布前** | VLM `promptId` 行为确认 | 与服务方确认 `prompt` 字段是否生效 |

已经完成、本次不再动的部分：

- 英文 VLM 议程图片 prompt；
- 议题纪要吃 `texts` 四字段；
- 中英生成 / 审核 / 渲染 prompt；
- 英文 `### I.` 标题本地化；
- supervisor 标题比对口径；
- 模板目录 `zh/`、`en/` 隔离（英文模板只完成 `general_minutes.md`）。

---

## 1. 图片议程链路现状

VLM 成功时：

```text
图片议程
  → AgendaVisionClient 识别
  → 结构化 JSON（theme / attendees / agenda_items）
  → vision_json_to_agenda_plan()
  → AgendaPlan
  → agenda_plan_to_markdown()
  → probe_valid_agendas()
  → parse_agenda_text()
```

关键点：

1. **VLM 已经完成“识别有效信息”**，不需要认表头；
2. `agenda_plan_to_markdown()` 输出的是**中文表头**的 Markdown；
3. `parse_agenda_text()` 在进程内会先命中 `_PARSED_AGENDA_RAW_CACHE`，直接拿回 `AgendaPlan`；
4. 只有缓存未命中时，才重新解析这段中文表头 Markdown；
5. 因此 **不需要补英文表头/列名/行列表**。

真正缺的是：

- VLM JSON 里的英文姓名被空格拆碎；
- 英文转写进入 alignment 后，所有中文信号都不命中；
- 议题全部 `skipped` → `probe_valid_agendas` 返回空 → 静默退回普通纪要。

---

## 2. 分支原则

| 层 | 策略 | 理由 |
|---|---|---|
| VLM JSON 姓名 | **共享、内容自适应** | 不按请求 `lang` 拆，按字符串内容判断中英文，避免中英混排名单出错 |
| 姓名匹配 | **共享 + ASCII 归一** | 大小写、空格、连字符归一；中文拼音/异体逻辑不动 |
| transcript 分块 | **共享** | 时间戳、`Name:`、`Speaker 1` 等与语种无关 |
| 换场、开场、收尾、设备噪声 | **按语种隔离** | 自然语言短语，中英混跑会误判 |
| 枢纽人物、评分、仪式过滤 | **按语种隔离** | 角色名和仪式词是自然语言 |
| 缓存 key | **alignment / process 加 `lang`** | 同一转写在 zh/en 下信号不同，结果可能不同 |
| parser 缓存 | **不加 `lang`** | parser 仍是语言无关的结构解析 + 姓名清洗 |
| 内部协议标记 | **不改** | `议题模式：agenda_enhanced` 是协议，不是输出 |

**语种来源：**

- HTTP：`req.lang`
- orchestrator：`state.get("lang")`
- `AgendaMinutesAgent`：`parse_lang_mode(shared_context)`
- 空值/未知：按 `zh`
- 不做自动语种检测

---

## 3. 执行步骤

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
- 英文姓名匹配大小写、连字符、撇号不敏感。

---

### Step 2：`lang` 贯通到 alignment / engine

**目标：** 把 `lang` 只传到真正需要按语种分支的对齐层，parser 保持语言无关。

#### 2.1 Alignment 签名

新增 `lang`，keyword-only，默认 `"zh"`：

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

- `parse_agenda_text`：仍是语言无关结构解析 + 姓名清洗；
- `clean_presenter_names`：内容自适应拆分；
- `match_presenter_name`：共享 ASCII 归一；
- `extract_speakers_from_transcript`：共享英文 speaker 形态；
- `reconcile_presenter_names`：共享匹配逻辑；
- `group_transcript_blocks`：共享分块逻辑；
- `_identify_hub_speakers`：共享角色前缀；
- `_score_block_for_item`：共享姓名匹配。

#### 2.2 Engine 签名

- `process_agenda_for_minutes(transcript, agenda_text, *, lang="zh")`
- `probe_valid_agendas(transcript, agenda_text, *, lang="zh")`
- `_extract_valid_agendas_from_alignment(alignment_res, *, lang="zh")`

#### 2.3 调用点

| 调用点 | 传值 |
|---|---|
| `app/tasks.py:747` `probe_valid_agendas(...)` | `lang=req.lang` |
| `app/tasks.py:696` `extract_agenda_from_image_docs(...)` | `lang=req.lang` |
| `orchestrator.py:1375` `process_agenda_for_minutes(...)` | `lang=state.get("lang") or "zh"` |
| `agenda_minutes_agent.py:747` `align_agenda_with_transcript(...)` | `lang=parse_lang_mode(shared_context)` |
| `agenda_minutes_agent.py:740` `parse_agenda_text(...)` | 不加 `lang` |
| `agenda_engine.py:176` `align_agenda_with_transcript(...)` | `lang=lang` |

> `app/tasks.py:696` 这条覆盖此前 VLM 清单里“`agenda_minutes` 调用点保持不变”的旧结论。现在 `agenda_minutes` 的图片议程也要按请求语种走英文 VLM prompt。

#### 2.4 缓存 key

| 缓存 | 处理 |
|---|---|
| `_ALIGNMENT_CACHE` | 加 `lang` |
| `_PROCESS_AGENDA_CACHE` | 加 `lang` |
| `_PARSED_AGENDA_CACHE` | **不变** |
| `_PARSED_AGENDA_RAW_CACHE` | **不变**（VLM 写入的原始 plan 与语种无关） |

#### 2.5 完成标准

- `grep` 所有 `align_agenda_with_transcript` / `process_agenda_for_minutes` / `probe_valid_agendas` 调用点，无遗漏；
- 不传 `lang` 的旧调用全部走 `zh`；
- 同一段英文转写分别用 `zh`、`en` 调用，不串缓存；
- parser 缓存 key 不变，`test_agenda_vision.py` 的 raw cache 断言不变。

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

#### 5.4 调用链

文件：`tests/unit/meeting/test_minutes_agenda_integration.py`

- `test_probe_valid_agendas_passes_lang`
- `test_process_agenda_passes_lang`
- `test_agenda_minutes_agent_passes_lang_to_alignment`
- `test_agenda_minutes_vlm_passes_lang`（覆盖 `app/tasks.py:696`）

#### 5.5 端到端

文件：`tests/integration/meeting/test_agenda_pipeline.py`

新增一条纯 Python 英文链路（不调 LLM）：

```text
英文 VLM JSON
  -> vision_json_to_agenda_plan()
  -> align_agenda_with_transcript(lang="en")
  -> process_agenda_for_minutes(lang="en")
  -> 断言 has_valid_agenda=True、议题顺序、tagged_transcript 含英文议题内容
```

#### 5.6 回归

```powershell
python -m pytest tests/unit/meeting/test_agenda_vision.py tests/unit/meeting/test_agenda_parser.py tests/unit/meeting/test_agenda_alignment.py tests/unit/meeting/test_agenda_engine.py -q
python -m pytest tests/unit/meeting -q
python -m pytest tests/unit/core -q
python -m pytest tests/integration/meeting/test_agenda_pipeline.py -q
```

基线：

- `tests/unit/meeting`：157 passed / 9 skipped；
- `tests/unit/core`：101 passed / 4 pre-existing failures。

新增用例必须全绿，既有失败不能增加。

#### 5.7 Lint

```powershell
python -m ruff check domains/meeting/tasks/agenda_minutes/agenda_parser.py domains/meeting/tasks/agenda_minutes/alignment_engine.py domains/meeting/agenda_engine.py domains/meeting/agenda_vision.py app/tasks.py domains/meeting/orchestrator.py domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py
```

允许既有 RUF022 等历史问题，但不能新增错误。

---

### Step 6：验收标准

- [ ] VLM JSON 字符串型英文姓名不被空格拆碎；
- [ ] 英文姓名匹配大小写、连字符、撇号不敏感；
- [ ] 英文 `probe_valid_agendas(..., lang="en")` 非空；
- [ ] 英文 `process_agenda_for_minutes(..., lang="en")` 返回 `has_valid_agenda=True`；
- [ ] 英文换场、开场、收尾、设备噪声识别正确；
- [ ] 英文仪式/后勤项被剔除，实质议题保留；
- [ ] 英文 Track B 能靠路标和标题词切换；
- [ ] `lang` 从 `app/tasks.py`、`orchestrator.py`、`agenda_minutes_agent.py` 贯通到 alignment；
- [ ] `agenda_minutes` 图片议程 VLM 收到 `lang=req.lang`；
- [ ] `_ALIGNMENT_CACHE`、`_PROCESS_AGENDA_CACHE` 带 `lang`，中英不串味；
- [ ] parser 缓存 key 不变，中文解析结果与改动前一致；
- [ ] 既有中文测试全绿，既有失败不增加；
- [ ] 无新增 lint 错误。

---

## 4. 明确不做

1. **英文文本议程 parser**：不补英文表头、列名、行列表、元数据；
2. **英文 OCR 兜底**：VLM 失败后的 OCR + 中文重构链路不做英文化；
3. **19 套英文议程模板**：独立工作，目前仍只有 `en/general_minutes.md`；
4. **会议类型关键词英文化**：`detect_agenda_type` 的 `spec.keywords` 仍以中文为主，英文可能落回 `decision_approval`；
5. **英文打标脚手架本地化**：默认保留中文标签，见第 5 节；
6. **VLM 服务 `promptId` 行为确认**：上线前与服务方确认，不在代码范围；
7. **`_ocr_single_agenda_doc`**：当前无调用，不处理。

---

## 5. 待确认决策

### 5.1 英文打标脚手架是否本地化？

当前 `agenda_engine.build_tagged_transcript_with_head_tail` 输出：

```text
【现场审定的有效议题清单】
【会议开场背景与主线脉络】
【议题 02：Architecture Review】（汇报人：Alice Chen）
【会末收尾与全场定调】
```

**推荐：保留中文脚手架。**

理由：

- 英文 prompt 正文仍是中文指令，且显式引用这些中文标签；
- 只改标签会让 prompt 引用不存在的标签；
- 彻底英文化要同时改 `agenda_engine`、`orchestrator`、`prompts.py`，属于独立工程；
- 脚手架是内部控制标签，最终交付正文仍是全英文。

### 5.2 英文仪式过滤阈值是否调整？

**推荐：先保持现有字符阈值不变。**

用英文夹具验证：

- `Group Photo`、`Lunch Break`、`Video Playback` 应剔除；
- `Architecture Review`、`Release Plan` 应保留；
- 只有明确误杀/漏杀时，才调英文分支阈值。

### 5.3 `lang` 为空时是否自动检测语种？

**推荐：不自动检测。**

以请求 `lang` 为准，空值按 `zh`。自动检测会改变现有中文行为。

---

## 6. 变更文件清单

| 文件 | 改动 |
|---|---|
| `domains/meeting/agenda_vision.py` | VLM JSON 英文姓名清洗、标题行误杀修复 |
| `domains/meeting/tasks/agenda_minutes/agenda_parser.py` | 姓名拆分、ASCII 匹配、英文 speaker 提取、标题守卫 |
| `domains/meeting/tasks/agenda_minutes/alignment_engine.py` | `lang` 参数、英文换场/开场/收尾/设备/仪式信号、评分与内容轨 |
| `domains/meeting/agenda_engine.py` | `lang` 贯通、`_PROCESS_AGENDA_CACHE` key、仪式过滤传参 |
| `app/tasks.py` | `agenda_minutes` VLM、`probe_valid_agendas` 传 `lang` |
| `domains/meeting/orchestrator.py` | `process_agenda_for_minutes` 传 `lang` |
| `domains/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py` | `align_agenda_with_transcript` 传 `lang` |
| `tests/unit/meeting/test_agenda_vision.py` | VLM JSON 英文姓名测试 |
| `tests/unit/meeting/test_agenda_parser.py` | 姓名清洗/匹配/英文字段测试 |
| `tests/unit/meeting/test_agenda_alignment.py` | 英文 alignment 测试 |
| `tests/unit/meeting/test_agenda_engine.py` | 英文 engine / 缓存测试 |
| `tests/unit/meeting/test_minutes_agenda_integration.py` | 调用链 `lang` 测试 |
| `tests/integration/meeting/test_agenda_pipeline.py` | 英文端到端纯 Python 链路 |

---

## 7. 风险与回滚

| 风险 | 处理 |
|---|---|
| 英文短语误判，改变换场 | 英文信号从严；每条信号配单测；中文列表完全不动 |
| 英文姓名被拆碎 | 内容自适应拆分；用 `Alice Chen`、`Anne-Marie`、`O'Connor`、中英混排夹具覆盖 |
| 英文姓名子串误匹配 | 英文取消任意子串，改用整词边界 |
| 英文仪式阈值不合适 | 先不调阈值，用夹具验证后再定 |
| 调用点漏传 `lang` | Step 2 用 `grep` 全量核对；调用链测试兜底 |
| 缓存串味 | `_ALIGNMENT_CACHE`、`_PROCESS_AGENDA_CACHE` 加 `lang`；parser 缓存不变 |

**回滚策略：**

- 所有新增参数默认 `lang="zh"`，中文路径不受影响；
- 姓名清洗是超集，中文夹具回归通过即可；
- 如英文信号引发问题，只回滚对应英文 pattern 列表，不动骨架。
