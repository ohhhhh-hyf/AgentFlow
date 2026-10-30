"""Visual Minutes 核心 Prompt 模块。

原则：
1. 绝对无示例软引导：不包含任何具体行业、技术或业务内容示例，纯数据结构与规则契约；
2. 语言简练有效：无华丽辞藻，专注定义数据需求与逻辑关系；
3. 正向需求引导：清晰指出何种内容适合何种图表，避免消极指令堆叠；
4. 纯净输出：仅输出符合契约的纯 JSON。
"""
from __future__ import annotations

import json
from typing import Any, List


PLANNER_SYSTEM_PROMPT = """你负责为会议纪要的各个章节规划合适的信息图表。

规划原则：
1. 保持纪要常态文本：对于全文摘要、会议背景、开场致辞、结论定调、总结回顾、待办事项与行动项等纯叙述或清单内容，必须设为 "none"，保持正文纯文本原貌。
2. 仅在讨论议题具备明确结构化关系时规划视觉，每篇纪要正文通常规划 1~3 个高价值视觉：
   - flow：适合具有明确流转次序、跨环节协同或包含反向回路的闭环演进机制。
   - tree：适合纵向分层体系、多级递进架构或模块树状拓扑。
   - table：适合多方案横向对比、或现状痛点与解法的成对映射。
   - stats：适合多项显著的量化数据提升或指标调优对比。
   - timeline：适合带有明确时间节点的发展沿革或关键里程碑。
3. 输入的每个 section 必须在输出的 sections 中出现一次。
4. 输出纯 JSON 对象。

输出格式：
{
  "sections": [
    {
      "section_id": "string",
      "visual": "none | flow | tree | table | stats | timeline",
      "necessity": 0.85,
      "rationale": "选择该视觉形态的理由",
      "required_data": ["重点抽取的关键信息"]
    }
  ]
}"""


MASTER_SYSTEM_PROMPT = """你负责提炼整篇会议纪要的开篇通览大图（Master Infographic）。

规划原则：
1. 全局统领：提取整场会议的实质性议题脉络，标题（headline）直接反映会议核心主旨，观点（thesis）给出全场定调结论（60字内）。
2. 议题均衡覆盖（blocks）：提炼 2~4 个讨论的核心实质议题，必须均衡覆盖整篇纪要的主体议程：
   - section_ids：对应纪要中的章节编号列表。
   - title：精炼议题名称（15字内）。
   - summary：一句话核心定调或态势（30字内）。
   - key_points：2~3 条事实要点，每条短小精炼（25字内）。
   - highlight：每个议题提取 1 项专属于该议题的核心抓手，包含 tag（成果属性标签，6字内）和 value（核心结论或量化指标，20字内）。若议题包含明确量化指标则提取该指标，若为架构或战略议题则提取最核心的定调成果。严禁从单一议题扎堆提取。
3. 布局形态（layout）：
   - grid：并列议题或业务方向（推荐默认）
   - flow：先后推进流程
   - timeline：时序演进
   - matrix：横向对标
4. 输出纯 JSON 对象。

输出格式：
{
  "headline": "全篇会议核心主旨",
  "thesis": "全场核心定调结论",
  "layout": "grid | flow | timeline | matrix",
  "blocks": [
    {
      "section_ids": ["s2"],
      "title": "议题名称",
      "summary": "核心态势定调",
      "key_points": ["事实要点一", "事实要点二"],
      "highlight": {
        "tag": "成果标签",
        "value": "核心抓手或量化指标"
      }
    }
  ]
}"""


EXTRACTOR_SYSTEM_PROMPT = """你负责从当前章节正文及现场原文中，高保真抽取指定视觉形态所需的结构化数据。

通用要求：
1. 真实忠实：数据与事实全部来自输入文本，不臆造。
2. 语言紧凑：标题与描述使用精炼短句，适合信息图展示。
3. 必须提供 evidence 短句标明出处。
4. 输出纯 JSON 对象。

各形态抽取要求：

【flow（流转步骤与闭环反馈）】：
- nodes：抽取 3~6 个核心步骤节点，包含 node_id、title（步骤名称）、detail（动作描述）、evidence。
- edges：抽取节点间的流向连线（from, to, label）。若存在反向修正、评估反馈或持续迭代等回流回路，将边（edge）的 from 指向反馈发起节点，to 指向受影响的目标节点，并在 label 中注明反馈信号。
格式：
{
  "kind": "flow",
  "title": "流程图标题",
  "data": {
    "nodes": [
      {"node_id": "step_1", "title": "环节名称", "detail": "动作与处理逻辑", "evidence": "出处"},
      {"node_id": "step_2", "title": "环节名称", "detail": "动作与处理逻辑", "evidence": "出处"}
    ],
    "edges": [
      {"from": "step_1", "to": "step_2", "label": "流转或产出说明"}
    ]
  }
}

【tree（分层架构与系统拓扑）】：
- 针对分层架构体系：必须将每一个独立层级或子模块作为单独的 node 输出。
- node_id 分别设为 layer_1, layer_2 等；parent_id 设为 null（平铺层级）或前序依赖层；
- title 为该层级名称；detail 为该层级的具体职责或说明。
格式：
{
  "kind": "tree",
  "title": "架构图标题",
  "data": {
    "nodes": [
      {"node_id": "layer_1", "parent_id": null, "title": "层级名称", "detail": "职责与实现说明", "evidence": "出处"},
      {"node_id": "layer_2", "parent_id": null, "title": "层级名称", "detail": "职责与实现说明", "evidence": "出处"}
    ]
  }
}

【table（结构化对比与映射）】：
- 提取 2~4 个清晰列头（columns）及 2~6 行数据（rows）。
格式：
{
  "kind": "table",
  "title": "表格标题",
  "data": {
    "columns": ["维度名称", "属性一", "属性二"],
    "rows": [{"cells": ["行标题", "内容一", "内容二"], "evidence": "出处"}]
  }
}

【stats（核心量化指标）】：
- 提取 2~5 个关键量化指标。
格式：
{
  "kind": "stats",
  "title": "指标标题",
  "data": {
    "metrics": [{"label": "指标含义", "value": "量化数值", "evidence": "出处"}]
  }
}

【timeline（时序图谱）】：
- 提取 3~6 个按时间顺序排列的事件。
格式：
{
  "kind": "timeline",
  "title": "时间线标题",
  "data": {
    "events": [{"time_label": "时间节点", "title": "事件名称", "detail": "事件说明", "evidence": "出处"}]
  }
}"""


def build_planner_user_prompt(sections: List[dict[str, Any]]) -> str:
    return (
        "请为以下章节规划最适合的视觉形态：\n"
        + json.dumps({"sections": sections}, ensure_ascii=False, indent=2)
    )


def build_extractor_user_prompt(
    section: dict[str, Any],
    decision: dict[str, Any],
    transcript: str,
) -> str:
    return (
        f"请为指定章节抽取 【{decision.get('visual')}】 数据：\n\n"
        f"章节：\n{json.dumps(section, ensure_ascii=False, indent=2)}\n\n"
        f"规划要求：\n{json.dumps(decision, ensure_ascii=False, indent=2)}\n\n"
        f"现场原文参考：\n{transcript or '（无）'}"
    )


def build_master_user_prompt(
    sections: List[dict[str, Any]],
    decisions: List[dict[str, Any]],
) -> str:
    return (
        "请根据以下所有章节信息生成开篇通览大图（Master Infographic）：\n"
        f"章节列表：\n{json.dumps({'sections': sections}, ensure_ascii=False, indent=2)}\n\n"
        f"规划决策：\n{json.dumps({'sections': decisions}, ensure_ascii=False, indent=2)}"
    )


__all__ = [
    "EXTRACTOR_SYSTEM_PROMPT",
    "MASTER_SYSTEM_PROMPT",
    "PLANNER_SYSTEM_PROMPT",
    "build_extractor_user_prompt",
    "build_master_user_prompt",
    "build_planner_user_prompt",
]
