"""会议多 Agent 组件。

每个 Agent 都是独立、可替换的类；编排关系位于 orchestrator.py。
"""

from .action_items_agent import ActionItemsAgent
from .final_integration_agent import FinalIntegrationAgent
from .meeting_understanding_agent import MeetingUnderstandingAgent
from .minutes_generation_agent import MinutesGenerationAgent
from .perspective_modeling_agent import PerspectiveModelingAgent

__all__ = [
    "ActionItemsAgent",
    "FinalIntegrationAgent",
    "MeetingUnderstandingAgent",
    "MinutesGenerationAgent",
    "PerspectiveModelingAgent",
]
