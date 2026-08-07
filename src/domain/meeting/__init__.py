from pathlib import Path

from .meeting_factory import MeetingAgentFactory
from .models import (
    ActionItemsSupervisorReview,
    ActionsReport,
    MinutesReport,
    MinutesSupervisorReview,
    UserIdentity,
)
from .orchestrator import MeetingAgentSystem

# 领域自包含的样例资源根目录（summary / profile / template）
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

__all__ = [
    "ActionItemsSupervisorReview",
    "ActionsReport",
    "MeetingAgentFactory",
    "MeetingAgentSystem",
    "MinutesReport",
    "MinutesSupervisorReview",
    "SAMPLES_DIR",
    "UserIdentity",
]
