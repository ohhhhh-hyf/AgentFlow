"""请求日志：按 request_id 隔离缓冲，调试台用 SSE 推送（不再靠高频轮询）。

机制：
- 每条请求一个环形缓冲（最多 500 条），最多保留 24 个请求；
- 无 request_id / uvicorn 访问日志不入库，避免把轮询或健康检查写进缓冲；
- 新日志通过线程安全队列推给 SSE 订阅者，前端一条连接看到实时进度。
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import queue
import threading
import time
from collections import OrderedDict, deque
from contextvars import ContextVar
from typing import Any, AsyncIterator, Callable, TypeVar

MAX_PER_REQUEST = 500
MAX_REQUESTS = 24

_T = TypeVar("_T")

_current_request: ContextVar[str] = ContextVar("agentflow_request_id", default="")
_tls = threading.local()
_lock = threading.Lock()
_active: set[str] = set()
_seq = 0

# rid -> deque of (seq, created, level, message)
_buffers: OrderedDict[str, deque[tuple[int, float, str, str]]] = OrderedDict()
# rid -> waiters
_waiters: dict[str, list[queue.SimpleQueue]] = {}


def _bound_request_id() -> str:
    rid = (_current_request.get() or "").strip()
    if rid:
        return rid
    rid = str(getattr(_tls, "request_id", "") or "").strip()
    if rid:
        return rid
    with _lock:
        if len(_active) == 1:
            return next(iter(_active))
    return ""


def _skip_record(record: logging.LogRecord) -> bool:
    name = record.name or ""
    if name.startswith("uvicorn."):
        return True
    msg = record.getMessage()
    if "/api/v1/logs" in msg:
        return True
    return False


def _publish(rid: str, seq: int, created: float, level: str, message: str) -> None:
    item = (seq, created, level, message)
    with _lock:
        buf = _buffers.get(rid)
        if buf is None:
            while len(_buffers) >= MAX_REQUESTS:
                old, _ = _buffers.popitem(last=False)
                _waiters.pop(old, None)
            buf = deque(maxlen=MAX_PER_REQUEST)
            _buffers[rid] = buf
        else:
            _buffers.move_to_end(rid)
        buf.append(item)
        waiters = list(_waiters.get(rid) or [])
    payload = _entry(seq, created, level, message)
    for waiter in waiters:
        try:
            waiter.put_nowait(payload)
        except Exception:  # noqa: BLE001
            pass


def _entry(seq: int, created: float, level: str, message: str) -> dict[str, Any]:
    return {
        "seq": seq,
        "created": created,
        "time": time.strftime("%H:%M:%S", time.localtime(created)),
        "level": level,
        "message": message,
    }


class _RequestLogHandler(logging.Handler):
    """把带 request_id 的日志行写入该请求的缓冲，并通知 SSE 订阅者。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if _skip_record(record):
                return
            rid = (getattr(record, "request_id", None) or "").strip() or _bound_request_id()
            if not rid:
                return
            global _seq
            with _lock:
                _seq += 1
                seq = _seq
            self.format(record)  # 填充 record.message
            _publish(rid, seq, record.created, record.levelname, record.getMessage())
        except Exception:  # noqa: BLE001 - 日志缓冲失败不影响业务
            pass


def install() -> None:
    """挂载一次日志缓冲 handler（幂等），并把 root 级别降到 INFO（调试台需要 INFO 日志）。"""
    root = logging.getLogger()
    if any(isinstance(h, _RequestLogHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    handler = _RequestLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)


def set_request_id(request_id: str) -> Any:
    """标记当前请求 ID，返回 reset token（finally 中 reset）。"""
    rid = (request_id or "").strip()
    _tls.request_id = rid
    if rid:
        with _lock:
            _active.add(rid)
            if rid not in _buffers:
                while len(_buffers) >= MAX_REQUESTS:
                    old, _ = _buffers.popitem(last=False)
                    _waiters.pop(old, None)
                _buffers[rid] = deque(maxlen=MAX_PER_REQUEST)
    return _current_request.set(rid)


def reset_request_id(token: Any) -> None:
    rid = str(getattr(_tls, "request_id", "") or "").strip()
    if rid:
        with _lock:
            _active.discard(rid)
    _tls.request_id = ""
    _current_request.reset(token)


async def to_thread(fn: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
    """asyncio.to_thread，并把 request_id（contextvar + 线程局部）带进工作线程。"""
    ctx = contextvars.copy_context()
    rid = _bound_request_id()

    def runner() -> _T:
        _tls.request_id = rid
        return ctx.run(lambda: fn(*args, **kwargs))

    return await asyncio.to_thread(runner)


def logs_for(request_id: str, after: float = 0.0, limit: int = 500) -> list[dict[str, str]]:
    """取某请求的日志快照（按时间升序）。"""
    rid = (request_id or "").strip()
    if not rid:
        return []
    with _lock:
        buf = list(_buffers.get(rid) or ())
    out: list[dict[str, str]] = []
    for seq, created, level, message in buf:
        if created < after:
            continue
        item = _entry(seq, created, level, message)
        out.append({"time": item["time"], "level": item["level"], "message": item["message"]})
        if len(out) >= limit:
            break
    return out


def _subscribe(rid: str) -> tuple[queue.SimpleQueue, list[dict[str, Any]]]:
    waiter: queue.SimpleQueue = queue.SimpleQueue()
    with _lock:
        _waiters.setdefault(rid, []).append(waiter)
        buf = list(_buffers.get(rid) or ())
    snapshot = [_entry(*row) for row in buf]
    return waiter, snapshot


def _unsubscribe(rid: str, waiter: queue.SimpleQueue) -> None:
    with _lock:
        items = _waiters.get(rid) or []
        _waiters[rid] = [item for item in items if item is not waiter]
        if not _waiters[rid]:
            _waiters.pop(rid, None)


def _queue_get(waiter: queue.SimpleQueue, timeout: float) -> dict[str, Any] | None:
    try:
        return waiter.get(timeout=timeout)
    except queue.Empty:
        return None


def _sse_data(item: dict[str, Any]) -> str:
    payload = {
        "time": item["time"],
        "level": item["level"],
        "message": item["message"],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def iter_log_sse(request_id: str, after: float, request: Any) -> AsyncIterator[str]:
    """SSE 事件流：先推快照，再推增量；客户端断开即停。"""
    rid = (request_id or "").strip()
    if not rid:
        yield "event: error\ndata: {\"detail\":\"缺少 request_id\"}\n\n"
        return
    waiter, snapshot = _subscribe(rid)
    last_seq = 0
    try:
        for item in snapshot:
            if item["created"] < after:
                continue
            last_seq = max(last_seq, int(item["seq"]))
            yield _sse_data(item)
        while True:
            if await request.is_disconnected():
                break
            item = await asyncio.to_thread(_queue_get, waiter, 8.0)
            if item is None:
                yield ": ping\n\n"
                continue
            seq = int(item.get("seq") or 0)
            if seq <= last_seq or float(item.get("created") or 0) < after:
                continue
            last_seq = seq
            yield _sse_data(item)
    finally:
        _unsubscribe(rid, waiter)
