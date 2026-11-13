"""独立日志系统与流量中间件单元测试：验证双文件轮转、诊断过滤与外挂请求生命周期记录。"""
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from infra.telemetry.logging import _DiagFilter, _rotating_handler
from infra.telemetry.middleware import LoggingMiddleware


def test_diag_filter_logic():
    """测试诊断日志过滤器放行规则."""
    filt = _DiagFilter()

    # 1. WARNING 级别无条件放行
    rec_warn = logging.LogRecord("test", logging.WARNING, "path", 1, "warning message", (), None)
    assert filt.filter(rec_warn) is True

    # 2. 核心诊断标签放行
    rec_llm = logging.LogRecord("test", logging.INFO, "path", 1, "[LLM:STREAM:FIRST_TOKEN] ttft=0.5s", (), None)
    assert filt.filter(rec_llm) is True

    rec_http = logging.LogRecord("test", logging.INFO, "path", 1, "[HTTP:RES] status=200 dur=1.2s", (), None)
    assert filt.filter(rec_http) is True

    rec_actions = logging.LogRecord("test", logging.INFO, "path", 1, "[ACTIONS:DONE] count=3", (), None)
    assert filt.filter(rec_actions) is True

    # 3. 普通业务 INFO 拦截不放行进入 diag.log
    rec_normal = logging.LogRecord("test", logging.INFO, "path", 1, "普通业务正常处理中", (), None)
    assert filt.filter(rec_normal) is False


def test_rotating_handler_creation(tmp_path: Path):
    """测试滚动日志文件 Handler 创建与写入."""
    log_file = tmp_path / "test_service.log"
    handler = _rotating_handler(log_file, logging.INFO)
    assert handler is not None

    logger = logging.getLogger("test_rotating")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("hello telemetry")
    handler.flush()
    handler.close()

    assert log_file.is_file()
    assert "hello telemetry" in log_file.read_text(encoding="utf-8")


def test_logging_middleware():
    """测试外挂式 LoggingMiddleware 捕获请求与响应."""
    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/api/test-echo")
    def echo_endpoint():
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.get("/api/test-echo", headers={"X-User-Id": "u123", "X-Request-Id": "req999"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-Id") == "req999"
