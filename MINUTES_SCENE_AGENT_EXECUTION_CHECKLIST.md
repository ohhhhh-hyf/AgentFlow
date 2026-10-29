zong# 会议纪要场景识别 Agent 执行清单

> 目标：`extra.template` 为空时，不再固定走 `general_minutes`，而是由一个 LangGraph 前置节点自动识别场景并回填模板；低置信度、短会、异常情况仍回退 `general_minutes`。
>
> 本清单基于以下已确认决策：
>
> - **一个 Agent**，普通纪要与议题纪要共用；
> - 普通候选 **29 个**，议题候选 **20 个**；
> - 短会阈值 **2000 字**；
> - 接受阈值 **confidence >= 0.70**；
> - 不新增接口字段；
> - Agent 基于 LangGraph，**放在现有节点最前方**；
> - 议题单线跳过 `meeting_understanding` 不影响本节点。

---

## 零、已确认决策

| 项 | 决策 |
| --- | --- |
| 触发条件 | `extra.template` 为空、`line=minutes`、`profile != user` |
| 短会阈值 | 去空白后总字符数 `< 2000` → 不跑 Agent，直接 `general_minutes` |
| 普通候选 | 29 个普通模板 |
| 议题候选 | 20 个议程模板 |
| 置信度阈值 | `>= 0.70` 采用；`< 0.70` 回退 |
| 输出 | `{"template": "英文模板 ID", "confidence": 0.0}` |
| 议题判断 | `line_extra["agenda_text"]` 存在（`probe_valid_agendas` 已通过） |
| 个人视角 | 不跑 Agent，仍走 `personal_minutes` |
| 显式模板 | 不跑 Agent，用户指定优先 |
| 接口字段 | 不新增 |
| 失败策略 | 任何异常/非法输出 → `general_minutes`，不阻塞主流程 |

### 两份文档的配合关系

| 文档 | 职责 |
| --- | --- |
| `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` | Prompt 文本、29 条场景判断准则、普通/议题候选块、置信度口径 |
| 本清单 | 前处理、LangGraph 节点、状态传递、后处理、日志、测试、灰度 |

落地时必须保持一致：

- [x] 代码里的 `SCENE_CATALOG` 与指南的场景 ID、数量、描述一致；
- [x] 代码里的普通候选 29、议题候选 20 与指南一致；
- [x] Prompt 的置信度口径与指南一致；
- [ ] 每次修改指南的场景描述，同步代码 catalog，并递增 `prompt_version`；
- [x] 测试校验 ID/数量、描述逐条一致、候选块与 System Prompt 与指南一致。

---

## 一、现有链路与插入点

### 1. 现状

```text
app.tasks._prepare
  → 解析 docs / 探测议程 / 裁决 view
  → _template_file 解析模板（空 template 默认 general_minutes）
  → prepare_run 编译模板文本，写入 PreparedRun.template_texts
  → graph:
       START → meeting_understanding → perspective_modeling → minutes_view
             → minutes_agent → minutes_supervisor → ... → render
```

议题单线且有效议程时，`meeting_understanding` 会短路；但模板在进入 graph 前已经解析好。

### 2. 目标链路

```text
app.tasks._prepare
  → 仍先按 general_minutes 兜底解析模板
  → 记录 template_auto=True/False
  → prepare_run 编译兜底模板文本
  → graph:
       START → template_classify → meeting_understanding → ...
```

`template_classify` 节点：

- 只在本次 `line_names` 包含 `minutes` 时加入图；
- 不是 minutes 的请求，保持 `START → meeting_understanding`；
- 节点内部根据 `template_auto` 决定是否真正调用 Agent；
- 选中模板后覆盖 `state["templates"]["minutes"]`；
- 后续 `meeting_understanding` / render 读到的就是新模板。

### 3. 为什么放在 graph 最前方

- 议题单线会跳过 `meeting_understanding`，但 `template_classify` 在它之前，仍会执行；
- 普通/议题共用同一个节点，只是候选集不同；
- 模板必须在 render 前确定，graph 前置节点能保证这一点；
- 不需要改 API 路由和请求字段。

---

## 二、状态与契约

### 1. 新增状态

| 状态键 | 类型 | 说明 |
| --- | --- | --- |
| `template_auto` | `bool` | 本次是否允许自动选模板 |
| `template_decision` | `dict` | 记录 mode / raw / normalized / confidence / action / reason / duration，供日志与调试 |
| `template_id` | `str` | 最终模板 ID；render 日志直接读取，避免从文本反推 |
| `template_source` | `str` | 最终模板来源：`auto` / `auto_fallback` / `explicit` / `personal_default` / `default` / `short_bypass` / `agent_error` |
| `template_mode` | `str` | `normal` / `agenda`；用于区分普通 general 与议程 general |
| `templates` | `dict[str, str]` | 既有字段；节点覆盖 `minutes` 的文本 |
| `line_extra["agenda_text"]` | `str` | 既有字段；存在即议题候选集 |

> `template_source` / `template_mode` 必须一路保留到 render 日志，保证能回答“最后到底用了哪个模板、哪个版本、为什么”。

### 初始化

- [ ] `_prepare` / `prepare_run` 先写入默认值：
  - `extra.template` 非空 → `template_source=explicit`，`template_id` 尽量归一化为模板 ID；
  - `profile=user` → `template_source=personal_default`，`template_id=personal_minutes`；
  - 自动候选 → `template_source=default`，`template_id=general_minutes`，由 `template_classify` 改写为 `auto` / `auto_fallback`；
  - 短会 → `template_source=short_bypass`；
  - Agent 异常 → `template_source=agent_error`。
- [ ] `template_mode` 初始按 `line_extra["agenda_text"]` 是否存在设置 `agenda` / `normal`；节点与 render 只读不改。
- [ ] `template_classify` 采用后同时更新 `template_id` / `template_source`；回退时 `template_source=auto_fallback`，`template_id=general_minutes`。

### 2. 不新增

- 不新增请求字段；
- 不新增响应字段；
- 不改 `MinutesReport`；
- 不改 supervisor 契约；
- 不改 `personal_minutes` 路径；
- 不改 `agenda_minutes` 独立任务线。

---

## 三、Phase 1：前处理

### 3.1 触发标记

- [ ] `app/tasks.py::_Prepared` 增加 `template_auto: bool = False`。
- [ ] `_prepare` 在模板解析前后设置：

```text
template_auto =
    line == "minutes"
    and not (extra.template or "").strip()
    and effective_profile != "user"
```

- [ ] 议题模式也允许 `template_auto=True`，不再排除 `agenda_from_docs`。
- [ ] `_prepare` 仍调用 `_template_file` 得到 `general_minutes` 兜底路径，保证 Agent 失败也有模板。
- [ ] `_runner_args` 把 `template_auto` 传给 `prepare_run` / `run`。

### 3.2 状态传递

- [ ] `core/runner/runner.py::PreparedRun` 增加 `template_auto: bool`。
- [ ] `prepare_run` 增加 `template_auto: bool = False` 参数，写入 `PreparedRun`。
- [ ] `run` / `run_streaming` 把 `template_auto` 写入 initial state。
- [ ] 不改 `templates` 的现有结构；仍先放兜底 `general_minutes` 文本。

### 3.3 短会放行

- [ ] 节点内读取 `state["transcript"]`，去首尾空白后计算字符数。
- [ ] `< 2000`：直接返回 `{}`，不调用 Agent，保留兜底 `general_minutes`。
- [ ] 议题模式下短会同样保留兜底模板；由于 `_prepare` 已按 `is_agenda_enhanced=True` 解析，兜底就是议程版 `general_minutes`。
- [ ] 不把“短会”错误地理解为“关闭议题模式”；议题模式仍按议程流程走。

### 3.4 文本裁剪

- [ ] `len >= 2000 and len <= 12000`：全文送入 Agent。
- [ ] `len > 12000`：头 6000 + 中 2000 + 尾 4000。
- [ ] 中段取自 `text[6000:-4000]`，居中取，避免与头尾重叠。
- [ ] 尽量在换行处切分，保持发言完整。
- [ ] 拼接时加清晰分隔符：

```text
【中段节选】
...
【结尾】
...
```

### 3.5 议题模式输入

- [ ] 读取 `state["line_extra"]["agenda_text"]`。
- [ ] 存在时，把现场审定的有效议题清单放在 transcript 前：

```text
【现场审定的有效议题清单】
1. 议题：...
2. 议题：...

【待检测文本】
...
```

- [ ] 议题清单只作为辅助信号，不替代 transcript。
- [ ] 候选集切换为 20 个议程模板。

### 3.6 不触发的请求

- [ ] `extra.template` 非空：节点直接返回 `{}`。
- [ ] `profile=user`：节点直接返回 `{}`。
- [ ] 非 minutes 线：图里不加入该节点。
- [ ] `agenda_minutes` 独立任务线：不加入该节点。
- [ ] 文本为空：不调用 Agent，保留兜底。

---

## 四、Phase 2：LangGraph 前置节点

### 4.1 节点注册

- [ ] 在 `domains/meeting/orchestrator.py::_build_core` 中判断：

```text
selected 包含 minutes（或 selected 为空表示全部）
  → add_node("template_classify", self._make_template_classify_node())
  → add_edge(START, "template_classify")
  → add_edge("template_classify", "meeting_understanding")
否则
  → 保持 add_edge(START, "meeting_understanding")
```

- [ ] 不改变 `core` 返回值：任务线仍从 `meeting_understanding` 之后接入。
- [ ] 确保 `minutes_trace` / `agenda_minutes` 等不含 minutes 的请求不新增节点。
- [ ] `meeting_understanding` 的议程短路逻辑完全不动。

### 4.2 节点职责

```text
async def template_classify_node(state):
    if not state.get("template_auto"): return {}
    if "minutes" not in line_names: return {}
    if len(transcript.strip()) < 2000: return {}

    mode = "agenda" if state["line_extra"].get("agenda_text") else "normal"
    candidates = agenda_ids if mode == "agenda" else normal_ids
    text = sample_transcript(state["transcript"])

    result = await classifier.run(text, agenda_text=..., candidates=candidates)
    decision = postprocess(result, candidates, mode)

    if not decision.accepted:
        return {"template_decision": decision.to_dict()}  # 保留兜底 general

    template_text = materialize_template(decision.template_id, mode, lang)
    if not template_text:
        return {"template_decision": ...fallback...}

    templates = dict(state.get("templates") or {})
    templates["minutes"] = template_text
    return {"templates": templates, "template_decision": decision.to_dict()}
```

- [ ] 节点内不抛异常；所有异常捕获后返回 `{}` 或 fallback decision。
- [ ] 节点不修改 `has_valid_agenda`、`valid_agendas`、`tagged_transcript`。
- [ ] 节点只负责选模板和写 `templates["minutes"]`。

### 4.3 模板物化

- [ ] 普通模式：`resolve_template_format(template_id, lang)`。
- [ ] 议题模式：`resolve_agenda_template_format(template_id, lang)`。
- [ ] 若返回空文本：回退 `general_minutes` 对应模式。
- [ ] 若模板类型为 `natural`，复用 `prepare_run` 的 `maybe_compile_natural_template` 逻辑（节点 async，可用 client）。
- [ ] 不重复写临时模板文件；直接把文本写入 `state["templates"]["minutes"]`。
- [ ] 物化失败不覆盖兜底模板。

### 4.4 议题单线兼容

- [ ] 确认 `template_classify` 在 `meeting_understanding` 之前执行。
- [ ] 单线议题纪要即使 `meeting_understanding` 短路，`state["templates"]["minutes"]` 已经是选中的议程模板。
- [ ] render 节点读取 `state["templates"]["minutes"]`，无需任何改动。
- [ ] 多线议题纪要同样适用；其它线不受影响。

### 4.5 日志

日志要回答三个问题：

1. Agent 原始输出了什么？
2. 后处理最终选了哪个模板、为什么？
3. Render 最后实际用的是哪个模板？

#### 节点开始

```text
[template:auto:start] mode=normal|agenda candidates=29|20
  transcript_chars=12345 agenda=0|1 prompt_version=scene-v1
```

#### Agent 原始输出

```text
[template:auto:agent] raw_template=project_progress raw_confidence=0.86
  duration=2.31s
```

- [ ] 记录模型原始 `template` 与 `confidence`；
- [ ] 非法/非 JSON 时记录截断后的原始文本：

```text
[template:auto:agent:invalid] raw=...<最多 200 字> duration=...
```

- [ ] 不记录完整 prompt、不记录 transcript、不记录 API Key。

#### 后处理决策

```text
[template:auto:decision] template=project_progress confidence=0.86
  action=use reason=none candidate_count=29 mode=normal
```

回退时：

```text
[template:auto:decision] template=general_minutes confidence=0.62
  action=fallback reason=low_confidence candidate_count=29 mode=normal
```

- [ ] `reason` 枚举：`none` / `low_confidence` / `invalid_id` / `not_in_candidates` / `general` / `short_text` / `error` / `no_agenda_variant`。
- [ ] `action` 枚举：`use` / `fallback` / `skip`。

#### 模板物化

```text
[template:auto:materialize] template_id=project_progress mode=normal
  template_chars=592 template_fingerprint=988ac157 source=auto duration=0.01s
```

- [ ] `template_chars`、`template_fingerprint` 便于确认实际加载的是哪一版模板；
- [ ] 物化失败：

```text
[template:auto:materialize] template_id=project_progress mode=normal
  action=fallback reason=empty_template source=auto_fallback
```

#### 节点结束

```text
[template:auto:done] final_template=project_progress
  template_source=auto template_mode=normal confidence=0.86 total_duration=2.33s
```

回退：

```text
[template:auto:done] final_template=general_minutes
  template_source=auto_fallback template_mode=agenda confidence=0.62
  reason=low_confidence total_duration=2.33s
```

#### 跳过 / 非自动路径

```text
[template:auto:skip] reason=explicit_template final_template=...
[template:auto:skip] reason=personal_profile final_template=personal_minutes
[template:auto:skip] reason=short_text transcript_chars=1200 final_template=general_minutes
[template:auto:skip] reason=not_minutes
```

- [ ] 显式模板、个人视角、短会、非 minutes 线都要记录 skip 原因与最终模板；
- [ ] 不记录完整 transcript；
- [ ] `template_decision` 写入 state，供 render 日志和调试使用，不进入 API 响应。

#### Render 最终模板

- [ ] 修改 `core/runtime/render.py` 的 render 日志，追加：

```text
render line=minutes template_id=project_progress template_source=auto
  template_mode=normal fill_mode=freeform gate=pass directives=0
```

- [ ] 即使没有走 Agent，也记录最终模板：

```text
render line=minutes template_id=general_minutes template_source=explicit
  template_mode=normal
render line=minutes template_id=personal_minutes template_source=personal_default
  template_mode=normal
render line=minutes template_id=general_minutes template_source=auto_fallback
  template_mode=agenda
```

- [ ] 保证从 `[template:auto:start]` 到 `render ... template_id=` 可以用同一请求串起来（有 request_id 就带上）。

---

## 五、Phase 3：Agent 与 Prompt

### 5.1 代码位置

- [ ] 新建 `domains/meeting/tasks/minutes/steps/template_classifier.py`（或同层新模块）。
- [ ] Prompt 以根目录 `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` 为准。
- [ ] 代码维护一份 `SCENE_CATALOG`（ID、中文名、描述、是否有议程版），不要运行时解析 md。
- [ ] 定义 `TEMPLATE_CLASSIFIER_PROMPT_VERSION`（如 `scene-v1`），写入开始/结束日志。
- [ ] 单测校验 `SCENE_CATALOG` 与 `resources/templates/{lang}`、`resources/agenda_templates/{lang}` 的 ID 一致。
- [ ] 单测解析 `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` 的 29 条描述，与 `SCENE_CATALOG` 逐条比对；不一致时失败，防止两份文档漂移。

### 5.2 候选集

- [ ] 普通：`resources/templates/{lang}/*.md` 的 29 个 ID。
- [ ] 议题：`resources/agenda_templates/{lang}/*.md` 的 20 个 ID。
- [ ] 议题候选必须是普通候选子集。
- [ ] `general_minutes` 两边都保留。
- [ ] 候选集按 `SCENE_CATALOG` 顺序拼接，生成 `- {id}（{中文名}）：{描述}`。

### 5.3 Prompt 组装

- [ ] 使用指南中的共用 System Prompt；`{{CANDIDATE_SCENES}}` 按模式替换。
- [ ] 普通/议题只在候选块和议题清单上不同。
- [ ] Prompt 中不写阈值 `0.70`。
- [ ] Prompt 中包含输入安全声明。

### 5.4 调用参数

- [ ] `temperature=0`。
- [ ] `max_tokens` 只需容纳一个 JSON（建议 64–128）。
- [ ] 超时 10–15 秒。
- [ ] 优先使用结构化输出；否则解析首个 JSON 对象。
- [ ] 失败/超时/非 JSON → fallback。

### 5.5 输出

- [ ] 只接受：

```json
{"template": "english_template_id", "confidence": 0.0}
```

- [ ] 不接受自然语言解释。
- [ ] 代码侧不信任模型输出，统一走 Phase 4 后处理。

---

## 六、Phase 4：后处理

### 6.1 解析

- [ ] `template` 转小写、去空白、去 `.md` 后缀。
- [ ] `confidence` 转 float；非数字 → fallback。
- [ ] 可选：用 `template_key()` 兜底中文名/英文显示名，但归一化后仍必须在当前候选集。

### 6.2 判定顺序

```text
1. JSON 解析失败 / 超时 / 异常 → fallback
2. template 非法 / confidence 非数字 → fallback
3. template 不在候选集 → fallback
4. template == general_minutes → fallback
5. confidence < 0.70 → fallback
6. 否则 → 采用
```

### 6.3 回退模板

- [ ] 普通模式：`general_minutes` 普通版。
- [ ] 议题模式：`general_minutes` 议程版。
- [ ] 回退不覆盖已存在的兜底模板；节点直接返回 `{}` 即可。
- [ ] 回退原因写入 `template_decision.reason`，并打日志。

### 6.4 边界

- [ ] 议题模式如果模型输出 9 个无议程版场景之一：候选集只有 20，正常不会出现；若 `template_key` 归一化后落在 9 个里，仍按“不在候选集”回退议程版 general_minutes。
- [ ] 模板文件缺失/解析失败：回退。
- [ ] `confidence` 正好 0.70：按 `>= 0.70` 采用。
- [ ] 模型输出 `general_minutes` 且 confidence 高：仍回退 general_minutes（与兜底一致）。

---

## 七、Phase 5：测试

### 7.1 单元测试

- [ ] 普通候选 29 个，议题候选 20 个，议题是普通子集。
- [ ] `SCENE_CATALOG` 与实际模板目录 ID 一致。
- [ ] `SCENE_CATALOG` 与 `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` 的 29 条描述逐条一致。
- [ ] Prompt 普通/议题候选块数量与内容正确。
- [ ] 短会 `< 2000` 不调用 Agent。
- [ ] 2000–12000 全文；>12000 头中尾不重叠。
- [ ] 换行切分不破坏发言。
- [ ] JSON 合法/非法/中文名/非法 ID/非数字 confidence。
- [ ] 阈值 0.70 边界：0.69 回退、0.70 采用。
- [ ] 议题模式回退议程版 general_minutes。

### 7.2 Graph 测试

- [ ] minutes 请求图中存在 `template_classify`，且位于 `meeting_understanding` 之前。
- [ ] 非 minutes 请求不包含该节点。
- [ ] `template_auto=False` 时节点 no-op，模板保持兜底。
- [ ] 短会时节点 no-op。
- [ ] 普通模式选中后 `state["templates"]["minutes"]` 被替换。
- [ ] 议题单线：`meeting_understanding` 跳过，但 render 使用选中的议程模板。
- [ ] 个人视角 / 显式 template：不触发 Agent。
- [ ] 节点异常不影响图执行，模板保持兜底。

### 7.3 集成测试

- [ ] 用 FakeLLM 返回固定分类结果，跑普通/议题两条路径。
- [ ] 校验 render prompt 中的模板文本确实是选中的模板。
- [ ] 校验 fallback 时 render 使用 general_minutes。
- [ ] 校验日志字段。

### 7.4 回归

```bash
python -m pytest tests/unit/meeting tests/meeting -q
python -m pytest tests -q
```

- [ ] 无新增失败。
- [ ] 既有明确失败能逐条说明。

### 7.5 日志测试

- [ ] 自动匹配成功时，日志包含 `[template:auto:agent]` 的 raw template / raw confidence。
- [ ] 日志包含 `[template:auto:decision]` 的 action / reason / confidence。
- [ ] 日志包含 `[template:auto:done]` 的 final_template / template_source。
- [ ] Render 日志包含 `template_id` / `template_source`。
- [ ] 回退时 `template_source=auto_fallback`，并带 reason。
- [ ] 显式模板/个人视角/短会都有 `[template:auto:skip]` 日志。
- [ ] 日志中不出现完整 transcript、完整 prompt、API Key。
- [ ] 同一条请求的 `[template:auto:start]` 与 `render ... template_id=` 能对应上。

---

## 八、Phase 6：观测、灰度与回滚

### 8.1 开关

- [ ] 增加环境变量开关（建议 `MINUTES_TEMPLATE_AUTO=on/off`，默认先 off 或灰度）。
- [ ] 关闭时完全保持旧行为：空 template → general_minutes。
- [ ] 关闭时仍记录 `[template:auto:skip] reason=disabled final_template=general_minutes`，便于确认。

### 8.2 关键指标

从日志聚合：

```text
auto_attempts                 触发自动匹配的请求数
auto_used                     采用专用模板的请求数
auto_fallback                 回退 general 的请求数
fallback_rate                 auto_fallback / auto_attempts
fallback_reason 分布          low_confidence / invalid_id / error / short_text / general
mode 分布                     normal / agenda
template_source 分布          auto / auto_fallback / explicit / personal_default / default / short_bypass / agent_error
chosen_template 分布          各模板被选中的次数
final_template 分布           render 日志里最终实际使用的模板
confidence 分桶分布           0.60–0.70 / 0.70–0.75 / 0.75–0.90 / 0.90–1.00
classifier_duration           p50 / p90 / max
materialize_failures          模板物化失败次数
```

### 8.3 日志查询示例

```bash
# 自动匹配整体
grep "\[template:auto:" logs/agentflow.log

# 回退原因
grep "\[template:auto:decision\].*action=fallback" logs/agentflow.log

# 最终模板
grep "render line=minutes .*template_id=" logs/agentflow.log

# 低置信度档
grep "\[template:auto:decision\].*confidence=0\.7" logs/agentflow.log
```

### 8.4 人工核对

- [ ] 抽样人工核对：选中模板是否真的比 `general_minutes` 更贴场景。
- [ ] 重点看 `0.70–0.75` 档：这一档是“证据略偏但接近阈值”，最容易误选。
- [ ] 重点看议题模式：20 个候选中是否出现庭审、医疗、面试等被映射到近义场景。
- [ ] 对比 `template_source=auto` 与 `template_source=auto_fallback` 的输出质量。

### 8.5 调参

- [ ] 如果 `0.70–0.75` 档误选高：先把阈值提到 `0.75`。
- [ ] 如果整体回退率过高：先优化场景描述/候选块，再考虑降阈值。
- [ ] 如果某个模板频繁被误选：检查该模板描述是否与近义场景重叠。
- [ ] 每次调整 Prompt/描述/阈值，递增 `prompt_version` 并在日志中保留，便于对比。

### 8.6 回滚

- [ ] 关闭 `MINUTES_TEMPLATE_AUTO` 即可，无需回滚代码。
- [ ] 关闭后日志仍能回答“最终用了哪个模板”，便于确认回到旧行为。

---

## 九、风险与开放决策

| 风险/决策 | 说明 | 建议 |
| --- | --- | --- |
| 议题只有 20 个候选 | 9 个场景无议程版 | 选中列表外场景时回退议程 general；观察是否频繁硬映射到近义场景 |
| 议程探测与二次校验不一致 | `_prepare` 有效、pipeline 无效 | 分类节点跟随 `agenda_text` 存在与否；这是现有边界 |
| 置信度不自校准 | 模型可能 0.9 但选错 | 阈值 0.70 起步；重点观察 0.70–0.75 档 |
| 短会阈值 2000 | 英文 2000 字符可能偏短/偏长 | 先统一按字符；后续按 lang 校准 |
| 分类延迟 | 多一次 LLM 调用 | 输入裁剪到 12k；后续可与理解并发 |
| 模板自然语言编译 | `prepare_run` 有 `maybe_compile_natural_template` | 节点物化时复用同一逻辑 |
| 模板目录变化 | 新增/改名 | `SCENE_CATALOG` 与目录一致性测试 |
| 多语种 | 英文名/描述不同 | 候选 ID 不变，描述按 lang 拼接 |

---

## 十、验收标准

- [ ] 接口请求字段不变。
- [ ] 空 template 的普通纪要会触发 `template_classify`。
- [ ] 空 template 的议题纪要也会触发，并使用 20 个议程候选。
- [ ] 短会 `< 2000` 不调用 Agent，走 general_minutes。
- [ ] Agent 输出只包含 `template` + `confidence`。
- [ ] `confidence >= 0.70` 且 ID 合法才采用。
- [ ] 低置信度 / 非法 ID / 异常 → general_minutes。
- [ ] 普通/议题分别回退普通版/议程版 general_minutes。
- [ ] 议题单线跳过 `meeting_understanding` 时，render 仍使用选中模板。
- [ ] 个人视角和显式 template 完全不受影响。
- [ ] 日志能看出 mode、candidates、chosen、confidence、action、reason。
- [ ] 日志包含 Agent 原始输出（raw template + raw confidence）。
- [ ] 日志包含后处理最终模板（final_template + template_source）。
- [ ] Render 日志包含最终实际使用的 `template_id` 与 `template_source`。
- [ ] 可以从一条请求的 `[template:auto:start]` 追到 `render ... template_id=`。
- [ ] 日志不包含完整 transcript、完整 prompt 或 API Key。
- [ ] 全量测试无新增失败。

---

## 十一、改动文件清单

| 文件 | 改动 |
| --- | --- |
| `app/tasks.py` | `_Prepared.template_auto`；`_prepare` 设置；`_runner_args` 传递 |
| `core/runner/runner.py` | `PreparedRun.template_auto`；`prepare_run` 参数；initial state |
| `core/graph/nodes.py` | `_build_graph` / `run_streaming` 传递 `template_auto` |
| `domains/meeting/orchestrator.py` | `_build_core` 插入 `template_classify`；`_make_template_classify_node`；模板物化 helper；节点日志；`template_source` 写入 state |
| `domains/meeting/tasks/minutes/steps/template_classifier.py` | 新 Agent：候选集、prompt、LLM 调用、原始输出日志、输出解析 |
| `domains/meeting/tasks/minutes/prompts.py`（或新 prompt 模块） | 分类 prompt 常量/组装；`prompt_version` |
| `core/runtime/render.py` | render 日志追加 `template_id` / `template_source` |
| `domains/meeting/tasks/minutes/contracts.py`（可选） | 分类输出模型/契约；也可用轻量 dataclass |
| 测试 | 单元、graph、集成、日志、回归 |
| `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` | 已存在；作为 prompt 与场景描述的维护源 |

---

## 十二、明确不做

- [ ] 不新增 API 请求/响应字段。
- [ ] 不按普通/议题拆成两个 Agent。
- [ ] 不修改 `meeting_understanding` 的议程短路逻辑。
- [ ] 不修改 `agenda_minutes` 独立任务线。
- [ ] 不修改个人视角 `personal_minutes` 路径。
- [ ] 不修改草稿/审核契约。
- [ ] 不把分类结果写入最终纪要正文。
- [ ] 不在运行时读取 `template.txt`。
- [ ] 不让分类失败阻塞主流程。

---

## 十三、执行顺序建议

```text
1. 状态与触发标记（template_auto / template_source）
2. 分类 Agent 模块 + prompt + 候选集 + prompt_version
3. 后处理纯函数（解析/校验/回退）
4. LangGraph 前置节点
5. 模板物化
6. 日志埋点（agent raw / decision / final / render template_id）
7. 单元测试 + 日志测试
8. Graph/集成测试
9. 灰度开关
10. 全量回归
```

每一步完成后再进入下一步，确保任一阶段失败都能单独回退到 `general_minutes`。

---

## 附录 A：Stage 0 基线记录（2026-10-29）

### A.1 测试基线

```bash
python -m pytest tests/unit/meeting tests/meeting -q
# 396 passed, 9 skipped, 2 failed

python -m pytest tests -q
# 571 passed, 9 skipped, 6 failed
```

既有失败（与本功能无关）：

```text
tests/unit/core/templates/test_column_projection.py::test_qa_name_priority
tests/unit/core/templates/test_column_pruning_refactor.py::test_prompts_overview_word_budget_and_mapping_rules
tests/unit/core/templates/test_section_pruner.py::test_home_school_feedback_groups
tests/unit/core/templates/test_section_pruner.py::test_media_briefing_evidence_and_depth
tests/unit/meeting/test_minutes_agenda_integration.py::test_minutes_prompt_matter_oriented_governance
tests/unit/meeting/test_minutes_prompt_map.py::test_minutes_prompt_no_content_examples
```

后两条是当前 prompt 简化留下的过期断言；前四条为既有模板内容断言。

### A.2 开关落地

- [x] `domains/meeting/domain_config.py` 增加：

```text
TEMPLATE_AUTO_MODES = ("off", "shadow", "on")
TEMPLATE_AUTO_SHORT_CHARS = 2000
minutes_template_auto_mode()
```

- [x] 默认 `off`；非法值/缺省一律按 `off`。
- [ ] 部署时在 `.env` 显式配置 `MINUTES_TEMPLATE_AUTO=off`（可省略，缺省等价）。
- [x] 当前没有任何业务路径读取该开关，因此关闭行为与改动前完全一致。
- [x] 新增测试 `tests/unit/meeting/test_minutes_template_auto_switch.py`，4 条全过。

### A.3 general_minutes 基线

本地未配置 `DEEPSEEK_API_KEY`，无法在当前代码上跑真实 LLM 基线。先从历史 server 日志（commit `5c3a08eb`）提取 `general_minutes` 请求作为参考：

```text
样本数：10
平均总耗时：53.78s
平均 total_tokens：26013.9
平均 render 耗时：13.84s
平均 result.md 字符数：1558
```

> 注意：这是历史代码版本的基线，不是当前 HEAD 的真实基线；配置 key 后需用当前代码重跑并更新本节。

### A.4 Stage 0 Gate

- [x] 开关默认 `off`，未接入主流程；
- [x] 改动仅新增配置函数与测试；
- [x] 测试结果与基线一致，无新增失败；
- [ ] 当前代码的 general_minutes 真实耗时/token 基线（阻塞：本地无 LLM key）。

---

## 附录 B：Stage 2 落地记录（2026-10-29）

### B.1 纯函数模块

`domains/meeting/tasks/minutes/steps/template_classifier.py`

```text
should_skip_by_length()
sample_transcript()
parse_classifier_output()
normalize_template_id()
postprocess()
TemplateDecision
```

- [x] 短会阈值复用 `TEMPLATE_AUTO_SHORT_CHARS = 2000`；
- [x] 2000–12000 全文；>12000 头 6k + 中 2k + 尾 4k；
- [x] 三段来自原文不重叠切片，尽量在换行处切分；
- [x] 解析支持 dict、JSON、```json 围栏、前后少量说明文字；
- [x] 拒绝非法 JSON、缺失字段、bool/字符串 confidence、越界 confidence；
- [x] 模板 ID 归一化：去空白、转小写、去 `.md`、候选集校验；
- [x] 后处理阈值 0.70，低于阈值/非法/未知/`general_minutes` 均回退；
- [x] 议题模式回退结果保留 `mode="agenda"`，模板 ID 仍为 `general_minutes`。

### B.2 测试

```text
tests/unit/meeting/test_minutes_template_classifier_core.py
14 passed
```

覆盖：

- 1999 / 2000 边界；
- 长文本头中尾采样、无换行场景；
- 合法 JSON、围栏 JSON、带噪 JSON；
- 非法 JSON、缺失字段、错误类型、越界 confidence；
- 模板 ID 归一化、中文名/未知 ID；
- 0.69 回退、0.70 采用；
- `general_minutes` 回退；
- 议程模式回退保留 mode。

### B.3 Gate

- [x] 纯函数测试全绿；
- [x] 不依赖 graph、不依赖 LLM；
- [x] 全量测试无新增失败（仍为既有 6 条）；
- [x] 未接入主流程，开关仍默认 `off`。

> 说明：`normalize_template_id` 当前只接受英文模板 ID；中文名/英文显示名的 `template_key()` 兜底留到 Stage 5 物化模板时处理（Stage 4 只透传原值）。

---

## 附录 C：Stage 1 落地记录（2026-10-29）

### C.1 纯数据模块

`domains/meeting/tasks/minutes/steps/scene_catalog.py`

```text
SCENE_CATALOG             29 条：ID / 中文名 / 大类 / 描述 / 是否有议程版
NORMAL_CANDIDATE_IDS      29 条
AGENDA_CANDIDATE_IDS      20 条（普通子集）
TEMPLATE_CLASSIFIER_PROMPT_VERSION = "scene-v1"
build_candidate_block()
build_system_prompt()
build_user_message()
candidate_ids_for_mode()
```

### C.2 同步校验

`tests/unit/meeting/test_minutes_scene_catalog.py`：9 passed

- 29 / 20 数量、ID 唯一、议题是普通子集；
- catalog 与指南第二节 29 条描述逐条一致；
- 普通 / 议题候选块与指南第五节 / 第六节逐字一致；
- System Prompt 与指南第四节逐字一致；
- 候选块只注入当前候选集；
- User Message 普通/议题格式正确；
- 未知 ID 抛出 ValueError；
- `prompt_version == scene-v1`。

### C.3 Gate

- [x] 纯数据、纯函数测试全绿；
- [x] 不 import graph、不调 LLM、不影响运行时；
- [x] 全量测试无新增失败（仍为既有 6 条）；
- [x] 开关仍默认 `off`；
- [x] 指南与代码 catalog / 候选块 / System Prompt 已有自动化同步校验。

---

## 附录 D：Stage 3 落地记录（2026-10-29）

### D.1 隔离 Agent

`domains/meeting/tasks/minutes/steps/template_classifier.py`

```text
ClassifierRunResult
TemplateClassifierAgent(client, timeout=15.0, max_tokens=128)
TemplateClassifierAgent.run(transcript, agenda_text, candidates, lang="zh")
```

行为：

- 短会 `< 2000` 直接返回 `skipped=True`，不调用 LLM；
- 长文本自动调用 Stage 2 的采样；
- Prompt 使用 Stage 1 的候选块；
- `temperature=0.0`、`json_mode=True`、`max_tokens=128`、`timeout=15s`；
- 调用标签 `minutes/template_classify`；
- 合法 JSON → `parsed={template, confidence}`；
- 非法 JSON / 调用异常 / 空候选 → `ok=False` + `error`，不抛出；
- 原始输出日志：

```text
[template:auto:agent] raw_template=... raw_confidence=... candidates=...
  prompt_version=scene-v1 duration=...
```

非法输出：

```text
[template:auto:agent:invalid] raw=...<最多 200 字> duration=...
```

### D.2 测试

`tests/unit/meeting/test_minutes_template_classifier_agent.py`：8 passed

- 合法 JSON + 调用参数（temperature/json_mode/max_tokens/timeout/label）；
- 短会不调用；
- 非法 JSON；
- 超时异常；
- 议题候选 20 + 议程清单输入；
- 长文本采样标记；
- 空候选；
- raw / invalid 日志。

### D.3 Gate

- [x] FakeLLM 下行为稳定；
- [x] 不修改任何现有节点；
- [x] 不接入 graph、不接运行时；
- [x] 全量测试无新增失败（仍为既有 6 条）；
- [x] 开关仍默认 `off`。

> 说明：`lang` 参数已保留，但当前 Prompt/场景描述仍是中文版本；英文 catalog 留到多语种阶段。

## 附录 E：Stage 4 落地记录（2026-10-29）

### E.1 状态组装（API 层）

`app/tasks.py`

`_Prepared` 新增四个字段：

```text
template_auto: bool = False
template_source: str = ""
template_id: str = ""
template_mode: str = "normal"
```

`_prepare()` 只对 `minutes` 线组装：

| 条件 | template_source | template_id | template_auto |
| --- | --- | --- | --- |
| `extra.template` 非空 | `explicit` | 去除 `.md` 后的原值 | `False` |
| 模板为空 + `profile="user"` | `personal_default` | `personal_minutes` | `False` |
| 模板为空 + 客观/职业模板 | `default` | `general_minutes` | `MINUTES_TEMPLATE_AUTO != "off"` |

`template_mode` 与本场是否检测到有效议程绑定：

- 有有效议程 → `agenda`（候选 20）；
- 无有效议程 → `normal`（候选 29）。

`_runner_args()` 同步透传四个字段，保证同步 `run()` 与流式接口共用同一份实参。

### E.2 Runner 与 Graph 透传

`core/runner/runner.py`

- `PreparedRun` 新增四个字段；
- `prepare_run()` / `run()` 新增四个关键字参数；
- `run()` 调用 `run_streaming` 前按签名能力注入（支持显式参数或 `**kwargs`），避免旧桩系统报错。

`app/tasks.py::iter_task_events()`

- 与 `run()` 使用同一套签名探测逻辑注入四个字段。

`core/graph/nodes.py::run_streaming()`

- 新增四个关键字参数并写入 `initial_state`：

```text
template_auto / template_source / template_id / template_mode
```

`domains/meeting/models.py::MeetingState`

- 显式声明四个 key。LangGraph 只传 TypedDict 声明过的字段，未声明会被静默丢弃。

### E.3 行为边界

- 开关默认仍为 `off`；`template_auto` 只在“模板为空 + 客观路径 + 开关非 off”时为 `True`；
- 显式模板、个人模板不进入自动匹配；
- 没有任何节点读取这四个字段（Stage 5 才消费）；
- 模板物化、`general_minutes` 兜底与渲染路径完全不变。

### E.4 测试

`tests/unit/meeting/test_minutes_template_state.py`：Stage 4 时 10 passed；Stage 5 追加中文显式模板归一化后 11 passed

- 开关关闭 → `default / general_minutes / normal`；
- 开关打开 → `template_auto=True`；
- 显式模板优先且不触发自动匹配（含 `.md` 去除）；
- 个人档 → `personal_default / personal_minutes`；
- 有效议程 → `template_mode="agenda"`；
- `_runner_args` 四字段齐全；
- `prepare_run()` 原样返回四字段；
- `run()` 把四字段传给 `run_streaming`；
- `run_streaming()` 把四字段写入 `initial_state`；
- `MeetingState` 声明四个 key。

### E.5 Gate

- [x] 开关默认 `off`，线上行为不变；
- [x] API → runner → graph 全链路字段可见；
- [x] 无节点消费、无模板切换；
- [x] meeting：437 passed / 2 failed（既有失败）；
- [x] 全量：612 passed / 6 failed（既有失败，无新增）；
- [x] Stage 5 可直接在 graph 最前端读取 `template_auto / template_mode / template_id`。

## 附录 F：Stage 5 落地记录（2026-10-29）

### F.1 Graph 接线

`domains/meeting/orchestrator.py`

```text
minutes（或未指定线 = 全部）:
  START → template_classify → meeting_understanding → ...

其它线（actions / agenda_minutes / minutes_trace）:
  START → meeting_understanding → ...
```

- `template_classify` 只在选中 `minutes` 时注册；
- core 返回值不变，任务线仍从 `meeting_understanding` 之后接入；
- 议题单线短路 `meeting_understanding` 时，模板已经写入 state。

### F.2 节点逻辑

`domains/meeting/tasks/minutes/steps/template_select.py`

```text
select_minutes_template(state, client=...)
```

判定顺序：

1. `template_auto=False` → no-op，日志 `reason=explicit_template / personal_profile / switch_off`；
2. `MINUTES_TEMPLATE_AUTO=off`（防御）→ no-op；
3. 去空白后 `< 2000` 字 → `short_text`，不调用 Agent；
4. 模式 `agenda` 用 20 候选，`normal` 用 29 候选；
5. 调用 `TemplateClassifierAgent`；
6. `postprocess` 阈值判定；
7. `on` + accepted → 物化并写 `templates["minutes"]`；
8. `shadow` → 只写 decision，不覆盖模板；
9. 任何失败 → 保留兜底 `general_minutes`，`template_source=auto_fallback`。

状态写入：

```text
templates["minutes"]    最终模板文本（仅 on + accepted）
template_id             最终英文模板 ID
template_source         auto / auto_fallback / 原值
template_mode           normal / agenda
template_decision       完整决策（仅调试，不进入 API 响应）
```

### F.3 模板物化

- 普通模式：`app.config.resolve_template_format()`；
- 议题模式：`app.config.resolve_agenda_template_format()`；
- natural 模板：`maybe_compile_natural_template(domain="meeting", line_name="minutes", schema_hint=...)`；
- 不写临时文件，直接写 state；
- 物化失败不覆盖兜底模板。

显式模板的 `template_id` 同时做了归一化：中文显示名 / `.md` → 注册表英文 ID
（如 `项目进度会` → `project_progress`），供 render 日志使用。

### F.4 日志

```text
[template:auto:start] mode=normal candidates=29 transcript_chars=... agenda=0 prompt_version=scene-v1 switch=on
[template:auto:agent] raw_template=... raw_confidence=... candidates=29 prompt_version=scene-v1 duration=...
[template:auto:decision] template=... confidence=... action=use|fallback reason=... candidate_count=29 mode=normal
[template:auto:materialize] template_id=... mode=... template_chars=592 template_fingerprint=988ac157 source=auto duration=...
[template:auto:done] final_template=... template_source=... template_mode=... confidence=... total_duration=...
[template:auto:skip] reason=explicit_template|personal_profile|switch_off|short_text final_template=...
```

`core/runtime/render.py` 的 render 日志追加：

```text
render line=minutes template_id=project_progress template_source=auto
  template_mode=normal fill_mode=freeform gate=pass directives=0
```

非 minutes 线保持原日志格式。

### F.5 测试

`tests/unit/meeting/test_minutes_template_classify_node.py`：15 passed

- `template_classify` 位于 `meeting_understanding` 之前；
- `actions` / `agenda_minutes` / `minutes_trace` 不注册该节点；
- 显式模板、个人档、开关关闭 → no-op；
- 短会不调用 Agent；
- `on` 应用模板并记录 start / decision / materialize / done；
- `shadow` 只分类、不覆盖；
- 低置信度 / 非法输出 / 物化失败 → `general_minutes` + `auto_fallback`；
- 议题 20 候选 + 议程模板物化；
- 议题单线短路理解后，`line_template(state, "minutes")` 仍是选中模板。

`tests/unit/meeting/test_minutes_template_state.py` 增加中文显式模板归一化用例：11 passed。

### F.6 Gate

- [x] `shadow` 下只分类、不覆盖模板；
- [x] `off` / 显式模板 / 个人档行为不变；
- [x] 议题单线短路不影响静默选中的模板；
- [x] render 日志可回答“最终用了哪个模板、来自哪里”；
- [x] meeting：452 passed / 2 failed（既有失败）；
- [x] 全量：628 passed / 6 failed（既有失败，无新增）。

## 附录 G：Stage 6 边界与集成记录（2026-10-29）

本阶段只补测试，不改生产代码。

### G.1 边界测试

`tests/unit/meeting/test_minutes_template_boundaries.py`：8 passed

| 场景 | 断言 |
| --- | --- |
| 候选集划分 | 普通 29、议题 20、无议程版 9，三者关系正确 |
| 9 个无议程版场景被 Agent 输出 | 议题模式按 `not_in_candidates` 回退，保留议程版 `general_minutes` |
| `agenda_text` 存在但 pipeline 二次校验失败 | `has_valid_agenda=False`，但已选议程模板不被清除（现有边界） |
| 模板文件缺失 | `resolve_template_*` 返回空 → `empty_template` → `auto_fallback` |
| Agent 超时 | 不抛出，回退 `general_minutes` + `auto_fallback` |
| `profile=role_template` | 仍进入自动匹配（`template_auto=True`） |
| `profile=user` | 不进入自动匹配，固定 `personal_minutes` |
| 换行切分 | 头段在换行处截断，不产生半句 |

### G.2 FakeLLM 集成

`tests/unit/meeting/test_minutes_template_integration.py`：3 passed

- 普通链路：编译后的 LangGraph 跑完 `template_classify → meeting_understanding → minutes_agent`，最终 `template_id=project_progress`、`template_source=auto`；
- 议题链路：长议程转写跑完整图，最终 `template_id=team_meeting`、`has_valid_agenda=True`；
- 回退链路：低置信度 → `general_minutes` + `auto_fallback`；
- 三种链路都把最终 state 交给真实 `produce_line`，用桩 render 捕获 `render.run(context, template)` 的模板文本，断言其与 state 中选中模板完全一致；
- 日志可在同一 `caplog` 中串起：
  `[template:auto:start]` → `[template:auto:agent]` → `[template:auto:decision]` → `[template:auto:done]` → `render line=minutes template_id=...`；
- 日志不包含完整 transcript、完整 Prompt。

### G.3 Gate

- [x] 9 个无议程版场景在议题模式全部回退议程 `general_minutes`；
- [x] 二次校验失败不破坏已选模板；
- [x] 物化失败 / 文件缺失 / 超时 / 非法 JSON 均不阻塞主流程；
- [x] 普通、议题、回退三条 FakeLLM 链路均通过；
- [x] render 实际收到的模板与 state 选中模板一致；
- [x] 日志能回答“用了什么模板、为什么”；
- [x] 全量：639 passed / 6 failed（既有失败，无新增）。
