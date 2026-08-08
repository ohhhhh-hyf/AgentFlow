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


# ── 生成模型生成区：由 tools/scripts/generation_contract.py 生成，勿手改 ──

@dataclass
class ActionItems(ModelMixin):
    """待办提取输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

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
    """会议理解输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

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
class Minutes(ModelMixin):
    """纪要草稿输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

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
class PerspectiveModeling(ModelMixin):
    """视角建模输出（浅校验：仅校验第一层键与类型，嵌套不校验）。"""

    confidence: Literal["high", "medium", "low"]
    name: str
    inferred_role: str
    responsibilities: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    relevant_topics: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "PerspectiveModeling":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        _string(data["name"], "name")
        _string(data["inferred_role"], "inferred_role")
        _string_list(data["responsibilities"], "responsibilities")
        _string_list(data["goals"], "goals")
        _string_list(data["concerns"], "concerns")
        _string_list(data["relevant_topics"], "relevant_topics")
        _string_list(data["evidence"], "evidence")
        return cls(**data)


# ── 生成模型生成区结束 ──

# ── 审核模型生成区：由 tools/scripts/supervisor_contract.py 生成，勿手改 ──

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


# ── 审核模型生成区结束 ──


@dataclass
class MinutesReport(ModelMixin):
    """纪要输出（与待办输出分离，各自独立）。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    ``title`` → 视角标题（通用计算）；``rendered`` → 渲染正文。
    """

    title: str = field(metadata={"source": "title"})
    personalized_minutes: str = field(metadata={"source": "rendered"})
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
class ActionItemsReport(ModelMixin):
    """待办输出（与纪要输出分离，各自独立）。

    字段的 ``metadata["source"]`` 供通用组装器从 state 抽屉取值：
    ``items`` → 结构化待办列表（extract_actions 合并结果）；
    ``rendered`` → LLM 渲染文本（无模板普通渲染 / 有模板按模板）。
    """

    # 结构化待办列表（客观视角 = 全员已分配 + 未分配；个人视角 = 本人）
    action_items: list[dict[str, Any]] = field(
        default_factory=list, metadata={"source": "items"}
    )
    # 仅由系统在兜底路径写入；LLM 输出不需要也不应包含该字段
    quality_warning: str | None = None
    # 待办渲染文本（无模板 / 有模板均为 LLM 输出）
    personalized_text: str | None = field(
        default=None, metadata={"source": "rendered"}
    )

    @classmethod
    def validate(cls, data: dict) -> "ActionItemsReport":
        allowed = {"action_items", "quality_warning", "personalized_text"}
        required = {"action_items"}

        if not isinstance(data, dict):
            raise OutputValidationError("ActionItemsReport 必须是 JSON 对象")

        actual = set(data)
        if not required.issubset(actual):
            raise OutputValidationError(
                f"ActionItemsReport 字段不一致：缺失={sorted(required - actual)}"
            )
        extra = actual - allowed
        if extra:
            raise OutputValidationError(
                f"ActionItemsReport 字段不一致：多余={sorted(extra)}"
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
    # 任务线子空间：lines[线名] = {draft, supervisor_review,
    #   revision_feedback, revision_count, degraded, rendered, items}
    lines: Annotated[dict[str, dict], _merge_lines]
    # 任意层降级（core 或任一任务线），用于最终质量警告（并发写，or 合并）
    quality_degraded: Annotated[bool, _merge_degraded]
    # 流式模式：图内渲染节点跳过 LLM 调用，由运行入口接管流式输出
    streaming: bool
    # 可选：各任务线的输出模板（线名 → 模板文本；占位符 [描述] 将被填充）
    templates: dict[str, str]
