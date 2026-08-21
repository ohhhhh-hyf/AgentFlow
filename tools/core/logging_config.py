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

    # 带时间戳与级别前缀，便于区分正常输出与降级/错误（不改变业务输出格式）
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    root.setLevel(level)
    root.addHandler(handler)
