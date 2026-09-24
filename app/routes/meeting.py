"""meeting 域路由：产物预览 ``/api/v1/meeting/{task}/preview``。

任务线清单在 ``app/tasklines.py``（唯一来源），注册逻辑在 ``app/routes/_registry.py``；
同步 / 流式 / 下载三类端点与域无关（域与线名走请求体），注册在统一入口 ``app/routes/agent.py``。
"""
from __future__ import annotations

from fastapi import APIRouter

from ._registry import register_domain

router = APIRouter(prefix="/api/v1/meeting", tags=["meeting"])

register_domain(router, "meeting")

__all__ = ["router"]
