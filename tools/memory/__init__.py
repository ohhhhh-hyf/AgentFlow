"""项目记忆：稳定 id + 短名锁定 + 分级挂钩，供笔记知识图谱增量。

会议域记忆已迁移到 ``tools.meeting_memory``（registry + meetings + state +
ChromaDB），本模块只保留 notes（graph / catalog）共享能力：
解析入口只有 ``resolve()``，注入和回写共用。
"""
from __future__ import annotations

from .entities import extract_quoted, pick_project_key
from .graph import inject_graph, merge_graph
from .resolve import Bind, extract_entities, resolve
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
    "extract_entities",
    "extract_quoted",
    "inject_graph",
    "list_records",
    "load_record",
    "merge_graph",
    "persist",
    "pick_project_key",
    "prepare",
    "record_dir",
    "resolve",
    "save_record",
    "shape_record",
]
