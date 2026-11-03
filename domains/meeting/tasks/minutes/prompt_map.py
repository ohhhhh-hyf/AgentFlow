"""minutes 的 prompt 映射。

- 生成 / 审核：``minutes_prompt_set`` 接收编排层已裁决的 view，返回对应 prompt；
- 渲染：``render_template_prompt`` 按 view 选择模板渲染 prompt。
  personal 使用独立渲染 prompt；objective / role_template 共用通用渲染 prompt。
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
    MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
    MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT,
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

_TOPIC_MAJOR_SET = MinutesPromptSet(
    view=VIEW_AGENDA_OBJECTIVE,
    generation=MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
    supervisor=MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT,
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


def _normalized_layout(layout: str) -> str:
    return (layout or "").strip().lower() or "column_major"


def is_topic_major(view: str, layout: str) -> bool:
    """是否为 agenda_objective 下的 topic_major 布局。"""
    return is_agenda_view((view or "").strip().lower()) and (
        _normalized_layout(layout) == "topic_major"
    )


def render_template_prompt(view: str, layout: str = "column_major") -> str:
    """渲染 prompt 按 agenda / personal / 其它三路分派；agenda 再按 layout 分派。"""
    normalized = (view or "").strip().lower()
    if is_agenda_view(normalized):
        if _normalized_layout(layout) == "topic_major":
            return MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT
        return MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    if normalized == VIEW_PERSONAL:
        return MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT
    return MINUTES_RENDER_TEMPLATE_PROMPT


def minutes_prompt_set(view: str, layout: str = "column_major") -> MinutesPromptSet:
    """view/layout → prompt 组合；未知 view 回退 objective，避免把请求打成 500。"""
    normalized = (view or "").strip().lower()
    if is_topic_major(normalized, layout):
        return _TOPIC_MAJOR_SET
    return _PROMPTS.get(normalized, _OBJECTIVE_SET)


def prompt_label(view: str, layout: str = "column_major") -> str:
    """日志/LLM label 用的短名（保持既有 label 口径）。"""
    normalized = (view or "").strip().lower()
    if is_topic_major(normalized, layout):
        return "agenda_topic"
    if normalized == VIEW_AGENDA_OBJECTIVE:
        return "agenda"
    if normalized == VIEW_PERSONAL:
        return "personal"
    return "objective"


def is_agenda_view(view: str) -> bool:
    return view == VIEW_AGENDA_OBJECTIVE


__all__ = [
    "MinutesPromptSet",
    "is_agenda_view",
    "is_topic_major",
    "minutes_prompt_set",
    "prompt_label",
    "render_template_prompt",
]
