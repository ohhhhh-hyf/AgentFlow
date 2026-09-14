"""risk —— 风险分析任务组。

流水线：agent（生成风险分析草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。
"""

from .steps.risks_agent import RiskAgent
from .steps.risks_render import RiskRender
from .steps.risks_supervisor import RiskSupervisor

RisksAgent = RiskAgent
RisksRender = RiskRender
RisksSupervisor = RiskSupervisor

__all__ = [
    "RiskAgent",
    "RiskRender",
    "RiskSupervisor",
    "RisksAgent",
    "RisksRender",
    "RisksSupervisor",
]
