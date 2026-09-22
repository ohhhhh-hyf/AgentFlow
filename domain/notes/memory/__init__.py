"""notes 域记忆（graph 线）：解析入口 + 图注入 + 跨场回写。

2026-09-22 从 ``tools/memory`` 下沉：这四个模块只服务 notes 域的 graph 线
（解析 ``resolve``、图合并 ``graph``、笔记合并 ``notes``、引擎门面 ``runtime``）。
留在 tools 的是共享底座 ``store``（落盘布局）/``embed``（向量索引）/``entities``
（实体抽取）——它们同时被 meeting 域的记忆复用。
"""
from __future__ import annotations

from .graph import inject_graph, merge_graph
from .notes import merge_notes
from .resolve import Bind, materialize, resolve, resolve_notes
from .runtime import MEMORY_LINES, persist, prepare

__all__ = [
    "Bind",
    "MEMORY_LINES",
    "inject_graph",
    "materialize",
    "merge_graph",
    "merge_notes",
    "persist",
    "prepare",
    "resolve",
    "resolve_notes",
]
