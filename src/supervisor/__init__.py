"""全局监督器 —— 提供所有领域都应遵从的整体监督标准。

通过 prompt 注入的方式参与执行：整体标准被拼入各任务组的
supervisor prompt，由任务 supervisor 一次调用完成双重评判。
"""

from .supervisor import GlobalSupervisor, inject_global_standard
from .supervisor_prompt import GLOBAL_SUPERVISOR_PROMPT

__all__ = [
    "GLOBAL_SUPERVISOR_PROMPT",
    "GlobalSupervisor",
    "inject_global_standard",
]
