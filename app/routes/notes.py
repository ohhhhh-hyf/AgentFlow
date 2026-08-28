"""notes 域路由：/api/v1/notes/{task}。"""
from __future__ import annotations

import uuid

from typing import Optional

from fastapi import APIRouter, Header

from ..schemas import TaskRequest, TaskResponse
from ..tasks import run_task

router = APIRouter(prefix="/api/v1/notes", tags=["notes"])


def _headers(x_request_id: str | None, x_user_id: str | None) -> tuple[str, str]:
    return (x_request_id or "").strip() or uuid.uuid4().hex, (x_user_id or "").strip()


@router.post("/graph", response_model=TaskResponse)
async def graph_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("notes", "graph", req, user_id=user_id, request_id=request_id)


@router.post("/library", response_model=TaskResponse)
async def library_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("notes", "library", req, user_id=user_id, request_id=request_id)


@router.post("/catalog", response_model=TaskResponse)
async def catalog_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("notes", "catalog", req, user_id=user_id, request_id=request_id)


@router.post("/checklist", response_model=TaskResponse)
async def checklist_run(
    req: TaskRequest,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TaskResponse:
    request_id, user_id = _headers(x_request_id, x_user_id)
    return await run_task("notes", "checklist", req, user_id=user_id, request_id=request_id)
