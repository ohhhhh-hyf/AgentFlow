"""agenda_minutes contract definitions.

Required by tools/codegen/sync_domain.py:
- class AgendaMinutesGenerationContract(GenerationContract)
- class AgendaMinutesSupervisorContract(SupervisorContract)
- AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT = AgendaMinutesGenerationContract.to_output_contract()
- AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT = AgendaMinutesSupervisorContract.to_output_contract()

Optional fallback:
- class AgendaMinutesFallbackRules(FallbackRules)
- AGENDA_MINUTES_FALLBACK_RULES = AgendaMinutesFallbackRules()
"""
from __future__ import annotations

from tools.schema.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    ObjField,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.schema.fallback_rules import FallbackRules


class AgendaMinutesGenerationContract(GenerationContract):
    """议程驱动型会议纪要生成契约（通用全景五要素架构）。"""

    fields = [
        ObjField(
            "meeting_meta",
            [
                StrField("theme", "会议主题全称"),
                StrField("date_time", "会议起止时间与主持人"),
                StrField("attendees_summary", "与会人员概况（包含全程参与人与分段参与人）"),
                StrField("overview_headline", "全会议程推进总体评价与核心结论摘要"),
                StrField("agenda_stats", "议题完成度统计（如：既定议题共4项，已审议2项，未讨论2项，临时追加1项）"),
            ],
            desc="全会基本信息与议程大盘总览",
        ),
        ObjListField(
            "agenda_items",
            [
                StrField("agenda_seq", "原议题序号（如 01, 02）"),
                StrField("agenda_title", "既定议程议题全称（严格以会前议程单 txt 为准，保持字面完全一致）"),
                StrField("presenter", "汇报人与责任团队/部门"),
                StrField("agenda_category", "议题属性分类：approval=评审审批类；share=知识分享与技术研讨类；consensus=协同拉通与排期对齐类"),
                StrField("status_tag", "议题结论定调（评审类：审议通过、有条件通过、未通过；协同类：达成共识、存在分歧；分享类：直接留空；未讨论统一为：本次未讨论）"),
                StrField("time_range", "议题原声时间戳区间/时长（如 00:10 ~ 00:24，未讨论为 —）"),
                StrListField("target_and_audience", "1. 目标与对象（为什么开、面向谁、期望发生什么变化、验收标准）"),
                StrListField("content_and_evidence", "2. 内容与依据（改动点、量化指标、方案事实）"),
                StrListField("process_and_interaction", "3. 过程与互动（争议焦点、评委质询、释疑论据）"),
                StrField("conclusion_and_status", "4. 结论与状态（自然语言陈述最终口径、生效约束红线、未决卡点）"),
                ObjListField(
                    "action_items",
                    [
                        StrField("owner", "跟进责任人/单位"),
                        StrField("task", "具体执行事项、闭环动作或验证探索"),
                        StrField("deadline", "完成时限节点或排期安排"),
                    ],
                    desc="5. 行动与效果",
                ),
                StrField("discussion_state", "讨论真实性标记：discussed=现场充分讨论；skipped=本次未讨论/录音未见提及"),
                # 兼容旧字段别名
                StrListField("proposal_highlights", "兼容旧字段：方案背景与核心诉求"),
                ObjField(
                    "deliberation_details",
                    [
                        StrListField("key_metrics", "硬核论据与量化指标"),
                        StrListField("feedback_concerns", "讨论交锋与各方反馈"),
                    ],
                    desc="兼容旧字段：研讨过程与关键论据",
                ),
                StrField("resolution", "兼容旧字段：最终定调与决议共识"),
                ObjListField(
                    "action_commitments",
                    [
                        StrField("owner", "跟进责任人/单位"),
                        StrField("task", "具体执行事项"),
                        StrField("deadline", "完成时限节点"),
                    ],
                    desc="兼容旧字段：后续行动与跟进责任",
                ),
            ],
            desc="既定议程逐项审议与研讨详情列表（按议程单序号严格逐项对齐）",
        ),
        ObjListField(
            "adhoc_items",
            [
                StrField("title", "临时追加议题/重要定调标题"),
                StrField("speaker", "定调领导/发言人"),
                StrField("content", "指示背景与核心决议要求"),
                StrField("action", "督办要求与牵头责任人"),
            ],
            desc="议程外临时追加事项或全局重要指示（若无则为空列表）",
        ),
    ]


class AgendaMinutesSupervisorContract(SupervisorContract):
    """议程驱动纪要领域审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空列表 []")
    checks = [
        Check("agenda_coverage_check", "议程覆盖与骨架核对：检查是否严格以会前议程单为骨架基准，不得篡改或遗漏议题。严格以议程单指定的法定汇报人为准，若法定汇报人未发言则议题如实标为 skipped，不得因孤立标题误判"),
        Check("grounding_facts_check", "现场事实与量化核对：检查各项参数、时延指标、发言人是否与现场实录严格一致，杜绝张冠李戴与伪造"),
        Check("decision_fidelity_check", "定调与共识核对：检查定调标签与结论是否准确反映现场权威拍板或技术研讨真实共识，附带约束条件不得遗漏"),
    ]


AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT = AgendaMinutesGenerationContract.to_output_contract()
AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT = AgendaMinutesSupervisorContract.to_output_contract()


SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT = """{
  "agenda_category": "approval",
  "presenter": "",
  "status_tag": "",
  "target_and_audience": [],
  "content_and_evidence": [],
  "process_and_interaction": [],
  "conclusion_and_status": "",
  "action_items": [
    {
      "owner": "",
      "task": "",
      "deadline": ""
    }
  ]
}

字段说明：
- agenda_category：议题属性分类，必须为以下三项之一：
  * "approval"：评审审批类（版本发布、准入、验收、立项审查等需过会表决定调的议题）
  * "share"：知识分享与学术研讨类（学术报告、前沿分享、技术讲座、调研洞察等纯知识同步无需表决的议题）
  * "consensus"：协同拉通与排期对齐类（跨团队协同、接口对齐、排期协商、分歧磋商等拉通共识的议题）
- presenter：实际现场汇报人（如现场由某专家实际汇报则填写其真实姓名，若为主讲人则填法定汇报人）
- status_tag：议题结论定调：
  * 若 agenda_category 为 "approval"：严格限定为 ["审议通过", "有条件通过", "未通过", "本次未讨论"] 之一
  * 若 agenda_category 为 "consensus"：严格限定为 ["达成共识", "存在分歧", "本次未讨论"] 之一
  * 若 agenda_category 为 "share"：直接填空字符串 ""（无需审批状态，不盖章；若整场未讨论则填 "本次未讨论"）
- target_and_audience：1. 目标与对象（为什么开、面向受众、明确排除项）
- content_and_evidence：2. 内容与依据（改动点、量化指标、方案事实）
- process_and_interaction：3. 过程与互动（争议焦点、评委质询、释疑论据，指名道姓保留真实发言人）
- conclusion_and_status：4. 结论与状态 / 核心认知与沉淀（若为分享类重点提炼核心认知与经验沉淀 Takeaways；若为评审/协同类陈述最终口径、约束红线或共识卡点）
- action_items：5. 行动与效果
- action_items[].owner：跟进责任人/单位
- action_items[].task：具体执行事项、闭环动作或交付物
- action_items[].deadline：完成时限节点或排期安排"""

import re
from typing import Any

STATUS_TAG_APPROVED = "审议通过"
STATUS_TAG_CONDITIONAL = "有条件通过"
STATUS_TAG_REJECTED = "未通过"
STATUS_TAG_CONSENSUS = "达成共识"
STATUS_TAG_DIVERGENCE = "存在分歧"
STATUS_TAG_SKIPPED = "本次未讨论"
STATUS_TAG_EMPTY = ""

STANDARD_STATUS_TAGS = [
    STATUS_TAG_APPROVED,
    STATUS_TAG_CONDITIONAL,
    STATUS_TAG_REJECTED,
    STATUS_TAG_CONSENSUS,
    STATUS_TAG_DIVERGENCE,
    STATUS_TAG_SKIPPED,
    STATUS_TAG_EMPTY,
]


def normalize_status_tag(tag: Any, category: str = "approval", is_skipped: bool = False) -> str:
    """归一化结论定调。

    根据议题类别 (approval / share / consensus) 与现场讨论状态，归一化定调标签：
    - is_skipped=True: 恒为 "本次未讨论"
    - share (分享类): 恒为 "" (空字符串，留空不盖章；未讨论为 "本次未讨论")
    - consensus (协同类): ["达成共识", "存在分歧"]
    - approval (评审类) 及兜底: ["审议通过", "有条件通过", "未通过"]
    """
    if is_skipped:
        return STATUS_TAG_SKIPPED

    cat = str(category or "approval").strip().lower()
    if cat not in ("approval", "share", "consensus"):
        cat = "approval"

    if cat == "share":
        if not tag:
            return STATUS_TAG_EMPTY
        s_raw = str(tag).strip()
        if any(k in s_raw for k in ("未讨论", "跳过", "skipped")):
            return STATUS_TAG_SKIPPED
        return STATUS_TAG_EMPTY

    if not tag:
        if cat == "consensus":
            return STATUS_TAG_CONSENSUS
        return STATUS_TAG_APPROVED

    s = str(tag).strip()
    s_clean = re.sub(r"^[\[【（(]\s*|\s*[\]】）)]$", "", s).strip()
    if not s_clean:
        if cat == "consensus":
            return STATUS_TAG_CONSENSUS
        return STATUS_TAG_APPROVED

    if "未讨论" in s_clean or "跳过" in s_clean or "skipped" in s_clean.lower():
        return STATUS_TAG_SKIPPED

    if cat == "consensus":
        if any(k in s_clean for k in ("分歧", "争议", "未达成", "未对齐", "再议", "待拉通", "未通过", "否决")):
            return STATUS_TAG_DIVERGENCE
        return STATUS_TAG_CONSENSUS

    # 评审类 (approval) 及默认
    if any(k in s_clean for k in ("未通过", "待补充", "补充材料", "材料", "延期", "再议", "否决", "不通过", "打回", "暂停")):
        return STATUS_TAG_REJECTED
    if any(k in s_clean for k in ("条件", "原则", "共识", "认可", "建议", "预研")):
        return STATUS_TAG_CONDITIONAL
    if any(k in s_clean for k in ("通过", "放行", "同意", "采纳", "批准")):
        return STATUS_TAG_APPROVED
    return STATUS_TAG_APPROVED


class AgendaMinutesFallbackRules(FallbackRules):
    """议程驱动纪要降级拼装规则。"""

    sections: list = []
    empty_text = "未解析到有效议题纪要。"
    structured = {"field": "agenda_items"}


AGENDA_MINUTES_FALLBACK_RULES = AgendaMinutesFallbackRules()

__all__ = [
    "AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT",
    "AGENDA_MINUTES_SUPERVISOR_OUTPUT_CONTRACT",
    "SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT",
    "AGENDA_MINUTES_FALLBACK_RULES",
    "STATUS_TAG_APPROVED",
    "STATUS_TAG_CONDITIONAL",
    "STATUS_TAG_REJECTED",
    "STATUS_TAG_CONSENSUS",
    "STATUS_TAG_DIVERGENCE",
    "STATUS_TAG_SKIPPED",
    "STATUS_TAG_EMPTY",
    "STANDARD_STATUS_TAGS",
    "normalize_status_tag",
]
