"""异步任务执行体：API 内联模式与独立 worker 共用一份实现。

从 ``app/routes/tasks.py`` 抽出来，让两种执行模式行为完全一致：
- ``inline``：API 进程内由 BackgroundTasks 调用 ``run_inline``；
- ``queue``：``python -m app.worker`` 从 Redis 队列取任务后调用 ``execute_job``。

执行体只负责"跑一条任务并写事件流"，终态判定（重试还是失败）交给调用方：
worker 有重试与租约，inline 则失败即终态。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .job_store import job_store
from .schemas import Extra, TaskRequest
from .tasks import ApiError, iter_task_events

logger = logging.getLogger("app.executor")


@dataclass
class JobOutcome:
    """一条任务的执行结果。"""

    ok: bool
    retryable: bool = False
    message: str = ""
    cost_time: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def payload_from_request(
    domain: str,
    task: str,
    req: TaskRequest,
    *,
    user_id: str,
    request_id: str,
) -> dict[str, Any]:
    """请求体序列化：worker 与 API 是不同进程，输入必须能通过 Redis 传递。"""
    return {
        "domain": domain,
        "task": task,
        "user_id": user_id,
        "request_id": request_id,
        "texts": dict(req.texts or {}),
        "docs": list(req.docs or []),
        "extra": req.extra.model_dump(),
        "time": req.time or "",
        "memory": req.memory,
    }


def request_from_payload(payload: dict[str, Any]) -> tuple[str, str, TaskRequest, str, str]:
    """还原 ``payload_from_request`` 的内容：返回 (domain, task, req, user_id, request_id)。"""
    data = dict(payload or {})
    domain = str(data.get("domain") or "").strip()
    task = str(data.get("task") or "").strip()
    extra_raw = data.get("extra")
    extra = (
        extra_raw
        if isinstance(extra_raw, Extra)
        else Extra.model_validate(extra_raw if isinstance(extra_raw, dict) else {})
    )
    req = TaskRequest(
        texts={k: v for k, v in dict(data.get("texts") or {}).items() if isinstance(v, str)},
        docs=[str(name) for name in list(data.get("docs") or [])],
        memory=bool(data.get("memory", False) or getattr(extra, "memory", False)),
        extra=extra,
        time=str(data.get("time") or getattr(extra, "time", "")),
    )
    return domain, task, req, str(data.get("user_id") or ""), str(data.get("request_id") or "")


def _touch_progress(store, job_id: str, event: dict[str, Any], start: float) -> None:
    """phase / chunk 事件只更新进度字段，不改状态机。"""
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


async def execute_job(
    job_id: str,
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
) -> JobOutcome:
    """执行一条任务：写事件流与成功终态；失败只返回结论，终态由调用方写。

    重试判定依据错误码：4xx（输入类错误，如缺必填/文件不存在）重试无意义；
    5xx 与未捕获异常视为可重试（LLM 抖动、依赖临时不可用等）。
    """
    store = job_store()
    start = time.time()
    logger.info(
        "[async:execute] job_id=%s domain=%s task=%s request_id=%s user_id=%s",
        job_id,
        domain,
        task,
        request_id,
        user_id,
    )
    try:
        event_gen = iter_task_events(domain, task, req, user_id=user_id, request_id=request_id)
    except ApiError as exc:
        # 校验/输入类错误：直接给出终态结论，不重试
        logger.warning(
            "[async:error] job_id=%s request_id=%s code=%d message=%s",
            job_id,
            request_id,
            exc.status,
            exc.message,
        )
        store.append_event(
            job_id, {"type": "error", "code": exc.status, "message": exc.message}
        )
        return JobOutcome(False, False, exc.message, round(time.time() - start, 1))
    except Exception as exc:  # noqa: BLE001 - 准备阶段异常算可重试的运行错误
        logger.exception(
            "[async:failed] job_id=%s request_id=%s error=%s",
            job_id,
            request_id,
            exc,
        )
        message = f"任务准备失败：{exc}"
        store.append_event(job_id, {"type": "error", "code": 500, "message": message})
        return JobOutcome(False, True, message, round(time.time() - start, 1))

    try:
        async for event in event_gen:
            etype = event.get("type")
            if etype == "phase" or etype == "chunk":
                # 进度写状态字段，事件仍进事件流：/stream 要能回放增量文本（断线重连也不丢）
                _touch_progress(store, job_id, event, start)
                store.append_event(job_id, event)
                continue
            if etype == "done":
                # 先落终态事件再翻状态：否则 /stream 可能在本轮无新事件时提前退出，
                # 客户端就拿不到最终结果（旧实现的状态先翻、事件后写）。
                store.append_event(job_id, event)
                monitor = event.get("monitor") or {}
                data = event.get("data") or {}
                cost = float(
                    (monitor or {}).get("cost_time") or round(time.time() - start, 1)
                )
                tokens = int((monitor or {}).get("token_usage") or 0)
                file_name = str((data or {}).get("file_name") or "")
                store.update_job(
                    job_id,
                    status="succeeded",
                    phase="done",
                    message="success",
                    error="",
                    finished_at=time.time(),
                    cost_time=cost,
                    token_usage=tokens,
                    cache_hit=int((monitor or {}).get("cache_hit") or 0),
                    file_name=file_name,
                    result=event,
                )
                logger.info(
                    "[async:succeeded] job_id=%s request_id=%s cost=%.2fs tokens=%d file=%s",
                    job_id,
                    request_id,
                    cost,
                    tokens,
                    file_name,
                )
                return JobOutcome(True, False, "", round(time.time() - start, 1))
            if etype == "error":
                message = str(event.get("message") or "任务运行失败")
                code = int(event.get("code") or 500)
                logger.warning(
                    "[async:error] job_id=%s request_id=%s code=%d message=%s",
                    job_id,
                    request_id,
                    code,
                    message,
                )
                # 事件先落盘（保留完整错误信息与错误码），终态由调用方写
                store.append_event(job_id, event)
                return JobOutcome(False, code >= 500, message, round(time.time() - start, 1))
    except Exception as exc:  # noqa: BLE001 - 迭代中断（含 worker 取消）视为可重试
        logger.exception(
            "[async:failed] job_id=%s request_id=%s error=%s",
            job_id,
            request_id,
            exc,
        )
        message = f"任务运行失败：{exc}"
        store.append_event(job_id, {"type": "error", "code": 500, "message": message})
        return JobOutcome(False, True, message, round(time.time() - start, 1))

    message = "任务未返回结果（事件流提前结束）"
    logger.warning(
        "[async:aborted] job_id=%s request_id=%s message=%s",
        job_id,
        request_id,
        message,
    )
    store.append_event(job_id, {"type": "error", "code": 500, "message": message})
    return JobOutcome(False, True, message, round(time.time() - start, 1))


async def run_inline(
    job_id: str,
    domain: str,
    task: str,
    req: TaskRequest,
    user_id: str,
    request_id: str,
) -> None:
    """inline 模式：API 进程内执行一次，失败即终态（没有 worker 兜底，不重试）。"""
    logger.info(
        "[async:inline_start] job_id=%s domain=%s task=%s request_id=%s",
        job_id,
        domain,
        task,
        request_id,
    )
    store = job_store()
    store.claim(job_id, "inline", lease=False)
    outcome = await execute_job(job_id, domain, task, req, user_id, request_id)
    logger.info(
        "[async:inline_done] job_id=%s ok=%s cost=%.2fs message=%s",
        job_id,
        outcome.ok,
        outcome.cost_time,
        outcome.message or "success",
    )
    if outcome.ok:
        return
    store.mark_failed(
        job_id,
        outcome.message,
        attempts=1,
        cost_time=outcome.cost_time,
    )


__all__ = [
    "JobOutcome",
    "execute_job",
    "payload_from_request",
    "request_from_payload",
    "run_inline",
]
