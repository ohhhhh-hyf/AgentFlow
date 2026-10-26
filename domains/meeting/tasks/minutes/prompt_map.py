"""minutes 的 view → prompt 映射（Step 3）。

把 ``is_agenda → personal → objective`` 的分散判断收口到一处：
- ``resolve_prompt_view`` 只负责判定本次上下文对应哪个 view；
- ``minutes_prompt_set`` 返回该 view 的生成/审核/渲染 prompt；
- 普通 personal / role_template / objective 行为保持不变。
"""
from __future__ import annotations

from dataclasses import dataclass

from core.execution.hard_execution import (
    is_agenda_enhanced_mode,
    parse_perspective_mode,
)

from ...views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_OBJECTIVE,
    VIEW_PERSONAL,
    VIEW_ROLE_TEMPLATE,
)
from .prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_RENDER_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_RENDER_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)


@dataclass(frozen=True)
class MinutesPromptSet:
    """一个 view 对应的完整 prompt 组合。"""

    view: str
    generation: str
    supervisor: str
    render: str
    render_template: str


_OBJECTIVE_SET = MinutesPromptSet(
    view=VIEW_OBJECTIVE,
    generation=MINUTES_OBJECTIVE_GENERATION_PROMPT,
    supervisor=MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    render=MINUTES_OBJECTIVE_RENDER_PROMPT,
    render_template=MINUTES_RENDER_TEMPLATE_PROMPT,
)

_PERSONAL_SET = MinutesPromptSet(
    view=VIEW_PERSONAL,
    generation=MINUTES_PERSONAL_GENERATION_PROMPT,
    supervisor=MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    render=MINUTES_PERSONAL_RENDER_PROMPT,
    render_template=MINUTES_RENDER_TEMPLATE_PROMPT,
)

_AGENDA_OBJECTIVE_SET = MinutesPromptSet(
    view=VIEW_AGENDA_OBJECTIVE,
    generation=MINUTES_AGENDA_GENERATION_PROMPT,
    supervisor=MINUTES_AGENDA_SUPERVISOR_PROMPT,
    render=MINUTES_AGENDA_RENDER_PROMPT,
    render_template=MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
)

# 职业模板沿用 objective prompt（与既有行为一致），但保留自己的 view 标签。
_ROLE_TEMPLATE_SET = MinutesPromptSet(
    view=VIEW_ROLE_TEMPLATE,
    generation=MINUTES_OBJECTIVE_GENERATION_PROMPT,
    supervisor=MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    render=MINUTES_OBJECTIVE_RENDER_PROMPT,
    render_template=MINUTES_RENDER_TEMPLATE_PROMPT,
)

_PROMPTS: dict[str, MinutesPromptSet] = {
    VIEW_OBJECTIVE: _OBJECTIVE_SET,
    VIEW_PERSONAL: _PERSONAL_SET,
    VIEW_ROLE_TEMPLATE: _ROLE_TEMPLATE_SET,
    VIEW_AGENDA_OBJECTIVE: _AGENDA_OBJECTIVE_SET,
}


def resolve_prompt_view(shared_context: str, mode: str | None = None) -> str:
    """从上下文判定 view；agenda 优先，其次 personal/role_template/objective。"""
    if is_agenda_enhanced_mode(shared_context):
        return VIEW_AGENDA_OBJECTIVE
    resolved = (mode or parse_perspective_mode(shared_context) or "").strip().lower()
    if resolved == VIEW_PERSONAL:
        return VIEW_PERSONAL
    if resolved == VIEW_ROLE_TEMPLATE:
        return VIEW_ROLE_TEMPLATE
    return VIEW_OBJECTIVE


def minutes_prompt_set(view: str) -> MinutesPromptSet:
    """view → prompt 组合；未知 view 回退 objective，避免把请求打成 500。"""
    return _PROMPTS.get((view or "").strip().lower(), _OBJECTIVE_SET)


def prompt_label(view: str) -> str:
    """日志/LLM label 用的短名（保持既有 label 口径）。"""
    if view == VIEW_AGENDA_OBJECTIVE:
        return "agenda"
    if view == VIEW_PERSONAL:
        return "personal"
    return "objective"


def is_agenda_view(view: str) -> bool:
    return view == VIEW_AGENDA_OBJECTIVE


__all__ = [
    "MinutesPromptSet",
    "is_agenda_view",
    "minutes_prompt_set",
    "prompt_label",
    "resolve_prompt_view",
]
