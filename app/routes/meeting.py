"""meeting 域路由：``/api/v1/meeting/{task}`` 与 ``/api/v1/meeting/{task}/stream``。

任务线清单在 ``app/tasklines.py``（唯一来源），注册逻辑在 ``app/routes/_registry.py``。
"""
from __future__ import annotations

from fastapi import APIRouter

from ._registry import register_domain

router = APIRouter(prefix="/api/v1/meeting", tags=["meeting"])

register_domain(router, "meeting")

__all__ = ["router"]
