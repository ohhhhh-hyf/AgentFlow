"""mindmap 的契约定义（prompt 文本见 prompts.py）。

思维导图线的草稿 = 会议内容的 Markdown 大纲（title + outline），
outline 是 markmap 的直接输入（标题层级 + 列表项），零转换。
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, Feedback, GenerationContract, StrField, SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Raw


class MindmapGenerationContract(GenerationContract):
    """思维导图大纲生成输出契约。"""

    fields = [
        StrField(
            "title",
            "思维导图根节点标题，即会议主题；来自会议原文或会议理解结果",
        ),
        StrField(
            "outline",
            "Markdown 大纲正文：用标题层级（# 根节点 / ## 主分支 / ### 子分支）"
            "和列表项表达会议要点，是思维导图的直接输入；"
            "只写会议原文明确出现的内容，宁缺毋滥",
        ),
    ]


class MindmapSupervisorContract(SupervisorContract):
    """思维导图大纲审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check(
            "mindmap_check",
            "仅记录严重问题：大纲出现原文不存在的事实、层级结构明显失实、"
            "遗漏关键决策/待办/风险",
        ),
    ]


MINDMAP_GENERATION_OUTPUT_CONTRACT = MindmapGenerationContract.to_output_contract()
MINDMAP_SUPERVISOR_OUTPUT_CONTRACT = MindmapSupervisorContract.to_output_contract()


class MindmapFallbackRules(FallbackRules):
    """思维导图降级拼装：保留大纲原文（outline 是单字符串字段）。"""

    sections = [
        Raw("outline"),
    ]
    empty_text = "暂无思维导图大纲"


MINDMAP_FALLBACK_RULES = MindmapFallbackRules()

__all__ = [
    "MINDMAP_GENERATION_OUTPUT_CONTRACT",
    "MINDMAP_SUPERVISOR_OUTPUT_CONTRACT",
    "MINDMAP_FALLBACK_RULES",
]
