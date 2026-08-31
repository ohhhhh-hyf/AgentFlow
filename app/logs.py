"""请求日志缓冲：按 request_id 收集后端运行日志，供调试台前端展示。

机制：
- 全局环形缓冲（最多 3000 条），挂到 root logger；
- ``_current_request`` contextvar 标记当前请求 ID（run_task / stream_task 入口设置，
  ``asyncio.to_thread`` 会复制调用方 context，任务线程内日志自动带上 request_id）；
- ``GET /api/v1/logs?request_id=xxx&after=epoch秒`` 拉取该请求的日志窗口。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from contextvars import ContextVar
from typing import Any

MAX_BUFFER = 3000

_current_request: ContextVar[str] = ContextVar("agentflow_request_id", default="")
_tls = threading.local()
_buffer: deque[tuple[str, float, str, str]] = deque(maxlen=MAX_BUFFER)


def _bound_request_id() -> str:
    rid = (_current_request.get() or "").strip()
    if rid:
        return rid
    return str(getattr(_tls, "request_id", "") or "").strip()


class _RequestLogHandler(logging.Handler):
    """把日志行按当前 request_id 存入环形缓冲。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rid = _bound_request_id()
            _buffer.append((rid, record.created, record.levelname, self.format(record)))
        except Exception:  # noqa: BLE001 - 日志缓冲失败不影响业务
            pass


def install() -> None:
    """挂载一次日志缓冲 handler（幂等），并把 root 级别降到 INFO（调试台需要 INFO 日志）。"""
    root = logging.getLogger()
    if any(isinstance(h, _RequestLogHandler) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    handler = _RequestLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


def set_request_id(request_id: str) -> Any:
    """标记当前请求 ID，返回 reset token（finally 中 reset）。"""
    rid = (request_id or "").strip()
    _tls.request_id = rid
    return _current_request.set(rid)


def reset_request_id(token: Any) -> None:
    _tls.request_id = ""
    _current_request.reset(token)


def logs_for(request_id: str, after: float = 0.0, limit: int = 500) -> list[dict[str, str]]:
    """取某请求的日志（按时间升序，after 为起始 epoch 秒，最多 limit 条）。"""
    out: list[dict[str, str]] = []
    for rid, created, level, message in _buffer:
        if rid == request_id and created >= after:
            out.append(
                {
                    "time": time.strftime("%H:%M:%S", time.localtime(created)),
                    "level": level,
                    "message": message,
                }
            )
            if len(out) >= limit:
                break
    return out
