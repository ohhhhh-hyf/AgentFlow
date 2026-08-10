"""risk 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class RiskGenerationContract(GenerationContract):
    """风险分析输出契约。"""

    fields = [
        ObjListField("risks", [
            StrField("risk", "风险描述，必须来自会议原文或会议理解结果"),
            StrField("source", "风险来源：原文依据或相关议题"),
            EnumField("severity", ["high", "medium", "low"]),
            StrField("impact", "如果风险发生，可能造成的影响"),
            StrField("mitigation", "原文中已有的应对措施；没有则为null"),
            StrField("owner", "原文明示的负责人；没有则为null"),
        ]),
    ]


class RiskSupervisorContract(SupervisorContract):
    """风险分析审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check("risk_check", "仅记录严重问题"),
    ]


RISK_GENERATION_OUTPUT_CONTRACT = RiskGenerationContract.to_json_template()
RISK_SUPERVISOR_OUTPUT_CONTRACT = RiskSupervisorContract.to_json_template()


class RiskFallbackRules(FallbackRules):
    """风险分析降级拼装：保留结构化 risks。"""

    sections = [
        Lines("risks"),
    ]
    empty_text = "暂无明确风险"
    structured = {"field": "risks"}


RISK_FALLBACK_RULES = RiskFallbackRules()

__all__ = [
    "RISK_GENERATION_OUTPUT_CONTRACT",
    "RISK_SUPERVISOR_OUTPUT_CONTRACT",
    "RISK_FALLBACK_RULES",
]
