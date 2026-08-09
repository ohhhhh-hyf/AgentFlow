"""tasks —— 任务型 Agent 组。

每个任务组是一条独立流水线（agent → supervisor → render），
彼此并行、互不阻塞：
- minutes_generation：纪要生成
- action_items：待办提取
"""

from . import action_items, minutes_generation

__all__ = ["action_items", "minutes_generation"]
