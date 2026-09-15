"""notes 域路由：``/api/v1/notes/{task}`` 与 ``/api/v1/notes/{task}/stream``。

任务线清单在 ``app/tasklines.py``（唯一来源），注册逻辑在 ``app/routes/_registry.py``。
产物端点只给有页面版产物的线（graph / checklist）：library 无落盘产物、
catalog 的 file_name 指向知识目录 JSON（不在 output 目录）。
"""
from __future__ import annotations

from fastapi import APIRouter

from ._registry import register_domain

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])

register_domain(router, "notes")

__all__ = ["router"]
