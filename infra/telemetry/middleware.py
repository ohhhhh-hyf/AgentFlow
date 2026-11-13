"""HTTP 流量非侵入式日志中间件 (完全外挂，0 侵入业务)."""
from __future__ import annotations

import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("telemetry.http")


class LoggingMiddleware(BaseHTTPMiddleware):
    """外挂式 HTTP 请求/响应生命周期记录器."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 健康探针跳过记录
        if path in ("/", "/health", "/favicon.ico"):
            return await call_next(request)

        method = request.method
        req_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        user_id = request.headers.get("X-User-Id") or "default"

        logger.info(
            f"[HTTP:REQ] method={method} path={path} req_id={req_id} user_id={user_id}"
        )

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            dur = time.perf_counter() - start_time
            # 确保 X-Request-Id 始终在响应头中
            if "X-Request-Id" not in response.headers:
                response.headers["X-Request-Id"] = req_id

            logger.info(
                f"[HTTP:RES] method={method} path={path} req_id={req_id} status={response.status_code} dur={dur:.3f}s"
            )
            return response
        except Exception as exc:
            dur = time.perf_counter() - start_time
            logger.error(
                f"[HTTP:ERR] method={method} path={path} req_id={req_id} dur={dur:.3f}s error={exc}",
                exc_info=True,
            )
            raise
