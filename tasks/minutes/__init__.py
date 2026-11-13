"""tasks.minutes package.

提供会议纪要端到端流式直出能力，支持普通纪要与议题纪要两大主模态。
"""
from tasks.minutes.agent import generate_minutes, stream_minutes_agent
from tasks.minutes.prompts import (
    AGENDA_COLUMN_MAJOR_PROMPT,
    AGENDA_TOPIC_MAJOR_PROMPT,
    NORMAL_MINUTES_PROMPT,
    select_minutes_prompt,
)

__all__ = [
    "stream_minutes_agent",
    "generate_minutes",
    "select_minutes_prompt",
    "NORMAL_MINUTES_PROMPT",
    "AGENDA_COLUMN_MAJOR_PROMPT",
    "AGENDA_TOPIC_MAJOR_PROMPT",
]
