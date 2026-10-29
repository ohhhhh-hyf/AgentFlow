"""会议理解的任务 profile：同时驱动 prompt 与输出契约。

单任务时使用精确 profile；多任务保留 union fallback；memory_on 走全量。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class UnderstandingProfile:
    """一个任务需要的理解字段与 session_segments 形态。"""

    segments: str
    fields: tuple[str, ...]
    intro: str = ""


TASK_PROFILES: dict[str, UnderstandingProfile] = {
    "minutes": UnderstandingProfile(
        segments="full",
        fields=("decisions", "open_questions", "risks"),
    ),
    "risks": UnderstandingProfile(
        segments="light",
        fields=("open_questions", "risks", "risk_hints"),
        intro="本次任务服务于风险治理与隐患挖掘。",
    ),
    "mindmap": UnderstandingProfile(
        segments="full",
        fields=("decisions", "risks", "open_questions"),
    ),
}

# actions-only 直接走待办 Agent，不参与会议理解 profile。
NO_UNDERSTANDING_TASKS = frozenset({"actions"})

FULL_PROFILE = UnderstandingProfile(
    segments="full",
    fields=(
        "decisions",
        "open_questions",
        "risks",
        "action_hints",
        "risk_hints",
        "dependencies",
    ),
)

# 多任务 union 时用于稳定字段顺序。
_FIELD_ORDER: tuple[str, ...] = (
    "decisions",
    "open_questions",
    "risks",
    "action_hints",
    "risk_hints",
    "dependencies",
)


def _task_list(active_tasks: Iterable[str] | None) -> list[str]:
    return [str(t).strip() for t in (active_tasks or []) if str(t).strip()]


def _union_profiles(profiles: list[UnderstandingProfile]) -> UnderstandingProfile:
    selected = {name for profile in profiles for name in profile.fields}
    fields = tuple(name for name in _FIELD_ORDER if name in selected)
    segments = "full" if any(p.segments == "full" for p in profiles) else "light"
    return UnderstandingProfile(segments=segments, fields=fields)


def resolve_profile(
    active_tasks: Iterable[str] | None,
    *,
    memory_on: bool = False,
    is_agenda: bool = False,
) -> UnderstandingProfile | None:
    """解析当前请求应使用的理解 profile。

    - memory_on：全量；
    - is_agenda：返回 None，调用方继续使用旧议题 prompt；
    - 空任务/未知任务：全量 fallback；
    - 多任务：字段 union + 完整/轻量 segments 合并。
    """
    if memory_on:
        return FULL_PROFILE
    if is_agenda:
        return None

    raw_tasks = _task_list(active_tasks)
    if not raw_tasks:
        return FULL_PROFILE

    tasks = [t for t in raw_tasks if t not in NO_UNDERSTANDING_TASKS]
    if not tasks:
        return None

    if len(tasks) == 1:
        return TASK_PROFILES.get(tasks[0], FULL_PROFILE)

    return _union_profiles([TASK_PROFILES.get(t, FULL_PROFILE) for t in tasks])


__all__ = [
    "FULL_PROFILE",
    "NO_UNDERSTANDING_TASKS",
    "TASK_PROFILES",
    "UnderstandingProfile",
    "resolve_profile",
]
