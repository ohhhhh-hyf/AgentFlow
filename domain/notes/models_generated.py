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
class KnowledgeGraph(ModelMixin):
    """KnowledgeGraph输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    title: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "KnowledgeGraph":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["title"], "title")
        if not isinstance(data["nodes"], list):
            raise OutputValidationError("nodes 必须是数组")
        if not isinstance(data["edges"], list):
            raise OutputValidationError("edges 必须是数组")
        return cls(**data)

@dataclass
class NotesUnderstanding(ModelMixin):
    """NotesUnderstanding输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    note_purpose: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "NotesUnderstanding":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["note_purpose"], "note_purpose")
        if not isinstance(data["sections"], list):
            raise OutputValidationError("sections 必须是数组")
        _string_list(data["key_terms"], "key_terms")
        _string_list(data["open_questions"], "open_questions")
        return cls(**data)

@dataclass
class Points(ModelMixin):
    """Points输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    points: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Points":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        if not isinstance(data["points"], list):
            raise OutputValidationError("points 必须是数组")
        return cls(**data)

# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

@dataclass
class PointsSupervisorReview(ModelMixin):
    """知识点总结任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    points_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("points_check",)

    @classmethod
    def validate(cls, data: dict) -> "PointsSupervisorReview":
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
class KnowledgeGraphSupervisorReview(ModelMixin):
    """知识图谱任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    graph_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("graph_check",)

    @classmethod
    def validate(cls, data: dict) -> "KnowledgeGraphSupervisorReview":
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

class KnowledgeGraphReportValidation:
    """KnowledgeGraphReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "KnowledgeGraphReport":
        allowed = {"outline", "title", "nodes", "edges", "quality_warning"}

        if not isinstance(data, dict):
            raise OutputValidationError("KnowledgeGraphReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"KnowledgeGraphReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("outline") or "", "outline")
        _string(data.get("title") or "", "title")
        if not isinstance(data.get("nodes") or [], list):
            raise OutputValidationError("nodes 必须是数组")
        if not isinstance(data.get("edges") or [], list):
            raise OutputValidationError("edges 必须是数组")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")

        return cls(
            outline=data.get("outline") or "",
            title=data.get("title") or "",
            nodes=data.get("nodes") or [],
            edges=data.get("edges") or [],
            quality_warning=data.get("quality_warning"),
        )

class PointsReportValidation:
    """PointsReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "PointsReport":
        allowed = {"points", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("PointsReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"PointsReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data.get("points") or [], list):
            raise OutputValidationError("points 必须是数组")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            points=data.get("points") or [],
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )

# ── Report 校验生成区结束 ──
