"""DeepSeek 配置模块。

本模块只适配 DeepSeek 官方 API。所有配置通过项目根目录的 .env 文件提供，
最小配置只需一行：

    DEEPSEEK_API_KEY=sk-你的Key

可选覆盖项（均有内置默认值，不配置也能运行）：

    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_MODEL=deepseek-chat
    DEEPSEEK_TEMPERATURE=0
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# DeepSeek 官方默认值
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.0

# .env 中可用的环境变量名
ENV_API_KEY = "DEEPSEEK_API_KEY"
ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"
ENV_TEMPERATURE = "DEEPSEEK_TEMPERATURE"

# 占位 Key，视为未配置
_PLACEHOLDER = "your_api_key_here"


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float


def load_env(path: Path) -> None:
    """使用标准库加载简单的 KEY=VALUE 环境配置（不覆盖已存在的环境变量）。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    if value and value != _PLACEHOLDER:
        return value
    return default


def resolve_llm_settings(
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> LLMSettings:
    """解析 DeepSeek 连接配置。

    优先级：显式参数 > .env 环境变量 > 内置默认值。
    最低配置要求：.env 中设置 DEEPSEEK_API_KEY，其余均可省略。

    provider 参数仅保留以兼容旧调用方，本模块固定使用 deepseek。
    """
    resolved_key = api_key or _env(ENV_API_KEY)
    if not resolved_key:
        raise ValueError(
            f"未找到 DeepSeek API Key，请在项目根目录的 .env 中配置："
            f"{ENV_API_KEY}=sk-你的Key"
        )

    resolved_base = (base_url or _env(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")
    resolved_model = model or _env(ENV_MODEL) or DEFAULT_MODEL

    if temperature is not None:
        resolved_temperature = float(temperature)
    else:
        raw = _env(ENV_TEMPERATURE)
        if raw:
            try:
                resolved_temperature = float(raw)
            except ValueError as exc:
                raise ValueError(f"temperature 必须是数字，当前为：{raw!r}") from exc
        else:
            resolved_temperature = DEFAULT_TEMPERATURE

    return LLMSettings(
        provider="deepseek",
        api_key=resolved_key,
        base_url=resolved_base,
        model=resolved_model,
        temperature=resolved_temperature,
    )
