from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Literal

from .validation import (
    OutputValidationError,
    _action,
    _choice,
    _exact_fields,
    _review_check,
    _string,
    _string_list,
)


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
    # "objective" = 全会客观视角；缺省或其它值 = 具体用户视角
    perspective: str | None = None


def is_objective_perspective(user: UserIdentity | dict | None) -> bool:
    """画像 perspective 为 objective 时走客观纪要/待办口径。"""
    if user is None:
        return False
    data = user.model_dump() if hasattr(user, "model_dump") else dict(user)
    return str(data.get("perspective") or "").strip().lower() == "objective"


# ── 业务数据模型（每个都自带 validate 类方法） ──────────────────────

@dataclass
class MeetingUnderstanding(ModelMixin):
    meeting_purpose: str
    topics: list[dict[str, Any]]
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MeetingUnderstanding":
        _exact_fields(
            data,
            [f.name for f in fields(cls)],
            cls.__name__,
        )
        _string(data["meeting_purpose"], "meeting_purpose")
        if not isinstance(data["topics"], list):
            raise OutputValidationError("topics 必须是对象数组")
        for index, topic in enumerate(data["topics"]):
            path = f"topics[{index}]"
            _exact_fields(
                topic,
                {"title", "discussion", "conclusion", "participants"},
                path,
            )
            _string(topic["title"], f"{path}.title")
            _string(topic["discussion"], f"{path}.discussion")
            _string(topic["conclusion"], f"{path}.conclusion", nullable=True)
            _string_list(topic["participants"], f"{path}.participants")
        for key in ("decisions", "open_questions", "risks"):
            _string_list(data[key], key)
        return cls(**data)


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

    @classmethod
    def validate(cls, data: dict) -> "PerspectiveProfile":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        _string(data["name"], "name", nullable=True)
        _string(data["inferred_role"], "inferred_role", nullable=True)
        for key in (
            "responsibilities", "goals", "concerns",
            "relevant_topics", "evidence",
        ):
            _string_list(data[key], key)
        return cls(**data)


@dataclass
class PersonalizedMinutes(ModelMixin):
    headline: str
    executive_summary: list[str]
    key_decisions: list[str] = field(default_factory=list)
    personally_relevant_points: list[str] = field(default_factory=list)
    risks_and_blockers: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "PersonalizedMinutes":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["headline"], "headline")
        for key in (
            "executive_summary", "key_decisions", "personally_relevant_points",
            "risks_and_blockers", "unresolved_questions",
        ):
            _string_list(data[key], key)
        return cls(**data)


@dataclass
class ActionItems(ModelMixin):
    my_actions: list[dict[str, Any]] = field(default_factory=list)
    delegated_actions: list[dict[str, Any]] = field(default_factory=list)
    unassigned_actions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "ActionItems":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in ("my_actions", "delegated_actions", "unassigned_actions"):
            if not isinstance(data[key], list):
                raise OutputValidationError(f"{key} 必须是数组")
            for index, item in enumerate(data[key]):
                _action(item, f"{key}[{index}]")
        return cls(**data)


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

    @classmethod
    def validate(cls, data: dict) -> "SupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)

        decisions = {
            "approve", "revise_minutes", "revise_actions",
            "revise_both", "reject",
        }
        _choice(data["decision"], decisions, "decision")

        check_keys = (
            "facts_check", "perspective_check",
            "action_items_check", "consistency_check",
        )
        for key in check_keys:
            _review_check(data[key], key)

        _string_list(data["minutes_feedback"], "minutes_feedback")
        _string_list(data["actions_feedback"], "actions_feedback")

        failed = [
            key for key in check_keys
            if data[key]["status"] == "fail"
        ]
        if data["decision"] == "approve" and failed:
            raise OutputValidationError(
                f"decision=approve 时检查项不得失败：{failed}"
            )
        if data["decision"] == "approve" and (
            data["minutes_feedback"] or data["actions_feedback"]
        ):
            raise OutputValidationError("decision=approve 时返工意见必须为空")
        if data["decision"] in {"revise_minutes", "revise_both"} and not data[
            "minutes_feedback"
        ]:
            raise OutputValidationError("纪要返工决定必须提供 minutes_feedback")
        if data["decision"] in {"revise_actions", "revise_both"} and not data[
            "actions_feedback"
        ]:
            raise OutputValidationError("待办返工决定必须提供 actions_feedback")
        if data["decision"] == "reject" and not failed:
            raise OutputValidationError("decision=reject 时至少一个检查项必须失败")

        return cls(**data)


@dataclass
class FinalReport(ModelMixin):
    title: str
    personalized_minutes: str
    action_items: list[dict[str, Any]] = field(default_factory=list)
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None

    @classmethod
    def validate(cls, data: dict) -> "FinalReport":
        # quality_warning 仅系统附加，LLM 不必输出；其余三字段必填
        allowed = {"title", "personalized_minutes", "action_items", "quality_warning"}
        required = {"title", "personalized_minutes", "action_items"}

        if not isinstance(data, dict):
            raise OutputValidationError("FinalReport 必须是 JSON 对象")

        actual = set(data)
        if not required.issubset(actual):
            raise OutputValidationError(
                f"FinalReport 字段不一致：缺失={sorted(required - actual)}"
            )
        extra = actual - allowed
        if extra:
            raise OutputValidationError(
                f"FinalReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data["title"], "title")
        _string(data["personalized_minutes"], "personalized_minutes")
        if not isinstance(data["action_items"], list):
            raise OutputValidationError("action_items 必须是数组")
        for index, item in enumerate(data["action_items"]):
            _action(item, f"action_items[{index}]")
        if "quality_warning" in data and data["quality_warning"] is not None:
            _string(data["quality_warning"], "quality_warning")

        # 标准化：只保留四个合法字段
        return cls(
            title=data["title"],
            personalized_minutes=data["personalized_minutes"],
            action_items=data["action_items"],
            quality_warning=data.get("quality_warning"),
        )
