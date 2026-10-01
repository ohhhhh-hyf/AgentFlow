"""产物文件 GET 端点：统一入口的产物下载。

- ``download``         GET /api/agent/v1/file/{request_id}/{file_name}
                       （附件下载；file_name 取响应 ``data.file_name``。域与线名不需要 ——
                        产物目录 ``data/{user_id}/output/{request_id}/`` 由 request_id 唯一确定）

user_id 支持 URL 参数 ?user_id= 或 X-User-Id 请求头（二者取一，都没有返回 400）；
产物只允许定位 data/{user_id}/output/{request_id}/ 内的文件（resolve_output_file 校验），
不暴露 /data 整树。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.outputs import resolve_output_file

logger = logging.getLogger("app.api.routes.file")


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
    logger.info(
        "[api:download] request_id=%s file_name=%s user_id=%s",
        request_id,
        file_name,
        uid,
    )
    path = resolve_output_file(uid, request_id, file_name)
    if path is None:
        logger.warning(
            "[api:download:not_found] request_id=%s file_name=%s user_id=%s",
            request_id,
            file_name,
            uid,
        )
        raise HTTPException(
            status_code=404,
            detail=f"产物文件不存在：output/{request_id}/{file_name}",
        )
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")


__all__ = ["download"]
