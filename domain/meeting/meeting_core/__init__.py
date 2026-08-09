"""meeting_core —— 会议理解与视角建模（核心 Agent）。

这两个 Agent 是会议处理的事实底座：
- MeetingUnderstandingAgent：客观提取议题、决策、风险、未决问题
- PerspectiveModelingAgent：把用户画像映射到本次会议，构建关注视角
"""

from .meeting_understanding_agent import MeetingUnderstandingAgent
from .perspective_modeling_agent import PerspectiveModelingAgent

__all__ = [
    "MeetingUnderstandingAgent",
    "PerspectiveModelingAgent",
]
