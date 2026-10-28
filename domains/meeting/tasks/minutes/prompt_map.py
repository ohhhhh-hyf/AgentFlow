"""minutes 的 prompt 映射。

- 生成 / 审核：``minutes_prompt_set`` 接收编排层已裁决的 view，返回对应 prompt；
- 渲染：``render_template_prompt`` 按 view 选择模板渲染 prompt。
  当前 objective / personal / role_template 共用同一份渲染 prompt。
"""
from __future__ import annotations

from dataclasses import dataclass

from ...views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_OBJECTIVE,
    VIEW_PERSONAL,
    VIEW_ROLE_TEMPLATE,
)
from .prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)


@dataclass(frozen=True)
class MinutesPromptSet:
    """一个 view 对应的生成 / 审核 prompt 组合。"""

    view: str
    generation: str
    supervisor: str


_OBJECTIVE_SET = MinutesPromptSet(
    view=VIEW_OBJECTIVE,
    generation=MINUTES_OBJECTIVE_GENERATION_PROMPT,
    supervisor=MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
)

_PERSONAL_SET = MinutesPromptSet(
    view=VIEW_PERSONAL,
    generation=MINUTES_PERSONAL_GENERATION_PROMPT,
    supervisor=MINUTES_PERSONAL_SUPERVISOR_PROMPT,
)

_AGENDA_OBJECTIVE_SET = MinutesPromptSet(
    view=VIEW_AGENDA_OBJECTIVE,
    generation=MINUTES_AGENDA_GENERATION_PROMPT,
    supervisor=MINUTES_AGENDA_SUPERVISOR_PROMPT,
)

# 职业模板沿用 objective prompt（与既有行为一致），但保留自己的 view 标签。
_ROLE_TEMPLATE_SET = MinutesPromptSet(
    view=VIEW_ROLE_TEMPLATE,
    generation=MINUTES_OBJECTIVE_GENERATION_PROMPT,
    supervisor=MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
)

_PROMPTS: dict[str, MinutesPromptSet] = {
    VIEW_OBJECTIVE: _OBJECTIVE_SET,
    VIEW_PERSONAL: _PERSONAL_SET,
    VIEW_ROLE_TEMPLATE: _ROLE_TEMPLATE_SET,
    VIEW_AGENDA_OBJECTIVE: _AGENDA_OBJECTIVE_SET,
}


def render_template_prompt(view: str) -> str:
    """渲染 prompt 只分 agenda / 非 agenda；view 已由编排层裁决。"""
    if is_agenda_view((view or "").strip().lower()):
        return MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    return MINUTES_RENDER_TEMPLATE_PROMPT


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
    "render_template_prompt",
]
