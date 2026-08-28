"""meeting 域路由：/api/v1/meeting/{task}。"""
from __future__ import annotations

import uuid

from typing import Optional

from fastapi import APIRouter, Header

from ..schemas import TaskRequest, TaskResponse
from ..tasks import run_task

router = APIRouter(prefix="/api/v1/meeting", tags=["meeting"])


def _headers(x_request_id: str | None, x_user_id: str | None) -> tuple[str, str]:
    return (x_request_id or "").strip() or uuid.uuid4().hex, (x_user_id or "").strip()


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
