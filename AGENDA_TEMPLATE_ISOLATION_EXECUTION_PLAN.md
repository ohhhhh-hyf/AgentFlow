# 基于独立目录隔离的议题模板纪要执行清单 (AGENDA_TEMPLATE_ISOLATION_EXECUTION_PLAN)

> **版本**：v1.0  
> **核心原则**：
> 1. **物理目录绝对隔离**：原有的 `resources/templates/` 目录 **100% 保持现状、一字不改、文件不动**；
> 2. **新建专属模板库**：新建 `resources/agenda_templates/` 目录，专门存放按议题结构化输出的场景模板；
> 3. **精准就近加载与平滑回退**：
>    - 触发议程增强纪要时（`line == "minutes"` 且有效议题 $\ge 1$），**优先检索 `resources/agenda_templates/`**；
>    - 若新目录下存在对应模板（如 `general_minutes.md`），立即采用；若新目录尚未定制该模板，**自动平滑回退至原 `resources/templates/`**；
>    - 常规纪要（无 docs 或非议程 docs）时，**100% 仅访问原 `resources/templates/`**。
> 4. **双重锁死闭环**：通过新模板内部的强负向约束占位符 + 渲染文末的排版命名执行令，彻底杜绝大模型“自行总结生造小标题”的顽疾。

---

## 目录
- [一、背景与痛点诊断](#一背景与痛点诊断)
- [二、新模板目录结构与优化版通用纪要设计](#二新模板目录结构与优化版通用纪要设计)
- [三、模板解析器自适应分流路由实现方案](#三模板解析器自适应分流路由实现方案)
- [四、编排层与渲染执行令尾部锁死设计](#四编排层与渲染执行令尾部锁死设计)
- [五、端到端四种场景加载行为矩阵](#五端到端四种场景加载行为矩阵)
- [六、分步可执行任务落地清单](#六分步可执行任务落地清单)

---

## 一、背景与痛点诊断

在实际测试中发现：即使上游已经把议题切片与打标原文整理完毕，若不对模板占位符和渲染 Prompt 进行强力约束，大模型依然会**“自作主张、自行归纳很多内容作为抽象小标题”**（例如自己发明 `### 业务背景分析`、`### 核心技术挑战`，而不用现场真实的议题名称）。

### 根因剖析：
1. **原模板包含诱发发散的词汇**：原模板顶部的 `采用议题聚类与结构化分节展开事实`，被大模型误读为“要对会议散落内容进行概念聚类（Topic Clustering）”；
2. **原模板占位符缺乏强负向禁令**：原占位符只写了“按议题设立小节标题 ### 议题名称”，没有明确禁止“严禁自行归纳生造概念小标题”；
3. **老模板不能随意修改**：如果直接改动现有的 `resources/templates/general_minutes.md`，可能会对无议程的普通随性会议造成不可预期的排版干扰。

因此，**建立全新的 `resources/agenda_templates/` 目录进行物理隔离与自适应路由分发，是兼顾历史稳定与议题强约束的最佳工程实践！**

---

## 二、新模板目录结构与优化版通用纪要设计

### 1. 目录结构
```text
resources/
├── profiles/
├── styles/
├── templates/                 <-- 原有目录 100% 保持不动（包含原版 general_minutes.md 等 32 个模板）
└── agenda_templates/          <-- 【新建独立目录】专供议题增强纪要模板
    └── general_minutes.md     <-- 【新建】专属优化的通用纪要模板
```

### 2. 优化版 `resources/agenda_templates/general_minutes.md` 源码内容
```markdown
# 通用纪要

<!-- requirement
客观全面呈现会议核心内容与决策，语气为严谨客观的公文陈述；以现场实质研讨议题为主线结构化分节展开事实，突出关键数据依据、各方立场与决策定调，严禁生造抽象空泛的业务小标题，篇幅充分饱满，信息密度高。
-->

## [全文摘要]
[单段概览，约 250–350 字：全面概述会议背景、主要参会方、涵盖的核心议题业务主线以及全场拍板的最关键决议；开门见山总揽全场宏观态势，具体细节论据归入 [要点梳理]，本栏严禁铺开分项展开。]

## [要点梳理]
[必须严格以会议实质议题为主线设立小节标题 ### 议题名称（若素材提供了审定议题清单，小节标题必须与清单中的议题全称一字不差对齐，按顺序依次展开，严禁自行总结生造小节标题，严禁遗漏任何议题）：各议题下以 - 逐项列出具体方案考量、事实论据、技术参数与明确要求；条数随现场实际讨论充分展开。]

## [结论与决定]
[聚焦会议最终形成的拍板定调、裁决方案，或各方达成的主流倾向共识与推进基调：分点写明决议或共识陈述、决策主体与落地要求（若全场无决议或共识内容则本栏整体不予呈现）。]
```

### 3. 三大关键优化点解读：
1. **剔除“议题聚类”**：消除模型自主聚类生造抽象标题的冲动；
2. **首栏单段锁死**：开门见山总揽大盘，严禁在第一栏分项罗列细节，避免与第二栏撞车；
3. **二栏强行对齐**：方括号内硬编码白纸黑字：**“小节标题必须与清单中的议题全称一字不差对齐，按顺序依次展开，严禁自行总结生造小节标题，严禁遗漏任何议题”**。

---

## 三、模板解析器自适应分流路由实现方案

### 1. 配置层支持（`app/config.py`）
新增议程模板目录识别与优先解析接口：

```python
# app/config.py

def agenda_template_dir() -> Path:
    """按议题输出纪要的专属模板目录（resources/agenda_templates/）。"""
    return PROJECT_ROOT / "resources" / "agenda_templates"

def resolve_agenda_template_format(template_value: str) -> str:
    """优先从 agenda_templates/ 加载模板；若不存在则自动回退至普通模板目录。"""
    value = (template_value or "").strip()
    if not value:
        return ""
    # 提取模板 ID（如 general_minutes）
    t_id = value.replace(".md", "").strip()
    agenda_file = agenda_template_dir() / f"{t_id}.md"
    if agenda_file.is_file():
        item = _parse_template_md(agenda_file)
        if item:
            fmt = str(item.get("format") or "").strip()
            req = str(item.get("requirement") or "").strip()
            from core.templates.router._base import wrap_template_requirement
            return wrap_template_requirement(fmt, req)
    
    # 平滑回退：若 agenda_templates 尚未定制该模板，回退至原有注册表
    return resolve_template_format(value)
```

### 2. 任务入口自适应分发（`app/tasks.py`）
在 `_template_file` 中增加 `is_agenda_enhanced` 参数：

```python
# app/tasks.py - _template_file
def _template_file(
    domain: str,
    line: str,
    template_value: str,
    profile_value: str = "",
    style_value: str = "",
    is_agenda_enhanced: bool = False,  # <-- 新增参数
) -> Path | None:
    ...
    # 解析模板格式内容：若命中议程增强，优先走专属议程模板解析
    if is_agenda_enhanced:
        fmt = resolve_agenda_template_format(value)
    else:
        fmt = resolve_template_format(value)
    ...
```

在 `app/tasks.py` 的调用处（约 750 行）：
```python
    template_path = _template_file(
        domain,
        line,
        extra.template,
        profile_value=extra.profile,
        style_value=extra.style,
        is_agenda_enhanced=bool(extra_line_inputs.get("agenda_text")),  # 依据是否有有效议程自适应分流
    )
```

---

## 四、编排层与渲染执行令尾部锁死设计

### 1. 尾部排版命名纪律注入（[domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py)）
在 `_render_context` 中，当 `has_valid_agenda` 为 True 时，在业务素材区除了提供审定议题清单外，追加一条**最终执行令**，利用大模型的临近效应（Recency Bias）彻底锁死命名：

```python
# domains/meeting/orchestrator.py - _render_context
if line_name == "minutes" and state.get("has_valid_agenda"):
    agendas = state.get("valid_agendas") or []
    if agendas:
        agenda_checklist = "\n".join(
            f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
            for i, a in enumerate(agendas)
        )
        directive_block = (
            f"【现场审定的有效议题清单（必须且仅按此结构与顺序展开）】：\n{agenda_checklist}\n\n"
            f"【排版与小节命名纪律】：\n"
            f"正文 [要点梳理] 栏目必须严格以且仅以本清单中的议题全称作为 ### 小节标题（100% 逐字对应，一字不差），"
            f"严禁自行合并、缩写或总结生造任何抽象小标题！"
        )
        extra_parts.append(directive_block)
```

---

## 五、端到端四种场景加载行为矩阵

| 场景 | 任务参数与输入 | 模板加载路径 | 执行效果 |
| :--- | :--- | :--- | :--- |
| **场景 A：议程增强纪要（已适配模板）** | `minutes` + docs包含议程单 + `general_minutes` | `resources/agenda_templates/general_minutes.md` | 严格按有效议题清单输出各 `### 议题名称` 小节，标题 100% 对齐 |
| **场景 B：议程增强纪要（未单独适配的新模板）** | `minutes` + docs包含议程单 + 某冷门模板 `xyz.md` | 平滑回退至 `resources/templates/xyz.md` | 新目录没有自动回退旧目录，零 400 报错，系统极度稳健 |
| **场景 C：常规纪要（传了非议程参考资料）** | `minutes` + docs包含财务报表（有效议题<1） | `resources/templates/general_minutes.md` | 100% 走旧目录旧模板，参考资料正常并入转写，零干扰 |
| **场景 D：常规纪要（无 docs）** | `minutes` + 无 docs | `resources/templates/general_minutes.md` | 100% 走旧目录旧模板，完全保持现有常规公文样式 |

---

## 六、分步可执行任务落地清单

| 任务步骤 | 涉及操作与文件 | 预期结果与落地标准 |
| :--- | :--- | :--- |
| **步骤 1：新建独立模板目录与文件** | 1. 创建目录 `resources/agenda_templates/`<br>2. 新建文件 `resources/agenda_templates/general_minutes.md` | 放入去除“议题聚类”、强化标题逐字对齐的优化版通用纪要。 |
| **步骤 2：配置层实现自适应模板解析** | 在 [app/config.py](file:///D:/study/demo/app/config.py) 中实现 `agenda_template_dir()` 与 `resolve_agenda_template_format()`。 | 支持新目录优先读取与平滑回退，单测验证解析正确。 |
| **步骤 3：入口层参数联动** | 在 [app/tasks.py](file:///D:/study/demo/app/tasks.py) 的 `_template_file` 接入 `is_agenda_enhanced` 标记。 | 当 `extra_line_inputs` 存在 `agenda_text` 时自动激活新目录。 |
| **步骤 4：编排层强化尾部执行令** | 在 [domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py) 的 `_render_context` 追加标题逐字对齐的强执行令。 | 形成“模板内要求 + 渲染文末执行令”双重锁死闭环。 |
| **步骤 5：单元测试与防回归验证** | 1. 在 `tests/unit/meeting/test_minutes_agenda_integration.py` 补充模板自适应路由单测；<br>2. 运行 `pytest tests/unit/meeting/`。 | 验证新模板加载正常、回退机制正常、全量测试 100% 通过。 |

---

> **清单结论**：通过建立独立的 `resources/agenda_templates/` 目录，不仅完好保留了原版模板目录的纯粹性与历史兼容性，更让议题专属模板拥有了独立的进化空间。此方案思路清晰，完全隔离，随时可开始落地。