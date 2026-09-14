"""产物文件 GET 端点工厂：指定名下载 / 便捷下载 / 受控预览。meeting 与 notes 域共用。

工厂与域无关，调用方在各自 router 上注册相对路径（如 /file、/preview）：
- download_endpoint        GET /{task}/file/{request_id}/{file_name}
- query_download_endpoint  GET /{task}/file?request_id=…&user_id=…（文件名免填，自动回退 html → {task}.md → result.md）
- preview_endpoint         GET /{task}/preview?request_id=…&user_id=…（{task}.html，text/html inline 渲染）

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


def download_endpoint(task: str):
    """指定文件名下载：GET /file/{request_id}/{file_name}，附件形式返回（强制下载）。"""

    async def _handler(
        request_id: str,
        file_name: str,
        user_id: Optional[str] = Query(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ):
        uid = _user_id(user_id, x_user_id)
        path = resolve_output_file(uid, request_id, file_name)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=f"产物文件不存在：output/{request_id}/{file_name}",
            )
        return FileResponse(path, filename=file_name, media_type="application/octet-stream")

    _handler.__name__ = f"{task}_download"
    return _handler


def query_download_endpoint(task: str):
    """便捷下载：GET /file?request_id=…&user_id=…，文件名免填，
    按 {task}.html → {task}.md → result.md 自动回退，附件形式返回。
    """

    async def _handler(
        request_id: str,
        user_id: Optional[str] = Query(default=None),
        x_user_id: Optional[str] = Header(default=None),
    ):
        uid = _user_id(user_id, x_user_id)
        for file_name in (f"{task}.html", f"{task}.md", "result.md"):
            path = resolve_output_file(uid, request_id, file_name)
            if path is not None:
                return FileResponse(path, filename=file_name, media_type="application/octet-stream")
        raise HTTPException(
            status_code=404,
            detail=f"产物文件不存在：output/{request_id}/（{task}.html 或 {task}.md）",
        )

    _handler.__name__ = f"{task}_file_download"
    return _handler


def preview_endpoint(task: str):
    """受控预览：GET /preview?request_id=…&user_id=…，返回 {task}.html
    （text/html，不带 attachment 头 → 浏览器直接渲染展示）。
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
