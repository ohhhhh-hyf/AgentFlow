# -*- coding: utf-8 -*-
"""pytest 根配置：保证能从项目根导入业务模块。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
