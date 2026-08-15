"""review 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    EnumField,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class ReviewGenerationContract(GenerationContract):
    """笔记审查输出契约。"""

    fields = [
        ObjListField(
            "knowledge_points",
            [
                StrField("title", "知识点标题，用原文术语"),
                StrField("evidence", "原文中支撑该知识点的原句或片段"),
                EnumField(
                    "complete",
                    ["yes", "partial", "no"],
                    "yes=记录完整；partial=缺步骤/条件/例子；no=几乎只有名词",
                ),
            ],
        ),
        ObjListField(
            "issues",
            [
                StrField(
                    "quote",
                    "必须逐字出自笔记原文的片段，用于左侧高亮；找不到原句则不要编造",
                ),
                EnumField(
                    "kind",
                    [
                        "incomplete",
                        "confusing",
                        "missing_condition",
                        "missing_example",
                        "inaccurate",
                    ],
                    "incomplete=记录不完整；confusing=概念易混；"
                    "missing_condition=公式缺适用条件；missing_example=建议补例题；"
                    "inaccurate=表述不准确",
                ),
                StrField("problem", "问题一句话，≤30 字"),
                StrField("analysis", "问题在哪里、为什么不对或不完整"),
                StrField("suggestion", "应如何改或补，不引入原文没有的新章节"),
            ],
        ),
        StrField(
            "corrected_notes",
            "按审查结果重写的完整笔记：只改清单里的问题，保留原文结构与术语",
        ),
    ]


class ReviewSupervisorContract(SupervisorContract):
    """笔记审查审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check(
            "review_check",
            "仅记录严重问题：quote 对不上原文、编造知识点或问题、"
            "把完整正确的内容标成错误、订正笔记引入原文没有的新章节",
        ),
    ]


REVIEW_GENERATION_OUTPUT_CONTRACT = ReviewGenerationContract.to_output_contract()
REVIEW_SUPERVISOR_OUTPUT_CONTRACT = ReviewSupervisorContract.to_output_contract()


class ReviewFallbackRules(FallbackRules):
    """笔记审查降级拼装：保留问题列表。"""

    sections = [
        Lines("issues"),
    ]
    empty_text = "暂未发现可审查的笔记问题"
    structured = {"field": "issues"}


REVIEW_FALLBACK_RULES = ReviewFallbackRules()

__all__ = [
    "REVIEW_FALLBACK_RULES",
    "REVIEW_GENERATION_OUTPUT_CONTRACT",
    "REVIEW_SUPERVISOR_OUTPUT_CONTRACT",
]
