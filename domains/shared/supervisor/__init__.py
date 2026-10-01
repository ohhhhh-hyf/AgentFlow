"""跨域共享：全局监督标准 + 结构化生成步基类。

全局监督器通过 prompt 注入的方式参与执行：整体标准被拼入各任务组的
supervisor prompt，由任务 supervisor 一次调用完成双重评判。
生成步基类则收拢 agent / supervisor 两条样板链的重复实现。
"""
from .steps import StructuredDomainSupervisor, StructuredGenerationAgent
from .supervisor import GlobalSupervisor

__all__ = [
    "GlobalSupervisor",
    "StructuredDomainSupervisor",
    "StructuredGenerationAgent",
]
