"""LLM 配置模块。

默认适配 DeepSeek 官方 HTTP API，也支持服务器上的 WebSocket OpenAI 兼容接口。
所有配置通过项目根目录的 .env 文件提供，HTTP 最小配置只需一行：

    DEEPSEEK_API_KEY=sk-你的Key

可选覆盖项（均有内置默认值，不配置也能运行）：

    LLM_BACKEND=http
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    DEEPSEEK_MODEL=deepseek-chat
    DEEPSEEK_TEMPERATURE=0

服务器 WebSocket 示例：

    LLM_BACKEND=websocket
    LLM_WS_URL=ws://10.32.101.24:18087/llm/websocket/openai/chat/completions
    LLM_WS_API_KEY=AccessService
    LLM_WS_SENDER=h00984725
    LLM_WS_USER=dudududux124erf8709e2
    LLM_WS_MODEL=deepseek-ai/DeepSeek-V4-Flash-0731/Cluster-1
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# DeepSeek 官方默认值
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 128
DEFAULT_MAX_TOKENS = 50000

# .env 中可用的环境变量名
ENV_BACKEND = "LLM_BACKEND"
ENV_API_KEY = "DEEPSEEK_API_KEY"
ENV_BASE_URL = "DEEPSEEK_BASE_URL"
ENV_MODEL = "DEEPSEEK_MODEL"
ENV_TEMPERATURE = "DEEPSEEK_TEMPERATURE"
ENV_WS_URL = "LLM_WS_URL"
ENV_WS_API_KEY = "LLM_WS_API_KEY"
ENV_WS_SENDER = "LLM_WS_SENDER"
ENV_WS_USER = "LLM_WS_USER"
ENV_WS_MODEL = "LLM_WS_MODEL"
ENV_WS_TEMPERATURE = "LLM_WS_TEMPERATURE"
ENV_WS_TOP_P = "LLM_WS_TOP_P"
ENV_WS_TOP_K = "LLM_WS_TOP_K"
ENV_WS_MAX_TOKENS = "LLM_WS_MAX_TOKENS"
ENV_WS_STOP = "LLM_WS_STOP"
ENV_WS_ENABLE_THINKING = "LLM_WS_ENABLE_THINKING"

# 网络参数（HTTP / WebSocket 共用）
ENV_TIMEOUT = "LLM_TIMEOUT"
ENV_MAX_RETRIES = "LLM_MAX_RETRIES"

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_RETRIES = 2

# 占位 Key，视为未配置
_PLACEHOLDERS = {
    "your_api_key_here",
    "sk-your-key",
    "sk-你的Key",
    "sk-你的key",
}


@dataclass(frozen=True)
class LLMSettings:
    backend: str
    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float
    ws_url: str = ""
    ws_sender: str = ""
    ws_user: str = ""
    top_p: float = DEFAULT_TOP_P
    top_k: int = DEFAULT_TOP_K
    max_tokens: int = DEFAULT_MAX_TOKENS
    stop: tuple[str, ...] = ()
    enable_thinking: bool = False
    # 网络参数（HTTP / WebSocket 共用；LLM_TIMEOUT / LLM_MAX_RETRIES 可覆盖）
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES


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
    if value and value not in _PLACEHOLDERS:
        return value
    return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字，当前为：{raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前为：{raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str) -> tuple[str, ...]:
    raw = _env(name)
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def resolve_llm_settings(
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
) -> LLMSettings:
    """解析 LLM 连接配置。

    优先级：显式参数 > .env 环境变量 > 内置默认值。
    HTTP 最低配置要求：.env 中设置 DEEPSEEK_API_KEY，其余均可省略。
    WebSocket 最低配置要求：LLM_WS_URL / LLM_WS_API_KEY / LLM_WS_MODEL。
    """
    resolved_timeout = timeout if timeout is not None else _env_float(
        ENV_TIMEOUT, DEFAULT_TIMEOUT
    )
    resolved_max_retries = max_retries if max_retries is not None else _env_int(
        ENV_MAX_RETRIES, DEFAULT_MAX_RETRIES
    )
    backend = _env(ENV_BACKEND, "http").lower()
    if backend in {"ws", "websocket"}:
        resolved_key = api_key or _env(ENV_WS_API_KEY)
        resolved_url = (base_url or _env(ENV_WS_URL)).rstrip("/")
        resolved_model = model or _env(ENV_WS_MODEL)
        if not resolved_url:
            raise ValueError(f"未找到 WebSocket 地址，请配置：{ENV_WS_URL}=ws://...")
        if not resolved_key:
            raise ValueError(f"未找到 WebSocket API Key，请配置：{ENV_WS_API_KEY}=...")
        if not resolved_model:
            raise ValueError(f"未找到 WebSocket 模型名，请配置：{ENV_WS_MODEL}=...")
        return LLMSettings(
            backend="websocket",
            provider=provider or "websocket",
            api_key=resolved_key,
            base_url="",
            model=resolved_model,
            temperature=(
                float(temperature)
                if temperature is not None
                else _env_float(ENV_WS_TEMPERATURE, DEFAULT_TEMPERATURE)
            ),
            ws_url=resolved_url,
            ws_sender=_env(ENV_WS_SENDER),
            ws_user=_env(ENV_WS_USER),
            top_p=_env_float(ENV_WS_TOP_P, DEFAULT_TOP_P),
            top_k=_env_int(ENV_WS_TOP_K, DEFAULT_TOP_K),
            max_tokens=_env_int(ENV_WS_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            stop=_env_csv(ENV_WS_STOP),
            enable_thinking=_env_bool(ENV_WS_ENABLE_THINKING, False),
            timeout=resolved_timeout,
            max_retries=resolved_max_retries,
        )

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
        backend="http",
        provider="deepseek",
        api_key=resolved_key,
        base_url=resolved_base,
        model=resolved_model,
        temperature=resolved_temperature,
        timeout=resolved_timeout,
        max_retries=resolved_max_retries,
    )
