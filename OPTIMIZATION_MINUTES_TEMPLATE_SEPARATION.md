# 议题纪要模板解耦：可执行优化清单

- 日期：2026-10-27
- 范围：`meeting` 域 `minutes` 任务线（普通模板纪要 + 议题增强纪要）
- 目标：生成阶段不再看完整排版模板；渲染阶段保留模板；7 字段完整输出；兜底只做无模板/失败兜底
- 不涉及：`agenda_minutes` 独立线、`minutes_styles`、notes 域

---

## 0. 已定约束

| 事项 | 决策 |
| --- | --- |
| 默认模板 `general_minutes` / `personal_minutes` | 也走 LLM；不切纯 Python |
| `render_draft` | 仅无模板 / 空白模板 / LLM 失败时兜底 |
| 模板没有 actions/risks/unresolved 栏目 | **折叠**到最近相关小节，不静默省略 |
| 模板内容侧重短提示 | 暂不加 |
| 模板 → 草稿字段能力表 | 暂不维护 |
| 审核是否纳入 decisions/risks/unresolved | 保持现状，不纳入 |
| `structured` 重试 | 可选参数隔离，默认旧行为，只让 `minutes` 开启 |

### 已完成，不需重复

- `render_fallback_minutes` + `render_draft` 7 字段兜底。
- `uses_llm_render` 删除默认模板名特判；默认模板也走 LLM。
- 对应测试已更新：`tests/meeting/test_minutes_fast_render.py`、
  `tests/meeting/test_minutes_fallback_render.py`。

---

## 1. 生成阶段移除模板 + 字段清单

**目标**：`minutes`（普通/议题）生成上下文不再出现 `【目标样式模板】`，
只保留 JSON 契约；用户消息末尾加 7 字段完整性清单。

### 1.1 移除模板注入

文件：`domains/meeting/orchestrator.py` `_line_shared_context`

删除 `line_name == "minutes"` 分支里的：

```python
tpl = (state.get("templates") or {}).get("minutes") or ""
tpl_str = str(tpl).strip()
if tpl_str:
    parts.append(f"【目标样式模板】\n{tpl_str}")
```

保留：

- `【审定议题草稿生成执行准绳】`（议题模式，正文写法）；
- `state["templates"]`（渲染阶段仍需要）。

### 1.2 加 7 字段完整性清单

在 `_line_shared_context` 返回前，对 `minutes` 追加：

```text
【本轮 JSON 输出契约（唯一结构，最高优先级）】
必须同时输出：
headline、executive_summary、key_decisions、personally_relevant_points、
risks_and_blockers、unresolved_questions、history_comparison。
无内容写 []；
不得因为最终模板栏目少而省略字段；
不得把 decisions / actions / risks 并入 executive_summary。
```

注意：普通纪要和议题纪要都加；`minutes_styles` 不加。

### 1.3 验证

- `_line_shared_context(state, "minutes")` 不含 `【目标样式模板】`；
- 含 7 字段清单；
- 议题模式仍含 `【审定议题草稿生成执行准绳】`；
- `minutes_styles` / `agenda_minutes` / `actions` / `risks` 上下文不变。

---

## 2. 篇幅预算不再带“本模板 N 栏”

**目标**：生成/审核阶段不暴露模板栏数，避免模型按模板栏目组织草稿；
渲染阶段保留栏数。

文件：`domains/meeting/orchestrator.py` `_length_budget_line`

### 2.1 改签名

增加参数：

```python
@staticmethod
def _length_budget_line(
    state: dict,
    line_name: str,
    *,
    include_columns: bool = True,
) -> str:
```

`include_columns=False` 时：

- 不调用 `plan_placeholder_fill` 计算栏数；
- `columns = 0`；
- 只输出总篇幅预算。

### 2.2 改调用点

| 调用点 | 参数 |
| --- | --- |
| `orchestrator.py:798` 生成 | `include_columns=False` |
| `orchestrator.py:879` 审核 | `include_columns=False` |
| `orchestrator.py:950` 渲染 | 默认 `True` |

### 2.3 验证

- 生成/审核上下文不含 `本模板 N 栏`；
- 渲染上下文仍含；
- 篇幅总预算数值不变。

---

## 3. `structured` 重试保留内容

**目标**：缺字段重试时保留第一次内容，只补缺失字段；不影响其他任务线。

文件：`infra/llm/llmclient.py` `structured`

### 3.1 加可选参数

```python
async def structured(
    ...,
    preserve_content_on_validation_error: bool = False,
) -> T:
```

默认 `False`，保持现有行为。

### 3.2 重试分支

当 `preserve_content_on_validation_error=True`：

- 不截断 `assistant_content`；
- 缺字段时提示：

```text
保留已有字段内容，只补齐缺失字段；
不要压缩、清空或改写已有内容。
```

- 只有“超长/截断/非法 JSON”才允许“篇幅精炼”或修复。

当为 `False`：保持现有逻辑。

### 3.3 `minutes` 调用开启

文件：`domains/meeting/tasks/minutes/steps/minutes_agent.py`

`minutes/agent/...` 的 `structured` 调用增加：

```python
preserve_content_on_validation_error=True,
```

### 3.4 验证

- 第一次返回 `headline + executive_summary` 长内容；
- 重试后保留长内容，只补缺失字段；
- 不再出现 922 字薄稿；
- notes/code 等其他线默认行为不变。

---

## 4. 渲染 prompt 补齐字段映射与折叠

**目标**：渲染器明确 7 字段 → 模板栏目；模板没有栏目时折叠，不丢事实。

文件：`domains/meeting/tasks/minutes/prompts.py`

### 4.1 `MINUTES_RENDER_TEMPLATE_PROMPT`

增加映射：

- `executive_summary` 第 1 项 → 概括/概况/摘要类栏目；
- `executive_summary` 第 2 项起 → 业务研讨/要点/进展类栏目；
- `key_decisions` → 决议/结论/拍板类栏目；
- `personally_relevant_points` → 后续计划/行动/执行/待办类栏目；
- `risks_and_blockers` → 风险/卡点/约束类栏目；
- `unresolved_questions` → 遗留问题/未决/待确认类栏目。

### 4.2 `MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`

增加同样的映射，保留现有：

- 议题 `### 一.` 块放议题研讨类栏目；
- `key_decisions` 放决议结论类栏目。

### 4.3 无栏目折叠规则（两处 prompt 都加）

```text
模板没有对应栏目时，按以下规则折叠，不得静默丢弃：
- personally_relevant_points：优先折入后续计划/行动/决议/结论类栏目；
  没有则折入最近议题/正文小节；
- risks_and_blockers：优先折入风险/卡点/约束类栏目；
  没有则折入结论/决议或最近议题小节；
- unresolved_questions：优先折入遗留问题/未决/待确认类栏目；
  没有则折入结论/决议或最近议题小节。

默认 general_minutes 三栏模板：
actions / risks / unresolved 统一折叠到“结论定调”，以子条目呈现。
折叠只加子条目，不新增顶层栏目。
```

### 4.4 验证

- 两个 render template prompt 都包含 6 项映射；
- 都包含折叠规则；
- 模板没有 actions/risks/unresolved 栏目时，最终正文仍能看到内容；
- `MINUTES_AGENDA_RENDER_PROMPT`（无模板路径）不在本次修改范围。

---

## 5. 测试与回归

### 5.1 新增/修改单元测试

- `_line_shared_context`：
  - 普通纪要：不含 `【目标样式模板】`，含 7 字段清单；
  - 议题纪要：不含 `【目标样式模板】`，含 7 字段清单和执行准绳；
- `_length_budget_line`：
  - 生成/审核不含“本模板 N 栏”；
  - 渲染含；
- `structured`：
  - `preserve_content_on_validation_error=True` 时保留长内容；
  - 默认 False 行为不变；
- render prompt：
  - 6 项字段映射存在；
  - 折叠规则存在。

### 5.2 集成测试

对 `resources/agenda_templates/zh/*.md` / `en/*.md` 逐个跑：

- 草稿 7 个键全部存在；
- `executive_summary` 没有混入 `## [栏目]`、表格、`[占位符]`；
- `key_decisions` / `personally_relevant_points` / `risks_and_blockers` /
  `unresolved_questions` 有对应事实时不为空；
- 模板没有对应栏目时，内容已折叠到目标小节，最终正文可见；
- 最终 Markdown 仍符合模板栏目。

### 5.3 回归

- 普通纪要 objective / personal；
- 议题增强中英文；
- 非议程 docs 回退普通纪要；
- 记忆开启/关闭；
- 辅助材料（keypoints / notes / vision）；
- `minutes_styles`、`agenda_minutes`、`actions`、`risks`；
- 自然语言模板编译。

### 5.4 命令

```bash
ruff check core/runtime/kinds.py \
  domains/meeting/orchestrator.py \
  domains/meeting/tasks/minutes/steps/minutes_render.py \
  domains/meeting/tasks/minutes/steps/minutes_agent.py \
  infra/llm/llmclient.py \
  tests/unit/meeting tests/meeting

python -m pytest tests/unit/meeting tests/meeting tests/integration/meeting -q
```

---

## 6. 观测与收尾

### 6.1 日志

- 在 `minutes/agent` 的 label 里带模板名：
  `label=f"minutes/agent/{label_mode}/{template_id}"`；
- 记录生成上下文是否包含模板、第一次 completion tokens、
  是否校验重试、缺失字段、最终草稿 chars。

### 6.2 文档/注释

- 同步 `OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md` 的完成状态；
- `DECISION_MINUTES_DEFAULT_RENDER_MODE.md` 保持已实施状态；
- 清理代码中“默认模板由 render_draft 纯 Python 装配”的旧说法。

---

## 7. 执行顺序

1. Step 1：生成阶段移除模板 + 字段清单（独立）
2. Step 2：篇幅预算去栏数（独立）
3. Step 3：`structured` 重试可选参数（独立）
4. Step 4：渲染 prompt 映射与折叠（依赖 #1 折叠决策，已定）
5. Step 5：测试与回归
6. Step 6：观测与收尾

每一步做完先跑对应定向测试，最后跑全量。

---

## 8. 验收标准

- [ ] 生成阶段（普通/议题）不再出现 `【目标样式模板】`；
- [ ] 用户消息末尾有 7 字段完整性清单；
- [ ] 生成/审核预算不含“本模板 N 栏”，渲染保留；
- [ ] `structured` 缺字段重试保留第一次内容；
- [ ] 渲染 prompt 有 6 项字段映射和折叠规则；
- [ ] 模板无 actions/risks/unresolved 栏目时，内容折叠后可见；
- [ ] 所有模板第一次生成输出 7 个键；
- [ ] 非通用模板不再稳定缺 4 个字段；
- [ ] 最终 Markdown 仍符合模板栏目；
- [ ] 普通纪要、议题纪要、`agenda_minutes`、`minutes_styles` 无回归；
- [ ] `ruff check` 通过；
- [ ] `tests/unit/meeting` + `tests/meeting` + `tests/integration/meeting` 全绿。

---

## 9. 不做清单

- 不切默认模板纯 Python；
- 不加模板内容侧重短提示；
- 不维护“模板 → 草稿字段”能力表；
- 不改审核覆盖（decisions/risks/unresolved 仍不送审）；
- 不改 `agenda_minutes` 独立线、`minutes_styles`；
- 不扩展 `render_draft` 为默认模板正常渲染器。
