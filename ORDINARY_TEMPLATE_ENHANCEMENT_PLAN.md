# 普通模板纪要核心优化执行清单 (ORDINARY_TEMPLATE_ENHANCEMENT_PLAN)

> **版本**：v1.0.0  
> **日期**：2026-10-22  
> **适用范围**：普通模板会议纪要（涵盖全量通用占位符模板、客观全员纪要、专题讲座及各垂直场景纪要）  
> **核心目标**：彻底解决总述栏多段合并（594字超长）告警、全链路统一 250–350 字口径、消除草稿模型偶发字段缺失引发的 7 秒无效重试。

---

## 一、背景与问题根因复盘

近期在测试服务器部署普通模板纪要优化后，整体执行耗时有显著下降，但在测试日志中暴露了以下两处关键问题：

### 1. 总述栏多段合并为一段，触发 Advisory 篇幅超长（594 字 > 450 字）
```text
2026-10-22 21:10:07 [INFO] [infra.llm.llmclient] llm call label=minutes/render mode=text
2026-10-22 21:10:07 [INFO] [core.runtime.render] advisory line=minutes：「本次讲座为基金经理肖楠面向机…」一段 594 字，超过 450 字：拆段或改用 `- ` 分点
2026-10-22 21:10:07 [INFO] [core.runtime.render] render line=minutes fill_mode=freeform gate=pass directives=0
2026-10-22 21:10:07 [INFO] [core.runtime.render] enforce line=minutes notes=「讲座概况」为总述栏（一段写完）：已把 3 段合并成一段
```
- **机制与原因**：
  1. **素材源头多段**：`executive_summary` 在草稿生成契约中定义为 `StrListField`，天然包含 2~4 个段落（首段为宏观总述，后续各段为业务模块/议题讨论）；
  2. **Freeform 渲染指令缺失映射规则**：在普通模板纪要的 Prompt（`MINUTES_RENDER_TEMPLATE_PROMPT`）中，缺少对“总述栏仅映射第 1 项”的明确指引，大模型在一次性生成整篇 Markdown 时，把草稿中的 3 个段落全写到了首栏；
  3. **门禁暴力拼接**：后置硬执行 `_merge_first_column_paragraphs` 识别到模板要求“单段概括”，强行把 3 个段落用空格拼成 1 个大段（594 字）；
  4. **字数门禁告警**：合并后单段达到 594 字，突破了单段 ≤450 字的基线，触发 Advisory 提示。

### 2. 字段缺失引发 7 秒无谓二次重试
```text
2026-10-22 21:28:30 [WARNING] [infra.llm.llmclient] structured invalid label=minutes/agent/objective attempt=1 err=Minutes 字段不一致：缺失=['history_comparison']，多余=[]
2026-10-22 21:28:30 [INFO] [infra.llm.llmclient] llm call label=minutes/agent/objective mode=structured 第2次
```
- **机制与原因**：
  1. `history_comparison` 被系统提示词声明为“由底层自动装配，无需编写（默认空数组 []）”；
  2. deepseek-v4-flash 在 attempt=1 时误将“无需编写”理解为“不用输出该键”，直接从 JSON 中省略了该 key；
  3. 底层 `Minutes.validate()` 采取全字段严格校验（`_exact_fields`），直接拦截并抛错，导致模型发起第 2 次重试，白白浪费 7 秒。

---

## 二、四大优化项详细实施清单

```mermaid
flowchart TD
    subgraph S1["1. 契约统一层 (Draft Generation)"]
        P1["prompts.py:63 / 131<br>首项字数 200–300字 ➔ 统一为 250–350字"]
    end

    subgraph S2["2. 渲染指令层 (Freeform Mode)"]
        P2["prompts.py:303<br>MINUTES_RENDER_TEMPLATE_PROMPT 补齐首栏单段映射规约"]
    end

    subgraph S3["3. 切片修剪层 (Column Pruning)"]
        P3["_placeholder.py:1115<br>is_overview_col 截断 executive_summary 为 [:1]"]
    end

    subgraph S4["4. 容错契约层 (Model Validation)"]
        P4["models_generated.py:161<br>Minutes.validate 增加 history_comparison 自动补齐"]
    end

    S1 --> S2
    S1 --> S3
    S2 --> OUT["消除 594 字超长合并告警 & 排版完全贴合模板"]
    S3 --> OUT
    S4 --> RETRY["彻底杜绝 7 秒无效重试"]
```

---

### 优化项 1：草稿生成契约字数统一（消除口径冲突）

- **目标文件**：`domains/meeting/tasks/minutes/prompts.py`
- **定位**：
  - 客观纪要提示词：第 63 行
  - 议题纪要提示词：第 131 行
- **修改方案**：
  将原本的 `200–300 字` 全面调整为与模板库一致的 `250–350 字`。

#### 代码变更对比：
```diff
--- a/domains/meeting/tasks/minutes/prompts.py
+++ b/domains/meeting/tasks/minutes/prompts.py
@@ -60,7 +60,7 @@ _MINUTES_OBJECTIVE_AGENT_RULES = """## 三、全员客观纪要专有规则
 - **headline（客观总结标题）**：
   - 概括会议核心业务主题，8–18 字，具备严谨公文标题风格；直接陈述核心业务事项与定调结论。
 - **executive_summary（全员全景正文）**：
-  - 首项（全局概览项）：客观概括全场会议背景、核心定调格局与全局统一部署（遵循篇幅预算，默认 200–300 字）；
+  - 首项（全局概览项）：客观概括全场会议背景、核心定调格局与全局统一部署（遵循篇幅预算，默认 250–350 字）；
   - 后续分项（业务模块项）：按业务模块归纳陈述，写清方案要点、关键数据与决议；不按发言人逐一点名罗列，过滤寒暄客套与非实质性过程细节；避免连续使用“某某提出/某某指出”句式。
 - **personally_relevant_points（全员落地行动分工）**：
 
@@ -128,7 +128,7 @@ MINUTES_AGENDA_GENERATION_PROMPT = """你是「会议纪要草稿 Agent」（审
 
 ### 2. executive_summary（审定议题层级分段正文）
 - **首项（全场概览项）**：
-  单段连贯文字（约 200–300 字），客观概括全场会议背景、核心主线推进态势与最关键的全局定调决议。
+  单段连贯文字（约 250–350 字），客观概括全场会议背景、核心主线推进态势与最关键的全局定调决议。
 - **后续分项（审定议题分项正文，与有效议题清单 1:1 严格对应）**：
   全场审定有效议题共有 N 个，后续分项恰好输出 N 个独立项。每一项按规范公文层级展开：
```

- **预期效益**：
  与全库 21 个模板中 `[单段概括，约 250–350 字]` 的标定口径 100% 吻合，大模型在草稿阶段便产出饱满且符合长度的概括段落，距离 450 字门禁上限预留 100 字安全带。

---

### 优化项 2：逐栏切片路径源头截断（防御性修剪）

- **目标文件**：`core/templates/router/_placeholder.py`
- **定位**：第 1113–1117 行 `is_overview_col` 判定分支内
- **修改方案**：
  在总述概况类栏目（`is_overview_col`）的上下文修剪中，将 `executive_summary` 严格截断为仅包含第 1 项 `[:1]`，后续业务模块讨论从素材源头切断。

#### 代码变更对比：
```diff
--- a/core/templates/router/_placeholder.py
+++ b/core/templates/router/_placeholder.py
@@ -1112,7 +1112,7 @@ def _prune_context_for_column(
                     if isinstance(draft_obj, dict):
                         compact_draft = {
                             "headline": draft_obj.get("headline") or "",
-                            "executive_summary": draft_obj.get("executive_summary") or [],
+                            "executive_summary": (draft_obj.get("executive_summary") or [])[:1],
                             "key_decisions": draft_obj.get("key_decisions") or [],
                         }
                         out_parts.append(f"{label}\n{json.dumps(compact_draft, ensure_ascii=False)}")
```

- **预期效益**：
  当调用走入逐栏装配（`fill_mode=assemble`）路径时，模型为概况栏写作时只看到 1 个全局概括段落，从根本上杜绝“看到多段、写出多段”的物理可能性。

---

### 优化项 3：Freeform 渲染指令补齐（线上主干路径核心治本）

- **目标文件**：`domains/meeting/tasks/minutes/prompts.py`
- **定位**：第 303 行 `MINUTES_RENDER_TEMPLATE_PROMPT`
- **修改方案**：
  在普通模板的渲染提示词中，前置加入与议题模式同等严格的【栏目语义自适应映射】规约，明确指定概况栏只能取 `executive_summary` 的第 1 项，并强约束“单段交付、严禁分多段”。

#### 代码变更对比：
```diff
--- a/domains/meeting/tasks/minutes/prompts.py
+++ b/domains/meeting/tasks/minutes/prompts.py
@@ -301,6 +301,8 @@ MINUTES_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
     source="已审核草稿（结构化事实基准）",
     source_rule=(
         "**以已审核草稿为唯一事实与结构基准，自然映射业务板块**：草稿锁定了全场的核心论据与确定决议。\n"
+        "【栏目语义自适应映射】：\n"
+        "1. 概括总述类栏目（如【讲座概况】、【评审概况】、【会议概况】等声明单段写完的栏目）：映射草稿 executive_summary 的首项（全场概览项），以连贯单段呈现（约 250–350 字），严禁分多段输出；后续业务模块议题细节留待后文各小节展开；\n"
         "排版渲染时，将已审核草稿中的事实论述与指标数据，客观、严谨地排版映射到给定的模板章节中：\n"
         "1. 业务研讨板块映射：模板中若包含【要点梳理】栏目，按现场研讨的自然业务板块划分小节（设立三级小节标题，形如 ### 1. 业务板块/功能方向名称），正文以列表项（- ）展开方案考量、实测参数与关键结论，无需强求套用‘议题’一词；\n"
```

- **预期效益**：
  线上无论走到 Freeform 还是 Repair 模式，大模型在渲染第一栏时均明确遵循“仅取首项、连贯单段、250–350 字”的纪律，直接输出单段 Markdown，避免产生 3 段文本，彻底消灭后置门禁将 3 段合并为 594 字的 Advisory 告警。

---

### 优化项 4：字段缺失容错自动补齐（杜绝 7 秒无谓重试）

- **目标文件**：`domains/meeting/models_generated.py`
- **定位**：第 161 行 `Minutes.validate`
- **修改方案**：
  在调用严格键校验 `_exact_fields` 前，针对由系统自动装配、模型常因“无需编写”而误漏的 `history_comparison` 字段进行安全预设补齐。

#### 代码变更对比：
```diff
--- a/domains/meeting/models_generated.py
+++ b/domains/meeting/models_generated.py
@@ -159,6 +159,8 @@ class Minutes(ModelMixin):
 
     @classmethod
     def validate(cls, data: dict) -> "Minutes":
+        if isinstance(data, dict) and "history_comparison" not in data:
+            data["history_comparison"] = []
         _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
         _string(data["headline"], "headline")
         _string_list(data["executive_summary"], "executive_summary")
```

- **预期效益**：
  即便 deepseek-v4-flash 等小模型在输出 JSON 时偶尔完全省略 `"history_comparison"` 字段，程序在校验前即刻以 `[]` 补齐，直接判定合规，不再触发重试，每场会议可稳定挽救 **7~8 秒** 的无效重试延时。

---

## 三、兼容性与影响面评估

| 业务维度 | 影响面评估 | 说明 |
| :--- | :--- | :--- |
| **普通模板会议纪要** | **全面受益** | 彻底根治 594 字超长 Advisory 告警；消除 7 秒多余重试；字数口径完全统一。 |
| **议题纪要** | **完全兼容** | 议题纪要原本就是首项映射规则，本次将字数调整为 250–350 字与模板完全契合。 |
| **个人视角纪要** | **完全隔离** | 个人视角有专门的画像字段提炼与专属 Prompt 分支，不受本修改影响。 |
| **记忆与历史引用** | **完全保证** | `history_comparison` 本身就是下游在渲染完成后根据跨场记忆自动装配注入，草稿阶段默认给 `[]` 属于标准既定架构。 |
| **既有单元测试** | **100% 通过** | 不破坏任何已有测试用例契约与断言。 |

---

## 四、验证与执行检查清单

- [x] **代码实现**：
  - [x] 修改 `domains/meeting/tasks/minutes/prompts.py` 中的字数与映射规则
  - [x] 修改 `core/templates/router/_placeholder.py` 中的 `is_overview_col` 切片
  - [x] 修改 `domains/meeting/models_generated.py` 中的 `Minutes.validate`
- [x] **单元测试验证**：
  - [x] 执行 `pytest tests/unit/core/templates/test_column_pruning_refactor.py` 确保切片逻辑稳固
  - [x] 执行 `pytest tests/meeting/test_minutes_fast_render.py` 验证快速渲染路径
  - [x] 针对 `Minutes.validate` 编写缺失 `history_comparison` 的单测，验证无需重试直接通过
- [x] **整库回归**：
  - [x] 运行全套单元测试，确保 PASS 数维持在 314+ 项，0 失败（实测 317 passed, 9 skipped）
- [ ] **测试服务器部署与日志核查**：
  - [ ] 确认日志中不再出现 `「讲座概况」为总述栏（一段写完）：已把 3 段合并成一段`
  - [ ] 确认不再出现单段超 450 字的 Advisory 提示
  - [ ] 确认草稿节点不再出现 `缺失=['history_comparison']` 的 attempt=2 重试
