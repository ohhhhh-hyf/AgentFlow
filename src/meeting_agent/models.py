from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class ModelMixin:
    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UserIdentity(ModelMixin):
    name: str | None = None
    role: str | None = None
    department: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    context: str | None = None


@dataclass
class MeetingUnderstanding(ModelMixin):
    meeting_purpose: str
    topics: list[dict[str, Any]]
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class PerspectiveProfile(ModelMixin):
    confidence: Literal["high", "medium", "low"]
    name: str | None = None
    inferred_role: str | None = None
    responsibilities: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    relevant_topics: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class PersonalizedMinutes(ModelMixin):
    headline: str
    executive_summary: list[str]
    key_decisions: list[str] = field(default_factory=list)
    personally_relevant_points: list[str] = field(default_factory=list)
    risks_and_blockers: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)


@dataclass
class ActionItems(ModelMixin):
    my_actions: list[dict[str, Any]] = field(default_factory=list)
    delegated_actions: list[dict[str, Any]] = field(default_factory=list)
    unassigned_actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SupervisorReview(ModelMixin):
    decision: Literal[
        "approve",
        "revise_minutes",
        "revise_actions",
        "revise_both",
        "reject",
    ]
    facts_check: dict[str, Any]
    perspective_check: dict[str, Any]
    action_items_check: dict[str, Any]
    consistency_check: dict[str, Any]
    minutes_feedback: list[str] = field(default_factory=list)
    actions_feedback: list[str] = field(default_factory=list)


@dataclass
class FinalReport(ModelMixin):
    title: str
    personalized_minutes: str
    action_items: list[dict[str, Any]] = field(default_factory=list)
