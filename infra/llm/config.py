"""LLM 配置解析模块 (零旧代码依赖).
支持 DeepSeek 官方 HTTP 与服务器 vLLM OpenAI 兼容接口自由切换。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# 优先加载 demo/.env，若无则加载项目根目录 .env
_DEMO_ENV = Path(__file__).resolve().parents[2] / ".env"
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"

if _DEMO_ENV.is_file():
    load_dotenv(_DEMO_ENV, override=False)
if _ROOT_ENV.is_file():
    load_dotenv(_ROOT_ENV, override=False)
load_dotenv(override=False)


@dataclass
class LLMSettings:
    """大模型核心配置参数."""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.2
    timeout: float = 60.0
    max_retries: int = 3
    backend: str = "http"


def resolve_llm_settings(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    backend: str | None = None,
) -> LLMSettings:
    """解析并生成最终 LLM 配置.

    模式支持:
    1. vLLM 后端 (LLM_BACKEND=vllm):
       - LLM_VLLM_BASE_URL (默认 http://127.0.0.1:8000/v1)
       - LLM_VLLM_API_KEY (默认 EMPTY)
       - LLM_VLLM_MODEL (默认 deepseek-v4-flash-0731)
       - LLM_VLLM_TEMPERATURE (默认 0.2)
    2. HTTP 后端 (LLM_BACKEND=http 或未配置，默认 DeepSeek 官方):
       - LLM_API_KEY / DEEPSEEK_API_KEY
       - LLM_BASE_URL / DEEPSEEK_BASE_URL (默认 https://api.deepseek.com)
       - LLM_MODEL / DEEPSEEK_MODEL (默认 deepseek-chat)
       - LLM_TEMPERATURE / DEEPSEEK_TEMPERATURE (默认 0.2)
    """
    be = (backend or os.getenv("LLM_BACKEND") or "http").strip().lower()

    if be in ("vllm", "local_vllm", "server_vllm"):
        key = (
            api_key
            or os.getenv("LLM_VLLM_API_KEY")
            or os.getenv("LLM_API_KEY")
            or "EMPTY"
        ).strip()
        url = (
            base_url
            or os.getenv("LLM_VLLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or "http://127.0.0.1:8000/v1"
        ).strip().rstrip("/")
        mdl = (
            model
            or os.getenv("LLM_VLLM_MODEL")
            or os.getenv("LLM_MODEL")
            or "deepseek-v4-flash-0731"
        ).strip()
        temp_env = os.getenv("LLM_VLLM_TEMPERATURE") or os.getenv("LLM_TEMPERATURE") or "0.2"
    else:
        key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or ""
        ).strip()
        url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        ).strip().rstrip("/")
        mdl = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-chat"
        ).strip()
        temp_env = os.getenv("DEEPSEEK_TEMPERATURE") or os.getenv("LLM_TEMPERATURE") or "0.2"

    # 规范化 URL: 剥离可能多余的 /chat/completions 尾缀
    if url.endswith("/chat/completions"):
        url = url[:-len("/chat/completions")].rstrip("/")

    temp_val = temperature if temperature is not None else float(temp_env)
    to_val = timeout if timeout is not None else float(os.getenv("LLM_TIMEOUT", "60.0"))
    retries_val = max_retries if max_retries is not None else int(os.getenv("LLM_MAX_RETRIES", "3"))

    return LLMSettings(
        api_key=key,
        base_url=url,
        model=mdl,
        temperature=temp_val,
        timeout=to_val,
        max_retries=retries_val,
        backend=be,
    )
