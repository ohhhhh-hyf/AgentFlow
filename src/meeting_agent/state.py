from __future__ import annotations

from typing import TypedDict

class MeetingState(TypedDict, total=False):
    """LangGraph 在本次运行的所有节点间传递的内存状态。"""

    transcript: str
    user: dict
    meeting_understanding: dict
    perspective_profile: dict
    minutes_draft: dict
    extracted_action_items: dict
    final_report: dict
