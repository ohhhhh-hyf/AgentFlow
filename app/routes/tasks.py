"""Async task API backed by Redis job state.

四个接口统一返回同一份"任务快照"（见 ``_job_view``）：::

    {
      "code": 0,                    // 0=成功；非 0=HTTP 状态码
      "job_id": "job_…",
      "request_id": "request_…",    // 下载产物要用（/file/{request_id}/{file_name}）
      "status": "queued",           // queued / running / succeeded / failed
      "message": "queued",          // 阶段名 或 失败原因（人可读）
      "text": null,                 // 产物正文：仅结果接口有值
      "file_name": "",              // 产物文件名
      "monitor": {"token_usage": 0, "cache_hit": 0, "cost_time": 0.0}   // 消耗，零值起步
    }

差别只在填充程度：提交=queued 零值、状态=实时进度、结果=带正文。事件流（``_event_view``）
每行多一个 ``type``，字段名与上面一致；``done`` 那行与结果接口逐字一致。
错误统一为 ``{"code": <HTTP 状态码>, "message": "<原因>"}``（``AsyncApiError``）。
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header
from fastapi.responses import StreamingResponse

from ..config import run_mode
from ..executor import payload_from_request, run_inline
from ..id_worker import next_request_id
from ..job_store import JobStoreError, job_store
from ..schemas import DomainTaskRequest, Extra, TaskRequest, ndjson_line as _ndjson
from ..tasklines import TaskLineNotFound, resolve_line

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


class AsyncApiError(Exception):
    """异步接口的业务错误：响应体统一为 ``{"code": status, "message": message}``。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class AsyncTaskRequest(DomainTaskRequest):
    """异步提交请求体：与统一入口 ``/api/agent/v1`` 同形（domain + task + TaskRequest）。"""


def _store():
    try:
        store = job_store()
        store.ping()  # Redis 挂了要回 503（而不是让命令异常冒成 500）
        return store
    except JobStoreError as exc:
        raise AsyncApiError(503, str(exc)) from exc


def _validate_domain_task(domain: str, task: str) -> tuple[str, str]:
    """校验 domain + task 组合，返回 (域, 代码线名)。白名单与统一入口共用一份。

    判定规则与文案在 ``app.tasklines.resolve_line``（同步 / 流式同样调它），这里只把
    错误转成异步接口的 ``AsyncApiError``。
    """
    try:
        return resolve_line(domain, task)
    except TaskLineNotFound as exc:
        raise AsyncApiError(exc.status, exc.message) from exc


def _job_view(job: dict[str, Any], *, with_text: bool = False) -> dict[str, Any]:
    """任务记录 → 统一响应体（8 字段；有质量提示时多一个 ``quality_warning``）。

    ``message`` 在失败时展示 ``error``（具体原因），其余时候展示 ``message``
    （``queued`` / ``running:阶段`` / ``success`` / ``requeued(attempt N)``）。
    """
    status = str(job.get("status") or "")
    reason = str(job.get("error") or "")
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    data = (result or {}).get("data") or {}
    monitor = {
        "token_usage": int(job.get("token_usage") or 0),
        "cache_hit": int(job.get("cache_hit") or 0),
        "cost_time": float(job.get("cost_time") or 0.0),
    }
    view: dict[str, Any] = {
        "code": 0,
        "job_id": str(job.get("job_id") or ""),
        "request_id": str(job.get("request_id") or ""),
        "status": status,
        "message": reason if (status == "failed" and reason) else str(job.get("message") or ""),
        # 正文只在结果接口（with_text=True）且已成功时返回，状态轮询不背大文本
        "text": str(data.get("text") or "") if (with_text and status == "succeeded") else None,
        "file_name": str(data.get("file_name") or job.get("file_name") or ""),
        "monitor": monitor,
    }
    warning = (result or {}).get("quality_warning")
    if with_text and warning:
        view["quality_warning"] = warning
    return view


def _event_view(job_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """事件流每行 → 统一形状：``type`` + ``job_id`` + ``status`` + ``message`` 恒定，其余按需。"""
    etype = str((event or {}).get("type") or "")
    if etype == "queued":
        return {
            "type": etype, "job_id": job_id, "request_id": str(event.get("request_id") or ""),
            "status": "queued", "message": "queued",
        }
    if etype == "started":
        return {
            "type": etype, "job_id": job_id, "status": "running", "message": "running",
            "attempt": int(event.get("attempt") or 0),
        }
    if etype == "phase":
        node = str(event.get("node") or "")
        return {"type": etype, "job_id": job_id, "status": "running", "message": f"running:{node}"}
    if etype == "chunk":
        return {
            "type": etype, "job_id": job_id, "status": "running",
            "message": str(event.get("title") or ""), "text": str(event.get("text") or ""),
        }
    if etype == "requeued":
        attempt = int(event.get("attempt") or 0)
        return {
            "type": etype, "job_id": job_id, "status": "queued",
            "message": f"requeued(attempt {attempt})", "attempt": attempt,
        }
    if etype == "error":
        return {
            "type": etype, "job_id": job_id, "status": "failed",
            "message": str(event.get("message") or ""), "code": int(event.get("code") or 500),
        }
    if etype == "done":
        monitor = event.get("monitor") or {}
        data = event.get("data") or {}
        view: dict[str, Any] = {
            "type": etype, "code": 0, "job_id": job_id,
            "request_id": str(event.get("request_id") or ""),
            "status": "succeeded", "message": "success",
            "text": str(data.get("text") or ""),
            "file_name": str(data.get("file_name") or ""),
            "monitor": {
                "token_usage": int(monitor.get("token_usage") or 0),
                "cache_hit": int(monitor.get("cache_hit") or 0),
                "cost_time": float(monitor.get("cost_time") or 0.0),
            },
        }
        if event.get("quality_warning"):
            view["quality_warning"] = event["quality_warning"]
        return view
    return {"type": etype, "job_id": job_id}


@router.post("")
async def submit_task(
    req: AsyncTaskRequest,
    background_tasks: BackgroundTasks,
    x_request_id: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> dict:
    """Submit an async task and return immediately with the task snapshot (status=queued).

    执行位置由 ``AGENTFLOW_RUN_MODE`` 决定（见 ``GET /api/v1/health`` 的 ``run_mode``）：

    - ``queue``：请求体落 Redis + 任务入队，由 ``python -m app.worker`` 消费（生产主路径）；
    - ``inline``：交给本进程的 BackgroundTasks 执行（缺省，起个 uvicorn 就能用）。
    """
    domain, line = _validate_domain_task(req.domain, req.task)
    user_id = (x_user_id or "").strip()
    if not user_id:
        raise AsyncApiError(400, "缺少 X-User-Id")
    request_id = (x_request_id or "").strip() or next_request_id()
    store = _store()
    job_id = store.new_job_id()
    payload = store.create_job(
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
            raise AsyncApiError(503, f"任务入队失败：{exc}") from exc
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
    return _job_view(payload)


@router.get("/{job_id}")
async def get_task(job_id: str) -> dict:
    """查询任务状态：返回统一快照（不含正文，轮询体量小）。"""
    store = _store()
    job = store.get_job(job_id)
    if job is None:
        raise AsyncApiError(404, f"任务不存在：{job_id}")
    return _job_view(job)


@router.get("/{job_id}/result")
async def get_task_result(job_id: str) -> dict:
    """获取任务结果：仍是统一快照，成功的任务会带上 ``text`` / ``file_name``。

    任务未完成或失败同样返回该快照（``status`` 为 ``queued`` / ``running`` / ``failed``，
    失败原因在 ``message``），**不再用 409** —— 四个接口形状一致，调用方无需分支。
    """
    store = _store()
    job = store.get_job(job_id)
    if job is None:
        raise AsyncApiError(404, f"任务不存在：{job_id}")
    return _job_view(job, with_text=True)


@router.get("/{job_id}/stream")
async def stream_task_events(job_id: str, cursor: int = 0) -> StreamingResponse:
    """订阅任务事件流（NDJSON，每行多一个 ``type``；``done`` 与结果接口逐字一致）。"""
    store = _store()
    if store.get_job(job_id) is None:
        raise AsyncApiError(404, f"任务不存在：{job_id}")

    async def events():
        index = max(0, int(cursor or 0))
        while True:
            batch = store.events_since(job_id, index)
            if batch:
                for item in batch:
                    yield _ndjson(_event_view(job_id, item))
                index += len(batch)
            job = store.get_job(job_id) or {}
            if job.get("status") in {"succeeded", "failed", "cancelled"} and not batch:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="application/x-ndjson")


__all__ = ["AsyncApiError", "router"]
