"""按 ``app/tasklines.py`` 的声明注册一个域的全部路由。

每条任务线注册（字段含义见 tasklines.TaskLine）：

```
POST /{line}                          同步接口（response_model=TaskResponse）
POST /{line}/stream                   流式接口（NDJSON 事件流）
GET  /{line}/file/{request_id}/{name} 指定文件名下载        ┐ 仅 files=True 的任务线
GET  /{line}/preview?request_id=&user_id= 浏览器预览          ┘
```

路由的 path / name / summary / response_model 与拆分前逐字一致（可用接口清单脚本比对）。
已移除的形态见 ``app/tasklines.py`` 模块注释（便捷下载、同义 URL）。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header

from ..id_worker import next_request_id
from ..schemas import TaskRequest, TaskResponse
from ..tasklines import DOMAINS
from ..tasks import run_task, stream_task
from ._file_endpoints import (
    download_endpoint as _download_endpoint,
    preview_endpoint as _preview_endpoint,
)


def _headers(x_request_id: str | None, x_user_id: str | None) -> tuple[str, str]:
    """X-Request-Id 可选；缺省时生成 request_ + 分布式数字 ID。X-User-Id 必填由任务层校验。"""
    request_id = (x_request_id or "").strip() or next_request_id()
    user_id = (x_user_id or "").strip()
    return request_id, user_id


def _run_endpoint(domain: str, line: str):
    """同步端点工厂：POST /{line}。"""

    async def _handler(
        req: TaskRequest,
        x_request_id: Optional[str] = Header(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ) -> TaskResponse:
        request_id, user_id = _headers(x_request_id, x_user_id)
        return await run_task(domain, line, req, user_id=user_id, request_id=request_id)

    _handler.__name__ = f"{line}_run"
    return _handler


def _stream_endpoint(domain: str, line: str):
    """流式端点工厂：POST /{line}/stream（NDJSON 事件流）。"""

    async def _handler(
        req: TaskRequest,
        x_request_id: Optional[str] = Header(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ):
        request_id, user_id = _headers(x_request_id, x_user_id)
        return await stream_task(domain, line, req, user_id=user_id, request_id=request_id)

    _handler.__name__ = f"{line}_stream"
    return _handler


def register_domain(router: APIRouter, domain: str) -> None:
    """把某个域的全部任务线路由挂到 ``router``（调用方的 prefix 形如 ``/api/v1/meeting``）。"""
    for item in DOMAINS[domain]:
        line = item.line
        router.add_api_route(
            f"/{line}/stream",
            _stream_endpoint(domain, line),
            methods=["POST"],
            name=f"{line}_stream",
            summary=f"流式{line}（NDJSON 事件流，请求体与同步接口一致）",
        )
        if item.files:
            router.add_api_route(
                f"/{line}/file/{{request_id}}/{{file_name}}",
                _download_endpoint(line),
                methods=["GET"],
                name=f"{line}_download",
                summary=f"下载{line}产物（request_id 为生成时的 X-Request-Id，file_name 为响应 data.file_name）",
            )
            router.add_api_route(
                f"/{line}/preview",
                _preview_endpoint(line),
                methods=["GET"],
                name=f"{line}_preview",
                summary=f"浏览器预览{line}页面版产物（?request_id=…&user_id=…，text/html 直接渲染）",
            )
        router.add_api_route(
            f"/{line}",
            _run_endpoint(domain, line),
            methods=["POST"],
            name=f"{line}_run",
            response_model=TaskResponse,
        )


__all__ = ["register_domain"]
