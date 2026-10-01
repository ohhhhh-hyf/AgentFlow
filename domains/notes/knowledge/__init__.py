"""notes 域知识库门面（RAG）：文档入库后的检索、带出处问答与应用侧引用。

2026-09-22 从 ``tools/knowledge`` 下沉：这三个模块（tool / rag / cite）的消费者**全部**在 notes 域
（catalog / checklist / library / quiz / review），属域实现而非通用基础设施。
留在 tools 的是通用底座：``document_processor``（文件 → 文本）、``vector_store``
（chroma 封装）、``config``（存储与 embedding 配置）、``source_role``（资料角色/标题层级）——它们被 ``tools/core/io``、
``tools/ocr``、``tools/memory/embed`` 复用，不该跟着域走。
"""
from __future__ import annotations

from .cite import cite_text, library_has_docs, open_knowledge, parse_scope
from .tool import AskResult, KnowledgeTool, SearchResult, get_knowledge

__all__ = [
    "AskResult",
    "KnowledgeTool",
    "SearchResult",
    "cite_text",
    "get_knowledge",
    "library_has_docs",
    "open_knowledge",
    "parse_scope",
]
