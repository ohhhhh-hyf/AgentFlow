"""记忆向量索引（方案 B：档案级 + 摘录级，复用知识库 embedding/chroma 逻辑）。

布局：
- ``data/memory/chromadb/``：独立 chroma 实例（与 ``data/knowledge/chromadb`` 并列），
  collection 名固定 ``memory``（cosine 空间）。
- 两类向量（metadata 的 ``kind`` 区分）：
  - ``project``：每个项目档案一行，document=项目身份文本
    （display_name + project_key + purpose + entities + 最近决策），
    供「归属解析」语义匹配（换说法也能认回同一项目）。
  - ``entry``：每条历史 目的/议题/决策/未决/风险 一行，
    metadata 带 ``seq``(场次)/``title``/``at``/``etype`` 定位，
    供「记忆摘录注入」语义 top-k 只拉与本次相关条目。

原则：
- record.json 仍是事实本体（权威）；本模块只是可重建的检索索引。
- 全链路容错：embedding/chroma 不可用或抛异常 → 方法返回 None/[]，
  调用方（resolve / inject）自动降级回规则匹配。
- 开关：``MEMORY_EMBEDDING=0`` 关闭（默认开）；阈值/数量可配。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterator

from .entities import entity_names

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

MEMORY_PERSIST_DIR = os.getenv(
    "MEMORY_PERSIST_DIR", str(_PROJECT_ROOT / "data" / "memory" / "chromadb")
)


def memory_persist_dir_for_user(user_id: str) -> str:
    """按用户隔离的记忆向量目录：``data/{user_id}/memory/chromadb``。"""
    uid = (user_id or "").strip()
    if not uid:
        return MEMORY_PERSIST_DIR
    from .store import safe_id

    return str(_PROJECT_ROOT / "data" / safe_id(uid) / "memory" / "chromadb")


def _embedding_enabled() -> bool:
    """动态读开关（运行中改 env 也生效）；默认开启。"""
    return (
        os.getenv("MEMORY_EMBEDDING", "1").strip().lower()
        not in {"0", "false", "off", "no", "disable", "disabled"}
    )


MEMORY_EMBEDDING = _embedding_enabled()
MEMORY_EMBED_MIN_SCORE = float(os.getenv("MEMORY_EMBED_MIN_SCORE", "0.55"))
MEMORY_EMBED_PROJECT_TOP_K = int(os.getenv("MEMORY_EMBED_PROJECT_TOP_K", "3"))
MEMORY_EMBED_ENTRY_TOP_K = int(os.getenv("MEMORY_EMBED_ENTRY_TOP_K", "8"))
# 规则信号加权：查询含档案 project_key/别名/实体（signals 子串）→ 候选加分
MEMORY_EMBED_RULE_BOOST = float(os.getenv("MEMORY_EMBED_RULE_BOOST", "0.08"))

COLLECTION = "memory"


# ── 文本辅助（自包含，避免与 meeting.py 循环依赖）────────────────
def _clean(text: object) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _entry_id(domain: str, user_id: str, project_id: str, seq: int, kind: str, text: str) -> str:
    raw = f"e:{domain}:{user_id}:{project_id}:{seq}:{kind}:{_clean(text)}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _project_id(domain: str, user_id: str, project_id: str) -> str:
    return hashlib.md5(
        f"p:{domain}:{user_id}:{project_id}".encode("utf-8")
    ).hexdigest()


def _project_document(record: dict[str, Any]) -> str:
    """档案级 document：项目身份文本（语义归属匹配用）。

    组合身份字段（display_name/project_key）、最新状态（active_summary）、
    主题词（key_terms）、最近议题（recent_topics）、进行中事项（open_items）
    与最近决策，让向量代表项目"当前状态"而非最初目的。
    """
    meeting = record.get("meeting") if isinstance(record.get("meeting"), dict) else {}
    parts = [
        _clean(record.get("display_name")),
        _clean(record.get("project_key")),
        _clean(record.get("active_summary") or meeting.get("purpose")),
    ]
    terms = [str(t).strip() for t in (record.get("key_terms") or []) if str(t).strip()]
    if terms:
        parts.append("主题：" + "、".join(terms[:12]))
    topics = [str(t).strip() for t in (record.get("recent_topics") or []) if str(t).strip()]
    if topics:
        parts.append("议题：" + "；".join(topics[:6]))
    opens = [
        _clean(item.get("item"))
        for item in (meeting.get("open_items") or [])[:6]
        if isinstance(item, dict) and _clean(item.get("item"))
    ]
    if opens:
        parts.append("进行中：" + "；".join(opens))
    ents = entity_names(record.get("entities"))
    if ents:
        parts.append("实体：" + "、".join(ents[:10]))
    decisions = [
        _clean(d.get("decision"))
        for d in (meeting.get("decisions") or [])[-3:]
        if isinstance(d, dict) and _clean(d.get("decision"))
    ]
    if decisions:
        parts.append("决策：" + "；".join(decisions))
    return " ".join(p for p in parts if p)


def _iter_entries(record: dict[str, Any]) -> Iterator[tuple[int, str, str, str, str]]:
    """从 record 提取摘录条目：(seq, title, at, etype, text)。

    兼容旧档案的 sessions 快照；seq 缺失时按 run_count 回推。
    """
    meeting = record.get("meeting") if isinstance(record.get("meeting"), dict) else {}
    sessions = [
        s for s in (meeting.get("sessions") or []) if isinstance(s, dict)
    ]
    n = len(sessions)
    run_count = int(record.get("run_count") or n or 0)
    for i, session in enumerate(sessions):
        seq = session.get("seq")
        if not (isinstance(seq, int) and seq > 0):
            seq = max(run_count - n + i + 1, i + 1)
        title = _clean(session.get("title")) or _clean(session.get("purpose")) or "历史会议"
        at = _clean(session.get("at"))
        purpose = _clean(session.get("purpose"))
        if purpose:
            yield (seq, title, at, "目的", purpose)
        for topic in session.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            t, c = _clean(topic.get("title")), _clean(topic.get("conclusion"))
            if t:
                yield (seq, title, at, "议题", f"{t}（结论：{c}）" if c else t)
        for text in _str_list(session.get("decisions")):
            yield (seq, title, at, "决策", text)
        for text in _str_list(session.get("open_questions")):
            yield (seq, title, at, "未决", text)
        for text in _str_list(session.get("risks")):
            yield (seq, title, at, "风险", text)


class MemoryEmbedder:
    """记忆向量索引封装（档案级 + 摘录级）。

    用法：``get_embedder()`` 取模块级单例；或直接构造（fake=True 离线测试）。
    所有公开方法在 embedding/chroma 不可用时返回安全空值，绝不抛给上层。
    """

    def __init__(self, persist_dir: str | None = None, fake: bool = False) -> None:
        self.fake = fake
        self._store = None
        try:
            from tools.knowledge.config import KnowledgeToolConfig
            from tools.knowledge.vector_store import VectorStore

            cfg = KnowledgeToolConfig(
                persist_dir=persist_dir or MEMORY_PERSIST_DIR,
                min_score=0.0,  # 阈值由本模块自行判定（MEMORY_EMBED_MIN_SCORE）
            )
            self._store = VectorStore(cfg, fake=fake)
            # 预先探测：get_or_create collection（cosine 空间），失败即降级
            self._coll()
        except Exception as exc:  # noqa: BLE001 - 记忆向量不可用不影响主流程
            logger.warning("记忆向量索引初始化失败，将降级规则匹配: %s", exc)
            self._store = None

    # ── 内部 ──────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return bool(self._store is not None and _embedding_enabled())

    def _coll(self):
        if self._store is None:
            raise RuntimeError("记忆向量索引不可用")
        return self._store.client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    def _upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        if not ids or self._store is None:
            return
        emb = self._store.embedding.embed(texts)
        self._coll().upsert(ids=ids, embeddings=emb, documents=texts, metadatas=metadatas)

    def _record(self, *, ok: bool = True, hits: int = 0, calls: int = 0) -> None:
        try:
            from tools.monitor.side import record_memory_embed

            record_memory_embed(ok=ok, hits=hits, calls=calls)
        except Exception:  # noqa: BLE001
            return

    # ── 写入（persist 后调用）─────────────────────────────────

    def upsert_project(self, user_id: str, domain: str, record: dict[str, Any]) -> None:
        """档案级：项目身份向量（upsert 幂等）。"""
        pid = str(record.get("project_id") or "")
        if not pid:
            return
        doc = _project_document(record)
        if not doc:
            return
        # signals：供检索层规则加权（查询含其中任一子串 → 候选加分）
        aliases = [str(a).strip() for a in (record.get("name_aliases") or []) if str(a).strip()]
        entities = entity_names(record.get("entities"))
        signals = "|".join(
            list(dict.fromkeys(
                [str(record.get("project_key") or ""), *aliases, *entities[:15]]
            ))
        )
        self._upsert(
            [_project_id(domain, user_id, pid)],
            [doc],
            [{
                "owner": user_id,
                "domain": domain,
                "project_id": pid,
                "project_key": str(record.get("project_key") or ""),
                "signals": signals,
                "run_count": int(record.get("run_count") or 0),
                "kind": "project",
            }],
        )

    def upsert_entries(self, user_id: str, domain: str, record: dict[str, Any]) -> None:
        """摘录级：每条历史 目的/议题/决策/未决/风险 一个向量（upsert 幂等）。"""
        pid = str(record.get("project_id") or "")
        if not pid:
            return
        ids: list[str] = []
        texts: list[str] = []
        metas: list[dict] = []
        for seq, title, at, etype, text in _iter_entries(record):
            body = _clean(text)
            if len(body) < 2:
                continue
            ids.append(_entry_id(domain, user_id, pid, seq, etype, body))
            texts.append(f"{etype}：{body}")
            metas.append({
                "owner": user_id,
                "domain": domain,
                "project_id": pid,
                "seq": int(seq),
                "title": title,
                "at": at,
                "etype": etype,
                "kind": "entry",
            })
        self._upsert(ids, texts, metas)

    def sync_record(self, user_id: str, domain: str, record: dict[str, Any]) -> bool:
        """persist 写回 record.json 后同步向量索引。

        先删该项目旧向量（档案级+摘录级），再 upsert 新版本；
        id 确定性 + upsert 保证幂等；失败返回 False（不影响主流程）。
        """
        if not self.enabled:
            return False
        pid = str(record.get("project_id") or "")
        if not pid:
            return False
        try:
            coll = self._coll()
            try:
                got = coll.get(
                    where={"$and": [{"domain": domain}, {"project_id": pid}]},
                    include=[],
                )
                stale = got.get("ids") or []
                if stale:
                    coll.delete(ids=stale)
            except Exception:  # noqa: BLE001 - 删旧失败继续 upsert（幂等覆盖）
                pass
            self.upsert_project(user_id, domain, record)
            self.upsert_entries(user_id, domain, record)
            self._record(ok=True, calls=1)
            logger.info(
                "记忆向量已同步：%s/%s（%s）", user_id, pid, domain
            )
            return True
        except Exception:  # noqa: BLE001 - 向量索引异常不阻断主流程
            logger.warning("记忆向量同步失败，跳过（不影响主流程）", exc_info=True)
            self._record(ok=False)
            return False

    # ── 检索 ──────────────────────────────────────────────────

    def search_projects(
        self, transcript: str, user_id: str, top_k: int | None = None
    ) -> list[dict[str, Any]]:
        """归属语义检索：本次原文 → 档案级向量 top-k（按 owner 行级过滤）。

        规则信号加权（优化 D）：查询文本含某档案 project_key/别名/实体
        （signals 子串命中）→ 该候选 +MEMORY_EMBED_RULE_BOOST 并重新排序，
        救回"实体命中但语义分略低"的漏绑（如 Gradio/记忆引用）。

        返回 [{project_id, project_key, run_count, score}]；不可用返回 []。
        """
        if not self.enabled or not (transcript or "").strip():
            return []
        try:
            rows = self._store.query(
                COLLECTION,
                transcript,
                top_k or MEMORY_EMBED_PROJECT_TOP_K * 2,
                where={"owner": user_id, "kind": "project"},
            )
            out: list[dict[str, Any]] = []
            by_pid: dict[str, dict[str, Any]] = {}
            for row in rows:
                meta = row.get("metadata") or {}
                pid = str(meta.get("project_id") or "")
                if not pid:
                    continue
                item = {
                    "project_id": pid,
                    "project_key": str(meta.get("project_key") or ""),
                    "run_count": int(meta.get("run_count") or 0),
                    "score": float(row.get("score") or 0.0),
                }
                by_pid[pid] = item
                out.append(item)
            # 规则信号加权：扫描该用户全部档案的 signals，子串命中 → 加分
            if out:
                boost = MEMORY_EMBED_RULE_BOOST
                got = self._coll().get(
                    where={"$and": [{"owner": user_id}, {"kind": "project"}]},
                    include=["metadatas"],
                )
                for meta in got.get("metadatas") or []:
                    signals = str(meta.get("signals") or "")
                    pid = str(meta.get("project_id") or "")
                    if not pid or not signals:
                        continue
                    if any(sig and sig in transcript for sig in signals.split("|")):
                        item = by_pid.get(pid)
                        if item is not None:
                            item["score"] = round(item["score"] + boost, 3)
                        else:
                            item = {
                                "project_id": pid,
                                "project_key": str(meta.get("project_key") or ""),
                                "run_count": int(meta.get("run_count") or 0),
                                "score": round(MEMORY_EMBED_MIN_SCORE + boost * 2, 3),
                            }
                            by_pid[pid] = item
                            out.append(item)
                out.sort(key=lambda c: -float(c["score"]))
            self._record(ok=True, hits=len(out), calls=1)
            return out
        except Exception:  # noqa: BLE001
            self._record(ok=False)
            return []

    def search_entries(
        self,
        transcript: str,
        user_id: str,
        project_id: str,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """摘录语义检索：本次原文 → 该项目历史 目的/议题/决策/未决/风险 top-k。

        返回 [{text, seq, title, at, etype, score}]；不可用返回 []。
        """
        if not self.enabled or not (transcript or "").strip() or not project_id:
            return []
        try:
            rows = self._store.query(
                COLLECTION,
                transcript,
                top_k or MEMORY_EMBED_ENTRY_TOP_K,
                where={
                    "owner": user_id,
                    "kind": "entry",
                    "project_id": project_id,
                },
            )
            out: list[dict[str, Any]] = []
            for row in rows:
                meta = row.get("metadata") or {}
                out.append({
                    "text": str(row.get("text") or ""),
                    "seq": int(meta.get("seq") or 0),
                    "title": str(meta.get("title") or ""),
                    "at": str(meta.get("at") or ""),
                    "etype": str(meta.get("etype") or ""),
                    "score": float(row.get("score") or 0.0),
                })
            self._record(ok=True, hits=len(out), calls=1)
            return out
        except Exception:  # noqa: BLE001
            self._record(ok=False)
            return []


_embedder: MemoryEmbedder | None = None
_user_embedders: dict[str, MemoryEmbedder] = {}


def get_embedder(fake: bool = False, user_id: str = "") -> MemoryEmbedder:
    """记忆向量库（懒加载）。

    - 不传 ``user_id``：默认统一库单例（兼容旧路径）
    - 传 ``user_id``：按用户顶层物理隔离（``data/{user_id}/memory/chromadb``），
      每用户一个实例
    """
    uid = (user_id or "").strip()
    if not uid:
        global _embedder
        if _embedder is None:
            _embedder = MemoryEmbedder(fake=fake)
        return _embedder
    key = _project_uid_key(uid)
    if key not in _user_embedders:
        _user_embedders[key] = MemoryEmbedder(
            fake=fake, persist_dir=memory_persist_dir_for_user(uid)
        )
    return _user_embedders[key]


def _project_uid_key(user_id: str) -> str:
    from .store import safe_id

    return safe_id(user_id)


__all__ = [
    "COLLECTION",
    "MEMORY_EMBED_MIN_SCORE",
    "MEMORY_EMBEDDING",
    "MEMORY_PERSIST_DIR",
    "MemoryEmbedder",
    "get_embedder",
]
