"""Shared perspective modeling contract definitions."""
from __future__ import annotations

from tools.contracts import (
    EnumField, GenerationContract, StrField, StrListField,
)


class PerspectiveModelingGenerationContract(GenerationContract):
    """Perspective modeling output contract."""

    fields = [
        EnumField("confidence", ["high", "medium", "low"]),
        StrField("name", "User name; empty when unavailable or objective mode"),
        StrField("inferred_role", "Role inferred from source evidence"),
        StrListField("responsibilities", "Responsibilities relevant to this input"),
        StrListField("goals", "Goals relevant to this input"),
        StrListField("concerns", "Risks, uncertainties, or concerns to track"),
        StrListField("relevant_topics", "Topics directly relevant to the user or objective view"),
        StrListField("evidence", "Specific source evidence supporting the model"),
    ]


PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT = (
    PerspectiveModelingGenerationContract.to_json_template()
)

__all__ = [
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
]
