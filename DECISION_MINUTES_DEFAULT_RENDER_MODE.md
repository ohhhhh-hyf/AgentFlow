# 默认模板渲染模式收口：取消“默认模板走纯 Python”分支

- 日期：2026-10-27
- 状态：已实施（2026-10-27）
- 关联文档：`OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md`
- 范围：`meeting` 域 `minutes` 任务线
- 不涉及：`agenda_minutes` 独立线、`minutes_styles`、notes 域

---

## 1. 决策

采用以下统一规则：

```text
默认模板 = general_minutes（个人视角为 personal_minutes）
自定义模板 = 用户选择的模板
全部走 LLM 渲染
render_draft 只做失败兜底 / 无模板兜底
```

明确取消：

```text
“默认模板 general_minutes / personal_minutes 正常走纯 Python”
```

也就是说，`uses_llm_render` 不再对默认模板名做特殊放行。

---

## 2. 背景

### 2.1 原设计

`core/runtime/kinds.py` 的 `uses_llm_render` 原本想：

- 无模板 → 纯 Python `render_draft`；
- 默认模板 `general_minutes` / `personal_minutes` → 纯 Python；
- 自定义模板 → LLM 渲染。

### 2.2 实际情况

API 传给 `uses_llm_render` 的是**模板正文**，不是模板名：

```text
<!-- requirement
客观全面呈现会议核心内容与决策……
-->

## [全文摘要]
...
```

所以：

- `"general_minutes"` 名字判断永远不命中；
- 默认模板实际一直走 LLM；
- `render_draft` 只在模板为空或 LLM 渲染失败时兜底；
- 测试只覆盖了“传模板名”的路径，没有覆盖 API 真实路径，造成“默认模板是纯 Python”的误判。

### 2.3 为什么现在收口

`render_draft` 已改为 `render_fallback_minutes` 的 7 字段兜底布局，
支持议题 `### 一.` 块。兜底能力已经具备，默认模板不需要再保留一个
“纯 Python 正常路径”的旧分支。

继续保留该分支只会造成：

- 代码与实际行为不一致；
- 测试与生产路径不一致；
- 后续维护者误以为默认模板零 LLM；
- 与本次“默认模板也走 LLM”的决策冲突。

---

## 3. 目标逻辑

### 3.1 分流规则

| 情况 | 是否走 LLM | 走什么 |
| --- | --- | --- |
| 有非空模板（默认或自定义） | 是 | `render.run` / `render.stream` |
| 模板为空 / 空白 | 否 | `render_draft` 兜底 |
| LLM 渲染失败 | — | `render_draft` 兜底（`produce_line` 外层 except） |

### 3.2 默认模板

- 不传模板时，`app/tasks.py` 仍自动选择 `general_minutes` / `personal_minutes`；
- 选中后，模板正文非空 → 走 LLM；
- 默认模板不再走纯 Python 正常路径；
- 只有模板解析失败、模板为空、LLM 渲染失败时，才走 `render_draft`。

### 3.3 兜底

- `render_draft` 保留；
- 仅作为：
  - 无模板/空白模板的确定性输出；
  - LLM 渲染失败时的保底输出；
- 兜底布局为 7 字段 1:1 映射：
  - `headline` → 标题
  - `executive_summary[0]` → 全文摘要
  - `executive_summary[1:]` → 要点梳理
  - `key_decisions` → 关键决策
  - `personally_relevant_points` → 全员执行要点 / 职责相关事项
  - `risks_and_blockers` → 风险与阻塞
  - `unresolved_questions` → 未决问题
  - `history_comparison` → 与历史对比

---

## 4. 代码改动

### 4.1 `core/runtime/kinds.py`

**Before**

```python
def uses_llm_render(self, template: object = False) -> bool:
    if self.llm_render == "always":
        return True
    if self.llm_render == "never":
        return False
    if self.llm_render == "if_template":
        if not template:
            return False
        if isinstance(template, str):
            s = template.strip()
            # 通用纪要与个人视角纪要是系统的默认基线模板，字段 1:1 映射，
            # 由 render_draft 纯 Python 零延迟装配，不调 LLM
            if (
                not s
                or s in {"general_minutes", "personal_minutes", "通用纪要", "个人视角纪要"}
                or s.startswith("# 个人视角纪要")
            ):
                return False
        return bool(template)
    raise ValueError(f"未知 llm_render：{self.llm_render}")
```

**After**

```python
def uses_llm_render(self, template: object = False) -> bool:
    """是否走 LLM 渲染。

    if_template：有非空模板 → LLM；无模板/空白模板 → render_draft 兜底。
    """
    if self.llm_render == "always":
        return True
    if self.llm_render == "never":
        return False
    if self.llm_render == "if_template":
        if isinstance(template, str):
            return bool(template.strip())
        return bool(template)
    raise ValueError(f"未知 llm_render：{self.llm_render}")
```

### 4.2 行为对照

| 输入 | 旧行为 | 新行为 |
| --- | --- | --- |
| `""` | False | False |
| `"   "` | False | False |
| `False` / `None` / `0` | False | False |
| `True` | True | True |
| `"general_minutes"` | False | **True** |
| `"personal_minutes"` | False | **True** |
| `"通用纪要"` | False | **True** |
| `"个人视角纪要"` | False | **True** |
| `"# 个人视角纪要\n..."` | False | **True** |
| `"project_progress"` | True | True |
| 任意模板正文 | True | True |

**关键点**：

- 生产 API 传入的是**模板正文**，旧行为本来就是 True；
- 清理特判后生产 API 行为不变；
- 只有“传模板名”的测试/CLI/内部调用会从 False 变成 True。

---

## 5. 测试改动

### 5.1 `tests/meeting/test_minutes_fast_render.py:88`

测试：`test_line_policy_uses_llm_render_routing`

**Before**

```python
assert policy.uses_llm_render("general_minutes") is False
assert policy.uses_llm_render("personal_minutes") is False
assert policy.uses_llm_render("通用纪要") is False
assert policy.uses_llm_render("个人视角纪要") is False
assert policy.uses_llm_render("# 个人视角纪要\n\n## [会议概况]...") is False
```

**After**

```python
# 有模板（默认或自定义）→ LLM
assert policy.uses_llm_render("general_minutes") is True
assert policy.uses_llm_render("personal_minutes") is True
assert policy.uses_llm_render("通用纪要") is True
assert policy.uses_llm_render("个人视角纪要") is True
assert policy.uses_llm_render("# 个人视角纪要\n\n## [会议概况]...") is True

# 无模板 / 空白模板 → 纯 Python 兜底
assert policy.uses_llm_render("") is False
assert policy.uses_llm_render("   ") is False
assert policy.uses_llm_render(False) is False
```

测试名/注释同步改为：

```text
验证 LinePolicy 的有模板/无模板分流：
- 有非空模板（默认或自定义）→ LLM；
- 无模板/空白模板 → render_draft 兜底。
```

### 5.2 `tests/meeting/test_minutes_fast_render.py:108`

测试：`test_produce_line_minutes_fast_path_zero_llm`

该测试现在用：

```python
"templates": {"minutes": "general_minutes"}
```

清理特判后，这会走 LLM，测试会失败。

**改为无模板兜底测试**：

- 重命名为：

```python
def test_produce_line_minutes_no_template_fallback_zero_llm() -> None:
```

- 模板改为：

```python
"templates": {"minutes": ""}
```

- 断言保持：
  - `mock_render.stream_called == 0`
  - `mock_render.run_called == 0`
  - `fill_mode == "draft"`
  - 输出包含 `# 测试周会`、`## 全文摘要`、历史对照
  - `_render_context` 不被调用

这样它测的是“无模板兜底”，不是“默认模板快速路径”。

### 5.3 文件头注释

`tests/meeting/test_minutes_fast_render.py` 顶部：

**Before**

```text
2. LinePolicy.uses_llm_render 对默认模板与自定义模板的分流识别
```

**After**

```text
2. LinePolicy.uses_llm_render 的有模板/无模板分流识别
```

### 5.4 其他测试排查

已确认不需要改：

- `tests/meeting/test_render_resilience.py`：
  - 使用自定义 DummyPolicy，`minutes` 恒 True；
  - `render_draft` 失败兜底路径不受影响。
- `tests/meeting/test_minutes_styles.py`：
  - 使用自定义 mock policy，不受影响。
- `tests/unit/meeting/test_agenda_objective_boundary.py:114`：
  - 只构造 `templates` 状态，不调用 `produce_line`；
  - 不受影响。
- `tests/unit/core/templates/test_column_projection.py:531`：
  - 传入模板正文，不是模板名；
  - 新旧行为都是 True。
- `tests/meeting/test_meeting_memory.py`：
  - `# 个人视角纪要` 只用于 HTML 渲染断言，不走 `uses_llm_render`；
  - 不受影响。

建议实施前再跑一次：

```bash
grep -rn 'uses_llm_render\|"general_minutes"\|"personal_minutes"' tests --include=*.py
```

确认没有遗漏。

---

## 6. 文档改动

### 6.1 `OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md`

#### 5.6 默认模板渲染路径

- 标记“默认模板纯 Python”方案**不采用**；
- 写明：
  - 默认模板 `general_minutes` / `personal_minutes` 也走 LLM；
  - `render_draft` 仅做无模板/失败兜底；
  - `uses_llm_render` 删除默认模板特判。

#### 10.2 待决策问题

将：

```text
2. 默认 general_minutes / personal_minutes 是否切纯 Python？
```

改为：

```text
2. 默认模板是否切纯 Python？——已决策：不切。
   - 默认模板也走 LLM；
   - render_draft 仅兜底；
   - 详见 DECISION_MINUTES_DEFAULT_RENDER_MODE.md。
```

#### 5.10 已落地

补充：

```text
- 默认模板渲染模式收口：所有模板走 LLM，render_draft 仅兜底。
- 详见 DECISION_MINUTES_DEFAULT_RENDER_MODE.md。
```

### 6.2 代码注释

- `core/runtime/kinds.py`：删除“默认模板由 render_draft 纯 Python 装配”的注释；
- 改成“if_template：有非空模板 → LLM；无模板/空白 → render_draft 兜底”。

### 6.3 其他文档

建议全局搜索：

```bash
grep -rn "零 LLM\|纯 Python\|general_minutes.*render_draft\|默认模板.*Python" \
  --include=*.md --include=*.py .
```

把仍然暗示“默认模板纯 Python”的旧描述同步掉。

---

## 7. 影响分析

### 7.1 生产 API

**不变**：

- `minutes` 不传模板 → 自动 `general_minutes`；
- 模板正文非空 → LLM 渲染；
- 自定义模板 → LLM；
- 模板为空/解析失败/LLM 失败 → `render_draft`。

### 7.2 测试 / CLI / 内部调用

- 传模板**名**的路径会从“纯 Python”变为“LLM”；
- 这是本决策的预期结果；
- 需要同步更新测试断言；
- CLI 如果依赖默认模板零 LLM，成本/耗时会上升，但 API 本来就不是零 LLM。

### 7.3 功能取舍

- 移除“默认模板零 LLM 快速路径”；
- 保留 `render_draft` 兜底；
- 换来规则统一：有模板就 LLM，无模板/失败才 Python。

### 7.4 后续如果又想要纯 Python

不作为本次范围。若未来重启，需要：

1. 模板身份识别（`TemplateRef` / `is_default`）；
2. 默认模板三栏契约；
3. 独立的契约渲染器；
4. A/B 与开关；
5. 不能直接复用当前 7 栏兜底布局。

---

## 8. 风险与回滚

### 风险

1. 测试/CLI 传模板名的路径行为变化；
2. 有人仍以为默认模板零 LLM；
3. 删除特判后，若未来想恢复纯 Python，需要重新实现；
4. `minutes_styles` / `agenda_minutes` 的 `if_template` 语义也会变成“有模板就 LLM”，
   但它们生产路径传的也是模板正文，实际行为不变。

### 回滚

- 恢复 `uses_llm_render` 的默认模板特判；
- 恢复测试断言；
- 保留 `render_draft` 兜底不变。

生产 API 行为本来不变，回滚成本低。

---

## 9. 验收标准

- [x] `uses_llm_render` 不再包含 `general_minutes` / `personal_minutes` /
      `通用纪要` / `个人视角纪要` / `# 个人视角纪要` 特判；
- [x] `""`、`"   "`、`False` 返回 False；
- [x] 任意非空模板（默认名、自定义名、模板正文）返回 True；
- [x] `test_line_policy_uses_llm_render_routing` 更新并通过；
- [x] `test_produce_line_minutes_no_template_fallback_zero_llm` 改名/改模板并通过；
- [x] `render_draft` 仍可被无模板/失败路径调用；
- [x] `tests/meeting` + `tests/unit/meeting` 全绿；
- [x] `tests/integration/meeting` 全绿；
- [x] `ruff check` 通过；
- [x] `OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md` 已同步；
- [x] 代码中不再出现“默认模板由 render_draft 纯 Python 装配”的表述。

---

## 10. 实施清单

1. [x] 修改 `core/runtime/kinds.py` 的 `uses_llm_render`；
2. [x] 修改 `core/runtime/kinds.py` 注释；
3. [x] 更新 `tests/meeting/test_minutes_fast_render.py` 的两个测试；
4. [x] 更新 `tests/meeting/test_minutes_fast_render.py` 文件头注释；
5. [x] 更新 `OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md` 的 5.6 / 5.10 / 10.2；
6. [x] 全局搜索“默认模板纯 Python / 零 LLM”旧描述；
7. [x] 跑 `ruff check`；
8. [x] 跑 `tests/meeting`、`tests/unit/meeting`、`tests/integration/meeting`；
9. [x] 确认生产 API 行为不变（默认模板仍 LLM）；
10. [x] 确认 `render_draft` 仅作为兜底使用。

---

## 11. 实施结果（2026-10-27）

- `core/runtime/kinds.py` 的 `uses_llm_render` 已简化：
  - 非空字符串模板 → `True`；
  - 空串/空白串 → `False`；
  - 布尔 `True` → `True`，`False` → `False`；
  - 已删除默认模板名/个人模板正文特判。
- `tests/meeting/test_minutes_fast_render.py`：
  - `test_line_policy_uses_llm_render_routing` 断言已更新；
  - `test_produce_line_minutes_fast_path_zero_llm` 已重命名为
    `test_produce_line_minutes_no_template_fallback_zero_llm`，
    模板改为 `""`，测试无模板兜底；
  - 文件头注释已同步。
- `OPTIMIZATION_MINUTES_TEMPLATE_SEPARATION.md`：
  - 5.6 / 5.10 已更新为“默认模板不切纯 Python”；
  - 10.2 已标记为“已决策：不切”。
- 验证结果：
  - `tests/meeting` + `tests/unit/meeting` + `tests/integration/meeting`：
    **331 passed, 9 skipped**；
  - `ruff check`：通过。

---

## 12. 一句话总结

**把 `uses_llm_render` 简化成“有非空模板 → LLM，无模板/空白 → render_draft 兜底”，删除默认模板纯 Python 特判；同步修改两个测试、文件头注释和主优化文档。生产 API 行为不变，测试/CLI 传模板名的路径按新规则走 LLM。**
