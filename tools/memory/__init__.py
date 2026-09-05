"""项目记忆：notes（graph / catalog）的共享记忆能力。

会议域记忆在 ``tools.meeting_memory``（registry + meetings + states +
ChromaDB 语义兜底）。本模块只服务 notes 域：解析入口 ``resolve()``，
注入（inject_graph）与回写（persist）共用同一份 Bind。
"""
from __future__ import annotations

from .entities import extract_quoted
from .graph import inject_graph, merge_graph
from .resolve import Bind, resolve
from .runtime import persist, prepare
from .store import (
    append_history,
    empty_record,
    list_records,
    load_record,
    record_dir,
    save_record,
    shape_record,
)

__all__ = [
    "Bind",
    "append_history",
    "empty_record",
    "extract_quoted",
    "inject_graph",
    "list_records",
    "load_record",
    "merge_graph",
    "persist",
    "prepare",
    "record_dir",
    "resolve",
    "save_record",
    "shape_record",
]
