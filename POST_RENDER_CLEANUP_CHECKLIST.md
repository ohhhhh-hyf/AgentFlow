# 后处理 LLM 冗余调用拔除与纯程序化规整改造清单

> **文档定位**：针对会议纪要（普通纪要、个人视角、议题纪要双模式、模板纪要）在渲染 Agent 吐出正文后，彻底拔除后处理阶段的 LLM 阻塞重写与暴力硬截断，全面收敛为毫秒级纯 Python/正则确定性规整（Deterministic Pipeline）。

---

## 一、改造背景与核心目标

### 1. 现状痛点
1. **流式与 Done 体验割裂**：
   - 客户端已通过 SSE 流式块（`chunk` 事件）逐字接收完渲染 Agent 产出的 Markdown。
   - 渲染结束后，若正文偏长或命中门禁警告，后处理会再次唤醒 LLM 发起 1~2 轮全篇重写，耗时额外增加 **15~35 秒**；
   - 任务结束时推送的 `done` 事件（携带全量文本）会突然将用户刚刚在打字机看完的内容篡改/缩水，造成强烈的视觉跳变与认知割裂。
2. **防御机制过时（与现代模型能力不匹配）**：
   - 当前的“篇幅压缩重写（`_COMPRESS_REVISION`）”与“门禁返工修复（`_GATE_REPAIR`）”是历史早期模型（遵循力差、容易漏栏目/死循环）遗留的多层防御措施。
   - 现代前沿模型配合上游的草稿审查（Draft + Supervisor）以及严格的前置【篇幅预算】与层级格式 Prompt，结构崩溃率极低。这两处后处理 LLM 调用平时极少触发，一旦偶发触发却带来巨大的延迟惩罚和降级风险。
3. **文意生硬破坏**：
   - 门禁未通过时的兜底硬截断（`truncate_to_budget`）直接按标点或字符硬切，经常导致文末议题被腰斩或半句话丢失，破坏了纪要的严肃性与完整性。

### 2. 改造目标
* **拔除后处理阶段全部 LLM 调用**：渲染 Agent 产出后，LLM 调用次数严格为 **0**。
* **保留并强化纯程序性逻辑（Deterministic Pipeline）**：利用正则与纯 Python 算法在 **<5ms** 内完成格式粘连修复、代码围栏剥离、标题括号清洗、单段超长拆分等操作。
* **流式与最终产物高度一致**：保证客户端流式看到的内容与最终落盘/全量刷新的内容在语义层面 100% 一致。
* **后处理延迟断崖式下降**：将后处理总耗时从“最坏情况下 20~40 秒”彻底收敛到“稳定 <10 毫秒”。

---

## 二、架构对比：改造前 vs 改造后

```
【改造前】
Render.stream() 产出 full_text
    │
    ├──> [LLM 调用 1] han > hi_i ? ──> _COMPRESS_REVISION (最多 2 轮 LLM，耗时 15~30s)
    │
    ├──> gate_render_output() 纯 Python 门禁检查
    │
    ├──> [LLM 调用 2] repair_issues ? ──> _GATE_REPAIR / _KEEP_COMPRESSING (最多 2 轮 LLM，耗时 15~30s)
    │                                └──> 超限仍未解决 ──> truncate_to_budget (暴力截断文本)
    │
    └──> 记忆注入 & 纯文本收尾 & 落盘

─────────────────────────────────────────────────────────────────────────────

【改造后 (纯程序化管线)】
Render.stream() 产出 full_text
    │
    ├──> [纯代码] 篇幅预算校验 ──> 若超出上限，仅打 Advisory 监控日志，不阻断、不调 LLM
    │
    ├──> [纯代码] gate_render_output() ──> 执行 enforce_render_output (毫秒级确定性清洗):
    │         ├── 1. 剥离外层代码围栏与字数元说明
    │         ├── 2. 修复 Markdown 表格行粘连与列名粘连
    │         ├── 3. 清除标题多余方括号 (## [栏名] -> ## 栏名)
    │         ├── 4. 修复孤立光杆标题
    │         ├── 5. 超过 400 字的单段按句号自然换行拆分 (保全全部事实)
    │         └── 6. 剔除全缺省占位行
    │
    ├──> [纯代码] 门禁状态审计 ──> 记录 gate_ok 与 issues 到元数据，若不合规打 quality_warning，绝不截断正文
    │
    └──> [纯代码] 记忆注入 & 纯文本收尾 & 落盘 (总耗时 < 10ms)
```

---

## 三、待改造模块与详细执行清单

### 任务 1：拔除篇幅预算二次 LLM 压缩循环
* **目标文件**：`core/runtime/render.py`
* **影响代码行**：约 L544 ~ L609
* **改造动作**：
  1. 删除调用 `_render_run(render, ... _COMPRESS_REVISION ...)` 的循环逻辑；
  2. 删除未使用的提示词常量 `_COMPRESS_REVISION`；
  3. 保留篇幅计算与预算对比逻辑，当正文字数超出预算上限时，仅将其作为 `advisory` 咨询建议记入日志和任务元数据（`line_state["render_advisory_issues"]`），用于监控大盘统计，不发起任何重写。

### 任务 2：拔除门禁修复二次 LLM 重写与暴力硬截断
* **目标文件**：`core/runtime/render.py`
* **影响代码行**：约 L648 ~ L746
* **改造动作**：
  1. 删除调用 `_render_run(render, ... _GATE_REPAIR ...)` 与 `_KEEP_COMPRESSING` 的两轮重写循环；
  2. 删除未使用的提示词常量 `_GATE_REPAIR`、`_OVERLONG_COMPRESS`、`_OVERLONG_SECTION`、`_KEEP_COMPRESSING`；
  3. 彻底删除最后的 `truncate_to_budget(full_text, int(compress_hi))` 暴力硬截断逻辑，坚决防止文章尾部被生硬切断；
  4. 保持 `gate_render_output` 的调用，获取 `gate["text"]`、`gate["notes"]` 和 `gate["issues"]`；
  5. 若 `gate_ok is False` 或存在 `hard_issues`，按既定机制设置 `line_state["render_gate_ok"] = False` 并记录 `line_state["quality_warning"]`，以透明标识代替阻塞返工。

### 任务 3：巩固并强化纯程序性清洗（Deterministic Pipeline）
* **目标文件**：`core/execution/hard_execution.py`（经由 `core/execution/gate.py`）
* **确保纯代码清洗完整生效**：
  - [x] 表格粘连修复：`fix_glued_table_rows`
  - [x] 标题方括号去除：`strip_bracketed_column_headings`
  - [x] 代码围栏剥离：`strip_outer_markdown_fence`
  - [x] 字数元说明剔除：`strip_char_budget_meta`
  - [x] 首栏总述多段合并：`_merge_first_column_paragraphs`
  - [x] 超长单段优雅换行：`split_overlong_paragraphs`（按句号拆分段落，不丢失字词）
  - [x] 纯缺省词过滤：`strip_default_only_content`
* **补充清洗项（如需）**：
  - 检查并补全可能未闭合的 Markdown 加粗标记 `**` 或行尾多余的空白符。

### 任务 4：状态标记与透传一致性收敛
* **目标文件**：`core/runtime/render.py`
* **改造动作**：
  1. `fill_mode` 统一为标准状态（流式直出为 `"freeform"`，重试直出为 `"retry_success"`，纯代码降级为 `"deterministic_draft"`），不再流转为 `"repair"`；
  2. 确保 `line_state["rendered"] = full_text` 与 `app/tasks.py` 消费的 `md_text` 保持权威同步；
  3. 确保 Done 事件 payload 结构完整，指标监控中的 `cost_time` 与 `token_usage` 真实反映优化收益。

### 任务 5：自动化回归与全链路测试验证
* **测试用例集**：
  1. 运行 `tests/integration/meeting/minutes/render/test_fast_render.py`：确保流式直出无冗余 LLM 调用；
  2. 运行 `tests/integration/meeting/minutes_styles/test_styles.py`：确保 brief 与 topic 等各模板模式在长短文本下均 0 次多余调用；
  3. 运行 `tests/integration/meeting/test_render_resilience.py`：确保渲染异常降级安全线完好；
  4. 运行 `tests/unit/core/templates/test_template_gate.py`：验证静态门禁与清洗逻辑正确生效。

---

## 四、关键指标预期改善

| 评估维度 | 改造前（现有现状） | 改造后（预期表现） | 收益分析 |
| :--- | :--- | :--- | :--- |
| **后处理 LLM 调用次数** | 0 ~ 4 次（篇幅超限 2 轮 + 门禁修复 2 轮） | **恒为 0 次** | 彻底拔除不确定性开销 |
| **流式结束后等待耗时** | 典型值 10ms，超限触发时 **15s ~ 40s** | **稳定在 2ms ~ 8ms** | 用户感知几乎即刻完成 |
| **后处理 Token 消耗** | 触发时额外消耗 2000 ~ 8000 Tokens | **恒为 0 Token** | 显著降低 API 账单成本 |
| **内容呈现一致性** | 触发压缩时，Done 事件与打字机输出产生**剧烈替换差异** | **100% 语义一致**（仅纯标点格式规整） | 彻底解决视觉与内容割裂 |
| **正文末尾完整度** | 存在被 `truncate_to_budget` 生硬截断的风险 | **永不截断**，保持事实原貌与闭环 | 杜绝虎头蛇尾与断句现象 |

---

## 五、实施落地确认

- [ ] 清单与方案已评审
- [ ] 待用户确认后启动代码改造
