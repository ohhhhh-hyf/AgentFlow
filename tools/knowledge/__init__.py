"""通用知识/文件底座（非某一业务域）：文件 → 文本、向量库封装、存储配置。

- ``document_processor``：PPT/PDF/docx/xlsx/txt → 文本（``tools/core/io`` 与 ``tools/ocr`` 共用）
- ``vector_store``：chromadb 集合封装（知识库与记忆向量索引共用）
- ``config``：存储目录/embedding 配置 + ``subject_to_pinyin``
- ``source_role``：入库资料角色 + 标题层级（``document_processor`` 与 notes 目录骨架共用）

notes 域的 RAG 门面（KnowledgeTool / cite / source_role / rag）已下沉到
``domain/notes/knowledge/``（2026-09-22）；本包只留被多个子系统复用的底座，不再有域语义。
"""
from __future__ import annotations

from .config import KnowledgeToolConfig, subject_to_pinyin
from .source_role import classify_source_role, heading_level
from .vector_store import VectorStore

__all__ = [
    "KnowledgeToolConfig",
    "VectorStore",
    "classify_source_role",
    "heading_level",
    "subject_to_pinyin",
]
