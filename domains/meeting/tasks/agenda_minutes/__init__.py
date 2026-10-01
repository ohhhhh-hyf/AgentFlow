"""agenda_minutes -- 议程驱动型会议纪要任务线。

流水线：agent（双向锚定对齐与四要素提炼）→ supervisor（领域审核把关）→ render（渲染双模态产物）。
"""
from __future__ import annotations

from .steps.agenda_minutes_agent import AgendaMinutesAgent
from .steps.agenda_minutes_render import AgendaMinutesRender
from .steps.agenda_minutes_supervisor import AgendaMinutesSupervisor

__all__ = [
    "AgendaMinutesAgent",
    "AgendaMinutesRender",
    "AgendaMinutesSupervisor",
]
