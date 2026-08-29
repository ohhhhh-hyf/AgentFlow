"""AgentFlow FastAPI 入口。

启动：uvicorn app.main:app --host 0.0.0.0 --port 8000
或：python -m app.main
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .config import load_env  # noqa: E402
from .routes import meeting, notes  # noqa: E402
from .schemas import TaskResponse  # noqa: E402
from .tasks import ApiError  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(title="AgentFlow API", version="1.0.0")

app.include_router(meeting.router)
app.include_router(notes.router)

# html 产物预览（可选）：data/{user_id}/output/{request_id}/{task}.html
_data_dir = PROJECT_ROOT / "data"
if _data_dir.is_dir():
    app.mount("/data", StaticFiles(directory=str(_data_dir)), name="data")


@app.exception_handler(ApiError)
async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    request_id = _request.headers.get("X-Request-Id", "")
    # 错误响应不携带 monitor / data（无监控数据与产物，省去全 0 / 空字段噪音）
    return JSONResponse(
        status_code=exc.status,
        content=TaskResponse(
            code=exc.status,
            request_id=request_id,
            message=exc.message,
        ).model_dump(exclude={"monitor", "data"}),
    )


@app.exception_handler(Exception)
async def _unexpected_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未捕获异常")
    request_id = _request.headers.get("X-Request-Id", "")
    return JSONResponse(
        status_code=500,
        content=TaskResponse(
            code=500,
            request_id=request_id,
            message=f"服务内部错误：{exc}",
        ).model_dump(exclude={"monitor", "data"}),
    )


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict:
    """健康检查 + 任务线清单（领域加载失败时降级报告）。"""
    from .config import load_domain

    lines: dict[str, list[str]] = {}
    degraded: list[str] = []
    for name in ("meeting", "notes"):
        try:
            ctx = load_domain(name)
            lines[name] = sorted(ctx.task_lines)
        except Exception as exc:  # noqa: BLE001 - 领域装配失败不影响健康检查
            degraded.append(f"{name}: {exc}")
    payload: dict[str, object] = {"status": "ok", "task_lines": lines}
    if degraded:
        payload["status"] = "degraded"
        payload["degraded"] = degraded
    return payload


def main() -> None:
    import uvicorn

    load_env()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
