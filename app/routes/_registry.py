"""按 ``app/tasklines.py`` 的声明注册一个域的**预览**路由。

同步 / 流式 / 下载三类端点与域无关（域与线名走请求体），注册在 ``app/routes/agent.py``；
这里只剩预览 —— 它是唯一还需要路径里带域与线名的端点，因为它靠 ``{line}.html`` 的
命名约定定位产物::

    GET /{line}/preview?request_id=&user_id=   仅 files=True 的任务线

路由的 path / name / summary 与拆分前逐字一致（可用接口清单脚本比对）。
已移除的端点形态见 ``app/tasklines.py`` 模块注释（路径带 {domain}/{task} 的三类统一端点）。
"""
from __future__ import annotations

from fastapi import APIRouter

from ..tasklines import DOMAINS
from ._file_endpoints import preview_endpoint as _preview_endpoint


def register_domain(router: APIRouter, domain: str) -> None:
    """把某个域的预览路由挂到 ``router``（调用方的 prefix 形如 ``/api/v1/meeting``）。"""
    for item in DOMAINS[domain]:
        if not item.files:
            continue
        line = item.line
        router.add_api_route(
            f"/{line}/preview",
            _preview_endpoint(line),
            methods=["GET"],
            name=f"{line}_preview",
            summary=f"浏览器预览{line}页面版产物（?request_id=…&user_id=…，text/html 直接渲染）",
        )


__all__ = ["register_domain"]
