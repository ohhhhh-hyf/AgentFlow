"""RAG 高层封装：一行构建【外部参考】上下文段。

任何任务线的 agent 都可以简单调用：

    from tools.rag import build_rag_reference, build_rag_reference_from_text

    ref = await build_rag_reference_from_text(
        "meeting", "risk", shared_context, RISK_KEYWORDS
    )
    user_prompt = f"{shared_context}\\n\\n{ref}" if ref else shared_context

设计约束（无痛降级）：
- ``RAG_ENABLED=false`` / 未入库 / 检索失败 / query 为空 → 返回 ``""``，调用方走原逻辑
- 不 import 任何 domain / 任务线（与 tools/rag 其余模块一致）
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from .config import RAGSettings, resolve_rag_settings
from .retriever import retrieve_context

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 按中文句末标点/换行切句
_SENTENCE_SPLIT = re.compile(r"[^。！？\n]+[。！？]?")
# query 长度保护（embedding 上限内）
_QUERY_MAX = 800


def extract_signal_sentences(
    text: str, keywords: list[str], limit: int = 6
) -> list[str]:
    """从文本中提取命中任一关键词的句子（用于构造 RAG query）。

    按中文句号/问号/感叹号/换行切句，保留含关键词的句子，按出现顺序取前 ``limit`` 条。
    """
    pattern = re.compile("|".join(re.escape(k) for k in keywords))
    hits: list[str] = []
    for raw in _SENTENCE_SPLIT.findall(text):
        sentence = re.sub(r"\s+", " ", raw).strip()
        if sentence and pattern.search(sentence):
            hits.append(sentence)
        if len(hits) >= limit:
            break
    return hits


def build_rag_reference_sync(
    domain: str,
    task: str,
    query: str,
    top_k: int = 3,
    settings: RAGSettings | None = None,
) -> str:
    """同步版：检索并拼【外部参考】段；任何失败返回 ``""``。"""
    try:
        cfg = settings or resolve_rag_settings(PROJECT_ROOT)
        if not cfg.enabled:
            return ""
        query = (query or "").strip()
        if not query:
            return ""
        result = retrieve_context(domain, task, query, cfg, top_k=top_k)
        block = result.get("context", "")
        if not block:
            return ""
        return (
            "\n\n【外部参考：历史案例（RAG 检索，仅供类比，非当前事实）】\n"
            f"{block}"
        )
    except Exception:  # noqa: BLE001 - RAG 任何失败都不影响主流程
        return ""


async def build_rag_reference(
    domain: str,
    task: str,
    query: str,
    top_k: int = 3,
) -> str:
    """异步版：检索并拼【外部参考】段（embedding 调用放线程池，不阻塞事件循环）。"""
    return await asyncio.to_thread(
        build_rag_reference_sync, domain, task, query, top_k
    )


async def build_rag_reference_from_text(
    domain: str,
    task: str,
    text: str,
    keywords: list[str],
    top_k: int = 3,
) -> str:
    """最简调用：从文本提取信号句作 query → 检索 → 返回【外部参考】段。

    文本无命中信号句时返回 ``""``。
    """
    sentences = extract_signal_sentences(text, keywords)
    if not sentences:
        return ""
    query = "；".join(sentences)[:_QUERY_MAX]
    return await build_rag_reference(domain, task, query, top_k=top_k)


__all__ = [
    "build_rag_reference",
    "build_rag_reference_from_text",
    "build_rag_reference_sync",
    "extract_signal_sentences",
]
