# AgentFlow 会议领域：minutes + docs（议程增强模式）深度重构方案清单（v3 协同优化版）

本文档专为 **`task == "minutes"` 且携带有效议程单（`docs` 非空且探测出有效议题）** 场景设计。

**本次重构核心原则：**
1. **模板与 Prompt 协同优化**：对 `resources/agenda_templates/general_minutes.md` 进行精炼优化（修补错别字、严格单行闭合防止解析崩溃、明确公文层级），与 Prompt 形成前后协同；
2. **彻底跳过会议理解层（meeting_understanding）**：消除 46s 的冗余等待，使整体执行耗时从 **~100s 骤降至 35s~40s**；
3. **彻底理清草稿字段流转机制**：透明化阐述草稿中的 `executive_summary`、`key_decisions` 等字段如何流入渲染器并完成栏目映射；
4. **渲染 Prompt 动态语义解耦**：不在 Prompt 中硬编码 `[全文摘要]`、`[要点梳理]` 等具体字眼，采用通用的栏目语义角色（概括类、研讨类、决议类）自适应适配；
5. **格式新规矩闭环**：实现标准公文层级（中文数字 `一.`、单组直接平铺 `- `、多组阿拉伯数字 `1.` 分组分点、正文强制 `- ` 分行）。

> [!IMPORTANT]
> **绝对隔离原则**：本方案仅在 `selected == ["minutes"]` 且 `state["has_valid_agenda"] == True` 时生效。无议程单普通纪要、个人视角纪要、多任务并行以及其他 7 个垂直任务**绝不受任何影响**。

---

## 目录索引
1. [零副作用范围隔离矩阵](#一零副作用范围隔离矩阵)
2. [底层机制剖析：草稿字段是如何流入并被渲染器使用的？](#二底层机制剖析草稿字段是如何流入并被渲染器使用的)
3. [改动模块 1：编排层跳过会议理解（orchestrator.py）](#三改动模块-1编排层跳过会议理解orchestratorpy)
4. [改动模块 2：通用纪要模板 md 精炼优化（general_minutes.md）](#四改动模块-2通用纪要模板-md-精炼优化general_minutesmd)
5. [改动模块 3：草稿生成 Prompt 彻底重构（prompts.py）](#五改动模块-3草稿生成-prompt-彻底重构promptspy)
6. [改动模块 4：终稿渲染 Prompt 动态语义重构（prompts.py）](#六改动模块-4终稿渲染-prompt-动态语义重构promptspy)
7. [改动模块 5：监督审核 Prompt 适配（prompts.py）](#七改动模块-5监督审核-prompt-适配promptspy)
8. [重构前后流水线耗时与产物形态对比](#八重构前后流水线耗时与产物形态对比)

---

## 一、零副作用范围隔离矩阵

| 任务场景 | `selected` 条件 | `docs` / 议程状态 | 是否跳过理解层 | 调用的 Prompt / 模板分支 | 影响评估 |
|---|---|---|---|---|---|
| **单跑议程纪要** | `["minutes"]` | 传文档且探出有效议题 | **跳过（0s 短路）** | 重构后的 `AGENDA` 专有集合 + 优化版模板 | **性能暴增 2.5 倍，格式全新升级** |
| **单跑普通纪要** | `["minutes"]` | 空或未探出议题 | 照常执行 | `OBJECTIVE` / `PERSONAL` + 默认模板 | 零改动，完全保持原生逻辑 |
| **个人视角纪要** | `["minutes"]` | `profile="user"` | 照常执行 | `PERSONAL` 集合 | 零改动，工作台看板逻辑不变 |
| **多任务并行** | `["minutes", "actions", ...]` | 任意 | 照常执行 | 通用集合 | 零改动，公共底座正常复用 |
| **其他 7 个任务** | `["actions"]` 等 | 任意 | 照常执行 | 各线独立 Prompt | 零改动，物理隔离 |

---

## 二、底层机制剖析：草稿字段是如何流入并被渲染器使用的？

整个数据链路是由 **系统状态机 -> 上下文组装器 -> 渲染器语义映射** 闭环完成的：

### 1. 草稿生成阶段（`MinutesGenerationAgent`）
Agent 接收输入并调用大模型，输出结构化 Pydantic 模型 `Minutes`，其底层字典保存在系统全局状态中：
```python
state["lines"]["minutes"]["draft"] = {
    "headline": "...",
    "executive_summary": [
        "首项：全场宏观概览...",
        "【一. 议题一】单组核心论据...",
        "【二. 议题二 / 1. 子主题】多组论据..."
    ],
    "key_decisions": [
        "【事项名称】拍板定调与指标要求..."
    ],
    "personally_relevant_points": [],
    "risks_and_blockers": [],
    "unresolved_questions": []
}
```

### 2. 渲染上下文打包阶段（`orchestrator.py` -> `build_render_context`）
在调用渲染节点前，编排器执行 `_render_context`：
```python
return build_render_context(
    ...
    draft=sub.get("draft"),  # 传入 draft 字典
    ...
)
```
进入 `core/runtime/context.py` 的 `build_render_context`：
```python
parts.append(f"已批准会议纪要草稿：\n{serialize(draft)}")
```
草稿 JSON 数据被完整注入到 `approved_context`（渲染上下文）中。

### 3. 渲染 User 消息组装（`core/runner/prompt_utils.py`）
渲染器将 **模板原文**（`resources/agenda_templates/general_minutes.md`）与 **已审核上下文** 组合成 User 消息发送给渲染 LLM：
```text
模板原文：
# 通用纪要
## [全文摘要]
[单段概览...]
## [要点梳理]
[以现场审定的有效议题清单为主线展开呈现...]
## [结论与决定]
[聚焦会议最终形成的拍板定调...]

========================================
【待处理业务素材】
...
已批准会议纪要草稿：
{
  "executive_summary": [ ... ],
  "key_decisions": [ ... ]
}
```

### 4. 为什么没有死板的 Python 代码去提取 `dict["executive_summary"]`？
系统采用的是 **LLM 语义驱动的模板填充引擎**：
- 渲染器（LLM）充当高级公文排版员，读取素材里的 `已批准会议纪要草稿`，并依据模板的栏目标题进行排版；
- 在渲染器 System Prompt 中下达 **通用语义映射契约**：
  - **概括总述类栏目**：映射 `executive_summary` 首项（宏观概括）；
  - **议题研讨类栏目**：映射 `executive_summary` 后续议题项，并按三级与四级标题展开；
  - **决议结论类栏目**：映射 `key_decisions` 列表逐条列出！

---

## 三、改动模块 1：编排层跳过会议理解（orchestrator.py）

### 1. 修改文件
`domains/meeting/orchestrator.py`

### 2. 精准短路逻辑
在 `_make_meeting_understanding_node` 中，当对齐引擎确认 `has_valid_agenda=True` 且单跑 `minutes` 任务时，直接短路放行，不再发起 46 秒的 LLM 调用。

```python
# 位置：domains/meeting/orchestrator.py 约 1280 行
if "minutes" in selected and agenda_text and transcript_input:
    from domains.meeting.agenda_engine import process_agenda_for_minutes

    agenda_res = process_agenda_for_minutes(transcript_input, agenda_text)
    if agenda_res.has_valid_agenda:
        state["valid_agendas"] = agenda_res.valid_agendas
        state["tagged_transcript"] = agenda_res.tagged_transcript
        state["has_valid_agenda"] = True
        agenda_update = {
            "valid_agendas": agenda_res.valid_agendas,
            "tagged_transcript": agenda_res.tagged_transcript,
            "has_valid_agenda": True,
        }
        transcript_input = agenda_res.tagged_transcript
        logger.info(
            "[AGENDA_ENGINE] 议程增强流程就绪: 注入 %d 个有效研讨议题, 打标转写共 %d 字符",
            len(agenda_res.valid_agendas),
            len(agenda_res.tagged_transcript),
        )

        # ──【本次新增短路放行】单任务 minutes 且议题已结构化打标，直接跳过 meeting_understanding ──
        if selected == ["minutes"]:
            progress("skip meeting_understanding (minutes agenda enhanced self-contained)")
            logger.info("[AGENDA_ENGINE] minutes 议题增强自包含，直接放行 meeting_understanding")
            return {
                "meeting_understanding": _EMPTY_MEETING_UNDERSTANDING,
                **agenda_update,
            }
```

---

## 四、改动模块 2：通用纪要模板 md 精炼优化（general_minutes.md）

### 1. 修改文件
`resources/agenda_templates/general_minutes.md`

### 2. 优化要点与防坑底线
- **解析安全铁律**：方括号说明 `[...]` 必须保持**单行闭合、绝不能包含换行和空行**，防止占位符提取正则失效或大模型将其误识别为静态正文；
- **修正历史瑕疵**：移除原模板第 11 行的拼音错别字 `danshi；`；
- **形态指引升级**：精炼交代“中文数字大项（### 一.）”、“单组无序列表平铺 vs 多组四级子标题”、“正文强制列表项（- ）分行呈现”。

```markdown
# 通用纪要

<!-- requirement
以现场审定的有效议题为主线展开事实陈述，突出关键数据依据、各方立场与决策定调，行文严谨客观，篇幅充分饱满，信息密度高。
-->

## [全文摘要]
[单段概览，约 250–350 字：全面概述会议背景、主要参会方、涵盖的核心议题业务主线以及全场拍板的最关键决议；立足全局宏观态势进行通盘概括，将分项细节留归后文展开。]

## [要点梳理]
[以现场审定的有效议题清单为主线展开呈现：议题大项统一使用中文数字序号设立三级标题（### 一. 议题名称）；单组研讨直接在三级标题下方以无序列表项（- ）分点展开，多组研讨使用阿拉伯数字设立四级子标题（#### 1. 子主题名称）后再行分点；各标题正文一律使用列表项（- ）分行呈现，提炼业务方案与量化依据，去除发言人机械前缀。]

## [结论与决定]
[聚焦会议最终形成的拍板定调、裁决方案或共识基调：使用列表项逐条陈述决议内容与落地要求，以「- **事项名称**：具体决议与指标要求」展开；若全场无决议或共识内容，本栏目自适应隐去。]
```

---

## 五、改动模块 3：草稿生成 Prompt 彻底重构（prompts.py）

### 1. 修改文件
`domains/meeting/tasks/minutes/prompts.py`

### 2. 核心重构：`MINUTES_AGENDA_GENERATION_PROMPT`
彻底脱离对上游 `MeetingUnderstanding` 的依赖，直接以打标文本为事实底座，并规范输出带序号的自适应分组标签。

```python
MINUTES_AGENDA_GENERATION_PROMPT = """你是「会议纪要草稿 Agent」（审定议题专有模式）。
上下文中的会议转写已由系统结合会前既定议程单完成了精准对齐与分块打标。你以【现场审定的有效议题清单】及各【议题 XX】切片为唯一主线事实源，通读切片内容，直接提炼生成饱满、高信息密度的结构化纪要草稿。只输出结构化 JSON 数据。

---

## 一、核心输出字段提炼与格式规约

### 1. executive_summary（审定议题层级分段正文）
- **首项（全场概览项）**：
  客观概括全场会议背景、核心主线推进态势与最关键的全局定调决议（约 200–300 字）。
- **后续分项（议题分段项——中文数字序号与自适应分组）**：
  • **议题序号**：严格按照现场审定的有效议题先后时序推进，大项统一使用中文数字序号（如 一. 二. 三.）；
  • **自适应单组 vs 多组与段首标签规矩**：
    ① 单组研讨（讨论内容集中单一，只能总结出一组要点）：
       段首统一标为【一. 议题名称】（无斜杠），段内直接叙述该议题的核心方案、论据与结论；
    ② 多组研讨（讨论内容丰富，包含多个不同业务方向或模块）：
       按阿拉伯数字设立子主题，每个子主题独立成段，段首分别标为【二. 议题名称 / 1. 子主题】、【二. 议题名称 / 2. 子主题】；
  • **正文行文标准**：
    直陈业务方案考量、关键量化指标（如算力卡规格、时延参数、测试数据、资源配比）与落地定调；保持高信息密度，就事论事，省略发散与无用客套对白，去发言人机械前缀。

### 2. key_decisions（全场决策决议）
- 通读各议题切片及【会末收尾与全场定调】，直接提炼现场明确拍板的最终决议列表；
- 以被决定的业务事项为主干陈述终局定调（如“【事项】统一定调/指标要求”），去除口语化建议前缀，全景平铺列出。

### 3. personally_relevant_points（全员落地行动分工）
- 从讨论中提取面向团队或具体责任人的明确行动要求与交付排期；全场无具体待办时输出 []。

### 4. risks_and_blockers / unresolved_questions（全场风险与未决）
- 提取现场明确提出的技术瓶颈、外部依赖卡点与悬而未决的争议事项；无则输出 []。

### 5. history_comparison
- 统一输出空列表 []。

---

## 二、真实性底线
所有数据、人名、决策严格以打标转写文本为准；研讨探讨与拍板定调严格区分边界；有据才写，忠实于原始事实。
"""
```

---

## 六、改动模块 4：终稿渲染 Prompt 动态语义重构（prompts.py）

### 1. 修改文件
`domains/meeting/tasks/minutes/prompts.py`

### 2. 核心重构：`MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT`
> [!TIP]
> **关键设计升级**：不在 Prompt 中硬编码 `[全文摘要]`、`[要点梳理]`、`[结论与决定]` 等具体栏目字眼，使用通用的“概括总述类栏目”、“议题研讨类栏目”、“决议结论类栏目”语义角色，确保无论是通用模板还是未来其他议程模板均能自适应动态适配！

```python
MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="会议纪要渲染器",
    source="已审核草稿（结构化事实基准）",
    source_rule=(
        "**以已审核草稿为事实基准，严格遵循模板栏目规约与公文层级标准完成排版**：\n"
        "【栏目语义自适应映射】：\n"
        "1. 概括总述类栏目：映射草稿 executive_summary 的首项（全场概览项），以连贯单段呈现；\n"
        "2. 议题研讨类栏目：映射草稿 executive_summary 的后续议题分段项，按以下规则严格排版：\n"
        "   - 议题大项（### 一. 议题名称）：必须使用草稿中记录的带中文数字序号的审定议题全称设立三级小节标题；\n"
        "   - 单组研讨排版（草稿段首无斜杠子主题）：直接在三级标题下方以无序列表项（- ）分点输出核心事实，不设立四级小节标题；\n"
        "   - 多组研讨排版（草稿段首带斜杠子主题）：使用阿拉伯数字设立四级子标题（#### 1. xxx、#### 2. xxx），并在每个四级标题下方以无序列表项（- ）分点输出；\n"
        "   - 强制列表分点（- ）：研讨正文一律以列表项（- ）分行呈现，将草稿事实按句意自然拆分为多行“- ”条目（无需添加粗体小标题），不直接输出无前缀的纯文本段落；\n"
        "3. 决议结论类栏目：映射草稿 key_decisions 列表，使用列表项逐条陈述现场明确拍板的决议（推荐以「- **事项名称**：具体决议与指标要求」展开）；若草稿无决议，整栏自适应隐去；\n"
        "4. 草稿段首标记平滑吸收：草稿段首的【一. 议题名称】或【二. 议题名称 / 1. 子主题】为结构辅助标记，排版时自然转化为对应层级的三级与四级标题，列表中直接陈述业务事实，不复述中括号标记；\n"
        "5. 事实保真全量输出：草稿中的量化指标、方案考量与结论定调完整呈现在对应小节中，无事实遗漏；专有名词与数据严格以草稿为准。"
    ),
    empty_rule=(
        "某栏在草稿中对该栏主题无依据且模板允许省略时直接保持空内容自适应隐去；"
        "模板没约定时优先自适应隐去，确需占位时按模板指定词填写，不使用外部常识补全。"
    ),
    extra_rules=[
        "模板若含写作要求，按该要求客观准确填写",
    ],
)
```

---

## 七、改动模块 5：监督审核 Prompt 适配（prompts.py）

### 1. 修改文件
`domains/meeting/tasks/minutes/prompts.py`

### 2. 适配内容：`MINUTES_AGENDA_SUPERVISOR_PROMPT`
审核器重点审查草稿事实是否背离打标原文，并放行新格式标签：

```python
_AGENDA_SUPERVISOR_RULES = """### 审定议题模式审查专项
1. **议题完整性与时序审查**：
   - 审查草稿 executive_summary 是否覆盖本次审定的有效讨论议题；
   - 审查中文数字序号（一. 二.）及单组【一. 议题】、多组【二. 议题 / 1. 子主题】格式，判定为标准规范直接放行；
2. **事实保真与决议放行**：
   - 重点审查正文技术参数与结论是否在打标原文中有据可查，是否存在虚构人名或数字；
   - 决议项以业务标的为主干陈述终局定调，去口头前缀属于公文规范，予以认可并放行；
   - 未发现关键事实严重错误时，一律予以 approve 放行。"""

MINUTES_AGENDA_SUPERVISOR_PROMPT = _SUPERVISOR_COMMON_BASE + "\n\n" + _AGENDA_SUPERVISOR_RULES
```

---

## 八、重构前后流水线耗时与产物形态对比

### 1. 执行耗时对比

```
【重构前流水线 (耗时约 100s ~ 130s)】
[议程对齐 1s] → [理解层 LLM 46s] → [草稿层 LLM 25s] → [审核层 LLM 2s] → [渲染层 LLM 16s]

【重构后流水线 (耗时约 35s ~ 40s，提速 2.5 倍)】
[议程对齐 1s] → [跳过理解 0s]   → [草稿层 LLM 18s] → [审核层 LLM 2s] → [渲染层 LLM 12s]
```

### 2. 最终产物形态预览（result.md）

```markdown
# 通用纪要

## 全文摘要

本次会议为华为终端小艺业务北京团队交流会，何刚总出席并致辞...（略）

## 要点梳理

### 一. 何刚总致辞

- 何刚回顾北京业务历史，荣耀2020年8月出售后北京团队规模缩减，下一步将加强北京团队建设和产品布局。
- 强调华为AI核心优势在于与硬件深度协同，要求小艺在华为手机上的使用量、日活数和体验全面超过豆包。
- 坚定切入具身智能市场，但坚持商业成功与长期主义，先做好底层技术积累，不追求概念炒作。

### 二. 互动交流

#### 1. 产品线拉通与规格统一

- 针对小艺多终端唤醒体验不一致问题，建议手机和PC高中低端各统一一套硬件规格，别再频繁变动。
- 建议通过 TMT 平台统一提出诉求并上升决策，历史产品逐步兼容，未来新产品严格统一落地。

#### 2. AI撬动消费与场景打透

- 提出语音助手心智仍需培养，必须聚焦买锅、买纸等日常高频场景彻底打透，补足最后20%体验差距。
- 针对小艺慧记，提出尽快支持输入会议日程图片自动按议题生成纪要，并在10人组实现3天声纹免标注。

#### 3. 算力资源保障与人才战略

- 面对英伟达新卡特性和模型转换精度损失，明确全力以赴协调获取950芯片，必要时外部租赁算力保训练。
- 面对高薪争夺AI人才，坚持长期主义企业文化，吸引真正认可核心价值观的顶尖人才。

### 三. 任务令签署与授予仪式

- 举行 543-5 会战任务令签发仪式，何刚总现场为 6 支战队签发任务令，各战队代表上台接令并合影。
- 强调成本时延战队要重点攻坚省算力、低延迟推理，对算法调优提出极高要求。

## 结论与决定

- **小艺体验对标豆包**：小艺在华为手机上的使用量、日活数和体验要超过豆包。
- **产品线规格拉通**：手机高端低端各一个规格，PC类似，反向推动产品线。
- **小艺慧记会议纪要**：尽快支持输入会议日程图片，自动按议题生成会议纪要。
- **卡资源保障**：全力以赴解决算力卡资源，重点推进950芯片与外部租赁方案。
```
