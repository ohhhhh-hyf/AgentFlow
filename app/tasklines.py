"""接口任务线声明：**域 → 任务线** 的唯一来源。

新增 / 调整一条对外任务线时只改这里，下列位置全部从这份声明派生，避免多处清单不同步：
- 路由注册：``app/routes/_registry.py``（预览端点）
- 统一入口校验：``app/routes/agent.py``（同步 / 流式）与 ``app/routes/tasks.py``（异步）
  —— 两处都调本模块的 ``resolve_line``
- 同步接口校验：``app/tasks.py`` 的 ``LINE_NAMES``（task 取值 → 代码线名）

字段含义：
- ``line``：代码线名，同时是 ``task`` 取值（**中文名不在这里**：运行时用的中文名以各域
  ``domain_config.LINE_CN_NAMES`` 为准，避免同一份清单维护两遍）
- ``files``：是否注册产物端点。无落盘产物（library）或产物不在 output 目录
  （catalog，file_name 指向知识目录 JSON）的任务线不注册。

对外端点（2026-09 收敛：前三类统一到 ``/api/agent/v1``，域与线名改为请求体字段）::

    POST /api/agent/v1                                同步（请求体带 domain / task）
    POST /api/agent/v1/stream                         流式（NDJSON 事件流）
    GET  /api/agent/v1/file/{request_id}/{file_name}  下载产物
    GET  /api/v1/{domain}/{line}/preview?request_id=&user_id=
                                                      预览（仅 ``files=True``；唯一
                                                      仍需路径里带域与线名的端点，
                                                      因为它靠 ``{line}.html`` 命名约定定位产物）

已移除的端点形态（2026-09 精简，勿再加回）：
- 路径带 ``{domain}/{task}`` 的同步 / 流式 / 下载三类端点（``POST /api/v1/{domain}/{line}``、
  ``POST /api/v1/{domain}/{line}/stream``、``GET /api/v1/{domain}/{line}/file/{request_id}/{file_name}``）：
  能力被 ``/api/agent/v1`` 三条统一端点覆盖，域与线名改由请求体传；
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


class TaskLineNotFound(Exception):
    """domain + task 组合不合法。``status`` 为 HTTP 状态码（400 域不存在 / 404 线不存在）。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def resolve_line(domain: str, task: str) -> tuple[str, str]:
    """``domain`` + ``task`` → (规范域, 线名)；非法组合抛 ``TaskLineNotFound``。

    同步（``app/routes/agent.py``）、流式与异步（``app/routes/tasks.py``）三个统一入口
    共用这一份白名单；调用方只把 ``status`` / ``message`` 转成自己的错误类型
    （``app.tasks.ApiError`` 或 ``AsyncApiError``），错误文案与状态码全局一致。

    按域校验而非全局校验：``notes`` + ``minutes`` 这类「别的域有、本域没有」的组合
    返回 404 并说明是域不支持，不再落到更深的域装配里报错。
    """
    domain = (domain or "").strip().lower()
    task = (task or "").strip()
    if domain not in DOMAINS:
        raise TaskLineNotFound(400, f"domain 仅支持 {' / '.join(DOMAIN_NAMES)}")
    if task not in lines_for(domain):
        # 与其他域的同名任务线区分开：域内不存在 vs 全局不存在
        if task in all_lines():
            raise TaskLineNotFound(404, f"{domain} 不支持任务线：{task}")
        raise TaskLineNotFound(404, f"任务线不存在：{task}")
    return domain, task  # 线名即 task 取值（见本模块 lines_for）


__all__ = [
    "DOMAIN_NAMES",
    "DOMAINS",
    "TaskLine",
    "TaskLineNotFound",
    "all_lines",
    "lines_for",
    "resolve_line",
]
