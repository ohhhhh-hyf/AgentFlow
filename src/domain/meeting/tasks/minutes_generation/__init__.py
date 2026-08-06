"""minutes_generation —— 纪要生成任务组。

流水线：agent（生成纪要草稿）→ supervisor（领域审核 + 全局标准）→ render（渲染正文）。
"""

from .minutes_generation_agent import MinutesGenerationAgent
from .minutes_generation_render import MinutesGenerationRender
from .minutes_generation_supervisor import MinutesGenerationSupervisor

__all__ = [
    "MinutesGenerationAgent",
    "MinutesGenerationRender",
    "MinutesGenerationSupervisor",
]
