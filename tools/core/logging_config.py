from __future__ import annotations

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """配置标准库 logging（统一格式：时间戳 + 级别 + 来源模块 + 消息）。

    只在 root logger 没有 handler 时配置，避免重复添加。
    """
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # 带时间戳、级别与来源模块，便于区分正常输出与降级/错误（不改变业务输出格式）
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )

    root.setLevel(level)
    root.addHandler(handler)


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
