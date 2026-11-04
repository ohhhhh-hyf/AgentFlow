"""Pytest 全局配置与基础夹具。

项目根目录由 ``pyproject.toml`` 的 ``pythonpath`` 注入；这里保留 ``sys.path``
兜底，便于直接运行单个文件或在未读取 pytest 配置的场景下工作。
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# 兜底：确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 测试隔离：所有运行期产物/日志写到会话级临时目录，不污染仓库 data/、logs/。
# 必须在 app/config 等模块首次导入之前设置。
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="agentflow-tests-"))
os.environ["AGENTFLOW_DATA_DIR"] = str(_TEST_ROOT / "data")
os.environ["AGENTFLOW_LOG_DIR"] = str(_TEST_ROOT / "logs")
os.environ["AGENTFLOW_LOG_FILE"] = str(_TEST_ROOT / "logs" / "agentflow.log")
os.environ["AGENTFLOW_DIAG_LOG_FILE"] = str(_TEST_ROOT / "logs" / "diag.log")

# 测试不依赖真实模型：无外部 Key 时给占位值，仅供客户端构造（不会发起真实调用）。
os.environ.setdefault("DEEPSEEK_API_KEY", "test-dummy-key")
os.environ.setdefault("SILICONFLOW_API_KEY", "test-dummy-key")
atexit.register(shutil.rmtree, _TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例重新钉住隔离目录，避免个别用例改环境后外溢。"""
    monkeypatch.setenv("AGENTFLOW_DATA_DIR", str(_TEST_ROOT / "data"))
    monkeypatch.setenv("AGENTFLOW_LOG_DIR", str(_TEST_ROOT / "logs"))
    monkeypatch.setenv("AGENTFLOW_LOG_FILE", str(_TEST_ROOT / "logs" / "agentflow.log"))
    monkeypatch.setenv("AGENTFLOW_DIAG_LOG_FILE", str(_TEST_ROOT / "logs" / "diag.log"))
