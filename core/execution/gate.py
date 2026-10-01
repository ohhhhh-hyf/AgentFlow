"""core.execution.gate —— 上游硬对齐、表行截断、验收硬门禁。"""
from __future__ import annotations

import core.execution.hard_execution as _he

for _name in dir(_he):
    globals()[_name] = getattr(_he, _name)
