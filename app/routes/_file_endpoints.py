"""产物文件 GET 端点：统一入口的下载 + 按域注册的预览。

- ``download``         GET /api/agent/v1/file/{request_id}/{file_name}
                       （附件下载；file_name 取响应 ``data.file_name``。域与线名不需要 ——
                        产物目录 ``data/{user_id}/output/{request_id}/`` 由 request_id 唯一确定）
- ``preview_endpoint`` GET /api/v1/{domain}/{task}/preview?request_id=&user_id=
                       （``{task}.html``，text/html inline 渲染）

> 预览是唯一仍需路径里带域与线名的端点：它靠 ``{task}.html`` 的命名约定定位产物。
> 便捷下载（``GET /file?request_id=&user_id=``，文件名自动回退）已于 2026-09 移除：
> 能力被指定名下载覆盖，且后者无回退歧义。详见 ``app/tasklines.py`` 模块注释。

user_id 支持 URL 参数 ?user_id= 或 X-User-Id 请求头（二者取一，都没有返回 400）；
产物只允许定位 data/{user_id}/output/{request_id}/ 内的文件（resolve_output_file 校验），
不暴露 /data 整树。
"""
from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, Query
from fastapi.responses import FileResponse

from ..outputs import resolve_output_file


def _user_id(user_id: Optional[str], x_user_id: Optional[str]) -> str:
    uid = (user_id or "").strip() or (x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="缺少 user_id（URL 参数 ?user_id= 或 X-User-Id 请求头）")
    return uid


async def download(
    request_id: str,
    file_name: str,
    user_id: Optional[str] = Query(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    """指定文件名下载：GET /file/{request_id}/{file_name}，附件形式返回（强制下载）。"""
    uid = _user_id(user_id, x_user_id)
    path = resolve_output_file(uid, request_id, file_name)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"产物文件不存在：output/{request_id}/{file_name}",
        )
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")


def preview_endpoint(task: str):
    """受控预览：GET /preview?request_id=…&user_id=…，返回 {task}.html
    （text/html，不带 attachment 头 → 浏览器直接渲染展示）。

    工厂保留 ``task`` 参数：预览没有 file_name 入参，只能按 ``{task}.html`` 命名约定取。
    """

    async def _handler(
        request_id: str,
        user_id: Optional[str] = Query(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ):
        uid = _user_id(user_id, x_user_id)
        path = resolve_output_file(uid, request_id, f"{task}.html")
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=f"页面版产物不存在：output/{request_id}/{task}.html",
            )
        return FileResponse(path, media_type="text/html")

    _handler.__name__ = f"{task}_preview"
    return _handler


__all__ = ["download", "preview_endpoint"]
