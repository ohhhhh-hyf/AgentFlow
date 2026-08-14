"""项目记忆：稳定 id + 短名锁定 + 分级挂钩，供会议纪要对照与笔记图谱增量。

身份靠第一场理解里锁定的 ``project_key``（引号专名），不靠 LLM 起的长标题做匹配。
会议命中后按重叠实体回放历史摘录。笔记按 user_id + 学科分档，知识图谱增量合并。
解析入口只有 ``resolve()``，注入和回写共用。
"""
from __future__ import annotations

from .entities import extract_quoted, pick_project_key
from .graph import inject_graph, merge_graph
from .citations import (
    MemoryReference,
    apply_memory_citations,
    extract_memory_references,
)
from .meeting import inject_meeting, merge_meeting
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
    "MemoryReference",
    "append_history",
    "apply_memory_citations",
    "empty_record",
    "extract_entities",
    "extract_memory_references",
    "extract_quoted",
    "inject_graph",
    "inject_meeting",
    "list_records",
    "load_record",
    "merge_graph",
    "merge_meeting",
    "persist",
    "pick_project_key",
    "prepare",
    "record_dir",
    "resolve",
    "save_record",
    "shape_record",
]
