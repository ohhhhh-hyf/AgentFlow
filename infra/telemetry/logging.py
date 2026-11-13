"""独立无侵入日志系统 (零业务代码耦合，全量与诊断双文件轮转).

核心设计:
1. 独立生命周期: setup_logging 统一在 main.py 服务启动时配置，业务代码零感知;
2. 双落盘输出:
   - service.log: 全量 INFO 及以上运行日志，自动按 20MB 轮转保留 5 份;
   - diag.log: 诊断过滤日志，仅提取 WARNING+、HTTP、LLM 与任务完成等核心诊断行;
3. 纯英文结构化日志规范: 统一采用 [TAG:SUBTAG] key=value 格式，便于运维监控与日志收集检索。
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 默认日志路径（相对项目根 demo/ 目录）
DEMO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = DEMO_ROOT / "logs"

_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# 诊断日志放行的关键标签前缀
_DIAG_TAGS = (
    "[HTTP:",
    "[LLM:",
    "[MINUTES:",
    "[ACTIONS:",
    "[AGENDA:",
    "[VLM:",
    "[ARTIFACT:",
    "[CALENDAR:",
)


class _DiagFilter(logging.Filter):
    """诊断日志过滤器: 放行 WARNING+ 或含有核心诊断标签的记录."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        msg = str(record.getMessage())
        return any(tag in msg for tag in _DIAG_TAGS)


def _rotating_handler(
    file_path: Path,
    level: int,
    *,
    filt: logging.Filter | None = None,
) -> logging.Handler | None:
    """创建自滚动日志 Handler."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        max_bytes = int(float(os.getenv("LOG_MAX_MB", "20")) * 1024 * 1024)
        backups = int(os.getenv("LOG_BACKUPS", "5"))
        handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
            delay=True,
        )
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
        if filt is not None:
            handler.addFilter(filt)
        return handler
    except OSError as exc:
        logging.getLogger(__name__).warning("file logging disabled (%s): %s", file_path, exc)
        return None


def setup_logging(
    log_dir: Path | str | None = None,
    level: int | None = None,
) -> None:
    """初始化全局日志系统 (幂等，重复调用安全).

    Args:
        log_dir: 日志落盘目录 (默认 demo/logs/)
        level: 日志级别 (默认从环境变量 LOG_LEVEL 读取，或 INFO)
    """
    root = logging.getLogger()
    if getattr(root, "_demo_logging_configured", False):
        return

    lvl_env = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    lvl = level if level is not None else getattr(logging, lvl_env, logging.INFO)
    root.setLevel(lvl)

    # 1. 控制台 Handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(lvl)
    console.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
    root.addHandler(console)

    # 2. 全量日志文件 (service.log)
    base_dir = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    service_log = base_dir / "service.log"
    service_handler = _rotating_handler(service_log, lvl)
    if service_handler:
        root.addHandler(service_handler)

    # 3. 诊断日志文件 (diag.log)
    diag_log = base_dir / "diag.log"
    diag_handler = _rotating_handler(diag_log, lvl, filt=_DiagFilter())
    if diag_handler:
        root.addHandler(diag_handler)

    root._demo_logging_configured = True
    logging.getLogger("telemetry").info("[TELEMETRY:INIT] logging initialized, dir=%s", base_dir)


def unify_uvicorn_loggers() -> None:
    """将 Uvicorn 的独立 logger 统一重定向至 Root Logger."""
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
