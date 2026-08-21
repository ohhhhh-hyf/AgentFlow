"""生成模型 / 审核模型 / Report 校验。由 tools/scripts/sync_domain.py 写入，勿手改。"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Literal

from tools.validation import (
    OutputValidationError,
    _action,
    _choice,
    _exact_fields,
    _review_check,
    _string,
    _string_list,
    validate_supervisor_semantics,
)

from .models_base import ModelMixin

# ── 生成模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

@dataclass
class ActionItems(ModelMixin):
    """ActionItems输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    my_actions: list[dict[str, Any]] = field(default_factory=list)
    delegated_actions: list[dict[str, Any]] = field(default_factory=list)
    unassigned_actions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "ActionItems":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        if not isinstance(data["my_actions"], list):
            raise OutputValidationError("my_actions 必须是数组")
        if not isinstance(data["delegated_actions"], list):
            raise OutputValidationError("delegated_actions 必须是数组")
        if not isinstance(data["unassigned_actions"], list):
            raise OutputValidationError("unassigned_actions 必须是数组")
        return cls(**data)

@dataclass
class MeetingUnderstanding(ModelMixin):
    """MeetingUnderstanding输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    meeting_purpose: str
    scene: Literal["通用", "团队例会", "脑暴/讨论", "项目决策与评审", "专项讨论会", "研讨会", "采访/对话"]
    topics: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    action_hints: list[dict[str, Any]] = field(default_factory=list)
    risk_hints: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MeetingUnderstanding":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["meeting_purpose"], "meeting_purpose")
        _choice(data["scene"], {"通用", "团队例会", "脑暴/讨论", "项目决策与评审", "专项讨论会", "研讨会", "采访/对话"}, "scene")
        if not isinstance(data["topics"], list):
            raise OutputValidationError("topics 必须是数组")
        _string_list(data["decisions"], "decisions")
        _string_list(data["open_questions"], "open_questions")
        _string_list(data["risks"], "risks")
        if not isinstance(data["action_hints"], list):
            raise OutputValidationError("action_hints 必须是数组")
        if not isinstance(data["risk_hints"], list):
            raise OutputValidationError("risk_hints 必须是数组")
        _string_list(data["dependencies"], "dependencies")
        return cls(**data)

@dataclass
class Mindmap(ModelMixin):
    """Mindmap输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    title: str
    outline: str

    @classmethod
    def validate(cls, data: dict) -> "Mindmap":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["title"], "title")
        _string(data["outline"], "outline")
        return cls(**data)

@dataclass
class Minutes(ModelMixin):
    """Minutes输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    headline: str
    executive_summary: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    personally_relevant_points: list[str] = field(default_factory=list)
    risks_and_blockers: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    history_comparison: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Minutes":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["headline"], "headline")
        _string_list(data["executive_summary"], "executive_summary")
        _string_list(data["key_decisions"], "key_decisions")
        _string_list(data["personally_relevant_points"], "personally_relevant_points")
        _string_list(data["risks_and_blockers"], "risks_and_blockers")
        _string_list(data["unresolved_questions"], "unresolved_questions")
        _string_list(data["history_comparison"], "history_comparison")
        return cls(**data)

@dataclass
class MinutesTrace(ModelMixin):
    """MinutesTrace输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    scene: Literal["通用", "团队例会", "脑暴/讨论", "项目决策与评审", "专项讨论会", "研讨会", "采访/对话"]
    minutes_md: str
    alignments: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MinutesTrace":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["scene"], {"通用", "团队例会", "脑暴/讨论", "项目决策与评审", "专项讨论会", "研讨会", "采访/对话"}, "scene")
        _string(data["minutes_md"], "minutes_md")
        if not isinstance(data["alignments"], list):
            raise OutputValidationError("alignments 必须是数组")
        return cls(**data)

@dataclass
class MultiStyles(ModelMixin):
    """MultiStyles输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    mode: Literal["time", "logic", "causal", "party", "urgency"]
    title: str
    summary: str
    sections: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MultiStyles":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["mode"], {"time", "logic", "causal", "party", "urgency"}, "mode")
        _string(data["title"], "title")
        _string(data["summary"], "summary")
        if not isinstance(data["sections"], list):
            raise OutputValidationError("sections 必须是数组")
        return cls(**data)

@dataclass
class Risk(ModelMixin):
    """Risk输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    risks: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Risk":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        if not isinstance(data["risks"], list):
            raise OutputValidationError("risks 必须是数组")
        return cls(**data)

# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

@dataclass
class MinutesSupervisorReview(ModelMixin):
    """纪要任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    facts_check: dict[str, Any]
    perspective_check: dict[str, Any]
    consistency_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("facts_check", "perspective_check", "consistency_check")

    @classmethod
    def validate(cls, data: dict) -> "MinutesSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

@dataclass
class ActionItemsSupervisorReview(ModelMixin):
    """待办任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    action_items_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("action_items_check",)

    @classmethod
    def validate(cls, data: dict) -> "ActionItemsSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

@dataclass
class RiskSupervisorReview(ModelMixin):
    """风险分析任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    risk_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("risk_check",)

    @classmethod
    def validate(cls, data: dict) -> "RiskSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

@dataclass
class MindmapSupervisorReview(ModelMixin):
    """思维导图任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    mindmap_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("mindmap_check",)

    @classmethod
    def validate(cls, data: dict) -> "MindmapSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

@dataclass
class MultiStylesSupervisorReview(ModelMixin):
    """多样式纪要任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    mode_check: dict[str, Any]
    facts_check: dict[str, Any]
    consistency_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("mode_check", "facts_check", "consistency_check")

    @classmethod
    def validate(cls, data: dict) -> "MultiStylesSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

@dataclass
class MinutesTraceSupervisorReview(ModelMixin):
    """溯源纪要任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    facts_check: dict[str, Any]
    template_check: dict[str, Any]
    trace_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("facts_check", "template_check", "trace_check")

    @classmethod
    def validate(cls, data: dict) -> "MinutesTraceSupervisorReview":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        for key in cls.CHECK_KEYS:
            _review_check(data[key], key)
        _string_list(data["feedback"], "feedback")
        # 公共语义规则：decision 枚举 + 与检查项/feedback 的联动约束
        validate_supervisor_semantics(
            data["decision"],
            data["feedback"],
            {key: data[key] for key in cls.CHECK_KEYS},
        )
        return cls(**data)

# ── 审核模型生成区结束 ──

# ── Report 校验生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

class ActionItemsReportValidation:
    """ActionItemsReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "ActionItemsReport":
        allowed = {"action_items", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("ActionItemsReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"ActionItemsReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data.get("action_items") or [], list):
            raise OutputValidationError("action_items 必须是数组")
        for index, item in enumerate(data.get("action_items") or []):
            _action(item, f"action_items[{index}]")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            action_items=data.get("action_items") or [],
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


class MindmapReportValidation:
    """MindmapReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "MindmapReport":
        allowed = {"outline", "quality_warning"}

        if not isinstance(data, dict):
            raise OutputValidationError("MindmapReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"MindmapReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("outline") or "", "outline")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")

        return cls(
            outline=data.get("outline") or "",
            quality_warning=data.get("quality_warning"),
        )


class MinutesReportValidation:
    """MinutesReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "MinutesReport":
        allowed = {"title", "personalized_minutes", "quality_warning"}

        if not isinstance(data, dict):
            raise OutputValidationError("MinutesReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"MinutesReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("title") or "", "title")
        _string(data.get("personalized_minutes") or "", "personalized_minutes")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")

        return cls(
            title=data.get("title") or "",
            personalized_minutes=data.get("personalized_minutes") or "",
            quality_warning=data.get("quality_warning"),
        )


class MinutesTraceReportValidation:
    """MinutesTraceReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "MinutesTraceReport":
        allowed = {"title", "personalized_minutes", "quality_warning"}

        if not isinstance(data, dict):
            raise OutputValidationError("MinutesTraceReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"MinutesTraceReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("title") or "", "title")
        _string(data.get("personalized_minutes") or "", "personalized_minutes")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")

        return cls(
            title=data.get("title") or "",
            personalized_minutes=data.get("personalized_minutes") or "",
            quality_warning=data.get("quality_warning"),
        )


class MultiStylesReportValidation:
    """MultiStylesReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "MultiStylesReport":
        allowed = {"mode", "title", "summary", "sections", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("MultiStylesReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"MultiStylesReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("mode") or "", "mode")
        _string(data.get("title") or "", "title")
        _string(data.get("summary") or "", "summary")
        if not isinstance(data.get("sections") or [], list):
            raise OutputValidationError("sections 必须是数组")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            mode=data.get("mode") or "",
            title=data.get("title") or "",
            summary=data.get("summary") or "",
            sections=data.get("sections") or [],
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


class RiskReportValidation:
    """RiskReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "RiskReport":
        allowed = {"risks", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("RiskReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"RiskReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data.get("risks") or [], list):
            raise OutputValidationError("risks 必须是数组")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            risks=data.get("risks") or [],
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )

# ── Report 校验生成区结束 ──
