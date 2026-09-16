"""给调试台/终端的进度日志（INFO），标明当前 Agent。"""
from __future__ import annotations

import logging

logger = logging.getLogger("agentflow")


def progress(msg: str, *args) -> None:
    logger.info(msg, *args)
