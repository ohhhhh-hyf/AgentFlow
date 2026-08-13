"""points 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, StrListField, SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class PointsGenerationContract(GenerationContract):
    """知识点总结输出契约。"""

    fields = [
        ObjListField("points", [
            StrField("title", "知识点标题"),
            StrField("summary", "知识点的一句话总结"),
            StrField("explanation", "对知识点的解释，避免只复制原文"),
            StrField("evidence", "原文中支撑该知识点的具体语句或片段"),
            EnumField("importance", ["high", "medium", "low"]),
            StrListField("review_questions", "用于复习该知识点的问题"),
        ]),
    ]


class PointsSupervisorContract(SupervisorContract):
    """知识点总结审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check("points_check", "仅记录严重问题"),
    ]


POINTS_GENERATION_OUTPUT_CONTRACT = PointsGenerationContract.to_output_contract()
POINTS_SUPERVISOR_OUTPUT_CONTRACT = PointsSupervisorContract.to_output_contract()


class PointsFallbackRules(FallbackRules):
    """知识点总结降级拼装：保留结构化 points。"""

    sections = [
        Lines("points"),
    ]
    empty_text = "暂无明确知识点"
    structured = {"field": "points"}


POINTS_FALLBACK_RULES = PointsFallbackRules()

__all__ = [
    "POINTS_GENERATION_OUTPUT_CONTRACT",
    "POINTS_SUPERVISOR_OUTPUT_CONTRACT",
    "POINTS_FALLBACK_RULES",
]