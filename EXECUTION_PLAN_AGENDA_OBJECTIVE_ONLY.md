# 议题纪要：个人视角关闭 + 记忆适配执行清单（v1.2）

> 版本：v1.2（2026-10-26）  
> 范围：**仅 `meeting` 域下 `minutes` 的议题增强分支（`agenda_enhanced`）**  
> 明确不在范围：
> - 独立任务线 `agenda_minutes`（现有行为不动）
> - `minutes_styles` / `minutes_trace` 的既有逻辑
> - **1.3C 记忆 mode 修正**（它是普通个人纪要的共享 bug，另开专项）
> 状态：执行清单；**Step 1 + Step 2 已落地（2026-10-26）**，Step 3–6 待做

## 实施状态（2026-10-26）

- [x] Step 1：`resolve_profile_mode` / `resolve_minutes_view` / `[minutes:view]` 日志
- [x] Step 2A：`personal × agenda` 400；`role_template × agenda` effective profile=objective
- [x] Step 2B：agenda_objective 上下文/模板/后处理/视角建模/标题去个人/角色化
- [x] Step 2C：显式 `source_transcript`；议程分支跳过 `purge_stale_memory_from_decisions`
- [x] Step 2D：README / api_test 能力边界说明
- [ ] Step 3：prompt map + 议程专用输出契约（未做）
- [ ] Step 4：议程注入事实（未做）
- [ ] Step 5：议程持久化事实（未做）
- [ ] Step 6：exact purge / 1.3C / 未来 agenda_personal（未做）
- 已知既有失败（与本步无关）：`tests/unit/meeting/test_minutes_agenda_integration.py` 2 处模板措辞断言、`tests/unit/core/templates` 4 处模板断言

---

## 0. 一页结论

### 0.1 两条工作流

| 工作流 | 目标 | 是否影响普通纪要 |
|---|---|---|
| **A. 个人视角关闭** | personal × agenda → 400；role_template × agenda → 强制 objective；agenda 路径去个人/角色上下文 | 否（普通 personal / objective / role_template 不变） |
| **B. 议题纪要记忆适配** | 1.3A 注入事实、7.5 迁移止血、1.3B 持久化事实 | 否（必须用议程专用分支；普通 minutes / minutes_styles 不变） |

### 0.2 已确认决策

1. **`personal × agenda` → reject(400)**，v1 不提供自动降级。
2. **强制客观时不保留姓名**：`role_template × agenda` 按 objective 运行，标题回退「客观会议纪要」。
3. **`role_template × agenda` → 统一 objective**：剥离角色画像、视角模型、命中/雷达。
4. **`agenda_minutes` 独立线不动**。
5. **1.3C 不在本清单**：它是普通个人纪要的共享记忆 bug；议题纪要 v1.1 后已是 objective，不需要 1.3C。
6. **议题纪要保留记忆功能**：不关 memory；把事实源从「会议理解」改成「tagged transcript + 已批准议程草稿」。

### 0.3 零影响普通纪要的硬约束

所有 B 类改动必须满足：

- [ ] 只在 `line_name == "minutes"` + `has_valid_agenda` / `is_agenda_mode` / `minutes_view == "agenda_objective"` 时生效
- [ ] 不改变共享函数的默认参数与默认行为
- [ ] 新增可选参数必须有默认值，默认走旧逻辑
- [ ] `minutes_styles` 不得因为 `has_valid_agenda` 被误伤
- [ ] 普通分钟（objective / personal / role_template）与 `minutes_styles` 全部回归通过
- [ ] 议程分支的日志与普通分支可区分

### 0.4 不要做什么

- ❌ 不要删 `MINUTES_PERSONAL_*`
- ❌ 不要删 `personal_minutes.md`
- ❌ 不要删 `personally_relevant_points`
- ❌ 不要删 `KEYPOINTS / NOTES / VISION` blocks
- ❌ 不要删 `normalize_personal_sections`（加门禁即可）
- ❌ 不要改 `agenda_minutes` 独立线
- ❌ 不要在本清单里修 1.3C
- ❌ 不要直接改共享函数的默认行为来“顺手修议程”

---

## 1. 现状与证据

### 1.1 个人视角现状（Part A）

| 层 | 现状（agenda + personal） | 是否含个人内容 |
|---|---|---|
| `MINUTES_AGENDA_*` prompt 文本 | objective 规则 | 否 |
| `structured()` 追加的输出契约 | 4 处「个人模式下」+ 3 处「来自 MeetingUnderstanding」 | **是（隐藏泄漏）** |
| Agent user 上下文 | 视角模式、画像、偏好、命中、雷达、视角模型 | **是** |
| Supervisor user 上下文 | source pack 无条件加画像/视角模型 + 命中/雷达 | **是** |
| Render user 上下文 | 画像、视角模型、命中/雷达/偏好 | **是** |
| 模板 | `profile=user` → `personal_minutes` 回退 | **是** |
| 渲染后处理 | `normalize_personal_sections` | **是，可能破坏议程排版** |
| 视角建模 | `minutes` 不在 `skip_perspective` | **是，可能多一次 LLM** |
| 硬执行 | agenda 分支不使用 mode/perspective | 否 |

证据：

- `minutes_agent.py:84-95`、`minutes_supervisor.py:34-45`、`minutes_render.py:174-182`
- `infra/llm/llmclient.py:849-865` 追加 `MINUTES_GENERATION_OUTPUT_CONTRACT`
- `orchestrator.py:727-758`、`814-822`、`867-909`
- `core/graph/nodes.py:263-273`
- `orchestrator.py:1122-1146`、`1150-1173`、`1177-1230`
- `app/tasks.py:524-538`、`app/config.py:413-441`

### 1.2 记忆现状（Part B）

议题纪要目前**有完整记忆管线**，但套用的是普通纪要的假设：

| 步骤 | 入口 | 议题纪要下实际状态 |
|---|---|---|
| 1. 开关与 meta | `prepare_run` → `prepare_memory` | 正常 |
| 2. 注入准备 | `build_line_extra` → `build_memory_context` | 记忆块有；`current_fact` 空 → 排序退化 |
| 3. Agent 上下文 | `_make_agent_node` | 记忆块追加到 agenda agent user message 末尾 |
| 4. history_comparison | `_make_agent_node` | 正常写入草稿 |
| 5. 硬执行 purge | `enforce_minutes_draft` | **7.5：transcript 被 `════════` 截断 + 模糊匹配 → 误迁** |
| 6. Supervisor | `_supervisor_context` | 能看到 memory_context；但 key_decisions 被 drop |
| 7. 渲染后引用 | `_apply_memory_citations` | 正常追加 `## 历史对照` / `## 历史记忆引用` |
| 8. 持久化 | `persist_after_run` | **understanding 空 → 决策/风险/待办/议题不写入** |

证据：

- `core/runner/runner.py:259`、`284-300`、`478-496`
- `domains/meeting/hooks.py:25`、`30-46`
- `domains/meeting/memory/runtime.py:350-417`、`454-528`
- `domains/meeting/memory/inject.py:364-480`
- `domains/meeting/memory/extract.py:434-491`
- `core/graph/nodes.py:567-586`、`620-624`
- `minutes_agent.py:23-70`、`128-148`
- `core/execution/hard_execution.py:430-525`
- `core/runtime/render.py:223-261`、`643-645`、`742-744`
- `domains/meeting/memory/render.py:667-786`
- `orchestrator.py:804-806`

### 1.3 记忆的四条失效假设

| # | 普通纪要的假设 | 议题纪要的现实 | 后果 |
|---|---|---|---|
| 1 | `meeting_understanding` 提供当前事实 | 理解被跳过，是空的 | 注入排序退化；comparison 缺本场新增决策 |
| 2 | 决策是原文逐字搬运 | 决策是模型从 tagged transcript 提炼 | purge 把大量决策判成“原文没有” |
| 3 | `persist_after_run` 用 understanding 建事实 | understanding 为空 | 本场决策/风险/待办/议题不写入记忆 |
| 4 | `build_line_extra` 从 `line_modes` 取 mode | minutes 的 line_modes 通常为空 | 普通个人纪要也受影响；**本清单不修（1.3C 另开）** |

### 1.4 目标与非目标

**目标**

- Part A：personal × agenda 明确 400；role_template × agenda 强制 objective；agenda_objective 全链路无个人/角色内容。
- Part B：议题纪要保留记忆；注入事实更准、迁移不误删、持久化有内容。
- 普通 minutes / minutes_styles / role_template 不变。

**非目标**

- 不实现 `agenda_personal`（未来）。
- 不修 1.3C。
- 不修 7.1/7.2/7.3（审核看不到决策/议程清单/骨架未硬锁）。
- 不动 `agenda_minutes`。

---

# Part A：个人视角关闭

## 2. 能力矩阵与策略

| 视角 | 普通纪要 | 议题纪要 |
|---|---|---|
| `objective`（空 / objective / object） | 支持 | 支持 |
| `personal`（`profile=user`） | 支持 | **reject(400)** |
| `role_template`（developer 等） | 支持 | **agenda_objective（effective profile = objective）** |

v1 策略固定：

```text
AGENDA_PERSONAL_POLICY = reject
AGENDA_ROLE_POLICY     = objective
```

不提供 `objective`/`fallback` 自动降级。

### 2.1 行为定义

| 组合 | v1 行为 | effective profile | 提示 |
|---|---|---|---|
| `personal + agenda` | 400 | — | 400 文案 |
| `role_template + agenda` | `agenda_objective` | **objective**（不保留姓名/角色） | 日志 `forced_objective_role` |
| `objective + agenda` | `agenda_objective` | objective | 无 |
| `personal` 无议程 | `personal` | personal | 无 |
| `role_template` 无议程 | `role_template` | role_template | 无 |
| `objective` 无议程 | `objective` | objective | 无 |

400 文案：

```text
个人视角暂不支持议题增强模式：
- 如需议题纪要，请将 extra.profile 设为 objective 或留空；
- 如需个人视角，请改用普通纪要（不要上传议程 docs）。
```

## 3. 目标架构（Part A）

### 3.1 单一裁决

新增 `domains/meeting/views.py`：

```python
def resolve_profile_mode(user_data: dict) -> str:
    """objective | personal | role_template，与 run_streaming 同源。"""

def resolve_minutes_view(*, has_valid_agenda: bool, profile_mode: str) -> str:
    """
    has_valid_agenda=False        -> profile_mode
    agenda + personal             -> raise AgendaPersonalUnsupported
    agenda + objective/role_template -> "agenda_objective"
    """
```

### 3.2 数据流

```
_prepare
  → resolve_profile_mode
  → probe_valid_agendas
  → resolve_minutes_view
      ├─ agenda + personal      → ApiError(400)
      ├─ agenda + role_template → effective_profile = objective
      └─ 其他                    → 原样
  → _profile_file(effective_profile)
  → _template_file(effective_profile, is_agenda_enhanced)
prepare_run（防御性复核）
  → agenda_text + personal      → ValueError
  → agenda_text + role_template → user.perspective = objective
run_streaming
  → meeting_understanding（议程短路）
  → perspective_modeling（agenda_objective 短路）
  → minutes_agent / supervisor（prompt map）
produce_line
  → render context / template / post-hook 按 view 去个人化
```

### 3.3 View → 各层

| view | 生成 | 审核 | 渲染 | 模板 | 个人/角色上下文 | 视角建模 | 后处理 | 标题 |
|---|---|---|---|---|---|---|---|---|
| `objective` | OBJECTIVE | OBJECTIVE | OBJECTIVE / 普通模板 | general_minutes | 否 | 短路 | 否 | 客观 |
| `personal` | PERSONAL | PERSONAL | PERSONAL / 普通模板 | personal_minutes | 是 | 合成/LLM | 是 | 个人 |
| `role_template` | OBJECTIVE | OBJECTIVE | OBJECTIVE / 普通模板 | general_minutes | 画像（现状） | 合成/LLM | 否 | 客观 |
| `agenda_objective` | AGENDA | AGENDA | AGENDA / 议程模板 | agenda_templates | **否** | **短路** | **否** | 客观 |

## 4. Part A 执行清单

### A-P0 止血与可观测

- [ ] **A-P0-1 `resolve_profile_mode`**
  - 位置：`core/runner/profiles.py` 或 `domains/meeting/views.py`
  - 与 `run_streaming` 的模式判定同源
  - 测试：空 / objective / user / developer

- [ ] **A-P0-2 `resolve_minutes_view`**
  - 位置：`domains/meeting/views.py`
  - personal + agenda → raise
  - role_template + agenda → `agenda_objective`
  - 测试：6 种矩阵

- [ ] **A-P0-3 入口门禁（`app/tasks._prepare`）**
  - 位置：`app/tasks.py:688-735`
  - `probe_valid_agendas` 之后、`agenda_from_docs` 之前
  - personal → `ApiError(400)`
  - role_template → `effective_profile = "objective"`
  - `_profile_file` / `_template_file` 使用 effective profile
  - 测试：三种组合

- [ ] **A-P0-4 防御性复核（`core/runner/runner.py::prepare_run`）**
  - `line_extra["agenda_text"]` 非空 + personal → ValueError
  - `line_extra["agenda_text"]` 非空 + role_template → `user["perspective"]="objective"`
  - 测试：编程调用

- [ ] **A-P0-5 日志/指标**
  - `[minutes:view] requested=... resolved=... profile_mode=... action=...`
  - action：`rejected_personal` / `forced_objective_role` / `agenda_objective` / `normal`

- [ ] **A-P0-6 400 / 强制客观文案**
  - personal 400 文案可操作
  - role_template 记录 `forced_objective_role`（可选用户可见 warning）

- [ ] **A-P0-7 保留 personal prompts / templates**
  - 普通个人纪要回归通过

### A-P1 议程路径去个人化

- [ ] **A-P1-1 Prompt 选择收口**
  - 新增 `minutes_prompts(view)` 映射
  - 修改 `minutes_agent.py:84-95`、`minutes_supervisor.py:34-45`、`minutes_render.py:174-182`
  - `role_template` → OBJECTIVE；`agenda_objective` → AGENDA
  - 不再写分散的 `if is_agenda ... elif personal ...`

- [ ] **A-P1-2 Agent 上下文去个人/角色化**
  - `orchestrator._line_shared_context`（`orchestrator.py:670-786`）
  - `agenda_objective` 不追加：画像、偏好、命中、雷达、视角模型、空会议理解
  - 保留：客观视角模式、议题标记、fact_note、tagged transcript、预算、aux、模板、执行准绳

- [ ] **A-P1-3 Supervisor 上下文去个人/角色化**
  - `_supervisor_context`（`orchestrator.py:788-830`）
  - `_supervisor_source_pack` 增加 `include_profile=False`（`core/graph/nodes.py:188-273`）
  - `agenda_objective` 不追加 hits / radar
  - 保留 aux / memory（objective）

- [ ] **A-P1-4 Render 上下文去个人/角色化**
  - `_render_context`（`orchestrator.py:858-920`）
  - `agenda_objective` 不追加画像、视角模型、命中/雷达/偏好、空会议理解
  - 保留议题模式、议程清单、预算、草稿、审核结论

- [ ] **A-P1-5 模板选择去个人/角色化**
  - `_template_file`（`app/tasks.py:499-554`）
  - `agenda_objective` 用 effective profile objective → agenda 模板
  - 防止 `profile=user/developer` 选中 `personal_minutes` / 普通模板

- [ ] **A-P1-6 渲染后处理门禁**
  - `_post_render_hook`（`orchestrator.py:1122-1146`）
  - 仅 `view == personal` 运行 `normalize_personal_sections`
  - agenda_objective 不运行

- [ ] **A-P1-7 视角建模短路**
  - `_make_perspective_node`（`orchestrator.py:1177-1230`）
  - `agenda_objective` 直接返回空 profile / 空 hits / 空 radar
  - 必须覆盖 role_template + agenda

- [ ] **A-P1-8 标题去个人化**
  - `_compute_title` / `_line_title`（`orchestrator.py:487-510`）
  - agenda_objective 优先 headline，回退「客观会议纪要」
  - role_template 不出现角色姓名

- [ ] **A-P1-9 议程专用输出契约**
  - `domains/meeting/tasks/minutes/contracts.py`
  - 新增普通字符串常量 `MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT`
  - 不含「个人模式下」「来自 MeetingUnderstanding」
  - `minutes_agent.run` 在 `is_agenda` 时使用
  - 不要新增 `*GenerationContract` 子类（避免 codegen 生成多余模型）
  - 测试：键集合一致；`sync_domain.py --check`

### A-P2 加固

- [ ] **A-P2-1 监控/日志落地**
- [ ] **A-P2-2 可选：role_template 强制客观 warning 传播**
- [ ] **A-P2-3 可选：议程 supervisor prompt 与硬执行对齐**
- [ ] **A-P2-4 README / API 文档 / 前端提示**

### A-P3 可选

- [ ] **A-P3-1 共享契约模式中性化（长期）**
- [ ] **A-P3-2 拆分 `MINUTES_RENDER_TEMPLATE_PROMPT`**
- [ ] **A-P3-3 死代码清理（`_render_directives` / `_person_transcript`）**

---

# Part B：议题纪要记忆适配

## 5. 设计原则

### 5.1 只改议程分支，不动普通纪要

| 共享函数 | 服务对象 | Agenda 专用分支 | 普通纪要保证 |
|---|---|---|---|
| `build_line_extra` | minutes + minutes_styles | `line_name=="minutes" and has_valid_agenda` → 议程 fact | 其他走原 `extract_meeting_fact` |
| `extract_meeting_fact` | minutes + minutes_styles | 新增独立 helper，不改默认 | 默认行为不变 |
| `enforce_minutes_draft` | minutes only | 只改 `is_agenda_mode` 分支 | 非 agenda 分支不动 |
| `_extract_transcript` | minutes（普通 + 议程） | 议程用显式 `source_transcript` | 普通继续用旧提取 |
| `persist_after_run` | minutes + minutes_styles | `reports["minutes"] + understanding 空 + agenda draft` | 其他走原 understanding 路径 |
| `run_streaming` done 事件 | 所有线 | 新增 `drafts` / `has_valid_agenda` / `agenda_titles`（additive） | 普通消费方忽略 |

### 5.2 三个改动

| 编号 | 改动 | 目的 |
|---|---|---|
| B-1.3A | 注入事实从 `valid_agendas` 投影 | 让历史记忆排序/筛选不再退化 |
| B-7.5 | 显式 transcript + 议程保守迁移 | 停止误删本场决策 |
| B-1.3B | 持久化事实从已批准草稿投影 | 让下一场能看到本场决策/风险/待办/议题 |
| B-1.3C | **不在本清单** | 普通个人纪要共享 bug，另开专项 |

### 5.3 零影响普通纪要的硬约束

- [ ] `build_line_extra` 的议程分支必须同时满足 `line_name == "minutes"` 和 `state.get("has_valid_agenda")`
- [ ] `minutes_styles` 不得使用议程 fact；多线请求中它继续走旧事实
- [ ] `extract_meeting_fact` 默认参数/默认行为不变；议程事实用新 helper
- [ ] `enforce_minutes_draft` 只改 `is_agenda_mode` 分支；普通分支保持原逻辑
- [ ] `_extract_transcript` 不动普通路径；议程通过 `source_transcript` 显式传入
- [ ] `persist_after_run` 只在 `reports.get("minutes")` + `not understanding` + agenda 时用草稿
- [ ] `run_streaming` 新增字段是 additive；普通线忽略
- [ ] 回归测试覆盖普通 minutes（objective/personal/role_template）与 minutes_styles

## 6. B-1.3A：注入事实从 `valid_agendas` 投影

### 6.1 现状

`domains/meeting/memory/runtime.py:350-417`

```python
fact = extract_meeting_fact(
    state.get("meeting_understanding") or {},   # 议题模式为空
    transcript,
    ...
)
```

议题模式下 `fact` 的 `decisions / open_items / risks / action_items / topics` 为空；`build_memory_context` 的 `_relevance` 退化，历史记忆按最近场次排序，相关条目可能排不上。

### 6.2 目标

新增 `domains/meeting/memory/extract.py::extract_agenda_meeting_fact`：

```python
def extract_agenda_meeting_fact(
    valid_agendas,
    transcript: str,
    *,
    request_id: str = "",
    time: str = "",
) -> MeetingFact:
    base = extract_meeting_fact({}, transcript, request_id=request_id, time=time)
    titles = [a.title for a in valid_agendas if a.title]
    presenters = [p for a in valid_agendas for p in (a.presenters or [])]
    base.title = titles[0] if titles else base.title
    base.summary = "议题：" + "；".join(titles[:5]) if titles else base.summary
    base.topics = [
        {"topic_id": "", "module": "", "title": a.title,
         "decisions": [], "actions": [], "risks": [], "open_issues": []}
        for a in valid_agendas if a.title
    ]
    base.anchors = list(dict.fromkeys([*base.anchors, *titles, *presenters]))
    return base
```

`build_line_extra` 中：

```python
if line_name == "minutes" and state.get("has_valid_agenda"):
    fact = extract_agenda_meeting_fact(
        state.get("valid_agendas") or [],
        transcript,
        request_id=...,
        time=...,
    )
else:
    fact = extract_meeting_fact(state.get("meeting_understanding") or {}, transcript, ...)
```

`build_memory_context` 不改；只传不同的 `current_fact`。

### 6.3 为什么能改善

- `_relevance(item, fact)` 会用 fact 的 topics/anchors 做 n-gram 匹配
- 过去条目里含「网关鉴权」「前端渲染」的会被打高分
- `_rank` 在有正分时只保留正分条目，减少无关历史
- `preview_comparison` 的 scope labels 也会更准

### 6.4 不做什么

- 不改 `build_memory_context` 的内部逻辑
- 不改 `minutes_styles` 的 fact
- 不在注入阶段跑 LLM；纯程序投影
- 不修 1.3C（mode 仍是 objective，对 agenda_objective 是正确的）

### 6.5 测试

- [ ] `test_extract_agenda_meeting_fact_topics`：topics 标题/汇报人正确
- [ ] `test_agenda_injection_fact_used`：`build_line_extra` 在 minutes + agenda 时用议程 fact
- [ ] `test_minutes_styles_injection_unchanged`：minutes_styles 仍用旧 fact
- [ ] `test_normal_minutes_injection_unchanged`：普通 minutes 仍用 understanding fact
- [ ] 集成：过去记忆含无关近期项 + 相关旧项；议程请求的【会议记忆】优先包含相关项

## 7. B-7.5：迁移止血 + 显式 transcript

### 7.1 现状与问题

`minutes_agent._extract_transcript` 在 `会议原文：` 后找第一个 `\n\n════════` 截断；tagged transcript 的每个议题切片都用 `════════` 分隔，所以后续议题正文全部丢失。

`purge_stale_memory_from_decisions` 用“模糊/子串命中 + 原文无据”删除决策；议题决策是模型提炼的，通常不是逐字原文，所以大量决策被判“原文没有”，命中历史记忆就被迁走。

### 7.2 目标

#### B-7.5a 显式 `source_transcript`

- `MinutesGenerationAgent.run(shared_context, *, lang=None, source_transcript: str = "")`
- `DomainNodes._make_agent_node` 增加签名探测：
  ```python
  if "source_transcript" in sig.parameters or VAR_KEYWORD:
      run_kwargs["source_transcript"] = state.get("tagged_transcript") or ""
  ```
- `enforce_minutes_draft(..., transcript=source_transcript or _extract_transcript(shared_context))`
- **普通 minutes 不传 `tagged_transcript`（为空）→ 继续走旧 `_extract_transcript`，行为不变**
- 议程 minutes 传完整 tagged transcript

#### B-7.5b 议程迁移策略

在 `enforce_minutes_draft` 的 `is_agenda_mode` 分支：

- **v1 止血（推荐先做）**：**直接跳过 `purge_stale_memory_from_decisions`**
  - 保留 `history_comparison`（由 `_make_agent_node` 写入）
  - 本场决策全部保留在 `key_decisions`
  - 代价：如果模型真的逐字复读往期决策，可能留在 key_decisions；但比误删本场决策安全
- **可选加固（P3）**：新增 `purge_exact_stale_decisions`
  - 只迁移「规范化后与记忆完全相等」且「完整 tagged transcript 中不存在」的决策
  - 不能用子串/模糊匹配
  - 只用于 agenda 分支；普通分支保持原 `purge_stale_memory_from_decisions`

### 7.3 普通纪要零影响

- `source_transcript` 只在 `state["tagged_transcript"]` 存在时传入；普通 minutes 没有该字段 → 空 → 旧路径
- `purge` 只改 `is_agenda_mode` 分支；普通分支不变
- `_extract_transcript` 本身不改；普通行为不变
- 多线请求里 `minutes_styles` 不走 `enforce_minutes_draft`

### 7.4 测试

- [ ] `test_agenda_source_transcript_full`：议程 agent 拿到完整 tagged transcript
- [ ] `test_agenda_purge_skipped`：D1（改写 + 记忆子串）、D2（逐字重申在议题02）都保留
- [ ] `test_agenda_purge_skip_logs`：日志 `[memory:purge] agenda policy=skip`
- [ ] `test_normal_minutes_purge_unchanged`：普通 minutes 的行为与改造前一致
- [ ] 可选 `test_exact_purge_optional`：只有 D4（逐字往期、本场未提）被迁移
- [ ] 集成：agenda + memory；`key_decisions` 与草稿一致；`history_comparison` 不出现 D1/D2 的「往期沿革」

### 7.5 观测

```text
[memory:purge] line=minutes is_agenda=True policy=skip decisions=N
```

如果未来启用 exact 策略：

```text
[memory:purge] line=minutes is_agenda=True policy=exact decisions=N migrated=M
```

## 8. B-1.3B：持久化事实从已批准草稿投影

### 8.1 现状

`domains/meeting/memory/runtime.py:454-528`

```python
fact = extract_meeting_fact(understanding or {}, transcript, ...)
```

议题模式 understanding 为空 → `decisions / open_items / risks / action_items / topics` 全空；只保存标题 + 渲染预览。

### 8.2 目标

#### B-1.3B-a done 事件增加结构化草稿

`core/graph/nodes.py::run_streaming` 的 done 事件增加：

```python
{
    "drafts": {name: line(state, name).get("draft") for name in line_names},
    "has_valid_agenda": bool(state.get("has_valid_agenda")),
    "agenda_titles": [a.title for a in (state.get("valid_agendas") or [])],
}
```

- additive；普通消费方忽略
- 不把 dataclass 直接塞进事件，只传 title 列表

#### B-1.3B-b `extract_meeting_fact_from_minutes_draft`

新增 `domains/meeting/memory/extract.py::extract_meeting_fact_from_minutes_draft`：

| MeetingFact 字段 | 来源 |
|---|---|
| `decisions` | `draft["key_decisions"]` |
| `open_items` | `draft["unresolved_questions"]` |
| `risks` | `draft["risks_and_blockers"]` |
| `action_items` | `draft["personally_relevant_points"]` → `{"text": ...}` |
| `summary` | `draft["executive_summary"][0]` 或 `headline` |
| `topics` | `agenda_titles` 或解析 `executive_summary[1:]` 的 `### 一.` |
| `title` | `draft["headline"]` 或首个议题标题 |
| `anchors` / `project_candidates` | 复用现有 helper / transcript |
| `meeting_id` / `time` | `request_id` / `time` |

#### B-1.3B-c `persist_after_run` 门禁

```python
if (
    not understanding
    and has_valid_agenda
    and drafts.get("minutes")
    and not drafts["minutes"].get("degraded")
):
    fact = extract_meeting_fact_from_minutes_draft(
        drafts["minutes"],
        agenda_titles=agenda_titles,
        transcript=transcript,
        request_id=request_id,
        time=meeting_time,
    )
else:
    fact = extract_meeting_fact(understanding or {}, transcript, ...)
```

调用点：

- `core/runner/runner.py::run` → `hooks.persist_memory(..., drafts=event.get("drafts"), has_valid_agenda=..., agenda_titles=...)`
- `app/tasks.py::iter_task_events` → 直接调用 `persist_after_run(..., drafts=event.get("drafts"), has_valid_agenda=..., agenda_titles=...)`
- `domains/meeting/hooks.py::_persist_memory` 透传新参数

### 8.3 普通纪要零影响

- 普通 minutes：`understanding` 非空 → 旧路径
- `minutes_styles`：`reports.get("minutes")` / `drafts["minutes"]` 不满足 → 旧路径
- 非议程但 understanding 为空：`has_valid_agenda=False` → 旧路径
- 草稿 degraded：不用草稿投影，回退旧路径并记录 warning
- `run_streaming` 新字段 additive

### 8.4 测试

- [ ] `test_extract_fact_from_minutes_draft`：字段映射正确
- [ ] `test_persist_agenda_uses_draft`：议程 + memory 写回 decisions/risks/actions/topics
- [ ] `test_persist_normal_uses_understanding`：普通 minutes 行为不变
- [ ] `test_persist_minutes_styles_unchanged`：minutes_styles 行为不变
- [ ] 集成：第一场议程纪要 + memory → 第二场 memory 块出现上一场决策/延续事项
- [ ] `test_persist_degraded_draft_falls_back`

## 9. B-1.3C：明确不在本清单

`build_line_extra` 的 mode 来自：

```python
mode = (state.get("line_modes") or {}).get(line_name) or "objective"
```

- 这是**普通个人纪要**的共享 bug
- v1.1 后议程是 objective，1.3C 对议程没有需求
- 修它会改变普通个人纪要的记忆行为（虽然是把 bug 修对）
- **本清单不修；另开普通个性纪要专项**

## 10. Part B 执行清单

### B-P0 止血（建议与 Part A 同版本或紧随）

- [ ] **B-P0-1 显式 `source_transcript`**
  - `MinutesGenerationAgent.run` 增加可选参数
  - `_make_agent_node` 签名探测传入 `state.get("tagged_transcript") or ""`
  - 普通 minutes 空 → 旧 `_extract_transcript`

- [ ] **B-P0-2 议程 purge 跳过**
  - `enforce_minutes_draft` 的 `is_agenda_mode` 分支不调用 `purge_stale_memory_from_decisions`
  - 普通分支不动
  - 记录 `[memory:purge] agenda policy=skip`

- [ ] **B-P0-3 测试**
  - D1/D2/D3 保留
  - 普通 minutes purge 回归
  - 集成：key_decisions 不再被误删

### B-P1 注入事实

- [ ] **B-P1-1 `extract_agenda_meeting_fact`**
- [ ] **B-P1-2 `build_line_extra` 议程分支**
  - 严格 `line_name == "minutes" and has_valid_agenda`
- [ ] **B-P1-3 测试**
  - 议程 fact 的 topics/anchors
  - 普通 minutes / minutes_styles 不变
  - 记忆排序改善

### B-P2 持久化事实

- [ ] **B-P2-1 done 事件增加 `drafts` / `has_valid_agenda` / `agenda_titles`**
- [ ] **B-P2-2 `extract_meeting_fact_from_minutes_draft`**
- [ ] **B-P2-3 `persist_after_run` 门禁 + 调用点透传**
  - `runner.run`
  - `app/tasks.iter_task_events`
  - `meeting/hooks._persist_memory`
- [ ] **B-P2-4 测试**
  - 草稿映射
  - 议程回写
  - 普通 minutes / minutes_styles 不变
  - 下一场记忆可见

### B-P3 可选加固

- [ ] **B-P3-1 exact-match purge**（替代 skip）
- [ ] **B-P3-2 记忆块议题标签/作用域**
- [ ] **B-P3-3 审核看到 key_decisions（关联 7.1，可选）**
- [ ] **B-P3-4 1.3C 另开专项**

---

## 11. 合并文件级改动清单

| 优先级 | 工作流 | 文件 | 函数/常量 | 改动 | 零影响门禁 |
|---|---|---|---|---|---|
| A-P0 | A | `core/runner/profiles.py` / `domains/meeting/views.py` | `resolve_profile_mode` | 新增 | — |
| A-P0 | A | `domains/meeting/views.py` | `resolve_minutes_view` | 新增 | — |
| A-P0 | A | `app/tasks.py` | `_prepare` | personal→400；role_template→effective objective | 只对 minutes agenda |
| A-P0 | A | `core/runner/runner.py` | `prepare_run` | 防御性复核 | 只对 agenda_text |
| A-P1 | A | `minutes_agent.py` | `run` | prompt map + 议程契约 | `is_agenda` 分支 |
| A-P1 | A | `minutes_supervisor.py` | `review` | prompt map | `is_agenda` 分支 |
| A-P1 | A | `minutes_render.py` | `_prompt_and_user` | prompt map | `is_agenda` 分支 |
| A-P1 | A | `orchestrator.py` | `_line_shared_context` | agenda_objective 去个人/角色块 | view 判断 |
| A-P1 | A | `orchestrator.py` | `_supervisor_context` | 去画像/视角/命中/雷达 | view 判断 |
| A-P1 | A | `orchestrator.py` | `_render_context` | 去个人/角色块 | view 判断 |
| A-P1 | A | `core/graph/nodes.py` | `_supervisor_source_pack` | `include_profile` | 默认 True |
| A-P1 | A | `orchestrator.py` | `_post_render_hook` | 仅 personal 运行 | view 判断 |
| A-P1 | A | `orchestrator.py` | `_make_perspective_node` | agenda_objective 短路 | view 判断 |
| A-P1 | A | `orchestrator.py` | `_compute_title` / `_line_title` | 客观标题 | view 判断 |
| A-P1 | A | `app/tasks.py` | `_template_file` | effective profile + agenda 模板 | agenda 判断 |
| A-P1 | A | `minutes/contracts.py` | `MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT` | 新增普通字符串 | `is_agenda` |
| B-P0 | B | `minutes_agent.py` | `run` | `source_transcript` | tagged 为空走旧路径 |
| B-P0 | B | `core/graph/nodes.py` | `_make_agent_node` | 签名探测传 `tagged_transcript` | 普通为空 |
| B-P0 | B | `hard_execution.py` | `enforce_minutes_draft` | agenda 分支 skip purge | 只改 `is_agenda` |
| B-P1 | B | `memory/extract.py` | `extract_agenda_meeting_fact` | 新增 | 不改默认 |
| B-P1 | B | `memory/runtime.py` | `build_line_extra` | agenda fact 分支 | `line_name=="minutes"` + agenda |
| B-P2 | B | `core/graph/nodes.py` | `run_streaming` done | 增加 drafts/has_valid_agenda/agenda_titles | additive |
| B-P2 | B | `memory/extract.py` | `extract_meeting_fact_from_minutes_draft` | 新增 | 不改默认 |
| B-P2 | B | `memory/runtime.py` | `persist_after_run` | 草稿投影门禁 | minutes + empty understanding + agenda |
| B-P2 | B | `core/runner/runner.py` | `run` | 透传 drafts | 普通忽略 |
| B-P2 | B | `app/tasks.py` | `iter_task_events` | 透传 drafts | 普通忽略 |
| B-P2 | B | `domains/meeting/hooks.py` | `_persist_memory` | 透传 drafts | 普通忽略 |

明确不改：

- `domains/meeting/tasks/agenda_minutes/*`
- `domains/meeting/agenda_engine.py`
- `domains/meeting/agenda_vision.py`
- `minutes_styles` 的生成/渲染逻辑
- `1.3C` 的 mode 修正

---

## 12. 合并测试矩阵

### 12.1 Part A

| 测试 | 断言 |
|---|---|
| `test_resolve_profile_mode` | 4 种 profile |
| `test_resolve_minutes_view_matrix` | 6 种组合 |
| `test_minutes_agenda_personal_reject` | 400；不跑 LLM |
| `test_minutes_agenda_role_template_objective` | 客观议程；无姓名/角色画像 |
| `test_agenda_agent_context_has_no_personal` | 无个人/角色块 |
| `test_agenda_supervisor_context_has_no_personal` | 无个人/角色块 |
| `test_agenda_render_context_has_no_personal` | 无个人/角色块 |
| `test_agenda_template_is_objective` | 议程模板 |
| `test_post_render_hook_skips_agenda` | 不被个人规范化改写 |
| `test_perspective_skipped_for_agenda_objective` | 0 次 LLM |
| `test_agenda_contract_clean` | 无个人/上游说明 |
| `test_agenda_title_objective` | 客观标题 |

### 12.2 Part B

| 测试 | 断言 |
|---|---|
| `test_extract_agenda_meeting_fact_topics` | topics/anchors 正确 |
| `test_agenda_injection_fact_used` | minutes + agenda 用议程 fact |
| `test_normal_minutes_injection_unchanged` | 普通 minutes fact 不变 |
| `test_minutes_styles_injection_unchanged` | minutes_styles fact 不变 |
| `test_agenda_source_transcript_full` | 完整 tagged transcript |
| `test_agenda_purge_skipped` | D1/D2/D3 保留 |
| `test_normal_minutes_purge_unchanged` | 普通 purge 不变 |
| `test_extract_fact_from_minutes_draft` | 字段映射 |
| `test_persist_agenda_uses_draft` | 决策/风险/待办/议题写入 |
| `test_persist_normal_uses_understanding` | 普通持久化不变 |
| `test_persist_minutes_styles_unchanged` | minutes_styles 不变 |
| `test_memory_next_session_sees_agenda_facts` | 第二场可见上一场事实 |

### 12.3 回归

- [ ] 普通 minutes objective
- [ ] 普通 minutes personal
- [ ] 普通 minutes role_template
- [ ] `minutes_styles`
- [ ] `pytest tests/meeting tests/unit/meeting tests/core -q`
- [ ] `python tools/codegen/sync_domain.py --check`
- [ ] `python -m compileall domains/meeting app core`

---

## 13. 合并 DoD

### Part A

- [ ] personal × agenda 稳定 400
- [ ] role_template × agenda 稳定客观，无姓名/角色画像
- [ ] agenda_objective 无个人/角色上下文
- [ ] agenda_objective 不用个人模板
- [ ] agenda_objective 不跑个人后处理
- [ ] agenda_objective 不跑 perspective
- [ ] 议程 system prompt 无个人/上游字段说明
- [ ] 普通 minutes / minutes_styles 不变

### Part B

- [ ] 议程 + memory：本场决策不被误迁
- [ ] 议程 + memory：`key_decisions` 与草稿一致
- [ ] 议程 + memory：回写包含 decisions/risks/actions/topics
- [ ] 下一场会议记忆块能看到上一场议程事实
- [ ] 议程注入排序改善（相关历史优先）
- [ ] 普通 minutes purge/持久化不变
- [ ] `minutes_styles` 记忆不变
- [ ] 1.3C 未改动

---

## 14. 回滚方案

| 改动 | 回滚方式 | 普通纪要影响 |
|---|---|---|
| Part A personal 400 | 回滚 view/门禁 commit | 无 |
| Part A role_template 强制客观 | 回滚 effective profile/上下文门禁 | 无 |
| Part A 议程契约 | 切回 `MINUTES_GENERATION_OUTPUT_CONTRACT` | 无 |
| B-P0 source_transcript | 回滚 agent/引擎参数 | 无（普通本来就走旧路径） |
| B-P0 purge skip | 恢复 agenda 分支调用 | 无 |
| B-P1 注入 fact | 回滚 `build_line_extra` 议程分支 | 无 |
| B-P2 草稿投影 | 回滚 `persist_after_run` 门禁/透传 | 无 |

可选：增加 `AGENDA_MEMORY_MODE=legacy|agenda_aware`（默认 agenda_aware），仅议程分支读取；普通纪要永远走 legacy 路径。便于灰度/回滚。

---

## 15. 未来演进

### 15.1 个人议题（未来）

- `agenda_personal` view
- 个人议程模板
- 个人议程 prompt / supervisor / render
- 议程覆盖硬校验
- `AGENDA_PERSONAL_POLICY=allow` + 灰度

### 15.2 记忆增强（未来）

- exact-match purge（替代 skip）
- 审核看到 key_decisions（关联 7.1）
- 记忆块议题作用域标签
- 1.3C 普通个人纪要专项

---

## 16. 不要删清单

| 对象 | 原因 |
|---|---|
| `MINUTES_PERSONAL_*` | 普通个人纪要 |
| `personal_minutes.md` | 普通个人模板 |
| `personally_relevant_points` | 7 字段契约 |
| `KEYPOINTS/NOTES/VISION` | 多源辅助 |
| `PREFERENCE_LINES` / hits / radar | 普通个人基础设施 |
| `normalize_personal_sections` | 普通个人后处理；议程加门禁 |
| `MINUTES_AGENDA_*` | 议程核心 prompt |
| `agenda_templates/*` | 议程模板 |
| `purge_stale_memory_from_decisions` | 普通 minutes 仍需要 |
| `extract_meeting_fact` | 普通 minutes/minutes_styles 仍需要 |
| `build_memory_context` | 普通记忆仍需要 |
| `agenda_minutes/*` | 独立线，不在范围 |

---

## 17. 风险与待确认

| # | 风险 | 影响 | 建议 |
|---|---|---|---|
| 1 | `_prepare` 只解析 profile 路径 | 门禁拿不到真实 mode | `resolve_profile_mode` 与 `run_streaming` 同源 |
| 2 | 硬 400 可能破坏调用方 | 兼容性 | 前端禁用组合；日志观察 |
| 3 | `role_template` 姓名剥离 | 标题/记忆变化 | effective profile objective |
| 4 | 编程调用绕过入口 | 混搭复现 | `prepare_run` 防御 |
| 5 | `build_line_extra` 误伤 minutes_styles | 多线行为变化 | 严格 `line_name=="minutes"` |
| 6 | `persist_after_run` 误伤 minutes_styles | 多线持久化变化 | `reports["minutes"]` + empty understanding + agenda |
| 7 | `source_transcript` 影响普通 | 普通 purge 变化 | 只在 tagged_transcript 存在时传 |
| 8 | 契约测试已过期 | 改契约测试失败 | 先核对 `test_column_projection.py` |
| 9 | 新增 `*GenerationContract` 子类 | codegen 生成多余模型 | 用普通字符串常量 |
| 10 | 草稿 degraded 时投影 | 写入不完整事实 | 回退旧路径 + warning |
| 11 | exact purge 未做时 stale 决策保留 | 少量噪音 | 日志观察；P3 再收紧 |
| 12 | 1.3C 未修 | 普通个人记忆仍 objective | 另开专项 |

---

## 18. 推荐提交拆分

| Commit | 内容 | 依赖 |
|---|---|---|
| C1 | `resolve_profile_mode` / `resolve_minutes_view` + 单测 | 无 |
| C2 | 入口门禁 + `prepare_run` 防御 + 日志 | C1 |
| C3 | prompt map + 议程专用契约 | C1 |
| C4 | agent/supervisor/render 上下文去个人/角色化 | C1、C3 |
| C5 | 模板/后处理/标题/视角节点门禁 | C1、C4 |
| C6 | B-P0 source_transcript + 议程 purge skip | C1 |
| C7 | B-P1 注入 fact | C6 |
| C8 | B-P2 草稿持久化 | C6 |
| C9 | 文档/前端 | C2 |
| C10 | 可选：exact purge / 契约中性化 / 死代码 | 单独评审 |

---

## 19. 最终 checklist

### Part A

- [ ] `resolve_profile_mode`
- [ ] `resolve_minutes_view`
- [ ] 入口：personal→400；role_template→effective objective
- [ ] `prepare_run` 防御
- [ ] prompt map
- [ ] agent/supervisor/render 上下文去个人/角色化
- [ ] 模板选择
- [ ] 后处理门禁
- [ ] perspective 短路
- [ ] 标题
- [ ] 议程专用契约
- [ ] 普通 minutes / minutes_styles 回归

### Part B

- [ ] 显式 `source_transcript`（仅 tagged）
- [ ] 议程 purge skip
- [ ] `extract_agenda_meeting_fact`
- [ ] `build_line_extra` 议程分支（仅 minutes + agenda）
- [ ] done 事件 `drafts` / `has_valid_agenda` / `agenda_titles`
- [ ] `extract_meeting_fact_from_minutes_draft`
- [ ] `persist_after_run` 草稿投影门禁
- [ ] 普通 minutes / minutes_styles 记忆回归
- [ ] 议程 + memory 端到端：不误删、能回写、下一场可见
- [ ] 1.3C 未改动
- [ ] `agenda_minutes` 未改动
