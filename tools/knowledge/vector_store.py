"""向量库 —— ChromaDB(独立新库) + 硅基流动 Embedding(可测试模式)。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Dict, List, Optional

from .config import KnowledgeToolConfig

try:  # chromadb 缺失时降级（离线/测试环境）
    from chromadb.errors import NotFoundError as _COLLECTION_MISSING
except Exception:  # pragma: no cover - noqa: BLE001
    _COLLECTION_MISSING = Exception  # type: ignore[misc]


# ChromaDB 集合名要求: 3-512 字符, [a-zA-Z0-9._-], 首尾字母数字
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]$")


def _safe_name(name: str) -> str:
    """合规名字直接用; 否则映射为 c_<md5> 内部名"""
    if 3 <= len(name) <= 512 and _NAME_RE.match(name):
        return name
    return "c_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:16]


# 每次嵌入请求的最大文本条数(硅基流动 API 单请求输入限制)
EMBED_BATCH = 64

# ── 短块嵌入带标题上下文（策略三）────────────────────────────
# 短块（估算 token < 64）在向量空间中被少数词主导，缺章节语义；长块自身语义
# 已足，加前缀反而稀释。64 ≈ 平均块长（约 100 token）的过半，低于它正文不足
# 以自释上下文。嵌入输入 = heading_path_text + 正文；存储 document 与 metadata
# 保持原文本——检索返回、RRF 融合键、cite 重合评分、块 ID 全部零影响。
# 开关 KNOWLEDGE_EMBED_HEADING_PREFIX=0 关闭（A/B 用；切换后建议重建库保持
# 全库向量口径一致——unchanged 块不重嵌，见 sync_files）。
_HEADING_PREFIX_MAX_TOKENS = 64


def _heading_prefix_enabled() -> bool:
    return os.getenv("KNOWLEDGE_EMBED_HEADING_PREFIX", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }

# ── 混合检索辅助（#6 向量+关键词）─────────────────────────────
# 查询关键词提取：只做形态与停用词过滤，不做语义分词。
_QUERY_STOP = frozenset(
    """
    的 了 呢 吗 啊 吧 是 在 有 和 与 或 及 对 从 把 被 就 都 也 还 又 很 更 最
    怎么 如何 什么 哪些 哪个 多少 为什么 是否 可以 需要 请问 一下 一个 一种
    这种 那种 这样 那样 我们 你们 他们 这个 那个 没有 不是 还是 已经 现在 今天
    the and for with from that this have been will not what how why which where when
    is are of to in on at by or an as
    """.split()
)
_QUERY_HAN = re.compile(r"[\u4e00-\u9fff]+")
_QUERY_LATIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-]{1,}")
_QUERY_EDGE = set("的了着过在是就也还又都和与或及把被从对把")


def _extract_keywords(query: str, limit: int = 6) -> list[str]:
    """从查询提取 where_document 关键词：拉丁/数字 token + 中文 3-4 字块。

    中文不做分词，取 3-4 字 n-gram（有信息量的连续块），
    供 chroma ``$contains`` 子串匹配做关键词路召回。
    """
    text = (query or "").strip()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        tok = (tok or "").strip()
        if len(tok) < 2 or tok.lower() in _QUERY_STOP:
            return
        if tok[0] in _QUERY_EDGE or tok[-1] in _QUERY_EDGE:
            return
        if tok in seen:
            return
        seen.add(tok)
        out.append(tok)

    for tok in _QUERY_LATIN.findall(text):
        add(tok)
    for block in _QUERY_HAN.findall(text):
        n = len(block)
        for size in (4, 3):
            if n < size:
                continue
            for i in range(0, n - size + 1):
                add(block[i : i + size])
                if len(out) >= limit:
                    return out[:limit]
    return out[:limit]


def _rrf_merge(groups: list[list[dict]], top_k: int, k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion：多路召回按 rank 倒数加权合并，返回 top_k 条。

    同一条文（document 原文）跨路合并分数；保留首次出现时的完整行。
    """
    acc: dict[str, dict] = {}
    score: dict[str, float] = {}
    for group in groups:
        for rank, row in enumerate(group):
            key = str(row.get("text") or "")
            if not key:
                continue
            score[key] = score.get(key, 0.0) + 1.0 / (k + rank + 1)
            acc.setdefault(key, row)
    ordered = sorted(acc.keys(), key=lambda x: score[x], reverse=True)
    return [acc[key] for key in ordered[:top_k]]


def _chunk_key(chunk) -> str:
    """块定位键: 行级作用域 + 文件名 + 页码/行号/块序号 + 文本。

    用于生成确定性块 ID; 同文件同页同文本 → 相同 ID(增量同步可识别未变化块),
    不同页同文本 → 不同 ID(避免 ChromaDB id 冲突)。
    含 owner/subject：行级隔离下不同用户同名同文本文件不互相覆盖。
    """
    m = getattr(chunk, "metadata", {}) or {}
    loc = "|".join(str(m.get(k, "")) for k in
                   ("page", "rows", "sheet", "chunk_index"))
    scope = f"{m.get('owner', '')}|{m.get('subject', '')}"
    return f"{scope}|{m.get('source', '')}|{loc}|{getattr(chunk, 'text', chunk)}"


def _normalize_where(where: Optional[Dict]) -> Optional[Dict]:
    """chroma 1.5.9 兼容：多条件 where 必须包 ``$and``（单条件保持原样）。"""
    if not where or len(where) <= 1:
        return where
    return {"$and": [{key: value} for key, value in where.items()]}


def _unique_ids(chunks) -> List[str]:
    """确定性块 ID 列表; 极端重复(同页同文本)时追加序号保证唯一。"""
    ids, seen = [], set()
    for c in chunks:
        base = hashlib.md5(_chunk_key(c).encode("utf-8")).hexdigest()
        key = base
        i = 1
        while key in seen:
            key = hashlib.md5(f"{base}#{i}".encode("utf-8")).hexdigest()
            i += 1
        seen.add(key)
        ids.append(key)
    return ids

# ============================================================
# Embedding 客户端
# ============================================================
class EmbeddingClient:
    """OpenAI 兼容嵌入客户端(默认硅基流动 BAAI/bge-m3)"""

    def __init__(self, cfg: KnowledgeToolConfig, fake: bool = False):
        self.cfg = cfg
        self.fake = fake
        self._client = None

    def _lazy_client(self):
        if self.fake:
            return None
        if self._client is None:
            import httpx
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.cfg.embedding_api_key,
                base_url=self.cfg.embedding_base_url,
                http_client=httpx.Client(
                    verify=self.cfg.embedding_verify_ssl,
                    trust_env=True,
                ),
            )
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入(按硅基流动 API 约束分批)。

        - 过滤空字符串(文档明确禁止空 input)
        - 分批提交: 每批最多 EMBED_BATCH 条(避免超模型上下文 token 限制)
        - 传 truncate="right": 超长文本按右侧截断(与硅基流动文档对齐)
        fake=True 时返回确定性伪向量(离线测试/开发用)。
        """
        texts = [t for t in texts if t and t.strip()]
        if self.fake:
            return [self._fake_embed(t) for t in texts]
        client = self._lazy_client()
        results: List[List[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            resp = client.embeddings.create(
                model=self.cfg.embedding_model,
                input=batch,
                extra_body={"truncate": "right"},   # 硅基流动: 超长右截断
            )
            results.extend(d.embedding for d in resp.data)
            self._record_usage(resp, batch)
        return results

    @staticmethod
    def _record_usage(resp: object, batch: List[str]) -> None:
        """记录本次 embedding 调用的消耗（进任务监控，与 LLM usage 分开）。

        优先读响应 usage（prompt_tokens）；缺失时按字符粗略估算。
        任何异常都吞掉，监控失败不影响主流程。
        """
        try:
            usage = getattr(resp, "usage", None)
            tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            if not tokens:
                tokens = sum(len(t) for t in batch) // 2
            from tools.monitor.side import record_embed

            record_embed(calls=1, tokens=tokens)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _fake_embed(text: str, dim: int = 384) -> List[float]:
        """确定性 hash 向量: 同文本 → 同向量, 保证检索可复现"""
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [0.0] * dim
        for i in range(dim):
            vec[i] = (h[i % 32] / 255.0) - 0.5
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _embedding_input(chunk) -> str:
        """嵌入输入组装：短块加 heading_path_text 前缀（策略三）。

        只影响向量计算；块的存储 text / metadata / 块 ID 均不受影响。
        无 heading_path_text 的块（xlsx/pdf 按页块等）自然回退纯文本。"""
        text = str(getattr(chunk, "text", "") or "")
        if not _heading_prefix_enabled():
            return text
        from .document_processor import _estimated_tokens

        if _estimated_tokens(text) >= _HEADING_PREFIX_MAX_TOKENS:
            return text
        path = str((getattr(chunk, "metadata", {}) or {}).get("heading_path_text") or "").strip()
        if not path:
            return text
        return f"{path}\n{text}"


# ============================================================
# VectorStore
# ============================================================
class VectorStore:
    """ChromaDB 封装: 集合管理 / 入库 / 检索 / 删除。
    集合名不合规(短名/中文)时自动映射为内部安全名, 映射持久化在 persist_dir。"""

    def __init__(self, cfg: KnowledgeToolConfig, fake: bool = False):
        import chromadb
        self.cfg = cfg
        self.fake = fake
        self.client = chromadb.PersistentClient(path=cfg.persist_dir)
        self.embedding = EmbeddingClient(cfg, fake=fake)
        self._map_file = os.path.join(cfg.persist_dir, "_collections_map.json")
        self._name_map: Dict[str, str] = {}   # 显示名 → 内部名
        self._load_map()

    # ---------------- 名称映射 ----------------
    def _load_map(self) -> None:
        if os.path.isfile(self._map_file):
            try:
                with open(self._map_file, "r", encoding="utf-8") as f:
                    self._name_map = json.load(f)
            except Exception:
                self._name_map = {}

    def _save_map(self) -> None:
        os.makedirs(self.cfg.persist_dir, exist_ok=True)
        with open(self._map_file, "w", encoding="utf-8") as f:
            json.dump(self._name_map, f, ensure_ascii=False, indent=2)

    def _internal(self, name: str) -> str:
        """显示名 → 内部集合名(并记录映射)"""
        if name in self._name_map:
            return self._name_map[name]
        internal = _safe_name(name)
        if internal != name:
            self._name_map[name] = internal
            self._save_map()
        return internal

    # ---------------- 入库 ----------------
    def sync_files(self, collection: str, items: List) -> List[dict]:
        """批量增量同步多个文件（处理"用户更新/替换同名文件"场景）：

        - 逐文件按确定性块 ID（md5(scope+source+loc+text)）规划
          removed/added/unchanged；
        - 全部文件的 removed 合并一次 delete，全部 added 的文本合并**一次**
          embedding 调用（API 往返与文件数无关）后合并 upsert；
        - unchanged 块不写入：同 ID 即同文本，嵌入与内容均无变化（原实现会
          全量重嵌 + upsert 覆盖，是纯浪费；元数据在同代码版本下也逐字相同）。

        返回按输入顺序的逐文件结果，每项含：
        - {"added","removed","unchanged"}：增量计数（与原 sync_file 口径一致）
        - "chunks"：该文件入库后的全部块（added+unchanged，{"text","metadata"}），
          供入库报告直接使用，免去事后全库扫描按 source 过滤。
        """
        coll = self.client.get_or_create_collection(
            name=self._internal(collection), metadata={"hnsw:space": "cosine"}
        )
        plans: List[dict] = []
        for filename, chunks in items:
            # embed() 会丢弃空文本并导致向量错位，这里在规划期显式排除空文本块
            chunks = [
                c for c in chunks
                if str(getattr(c, "text", "") or "").strip()
            ]
            new_ids = _unique_ids(chunks)
            new_set = set(new_ids)
            chunk_by_id = dict(zip(new_ids, chunks))

            # 该文件当前已有的块 id（行级模式按 owner/subject 限定，防跨用户同名文件误删）
            existing_ids: set = set()
            try:
                cond: Dict = {"source": filename}
                if chunks:
                    m0 = getattr(chunks[0], "metadata", {}) or {}
                    if m0.get("owner"):
                        cond["owner"] = m0["owner"]
                    if m0.get("subject"):
                        cond["subject"] = m0["subject"]
                got = coll.get(where=_normalize_where(cond), include=["metadatas"])
                existing_ids = {i for i in got.get("ids", [])}
            except Exception:
                pass   # where 过滤异常时保守处理: 仅 upsert 新块

            added_ids = [i for i in new_ids if i not in existing_ids]
            plans.append({
                "filename": filename,
                "chunks": chunks,
                "added_ids": added_ids,
                "added_chunks": [chunk_by_id[i] for i in added_ids],
                "removed": sorted(existing_ids - new_set),
                "unchanged": len(new_set & existing_ids),
            })

        all_removed = [i for p in plans for i in p["removed"]]
        if all_removed:
            coll.delete(ids=all_removed)

        # 全部文件的 added 合并一次嵌入（嵌入是入库的 API 成本大头）；
        # 嵌入输入经 _embedding_input 组装（短块带标题上下文），存储文本不变
        added_chunks = [c for p in plans for c in p["added_chunks"]]
        import time

        t0 = time.monotonic()
        if added_chunks:
            embeddings = self.embedding.embed(
                [EmbeddingClient._embedding_input(c) for c in added_chunks]
            )
            coll.upsert(
                ids=[i for p in plans for i in p["added_ids"]],
                embeddings=embeddings,
                documents=[c.text for c in added_chunks],
                metadatas=[dict(c.metadata) for c in added_chunks],
            )
        results: List[dict] = []
        for p in plans:
            results.append({
                "added": len(p["added_ids"]),
                "removed": len(p["removed"]),
                "unchanged": p["unchanged"],
                "chunks": [
                    {"text": c.text, "metadata": dict(c.metadata)}
                    for c in p["chunks"]
                ],
            })
        try:
            from tools.monitor.side import record_knowledge_ingest

            record_knowledge_ingest(
                files=len(plans),
                added=sum(r["added"] for r in results),
                removed=sum(r["removed"] for r in results),
                unchanged=sum(r["unchanged"] for r in results),
                seconds=time.monotonic() - t0,
                collection=collection,
            )
        except Exception:  # noqa: BLE001
            pass
        return results

    def delete_sources(
        self,
        collection: str,
        filenames: List[str],
        where: Optional[Dict] = None,
    ) -> int:
        """删除指定来源文件的全部块（行级 where 限定 owner/subject 防跨用户误删）。

        用于"代际替换"场景：新版文件入库前清掉旧代来源的全部块。
        返回实际删除的块数；来源不存在返回 0。
        """
        if not filenames:
            return 0
        try:
            coll = self.client.get_collection(name=self._internal(collection))
        except _COLLECTION_MISSING:
            return 0
        cond: Dict = {"source": {"$in": list(filenames)}}
        if where:
            cond.update(where)
        try:
            got = coll.get(where=_normalize_where(cond), include=[])
        except Exception:
            return 0
        ids = list(got.get("ids", []))
        if ids:
            coll.delete(ids=ids)
        return len(ids)

    # ---------------- 检索 ----------------
    def query(
        self,
        collection: str,
        query_text: str,
        top_k: int,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """混合检索 → [{text, metadata, score}], score = 1 - distance。

        两路召回后 RRF 融合：
        - 路1 纯向量相似度（语义召回）
        - 路2 关键词过滤 + 向量排序（chroma ``where_document $contains`` 子串命中，
          中文专业词/编号/缩写场景下补语义漏配）
        ``where``：可选 metadata 过滤（如 {"owner": user_id}，行级隔离用）。
        融合后按 ``cfg.min_score`` 过滤低相关块；fake 模式跳过阈值（伪向量分布不真实）。
        """
        import time

        t0 = time.monotonic()
        try:
            coll = self.client.get_collection(name=self._internal(collection))
        except _COLLECTION_MISSING:
            return []  # 用户库尚未创建时视为空库
        emb = self.embedding.embed([query_text])[0]
        # 旧库兼容：chroma 默认 L2 空间（score=1-L2 与余弦语义不同），
        # 该空间的 min_score 阈值不生效，保持旧行为；cosine 空间才启用阈值。
        space = str((coll.metadata or {}).get("hnsw:space") or "l2")
        count = coll.count()
        if count <= 0:
            try:
                from tools.monitor.side import record_knowledge_search

                record_knowledge_search(
                    hits=0,
                    seconds=time.monotonic() - t0,
                    collection=collection,
                )
            except Exception:  # noqa: BLE001
                pass
            return []
        # 融合需要更多候选：各路召回 top_k*2，RRF 后收敛回 top_k
        recall_k = min(top_k * 2, count)
        include = ["documents", "metadatas", "distances"]

        def _to_rows(got: dict) -> List[Dict]:
            docs, metas, dists = (
                got["documents"][0],
                got["metadatas"][0],
                got["distances"][0],
            )
            return [
                {"text": d, "metadata": m, "score": round(1 - dist, 4)}
                for d, m, dist in zip(docs, metas, dists)
            ]

        # 路1：纯向量
        got1 = coll.query(
            query_embeddings=[emb],
            n_results=recall_k,
            include=include,
            where=_normalize_where(where),
        )
        rows1 = _to_rows(got1)
        # 路2：关键词过滤 + 向量排序
        rows2: List[Dict] = []
        if getattr(self.cfg, "hybrid_search", True):
            kws = _extract_keywords(query_text, int(getattr(self.cfg, "hybrid_keywords", 6) or 6))
            if kws:
                where_doc = {"$or": [{"$contains": kw} for kw in kws]}
                try:
                    got2 = coll.query(
                        query_embeddings=[emb],
                        n_results=recall_k,
                        where_document=where_doc,
                        where=_normalize_where(where),
                        include=include,
                    )
                    rows2 = _to_rows(got2)
                except Exception:  # noqa: BLE001 - where_document 兼容性失败退化为纯向量
                    rows2 = []
        if rows2:
            rows = _rrf_merge([rows1, rows2], top_k)
        else:
            rows = rows1[:top_k]
        # score 阈值过滤（fake 伪向量分布不真实；L2 旧库分数语义不同，均跳过）
        min_score = float(getattr(self.cfg, "min_score", 0.0) or 0.0)
        if min_score > 0 and not self.fake and space == "cosine":
            rows = [r for r in rows if r["score"] >= min_score]
        try:
            from tools.monitor.side import record_knowledge_search

            record_knowledge_search(
                hits=len(rows),
                seconds=time.monotonic() - t0,
                collection=collection,
            )
        except Exception:  # noqa: BLE001
            pass
        return rows

    def list_files(
        self, collection: str, where: Optional[Dict] = None
    ) -> List[str]:
        coll = self.client.get_collection(name=self._internal(collection))
        got = coll.get(where=_normalize_where(where), include=["metadatas"])
        return sorted({m["source"] for m in (got.get("metadatas") or [])
                       if m and m.get("source")})

    def list_chunks(
        self,
        collection: str,
        filename: str = "",
        where: Optional[Dict] = None,
        *,
        with_metadata: bool = True,
        with_text: bool = True,
    ) -> List[Dict]:
        """列出某库中的块；可按来源文件/行级 where 过滤（多条件 AND）。

        - with_metadata=False：只取 text（轻量扫描，供全库对比类消费方省 IO）；
        - with_text=False：只取 metadata（标题/字段扫描类消费方，全库正文不进
          内存——如目录 briefing 只消费 heading/score/kind 等元字段）；
        - 两者不可同时为 False（无字段可返回）。
        """
        if not with_metadata and not with_text:
            raise ValueError("list_chunks: with_metadata 与 with_text 不能同时为 False")
        try:
            coll = self.client.get_collection(name=self._internal(collection))
        except _COLLECTION_MISSING:
            return []  # 用户库尚未创建时视为空库
        cond: Dict = {}
        if filename:
            cond["source"] = filename
        if where:
            cond.update(where)
        include: List[str] = []
        if with_text:
            include.append("documents")
        if with_metadata:
            include.append("metadatas")
        got = coll.get(where=_normalize_where(cond) if cond else None,
                       include=include)
        docs = got.get("documents") or []
        if not with_metadata:
            return [{"text": text or ""} for text in docs]
        metas = got.get("metadatas") or []
        out: List[Dict] = []
        if not with_text:
            # 无正文档：返回项不含 text 键（消费方误用会立即暴露，而非静默空串）
            for meta in metas:
                out.append({"metadata": meta or {}})
            try:
                from tools.monitor.side import record_knowledge_search

                record_knowledge_search(hits=len(out), collection=collection, kind="scan")
            except Exception:  # noqa: BLE001
                pass
            return out
        for text, meta in zip(docs, metas):
            out.append({"text": text or "", "metadata": meta or {}})
        try:
            from tools.monitor.side import record_knowledge_search

            record_knowledge_search(hits=len(out), collection=collection, kind="scan")
        except Exception:  # noqa: BLE001
            pass
        return out
