"""points —— 知识点总结任务组。

流水线：agent（生成知识点总结草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。
"""

from .steps.points_agent import PointsAgent
from .steps.points_render import PointsRender
from .steps.points_supervisor import PointsSupervisor

__all__ = [
    "PointsAgent",
    "PointsRender",
    "PointsSupervisor",
]
