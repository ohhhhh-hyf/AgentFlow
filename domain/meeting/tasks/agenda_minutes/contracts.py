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
from tools.schema.fallback_rules import FallbackRules, Lines, Raw


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
                StrField("status_tag", "议题结论状态标签（如 原则同意、审议通过、待补充、本次未讨论 等）"),
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
- presenter：实际现场汇报人（如现场由某专家实际汇报则填写其真实姓名，若为主讲人则填法定汇报人）
- status_tag：议题结论状态标签（如 原则同意、审议通过、技术共识、待补充材料、本次未讨论 等）
- target_and_audience：1. 目标与对象（为什么开、面向受众、明确排除项）
- content_and_evidence：2. 内容与依据（改动点、量化指标、方案事实）
- process_and_interaction：3. 过程与互动（争议焦点、评委质询、释疑论据，指名道姓保留真实发言人）
- conclusion_and_status：4. 结论与状态（自然语言陈述最终口径、生效约束红线、未决卡点）
- action_items：5. 行动与效果
- action_items[].owner：跟进责任人/单位
- action_items[].task：具体执行事项、闭环动作或交付物
- action_items[].deadline：完成时限节点或排期安排"""


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
]
