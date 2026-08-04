from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """配置标准库 logging，替代 print 输出。

    只在 root logger 没有 handler 时配置，避免重复添加。
    """
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # 简洁格式：只显示消息本身（进度 / 结果由 presenter 控制格式）
    handler.setFormatter(logging.Formatter("%(message)s"))

    root.setLevel(level)
    root.addHandler(handler)
