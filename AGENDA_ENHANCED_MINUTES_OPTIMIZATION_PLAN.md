# 基于议程对齐的模板纪要增强方案 (AGENDA_ENHANCED_MINUTES_OPTIMIZATION_PLAN)

> **版本**：v2.1（全要素防御性架构版）  
> **核心原则**：
> 1. **激活条件严格受限**：仅当 `line == "minutes"` 且 `req.docs` **非空** 时才尝试探测议程。
> 2. **无感降级与原有行为 100% 保持**：若 `docs` 解析出的有效讨论议题 `< 1`（如上传的是参考资料、财务报表、纯代码，或现场全部未讨论），**严格回退至现有 `minutes` 的 `material_docs` 逻辑**（资料正常预览/OCR 并入转写），绝不丢失文件，绝不报错中断。
> 3. **对其他任务 0 侵入**：`agenda_minutes`、`actions`、`risks` 等所有其他任务代码与流程 **100% 保持现状、零改动**。
> 4. **模板与 Agent 源码 0 侵入**：模板 `.md`、通用编译器 `core/templates/`、`meeting_understanding_agent.py` 以及 `minutes_agent.py` **源代码一字不改**，仅在 `orchestrator.py` 编排层单点控制上下文装配。

---

## 目录
- [一、核心架构与绝对安全防御机制](#一核心架构与绝对安全防御机制)
- [二、第一步：公共提纯与探测引擎设计 (`agenda_engine.py`)](#二第一步公共提纯与探测引擎设计-agenda_enginepy)
- [三、第二步：入口适配与材料防丢回退机制 (`app/tasks.py`)](#三第二步入口适配与材料防丢回退机制-apptaskspy)
- [四、第三步：编排层状态流转与单点控制 (`orchestrator.py`)](#四第三步编排层状态流转与单点控制-orchestratorpy)
- [五、零侵入 Agent 协同与模板原生渲染机制](#五零侵入-agent-协同与模板原生渲染机制)
- [六、端到端完整数据流与时序验证](#六端到端完整数据流与时序验证)
- [七、实施文件修改索引与防回归单测矩阵](#七实施文件修改索引与防回归单测矩阵)

---

## 一、核心架构与绝对安全防御机制

### 1. 全任务分支矩阵（保证 0 交叉影响）

| 任务场景 | 触发条件 | 执行链路 | 对原系统影响 |
| :--- | :--- | :--- | :--- |
| **议程增强纪要** (新增) | `line == "minutes"` 且 `docs` 非空 且 `valid_agendas >= 1` | 激活新链路：议程提纯 ➔ 头尾保护打标 ➔ 结构化草稿 ➔ 模板原生按议题输出 | 仅在有明确有效议程时激活 |
| **常规纪要（传了非议程参考资料）** | `line == "minutes"` 且 `docs` 非空 且 `valid_agendas < 1` | **自动回退老逻辑**：`docs` 视为 `material_docs` 正常 OCR/预览并入 `transcript`，原有常规纪要流水线 100% 运行 | **完全保留原参考资料并入转写的行为**，文件不丢 |
| **常规纪要（无 docs）** | `line == "minutes"` 且 `docs` 为空 | 100% 走现有常规纪要代码 | 零改动 |
| **原有既定议程纪要** | `line == "agenda_minutes"` | 100% 走现有的 `agenda_minutes` 独立流水线 | 零改动 |
| **待办、风险、图谱等其他任务** | `line in {"actions", "risks", "catalog", ...}` | 100% 走各任务原有逻辑 | 零改动 |

```
                              【任务请求到达】
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
       line != "minutes"                       line == "minutes"
                 │                                       │
     【100% 走原有其他任务】                    ┌────────┴────────┐
   (agenda_minutes/actions/等)                  ▼                 ▼
                                         docs 为空            docs 非空
                                                │                 │
                                                ▼                 ▼
                                    【100% 走现有无文档纪要】   【快速纯 Python 预探测】
                                                                  │
                                                ┌─────────────────┴─────────────────┐
                                                ▼                                   ▼
                                     有效议题数 < 1                       有效议题数 >= 1
                                                │                                   │
                                                ▼                                   ▼
                                    【100% 回退现有参考资料纪要】         【激活议程增强新轨道】
                                    - docs 并入 transcript 作为资料       - 议程单独立抽取不污染原文
                                    - has_valid_agenda = False           - 打标实录（头尾保护）
                                    - 正常产出常规纪要                   - 结构化草稿，模板按议题输出
```

---

## 二、第一步：公共提纯与探测引擎设计 (`agenda_engine.py`)

### 1. 新建公共模块：`domains/meeting/agenda_engine.py`
抽取 `domains/meeting/tasks/agenda_minutes/alignment_engine.py` 和 `agenda_parser.py` 的算法能力，封装为纯 Python（零 LLM 调用、运行耗时 < 0.05s）的公共引擎：

```python
# domains/meeting/agenda_engine.py
from __future__ import annotations
from dataclasses import dataclass
import logging
from domains.meeting.tasks.agenda_minutes.agenda_parser import parse_agenda_text
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    is_trivial_ceremonial_item,
    AgendaAlignment,
    DiscussionBlock,
)

logger = logging.getLogger(__name__)

@dataclass
class ValidAgendaItem:
    seq: str
    title: str
    presenters: list[str]
    start_index: int
    end_index: int
    matched_blocks: list[DiscussionBlock]

@dataclass
class AgendaProcessResult:
    has_valid_agenda: bool
    valid_agendas: list[ValidAgendaItem]
    tagged_transcript: str
```

### 2. 核心清洗规则
1. **仪式与会务动线过滤**：复用 `is_trivial_ceremonial_item(align)`，自动过滤“观看宣传片/视频”、“合影留念”、“纯仪式致辞”、“茶歇就餐”、“乘车参观”；
2. **零证据未讨论过滤**：严格过滤 `align.status == "skipped"`，避免模型虚构未发生的讨论；
3. **现场发言时序对齐**：使用 `alignment_res.chronological_alignments`，完全尊重现场实际发言先后顺序。

### 3. 头尾保护机制（开场与收尾绝对不丢）
```python
def build_tagged_transcript_with_head_tail(
    all_blocks: list[DiscussionBlock],
    valid_agendas: list[ValidAgendaItem],
) -> str:
    """按议题打标，同时物理保护开场白与会末定调。"""
    if not valid_agendas or not all_blocks:
        return "\n".join(f"{b.speaker}: {b.content}" for b in all_blocks)

    min_start_block_idx = min(a.matched_blocks[0].index for a in valid_agendas if a.matched_blocks)
    max_end_block_idx = max(a.matched_blocks[-1].index for a in valid_agendas if a.matched_blocks)

    parts: list[str] = []

    # 1. 头部保护：首个实质议题前的发言（开场白、背景动线）
    head_blocks = [b for b in all_blocks if b.index < min_start_block_idx]
    if head_blocks:
        head_text = "\n".join(f"{b.speaker}: {b.content}" for b in head_blocks).strip()
        if head_text:
            parts.append(f"【会议开场背景与宏观动线】：\n{head_text}")

    # 2. 各实质有效议题切片（按现场实际先后时序排列）
    for a in valid_agendas:
        item_text = "\n".join(f"{b.speaker}: {b.content}" for b in a.matched_blocks).strip()
        pres_str = "、".join(a.presenters) if a.presenters else "未指定"
        parts.append(
            f"════════════════════════════════════════\n"
            f"【议题 {a.seq}：{a.title}】（汇报人：{pres_str}）\n"
            f"{item_text}"
        )

    # 3. 尾部保护：末个实质议题后的发言（散会决议、领导最终拍板）
    tail_blocks = [b for b in all_blocks if b.index > max_end_block_idx]
    if tail_blocks:
        tail_text = "\n".join(f"{b.speaker}: {b.content}" for b in tail_blocks).strip()
        if tail_text:
            parts.append(f"════════════════════════════════════════\n【会末收尾与全场定调】：\n{tail_text}")

    return "\n\n".join(parts)
```

---

## 三、第二步：入口适配与材料防丢回退机制 (`app/tasks.py`)

### 1. 严格隔离 `agenda_minutes` 与 `minutes`
在 `app/tasks.py` 中，**绝不合并** `elif line in {"agenda_minutes", "minutes"}:`，而是为 `minutes` 设立独立探测：

```python
# app/tasks.py (在 line == "agenda_minutes" 分支之后)
elif line == "minutes" and req.docs:
    # 仅针对 minutes 且 docs 非空时进行尝试提取
    candidate_parts = []
    image_docs = [n for n in req.docs if _is_image_name(n)]
    text_docs = [n for n in req.docs if not _is_image_name(n)]
    if image_docs:
        candidate_spk = []
        if transcript:
            from domains.meeting.tasks.agenda_minutes.agenda_parser import extract_speakers_from_transcript
            candidate_spk = extract_speakers_from_transcript(transcript)
        ocr_text = _ocr_single_agenda_doc(user_id, image_docs, candidate_speakers=candidate_spk)
        if ocr_text:
            candidate_parts.append(ocr_text)
    for name in text_docs:
        path = _input_file(user_id, "docs", name)
        try:
            body = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            body = path.read_text(encoding="gbk", errors="replace").strip()
        if body:
            candidate_parts.append(body)
    candidate_agenda_text = "\n\n".join(candidate_parts).strip()

    # 纯 Python 快速预判（耗时 < 0.05s）
    from domains.meeting.agenda_engine import probe_valid_agendas
    valid_agendas = probe_valid_agendas(transcript, candidate_agenda_text) if (candidate_agenda_text and transcript) else []

    if valid_agendas:
        # 【分支 A：确认是有效议程】专供 agenda_text，不并入转写，避免表格重复污染
        extra_line_inputs["agenda_text"] = candidate_agenda_text
        logger.info("minutes task: detected %d valid discussed agendas from docs, activating agenda-enhanced minutes", len(valid_agendas))
    else:
        # 【分支 B：回退老逻辑（防丢机制）】未探测到有效议程（传的是参考材料、非议程文档或全未讨论）
        # 100% 回退至原有 material_docs 逻辑，资料正常 OCR/预览并入 transcript！
        logger.info("minutes task: docs does not contain valid discussed agendas, silently falling back to legacy material docs")
        material_docs = [name.strip() for name in req.docs]
```

---

## 四、第三步：编排层状态流转与单点控制 (`orchestrator.py`)

### 1. 状态初始化（`initial_state`）
在编排层初始状态装配中：
```python
# domains/meeting/orchestrator.py
agenda_text = str((state.get("line_extra") or {}).get("agenda_text") or "").strip()
if line_name == "minutes" and agenda_text and state.get("transcript"):
    from domains.meeting.agenda_engine import process_agenda_for_minutes
    agenda_res = process_agenda_for_minutes(state["transcript"], agenda_text)
    state["valid_agendas"] = agenda_res.valid_agendas
    state["tagged_transcript"] = agenda_res.tagged_transcript
    state["has_valid_agenda"] = agenda_res.has_valid_agenda
else:
    state["valid_agendas"] = []
    state["tagged_transcript"] = state.get("transcript") or ""
    state["has_valid_agenda"] = False
```

### 2. 会议理解节点单点控制（`_meeting_understanding_node_factory`）
`meeting_understanding_agent.py` **源代码零改动**。编排层直接利用其原生的 `transcript` 与 `user_channel` 参数：
```python
# 当且仅当 has_valid_agenda 为 True 时，传入打标转写并注入议题参考
if state.get("has_valid_agenda"):
    transcript_input = state["tagged_transcript"]
    agendas = state["valid_agendas"]
    agenda_checklist = "\n".join(f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）" for i, a in enumerate(agendas))
    agenda_nav_block = f"【会前审定议题参考（供阶段划分与研讨归集对齐）】：\n{agenda_checklist}"
    existing_channel = kwargs.get("user_channel") or ""
    kwargs["user_channel"] = f"{agenda_nav_block}\n\n{existing_channel}".strip()
else:
    transcript_input = state["transcript"]
    # kwargs 保持原有原样，完全走原有逻辑
```

### 3. 纪要草稿上下文装配（`_line_shared_context`）
`minutes_agent.py` **源代码零改动**。编排层在组装 `minutes` 任务的 `shared_context` 时：
```python
# domains/meeting/orchestrator.py - _line_shared_context
if line_name == "minutes" and state.get("has_valid_agenda"):
    agendas = state["valid_agendas"]
    agenda_checklist = "\n".join(f"{i+1}. 议题：{a.title}" for i, a in enumerate(agendas))
    parts.append(f"【现场审定的有效议题清单（请按此结构展开正文）】：\n{agenda_checklist}")
    parts.append(f"【会议原文（已标注议题边界，包含开场与收尾）】：\n{state['tagged_transcript']}")
else:
    # 100% 原样走原有老逻辑：
    parts.append(f"会议原文：\n{state.get('transcript') or ''}")
```

---

## 五、零侵入 Agent 协同与模板原生渲染机制

### 1. 为什么 `meeting_understanding_agent.py` 与 `minutes_agent.py` 0 改动？
- `MeetingUnderstandingAgent.run` 原生接受 `transcript: str` 和 `user_channel: str`；
- `MinutesGenerationAgent.run` 原生只接受一个合并后的 `shared_context: str`。
所有结构化信息完全在 `orchestrator.py` 这一处组装完成，无需侵入 Agent 类定义，极大降低单测维护成本与回归风险。

### 2. 为什么模板 `.md` 与 `core/templates/` 0 改动？
现有模板（如 [general_minutes.md](file:///D:/study/demo/resources/templates/general_minutes.md)）：
- `[全文摘要]` 明确要求：“一段写完……全面概述会议背景……研讨的核心业务主线以及拍板定夺的最关键决议……具体研讨细节归 [要点梳理]，本栏不铺开展开。”
- `[要点梳理]` 明确要求：“以议题为主线展开过程与事实细节：**按议题设立小节标题 ### 议题名称**；以 - 逐项列出具体方案考量与论据……”

当上游的草稿 `executive_summary` 已经由 `minutes_agent` 分层（段 0 是大盘，段 1~N 是各有效议题细节），下游模板渲染模型在看到清晰分块的草稿后，顺理成章会在 `[要点梳理]` 输出 `### 议题名称` 小节，完全不需要任何下游规则补丁。

---

## 六、端到端完整数据流与时序验证

```
场景一：用户发起常规 minutes 任务，传了议程单（有效议题 3 项）
app/tasks.py ➔ 探测到 3 项有效议题 ➔ extra_line_inputs["agenda_text"]
orchestrator.py ➔ has_valid_agenda = True ➔ 生成 tagged_transcript
meeting_understanding ➔ 基于 tagged_transcript 输出对齐议题的理解
minutes_agent ➔ 产出分段 executive_summary 草稿（段0大盘，段1~3分议题）
minutes_render ➔ 结合 general_minutes.md，自然输出含 ### 议题名称 的模板纪要

场景二：用户发起常规 minutes 任务，传了技术方案 PDF（非议程文档）
app/tasks.py ➔ 探测有效议题 = 0 ➔ 默认回退！docs 进入 material_docs ➔ 正常 OCR 并入 transcript
orchestrator.py ➔ has_valid_agenda = False ➔ 全流程执行原有常规逻辑，无异常中断，参考材料完好保留

场景三：用户发起常规 minutes 任务，无 docs
app/tasks.py ➔ 无 docs ➔ 全流程 100% 走现有常规逻辑，零分支变化

场景四：用户发起 agenda_minutes 任务
app/tasks.py ➔ 进入原有的 elif line == "agenda_minutes": 独立分支 ➔ 100% 走 agenda_minutes 原有链路
```

---

## 七、实施文件修改索引与防回归单测矩阵

### 1. 真实修改文件清单（仅 3 处代码修改）

| 序号 | 文件路径 | 修改性质 | 涉及改动点 |
| :--- | :--- | :--- | :--- |
| 1 | `domains/meeting/agenda_engine.py` | **新建文件** | 纯 Python 提纯引擎，包含 `extract_valid_discussed_agendas`、`probe_valid_agendas`、`build_tagged_transcript_with_head_tail`。 |
| 2 | [app/tasks.py](file:///D:/study/demo/app/tasks.py) | **局部修改** | 针对 `line == "minutes"` 且 `req.docs` 非空增加探测逻辑；有效时写入 `agenda_text`，无效时回退至 `material_docs`。 |
| 3 | [domains/meeting/orchestrator.py](file:///D:/study/demo/domains/meeting/orchestrator.py) | **局部修改** | 状态初始化增加 `has_valid_agenda` 判定；在理解节点与草稿节点上下文组装处增加条件分支。 |

### 2. 绝对不修改的文件清单（0 侵入）
- `domains/meeting/meeting_core/meeting_understanding_agent.py`（0 改动）
- `domains/meeting/tasks/minutes/steps/minutes_agent.py`（0 改动）
- `domains/meeting/tasks/agenda_minutes/**`（0 改动，原有既定议程流水线完全独立）
- `resources/templates/*.md`（32 个场景模板 0 改动）
- `core/templates/**`（核心通用模板路由器 0 改动）

### 3. 防回归单元测试矩阵
1. **提纯算法单测**（`tests/unit/meeting/test_agenda_engine.py`）：
   - 验证视频/合影/茶歇等仪式过滤；
   - 验证超时跳过的议题被过滤；
   - 验证现场发言顺序调换时时序重排；
   - 验证开场白与收尾定调头尾保护。
2. **容错与回退单测**（`tests/unit/meeting/test_minutes_agenda_fallback.py`）：
   - 验证 `docs` 传入无关文字/纯代码时，系统安全回退，`has_valid_agenda == False`；
   - 验证 `docs` 为空时，100% 走原流水线；
   - 验证 `docs` 传入有效议程时，正向生成打标文本与结构化纪要。