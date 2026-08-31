"""meeting 域路由：/api/v1/meeting/{task} 与 /api/v1/meeting/{task}/stream。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

from ..outputs import resolve_output_file
from ..schemas import TaskRequest, TaskResponse
from ..tasks import run_task, stream_task

router = APIRouter(prefix="/api/v1/meeting", tags=["meeting"])


def _headers(x_request_id: str | None, x_user_id: str | None) -> tuple[str, str]:
    """X-Request-Id 必填（调用方追踪 ID，建议用 UUID；产物目录以它为名）；X-User-Id 必填。"""
    request_id = (x_request_id or "").strip()
    user_id = (x_user_id or "").strip()
    if not request_id:
        raise HTTPException(
            status_code=400,
            detail="缺少 X-Request-Id（调用方追踪 ID，建议用 UUID；产物目录 data/{user_id}/output/{request_id}/ 以它为名）",
        )
    return request_id, user_id


def _download_endpoint(task: str):
    """下载端点工厂：GET /api/v1/meeting/{task}/file/{request_id}/{file_name}。

    request_id 为生成时的 X-Request-Id，file_name 为响应 data.file_name；
    产物文件 data/{user_id}/output/{request_id}/{file_name} 以附件形式返回（强制下载）。
    """

    async def _handler(
        request_id: str,
        file_name: str,
        x_user_id: Optional[str] = Header(default=None),
    ):
        user_id = (x_user_id or "").strip()
        if not user_id:
            raise HTTPException(status_code=400, detail="缺少 X-User-Id（产物按用户隔离）")
        path = resolve_output_file(user_id, request_id, file_name)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=f"产物文件不存在：output/{request_id}/{file_name}",
            )
        return FileResponse(path, filename=file_name, media_type="application/octet-stream")

    _handler.__name__ = f"{task}_download"
    return _handler


def _stream_endpoint(task: str):
    """流式端点工厂：POST /api/v1/meeting/{task}/stream（NDJSON 事件流）。"""

    async def _handler(
        req: TaskRequest,
        x_request_id: Optional[str] = Header(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ):
        request_id, user_id = _headers(x_request_id, x_user_id)
        return await stream_task("meeting", task, req, user_id=user_id, request_id=request_id)

    _handler.__name__ = f"{task}_stream"
    return _handler


for _task in ("minutes", "actions", "risks", "minutes_styles", "minutes_trace"):
    router.add_api_route(
        f"/{_task}/stream",
        _stream_endpoint(_task),
        methods=["POST"],
        name=f"{_task}_stream",
        summary=f"流式{_task}（NDJSON 事件流，请求体与同步接口一致）",
    )
    router.add_api_route(
        f"/{_task}/file/{{request_id}}/{{file_name}}",
        _download_endpoint(_task),
        methods=["GET"],
        name=f"{_task}_download",
        summary=f"下载{_task}产物（request_id 为生成时的 X-Request-Id，file_name 为响应 data.file_name）",
    )


@router.post("/minutes", response_model=TaskResponse)
async def minutes_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("meeting", "minutes", req, user_id=user_id, request_id=request_id)


@router.post("/actions", response_model=TaskResponse)
async def actions_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("meeting", "actions", req, user_id=user_id, request_id=request_id)


@router.post("/risks", response_model=TaskResponse)
async def risks_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("meeting", "risks", req, user_id=user_id, request_id=request_id)


@router.post("/minutes_styles", response_model=TaskResponse)
async def minutes_styles_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("meeting", "minutes_styles", req, user_id=user_id, request_id=request_id)


@router.post("/minutes_trace", response_model=TaskResponse)
async def minutes_trace_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("meeting", "minutes_trace", req, user_id=user_id, request_id=request_id)
