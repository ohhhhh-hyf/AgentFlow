# 测试目录重构方案（TESTS_REFACTOR_PLAN）

> 分支：`feat/test`
> 日期：2026-11-03
> 范围：`tests/` 目录的结构、配置、可靠性与可维护性
> 原则：**先修红、再搬家、再改写法、最后拆文件**；每一步都可独立回滚，搬家阶段零逻辑修改。

---

## 0. TL;DR

当前 `tests/` 不是"缺少整理"，而是**一次目录迁移没有做完**：

- 旧的 `tests/core`、`tests/meeting` 与新的 `tests/unit/...` 两套结构并存；
- 至少 5 组目录与生产包结构对不上；
- 9 个文件约 **880 处 `check()` 没有任何 assert**，pytest 永远是绿；
- 20 个测试文件超过 500 行，最大的 1899 行；
- 没有 `pyproject.toml` / `pytest.ini`，没有 marker、没有覆盖率门槛；
- 跑一次全量测试会往仓库根目录写 `data/test_user/` 和 `logs/`。

**结论：不需要推倒重写。** 按本文步骤执行，可以在不丢任何有效断言的前提下，把目录迁到镜像生产代码的标准结构，并把测试从"能跑"提升到"失败会红、隔离干净、边界清晰"。

---

## 1. 现状快照

复现命令：

```bash
python -m pytest tests -q
python -m pytest tests --collect-only -q
```

基线（2026-11-03）：

| 指标 | 数值 |
|---|---|
| Python 文件总数 | 101 |
| 测试文件数 | 86 |
| 测试函数数 | 794 |
| pytest 收集用例数（含参数化展开） | 805 |
| 代码总行数 | 27,380 |
| 全量耗时 | 20.97s |
| 结果 | **15 failed, 781 passed, 9 skipped** |

目录分布：

| 目录 | 测试函数数 | 说明 |
|---|---:|---|
| `tests/unit/meeting` | 615 | 新结构，但少了 `domains/` 层 |
| `tests/meeting` | 123 | 旧结构，未迁移 |
| `tests/core` | 41 | 旧结构，未迁移 |
| `tests/integration` | 15 | 只有 2 个文件 |
| `tests/unit/core` | 约 100 | 部分目录归属错误 |

---

## 2. 问题清单

### P0：会导致测试"假绿"或无法安全重构

#### P0-1 两套并行目录，迁移未完成

旧文件创建于 10-01 ~ 10-24，新结构从 10-09 起逐步增加，旧文件从未删除或搬走。同一个业务主题（perspective、memory、supervisor、actions）在两套目录里都有测试。

后果：

- 不知道该改哪个文件；
- 新增测试继续随机选边；
- 旧文件里的独有断言逐渐失效却没人发现。

#### P0-2 静默测试：`check()` 不抛异常

9 个文件定义了或引入了 `check(name, ok)`，它只做两件事：

```python
PASS.append(name)   # 或 FAIL.append(...)
print("PASS/FAIL ...")
```

没有任何 `assert`。pytest 收集到这些 `test_*` 函数时会执行，但失败只进全局列表，测试结果仍然是 passed。

| 文件 | 行数 | `check()` 次数 | assert |
|---|---:|---:|---|
| `tests/unit/core/templates/test_column_projection.py` | 1899 | 225 | 无 |
| `tests/core/test_perspective.py` | 1054 | 186 | 无 |
| `tests/meeting/test_meeting_memory.py` | 1358 | 178 | 无 |
| `tests/core/test_core.py` | 706 | 132 | 无 |
| `tests/unit/core/templates/test_template_gate.py` | 574 | 67 | 无 |
| `tests/core/test_supervisor_optimization.py` | 532 | 38 | 无 |
| `tests/meeting/test_agenda_coercion.py` | 335 | 29 | 无 |
| `tests/core/test_engine_smoke.py` | 312 | 14 | 无 |
| `tests/core/test_draft_scrape.py` | 108 | 11 | 无 |

另有 2 个文件同时使用 `check()` 和 assert（`test_placeholder_parser.py` 90 次、`test_section_pruner.py` 252 次），属于半静默，也要一起清理。

如果严格按"**每个测试函数都必须 assert 或调用 expect()**"检查，当前 86 个测试文件里有 **17 个**存在至少一个无断言的测试函数（上表 9 个是完全无 assert 的文件，其余是部分函数静默）。Step 5 的验收脚本用的就是这个严格口径。

> 这是整个重构里优先级最高的问题。目录再漂亮，测试不会红也没有意义。

#### P0-3 基线是红的

15 个失败必须先分诊，否则搬家后无法判断是否引入了新回归。详见附录 A。

分类：

- **Prompt 断言漂移（7 个）**：`test_template_i18n.py` 4 个、`test_minutes_view_required.py` 1 个、`test_minutes_template_integration.py` 1 个、`test_agenda_objective_boundary.py` 1 个。
- **模板数据漂移（5 个）**：`test_column_projection.py::test_qa_name_priority` 1 个、`test_column_pruning_refactor.py` 2 个、`test_section_pruner.py` 2 个。
- **场景目录与 guide 不一致（3 个）**：`test_minutes_scene_catalog.py`。

### P1：结构性问题

#### P1-1 目录与生产包不对应

生产代码是 `app/ core/ domains/ infra/`，测试应当镜像它。

| 当前测试路径 | 实际被测代码 | 问题 |
|---|---|---|
| `tests/unit/meeting/` | `domains/meeting/` | 缺少 `domains/` 层 |
| `tests/unit/core/perspective/` | `domains/shared/perspective/` | 生产代码没有 `core/perspective` |
| `tests/unit/shared/` | `domains/shared/` | 没有 `shared/` 顶级包 |
| `tests/integration/core/test_api_routes.py` | `app/api/` | 归属错误 |
| `tests/unit/core/profiles/` | `core/runner/profiles.py` | 应位于 `core/runner/` 下 |

#### P1-2 单元 / 集成 / 端到端边界模糊

- `domains.meeting.orchestrator` 被 37 个测试文件导入；
- `domains.meeting.tasks` 被 47 个测试文件导入；
- 39 个测试文件直接导入私有 `_` 函数；
- 只有 4 个文件使用 `async def test`，33 个文件用 `asyncio.run`；
- 只有 3 个文件使用 `parametrize`。

很多标在 `tests/unit` 下的文件实际需要 5~8 个生产包协同，属于集成测试。它们会让单元测试变慢、变脆，也无法定位失败层级。

#### P1-3 测试污染工作区

全量测试会生成：

```
data/test_user/output/...
logs/agenda_ocr/...
```

且 `.gitignore` 没有覆盖。测试隔离不合格。

### P2：可维护性问题

#### P2-1 巨石文件

超过 500 行的文件有 20 个，Top 12：

| 文件 | 行数 |
|---|---:|
| `tests/unit/core/templates/test_column_projection.py` | 1899 |
| `tests/unit/core/templates/test_section_pruner.py` | 1529 |
| `tests/meeting/test_meeting_memory.py` | 1358 |
| `tests/integration/meeting/test_agenda_pipeline.py` | 1139 |
| `tests/unit/meeting/test_minutes_agenda_integration.py` | 1064 |
| `tests/core/test_perspective.py` | 1054 |
| `tests/unit/meeting/test_agenda_alignment.py` | 971 |
| `tests/unit/meeting/test_template_i18n.py` | 868 |
| `tests/core/test_core.py` | 706 |
| `tests/unit/core/templates/test_placeholder_parser.py` | 646 |
| `tests/unit/meeting/test_agenda_objective_boundary.py` | 611 |
| `tests/unit/meeting/test_multi_source_minutes.py` | 580 |

#### P2-2 配置缺失

- 没有 `pyproject.toml` / `pytest.ini` / `setup.cfg`；
- `tests/conftest.py` 只做 `sys.path.insert`；
- 没有 marker 注册，无法按层级筛选；
- 没有 `--strict-markers`、`--strict-config`；
- 没有覆盖率统计与门槛；
- `tests/fixtures/sample_images/` 无人引用。

#### P2-3 命名不一致

- 面向实现细节命名：`test_minutes_view_injection.py`、`test_minutes_template_classify_node.py`；
- 同一主题命名不统一：`test_minutes_template_*` 有 9 个变体；
- 测试函数名有的写行为，有的写成 `test_xxx_1/2/3`。

---

## 3. 目标结构与规则

### 3.1 目标目录树

```
tests/
├── conftest.py                     # 全局 fixture（路径、工厂、环境隔离）
├── support/                        # 非测试辅助代码，pytest 不收集
│   ├── __init__.py
│   ├── builders.py                 # MeetingState / 草稿 / 模板构造器
│   ├── fakes.py                    # FakeLLM / FakeVLM / FakeStorage
│   └── expectations.py             # expect()：失败即 raise AssertionError
├── fixtures/                       # 真正被引用的静态数据
├── unit/
│   ├── core/
│   │   ├── templates/
│   │   ├── runner/
│   │   ├── execution/
│   │   ├── graph/
│   │   └── runtime/
│   ├── domains/
│   │   ├── meeting/
│   │   │   ├── minutes/
│   │   │   │   ├── test_prompt_rules.py
│   │   │   │   ├── test_render_prompts.py
│   │   │   │   ├── render/
│   │   │   │   ├── templates/
│   │   │   │   └── topic_major/
│   │   │   ├── agenda/
│   │   │   ├── actions/
│   │   │   ├── personal/
│   │   │   ├── supervisor/
│   │   │   ├── memory/
│   │   │   ├── consensus_decision/
│   │   │   └── minutes_trace/
│   │   ├── shared/
│   │   │   ├── perspective/
│   │   │   └── section_summary/
│   │   └── notes/
│   └── infra/
│       ├── llm/
│       ├── ocr/
│       └── vlm/
├── integration/
│   ├── api/
│   ├── core/
│   └── meeting/
└── e2e/
    └── meeting/
```

### 3.2 硬性规则

1. **镜像生产包**：`tests/unit/<pkg_path>/test_<module>.py` 对应 `<pkg_path>/<module>.py`。
2. **一个模块一个文件**；一个模块有多个关注点时按关注点拆，不在一个文件里测多个包。
3. **单元测试禁止导入 ≥ 2 个顶级包**。导入 `core` + `domains` + `infra` 的测试归 `integration/`。
4. **单个测试文件 ≤ 500 行**，超过必须拆分。
5. **测试函数必须有 assert 或调用会抛异常的 `expect()`**；禁止模块级可变 `PASS`/`FAIL` 列表。
6. **单元测试不得读写仓库内真实路径**。需要文件时用 `tmp_path`；需要配置时 monkeypatch 配置读取函数。
7. **命名**：
   - 文件：`test_<subject>_<behavior>.py`
   - 函数：`test_<behavior>_<expected>()`
   - 描述行为的断言，不写 `assert x == 1  # noqa`。
8. **不测试实现细节的地方不测私有函数**；必须测时，文件放在模块同级并加注释说明契约。

### 3.3 pytest 配置

新增根目录 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers --strict-config"
markers = [
    "integration: 跨模块、跨运行时边界的测试",
    "e2e: 端到端流程测试",
    "slow: 单文件或单用例超过 2 秒",
    "llm: 需要真实模型/网络（默认不进入 CI）",
]
filterwarnings = [
    "error::DeprecationWarning:domains.*",
]
```

约定：

- `unit/` 下的测试**不加 marker**，靠路径筛选；
- `integration/`、`e2e/` 下的测试加对应 marker；
- CI 默认 `python -m pytest -m "not llm"`；
- `--strict-markers` 保证写错 marker 直接报错。

---

## 4. 逐文件迁移映射

迁移原则：**每一批只做 `git mv` + 补 `__init__.py`，不改文件内容**。内容改造放到后续阶段。

### 4.1 第一批：结构性错位（低风险，先做）

| 现路径 | 目标路径 |
|---|---|
| `tests/unit/core/perspective/test_personal_evidence_pack.py` | `tests/unit/domains/shared/perspective/test_personal_evidence_pack.py` |
| `tests/unit/core/perspective/test_personal_perspective_agent.py` | `tests/unit/domains/shared/perspective/test_personal_perspective_agent.py` |
| `tests/unit/core/perspective/test_personal_perspective_model.py` | `tests/unit/domains/shared/perspective/test_personal_perspective_model.py` |
| `tests/unit/shared/test_section_summary.py` | `tests/unit/domains/shared/section_summary/test_section_summary.py` |
| `tests/unit/core/profiles/test_role_mapping.py` | `tests/unit/core/runner/test_role_mapping.py` |
| `tests/unit/core/profiles/test_user_profile.py` | 先移至 `tests/unit/core/runner/test_user_profile.py`；审计后把模型断言拆到 `tests/unit/domains/meeting/` |
| `tests/integration/core/test_api_routes.py` | `tests/integration/api/test_routes.py` |
| `tests/unit/core/test_structured_logging.py` | 先移至 `tests/unit/app/tasks/test_structured_logging.py`；审计如果测的是 `core` 再回调 |

> `tests/unit/core/profiles` 目录迁移完成后删除。

### 4.2 第二批：`tests/unit/meeting/` → `tests/unit/domains/meeting/`

先整体平移目录，再按下面的子目录归位。文件名同步去掉重复的 `minutes_` 前缀。

#### `minutes/`（纪要任务主体）

| 现文件 | 目标 |
|---|---|
| `test_minutes_prompt_map.py` | `minutes/test_prompt_map.py` |
| `test_minutes_qa_quote_prompt_rules.py` | `minutes/test_prompt_rules.py`（生成 + 渲染问答/金句规则） |
| `test_minutes_view_state.py` | `minutes/test_view_state.py` |
| `test_minutes_view_injection.py` | `minutes/test_view_injection.py` |
| `test_minutes_view_required.py` | `minutes/test_view_required.py` |
| `test_minutes_template_auto_switch.py` | `minutes/templates/test_auto_switch.py` |
| `test_minutes_template_boundaries.py` | `minutes/templates/test_boundaries.py` |
| `test_minutes_template_classifier_agent.py` | `minutes/templates/test_classifier_agent.py` |
| `test_minutes_template_classifier_core.py` | `minutes/templates/test_classifier_core.py` |
| `test_minutes_template_classify_node.py` | `minutes/templates/test_classify_node.py` |
| `test_minutes_template_integration.py` | `minutes/templates/test_integration.py`（若跨 3+ 包，改挂 `integration/`） |
| `test_minutes_template_matrix.py` | `minutes/templates/test_matrix.py` |
| `test_minutes_template_separation.py` | `minutes/templates/test_separation.py` |
| `test_minutes_template_state.py` | `minutes/templates/test_state.py` |
| `test_minutes_scene_catalog.py` | `minutes/templates/test_scene_catalog.py` |
| `test_template_i18n.py` | `minutes/templates/test_i18n.py`（868 行，后续拆） |
| `test_multi_source_minutes.py` | `minutes/test_multi_source.py` |
| `test_debates_field_removed.py` | `minutes/test_removed_fields.py`（与下一条合并） |
| `test_scene_field_removed.py` | `minutes/test_removed_fields.py`（与上一条合并） |
| `test_understanding_profiles.py` | `minutes/test_understanding_profiles.py` |
| `test_minutes_agenda_integration.py` | `tests/integration/meeting/minutes/test_agenda.py`（导入 8 个包，1064 行） |
| `test_intelligent_minutes_integration.py` | `tests/integration/meeting/minutes/test_intelligent.py` |

#### `minutes/topic_major/`

| 现文件 | 目标 |
|---|---|
| `test_minutes_topic_major_agent.py` | `minutes/topic_major/test_agent.py` |
| `test_minutes_topic_major_contract.py` | `minutes/topic_major/test_contract.py` |
| `test_minutes_topic_major_memory.py` | `minutes/topic_major/test_memory.py` |
| `test_minutes_topic_major_prompts.py` | `minutes/topic_major/test_prompts.py` |
| `test_minutes_topic_major_render.py` | `minutes/topic_major/test_render.py` |
| `test_minutes_topic_major_supervisor.py` | `minutes/topic_major/test_supervisor.py` |

#### `agenda/`

| 现文件 | 目标 |
|---|---|
| `test_agenda_alignment.py` | `agenda/test_alignment.py`（971 行，后续拆） |
| `test_agenda_assembly.py` | `agenda/test_assembly.py` |
| `test_agenda_engine.py` | `agenda/test_engine.py` |
| `test_agenda_memory_injection.py` | `agenda/test_memory_injection.py` |
| `test_agenda_memory_persistence.py` | `agenda/test_memory_persistence.py` |
| `test_agenda_objective_boundary.py` | `agenda/test_objective_boundary.py`（611 行，后续拆） |
| `test_agenda_parser.py` | `agenda/test_parser.py` |
| `test_agenda_vision.py` | `agenda/test_vision.py` |
| `test_tasks_image_agenda.py` | `agenda/test_image_agenda.py` |

#### `actions/`

| 现文件 | 目标 |
|---|---|
| `test_actions_context.py` | `actions/test_context.py` |
| `test_actions_context_cleanup.py` | `actions/test_context_cleanup.py` |
| `test_actions_objective_contract_freeze.py` | `actions/test_contract_freeze.py` |
| `test_actions_skip_perspective.py` | `actions/test_skip_perspective.py` |

#### `personal/`

| 现文件 | 目标 |
|---|---|
| `test_personal_context_cleanup.py` | `personal/test_context_cleanup.py` |
| `test_personal_contract_freeze.py` | `personal/test_contract_freeze.py` |
| `test_personal_draft_context.py` | `personal/test_draft_context.py` |
| `test_personal_hard_execution.py` | `personal/test_hard_execution.py` |
| `test_personal_perspective_node.py` | `personal/test_perspective_node.py` |
| `test_memory_perspective_mode.py` | `personal/test_memory_mode.py` |

#### `supervisor/`

| 现文件 | 目标 |
|---|---|
| `test_supervisor_prompt_structure.py` | `supervisor/test_prompt_structure.py` |
| `test_supervisor_source_pack.py` | `supervisor/test_source_pack.py` |

> `tests/unit/meeting/` 清空后删除。

### 4.3 第三批：旧目录 `tests/core` + `tests/meeting`

这些文件先**审计**再决定去向。审计标准：

1. 是否已被新目录中的测试覆盖？
2. 是否有独有断言？
3. 是否实际是集成/端到端？

| 现文件 | 行数 | 建议目标 | 方式 |
|---|---:|---|---|
| `tests/core/test_core.py` | 706 | 拆到 `unit/core/runner/`、`unit/core/registry/`、`integration/core/` | 先审计，再拆 |
| `tests/core/test_draft_scrape.py` | 108 | `unit/core/graph/test_draft_scrape.py` | 与现有 graph 测试合并 |
| `tests/core/test_engine_smoke.py` | 312 | `integration/core/test_engine_smoke.py` | 整体迁移 |
| `tests/core/test_perspective.py` | 1054 | `unit/domains/shared/perspective/` 下按证据包/agent/model 拆分 | 转 assert 后合并 |
| `tests/core/test_supervisor_optimization.py` | 532 | `unit/core/runtime/test_supervisor_slice.py` + `unit/domains/meeting/supervisor/` | 拆分 |
| `tests/meeting/test_actions_only_e2e.py` | 125 | `e2e/meeting/test_actions_only.py` | 整体迁移 |
| `tests/meeting/test_actions_risks.py` | 546 | `unit/domains/meeting/actions/test_actions_risks.py` | 拆分 |
| `tests/meeting/test_agenda_coercion.py` | 335 | `unit/domains/meeting/agenda/test_coercion.py` | 转 assert |
| `tests/meeting/test_consensus_decision.py` | 408 | `unit/domains/meeting/consensus_decision/test_decision.py` | 整体迁移 |
| `tests/meeting/test_meeting_memory.py` | 1358 | `unit/domains/meeting/memory/` 下按事实抽取/持久化/双会话拆分 | 转 assert 后拆分 |
| `tests/meeting/test_meeting_memory_dual_session.py` | 341 | `unit/domains/meeting/memory/test_dual_session.py` | 整体迁移 |
| `tests/meeting/test_minutes_decoupling.py` | 282 | `unit/domains/meeting/personal/test_decoupling.py` | 审计 |
| `tests/meeting/test_minutes_fallback_render.py` | 200 | `unit/domains/meeting/minutes/render/test_fallback.py` | 整体迁移 |
| `tests/meeting/test_minutes_fast_render.py` | 390 | `unit/domains/meeting/minutes/render/test_fast_render.py` | 整体迁移 |
| `tests/meeting/test_minutes_styles.py` | 401 | `unit/domains/meeting/minutes_styles/test_styles.py` | 整体迁移 |
| `tests/meeting/test_minutes_trace.py` | 401 | `unit/domains/meeting/minutes_trace/test_trace.py` | 整体迁移 |
| `tests/meeting/test_personal_pipeline_e2e.py` | 213 | `e2e/meeting/test_personal_pipeline.py` | 整体迁移 |
| `tests/meeting/test_render_resilience.py` | 423 | `integration/meeting/test_render_resilience.py` | 整体迁移 |

> `tests/core/`、`tests/meeting/` 清空后删除。

### 4.4 第四批：巨石文件拆分

拆分顺序按"被依赖程度"和"静默程度"排，先转 assert 再拆。

| 文件 | 行数 | 拆分建议 |
|---|---:|---|
| `test_column_projection.py` | 1899 | `test_projection_basic.py` / `test_projection_qa_priority.py` / `test_projection_sections.py` / `test_projection_gate.py` / `test_projection_integration.py` |
| `test_section_pruner.py` | 1529 | `test_section_pruner_core.py` / `test_section_pruner_templates.py` / `test_section_pruner_matrix.py` |
| `test_meeting_memory.py` | 1358 | `test_memory_fact_extract.py` / `test_memory_persist.py` / `test_memory_render.py` / `test_memory_dual_session.py` |
| `test_agenda_pipeline.py` | 1139 | `integration/meeting/agenda/test_parse.py` / `test_assemble.py` / `test_export.py` |
| `test_minutes_agenda_integration.py` | 1064 | `integration/meeting/minutes/test_generation.py` / `test_supervisor.py` / `test_render.py` / `test_template_select.py` |
| `test_perspective.py` | 1054 | 证据包 / agent / model / 集成四块 |
| `test_agenda_alignment.py` | 971 | `agenda/test_alignment.py` / `agenda/test_export.py` |
| `test_template_i18n.py` | 868 | `minutes/templates/test_i18n_render.py` / `test_i18n_supervisor.py` / `test_i18n_generation.py` |
| `test_core.py` | 706 | `core/runner/test_hooks.py` / `core/registry/test_domain_hooks.py` / `core/config/test_config.py` |
| `test_placeholder_parser.py` | 646 | `test_placeholder_parse.py` / `test_placeholder_plan.py` / `test_placeholder_fill.py` |
| `test_agenda_objective_boundary.py` | 611 | `test_boundary_rules.py` / `test_supervisor.py` / `test_injection.py` |
| `test_template_gate.py` | 574 | `test_gate_empty.py` / `test_gate_brackets.py` / `test_gate_validation.py` |

拆分规则：

- 先 `git mv` 得到一个文件，再新建文件移函数；
- 每次只拆一个文件，提交后跑全量；
- 拆分不改断言，只移动；
- 共享的构造数据移到 `tests/support/builders.py`。

---

## 5. 最佳落地步骤

> 顺序不可随意调换：**配置 → 搬家 → 转 assert → 拆文件 → 分级 → 隔离 → CI**。
> 每一步都以"全量用例数与通过数不下降"为验收。

### 5.0 路线总览

| Step | 内容 | 前置 | 预估 | 提交粒度 |
|---|---|---|---|---|
| 0 | 基线转绿 | 无 | 0.5–2 天 | 每个失败一个修复 |
| 1 | 配置与 support | 0 | 0.5 天 | 1 |
| 2 | 结构性错位搬家 | 1 | 0.5 天 | 1 |
| 3 | `unit/meeting` 归位 | 2 | 1 天 | 7 |
| 4 | 旧目录清仓 | 3 | 1–2 天 | 每文件/每批 |
| 5 | `check()` → `expect()` | 4 | 1–3 天 | 每文件 |
| 6 | 拆分巨石文件 | 5 | 2–3 天 | 每文件 |
| 7 | unit / integration / e2e 分级 | 3、6 | 1 天 | 每目录 |
| 8 | 隔离与 fixture 治理 | 1 | 0.5–1 天 | 1–2 |
| 9 | 覆盖率与 CI | 7、8 | 0.5 天 | 1 |
| 10 | 文档与收尾 | 全部 | 0.5 天 | 1 |

关键路径：**0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 9**。

并行建议：

- Step 4 与 Step 5 存在文件重叠（旧目录里的静默测试），同一文件必须串行；不同子目录可以并行。
- Step 8 可以与 Step 5/6 并行，因为改的是 fixture 和路径，不碰断言。
- 任何时候都不要让两个人同时改同一个测试文件；按子目录切分工作。

### Step 0：冻结基线并分诊 15 个失败（必须先做）

**目标**：把 red 变成 green，后续每一步才可判断回归。

动作：

1. 保存基线：
   ```bash
   python -m pytest tests -q > /tmp/pytest-baseline.txt 2>&1
   ```
2. 逐个处理附录 A 的 15 个失败：
   - 断言过时 → 更新断言；
   - 模板数据/guide 漂移 → 更新数据或测试；
   - 真 bug → 修生产代码。
3. 不允许用 `skip`/`xfail` 批量掩盖；如果确需临时冻结，必须 `xfail(strict=True)` 并记录 issue。

验收：

```bash
python -m pytest tests -q
# 0 failed, 796 passed, 9 skipped（数量以实际为准）
```

#### Step 0 执行记录（2026-11-03）

结果：

```bash
python -m pytest tests -q
# 793 passed, 9 skipped, 1 warning in 19.23s
```

用例数变化：805 → 802（删除了 3 个已验证失效的文档同步测试）。

| # | 失败测试 | 根因 | 处理 |
|---:|---|---|---|
| 1 | `test_column_projection.py::test_qa_name_priority` | 模板已重构，旧短语「一条问答独立成段」不存在；原测试依赖已删除的称呼规则 | 按当前模板重写断言，并把该函数的 `check()` 改为 assert |
| 2 | `test_column_pruning_refactor.py::test_minutes_validation_auto_fills_missing_history_comparison` | 自动补全从 `Minutes.validate` 移到硬执行层 `enforce_minutes_draft` | 改测真实链路：`enforce_minutes_draft` → `Minutes.validate` |
| 3 | `test_column_pruning_refactor.py::test_prompts_overview_word_budget_and_mapping_rules` | 生成 prompt 去掉了「默认」字样 | 断言改为 `250–350 字` |
| 4 | `test_section_pruner.py::test_home_school_feedback_groups` | 模板栏目 `[家校探讨]` 已改为 `[话题探讨]`，措辞整体更新 | 按当前模板重写断言 |
| 5 | `test_section_pruner.py::test_media_briefing_evidence_and_depth` | 模板结构改为「按业务领域或政策板块设立小节」+「举措/成果要点」 | 按当前模板重写断言 |
| 6 | `test_agenda_objective_boundary.py::test_agenda_supervisor_aux_rule` | prompt 措辞为「指出来源辅助材料」 | 更新断言 |
| 7–9 | `test_minutes_scene_catalog.py` 3 个指南同步测试 | `MINUTES_SCENE_AGENT_PROMPT_GUIDE.md` 已于 `3e092c08` 删除 | 删除 3 个失效的文档同步测试及 helper |
| 10 | `test_minutes_template_integration.py::test_agenda_graph_selects_agenda_template_and_render_uses_it` | 编排层会剥离模板的 `<!-- layout ... -->` 元数据 | 期望值改为 `split_template_layout()` 后的干净模板 |
| 11 | `test_minutes_view_required.py::test_minutes_render_uses_view_not_context` | personal view 使用独立渲染 prompt，不含议程映射标题 | 改为断言 personal 渲染器标识 + 不含议程标题 |
| 12–14 | `test_template_i18n.py::test_supervisor_english_prompt_keeps_common_rules`（3 组参数） | 公共审核规则标题已改为「整体标准（所有领域通用的评判准则）」 | 更新断言 |
| 15 | `test_template_i18n.py::test_personal_en_render_prompt_uses_normal_template_prompt` | 同 #11，personal 使用独立渲染 prompt | 更新断言 |

注意：本批只修了失败点；`test_column_projection.py`、`test_section_pruner.py` 里仍有大量静默 `check()`，留到 Step 5 统一处理。

### Step 1：建立配置与 support 基础设施

**目标**：让后续搬家有统一入口，避免每个文件各自 `sys.path`。

动作：

1. 新增 `pyproject.toml`（内容见 3.3）。
2. 新建 `tests/support/`：
   ```
   tests/support/__init__.py
   tests/support/builders.py
   tests/support/fakes.py
   tests/support/expectations.py
   ```
3. `expectations.py` 提供：
   ```python
   def expect(ok: bool, message: str) -> None:
       if not ok:
           raise AssertionError(message)
   ```
4. 更新 `.gitignore`：
   ```
   data/test_user/
   logs/agenda_ocr/
   ```
   或更通用：`logs/`、`data/test_user/`（确认不会忽略业务数据）。
5. 保留 `tests/conftest.py` 的 `sys.path` 兜底，但新增注释说明 `pyproject.toml` 的 `pythonpath` 是主入口。

验收：

```bash
python -m pytest tests --collect-only -q    # 用例数不变
python -m pytest tests -q -m "not llm"      # 结果不变
```

#### Step 1 执行记录（2026-11-03）

已落地：

| 文件 | 内容 |
|---|---|
| `pyproject.toml` | `testpaths`、`pythonpath`、`--strict-markers --strict-config`、4 个 marker、`filterwarnings` |
| `tests/support/__init__.py` | 支撑包说明 |
| `tests/support/expectations.py` | `expect(condition, message)`：失败即 `AssertionError` |
| `tests/support/builders.py` | `minutes_draft(**overrides)`：最小 7 字段草稿构造器 |
| `tests/support/fakes.py` | 替身模块占位，Step 5/6 再收敛各测试的局部 `FakeLLM` |
| `.gitignore` | 忽略 `data/test_user/`、`logs/` |
| `tests/conftest.py` | 注明 `pythonpath` 是主入口，保留 `sys.path` 兜底 |

验证：

```bash
python -m pytest tests --collect-only -q
# 802 tests collected

python -m pytest tests -q
# 793 passed, 9 skipped, 1 warning in 19.43s
```

其他验证：

- `pytest --markers` 能列出 `integration` / `e2e` / `slow` / `llm`；
- `git check-ignore -v data/test_user/foo logs/agenda_ocr/bar` 命中新增规则；
- `expect(False, ...)` 确认抛出 `AssertionError`；
- `filterwarnings` 只对本仓库 `domains.*` 的 `DeprecationWarning` 升级为错误，langgraph 的三方警告不受影响。

### Step 2：第一批机械迁移（结构性错位）

**目标**：修掉最明显的 5 组错位。

动作（示例，Windows/Git Bash 均可）：

```bash
mkdir -p tests/unit/domains/shared/perspective
git mv tests/unit/core/perspective/test_personal_evidence_pack.py tests/unit/domains/shared/perspective/
git mv tests/unit/core/perspective/test_personal_perspective_agent.py tests/unit/domains/shared/perspective/
git mv tests/unit/core/perspective/test_personal_perspective_model.py tests/unit/domains/shared/perspective/
rmdir tests/unit/core/perspective

mkdir -p tests/unit/domains/shared/section_summary
git mv tests/unit/shared/test_section_summary.py tests/unit/domains/shared/section_summary/
rmdir tests/unit/shared

mkdir -p tests/unit/core/runner
git mv tests/unit/core/profiles/test_role_mapping.py tests/unit/core/runner/
git mv tests/unit/core/profiles/test_user_profile.py tests/unit/core/runner/
rmdir tests/unit/core/profiles

mkdir -p tests/unit/app/tasks
git mv tests/unit/core/test_structured_logging.py tests/unit/app/tasks/

mkdir -p tests/integration/api
git mv tests/integration/core/test_api_routes.py tests/integration/api/test_routes.py
rmdir tests/integration/core
```

补充 1：每个新目录创建 `__init__.py`：

```bash
find tests/unit/domains tests/integration/api -type d -exec touch {}/__init__.py \;
```

补充 2：`rmdir` 只能删除空目录，搬运前先清理缓存：

```bash
find tests -type d -name __pycache__ -exec rm -rf {} +
```

验收：

- `pytest --collect-only` 用例数不变；
- 全量结果与 Step 0 一致。

#### Step 2 执行记录（2026-11-03）

已完成 5 组机械迁移（仅 `git mv` + 包文件，无内容修改）：

| 原位置 | 新位置 | 文件数 |
|---|---|---:|
| `tests/unit/core/perspective/` | `tests/unit/domains/shared/perspective/` | 3 |
| `tests/unit/shared/test_section_summary.py` | `tests/unit/domains/shared/section_summary/` | 1 |
| `tests/unit/core/profiles/` | `tests/unit/core/runner/` | 2 |
| `tests/unit/core/test_structured_logging.py` | `tests/unit/app/tasks/` | 1 |
| `tests/integration/core/test_api_routes.py` | `tests/integration/api/test_routes.py` | 1 |

同步处理：

- 新增 `tests/unit/domains/`、`tests/unit/app/`、`tests/unit/core/runner/`、`tests/integration/api/` 的 `__init__.py`；
- 删除 `tests/unit/core/perspective/`、`tests/unit/core/profiles/`、`tests/unit/shared/`、`tests/integration/core/` 四个旧目录；
- 未发现残留的旧模块导入（`tests.unit.core.perspective` 等）。

验证：

```bash
python -m pytest tests --collect-only -q
# 802 tests collected（不变）

python -m pytest tests -q
# 793 passed, 9 skipped, 1 warning in 15.14s（不变）
```

### Step 3：第二批机械迁移（`tests/unit/meeting` 归位）

**目标**：建立 `tests/unit/domains/meeting/` 骨架，只搬家不改内容。

动作：

1. 建目录：
   ```bash
   mkdir -p tests/unit/domains/meeting/{minutes/{templates,topic_major,render},agenda,actions,personal,supervisor,memory,consensus_decision,minutes_styles,minutes_trace}
   ```
2. 按 4.2 的表逐批 `git mv`。建议按子目录分 7 个提交：minutes、topic_major、agenda、actions、personal、supervisor、其余。
3. 每个新目录补 `__init__.py`。
4. 删除空目录 `tests/unit/meeting`。

验收：

```bash
python -m pytest tests -q
# 与 Step 0 相同的通过数
```

#### Step 3 执行记录（2026-11-03）

已完成 `tests/unit/meeting/` → `tests/unit/domains/meeting/` 的整体迁移：

| 目标目录 | 测试文件数 |
|---|---:|
| `minutes/` | 9 |
| `minutes/templates/` | 11 |
| `minutes/topic_major/` | 6 |
| `agenda/` | 9 |
| `actions/` | 4 |
| `personal/` | 6 |
| `supervisor/` | 2 |
| `tests/integration/meeting/minutes/` | 2 |
| **合计** | **49** |

同步处理：

- 新增 8 个 `__init__.py`（`domains/meeting` 及 7 个子目录）；
- 删除旧目录 `tests/unit/meeting/`；
- `test_minutes_agenda_integration.py` → `tests/integration/meeting/minutes/test_agenda.py`；
- `test_intelligent_minutes_integration.py` → `tests/integration/meeting/minutes/test_intelligent.py`；
- `test_debates_field_removed.py` 与 `test_scene_field_removed.py` 先各自平移，合并到 `test_removed_fields.py` 留到 Step 6。

**必要的路径索引修正**：目录层级加深，5 处 `Path(__file__).resolve().parents[N]` 同步调整：

| 文件 | 新层级 | parents |
|---|---|---:|
| `agenda/test_objective_boundary.py` | `tests/unit/domains/meeting/agenda/` | 3 → 5 |
| `minutes/test_prompt_map.py` | `tests/unit/domains/meeting/minutes/` | 3 → 5 |
| `minutes/templates/test_boundaries.py` | `tests/unit/domains/meeting/minutes/templates/` | 3 → 6 |
| `minutes/templates/test_state.py` | `tests/unit/domains/meeting/minutes/templates/` | 3 → 6 |
| `minutes/topic_major/test_render.py` | `tests/unit/domains/meeting/minutes/topic_major/` | 3 → 6 |

验证：

```bash
python -m pytest tests --collect-only -q
# 802 tests collected（不变）

python -m pytest tests -q
# 793 passed, 9 skipped, 1 warning in 14.67s（不变）
```

### Step 4：第三批机械迁移（旧目录清仓）

**目标**：消灭 `tests/core/`、`tests/meeting/`。

动作：

1. 先审计：对每个旧文件执行：
   ```bash
   python -m pytest <旧文件> -q
   ```
   与目标目录中同类测试对比，确认独有断言。
2. 按 4.3 表 `git mv`。
3. 需要拆分的文件**先整体搬过去**，拆在 Step 6 做。
4. 删除空目录。

验收：

- `tests/core`、`tests/meeting` 不存在；
- 用例数与通过数不低于 Step 0。

#### Step 4 执行记录（2026-11-03）

审计结论：

- 迁移前 `tests/core` + `tests/meeting` 共 **164 passed**；
- 与新测试只有 1 个同名函数：`test_actions_has_no_understanding_profile`，但旧文件覆盖 actions/risks/minutes 的契约组合，新文件只覆盖 profile 解析，内容不同，**保留两份**，去重留到 Step 6；
- 其余旧测试没有同名覆盖，先整体迁移，拆分留到 Step 6。

迁移结果（18 个文件）：

| 原文件 | 新位置 |
|---|---|
| `tests/core/test_core.py` | `tests/integration/core/test_core.py` |
| `tests/core/test_draft_scrape.py` | `tests/unit/core/graph/test_draft_scrape.py` |
| `tests/core/test_engine_smoke.py` | `tests/integration/core/test_engine_smoke.py` |
| `tests/core/test_perspective.py` | `tests/unit/domains/shared/perspective/test_perspective.py` |
| `tests/core/test_supervisor_optimization.py` | `tests/unit/core/runtime/test_supervisor_optimization.py` |
| `tests/meeting/test_actions_only_e2e.py` | `tests/e2e/meeting/test_actions_only.py` |
| `tests/meeting/test_actions_risks.py` | `tests/unit/domains/meeting/actions/test_actions_risks.py` |
| `tests/meeting/test_agenda_coercion.py` | `tests/unit/domains/meeting/agenda/test_coercion.py` |
| `tests/meeting/test_consensus_decision.py` | `tests/unit/domains/meeting/consensus_decision/test_decision.py` |
| `tests/meeting/test_meeting_memory.py` | `tests/unit/domains/meeting/memory/test_meeting_memory.py` |
| `tests/meeting/test_meeting_memory_dual_session.py` | `tests/unit/domains/meeting/memory/test_dual_session.py` |
| `tests/meeting/test_minutes_decoupling.py` | `tests/unit/domains/meeting/personal/test_decoupling.py` |
| `tests/meeting/test_minutes_fallback_render.py` | `tests/unit/domains/meeting/minutes/render/test_fallback.py` |
| `tests/meeting/test_minutes_fast_render.py` | `tests/unit/domains/meeting/minutes/render/test_fast_render.py` |
| `tests/meeting/test_minutes_styles.py` | `tests/unit/domains/meeting/minutes_styles/test_styles.py` |
| `tests/meeting/test_minutes_trace.py` | `tests/unit/domains/meeting/minutes_trace/test_trace.py` |
| `tests/meeting/test_personal_pipeline_e2e.py` | `tests/e2e/meeting/test_personal_pipeline.py` |
| `tests/meeting/test_render_resilience.py` | `tests/integration/meeting/test_render_resilience.py` |

同步处理：

- 新建 `tests/e2e/`、`tests/unit/core/graph/`、`tests/unit/core/runtime/`、`tests/unit/domains/meeting/{memory,minutes/render,minutes_styles,minutes_trace,consensus_decision}/` 及对应 `__init__.py`；
- 删除 `tests/core/`、`tests/meeting/`；
- **路径索引修正**：`tests/integration/core/test_engine_smoke.py` 的 `parents[2]` → `parents[3]`（层级加深一层）；
- 其余旧文件使用 `app.config.PROJECT_ROOT` 或搜索式定位，不受移动影响。

验证：

```bash
python -m pytest tests --collect-only -q
# 802 tests collected（不变）

python -m pytest tests -q
# 793 passed, 9 skipped, 1 warning in 18.28s（不变）

python -m pytest <18 个文件的新目录> -q
# 198 passed（含同目录已有测试）
```

### Step 5：消灭静默 `check()`

**目标**：所有测试函数都能真正失败。

动作：

1. 把 `tests/support/expectations.py` 的 `expect()` 作为唯一入口。
2. 逐文件替换：
   ```python
   # before
   check("xxx", actual == expected, detail)
   # after
   expect(actual == expected, f"xxx: {detail}")
   ```
3. 删除本地 `PASS`/`FAIL` 全局列表和 `check()` 定义。
4. `tests/unit/core/templates/_common.py`：
   - 移除 `PASS`/`FAIL`；
   - `check` 改为 `expect`；
   - 迁移到 `tests/support/expectations.py`，`_common.py` 只保留模板基线常量。
5. 每改完一个文件，做一次**变异验证**：把某个断言条件取反，确认 pytest 能红，再改回来。

验收：

```bash
# 有 test 函数但既不 assert 也不调用 expect() 的文件数应为 0
python - <<'PY'
import ast, pathlib

def raises_on_failure(node):
    has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(node))
    has_expect = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "expect"
        for n in ast.walk(node)
    )
    return has_assert or has_expect

bad = []
for p in pathlib.Path("tests").rglob("test_*.py"):
    if "__pycache__" in str(p):
        continue
    tree = ast.parse(p.read_text(encoding="utf-8"))
    fns = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test")
    ]
    if fns and not all(raises_on_failure(f) for f in fns):
        bad.append(str(p))
print("files without assert/expect:", bad)
PY
```

> 注意：转 assert 后可能会暴露此前被掩盖的真实失败。这是预期收益，逐个修复，不要回退。

#### Step 5 执行记录（2026-11-03 / 11-04）

已完成全量转换：

| 指标 | 数值 |
|---|---:|
| 转换文件 | 11 |
| `check()` 调用 | 1,185 |
| 其中原本完全静默的文件 | 9 |
| 半静默文件（同时有 assert） | 2 |

转换后共暴露 **60 个此前被静默掩盖的失败**，全部处理完毕：

- **真实 bug（修生产代码）2 个**：
  - `domains/meeting/memory/inject.py`：`_item_matches_text` 的 4 字重合回退把「是否默认开启记忆引用」误判为「补齐记忆引用来源字段」已闭环；移除闭环判定的 4 字放宽（锚点定位仍保留）。
  - `core/graph/nodes.py`：规则门禁在发言人清单缺失时仍可免审放行；补充「speakers 非空」前置条件，与 `_few_party_reason` 同口径。
- **测试契约更新 58 处**：模板/prompt 文案漂移、渲染上下文边界、表格/栏位结构变化等，按当前实现更新断言或重写测试函数。
- **删除 1 个失效测试**：`test_group_headings_need_body` 依赖的全局模板句已不存在。
- **保留并回退的边界**：personal / actions 渲染上下文仍为「仅草稿 + 审核结论」；命中/偏好块只进 `minutes_styles` 等通用路径，未改变既有契约。

验证：

```bash
python -m pytest tests -q
# 792 passed, 9 skipped, 1 warning in 18.40s
```

静默检查：

- 源码中已无 `check()` 调用（仅注释/文档字符串提及）；
- 按「每个测试函数必须 assert / expect / pytest.raises」审计：**0 个文件不达标**。

### Step 6：拆分巨石文件

**目标**：单文件 ≤ 500 行。

动作：

1. 按 4.4 的顺序逐个拆。
2. 每拆一个文件：
   - 新建目标文件；
   - 复制必要 imports 和 fixture；
   - 移动测试函数；
   - 删除原文件或保留为薄入口（不推荐）；
   - `git add -A` 后跑该文件 + 全量。
3. 共享测试数据移到 `tests/support/builders.py`。

验收：

```bash
find tests -name "test_*.py" -exec wc -l {} + | awk '$1>500 {print}'
# 应为空，或仅剩有明确理由的文件
```

#### Step 6 执行记录（2026-11-04）

拆分前有 **13 个测试文件超过 500 行**，最大 `test_column_projection.py` 1,605 行。拆分后：

```bash
find tests -name "test_*.py" -not -path "*__pycache__*" -exec wc -l {} + \
  | awk '$2!="total" && $1>500'
# 空
```

最大文件降至 **484 行**（`test_supervisor_optimization.py`），测试文件总数 86 → 123。

主要拆分：

| 原文件 | 拆分后 |
|---|---|
| `test_column_projection.py` 1,605 | `test_prompt_contracts.py`、`test_understanding_names.py`、`test_column_fill.py`、`test_column_fill_edge_cases.py`、`test_render_context.py`、`test_supervisor_and_personal.py` |
| `test_meeting_memory.py` 1,195 | `test_memory_identity_bind.py`、`test_memory_state_persist.py`、`test_memory_render.py`、`test_memory_purge.py`，原文件保留 comparison 组 |
| `test_agenda_pipeline.py` 1,138 | `test_agenda_agent.py`、`test_agenda_render.py`、`test_agenda_coercion.py`、`test_agenda_vlm.py`，原文件保留 orchestrator 熔断 |
| `test_agenda.py`（integration）1,063 | `test_minutes_agenda_context.py`、`test_minutes_agenda_prepare.py`、`test_minutes_agenda_prompts.py`、`test_agenda_async.py` |
| `test_alignment.py` 970 | `test_alignment_english.py`、`test_alignment_advanced.py` |
| `test_perspective.py` 926 | `test_perspective_preferences.py`、`test_perspective_hits.py`、`test_perspective_templates.py` |
| `test_i18n.py` 868 | `test_i18n_render.py`、`test_i18n_parity.py`、`test_i18n_resolution.py` |
| `test_section_pruner.py` 829 | `test_section_pruner_behavior.py`、`test_first_column_behavior.py` |
| `test_core.py` 666 | `test_core_schema_artifacts.py`、`test_core_reports.py` |
| `test_objective_boundary.py` 610 | `test_agenda_context_boundaries.py` |
| `test_multi_source.py` 579 | `test_multi_source_pipeline.py` |
| `test_actions_risks.py` 545 | `test_actions_render.py`、`test_risks_render.py` |
| `test_placeholder_parser.py` 537 | `test_placeholder_budget.py`、`test_placeholder_templates.py` |

验证：

```bash
python -m pytest tests -q
# 792 passed, 9 skipped, 1 warning in 15.85s（不变）
```

说明：拆分时共享的 helper/常量会随函数复制到新文件（如 `_fact`、`_make_minutes_mock_client`）。这些重复的收敛到 `tests/support/` 留到 Step 10 统一处理，避免本轮同时改动断言与 helper 造成不可控回归。

### Step 7：重新划分 unit / integration / e2e

**目标**：`tests/unit` 只保留纯单元测试。

动作：

1. 对每个测试文件统计导入的顶级包数量（`app`/`core`/`domains`/`infra`）。
2. 导入 ≥ 2 个顶级包，或需要真实资源/真实 runner 的，移到 `integration/`。
3. 覆盖完整流程（输入 → 图执行 → 导出）的，移到 `e2e/`。
4. 给 `integration/`、`e2e/` 文件加 marker：
   ```python
   pytestmark = pytest.mark.integration
   ```
5. 单元测试保持无 marker，靠 `pytest tests/unit` 运行。

验收：

```bash
python -m pytest tests/unit -q -m "not integration and not e2e and not slow"
# 应在 10 秒内完成
python -m pytest -m integration -q
python -m pytest -m e2e -q
```

#### Step 7 执行记录（2026-11-04）

按「导入的顶级包数量」重新划分：

| 分类 | 文件数/用例数 | 规则 |
|---|---:|---|
| `tests/unit/` | 374 用例 | 只导入 1 个顶级包；运行 1.69s |
| `tests/integration/` | 424 用例 | 导入 ≥2 个顶级包，或跨模块/跨运行时 |
| `tests/e2e/` | 3 用例 | 完整流程 |

本次共将 **51 个**跨包文件从 `tests/unit/` 迁到 `tests/integration/`：

- `tests/unit/domains/meeting/**` → `tests/integration/meeting/**`（去掉 `domains/` 层）
- `tests/unit/domains/shared/**` → `tests/integration/shared/**`
- `tests/unit/core/**` → `tests/integration/core/**`
- `tests/unit/infra/**` → `tests/integration/infra/**`

同步处理：

- 所有 `tests/integration/**/test_*.py` 加 `pytestmark = pytest.mark.integration`；
- 所有 `tests/e2e/**/test_*.py` 加 `pytestmark = pytest.mark.e2e`；
- 5 处 `parents[N]` 因目录深度减少而同步减 1；
- 删除迁移后完全空的 3 个目录：`unit/core/runtime`、`unit/domains/meeting/consensus_decision`、`unit/domains/meeting/minutes_styles`；
- `tests/unit` 中已不存在导入 ≥2 个顶级包的测试文件。

验证：

```bash
python -m pytest tests -q
# 792 passed, 9 skipped, 1 warning in 16.97s

python -m pytest tests/unit -q
# 374 passed, 1 warning in 1.69s

python -m pytest tests -m integration --collect-only -q
# 424/801 tests collected

python -m pytest tests -m e2e --collect-only -q
# 3/801 tests collected
```

### Step 8：测试隔离与 fixture 治理

**目标**：跑测试不污染仓库。

动作：

1. 全量跑完后检查：
   ```bash
   git status --short
   ```
   不允许出现 `data/`、`logs/` 新文件。
2. 用 `tmp_path` 替换 `tempfile.mkdtemp`；用 fixture 管理全局输出目录。
3. `tests/conftest.py` 增加自动隔离 fixture：
   ```python
   @pytest.fixture(autouse=True)
   def _isolate_workspace(monkeypatch, tmp_path):
       monkeypatch.setenv("APP_OUTPUT_DIR", str(tmp_path / "output"))
       monkeypatch.setenv("APP_LOG_DIR", str(tmp_path / "logs"))
   ```
   前提是生产代码通过环境变量读取路径；否则 monkeypatch 配置函数。
4. `tests/fixtures/sample_images/`：要么在测试中引用，要么删除。

验收：

```bash
python -m pytest tests -q
git status --short   # 只剩本次代码改动
```

#### Step 8 执行记录（2026-11-04）

已实现运行期路径隔离：

| 层 | 改动 |
|---|---|
| `app/config.py` | 新增 `data_root()` / `log_root()`，分别读取 `AGENTFLOW_DATA_DIR` / `AGENTFLOW_LOG_DIR` |
| `app/outputs.py` | 产物目录改用 `data_root()` |
| `infra/exporters/outputs.py` | CLI 产物目录优先 `AGENTFLOW_DATA_DIR`，否则回退 `ctx.project_root/data` |
| `core/runner/runner.py` | TaskMonitor 目录优先 `AGENTFLOW_DATA_DIR` |
| `domains/meeting/agenda_vision.py` / `agenda_parser.py` | `logs/agenda_ocr` 改用 `AGENTFLOW_LOG_DIR` |
| `infra/ocr/engines.py` / `server_ocr.py` | `logs/ocr_failed` 改用 `AGENTFLOW_LOG_DIR` |
| `tests/conftest.py` | 导入期设置 `AGENTFLOW_DATA_DIR` / `AGENTFLOW_LOG_DIR` / `AGENTFLOW_LOG_FILE` / `AGENTFLOW_DIAG_LOG_FILE` 到会话级临时目录；autouse fixture 每例重新钉住；退出时自动清理 |
| `tests/fixtures/` | 删除未引用的 2 张样例图片 |

验证：

```bash
rm -rf data/test_user logs
python -m pytest tests -q
# 792 passed, 9 skipped, 1 warning in 15.81s

find data/test_user logs -type f
# 无输出

git status --short data logs
# 无输出
```

说明：测试仍可读取仓库内已跟踪的 `data/1/**` 输入素材；只有运行期产物与日志被重定向到临时目录。

### Step 9：覆盖率与 CI

**目标**：防止重构后测试质量回退。

动作：

1. 引入 `pytest-cov`（加入 requirements）。
2. 记录基线：
   ```bash
   python -m pytest tests -q -m "not llm" --cov=core --cov=domains --cov=app --cov=infra --cov-report=term-missing
   ```
3. 在 CI 中设置"只降不升"门槛：先按当前覆盖率减 2% 设阈值。
4. CI 命令：
   ```bash
   python -m pytest tests -m "not llm" --cov=core --cov=domains --cov=app --cov=infra --cov-fail-under=<baseline>
   ```
5. 每周跑一次 `-m llm` 的慢速集。

验收：

- CI 全绿；
- 覆盖率不低于基线；
- 新增测试必须落在 `unit/` 或 `integration/` 下的镜像路径。

#### Step 9 执行记录（2026-11-04）

已落地：

| 文件 | 内容 |
|---|---|
| `requirements-dev.txt`（新增） | `-r requirements.txt` + `pytest>=8,<9` + `pytest-cov>=7,<8` + `anyio>=4` |
| `pyproject.toml` | 新增 `[tool.coverage.run]` / `[tool.coverage.report]`，`fail_under = 47` |
| `.github/workflows/tests.yml`（新增） | push/PR 跑 `-m "not llm"` 并校验覆盖率；每周一跑 `-m llm`；同时检查测试没有写仓库 `data/`、`logs/` |
| `tests/conftest.py` | 无外部 Key 时设置占位 `DEEPSEEK_API_KEY` / `SILICONFLOW_API_KEY`，保证 CI 不需要 `.env` |

覆盖率基线（`-m "not llm"`）：

```
TOTAL   41842   21292   49%
Required test coverage of 47% reached. Total coverage: 49.11%
```

验证：

```bash
rm -rf data/test_user logs
python -m pytest tests -m "not llm" -q \
  --cov=app --cov=core --cov=domains --cov=infra \
  --cov-report=term-missing --cov-fail-under=47
# 792 passed, 9 skipped
# coverage 49.11% >= 47%

find data/test_user logs -type f
# 无输出
```

说明：当前没有测试标记 `llm`，每周定时任务暂时收集 0 个用例；后续新增真实模型测试时补 `@pytest.mark.llm` 即可。

### Step 10：文档与收尾

动作：

1. 新增 `tests/README.md`：目录约定、命名规则、如何跑 unit/integration/e2e、如何加新测试。
2. 删除 `tests/__main__.py`（可选；如果团队习惯 `python -m tests` 则保留）。
3. 在 CI 中加一步"目录镜像检查"（可选）：校验每个 `tests/unit/<path>` 在源码中存在对应目录。

#### Step 10 执行记录（2026-11-04）

已完成：

- 新增 `tests/README.md`：目录结构、分层规则、命名、运行命令、新增测试流程、隔离与 CI 约定；
- 保留 `tests/__main__.py`（`python -m tests` 仍可用）；
- 收敛拆分产生的重复 helper：
  - `_fact` → `tests/support/builders.py::meeting_fact`，5 个记忆测试文件改为导入；
  - `_make_minutes_mock_client` / `_run_minutes_graph` → `tests/support/fakes.py`，5 个 minutes 集成文件改为导入；
  - 多源上下文字符串与 `_agenda_context` / `_normal_context` → `tests/support/builders.py`，2 个文件改为导入；
- 修复 `tests/support/fakes.py` 缺失 docstring 结束引号的历史问题（此前未被导入所以未暴露）；
- 目录镜像检查未加入 CI（可选），当前靠 `tests/README.md` 约定 + review。

验证：

```bash
python -m pytest tests -q
# 792 passed, 9 skipped, 1 warning in 11.50s
```

---

## 6. 验收指标

| 指标 | 当前 | 目标 |
|---|---|---|
| 静默 `check()` 文件 | 9 | 0 |
| 有 test 函数但无 assert 的文件 | 9 | 0 |
| `tests/core`、`tests/meeting` | 存在 | 删除 |
| 目录与生产包错位 | 5 组 | 0 |
| 单文件 > 500 行 | 20 | ≤ 2（需说明理由） |
| pytest 配置文件 | 无 | `pyproject.toml` |
| 全量失败数 | 15 | 0（llm 除外） |
| 测试写仓库文件 | 是 | 否 |
| CI 覆盖率门槛 | 无 | 有，且只升不降 |

---

## 7. 风险与回滚

| 风险 | 影响 | 处理 |
|---|---|---|
| 转 assert 暴露大量真实失败 | 工期拉长 | 这是重构的核心收益；按文件修，禁止批量 xfail |
| 搬运导致 import 断链 | 全量 red | 每批只 `git mv`，跑 `--collect-only` 和全量；失败即回滚该批 |
| `tests.unit.core.templates._common` 被多处引用 | 移动后 import 失败 | Step 5 一并迁到 `tests/support/`，全局搜索替换 |
| Windows 路径/大小写 | 文件丢失 | 使用 `git mv` 和 `git status` 校验 |
| 多人同时改测试 | 冲突 | 按子目录分提交，先协调 `tests/unit/domains/meeting/` |
| 测试依赖真实 `resources/` | 环境敏感 | Step 8 用 fixture 固定目录；必要时塞进 `tests/fixtures/` |
| 覆盖率门槛误伤 | CI 红 | 先记录基线，再按基线减 2% 设阈值，逐步提高 |

通用回滚：

```bash
git reset --hard HEAD      # 丢弃当前批次
git clean -fd tests        # 清理未跟踪的新目录（确认后执行）
```

> 只在一个批次内回滚；不要把多批改动混在一个提交里。

---

## 8. 提交规范建议

每个批次一个提交，消息模板：

```
refactor(tests): move perspective tests under domains/shared

- git mv only, no content changes
- pytest: 805 collected, 781 passed, 15 failed (baseline unchanged)
```

拆分/改写：

```
test(tests): replace silent check() with expect() in test_perspective

- 186 checks converted to assertion-raising expect()
- mutation check: inverted condition now fails as expected
```

---

## 附录 A：15 个基线失败

| # | 文件::用例 | 分类 | 处理建议 |
|---:|---|---|---|
| 1 | `tests/unit/core/templates/test_column_projection.py::test_qa_name_priority` | 模板/断言漂移 | 对照当前 Q&A 命名优先级更新断言 |
| 2 | `tests/unit/core/templates/test_column_pruning_refactor.py::test_minutes_validation_auto_fills_missing_history_comparison` | 模板数据漂移 | 检查校验默认值是否变化 |
| 3 | `tests/unit/core/templates/test_column_pruning_refactor.py::test_prompts_overview_word_budget_and_mapping_rules` | prompt 断言漂移 | 更新 prompt 断言 |
| 4 | `tests/unit/core/templates/test_section_pruner.py::test_home_school_feedback_groups` | 模板数据漂移 | 更新模板/断言 |
| 5 | `tests/unit/core/templates/test_section_pruner.py::test_media_briefing_evidence_and_depth` | 模板数据漂移 | 更新模板/断言 |
| 6 | `tests/unit/meeting/test_agenda_objective_boundary.py::test_agenda_supervisor_aux_rule` | prompt 断言漂移 | 统一口径 |
| 7 | `tests/unit/meeting/test_minutes_scene_catalog.py::test_catalog_matches_guide_tables` | 数据/guide 漂移 | 更新 guide 或目录 |
| 8 | `tests/unit/meeting/test_minutes_scene_catalog.py::test_candidate_blocks_match_guide` | 数据/guide 漂移 | 同上 |
| 9 | `tests/unit/meeting/test_minutes_scene_catalog.py::test_system_prompt_template_matches_guide` | 数据/guide 漂移 | 同上 |
| 10 | `tests/unit/meeting/test_minutes_template_integration.py::test_agenda_graph_selects_agenda_template_and_render_uses_it` | 集成断言漂移 | 检查模板选择链路 |
| 11 | `tests/unit/meeting/test_minutes_view_required.py::test_minutes_render_uses_view_not_context` | prompt 断言漂移 | 更新 view 口径 |
| 12 | `tests/unit/meeting/test_template_i18n.py::test_supervisor_english_prompt_keeps_common_rules[agenda_objective]` | prompt 断言漂移 | 更新英文 supervisor 断言 |
| 13 | `tests/unit/meeting/test_template_i18n.py::test_supervisor_english_prompt_keeps_common_rules[objective]` | prompt 断言漂移 | 同上 |
| 14 | `tests/unit/meeting/test_template_i18n.py::test_supervisor_english_prompt_keeps_common_rules[personal]` | prompt 断言漂移 | 同上 |
| 15 | `tests/unit/meeting/test_template_i18n.py::test_personal_en_render_prompt_uses_normal_template_prompt` | prompt 断言漂移 | 同上 |

---

## 附录 B：常用命令

```bash
# 收集用例（搬家后第一时间跑）
python -m pytest tests --collect-only -q

# 全量
python -m pytest tests -q

# 只跑单元
python -m pytest tests/unit -q

# 只跑集成
python -m pytest -m integration -q

# 只跑端到端
python -m pytest -m e2e -q

# 指定文件
python -m pytest tests/unit/domains/meeting/minutes/test_prompt_rules.py -q

# 找超长测试文件
find tests -name "test_*.py" -exec wc -l {} + | awk '$1>500 {print}'
```
