"""兼容入口：新代码请优先从 ``client.llmclient`` 导入。"""

from .llmclient import LLMClient

__all__ = ["LLMClient"]
