"""Shared perspective modeling contract definitions."""
from __future__ import annotations

from core.schema.contracts import (
    EnumField, GenerationContract, StrField, StrListField,
)


class PerspectiveModelingGenerationContract(GenerationContract):
    """Perspective modeling output contract.

    深度视角模型：不仅回答"用户是谁"，还回答"在这份输入里用户关心什么、
    会怎么理解、可能需要做什么、有哪些偏好信号"，供下游各任务线直接使用。
    字段定义顺序仅供参考（生成器会把无默认值的必填字段排在可选字段之前），
    新增字段不影响既有字段语义。
    """

    fields = [
        EnumField("confidence", ["high", "medium", "low"]),
        StrField("name", "User name; empty when unavailable or objective mode"),
        StrField(
            "personal_summary",
            "100-150字作战概览：立足核心承接事项与上下游协同卡点，紧凑具体，可被下游直接引用",
        ),
        StrListField(
            "attention_points",
            "3-8 concrete items in this input most important to the user, anchored to source text",
        ),
        StrListField(
            "possible_actions",
            "Actions the user needs or is expected to take, marked with 「原文承诺」 or inferred basis",
        ),
        StrListField("concerns", "Risks, uncertainties, or personal concerns to track"),
        StrListField("evidence", "Specific source evidence supporting the model"),
        StrListField("responsibilities", "Responsibilities relevant to this input"),
        StrListField("relevant_topics", "Topics directly relevant to the user"),
        StrListField(
            "open_questions",
            "Unresolved questions or alignment items the user needs to follow up after meeting",
        ),
        StrListField(
            "data_gaps",
            "External dependencies or missing materials blocking the user delivery",
        ),
    ]


PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT = (
    PerspectiveModelingGenerationContract.to_output_contract()
)

__all__ = [
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
]
