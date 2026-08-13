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
    validate_supervisor_semantics,
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
    topics: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "MeetingUnderstanding":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["meeting_purpose"], "meeting_purpose")
        if not isinstance(data["topics"], list):
            raise OutputValidationError("topics 必须是数组")
        _string_list(data["decisions"], "decisions")
        _string_list(data["open_questions"], "open_questions")
        _string_list(data["risks"], "risks")
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

    @classmethod
    def validate(cls, data: dict) -> "Minutes":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["headline"], "headline")
        _string_list(data["executive_summary"], "executive_summary")
        _string_list(data["key_decisions"], "key_decisions")
        _string_list(data["personally_relevant_points"], "personally_relevant_points")
        _string_list(data["risks_and_blockers"], "risks_and_blockers")
        _string_list(data["unresolved_questions"], "unresolved_questions")
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

# ── LangGraph 共享状态 ────────────────────────────────────────

def _merge_degraded(a: bool | None, b: bool | None) -> bool:
    """quality_degraded 的 LangGraph reducer：任一为 True 则降级。

    双线并行时多个节点可能同时写该键，
    用 or 合并避免并发写冲突（InvalidUpdateError）。
    """
    return bool(a) or bool(b)

def _merge_lines(a: dict | None, b: dict | None) -> dict:
    """任务线子空间（lines）的 LangGraph reducer：按线名浅合并。

    双线并行时各线同时写自己的子空间（不同 key），
    同一条线内的多次更新（draft / review / count）也做字段级合并，
    避免整线替换丢失已有字段。
    """
    out = {name: dict(patch or {}) for name, patch in (a or {}).items()}
    for name, patch in (b or {}).items():
        cur = out.get(name)
        if isinstance(cur, dict) and isinstance(patch, dict):
            merged = dict(cur)
            merged.update(patch)
            out[name] = merged
        else:
            out[name] = patch
    return out

class MeetingState(TypedDict, total=False):
    """LangGraph 在一次运行中跨节点传递的共享上下文。

    核心层（会议理解/视角建模）为公共事实底座；
    每条任务线是一个自包含子空间（``lines[线名]``），内含草稿、
    审核结果、返工反馈与计数、降级标记，各线互不干扰。
    新增任务线只需在 ``orchestrator.TASK_LINES`` 注册，无需修改本状态。
    """

    transcript: str
    user: dict
    # 由画像 perspective=objective 判定，供展示与兜底拼装使用
    objective_perspective: bool
    # 核心 Agent 输出（公共事实底座）
    meeting_understanding: dict
    perspective_profile: dict
    # 任务线子空间：lines[线名] = {draft, review,
    #   revision_feedback, revision_count, degraded, rendered, structure}
    lines: Annotated[dict[str, dict], _merge_lines]
    # 任意层降级（core 或任一任务线），用于最终质量警告（并发写，or 合并）
    quality_degraded: Annotated[bool, _merge_degraded]
    # 可选：各任务线的输出模板（线名 → 模板文本；占位符 [描述] 将被填充）
    templates: dict[str, str]
    # 可选：各任务线的组织参数（线名 → 如 multi_styles 的 time/logic/causal/party/urgency）
    line_modes: dict[str, str]


# 多样式纪要：浅校验放行空 sections，这里补结构门禁，供 schema repair 重出。
from .tasks.multi_styles.contracts import enforce_multi_styles_sections  # noqa: E402

_orig_multi_styles_validate = MultiStyles.validate.__func__


@classmethod
def _validate_multi_styles_strict(cls, data: dict) -> "MultiStyles":
    enforce_multi_styles_sections(data)
    return _orig_multi_styles_validate(cls, data)


MultiStyles.validate = _validate_multi_styles_strict
