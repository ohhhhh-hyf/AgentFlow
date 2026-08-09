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
from tools.fallback_rules import FallbackRules, Join, Raw


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

# 降级拼装规则（声明式类）：fallback 节点由 sync_contracts.py 检测子类后生成
class MinutesFallbackRules(FallbackRules):
    """纪要降级拼装：headline + 5 段（带标签）+ 免责声明。"""

    sections = [
        Raw("headline"),
        Join("executive_summary", "会议要点"),
        Join("key_decisions", "关键决策"),
        Join(
            "personally_relevant_points",
            label={"objective": "全员执行要点", "personal": "职责相关事项"},
        ),
        Join("risks_and_blockers", "风险与阻塞"),
        Join("unresolved_questions", "未决问题"),
    ]
    empty_prefix = "系统未能通过质量审核，以下为基于现有材料的粗略整理。"
    empty_text = "请直接参考会议原文。"
    empty_purpose = True
    disclaimer = True


MINUTES_FALLBACK_RULES = MinutesFallbackRules()

__all__ = [
    "MINUTES_GENERATION_OUTPUT_CONTRACT",
    "MINUTES_SUPERVISOR_OUTPUT_CONTRACT",
    "MINUTES_FALLBACK_RULES",
]
