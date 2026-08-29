"""meeting 领域数据模型（手写）。生成模型在 models_generated.py。"""
from __future__ import annotations

from typing import Annotated, TypedDict

from .models_base import ModelMixin, UserIdentity
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
    # 可选：各任务线的组织参数（线名 → 如 minutes_styles 的 time/logic/causal/party/urgency）
    line_modes: dict[str, str]
    # 可选：各任务线附加上下文（线名 → 如记忆注入）
    line_extra: dict[str, str]


# 多样式纪要：浅校验放行空 sections，这里补结构门禁，供 schema repair 重出。
from .tasks.minutes_styles.contracts import enforce_minutes_styles_sections  # noqa: E402

_orig_minutes_styles_validate = MultiStyles.validate.__func__


@classmethod
def _validate_minutes_styles_strict(cls, data: dict) -> "MultiStyles":
    enforce_minutes_styles_sections(data)
    return _orig_minutes_styles_validate(cls, data)


MultiStyles.validate = _validate_minutes_styles_strict
