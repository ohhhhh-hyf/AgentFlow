"""core.registry —— 动态注册中心。"""
from .task_registry import TaskBundle, get_task, list_tasks, register_task

__all__ = ["TaskBundle", "get_task", "list_tasks", "register_task"]
