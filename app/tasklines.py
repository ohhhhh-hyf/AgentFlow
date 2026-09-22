"""接口任务线声明：**域 → 任务线** 的唯一来源。

新增 / 调整一条对外任务线时只改这里，下列位置全部从这份声明派生，避免多处清单不同步：
- 路由注册：``app/routes/_registry.py``
- 异步接口校验：``app/routes/tasks.py``（POST /api/v1/tasks 的 domain + task 白名单）
- 同步接口校验：``app/tasks.py`` 的 ``LINE_NAMES``（task 取值 → 代码线名）

字段含义：
- ``line``：代码线名，同时是 URL 段（**中文名不在这里**：运行时用的中文名以各域
  ``domain_config.LINE_CN_NAMES`` 为准，避免同一份清单维护两遍）
- ``files``：是否注册产物端点。无落盘产物（library）或产物不在 output 目录
  （catalog，file_name 指向知识目录 JSON）的任务线不注册。

每条任务线的端点（后两条仅 ``files=True``）::

    POST /api/v1/{domain}/{line}
    POST /api/v1/{domain}/{line}/stream
    GET  /api/v1/{domain}/{line}/file/{request_id}/{file_name}
    GET  /api/v1/{domain}/{line}/preview?request_id=&user_id=

已移除的端点形态（2026-09 精简，勿再加回）：
- 便捷下载 ``GET /file?request_id=&user_id=``（文件名自动回退）：能力被
  ``GET /file/{request_id}/{file_name}`` 覆盖，后者无回退歧义、且能指定取 ``.md``；
- 同义 URL ``/consensus``、``/decision``：规范名 ``consensus_decision`` 已足够。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskLine:
    """一条对外暴露的任务线。"""

    line: str
    files: bool = False


DOMAINS: dict[str, tuple[TaskLine, ...]] = {
    "meeting": (
        TaskLine("minutes", files=True),
        TaskLine("actions", files=True),
        TaskLine("risks", files=True),
        TaskLine("minutes_styles", files=True),
        TaskLine("minutes_trace", files=True),
        TaskLine("consensus_decision", files=True),
    ),
    "notes": (
        TaskLine("graph", files=True),
        TaskLine("library"),  # 无落盘产物
        TaskLine("catalog"),  # file_name 指向知识目录 JSON，不在 output 目录
        TaskLine("checklist", files=True),
    ),
}

# 域中文名（文档与报错提示复用）
DOMAIN_NAMES: dict[str, str] = {"meeting": "会议", "notes": "笔记"}


def lines_for(domain: str) -> frozenset[str]:
    """该域对外暴露的线名集合（调用方只需判存在，线名本身就是"task 取值"）。

    历史上这里返回"task 取值 → 代码线名"的 dict，但两者恒相等 ⇒ 换成集合，调用方直接
    用 `task if task in lines_for(domain) else None`。
    """
    return frozenset(
        item.line for item in DOMAINS.get((domain or "").strip().lower(), ())
    )


def all_lines() -> frozenset[str]:
    """全部域对外暴露的线名集合（供同步接口的任务名校验使用）。"""
    return frozenset().union(*(lines_for(domain) for domain in DOMAINS))


__all__ = [
    "DOMAIN_NAMES",
    "DOMAINS",
    "TaskLine",
    "all_lines",
    "lines_for",
]
