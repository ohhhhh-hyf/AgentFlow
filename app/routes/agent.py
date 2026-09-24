"""统一任务入口 ``/api/agent/v1``：同步 / 流式 / 下载三类端点。

2026-09 收敛：域与任务名不再由 URL 路径表达，改为请求体字段（``DomainTaskRequest``），
于是这三类端点从「每条任务线各一套」收敛为一套（预览端点除外，见 ``_registry.py``）::

    POST /api/agent/v1                                同步，阻塞到出结果（TaskResponse）
    POST /api/agent/v1/stream                         流式，NDJSON 事件流
    GET  /api/agent/v1/file/{request_id}/{file_name}  下载产物（file_name 取响应 data.file_name）

请求体的 ``domain`` / ``task`` 由 ``app.tasklines.resolve_line`` 校验（域不存在 400、
域内无此线 404），校验在跑任务之前完成，失败不触发模型；这也让同步接口的任务名校验
从「全局并集」收紧为「按域」（``notes`` + ``minutes`` 现在干净地 404，而不是落到域装配里报错）。

请求头：``X-Request-Id`` 可选（缺省生成 request_ + 分布式数字 ID）、``X-User-Id`` 必填。
业务错误（``app.tasks.ApiError``）由 ``app/main.py`` 的全局处理器转成
``{code, request_id, message}``，与收敛前逐字一致。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header

from ..id_worker import next_request_id
from ..schemas import DomainTaskRequest, TaskResponse
from ..tasklines import TaskLineNotFound, resolve_line
from ..tasks import ApiError, run_task, stream_task
from ._file_endpoints import download

router = APIRouter(prefix="/api/agent/v1", tags=["agent"])


def _headers(x_request_id: str | None, x_user_id: str | None) -> tuple[str, str]:
    """X-Request-Id 可选；缺省时生成 request_ + 分布式数字 ID。X-User-Id 必填由任务层校验。"""
    request_id = (x_request_id or "").strip() or next_request_id()
    user_id = (x_user_id or "").strip()
    return request_id, user_id


def _line(req: DomainTaskRequest) -> tuple[str, str]:
    """请求体的 domain + task → (域, 线名)；非法组合转 ApiError（400 / 404）。"""
    try:
        return resolve_line(req.domain, req.task)
    except TaskLineNotFound as exc:
        raise ApiError(exc.status, exc.message) from exc


@router.post("", response_model=TaskResponse, name="agent_run")
async def run_agent(
    req: DomainTaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    """同步执行一条任务线：阻塞到出结果（请求体带 domain / task，见 API.md 2.5.1）。"""
    domain, line = _line(req)
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task(domain, line, req, user_id=user_id, request_id=request_id)


@router.post("/stream", name="agent_stream")
async def stream_agent(
    req: DomainTaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    """流式执行一条任务线：NDJSON 事件流，请求体与同步接口一致（见 API.md 2.5.2）。"""
    domain, line = _line(req)
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await stream_task(domain, line, req, user_id=user_id, request_id=request_id)


router.add_api_route(
    "/file/{request_id}/{file_name}",
    download,
    methods=["GET"],
    name="agent_download",
    summary="下载任务产物（request_id 为生成时的 X-Request-Id，file_name 为响应 data.file_name）",
)

__all__ = ["router"]
