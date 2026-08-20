"""KnowledgeTool —— Agent 可直接调用的统一入口。

用法:
    from knowledge_tool import KnowledgeTool

    kb = KnowledgeTool(embedding_api_key="sk-...", llm_api_key="sk-...")
    kb.add_file("考勤制度.pdf", collection="hr")
    result = kb.ask("病假怎么申请?", collection="hr")
    result.answer / result.sources
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBEDDING_BASE_URL,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_BASE_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PERSIST_DIR,
    DEFAULT_TOP_K,
    KnowledgeToolConfig,
)
from .document_processor import process_file
from .rag import RagService
from .vector_store import VectorStore


# ============================================================
# 结果类型
# ============================================================
@dataclass
class SearchResult:
    """检索结果片段"""
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


@dataclass
class AskResult:
    """问答结果"""
    answer: str
    sources: List[Dict] = field(default_factory=list)


# ============================================================
# KnowledgeTool
# ============================================================
class KnowledgeTool:
    """本地 AI 知识库工具(有状态, 复用客户端)。

    fake=True 时使用确定性伪向量 + 假 LLM, 用于无 API Key 的离线验证。
    """

    def __init__(self,
                 embedding_api_key: str = "",
                 llm_api_key: str = "",
                 embedding_base_url: Optional[str] = None,
                 embedding_model: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_model: Optional[str] = None,
                 persist_dir: Optional[str] = None,
                 chunk_size: Optional[int] = None,
                 chunk_overlap: Optional[int] = None,
                 top_k: Optional[int] = None,
                 max_tokens: Optional[int] = None,
                 fake: bool = False,
                 user_id: str = ""):
        """参数缺省时依次回退: .env → 环境变量 → 代码默认值(config.py)。
        fake=True 时不校验 API Key, 用伪向量+假 LLM 离线验证。

        ``user_id`` 非空且未显式传 ``persist_dir`` 时，按用户顶层物理隔离
        （``data/{user_id}/knowledge/chromadb``）。
        """
        if persist_dir is None and user_id:
            from tools.knowledge.config import persist_dir_for_user

            persist_dir = persist_dir_for_user(user_id)
        cfg = KnowledgeToolConfig(
            embedding_api_key=embedding_api_key,
            llm_api_key=llm_api_key,
            embedding_base_url=embedding_base_url or DEFAULT_EMBEDDING_BASE_URL,
            embedding_model=embedding_model or DEFAULT_EMBEDDING_MODEL,
            llm_base_url=llm_base_url or DEFAULT_LLM_BASE_URL,
            llm_model=llm_model or DEFAULT_LLM_MODEL,
            chunk_size=chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE,
            chunk_overlap=chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP,
            top_k=top_k if top_k is not None else DEFAULT_TOP_K,
            max_tokens=max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS,
            persist_dir=persist_dir or DEFAULT_PERSIST_DIR,
        )
        self.cfg = cfg
        self.fake = fake
        if not fake:
            cfg.ensure_keys()          # 真实模式: 提前校验 key, 报错更友好
        self.store = VectorStore(cfg, fake=fake)
        self.rag = RagService(cfg, self.store, fake=fake)

    # ---------------- 知识库管理 ----------------
    def list_collections(self) -> List[Dict]:
        return self.store.list_collections()

    def create_collection(self, name: str) -> str:
        return self.store.create_collection(name)

    def delete_collection(self, name: str) -> None:
        self.store.delete_collection(name)

    def list_files(
        self,
        collection: str = "default",
        user_id: str = "",
        subject: str = "",
    ) -> List[str]:
        coll, where = _scope(collection, user_id, subject)
        return self.store.list_files(coll, where=where)

    def delete_file(
        self,
        collection: str,
        filename: str,
        user_id: str = "",
        subject: str = "",
    ) -> int:
        coll, where = _scope(collection, user_id, subject)
        return self.store.delete_file(coll, filename, where=where)

    # ---------------- 入库 ----------------
    def add_file(
        self,
        path: str,
        collection: str = "default",
        user_id: str = "",
        subject: str = "",
    ) -> dict:
        """解析文档 → 增量同步入库(处理"更新/替换同名文件"场景)。

        返回 {"added": 新增块数, "removed": 清理的旧块数, "unchanged": 未变化块数}。
        - 新文件: removed=0
        - 替换同名文件: 旧版本独有块被删除, 新块入库, 未变块保留
        - 重复上传同内容: 全部 unchanged

        user_id/subject：行级隔离模式——数据进统一 ``knowledge`` 库，
        metadata 补 owner/subject；检索按 where 过滤。全不传则走旧 collection 行为。
        """
        coll, _ = _scope(collection, user_id, subject)
        chunks = process_file(path, self.cfg.chunk_size, self.cfg.chunk_overlap)
        for chunk in chunks:
            meta = dict(chunk.metadata)
            if (user_id or "").strip():
                meta["owner"] = (user_id or "").strip()
            if (subject or "").strip():
                meta["subject"] = (subject or "").strip()
            chunk.metadata = meta
        return self.store.sync_file(coll, os.path.basename(path), chunks)

    def add_files(
        self,
        paths,
        collection: str = "default",
        recursive: bool = True,
        user_id: str = "",
        subject: str = "",
    ) -> dict:
        """批量导入: 接受文件路径或目录的列表/单个路径。
        - 目录会递归(recursive=True)收集其中支持格式的文件
        - 返回 {"added": 入库文件数, "files": [{path, added, removed, unchanged}...],
                "skipped": [未支持/失败的文件列表], "total_chunks": 总新增块数}
        """
        from .document_processor import SUPPORTED_EXTS

        # 展开为文件路径列表
        file_list: List[str] = []
        raw = paths if isinstance(paths, (list, tuple, set)) else [paths]
        for p in raw:
            p = str(p)
            if os.path.isdir(p):
                for root, _, fs in os.walk(p):
                    for fn in sorted(fs):
                        if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTS:
                            file_list.append(os.path.join(root, fn))
                    if not recursive:
                        break
            elif os.path.isfile(p):
                file_list.append(p)

        result = {"added": 0, "files": [], "skipped": [], "total_chunks": 0}
        for fp in file_list:
            try:
                r = self.add_file(
                    fp, collection=collection, user_id=user_id, subject=subject
                )
                result["files"].append({"path": fp, **r})
                result["added"] += 1
                result["total_chunks"] += r["added"]
            except Exception as e:
                result["skipped"].append({"path": fp, "error": str(e)})
        return result

    def add_text(
        self,
        text: str,
        collection: str = "default",
        source: str = "text",
        user_id: str = "",
        subject: str = "",
    ) -> int:
        """直接以文本入库(便于 Agent 传递非文件内容)"""
        from .document_processor import TextChunk

        meta: Dict = {"source": source}
        if (user_id or "").strip():
            meta["owner"] = (user_id or "").strip()
        if (subject or "").strip():
            meta["subject"] = (subject or "").strip()
        coll, _ = _scope(collection, user_id, subject)
        chunks = [TextChunk(text, meta)]
        return self.store.add_documents(coll, chunks)

    # ---------------- 检索与问答 ----------------
    def search(
        self,
        question: str,
        collection: str = "default",
        top_k: Optional[int] = None,
        user_id: str = "",
        subject: str = "",
    ) -> List[SearchResult]:
        coll, where = _scope(collection, user_id, subject)
        docs = self.rag.search(coll, question, top_k, where=where)
        return [SearchResult(text=d["text"], metadata=d["metadata"],
                             score=d["score"]) for d in docs]

    def ask(
        self,
        question: str,
        collection: str = "default",
        top_k: Optional[int] = None,
        user_id: str = "",
        subject: str = "",
    ) -> AskResult:
        coll, where = _scope(collection, user_id, subject)
        result = self.rag.ask(coll, question, top_k, where=where)
        return AskResult(answer=result["answer"], sources=result["sources"])

    def locate(
        self,
        text: str,
        collection: str = "default",
        top_k: Optional[int] = None,
        user_id: str = "",
        subject: str = "",
    ) -> List[SearchResult]:
        """给一段内容找知识库出处（只检索，不调 LLM）。"""
        return self.search(text, collection, top_k, user_id=user_id, subject=subject)

    def list_chunks(
        self,
        collection: str = "default",
        filename: str = "",
        user_id: str = "",
        subject: str = "",
    ) -> List[Dict]:
        """列出已入库的知识块（可按来源文件 / 行级 owner+subject 过滤）。"""
        coll, where = _scope(collection, user_id, subject)
        return self.store.list_chunks(coll, filename, where=where)


def get_knowledge(
    *,
    fake: bool = False,
    persist_dir: str | None = None,
    user_id: str = "",
) -> KnowledgeTool:
    """按项目根 .env 构造知识库（LLM 跟随 LLM_BACKEND：vllm 时复用 LLM_VLLM_*）。

    传 ``user_id`` 时按用户顶层物理隔离（``data/{user_id}/knowledge/chromadb``），
    不传则用默认统一库路径。
    """
    if persist_dir is None and user_id:
        from tools.knowledge.config import persist_dir_for_user

        persist_dir = persist_dir_for_user(user_id)
    return KnowledgeTool(fake=fake, persist_dir=persist_dir)


def knowledge_for_user(user_id: str, *, fake: bool = False) -> KnowledgeTool:
    """按用户隔离的知识库实例（user 顶层物理隔离，subject 仍走 where）。"""
    return get_knowledge(fake=fake, user_id=user_id)


# 行级隔离的统一知识库 collection 名（owner/subject 走 metadata + where 过滤）
KB_COLLECTION = "knowledge"


def _scope(collection: str, user_id: str = "", subject: str = "") -> tuple[str, dict | None]:
    """行级模式路由：传了 user_id/subject 时固定统一库 + where 过滤；全空则旧 collection 行为。

    返回 (collection 名, where dict 或 None)。
    """
    uid = (user_id or "").strip()
    subj = (subject or "").strip()
    if uid or subj:
        where: dict = {}
        if uid:
            where["owner"] = uid
        if subj:
            where["subject"] = subj
        return KB_COLLECTION, where
    return (collection or "default"), None

