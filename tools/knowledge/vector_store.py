"""向量库 —— ChromaDB(独立新库) + 硅基流动 Embedding(可测试模式)。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .config import KnowledgeToolConfig

# ChromaDB 集合名要求: 3-512 字符, [a-zA-Z0-9._-], 首尾字母数字
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{1,510}[a-zA-Z0-9]$")


def _safe_name(name: str) -> str:
    """合规名字直接用; 否则映射为 c_<md5> 内部名"""
    if 3 <= len(name) <= 512 and _NAME_RE.match(name):
        return name
    return "c_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:16]


# 每次嵌入请求的最大文本条数(硅基流动 API 单请求输入限制)
EMBED_BATCH = 64


def _chunk_key(chunk) -> str:
    """块定位键: 文件名 + 页码/行号/块序号 + 文本。
    用于生成确定性块 ID; 同文件同页同文本 → 相同 ID(增量同步可识别未变化块),
    不同页同文本 → 不同 ID(避免 ChromaDB id 冲突)。"""
    m = getattr(chunk, "metadata", {}) or {}
    loc = "|".join(str(m.get(k, "")) for k in
                   ("page", "rows", "sheet", "chunk_index"))
    return f"{m.get('source', '')}|{loc}|{getattr(chunk, 'text', chunk)}"


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
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.cfg.embedding_api_key,
                base_url=self.cfg.embedding_base_url,
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
        return results

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
        self.client.get_or_create_collection(name=internal)
        return name

    def delete_collection(self, name: str) -> None:
        internal = self._internal(name)
        self.client.delete_collection(internal)
        self._name_map.pop(name, None)
        self._save_map()

    # ---------------- 入库 ----------------
    def add_documents(self, collection: str, chunks: List) -> int:
        """嵌入并 upsert; 返回成功入库块数。id 由 定位键 确定性生成(见 _unique_ids)。"""
        coll = self.client.get_or_create_collection(name=self._internal(collection))
        texts = [c.text for c in chunks]
        embeddings = self.embedding.embed(texts)
        ids = _unique_ids(chunks)
        coll.upsert(ids=ids, embeddings=embeddings,
                    documents=texts, metadatas=[dict(c.metadata) for c in chunks])
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
        coll = self.client.get_or_create_collection(name=self._internal(collection))
        new_ids = _unique_ids(chunks)
        new_set = set(new_ids)

        # 该文件当前已有的块 id
        existing_ids: set = set()
        try:
            got = coll.get(where={"source": filename}, include=["metadatas"])
            existing_ids = {i for i in got.get("ids", [])}
        except Exception:
            pass   # where 过滤异常时保守处理: 仅 upsert 新块

        removed = sorted(existing_ids - new_set)
        added = sorted(new_set - existing_ids)
        unchanged = sorted(new_set & existing_ids)
        if removed:
            coll.delete(ids=removed)

        # upsert 新块(相同 id 覆盖; unchanged 块 id 相同不产生实际写入)
        texts = [c.text for c in chunks]
        embeddings = self.embedding.embed(texts)
        coll.upsert(ids=new_ids, embeddings=embeddings,
                    documents=texts, metadatas=[dict(c.metadata) for c in chunks])
        return {"added": len(added), "removed": len(removed),
                "unchanged": len(unchanged)}

    # ---------------- 检索 ----------------
    def query(self, collection: str, query_text: str, top_k: int) -> List[Dict]:
        """相似度检索 → [{text, metadata, score}], score = 1 - distance"""
        coll = self.client.get_collection(name=self._internal(collection))
        emb = self.embedding.embed([query_text])[0]
        count = coll.count()
        k = min(top_k, count) if count > 0 else top_k
        if k <= 0:
            return []
        got = coll.query(query_embeddings=[emb], n_results=k,
                         include=["documents", "metadatas", "distances"])
        docs, metas, dists = got["documents"][0], got["metadatas"][0], got["distances"][0]
        return [{"text": d, "metadata": m, "score": round(1 - dist, 4)}
                for d, m, dist in zip(docs, metas, dists)]

    # ---------------- 文件级删除 ----------------
    def delete_file(self, collection: str, filename: str) -> int:
        coll = self.client.get_collection(name=self._internal(collection))
        got = coll.get(include=["metadatas"])
        ids = [i for i, m in zip(got.get("ids", []), got.get("metadatas") or [])
               if m and m.get("source") == filename]
        if ids:
            coll.delete(ids=ids)
        return len(ids)

    def list_files(self, collection: str) -> List[str]:
        coll = self.client.get_collection(name=self._internal(collection))
        got = coll.get(include=["metadatas"])
        return sorted({m["source"] for m in (got.get("metadatas") or [])
                       if m and m.get("source")})

    def list_chunks(self, collection: str, filename: str = "") -> List[Dict]:
        """列出某库中的块；可按来源文件过滤。"""
        coll = self.client.get_collection(name=self._internal(collection))
        if filename:
            got = coll.get(where={"source": filename}, include=["documents", "metadatas"])
        else:
            got = coll.get(include=["documents", "metadatas"])
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        out: List[Dict] = []
        for text, meta in zip(docs, metas):
            out.append({"text": text or "", "metadata": meta or {}})
        return out
