# minutes + docs（非空）议题增强纪要优化执行清单

> **核心原则与实验边界**：
> 1. **单模板先行实验**：当前阶段**仅针对 `resources/agenda_templates/general_minutes.md` 这一份通用纪要模板**进行实验验证；未定制的模板（如 `project_progress` 等）100% 平滑回退到普通模板目录；原有 `resources/templates/` 目录下的 32 个模板保持 **100% 纯净不动**。
> 2. **严格任务隔离**：所有改动仅在 `line == "minutes"` 且 `docs` 探测出 $\ge 1$ 个有效实质议题时生效；普通 `minutes`（无 docs 或文档无有效议程）及所有其他任务线（`actions`, `risks`, `consensus_decision`, `agenda_minutes` 等）**100% 保持原有基线，零改动、零干扰**。
> 3. **公共常量零污染**：不直接修改底层公共 System Prompt 常量（如 `MEETING_UNDERSTANDING_SYSTEM_PROMPT`），全部通过运行时在编排层动态注入正向指引，消除多任务耦合与“屎山”风险。
> 4. **正向引导与结构降噪**：摒弃“严禁xxx/违者严惩”等生硬负向用语与华丽词藻，采用专业、清晰、直接的正向结构化指引。
> 5. **树状层级自顶向下贯通**：从理解层、草稿层、模板层到渲染层，统一“一级法定议题 -> 二级业务子主题 -> 三级事实论据”的树状模型，彻底解决大议题被肢解、子研讨点扁平化外挂的问题。

---

## 一、当前输出问题诊断与根因定位

### 1. 现场实测现象对照

| 既定议程审定清单（3 项有效议题） | 上一轮大模型实际输出标题（共 11 个） | 现象本质与问题所在 |
| :--- | :--- | :--- |
| **议题 02: 何刚总致辞** | 1. `### 开场致辞与北京业务回顾`<br>2. `### AI与小艺发展战略`<br>3. `### 具身智能与商业成功` | **大议题被肢解**：议题内部讨论的 3 个方向被打平为 3 个一级大节，**法定议题名称反而丢失** |
| **议题 03: 互动交流（现场问答、自由交流与讨论）** | 4. `### 团队交流：唤醒体验与产品线协同`<br>5. `### 团队交流：AI撬动消费决策与小艺慧记`<br>6. `### 团队交流：安全合规与生态平衡`<br>7. `### 团队交流：全模态交互与终端壁垒`<br>8. `### 团队交流：人才与算力困难`<br>9. `### 团队交流：AI泡沫与终端未来`<br>10. `### 团队交流：小艺健康与情感化` | **层级扁平化坍塌**：把交流环节下的 7 个细分话题，全部升格为独立的 `###` 小节，缺少统一归集的大节 |
| **议题 04: 任务令签署与授予** | 11. `### 543-5会战任务令签发仪式` | **名称被随意替换**：未遵从议程中的规范名称，自行根据转写改成了仪式名称 |

### 2. 根因分析：流水线四级结构性脱节

1. **理解层（`meeting_understanding`）**：原提示词仅告知“顺应讨论推进时序划分自然研讨阶段”，且上下文仅标注为“参考”。大模型面对 400 余块转写，自由切出了 11 个局部微观阶段，导致源头事实底座被切碎。
2. **草稿层（`minutes_agent`）**：草稿 Prompt 明确以 `session_segments` 为骨架总纲，且其 `executive_summary: list[str]` 为扁平列表，没有“议题 -> 子议题”的层级结构，直接固化了这 11 个碎块。
3. **模板层（`general_minutes.md`）**：原说明仅允许 `### 议题名称` 下直接跟 `- 条目`，没有提供“二级小标题”的合法语法容器，导致模型在面对丰富讨论时，为了分段被迫把子主题升格为 `###`。
4. **渲染层（`minutes_render`）**：Render Prompt 严令“以草稿为唯一事实与结构基准，不得脱离草稿扩写”，而传入的草稿只有 11 个碎块、没有议题大纲。大模型陷入草稿与议题清单的死锁，只能加前缀妥协。

---

## 二、目标层次结构规范（以通用纪要为例）

在 `minutes + docs`（有效议题 $\ge 1$）模式下，最终交付的 Markdown 纪要结构规范如下：

```markdown
# 通用纪要

## 全文摘要
[单段概览，涵盖会议背景、主要参会方、涵盖的核心议题业务主线以及全场拍板的最关键决议；开门见山总揽全场宏观态势，具体细节论据归入要点梳理。]

## 要点梳理

### 01 何刚总致辞
#### 1. 北京业务回顾与人才布局
- 回顾北京业务历史：2020年8月荣耀出售带走2000多人，北京剩余八九百人...
- 强调北京人才优势，初步提出围绕AI、小艺、具身智能在北京布局的考虑...
#### 2. AI与小艺发展战略
- 小艺在华为手机上的使用量、日活数和体验要超过豆包...
- 讨论卡资源限制下的推广策略...
#### 3. 具身智能与商业成功
- 华为坚持以商业成功为目标，不追求炒作市值...

### 02 互动交流（现场问答、自由交流与讨论）
#### 1. 唤醒体验与产品线协同
- 高畅提出小艺作为平台面临不同产品线独特卖点影响用户心智稳定的问题...
- 何刚建议拉通规格：手机产品线高端一个规格、低端一个规格，PC类似...
#### 2. AI撬动消费决策与小艺慧记
- 叶康提问AI结合硬件如何成为消费者购买决策的关键因素...
- 何刚提出小艺慧记应支持图片日程输入，按议题生成纪要...
#### 3. 安全合规与生态平衡
- 丁博提出用户效率与安全合规、生态利益的冲突...
#### 4. 全模态交互与终端壁垒
- 任浩宇提出全模态自然交互趋势，结合OS和设备优势...
#### 5. 人才与算力瓶颈
- 叶康指出AI人才保鲜期与老旧卡架构痛点...
- 何刚强调长期主义并承诺解决算力卡问题...

### 03 任务令签署与授予
- 会议最后举行543-5会战任务令签署与授予，何总为6支战队签发任务令...

## 结论与决定
- 分点列出全场明确拍板的决议或主流共识。
```

---

## 三、四级贯通实施细节

### 步骤 1：专属场景模板层语法扩展（`resources/agenda_templates/general_minutes.md`）
- **文件路径**：[`resources/agenda_templates/general_minutes.md`](file:///D:/study/demo/resources/agenda_templates/general_minutes.md)
- **改动范围**：仅修改 `[要点梳理]` 的占位符说明文本，**提供标准的二级小标题语法容器**，去掉生硬说教词。
- **优化后文本**：
  ```markdown
  # 通用纪要

  <!-- requirement
  客观全面呈现会议核心内容与决策，语气为严谨客观的公文陈述；以现场实质研讨议题为主线结构化分节展开事实，突出关键数据依据、各方立场与决策定调，篇幅充分饱满，信息密度高。
  -->

  ## [全文摘要]
  [单段概览，约 250–350 字：全面概述会议背景、主要参会方、涵盖的核心议题业务主线以及全场拍板的最关键决议；开门见山总揽全场宏观态势，具体细节论据归入 [要点梳理]，本栏不铺开分项细节。]

  ## [要点梳理]
  [以现场审定的有效议题清单为主线展开呈现：
  每个审定议题设立三级小节标题：
  ### 议题名称

  各议题正文展开格式：
  - 若议题包含多个不同讨论方向（如交流问答、专题研讨），在议题下设立清晰的子标题划分各部分内容（推荐使用 #### 1. 子主题名称 或 **1. 子主题名称**：），在每个子主题下使用 - 逐项列出具体方案考量、事实论据与明确结论；
  - 若议题讨论内容集中单一，可直接在议题标题下使用 - 逐项列出核心事实与定调；
  条数随现场实际讨论充分展开。]

  ## [结论与决定]
  [聚焦会议最终形成的拍板定调、裁决方案，或各方达成的主流倾向共识与推进基调：分点写明决议或共识陈述、决策主体与落地要求（若全场无决议或共识内容则本栏整体不予呈现）。]
  ```

---

### 步骤 2：理解层正向阶段归集指引（`domains/meeting/orchestrator.py`）
- **触发函数**：`_make_meeting_understanding_node`
- **生效条件**：`"minutes" in selected and state.get("has_valid_agenda")`
- **注入位置**：`channel_text` 最前端
- **指引文案（正向、平实、明确）**：
  ```python
  if state.get("has_valid_agenda"):
      agendas = state.get("valid_agendas") or []
      checklist = "\n".join(
          f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
          for i, a in enumerate(agendas)
      )
      nav_block = (
          f"【审定议题阶段归集指引】：\n"
          f"本次会议已审定以下有效讨论议题：\n{checklist}\n\n"
          "请按上述清单组织 session_segments：\n"
          "1. 阶段对应：session_segments 与清单议题一一对应，segment_title 采用清单中的议题全称；\n"
          "2. 议题内部分点：若议题下包含多个讨论方向（如交流环节涵盖多个问答点），"
          "请在该阶段的 key_facts 中按子主题分类列出（格式：[子主题名称] 具体事实与论据）。"
      )
      channel_text = f"{nav_block}\n\n{channel_text}".strip()
  ```
- **隔离守护**：无 docs、docs 无议题或其他任务线时，`channel_text` 完全不含此 block，0 污染。

---

### 步骤 3：草稿层结构化正向引导（`domains/meeting/orchestrator.py`）
- **触发函数**：`_line_shared_context`
- **生效条件**：`line_name == "minutes" and state.get("has_valid_agenda")`
- **注入位置**：`parts` 装配段中取代原本模糊的自由分段说明
- **指引文案（正向、层次清晰）**：
  ```python
  if line_name == "minutes" and state.get("has_valid_agenda"):
      agendas = state.get("valid_agendas") or []
      agenda_checklist = "\n".join(
          f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
          for i, a in enumerate(agendas)
      )
      parts.append(
          f"【审定议题纪要撰写指引】：\n"
          f"本次会议已审定以下有效讨论议题：\n{agenda_checklist}\n\n"
          "请按以下结构撰写 executive_summary：\n"
          "1. 首项（全局概览）：简要概述全场会议背景、核心主线与最关键决议；\n"
          "2. 后续各项（议题分节）：严格按审定清单顺序，一项对应一个议题展开成段；\n"
          "3. 议题内部分点：对于包含多个讨论方向的议题，在段落内自然呈现各子主题（格式：[子主题名称] 论据与结论），交代完整研讨脉络。"
      )
      parts.append(
          f"【会议原文】\n{state.get('tagged_transcript') or state.get('transcript') or ''}"
      )
  ```
- **隔离守护**：仅在 `minutes` 且有有效议题时生效；普通 minutes 走原有 `fact_note` 和无标记原文。

---

### 步骤 4：渲染层排版解耦与执行引导（`domains/meeting/orchestrator.py`）
- **触发函数**：`_render_context`
- **生效条件**：`line_name == "minutes" and state.get("has_valid_agenda")`
- **注入位置**：`extra_parts` 注入块
- **指引文案（正向、解开草稿死锁）**：
  ```python
  if line_name == "minutes" and state.get("has_valid_agenda"):
      agendas = state.get("valid_agendas") or []
      if agendas:
          agenda_checklist = "\n".join(
              f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
              for i, a in enumerate(agendas)
          )
          extra_parts.append(
              f"【现场审定的有效议题清单】：\n{agenda_checklist}\n\n"
              "【议题结构排版指引】：\n"
              "排版 [要点梳理] 栏目时，请遵循以下层级规范：\n"
              "1. 一级小节：使用清单中的议题全称作为 ### 小节标题，按清单顺序依次呈现；\n"
              "2. 二级子分点：对于包含多个讨论方向的议题，将草稿中对应的讨论点作为子标题展开（使用 #### 1. 子主题名称 或 **1. 子主题名称**：），在子标题下方使用 - 列出具体事实论据；\n"
              "3. 事实归属：草稿中记录的各研讨事实，根据其讨论范畴归入对应议题的子主题下，使正文结构层次分明。"
          )
  ```
- **隔离守护**：仅在 `line_name == "minutes"` 且 `has_valid_agenda` 为 True 时注入。

---

## 四、全链路零侵入与降级保障矩阵

| 场景分支 | 触发条件 | 模板路径 | 理解层指引 | 草稿层指引 | 渲染层指引 | 行为预期 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A. minutes + docs（含有效议题）** | `line == "minutes"` 且 `docs` 检出有效议题 $\ge 1$ | 优先加载 `resources/agenda_templates/general_minutes.md` | 注入阶段归集指引，session_segments 1:1 对齐议题 | 注入议题草稿指引，段落按议题分层 | 注入层级排版指引，输出三级议题与四级子主题 | **完全按议题结构化输出（本优化目标）** |
| **B. minutes + docs（非议题文档）** | `line == "minutes"` 但 `docs` 为普通资料/无议程 | 加载 `resources/templates/general_minutes.md` | 不注入议题指引，正常自由切分 | 不注入议题指引，走原有 fact_note | 不注入议题指引，走通用渲染 | **100% 保持历史基线（OCR/资料并入转写）** |
| **C. minutes（无 docs）** | `line == "minutes"` 且 `docs` 为空 | 加载 `resources/templates/general_minutes.md` | 不注入议题指引 | 不注入议题指引 | 不注入议题指引 | **100% 保持历史基线** |
| **D. 非通用纪要模板（如项目进度会）** | `template == "project_progress"` | `agenda_templates` 未定制，平滑回退 `resources/templates/project_progress.md` | 按其既定规则执行 | 按其既定规则执行 | 按其既定规则执行 | **100% 保持历史基线** |
| **E. 其他任务线（actions, risks, etc.）** | `line in {"actions", "risks", "agenda_minutes", ...}` | 各任务线专属模板 | 不受 minutes 影响 | 不受 minutes 影响 | 不受 minutes 影响 | **100% 保持历史基线** |

---

## 五、验证与回归测试计划

1. **模板内容与解析测试**：
   - 验证 `resolve_agenda_template_format("general_minutes")` 正确解析出包含二级小标题语法说明的内容；
   - 验证 `resolve_template_format("general_minutes")` 依然读取老模板（原模板 100% 不动）。
2. **编排层上下文装配单测**：
   - 在 `tests/unit/meeting/test_minutes_agenda_integration.py` 中验证：
     - `state.has_valid_agenda=True` 时，`meeting_understanding` 包含【审定议题阶段归集指引】；
     - `state.has_valid_agenda=True` 时，`minutes_agent` 包含【审定议题纪要撰写指引】；
     - `state.has_valid_agenda=True` 时，`minutes_render` 包含【议题结构排版指引】；
     - `state.has_valid_agenda=False` 时，上述指引一律**不出现**。
3. **全域回归测试**：
   - 运行 `pytest tests/unit/meeting/`（确保 34 个用例持续全绿）；
   - 运行 `pytest tests/core/test_core.py`（确保 8 个核心基础用例全绿）。

---

## 六、实施步骤检查表

- [x] **步骤 1**：更新 `resources/agenda_templates/general_minutes.md`（扩展 `[要点梳理]` 支持二级小标题，去除生硬词汇）；
- [x] **步骤 2**：更新 `domains/meeting/orchestrator.py`：
  - [x] 2.1 优化 `_make_meeting_understanding_node`（正向审定议题阶段归集指引）；
  - [x] 2.2 优化 `_line_shared_context`（正向审定议题纪要撰写指引）；
  - [x] 2.3 优化 `_render_context`（正向议题结构排版指引）；
- [x] **步骤 3**：同步更新 `tests/unit/meeting/test_minutes_agenda_integration.py` 测试用例（9/9 全部通过）；
- [x] **步骤 4**：运行完整测试集确保 0 回归，更新进度追踪看板（全量单测通过）。
