# -*- coding: utf-8 -*-
"""多源检索聚合：资料知识库 + 会议记忆 → 统一上下文。

两路来源：
1. ``tools.knowledge``（KnowledgeTool）：笔记/资料，行级隔离（user_id 必填，subject 可选过滤）
2. ``tools.memory``（MemoryEmbedder）：会议记忆，先 ``search_projects`` 找相关档案，
   再 ``search_entries`` 取条目文本

任何一路检索失败都降级（返回已成功的一路），不中断会话。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _kb_docs(question: str, user_id: str, subject: str, top_k: int) -> list[dict[str, Any]]:
    """资料知识库检索（笔记/课件/讲义/入库文件，按用户顶层物理隔离）。"""
    from tools.knowledge.tool import knowledge_for_user

    kb = knowledge_for_user(user_id)
    hits = kb.search(
        question,
        user_id=user_id,
        subject=subject or "",
        top_k=top_k,
    )
    docs: list[dict[str, Any]] = []
    for h in hits:
        meta = h.metadata or {}
        src = str(meta.get("source") or "").strip()
        docs.append(
            {
                "text": str(h.text or ""),
                "source": f"[{src}]" if src else "[知识库]",
                "kind": "资料",
            }
        )
    return docs


def _memory_docs(question: str, user_id: str, top_k: int) -> list[dict[str, Any]]:
    """会议记忆检索：档案级 → 条目级（跨项目，按用户物理隔离）。"""
    from tools.memory.embed import get_embedder

    embedder = get_embedder(user_id=user_id)
    projects = embedder.search_projects(question, user_id, top_k=3)
    docs: list[dict[str, Any]] = []
    for proj in projects:
        pid = str(proj.get("project_id") or "")
        if not pid:
            continue
        entries = embedder.search_entries(question, user_id, pid, top_k=3)
        for e in entries:
            text = str(e.get("text") or "").strip()
            if not text:
                continue
            title = str(e.get("title") or "").strip() or "历史会议"
            seq = int(e.get("seq") or 0)
            at = str(e.get("at") or "").strip()
            date = at.split()[0] if at else ""
            etype = str(e.get("etype") or "").strip()
            bits = [title]
            suffix = ""
            if seq:
                suffix += f"第{seq}场"
            if date:
                suffix += f"（{date} 记录）"
            if suffix:
                bits.append(suffix)
            docs.append(
                {
                    "text": text,
                    "source": " · ".join(bits),
                    "kind": f"会议·{etype}" if etype else "会议",
                }
            )
    return docs


def gather(
    question: str,
    user_id: str,
    subject: str = "",
    *,
    top_k: int = 5,
    need_knowledge: bool = True,
    need_memory: bool = True,
) -> list[dict[str, Any]]:
    """多源检索聚合。返回 ``[{text, source, kind}]``（按来源分组：资料 → 会议记忆）。

    ``need_knowledge`` / ``need_memory`` 由检索门控（chat/gate.py）决定：
    不需要的源直接跳过，省检索成本；任一源失败仅记日志并跳过（不中断会话）。
    """
    docs: list[dict[str, Any]] = []
    if need_knowledge:
        try:
            docs.extend(_kb_docs(question, user_id, subject, top_k))
        except Exception as exc:  # noqa: BLE001
            logger.warning("检索来源 知识库 失败：%s", exc)
    if need_memory:
        try:
            docs.extend(_memory_docs(question, user_id, top_k))
        except Exception as exc:  # noqa: BLE001
            logger.warning("检索来源 会议记忆 失败：%s", exc)
    return docs


def build_context(docs: list[dict[str, Any]]) -> str:
    """把检索结果拼成带来源标注的上下文块。"""
    if not docs:
        return ""
    blocks: list[str] = []
    for i, doc in enumerate(docs, start=1):
        src = doc.get("source") or "未知来源"
        kind = doc.get("kind") or ""
        text = (doc.get("text") or "").strip()
        blocks.append(f"[{i}]（{kind} · {src}）{text}")
    return "\n".join(blocks)
