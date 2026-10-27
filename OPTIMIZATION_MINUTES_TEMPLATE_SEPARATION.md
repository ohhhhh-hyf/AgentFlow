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
- Step 1：生成阶段移除 `【目标样式模板】` + 追加 7 字段清单。
- Step 2：篇幅预算去栏数（生成/审核不暴露模板栏数，渲染保留）。
- Step 3：`structured` 缺字段重试保留第一次内容；默认行为不变。
- Step 4：两个渲染 prompt 补 6 项栏目语义说明 + 3 条内联折叠尾句。
- Step 5：单元测试、模板矩阵测试与会议域回归已完成。
- Step 6：模板指纹 label、生成日志、文档/注释收尾已完成。

### 执行进度

| Step | 内容 | 状态 |
| --- | --- | --- |
| 1 | 生成阶段移除模板 + 字段清单 | **已完成（2026-10-27）** |
| 2 | 篇幅预算去栏数 | **已完成（2026-10-27）** |
| 3 | `structured` 重试可选参数 | **已完成（2026-10-27）** |
| 4 | 渲染 prompt 语义说明与折叠 | **已完成（2026-10-27）** |
| 5 | 测试与回归 | **已完成（2026-10-27）** |
| 6 | 观测与收尾 | **已完成（2026-10-27）** |

---

## 1. 生成阶段移除模板 + 字段清单（已完成 2026-10-27）

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

## 2. 篇幅预算不再带“本模板 N 栏”（已完成 2026-10-27）

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
| `orchestrator.py:888` 审核 | `include_columns=False` |
| `orchestrator.py:967` 渲染 | 默认 `True` |

### 2.3 验证

- 生成/审核上下文不含 `本模板 N 栏`；
- 渲染上下文仍含；
- 篇幅总预算数值不变。

---

## 3. `structured` 重试保留内容（已完成 2026-10-27）

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

## 4. 渲染 prompt 补栏目语义说明与折叠（已完成 2026-10-27）

**目标**：在渲染 prompt 里用自然语言说明“哪类草稿字段适合填哪类栏目”；
模板没有对应栏目时，在对应字段的说明行内折入最近相关小节，
不单独增加折叠规则段，也不丢事实。

> 注意：这里的“对应关系”是写进 prompt 的通用语义说明，
> **不是 #6 的“模板 → 草稿字段能力表”**：
> 不新增配置/字典，不按模板逐个登记；
> 模型根据当前所选模板的栏目语义自行对应。

文件：`domains/meeting/tasks/minutes/prompts.py`

### 4.1 `MINUTES_RENDER_TEMPLATE_PROMPT`

增加栏目语义说明：

- `executive_summary` 第 1 项 → 概括/概况/摘要类栏目；
- `executive_summary` 第 2 项起 → 业务研讨/要点/进展类栏目；
- `key_decisions` → 决议/结论/拍板类栏目；
- `personally_relevant_points` → 后续计划/行动/执行/待办类栏目；
  模板无此类栏目时，折入结论/决议或最近相关小节；
- `risks_and_blockers` → 风险/卡点/约束类栏目；
  模板无此类栏目时，折入结论/决议或最近相关小节；
- `unresolved_questions` → 遗留问题/未决/待确认类栏目；
  模板无此类栏目时，折入结论/决议或最近相关小节。

### 4.2 `MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`

增加同样的栏目语义说明（actions / risks / unresolved 三条带内联折叠尾句），
保留现有：

- 议题 `### 一.` 块放议题研讨类栏目；
- `key_decisions` 放决议结论类栏目。

### 4.3 验证

- 两个 render template prompt 都包含 6 项栏目语义说明；
- actions / risks / unresolved 三条各自带内联折叠尾句；
- 不单独增加“无对应栏目时的折叠规则”段；
- 模板没有 actions/risks/unresolved 栏目时，最终正文仍能看到内容；
- `MINUTES_AGENDA_RENDER_PROMPT`（无模板路径）不在本次修改范围。

---

## 5. 测试与回归（已完成 2026-10-27）

### 5.1 已落地测试

**`tests/unit/meeting/test_minutes_template_separation.py`**

- 普通/议题 `minutes` 生成上下文不含 `【目标样式模板】`；
- 含 7 字段完整性清单；
- `minutes_styles` 不加清单；
- 生成/审核预算不含“本模板 N 栏”，渲染保留；
- 两个 render prompt 有 6 项栏目语义说明 + 3 条内联折叠尾句；
- 不包含单独折叠规则段。

**`tests/unit/meeting/test_minutes_template_matrix.py`**

对 `resources/agenda_templates/zh/*.md` / `en/*.md` 全量矩阵：

- 普通/议题生成上下文都不含模板正文；
- 都含 7 字段清单；
- 渲染 prompt 都含 6 项栏目语义说明和 3 条内联折叠尾句。

**`tests/unit/infra/test_llm_structured_retry.py`**

- `preserve_content_on_validation_error=True`：保留第一次长内容，只补缺失字段；
- 默认 `False`：保持旧截断 + “篇幅精炼”行为。

**`tests/unit/meeting/test_multi_source_minutes.py`**

- `_length_budget_line` 桩支持新增的 `include_columns` 参数。

### 5.2 回归结果

| 测试集 | 结果 |
| --- | --- |
| `tests/meeting` + `tests/unit/meeting` + `tests/integration/meeting` | **341 passed, 9 skipped** |
| `tests/unit/infra` | **11 passed** |
| `tests/unit/core/templates` | 92 passed, **4 个既有失败**（与本优化无关，均为旧模板文案断言） |

回归覆盖：

- 普通纪要 objective / personal；
- 议题增强中英文；
- 非议程 docs 回退普通纪要；
- 记忆开启/关闭；
- 辅助材料（keypoints / notes / vision）；
- `minutes_styles`、`agenda_minutes`、`actions`、`risks`；
- 自然语言模板编译路径。

### 5.3 说明

- 模板矩阵测试验证的是**生成上下文与渲染 prompt**，不依赖真实模型；
- 真实 LLM 的全模板 A/B（生成 → 渲染 → 最终 Markdown）需要外部模型环境，
  当前 CI 未跑；上线前可按需手工抽测。
- `tests/unit/core/templates` 的 4 个失败为既有基线问题，
  与本次 Step 1–4 改动无关。

### 5.4 复跑命令

```bash
python -m pytest tests/unit/meeting tests/meeting tests/integration/meeting -q
python -m pytest tests/unit/infra -q
```

---

## 6. 观测与收尾（已完成 2026-10-27）

### 6.1 日志

- `minutes/agent` 的 label 已带模板指纹：
  `label=f"minutes/agent/{label_mode}/{template_id}"`；
  `template_id` 为模板正文 sha1 前 8 位，空模板为 `none`。
- `_line_shared_context` 生成 `minutes` 时记录：
  ```text
  [minutes:generation] template_in_context=False template_id=... template_chars=...
  ```
- 现有日志继续覆盖：
  - `[llm:done]`：prompt/completion tokens；
  - `structured invalid`：校验失败与缺失字段；
  - `[agent:done]`：最终草稿 chars；
  - 审核/渲染阶段的 `[agent:review]`、`[render:done]`。

### 6.2 文档/注释

- 本清单已同步全部完成状态；
- `DECISION_MINUTES_DEFAULT_RENDER_MODE.md` 保持已实施状态；
- 代码中“默认模板由 render_draft 纯 Python 装配”的旧说法已清理；
- `tests/unit/meeting/test_minutes_agenda_integration.py` 的 label 断言
  已改为子串匹配，兼容新增模板指纹后缀。

### 6.3 收尾验证

- 模板指纹测试：通过；
- label 带 `template_id` 测试：通过；
- 生成日志 `template_in_context=False` 测试：通过；
- 全量回归见 Step 5 / 最终验收。

---

## 7. 执行顺序

1. Step 1：生成阶段移除模板 + 字段清单（已完成）
2. Step 2：篇幅预算去栏数（已完成）
3. Step 3：`structured` 重试可选参数（已完成）
4. Step 4：渲染 prompt 语义说明与折叠（已完成）
5. Step 5：测试与回归（已完成）
6. Step 6：观测与收尾（已完成）

每一步做完先跑对应定向测试，最后跑全量。

---

## 8. 验收标准

- [x] 生成阶段（普通/议题）不再出现 `【目标样式模板】`；
- [x] 用户消息末尾有 7 字段完整性清单；
- [x] 生成/审核预算不含“本模板 N 栏”，渲染保留；
- [x] `structured` 缺字段重试保留第一次内容；
- [x] 渲染 prompt 有 6 项栏目语义说明（含 3 条内联折叠尾句）；
- [x] 模板无 actions/risks/unresolved 栏目时，内容折叠后可见（兜底/提示级测试）；
- [ ] 所有模板第一次生成输出 7 个键；
- [ ] 非通用模板不再稳定缺 4 个字段；
- [ ] 最终 Markdown 仍符合模板栏目；
- [x] 普通纪要、议题纪要、`agenda_minutes`、`minutes_styles` 无回归；
- [ ] `ruff check` 通过；
- [x] `tests/unit/meeting` + `tests/meeting` + `tests/integration/meeting` 全绿。

---

## 9. 不做清单

- 不切默认模板纯 Python；
- 不加模板内容侧重短提示；
- 不维护“模板 → 草稿字段”能力表；
- 不改审核覆盖（decisions/risks/unresolved 仍不送审）；
- 不改 `agenda_minutes` 独立线、`minutes_styles`；
- 不扩展 `render_draft` 为默认模板正常渲染器。
