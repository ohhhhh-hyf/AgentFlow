"""minutes_styles —— 多样式纪要任务组。

流水线：agent（生成多样式纪要草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。
"""

from .steps.minutes_styles_agent import MultiStylesAgent
from .steps.minutes_styles_render import MultiStylesRender
from .steps.minutes_styles_supervisor import MultiStylesSupervisor

__all__ = [
    "MultiStylesAgent",
    "MultiStylesRender",
    "MultiStylesSupervisor",
]
