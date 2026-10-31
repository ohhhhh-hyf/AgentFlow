"""LLM 客户端构造。

连接方式、API Key、模型名全部由项目根目录 .env 与 infra.llm 决定。
"""
from __future__ import annotations

from infra.llm import LLMClient
from infra.llm.config import load_env

from .config import ENV_FILE


def default_client() -> LLMClient:
    """加载项目根 .env 后构造默认 LLMClient。"""
    load_env(ENV_FILE)
    return LLMClient()


__all__ = ["default_client"]
