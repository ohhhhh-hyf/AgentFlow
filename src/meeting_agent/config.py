from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# OpenAI 兼容 Chat Completions 的厂商预设
# temperature：部分 Kimi 模型只允许 1
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": "0",
        "api_key_envs": "LLM_API_KEY,DEEPSEEK_API_KEY",
        "base_url_envs": "LLM_BASE_URL,DEEPSEEK_BASE_URL",
        "model_envs": "LLM_MODEL,DEEPSEEK_MODEL",
        "temperature_envs": "LLM_TEMPERATURE,DEEPSEEK_TEMPERATURE",
    },
    "kimi": {
        # Moonshot / Kimi OpenAI 兼容接口
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-32k",
        "temperature": "1",
        "api_key_envs": "LLM_API_KEY,KIMI_API_KEY,MOONSHOT_API_KEY",
        "base_url_envs": "LLM_BASE_URL,KIMI_BASE_URL,MOONSHOT_BASE_URL",
        "model_envs": "LLM_MODEL,KIMI_MODEL,MOONSHOT_MODEL",
        "temperature_envs": "LLM_TEMPERATURE,KIMI_TEMPERATURE,MOONSHOT_TEMPERATURE",
    },
    "openai_compatible": {
        # 通用：vLLM / OneAPI / 其他 OpenAI 兼容服务，必须显式配置
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "default",
        "temperature": "0",
        "api_key_envs": "LLM_API_KEY,OPENAI_API_KEY",
        "base_url_envs": "LLM_BASE_URL,OPENAI_BASE_URL",
        "model_envs": "LLM_MODEL,OPENAI_MODEL",
        "temperature_envs": "LLM_TEMPERATURE,OPENAI_TEMPERATURE",
    },
}

# 别名，方便写 moonshot / moonshot-v1 等
PROVIDER_ALIASES: dict[str, str] = {
    "deepseek": "deepseek",
    "kimi": "kimi",
    "moonshot": "kimi",
    "moonshot-ai": "kimi",
    "openai": "openai_compatible",
    "openai_compatible": "openai_compatible",
    "vllm": "openai_compatible",
    "local": "openai_compatible",
}


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float


def load_env(path: Path) -> None:
    """使用标准库加载简单的 KEY=VALUE 环境配置。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _first_env(names: str) -> str | None:
    for name in names.split(","):
        value = os.getenv(name.strip())
        if value and value.strip() and value.strip() != "your_api_key_here":
            return value.strip()
    return None


def resolve_provider_name(provider: str | None = None) -> str:
    raw = (provider or os.getenv("LLM_PROVIDER") or "deepseek").strip().lower()
    if raw not in PROVIDER_ALIASES:
        supported = ", ".join(sorted(PROVIDER_PRESETS))
        raise ValueError(
            f"不支持的 LLM_PROVIDER={raw!r}，可选：{supported} "
            f"（也可用别名 kimi/moonshot、openai/vllm/local）"
        )
    return PROVIDER_ALIASES[raw]


def _resolve_temperature(
    preset: dict[str, str],
    temperature: float | None,
) -> float:
    if temperature is not None:
        return float(temperature)
    raw = _first_env(preset.get("temperature_envs", "LLM_TEMPERATURE"))
    if raw is not None:
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"temperature 必须是数字，当前为：{raw!r}") from exc
    return float(preset.get("temperature", "0"))


def resolve_llm_settings(
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> LLMSettings:
    """按厂商预设 + 环境变量解析 LLM 连接配置。"""
    name = resolve_provider_name(provider)
    preset = PROVIDER_PRESETS[name]

    resolved_key = api_key or _first_env(preset["api_key_envs"])
    if not resolved_key:
        envs = preset["api_key_envs"].replace(",", " / ")
        raise ValueError(
            f"未找到 {name} 的 API Key，请在 .env 中配置其一：{envs}"
        )

    resolved_base = (
        base_url
        or _first_env(preset["base_url_envs"])
        or preset["base_url"]
    ).rstrip("/")
    resolved_model = model or _first_env(preset["model_envs"]) or preset["model"]
    resolved_temperature = _resolve_temperature(preset, temperature)

    return LLMSettings(
        provider=name,
        api_key=resolved_key,
        base_url=resolved_base,
        model=resolved_model,
        temperature=resolved_temperature,
    )
