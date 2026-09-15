"""Async task API backed by Redis job state."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import StreamingResponse

from ..config import run_mode
from ..executor import payload_from_request, run_inline
from ..id_worker import next_request_id
from ..job_store import JobStoreError, job_store
from ..schemas import Extra, TaskRequest
from ..tasks import LINE_NAMES

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class AsyncTaskRequest(TaskRequest):
    """Async task submission body: URL task fields plus the existing TaskRequest."""

    domain: str
    task: str


def _store():
    try:
        store = job_store()
        store.ping()  # Redis 挂了要回 503（而不是让命令异常冒成 500）
        return store
    except JobStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _validate_domain_task(domain: str, task: str) -> tuple[str, str]:
    domain = (domain or "").strip().lower()
    task = (task or "").strip()
    if domain not in {"meeting", "notes"}:
        raise HTTPException(status_code=400, detail="domain 仅支持 meeting / notes")
    line = LINE_NAMES.get(task)
    if line is None:
        raise HTTPException(status_code=404, detail=f"任务线不存在：{task}")
    if domain == "meeting" and line not in {
        "minutes",
        "actions",
        "risks",
        "minutes_styles",
        "minutes_trace",
        "consensus_decision",
    }:
        raise HTTPException(status_code=404, detail=f"meeting 不支持任务线：{task}")
    if domain == "notes" and line not in {"graph", "library", "catalog", "checklist"}:
        raise HTTPException(status_code=404, detail=f"notes 不支持任务线：{task}")
    return domain, line


def _ndjson(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


@router.post("")
async def submit_task(
    req: AsyncTaskRequest,
    background_tasks: BackgroundTasks,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> dict:
    """Submit an async task and return immediately with job_id.

    执行位置由 ``AGENTFLOW_RUN_MODE`` 决定：
    - ``queue``：请求体落 Redis + 任务入队，由 ``python -m app.worker`` 消费（生产主路径）；
    - ``inline``：交给本进程的 BackgroundTasks 执行（缺省，起个 uvicorn 就能用）。
    """
    domain, line = _validate_domain_task(req.domain, req.task)
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="缺少 X-User-Id")
    request_id = (x_request_id or "").strip() or next_request_id()
    store = _store()
    job_id = store.new_job_id()
    store.create_job(
        job_id=job_id,
        request_id=request_id,
        user_id=user_id,
        domain=domain,
        task=line,
    )
    task_req = TaskRequest(
        texts=req.texts,
        docs=req.docs,
        extra=req.extra if isinstance(req.extra, Extra) else Extra.model_validate(req.extra),
        time=req.time,
    )
    if run_mode() == "queue":
        try:
            store.set_payload(
                job_id,
                payload_from_request(
                    domain, line, task_req, user_id=user_id, request_id=request_id
                ),
            )
            store.enqueue(job_id)
        except Exception as exc:  # noqa: BLE001 - 入队失败要让调用方知道，不能留个永远 queued 的 job
            store.mark_failed(job_id, f"任务入队失败：{exc}", attempts=0)
            raise HTTPException(status_code=503, detail=f"任务入队失败：{exc}") from exc
    else:
        background_tasks.add_task(
            run_inline,
            job_id,
            domain,
            line,
            task_req,
            user_id,
            request_id,
        )
    return {
        "code": 0,
        "message": "queued",
        "job_id": job_id,
        "request_id": request_id,
        "status": "queued",
        "run_mode": run_mode(),
    }


@router.get("/{job_id}")
async def get_task(job_id: str) -> dict:
    store = _store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")
    result = dict(job)
    result.pop("result", None)  # 正文可能很大，状态查询不返回
    return result


@router.get("/{job_id}/result")
async def get_task_result(job_id: str) -> dict:
    store = _store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")
    if job.get("status") != "succeeded":
        raise HTTPException(status_code=409, detail=f"任务尚未完成：{job.get('status')}")
    result = job.get("result") or {}
    return result if isinstance(result, dict) else {"result": result}


@router.get("/{job_id}/stream")
async def stream_task_events(job_id: str, cursor: int = 0) -> StreamingResponse:
    store = _store()
    if store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")

    async def events():
        index = max(0, int(cursor or 0))
        while True:
            batch = store.events_since(job_id, index)
            if batch:
                for item in batch:
                    yield _ndjson(item)
                index += len(batch)
            job = store.get_job(job_id) or {}
            if job.get("status") in {"succeeded", "failed", "cancelled"} and not batch:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="application/x-ndjson")


__all__ = ["router"]
