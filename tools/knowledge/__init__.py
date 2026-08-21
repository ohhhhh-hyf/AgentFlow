"""知识库子系统：文档入库、向量检索、带出处问答。

供后续 task 调用，不绑死任何一条任务线。

    from tools.knowledge import KnowledgeTool, get_knowledge

    kb = get_knowledge()                          # 读项目根 .env
    kb.add_file("课件.pptx", collection="math")   # PPT/PDF/docx/xlsx/txt
    hits = kb.locate("学习率太大", collection="math")
    ans = kb.ask("为什么学习率太大会发散？", collection="math")
    ans.answer / ans.sources
"""

from .cite import cite_text, format_cite_line, library_has_docs, open_knowledge
from .config import KnowledgeToolConfig
from .tool import (
    AskResult,
    KnowledgeTool,
    SearchResult,
    get_knowledge,
)

__all__ = [
    "AskResult",
    "KnowledgeTool",
    "KnowledgeToolConfig",
    "SearchResult",
    "cite_text",
    "format_cite_line",
    "get_knowledge",
    "library_has_docs",
    "open_knowledge",
]
