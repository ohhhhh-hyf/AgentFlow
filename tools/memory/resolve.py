"""归属解析入口（notes 域）：学科名单键绑定，不做实体模糊挂钩。

meeting 域的项目归属（规则绑定 + 记忆向量库语义兜底）由 ``tools.meeting_memory``
独立实现；本模块只服务 notes（graph）的共享能力：解析入口只有 ``resolve()``，
注入和回写共用同一份 Bind。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .store import (
    empty_record,
    list_records,
    load_record_any,
    next_project_id,
    safe_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Bind:
    """一次运行的项目归属。inject 与 write 必须用同一份。"""

    project_id: str | None
    create: bool
    hits: int = 0
    strong: int = 0
    entities: tuple[str, ...] = ()
    project_key: str = ""


def resolve_notes(
    project_root: Path,
    user_id: str,
    subject: str | None = None,
    explicit_id: str | None = None,
) -> Bind:
    """笔记归属：同一用户只按学科名分档，不做实体模糊挂钩。"""
    label = (subject or explicit_id or "").strip()
    if not (user_id or "").strip() or not label:
        return Bind(project_id=None, create=False)
    pid = safe_id(label)
    rec = load_record_any(project_root, "notes", user_id, pid)
    return Bind(
        project_id=pid,
        create=not bool(rec),
        project_key=label,
    )


def resolve(
    project_root: Path,
    domain: str,
    user_id: str,
    transcript: str,
    explicit_id: str | None = None,
    subject: str | None = None,
) -> Bind:
    """解析本次应归属的项目。

    当前唯一可达路径是 notes（graph 线）：user_id + 学科名（--subject，或
    --project 当作学科）单键绑定。meeting 域的归属（规则绑定 + 记忆向量库
    语义兜底）见 ``tools.meeting_memory.bind``；transcript 为域签名兼容保留，
    非 notes 域不注入、不新建。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return Bind(project_id=None, create=False)

    if (domain or "").strip() == "notes":
        return resolve_notes(project_root, user_id, subject, explicit_id)

    return Bind(project_id=None, create=False)


def materialize(
    project_root: Path,
    domain: str,
    user_id: str,
    bind: Bind,
) -> dict | None:
    """得到可读写的 record。create 时分配新 id；未绑定返回 None。

    读取 memory/{线名}/{project_id}/record.json；写回（persist）同路径。"""
    if bind.project_id:
        rec = load_record_any(project_root, domain, user_id, bind.project_id)
        return rec or empty_record(user_id, bind.project_id, domain)
    if bind.create:
        pid = next_project_id(list_records(project_root, domain, user_id))
        return empty_record(user_id, pid, domain)
    return None


__all__ = [
    "Bind",
    "materialize",
    "resolve",
    "resolve_notes",
]
