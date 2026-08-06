"""通用 LLM 客户端接口（与领域无关，供任意业务复用）。"""

from .client import DeepSeekClient, LLMClient

__all__ = ["DeepSeekClient", "LLMClient"]
