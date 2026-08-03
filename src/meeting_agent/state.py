from __future__ import annotations

from typing import TypedDict


class MeetingState(TypedDict, total=False):
    """LangGraph 在一次运行中跨节点传递的共享上下文。"""

    transcript: str
    user: dict
    meeting_understanding: dict
    perspective_profile: dict
    minutes_draft: dict
    extracted_action_items: dict
    supervisor_review: dict
    minutes_revision_feedback: list[str]
    actions_revision_feedback: list[str]
    revision_count: int
    final_report: dict
    human_decision: str
