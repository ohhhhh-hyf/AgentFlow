"""议题纪要的视角裁决（v1：personal × agenda 明确不支持）。

本模块把「画像模式」与「是否有审定议程」收口成一个 view，供 API 入口、
编排层上下文、模板选择、视角建模和渲染后处理共同使用。不要在各步骤里
再写分散的 ``if is_agenda ... elif personal ...``。
"""
from __future__ import annotations

from core.runner.profiles import (
    AGENDA_PERSONAL_UNSUPPORTED_MESSAGE,
    resolve_profile_mode,
)

VIEW_OBJECTIVE = "objective"
VIEW_PERSONAL = "personal"
VIEW_ROLE_TEMPLATE = "role_template"
VIEW_AGENDA_OBJECTIVE = "agenda_objective"
# 未来个人议题模式；v1 不返回，保留常量给后续演进。
VIEW_AGENDA_PERSONAL = "agenda_personal"


class AgendaPersonalUnsupported(Exception):
    """个人视角 + 议题增强模式在 v1 明确不支持。"""


def resolve_minutes_view(
    *,
    has_valid_agenda: bool,
    profile_mode: str,
    objective_perspective: bool = False,
) -> str:
    """返回本次 minutes 的运行视图。

    - 无议程：原样返回 objective / personal / role_template
    - 有议程 + personal：raise ``AgendaPersonalUnsupported``
    - 有议程 + objective / role_template：``agenda_objective``
    """
    mode = VIEW_OBJECTIVE if objective_perspective else (profile_mode or VIEW_OBJECTIVE)
    if mode not in {VIEW_OBJECTIVE, VIEW_PERSONAL, VIEW_ROLE_TEMPLATE}:
        mode = VIEW_OBJECTIVE
    if not has_valid_agenda:
        return mode
    if mode == VIEW_PERSONAL:
        raise AgendaPersonalUnsupported(AGENDA_PERSONAL_UNSUPPORTED_MESSAGE)
    return VIEW_AGENDA_OBJECTIVE


__all__ = [
    "AgendaPersonalUnsupported",
    "VIEW_OBJECTIVE",
    "VIEW_PERSONAL",
    "VIEW_ROLE_TEMPLATE",
    "VIEW_AGENDA_OBJECTIVE",
    "VIEW_AGENDA_PERSONAL",
    "resolve_profile_mode",
    "resolve_minutes_view",
]
