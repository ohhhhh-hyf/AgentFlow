"""consensus_decision —— 共识决策任务组。

流水线：agent（生成共识决策草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。
"""

from .steps.consensus_decision_agent import ConsensusDecisionAgent
from .steps.consensus_decision_render import ConsensusDecisionRender
from .steps.consensus_decision_supervisor import ConsensusDecisionSupervisor

__all__ = [
    "ConsensusDecisionAgent",
    "ConsensusDecisionRender",
    "ConsensusDecisionSupervisor",
]
