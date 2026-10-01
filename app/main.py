"""AgentFlow FastAPI 入口（兼容层）。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
或新架构入口：
    uvicorn app.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from app.api.main import app, main
from app.schemas import TaskResponse
from app.tasks import ApiError

__all__ = ["ApiError", "TaskResponse", "app", "main"]

if __name__ == "__main__":
    main()
