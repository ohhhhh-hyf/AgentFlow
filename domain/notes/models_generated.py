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
class Catalog(ModelMixin):
    """Catalog输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    course: str
    version: str
    mode: str
    chapters: list[dict[str, Any]] = field(default_factory=list)
    unmatched_content: list[str] = field(default_factory=list)
    uncertain_nodes: list[str] = field(default_factory=list)
    added_chapters: list[str] = field(default_factory=list)
    added_topics: list[str] = field(default_factory=list)
    added_knowledge_points: list[str] = field(default_factory=list)
    updated_knowledge_points: list[str] = field(default_factory=list)
    merged_nodes: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Catalog":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["course"], "course")
        _string(data["version"], "version")
        _string(data["mode"], "mode")
        if not isinstance(data["chapters"], list):
            raise OutputValidationError("chapters 必须是数组")
        _string_list(data["unmatched_content"], "unmatched_content")
        _string_list(data["uncertain_nodes"], "uncertain_nodes")
        _string_list(data["added_chapters"], "added_chapters")
        _string_list(data["added_topics"], "added_topics")
        _string_list(data["added_knowledge_points"], "added_knowledge_points")
        _string_list(data["updated_knowledge_points"], "updated_knowledge_points")
        _string_list(data["merged_nodes"], "merged_nodes")
        return cls(**data)

@dataclass
class Checklist(ModelMixin):
    """Checklist输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    course: str
    catalog_version: str
    cards: list[dict[str, Any]] = field(default_factory=list)
    uncertain_quotes: list[str] = field(default_factory=list)
    strategy: list[str] = field(default_factory=list)
    phases: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Checklist":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["course"], "course")
        _string(data["catalog_version"], "catalog_version")
        if not isinstance(data["cards"], list):
            raise OutputValidationError("cards 必须是数组")
        _string_list(data["uncertain_quotes"], "uncertain_quotes")
        _string_list(data["strategy"], "strategy")
        if not isinstance(data["phases"], list):
            raise OutputValidationError("phases 必须是数组")
        return cls(**data)

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
class Library(ModelMixin):
    """Library输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    message: str
    increment: str
    image_count: str = "0"
    doc_count: str = "0"
    files: list[dict[str, Any]] = field(default_factory=list)
    increment_by_file: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Library":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["message"], "message")
        _string(data["increment"], "increment")
        _string(data["image_count"], "image_count")
        _string(data["doc_count"], "doc_count")
        if not isinstance(data["files"], list):
            raise OutputValidationError("files 必须是数组")
        if not isinstance(data["increment_by_file"], list):
            raise OutputValidationError("increment_by_file 必须是数组")
        if not isinstance(data["conflicts"], list):
            raise OutputValidationError("conflicts 必须是数组")
        if not isinstance(data["items"], list):
            raise OutputValidationError("items 必须是数组")
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
class Quiz(ModelMixin):
    """Quiz输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    concepts: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Quiz":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        if not isinstance(data["concepts"], list):
            raise OutputValidationError("concepts 必须是数组")
        if not isinstance(data["relations"], list):
            raise OutputValidationError("relations 必须是数组")
        if not isinstance(data["details"], list):
            raise OutputValidationError("details 必须是数组")
        if not isinstance(data["questions"], list):
            raise OutputValidationError("questions 必须是数组")
        return cls(**data)

@dataclass
class Review(ModelMixin):
    """Review输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    corrected_notes: str
    knowledge_points: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "Review":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["corrected_notes"], "corrected_notes")
        if not isinstance(data["knowledge_points"], list):
            raise OutputValidationError("knowledge_points 必须是数组")
        if not isinstance(data["issues"], list):
            raise OutputValidationError("issues 必须是数组")
        return cls(**data)

# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

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

@dataclass
class ReviewSupervisorReview(ModelMixin):
    """笔记审查任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    review_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("review_check",)

    @classmethod
    def validate(cls, data: dict) -> "ReviewSupervisorReview":
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
class QuizSupervisorReview(ModelMixin):
    """自测题任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    quiz_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("quiz_check",)

    @classmethod
    def validate(cls, data: dict) -> "QuizSupervisorReview":
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
class LibrarySupervisorReview(ModelMixin):
    """资料入库任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    library_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("library_check",)

    @classmethod
    def validate(cls, data: dict) -> "LibrarySupervisorReview":
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
class CatalogSupervisorReview(ModelMixin):
    """知识目录任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    catalog_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("catalog_check",)

    @classmethod
    def validate(cls, data: dict) -> "CatalogSupervisorReview":
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
class ChecklistSupervisorReview(ModelMixin):
    """复习清单任务线的领域审核结果。"""

    decision: Literal["approve", "revise", "reject"]
    checklist_check: dict[str, Any]
    feedback: list[str] = field(default_factory=list)

    # 本模型的全部检查项（供结构校验与公共语义校验使用）
    CHECK_KEYS = ("checklist_check",)

    @classmethod
    def validate(cls, data: dict) -> "ChecklistSupervisorReview":
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

class CatalogReportValidation:
    """CatalogReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "CatalogReport":
        allowed = {"course", "version", "mode", "chapters", "unmatched_content", "uncertain_nodes", "added_chapters", "added_topics", "added_knowledge_points", "updated_knowledge_points", "merged_nodes", "catalog_html", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("CatalogReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"CatalogReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("course") or "", "course")
        _string(data.get("version") or "", "version")
        _string(data.get("mode") or "", "mode")
        if not isinstance(data.get("chapters") or [], list):
            raise OutputValidationError("chapters 必须是数组")
        _string_list(data.get("unmatched_content") or [], "unmatched_content")
        _string_list(data.get("uncertain_nodes") or [], "uncertain_nodes")
        _string_list(data.get("added_chapters") or [], "added_chapters")
        _string_list(data.get("added_topics") or [], "added_topics")
        _string_list(data.get("added_knowledge_points") or [], "added_knowledge_points")
        _string_list(data.get("updated_knowledge_points") or [], "updated_knowledge_points")
        _string_list(data.get("merged_nodes") or [], "merged_nodes")
        _string(data.get("catalog_html") or "", "catalog_html")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            course=data.get("course") or "",
            version=data.get("version") or "",
            mode=data.get("mode") or "",
            chapters=data.get("chapters") or [],
            unmatched_content=data.get("unmatched_content") or [],
            uncertain_nodes=data.get("uncertain_nodes") or [],
            added_chapters=data.get("added_chapters") or [],
            added_topics=data.get("added_topics") or [],
            added_knowledge_points=data.get("added_knowledge_points") or [],
            updated_knowledge_points=data.get("updated_knowledge_points") or [],
            merged_nodes=data.get("merged_nodes") or [],
            catalog_html=data.get("catalog_html") or "",
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


class ChecklistReportValidation:
    """ChecklistReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "ChecklistReport":
        allowed = {"course", "catalog_version", "cards", "phases", "strategy", "uncertain_quotes", "checklist_html", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("ChecklistReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"ChecklistReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("course") or "", "course")
        _string(data.get("catalog_version") or "", "catalog_version")
        if not isinstance(data.get("cards") or [], list):
            raise OutputValidationError("cards 必须是数组")
        if not isinstance(data.get("phases") or [], list):
            raise OutputValidationError("phases 必须是数组")
        _string_list(data.get("strategy") or [], "strategy")
        _string_list(data.get("uncertain_quotes") or [], "uncertain_quotes")
        _string(data.get("checklist_html") or "", "checklist_html")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            course=data.get("course") or "",
            catalog_version=data.get("catalog_version") or "",
            cards=data.get("cards") or [],
            phases=data.get("phases") or [],
            strategy=data.get("strategy") or [],
            uncertain_quotes=data.get("uncertain_quotes") or [],
            checklist_html=data.get("checklist_html") or "",
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


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


class LibraryReportValidation:
    """LibraryReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "LibraryReport":
        allowed = {"increment", "message", "files", "increment_by_file", "conflicts", "items", "library_html", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("LibraryReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"LibraryReport 字段不一致：多余={sorted(extra)}"
            )

        _string(data.get("increment") or "", "increment")
        _string(data.get("message") or "", "message")
        if not isinstance(data.get("files") or [], list):
            raise OutputValidationError("files 必须是数组")
        if not isinstance(data.get("increment_by_file") or [], list):
            raise OutputValidationError("increment_by_file 必须是数组")
        if not isinstance(data.get("conflicts") or [], list):
            raise OutputValidationError("conflicts 必须是数组")
        if not isinstance(data.get("items") or [], list):
            raise OutputValidationError("items 必须是数组")
        _string(data.get("library_html") or "", "library_html")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            increment=data.get("increment") or "",
            message=data.get("message") or "",
            files=data.get("files") or [],
            increment_by_file=data.get("increment_by_file") or [],
            conflicts=data.get("conflicts") or [],
            items=data.get("items") or [],
            library_html=data.get("library_html") or "",
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


class QuizReportValidation:
    """QuizReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "QuizReport":
        allowed = {"questions", "bank_questions", "bank_query", "bank_status", "quiz_html", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("QuizReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"QuizReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data.get("questions") or [], list):
            raise OutputValidationError("questions 必须是数组")
        if not isinstance(data.get("bank_questions") or [], list):
            raise OutputValidationError("bank_questions 必须是数组")
        _string(data.get("bank_query") or "", "bank_query")
        _string(data.get("bank_status") or "", "bank_status")
        _string(data.get("quiz_html") or "", "quiz_html")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            questions=data.get("questions") or [],
            bank_questions=data.get("bank_questions") or [],
            bank_query=data.get("bank_query") or "",
            bank_status=data.get("bank_status") or "",
            quiz_html=data.get("quiz_html") or "",
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )


class ReviewReportValidation:
    """ReviewReport 的校验逻辑（由脚本按手写字段自动生成）。"""

    @classmethod
    def validate(cls, data: dict) -> "ReviewReport":
        allowed = {"knowledge_points", "issues", "corrected_notes", "review_html", "original_notes", "quality_warning", "personalized_text"}

        if not isinstance(data, dict):
            raise OutputValidationError("ReviewReport 必须是 JSON 对象")

        extra = set(data) - allowed
        if extra:
            raise OutputValidationError(
                f"ReviewReport 字段不一致：多余={sorted(extra)}"
            )

        if not isinstance(data.get("knowledge_points") or [], list):
            raise OutputValidationError("knowledge_points 必须是数组")
        if not isinstance(data.get("issues") or [], list):
            raise OutputValidationError("issues 必须是数组")
        _string(data.get("corrected_notes") or "", "corrected_notes")
        _string(data.get("review_html") or "", "review_html")
        _string(data.get("original_notes") or "", "original_notes")
        if data.get("quality_warning") is not None:
            _string(data["quality_warning"], "quality_warning")
        if data.get("personalized_text") is not None:
            _string(data["personalized_text"], "personalized_text")

        return cls(
            knowledge_points=data.get("knowledge_points") or [],
            issues=data.get("issues") or [],
            corrected_notes=data.get("corrected_notes") or "",
            review_html=data.get("review_html") or "",
            original_notes=data.get("original_notes") or "",
            quality_warning=data.get("quality_warning"),
            personalized_text=data.get("personalized_text"),
        )

# ── Report 校验生成区结束 ──
