"""记忆/向量的**共享底座**（跨域）：落盘布局、实体抽取、记忆向量索引。

- ``store``：``data/{user_id}/memory/{线名}/`` 落盘布局（json 为事实权威，chroma 可重建）
- ``entities``：从原文抽挂钩实体（纯形态/频次，不维护业务词表）
- ``embed``：记忆向量索引（复用知识库向量库；语义兜底检索用）

域侧实现（各自的记忆语义）已按域下沉（2026-09-22）：
``domain/notes/memory/``（graph 线记忆）、``domain/meeting/memory/``（会议跨场记忆）。
"""
from __future__ import annotations

from .entities import extract_entities, extract_quoted, is_generic_entity, speaker_names
from .store import (
    append_history,
    empty_record,
    history_path,
    list_records,
    load_record,
    record_dir,
    record_path,
    save_record,
    shape_record,
    user_dir,
)

__all__ = [
    "append_history",
    "empty_record",
    "extract_entities",
    "extract_quoted",
    "history_path",
    "is_generic_entity",
    "list_records",
    "load_record",
    "record_dir",
    "record_path",
    "save_record",
    "shape_record",
    "speaker_names",
    "user_dir",
]
