"""risk 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from core.schema.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, SupervisorContract,
)
from core.schema.fallback_rules import FallbackRules, Lines


class RiskGenerationContract(GenerationContract):
    """风险分析输出契约。"""

    fields = [
        ObjListField("risks", [
            StrField("category", "该风险所属的宏观业务领域/风险大类组标题（直接沿用所属议题的module或title，全场会议聚拢为3~5个宏观组标题，如'核心系统稳定性'、'防汛与排水隐患'，严禁针对单条风险提取微小标题，同议题隐患必须共用相同组标题）"),
            StrField("risk", "风险描述，必须来自会议原文或会议理解结果"),
            StrField("source", "风险来源：原文依据或相关议题"),
            EnumField("severity", ["high", "medium", "low"]),
            StrField("impact", "如果风险发生，可能造成的潜在危害或不良业务后果；原文未提及为null"),
            StrField("mitigation", "原文中明确商讨的应对措施（单一大字段一体化陈述）；现场未讨论则为null"),
            StrField("owner", "原文明示的跟踪责任人或团队；未指派则为null"),
        ]),
    ]


class RiskSupervisorContract(SupervisorContract):
    """风险分析审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("risk_check", "仅记录严重问题"),
    ]


RISK_GENERATION_OUTPUT_CONTRACT = RiskGenerationContract.to_output_contract()
RISK_SUPERVISOR_OUTPUT_CONTRACT = RiskSupervisorContract.to_output_contract()


class RiskFallbackRules(FallbackRules):
    """风险分析降级拼装：保留结构化 risks。"""

    sections = [
        Lines("risks"),
    ]
    empty_text = "暂无明确风险事项"
    structured = {"field": "risks"}


RISK_FALLBACK_RULES = RiskFallbackRules()

__all__ = [
    "RISK_GENERATION_OUTPUT_CONTRACT",
    "RISK_SUPERVISOR_OUTPUT_CONTRACT",
    "RISK_FALLBACK_RULES",
]
