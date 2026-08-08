"""minutes_generation 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类 MinutesGenerationContract → to_json_template() 生成生成契约 prompt
- 审阅契约类 MinutesSupervisorContract → to_json_template() 生成审阅契约 prompt
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, Feedback, GenerationContract, StrField, StrListField,
    SupervisorContract,
)


class MinutesGenerationContract(GenerationContract):
    """纪要草稿输出契约。"""

    fields = [
        StrField("headline", "会议纪要标题"),
        StrListField("executive_summary", "概述要点（通常2-3条，内容不足时不强求，每条1-2句）"),
        StrListField("key_decisions", "决策（来自MeetingUnderstanding.decisions，列出全量，不要筛选）"),
        StrListField("personally_relevant_points", "执行要点（有明确分工则写，无则[]，每条一句）"),
        StrListField("risks_and_blockers", "风险（每条一句，无则[]）"),
        StrListField("unresolved_questions", "未决问题（每条一句，无则[]）"),
    ]


class MinutesSupervisorContract(SupervisorContract):
    """纪要审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check("facts_check", "仅记录严重问题，轻微问题不记录"),
        Check("perspective_check", "仅记录严重问题"),
        Check("consistency_check", "仅记录严重问题"),
    ]


MINUTES_GENERATION_OUTPUT_CONTRACT = MinutesGenerationContract.to_json_template()
MINUTES_SUPERVISOR_OUTPUT_CONTRACT = MinutesSupervisorContract.to_json_template()

__all__ = [
    "MINUTES_GENERATION_OUTPUT_CONTRACT",
    "MINUTES_SUPERVISOR_OUTPUT_CONTRACT",
]
