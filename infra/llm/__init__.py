"""通用模型客户端接口（与领域无关，供任意业务复用）。"""

from .llmclient import LLMClient

__all__ = ["LLMClient"]
