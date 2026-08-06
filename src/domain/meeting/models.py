from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Annotated, Any, Literal, TypedDict

from tools.validation import (
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
class MinutesSupervisorReview(ModelMixin):
    """纪要任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    facts_check: dict[str, Any]
    perspective_check: dict[str, Any]
    consistency_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MinutesSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)

        _choice(data["decision"], {"approve", "revise", "reject"}, "decision")

        check_keys = (
            "facts_check", "perspective_check", "consistency_check",
        )
        for key in check_keys:
            _review_check(data[key], key)

        _string_list(data["feedback"], "feedback")

        failed = [
            key for key in check_keys
            if data[key]["status"] == "fail"
        ]
        if data["decision"] == "approve" and failed:
            raise OutputValidationError(
                f"decision=approve 时检查项不得失败：{failed}"
            )
        if data["decision"] == "approve" and data["feedback"]:
            raise OutputValidationError("decision=approve 时返工意见必须为空")
        if data["decision"] == "revise" and not data["feedback"]:
            raise OutputValidationError("revise 决定必须提供 feedback")
        if data["decision"] == "reject" and not failed:
            raise OutputValidationError("decision=reject 时至少一个检查项必须失败")

        return cls(**data)


@dataclass
class ActionsSupervisorReview(ModelMixin):
    """待办任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    action_items_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "ActionsSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)

        _choice(data["decision"], {"approve", "revise", "reject"}, "decision")

        _review_check(data["action_items_check"], "action_items_check")
        _string_list(data["feedback"], "feedback")

        failed = data["action_items_check"]["status"] == "fail"
        if data["decision"] == "approve" and failed:
            raise OutputValidationError("decision=approve 时检查项不得失败")
        if data["decision"] == "approve" and data["feedback"]:
            raise OutputValidationError("decision=approve 时返工意见必须为空")
        if data["decision"] == "revise" and not data["feedback"]:
            raise OutputValidationError("revise 决定必须提供 feedback")
        if data["decision"] == "reject" and not failed:
            raise OutputValidationError("decision=reject 时至少一个检查项必须失败")

        return cls(**data)


@dataclass
class MinutesReport(ModelMixin):
    """纪要输出（与待办输出分离，各自独立）。"""

    title: str
    personalized_minutes: str
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None

    @classmethod
    def validate(cls, data: dict) -> "MinutesReport":
        # quality_warning 仅系统附加，LLM 不必输出；title 与纪要正文必填
        allowed = {"title", "personalized_minutes", "quality_warning"}
        required = {"title", "personalized_minutes"}

        if not isinstance(data, dict):
            raise OutputValidationError("MinutesReport 必须是 JSON 对象")

        actual = set(data)
        if not required.issubset(actual):
            raise OutputValidationError(
                f"MinutesReport 字段不一致：缺失={sorted(required - actual)}"
            )
        extra = actual - allowed
        if extra:
            raise OutputValidationError(
                f"MinutesReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data["title"], "title")
        _string(data["personalized_minutes"], "personalized_minutes")
        if "quality_warning" in data and data["quality_warning"] is not None:
            _string(data["quality_warning"], "quality_warning")

        # 标准化：只保留三个合法字段
        return cls(
            title=data["title"],
            personalized_minutes=data["personalized_minutes"],
            quality_warning=data.get("quality_warning"),
        )


@dataclass
class ActionsReport(ModelMixin):
    """待办输出（与纪要输出分离，各自独立）。"""

    action_items: list[dict[str, Any]] = field(default_factory=list)
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None
    # 待办模板渲染文本（--item_template 时 LLM 按模板输出；无模板为 None）
    personalized_text: str | None = None

    @classmethod
    def validate(cls, data: dict) -> "ActionsReport":
        allowed = {"action_items", "quality_warning", "personalized_text"}
        required = {"action_items"}

        if not isinstance(data, dict):
            raise OutputValidationError("ActionsReport 必须是 JSON 对象")

        actual = set(data)
        if not required.issubset(actual):
            raise OutputValidationError(
                f"ActionsReport 字段不一致：缺失={sorted(required - actual)}"
            )
        extra = actual - allowed
        if extra:
            raise OutputValidationError(
                f"ActionsReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data["action_items"], list):
            raise OutputValidationError("action_items 必须是数组")
        for index, item in enumerate(data["action_items"]):
            _action(item, f"action_items[{index}]")
        if "quality_warning" in data and data["quality_warning"] is not None:
            _string(data["quality_warning"], "quality_warning")
        if "personalized_text" in data and data["personalized_text"] is not None:
            _string(data["personalized_text"], "personalized_text")

        # 标准化：只保留合法字段
        return cls(
            action_items=data["action_items"],
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


# ── LangGraph 共享状态 ────────────────────────────────────────

def _merge_degraded(a: bool | None, b: bool | None) -> bool:
    """quality_degraded 的 LangGraph reducer：任一为 True 则降级。

    双线并行时两条 fallback 节点可能同时写该键，
    用 or 合并避免并发写冲突（InvalidUpdateError）。
    """
    return bool(a) or bool(b)


class MeetingState(TypedDict, total=False):
    """LangGraph 在一次运行中跨节点传递的共享上下文。

    纪要（minutes）与待办（action_items）为两条独立流水线，
    各自的审核结果、返工反馈与返工计数分开维护。
    """

    transcript: str
    user: dict
    # 由画像 perspective=objective 判定，供展示与兜底拼装使用
    objective_perspective: bool
    # 核心 Agent 输出（公共事实底座）
    meeting_understanding: dict
    perspective_profile: dict
    # 任务线草稿
    minutes_draft: dict
    extracted_action_items: dict
    # 各自领域的审核结果与返工反馈
    minutes_supervisor_review: dict
    actions_supervisor_review: dict
    minutes_revision_feedback: list[str]
    actions_revision_feedback: list[str]
    minutes_revision_count: int
    actions_revision_count: int
    # Supervisor 未批准时仍输出结果，标记为降级兜底（双线并发写，or 合并）
    quality_degraded: Annotated[bool, _merge_degraded]
    # 按线隔离的降级标记：避免一条线降级牵连另一条线的渲染方式
    minutes_degraded: Annotated[bool, _merge_degraded]
    actions_degraded: Annotated[bool, _merge_degraded]
    # 并行渲染结果：纪要正文 + 待办列表
    rendered_minutes: str
    formatted_actions: list[dict]
    # 待办模板渲染文本（--item_template 时 LLM 按模板输出）
    formatted_actions_text: str
    # 流式模式：图内渲染节点跳过 LLM 调用，由运行入口接管流式输出
    streaming: bool
    # 可选：最终纪要以此 Markdown 模板格式输出（占位符 [描述] 将被填充）
    template: str
    # 可选：最终待办以此模板格式输出（--item_template）
    item_template: str
