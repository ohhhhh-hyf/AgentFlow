"""接口任务线声明：**域 → 任务线** 的唯一来源。

新增 / 调整一条对外任务线时只改这里，下列位置全部从这份声明派生，避免多处清单不同步：
- 路由注册：``app/routes/_registry.py``
- 异步接口校验：``app/routes/tasks.py``（POST /api/v1/tasks 的 domain + task 白名单）
- 同步接口校验：``app/tasks.py`` 的 ``LINE_NAMES``（task 取值 → 代码线名）

字段含义：
- ``line``：代码线名，同时是 URL 段
- ``cn``：中文名（文档用）
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
    cn: str
    files: bool = False


DOMAINS: dict[str, tuple[TaskLine, ...]] = {
    "meeting": (
        TaskLine("minutes", "会议纪要", files=True),
        TaskLine("actions", "待办行动", files=True),
        TaskLine("risks", "风险分析", files=True),
        TaskLine("minutes_styles", "多样式纪要", files=True),
        TaskLine("minutes_trace", "溯源纪要", files=True),
        TaskLine("consensus_decision", "共识决策", files=True),
    ),
    "notes": (
        TaskLine("graph", "知识图谱", files=True),
        TaskLine("library", "资料入库"),  # 无落盘产物
        TaskLine("catalog", "知识目录"),  # file_name 指向知识目录 JSON，不在 output 目录
        TaskLine("checklist", "复习清单", files=True),
    ),
}

# 域中文名（文档与报错提示复用）
DOMAIN_NAMES: dict[str, str] = {"meeting": "会议", "notes": "笔记"}


def lines_for(domain: str) -> dict[str, str]:
    """该域可接受的 task 取值 → 代码线名。"""
    return {
        item.line: item.line
        for item in DOMAINS.get((domain or "").strip().lower(), ())
    }


def all_lines() -> dict[str, str]:
    """全部域的 task 取值 → 代码线名（供同步接口的任务名映射使用）。"""
    out: dict[str, str] = {}
    for domain in DOMAINS:
        out.update(lines_for(domain))
    return out


__all__ = [
    "DOMAIN_NAMES",
    "DOMAINS",
    "TaskLine",
    "all_lines",
    "lines_for",
]
