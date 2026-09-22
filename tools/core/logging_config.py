"""日志配置：控制台 + **落盘文件**（含一份只装诊断行的精简日志）。

三处输出（可用环境变量调整）：

| 输出 | 默认位置 | 内容 |
|---|---|---|
| 控制台 | stdout | 全部（原行为不变） |
| 全量日志 | ``logs/agentflow.log`` | 全部 INFO 及以上（按大小轮转） |
| **诊断日志** | ``logs/diag.log`` | 只装排查降级用的行：LLM 调用/响应、审核结论、路由、降级、任何 WARNING+ |

诊断日志的存在是为了"跑完直接把文件给出去分析"：体积小、信息全，不用再从控制台里 grep。

环境变量（都可省）：

    AGENTFLOW_LOG_FILE=logs/agentflow.log      # 全量日志路径；设为空字符串可关闭文件输出
    AGENTFLOW_DIAG_LOG_FILE=logs/diag.log      # 诊断日志路径；设为空字符串可关闭
    AGENTFLOW_LOG_LEVEL=INFO                   # DEBUG/INFO/WARNING/ERROR（控制台与文件共用）
    AGENTFLOW_LOG_MAX_MB=20                    # 单文件上限（MB），超出轮转
    AGENTFLOW_LOG_BACKUPS=5                    # 轮转保留份数
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_FILE = "logs/agentflow.log"
DEFAULT_DIAG_FILE = "logs/diag.log"

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# 诊断日志的 logger 白名单：与"为什么降级"直接相关的模块
_DIAG_LOGGERS = (
    "tools.llm.llmclient",      # 请求/响应/finish_reason/HTTP 错误/空正文/解析失败
    "tools.core.domain_engine",  # 审核结论、路由去向、降级汇总
    "tools.core.runner",     # ⚠ 生成可能有误
    "agentflow",             # 流水线节点进度（start/done）
)


class _DiagFilter(logging.Filter):
    """只放行诊断相关记录：白名单 logger，或任何 WARNING 及以上。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - stdlib 接口
        if record.levelno >= logging.WARNING:
            return True
        return any(record.name == n or record.name.startswith(n + ".") for n in _DIAG_LOGGERS)


def _log_level() -> int:
    raw = (os.getenv("AGENTFLOW_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def _rotating_handler(path: Path, level: int, *, filt: logging.Filter | None = None) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = int(float(os.getenv("AGENTFLOW_LOG_MAX_MB") or 20) * 1024 * 1024)
        backups = int(os.getenv("AGENTFLOW_LOG_BACKUPS") or 5)
        handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True
        )
    except OSError as exc:  # 磁盘/权限问题不应影响服务启动
        logging.getLogger(__name__).warning("file logging disabled (%s): %s", path, exc)
        return None
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    if filt is not None:
        handler.addFilter(filt)
    return handler


def setup_logging(level: int | None = None) -> None:
    """配置标准库 logging：控制台 + 全量文件 + 诊断文件（幂等，重复调用只生效一次）。

    只在 root logger 没有 handler 时配置，避免 uvicorn reload 等方式重复添加。
    """
    root = logging.getLogger()
    if getattr(root, "_agentflow_configured", False) or root.handlers:
        return

    lvl = _log_level() if level is None else level
    root.setLevel(lvl)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(lvl)
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    log_file = (os.getenv("AGENTFLOW_LOG_FILE") or DEFAULT_LOG_FILE).strip()
    if log_file:
        handler = _rotating_handler(PROJECT_ROOT / log_file, lvl)
        if handler is not None:
            root.addHandler(handler)

    diag_file = (os.getenv("AGENTFLOW_DIAG_LOG_FILE") or DEFAULT_DIAG_FILE).strip()
    if diag_file:
        handler = _rotating_handler(PROJECT_ROOT / diag_file, lvl, filt=_DiagFilter())
        if handler is not None:
            root.addHandler(handler)

    root._agentflow_configured = True  # type: ignore[attr-defined]


def unify_uvicorn_loggers() -> None:
    """让 uvicorn 自己的日志走同一套 handler 与格式。

    uvicorn 启动时会给自己的 logger 加 handler（格式是 ``INFO:     ...``），不处理的话
    服务日志会出现两种格式混排；清掉它们的 handler 并允许向上冒泡即可统一到 root 格式。
    要在 uvicorn 完成日志配置之后调用（放在 ``app`` 的 lifespan 里最稳）。
    """
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
