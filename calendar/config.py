"""calendar 独立包的配置。

只需要填这里的 DEEPSEEK_API_KEY，或者用环境变量覆盖。
不要把真实 Key 提交到仓库。
"""
from __future__ import annotations

import os

# ── 在这里填写你的 DeepSeek API Key ───────────────────────────
DEEPSEEK_API_KEY = "sk-3286bf3055ce4c52a59750f31f524c38"

# 默认使用 DeepSeek 官方 OpenAI 兼容接口。
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_TEMPERATURE = 0.0
DEEPSEEK_TIMEOUT_SECONDS = 60.0

DEFAULT_TIMEZONE = "Asia/Shanghai"


def get_api_key() -> str:
    """优先读取环境变量，其次读取本文件里的常量。"""
    return (os.getenv("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY or "").strip()


def get_base_url() -> str:
    return (os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL).strip().rstrip("/")


def get_model() -> str:
    return (os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_MODEL).strip()


def get_temperature() -> float:
    raw = os.getenv("DEEPSEEK_TEMPERATURE")
    if raw is None or not raw.strip():
        return DEEPSEEK_TEMPERATURE
    try:
        return float(raw)
    except ValueError:
        return DEEPSEEK_TEMPERATURE


def is_placeholder_api_key(value: str | None = None) -> bool:
    key = (value if value is not None else get_api_key()).strip()
    return (
        not key
        or key == "sk-REPLACE_ME"
        or "REPLACE_ME" in key
        or "请填写" in key
        or "你的Key" in key
    )


__all__ = [
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_TEMPERATURE",
    "DEEPSEEK_TIMEOUT_SECONDS",
    "DEFAULT_TIMEZONE",
    "get_api_key",
    "get_base_url",
    "get_model",
    "get_temperature",
    "is_placeholder_api_key",
]
