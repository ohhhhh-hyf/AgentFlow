"""notes 域对引擎暴露的钩子（记忆：归属解析 + 图注入/回写）。

引擎不再 import 本域模块，只问 ``hooks_for("notes")``（2026-09-22 决策）；
域内实现差异（resolve/prepare/persist 的参数形状）由本文件的适配器吸收。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.core.domain_hooks import DomainHooks

from .memory.runtime import MEMORY_LINES, persist, prepare


def _prepare_memory(
    *,
    project_root,
    domain: str,
    user_id: str,
    transcript: str,
    line_names: list[str],
    project_id: str | None = None,
    subject: str | None = None,
    meeting_time: str = "",
    request_id: str = "",
) -> tuple[Any, dict[str, str]]:
    """解析本次归属（按学科/项目绑定）并生成各线注入文本。"""
    return prepare(
        Path(project_root),
        domain,
        user_id,
        transcript,
        list(line_names),
        project_id,
        subject,
    )


def _persist_memory(
    *,
    project_root,
    domain: str,
    user_id: str,
    project_id: str | None = None,
    request_id: str = "",
    subject: str | None = None,
    transcript: str = "",
    reports: dict[str, Any] | None = None,
    understanding: dict[str, Any] | None = None,
    meeting_time: str = "",
    bind: Any = None,
) -> Any:
    if bind is None:
        return None
    return persist(
        Path(project_root),
        domain,
        user_id,
        bind,
        reports or {},
        understanding,
        transcript,
        subject,
    )


HOOKS = DomainHooks(
    memory_lines=MEMORY_LINES,
    prepare_memory=_prepare_memory,
    persist_memory=_persist_memory,
)

__all__ = ["HOOKS"]
