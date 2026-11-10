"""meeting 领域数据模型（手写）。生成模型在 models_generated.py。"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Annotated, Any, ClassVar, TypedDict

from core.schema.validation import (
    OutputValidationError,
    _exact_fields,
    _string,
    _string_list,
)

from .models_base import ModelMixin, UserIdentity  # noqa: F401 - 再导出：reports.py / __init__.py 从本模块取
from .models_generated import *  # noqa: F403

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
    # 会议开始时间（请求体 extra.time）；供 calendar 相对时间回填使用
    meeting_time: str
    user: dict
    # 由画像 perspective=objective 判定，供展示与兜底拼装使用
    objective_perspective: bool
    # 核心 Agent 输出（公共事实底座）
    meeting_understanding: dict
    perspective_profile: dict
    # 个人单线 minutes 专用视角模型（confidence + 8 个内容字段）；不写旧 perspective_profile
    personal_perspective: dict
    # 本用户命中表（程序判定：谁被点名、哪些待办是他的、依据在哪；视角节点写入）
    user_hits: dict
    # 命中块的渲染文本（拼进纪要上下文，避免多处重拼）
    user_hits_block: str
    # 分栏分组骨架（程序判定：末尾三栏要出现哪些组名行 `**与我相关**：`/`**姓名**：`；
    # 与命中块一样由视角节点写入）。**必须在这里声明**：LangGraph 只传本 TypedDict
    # 声明过的 key，未声明的写入会被静默丢掉（实测：骨架写了、下游全程收不到）。
    user_action_groups_block: str
    # 重点关注雷达块（程序判定：本人身份规范、重点盯防人物定调与重点标的深潜要求；由视角节点写入）
    user_radar_block: str
    # 任务线子空间：lines[线名] = {draft, review,
    #   revision_feedback, revision_count, degraded, rendered, structure}
    lines: Annotated[dict[str, dict], _merge_lines]
    # 任意层降级（core 或任一任务线），用于最终质量警告（并发写，or 合并）
    quality_degraded: Annotated[bool, _merge_degraded]
    # 可选：各任务线的输出模板（线名 → 模板文本；占位符 [描述] 将被填充）
    templates: dict[str, str]
    # 可选：各任务线的组织参数（线名 → 如 minutes_styles 的 brief/topic/review/retro/alignment）
    line_modes: dict[str, str]
    # 可选：各任务线附加上下文（线名 → 如记忆注入）
    line_extra: dict[str, str]
    # 各任务线的运行视角（线名 → objective/personal/role_template/agenda_objective）。
    # 当前仅 minutes 使用；必须显式声明，LangGraph 只传 TypedDict 声明过的 key。
    line_views: dict[str, str]
    # 各任务线的布局（线名 → column_major / topic_major）；由模板 layout 元数据裁决。
    # 必须显式声明，否则写入会被 LangGraph 静默丢弃。
    line_layouts: dict[str, str]
    # topic_major 布局下，各任务线的议题容器栏目名（线名 → 栏名）。
    line_containers: dict[str, str]
    # 语种标识（"zh" | "en"，供下游各节点、篇幅预算与渲染器使用）
    lang: str
    # 审定议题模式状态字段（用于 minutes 任务在检测到有效议程时跨节点传递）
    has_valid_agenda: bool
    valid_agendas: list
    tagged_transcript: str
    # 场景识别（模板自动匹配）状态：开关关闭时不参与任何节点决策。
    # template_auto=True 表示 template 为空且 MINUTES_TEMPLATE_AUTO!=off，允许前置 Agent 分类。
    template_auto: bool
    # 模板来源：explicit / personal_default / default / auto（Stage 5 写入）
    template_source: str
    # 当前生效的英文模板 ID（不含 .md）；模板为空时先落 general_minutes
    template_id: str
    # 场景模式：normal（29 候选）/ agenda（20 候选）
    template_mode: str
    # 场景识别决策（原始输出、后处理结果、是否实际应用）；仅用于日志/调试，不进入 API 响应
    template_decision: dict


@dataclass
class TopicMajorMinutes(ModelMixin):
    """topic_major 议题主序草稿输出（手写模型，不进 models_generated.py）。

    结构：
    - 顶层：overview / topics / history_comparison；
    - 每条议题：topic_name + topic_summary / decisions / actions / risks / open_questions。
    """

    overview: str
    topics: list[dict[str, Any]] = field(default_factory=list)
    history_comparison: list[str] = field(default_factory=list)

    _TOPIC_KEYS: ClassVar[tuple[str, ...]] = (
        "topic_name",
        "topic_summary",
        "decisions",
        "actions",
        "risks",
        "open_questions",
    )
    _TOPIC_LIST_KEYS: ClassVar[tuple[str, ...]] = (
        "topic_summary",
        "decisions",
        "actions",
        "risks",
        "open_questions",
    )

    @classmethod
    def validate(cls, data: dict) -> "TopicMajorMinutes":
        _exact_fields(data, [f.name for f in fields(cls)], cls.__name__)
        _string(data["overview"], "overview")

        if not isinstance(data["topics"], list):
            raise OutputValidationError("topics 必须是数组")
        for idx, item in enumerate(data["topics"]):
            if not isinstance(item, dict):
                raise OutputValidationError(f"topics[{idx}] 必须是对象")
            _exact_fields(item, list(cls._TOPIC_KEYS), f"topics[{idx}]")
            _string(item["topic_name"], f"topics[{idx}].topic_name")
            if not item["topic_name"].strip():
                raise OutputValidationError(f"topics[{idx}].topic_name 不能为空")
            for key in cls._TOPIC_LIST_KEYS:
                _string_list(item[key], f"topics[{idx}].{key}")

        _string_list(data["history_comparison"], "history_comparison")
        return cls(**data)


# 多样式纪要：浅校验放行空 sections，这里补结构门禁，供 schema repair 重出。
from .tasks.minutes_styles.contracts import enforce_minutes_styles_sections  # noqa: E402

_orig_minutes_styles_validate = MultiStyles.validate.__func__


@classmethod
def _validate_minutes_styles_strict(cls, data: dict) -> "MultiStyles":
    enforce_minutes_styles_sections(data)
    return _orig_minutes_styles_validate(cls, data)


MultiStyles.validate = _validate_minutes_styles_strict

from dataclasses import fields as _dc_fields

_orig_meeting_understanding_validate = MeetingUnderstanding.validate.__func__


@classmethod
def _validate_meeting_understanding_dynamic(cls, data: dict) -> "MeetingUnderstanding":
    for f in _dc_fields(cls):
        if f.name not in data and f.default_factory is list:
            data[f.name] = []
    return _orig_meeting_understanding_validate(cls, data)


MeetingUnderstanding.validate = _validate_meeting_understanding_dynamic
