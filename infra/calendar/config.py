"""Calendar 子包的本地配置。

LLM 连接信息统一由 ``infra.llm`` 从项目根目录 ``.env`` 读取；
本文件不再保存 API Key、BASE_URL 或模型名。
"""
from __future__ import annotations

DEFAULT_TIMEZONE = "Asia/Shanghai"
CALENDAR_LLM_LABEL = "calendar/deadline"

__all__ = ["CALENDAR_LLM_LABEL", "DEFAULT_TIMEZONE"]
