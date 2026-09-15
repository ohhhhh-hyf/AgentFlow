"""Async task API backed by Redis job state."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import StreamingResponse

from ..id_worker import next_request_id
from ..job_store import JobStoreError, job_store
from ..schemas import Extra, TaskRequest
from ..tasks import ApiError, LINE_NAMES, stream_task

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class AsyncTaskRequest(TaskRequest):
    """Async task submission body: URL task fields plus the existing TaskRequest."""

    domain: str
    task: str


def _store():
    try:
        return job_store()
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
    """Submit an async task and return immediately with job_id."""
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
    background_tasks.add_task(
        _run_background_job,
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
    }


@router.get("/{job_id}")
async def get_task(job_id: str) -> dict:
    store = _store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{job_id}")
    result = dict(job)
    result.pop("result", None)
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


async def _run_background_job(
    job_id: str,
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
) -> None:
    store = job_store()
    start = time.time()
    store.update_job(
        job_id,
        status="running",
        phase="prepare",
        message="running",
        started_at=start,
        cost_time=0.0,
    )
    store.append_event(job_id, {"type": "started", "job_id": job_id, "request_id": request_id})
    try:
        response = await stream_task(
            domain,
            task,
            req,
            user_id=user_id,
            request_id=request_id,
        )
        async for raw in response.body_iterator:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                _record_runtime_event(store, job_id, event, start)
                if event.get("type") != "error":
                    store.append_event(job_id, event)
    except ApiError as exc:
        _fail_job(store, job_id, start, exc.message)
    except Exception as exc:  # noqa: BLE001
        _fail_job(store, job_id, start, f"任务运行失败：{exc}")


def _record_runtime_event(store, job_id: str, event: dict, start: float) -> None:
    etype = event.get("type")
    if etype == "phase":
        node = str(event.get("node") or "")
        store.update_job(
            job_id,
            status="running",
            phase=node,
            message=f"running:{node}",
            cost_time=round(time.time() - start, 1),
        )
    elif etype == "chunk":
        line = str(event.get("line") or "")
        title = str(event.get("title") or "")
        store.update_job(
            job_id,
            status="running",
            phase=f"{line}:render",
            message=title or "rendering",
            cost_time=round(time.time() - start, 1),
        )
    elif etype == "done":
        monitor = event.get("monitor") or {}
        data = event.get("data") or {}
        store.update_job(
            job_id,
            status="succeeded",
            phase="done",
            message="success",
            finished_at=time.time(),
            cost_time=float((monitor or {}).get("cost_time") or round(time.time() - start, 1)),
            token_usage=int((monitor or {}).get("token_usage") or 0),
            cache_hit=int((monitor or {}).get("cache_hit") or 0),
            file_name=str((data or {}).get("file_name") or ""),
            result=event,
        )
    elif etype == "error":
        _fail_job(store, job_id, start, str(event.get("message") or "任务运行失败"))


def _fail_job(store, job_id: str, start: float, message: str) -> None:
    event = {
        "type": "error",
        "code": 500,
        "message": message,
        "ts": time.time(),
    }
    store.update_job(
        job_id,
        status="failed",
        phase="error",
        message="failed",
        error=message,
        finished_at=time.time(),
        cost_time=round(time.time() - start, 1),
    )
    store.append_event(job_id, event)


__all__ = ["router"]
