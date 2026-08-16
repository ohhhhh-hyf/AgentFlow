"""RAG 问答 —— 检索 + DeepSeek LLM, 带来源引用与统计 top_k 增强。"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .config import KnowledgeToolConfig
from .vector_store import VectorStore

# 统计类问题关键词: 命中则放大 top_k, 减少漏数
STAT_KEYWORDS = re.compile(
    r"多少|几个|几条|几项|几种|数量|总数|总共|总计|合计|统计|汇总|求和|"
    r"平均|最大|最小|占比|比例|百分比|分布|排名|排序|前\d|top\s*\d|"
    r"count|sum|avg|max|min",
    re.IGNORECASE,
)
STAT_TOPK_BOOST = 5

SYSTEM_PROMPT = """你是一个专业的知识库助手。请严格根据下方提供的【参考资料】来回答用户的问题。

要求：
1. 只使用参考资料中的信息回答，不要编造或添加资料中没有的内容
2. 如果参考资料中没有与问题相关的信息，请明确告知用户"在当前知识库中未找到相关信息"
3. 回答要准确、简洁、条理清晰
4. 如果参考资料中包含【统计摘要】，请优先使用摘要中的统计数据（如总行数、计数、求和、不同值分布等）来回答数量、统计类问题，摘要中的数据是对完整表格预计算的精确结果
5. 回答涉及数量统计时，如果有统计摘要请直接引用其数据；如果没有统计摘要，请说明"以下统计基于检索到的部分数据，可能不完整"
6. 在回答末尾，列出你引用的资料来源，格式为：
   【来源】文件名, 第X页"""

USER_PROMPT_TEMPLATE = "【参考资料】\n{context}\n\n【用户问题】\n{question}"


def _effective_top_k(question: str, top_k: int) -> int:
    if STAT_KEYWORDS.search(question):
        return top_k + STAT_TOPK_BOOST
    return top_k


def _build_context(docs: List[Dict]) -> str:
    """检索结果 → 参考资料文本"""
    parts = []
    for i, d in enumerate(docs):
        meta = d.get("metadata") or {}
        src = meta.get("source") or "未知来源"
        page = meta.get("page")
        head = f"[资料{i+1}] 来源: {src}" + (f" 第{page}页" if page else "")
        parts.append(f"{head}\n{d.get('text', '').strip()}")
    return "\n\n---\n\n".join(parts)


def _build_sources(docs: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for d in docs:
        meta = d.get("metadata") or {}
        fname = meta.get("source") or "未知文件"
        key = (fname, meta.get("page"))
        if key in seen:
            continue
        seen.add(key)
        excerpt = d.get("text", "")
        out.append({"file": fname, "page": meta.get("page"),
                    "excerpt": (excerpt[:80] + "..." if len(excerpt) > 80 else excerpt),
                    "score": d.get("score")})
    return out


class RagService:
    """检索增强问答服务"""

    def __init__(self, cfg: KnowledgeToolConfig, store: VectorStore, fake: bool = False):
        self.cfg = cfg
        self.store = store
        self.fake = fake
        self._client = None

    def _lazy_client(self):
        if self.fake:
            return None
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.cfg.llm_api_key,
                                  base_url=self.cfg.llm_base_url)
        return self._client

    # ---------------- 检索 ----------------
    def search(self, collection: str, question: str, top_k: Optional[int] = None) -> List[Dict]:
        k = _effective_top_k(question, top_k or self.cfg.top_k)
        return self.store.query(collection, question, k)

    # ---------------- 问答 ----------------
    def ask(self, collection: str, question: str,
            top_k: Optional[int] = None) -> Dict:
        """检索 + LLM 回答 → {"answer": str, "sources": [...]}"""
        docs = self.search(collection, question, top_k)
        if not docs:
            return {"answer": "在当前知识库中未找到相关信息，请确认知识库中已导入相关文档。",
                    "sources": []}
        if self.fake:
            answer = self._fake_answer(question, docs)
        else:
            client = self._lazy_client()
            resp = client.chat.completions.create(
                model=self.cfg.llm_model,
                max_tokens=self.cfg.max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                        context=_build_context(docs), question=question)},
                ],
            )
            answer = resp.choices[0].message.content or ""
        return {"answer": answer, "sources": _build_sources(docs)}

    @staticmethod
    def _fake_answer(question: str, docs: List[Dict]) -> str:
        """离线测试用假 LLM: 引用检索到的块"""
        parts = [f"[离线测试模式] 问题: {question}\n",
                 f"检索到 {len(docs)} 个相关片段, 最相关片段如下:\n"]
        parts.append(docs[0].get("text", "")[:200])
        return "\n".join(parts)
