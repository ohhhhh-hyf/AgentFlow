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

    def _display(self, internal: str) -> str:
        """内部集合名 → 显示名"""
        for d, i in self._name_map.items():
            if i == internal:
                return d
        return internal

    # ---------------- 集合 ----------------
    def list_collections(self) -> List[Dict]:
        out = []
        for c in self.client.list_collections():
            try:
                out.append({"name": self._display(c.name), "count": c.count()})
            except Exception:
                out.append({"name": self._display(c.name), "count": 0})
        return sorted(out, key=lambda x: x["name"])

    def create_collection(self, name: str) -> str:
        internal = self._internal(name)
        # 显式用余弦空间：score = 1 - distance = cos(相似度)，与 min_score 阈值语义一致
        self.client.get_or_create_collection(
            name=internal, metadata={"hnsw:space": "cosine"}
        )
        return name

    def delete_collection(self, name: str) -> None:
        internal = self._internal(name)
        self.client.delete_collection(internal)
        self._name_map.pop(name, None)
        self._save_map()

    # ---------------- 入库 ----------------
    def add_documents(self, collection: str, chunks: List) -> int:
        """嵌入并 upsert; 返回成功入库块数。id 由 定位键 确定性生成(见 _unique_ids)。"""
        import time

        t0 = time.monotonic()
        coll = self.client.get_or_create_collection(
            name=self._internal(collection), metadata={"hnsw:space": "cosine"}
        )
        texts = [c.text for c in chunks]
        embeddings = self.embedding.embed(texts)
        ids = _unique_ids(chunks)
        coll.upsert(ids=ids, embeddings=embeddings,
                    documents=texts, metadatas=[dict(c.metadata) for c in chunks])
        try:
            from tools.monitor.side import record_knowledge_ingest

            record_knowledge_ingest(
                files=1,
                added=len(ids),
                seconds=time.monotonic() - t0,
                collection=collection,
            )
        except Exception:  # noqa: BLE001
            pass
        return len(ids)

    def sync_file(self, collection: str, filename: str, chunks: List) -> dict:
        """增量同步一个文件的知识库内容(处理"用户更新/替换文件"场景):
        - 计算新块 id 集合(md5(source+文本))
        - 与集合中该 source 下已有块对比:
            removed  = 旧版本独有(已被新版本删除的块)
            added    = 新版本新增的块
            unchanged= 新旧都有的块(不重复 embedding, upsert 覆盖即可)
        - 删除 removed, upsert 新块

        新文件: removed=0; 同名替换: 旧内容被清理; 重复上传同内容: 全部 unchanged。
        """
        coll = self.client.get_or_create_collection(
            name=self._internal(collection), metadata={"hnsw:space": "cosine"}
        )
        new_ids = _unique_ids(chunks)
        new_set = set(new_ids)

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

        removed = sorted(existing_ids - new_set)
        added = sorted(new_set - existing_ids)
        unchanged = sorted(new_set & existing_ids)
        if removed:
            coll.delete(ids=removed)

        # upsert 新块(相同 id 覆盖; unchanged 块 id 相同不产生实际写入)
        import time

        t0 = time.monotonic()
        texts = [c.text for c in chunks]
        embeddings = self.embedding.embed(texts)
        coll.upsert(ids=new_ids, embeddings=embeddings,
                    documents=texts, metadatas=[dict(c.metadata) for c in chunks])
        result = {"added": len(added), "removed": len(removed),
                "unchanged": len(unchanged)}
        try:
            from tools.monitor.side import record_knowledge_ingest

            record_knowledge_ingest(
                files=1,
                added=result["added"],
                removed=result["removed"],
                unchanged=result["unchanged"],
                seconds=time.monotonic() - t0,
                collection=collection,
            )
        except Exception:  # noqa: BLE001
            pass
        return result

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

    # ---------------- 文件级删除 ----------------
    def delete_file(
        self, collection: str, filename: str, where: Optional[Dict] = None
    ) -> int:
        coll = self.client.get_collection(name=self._internal(collection))
        cond: Dict = {"source": filename}
        if where:
            cond.update(where)
        got = coll.get(where=_normalize_where(cond), include=["metadatas"])
        ids = [i for i, m in zip(got.get("ids", []), got.get("metadatas") or [])
               if m and m.get("source") == filename]
        if ids:
            coll.delete(ids=ids)
        return len(ids)

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
    ) -> List[Dict]:
        """列出某库中的块；可按来源文件/行级 where 过滤（多条件 AND）。"""
        try:
            coll = self.client.get_collection(name=self._internal(collection))
        except _COLLECTION_MISSING:
            return []  # 用户库尚未创建时视为空库
        cond: Dict = {}
        if filename:
            cond["source"] = filename
        if where:
            cond.update(where)
        got = coll.get(where=_normalize_where(cond) if cond else None,
                       include=["documents", "metadatas"])
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        out: List[Dict] = []
        for text, meta in zip(docs, metas):
            out.append({"text": text or "", "metadata": meta or {}})
        try:
            from tools.monitor.side import record_knowledge_search

            record_knowledge_search(hits=len(out), collection=collection, kind="scan")
        except Exception:  # noqa: BLE001
            pass
        return out
