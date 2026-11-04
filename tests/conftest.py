"""Pytest 全局配置与基础夹具。

项目根目录由 ``pyproject.toml`` 的 ``pythonpath`` 注入；这里保留 ``sys.path``
兜底，便于直接运行单个文件或在未读取 pytest 配置的场景下工作。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 兜底：确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
