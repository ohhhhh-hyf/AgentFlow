"""Shared perspective modeling contract definitions."""
from __future__ import annotations

from tools.contracts import (
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
        StrField("inferred_role", "Role inferred from source evidence"),
        StrListField("responsibilities", "Responsibilities relevant to this input"),
        StrListField("goals", "Goals relevant to this input"),
        StrListField("concerns", "Risks, uncertainties, or concerns to track"),
        StrListField("relevant_topics", "Topics directly relevant to the user or objective view"),
        StrListField("evidence", "Specific source evidence supporting the model"),
        StrField(
            "personal_summary",
            "2-4 sentence summary of what matters most to the user "
            "(or to the whole team in objective mode) in this input; "
            "an anchor downstream agents can quote directly",
        ),
        StrListField(
            "attention_points",
            "3-8 concrete items in this input most important to the user, "
            "each anchored to source text (paraphrase-free); cover each "
            "profile focus class that has source evidence",
        ),
        StrListField(
            "possible_actions",
            "Actions the user may need or be expected to take, inferred from "
            "profile + source; each item states its basis; objective mode: "
            "team-wide actions",
        ),
        StrListField(
            "preference_signals",
            "Inferred preference signals from profile + source "
            "(e.g. values progress / quality / cost / risk-avoidance / "
            "collaboration); each with basis; empty if no signal",
        ),
        StrListField(
            "stakeholders",
            "Parties, roles, or groups involved in or affected by this input "
            "(objective mode: all involved parties without favoritism; "
            "personal mode: those interacting with the user); "
            "empty if none",
        ),
        StrListField(
            "conclusions",
            "Key conclusions or decisions stated in the input, each anchored "
            "to source text (paraphrase-free); empty if the input states none",
        ),
        StrListField(
            "open_questions",
            "Questions left unanswered, unresolved items, or points needing "
            "follow-up in the input; empty if none",
        ),
        StrListField(
            "data_gaps",
            "Information missing, incomplete, or ambiguous in the input that "
            "matters to the view (e.g. missing owner, deadline, evidence, "
            "context); empty if none",
        ),
    ]


PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT = (
    PerspectiveModelingGenerationContract.to_output_contract()
)

__all__ = [
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
]
