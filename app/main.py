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

from typing import Optional  # noqa: E402

from fastapi import FastAPI, Header, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .config import load_env  # noqa: E402
from .routes import meeting, notes  # noqa: E402
from .schemas import TaskResponse  # noqa: E402
from .tasks import ApiError  # noqa: E402

logger = logging.getLogger(__name__)

app = FastAPI(title="AgentFlow API", version="1.0.0")

app.include_router(meeting.router)
app.include_router(notes.router)


@app.get("/api/v1/files", tags=["system"])
async def list_input_files(
    user_id: str = "",
    subject: str = "",
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> JSONResponse:
    """调试台用：列出 data/{user_id}/docs/ 可引用文件。"""
    from .outputs import list_user_input_files

    uid = (x_user_id or user_id or "").strip()
    if not uid:
        return JSONResponse(
            status_code=400,
            content={"detail": "缺少 X-User-Id（按用户列出 data/{user_id}/docs/）"},
        )
    payload = list_user_input_files(uid, subject)
    logger.info(
        "列出输入文件 user=%s docs=%s from %s",
        uid,
        len(payload.get("docs") or []),
        payload.get("docs_dir") or "",
    )
    return JSONResponse(content=payload)


# html 产物预览（可选）：data/{user_id}/output/{request_id}/{task}.html
_data_dir = PROJECT_ROOT / "data"
if _data_dir.is_dir():
    app.mount("/data", StaticFiles(directory=str(_data_dir)), name="data")

# 简易接口调试前端（可选）：front/ 目录存在时挂载，访问 /front/ 打开
_front_dir = PROJECT_ROOT / "front"
if _front_dir.is_dir():
    app.mount("/front", StaticFiles(directory=str(_front_dir), html=True), name="front")

# 样例文件只读挂载（调试台"从文件加载"用）：samples/meeting/file、samples/notes/file
_samples_dir = PROJECT_ROOT / "samples"
if _samples_dir.is_dir():
    app.mount("/samples", StaticFiles(directory=str(_samples_dir)), name="samples")

# 请求日志缓冲（调试台展示用）：挂 root logger，按 request_id 收集
from .logs import install as _install_logs  # noqa: E402

_install_logs()


@app.get("/", include_in_schema=False)
async def _index() -> HTMLResponse:
    """根路径直接打开接口调试台（front/index.html）。"""
    index_file = _front_dir / "index.html"
    if index_file.is_file():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return JSONResponse(content={"detail": "front 目录不存在"}, status_code=404)


@app.get("/api/v1/logs", tags=["system"])
async def request_logs(
    request_id: str,
    after: float = 0.0,
) -> JSONResponse:
    """调试台用：拉取某次请求（X-Request-Id）的后端运行日志。

    after 为起始 epoch 秒（前端提交时刻），只返回该窗口内的日志。
    """
    from .logs import logs_for

    return JSONResponse(content={"logs": logs_for(request_id, after=after)})


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
