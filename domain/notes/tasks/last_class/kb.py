"""last_class —— 知识库检索层。

从 display.py 拆出：集合解析、检索、专题文件命中、来源排序/折叠。
本模块自包含公共小工具（_clean/_soft_clean/_as_list/_is_raw_dump 等），
display.py 单向依赖本模块，避免循环 import。
"""
from __future__ import annotations

import re
from typing import Any

from tools.knowledge.cite import open_knowledge
from tools.knowledge.tool import collection_for


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _soft_clean(text: object) -> str:
    """保留换行，只收每行内部空白，方便还原对照表。"""
    lines: list[str] = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


_DUMP_MARKS = (
    "题型-方法对照",
    "考前自测清单",
    "能否默写全部",
    "能否用 ε-N",
    "能否用 ε-δ",
)


def _is_raw_dump(text: str) -> bool:
    raw = text or ""
    if raw.count("|") >= 6:
        return True
    return any(mark in raw for mark in _DUMP_MARKS)


def _strip_dump_tail(text: str) -> str:
    """精讲正文里不要粘对照表/自测清单；这些完整放到右侧出处。"""
    out = text or ""
    for mark in (
        "对照材料里的写法",
        "题型-方法对照",
        "考前自测清单",
        "| 题型 |",
        "|题型|",
    ):
        idx = out.find(mark)
        if idx >= 0:
            out = out[:idx]
    if out.count("|") >= 6:
        out = out.split("|", 1)[0]
    out = re.sub(r"（?\d+\.\d+）?。?$", "", _clean(out))
    return out.rstrip("。；;…")


# ── 集合解析与知识库句柄 ──────────────────────────────────────

_KB_CACHE: Any = None
_KB_READY = False


def _kb() -> Any:
    global _KB_CACHE, _KB_READY
    if not _KB_READY:
        _KB_READY = True
        _KB_CACHE = open_knowledge()
    return _KB_CACHE


def _collection_has_files(kb: Any, name: str) -> bool:
    if kb is None or not name:
        return False
    try:
        return bool(kb.list_files(name))
    except Exception:
        return False


def resolve_collection(user_id: str = "", subject: str = "", hinted: str = "") -> str:
    """对准入库时的集合：优先 user__subject；学科对得上也可回退。"""
    preferred = [collection_for(user_id=user_id, subject=subject)]
    if hinted:
        preferred.append(hinted.strip())
    if subject:
        preferred.append(subject.strip())
    kb = _kb()
    for name in preferred:
        if name and _collection_has_files(kb, name):
            return name
    if kb is None:
        return preferred[0] if preferred else "default"
    subject = (subject or "").strip()
    try:
        cols = kb.list_collections() or []
    except Exception:
        cols = []
    names = [c.get("name") if isinstance(c, dict) else str(c) for c in cols]
    if subject:
        for name in names:
            if name == subject or name.endswith("__" + subject):
                if _collection_has_files(kb, name):
                    return name
    return preferred[0] if preferred else "default"


# ── 基础检索 ──────────────────────────────────────────────────

_NOTE_EXT = {".txt", ".md"}
_PPT_EXT = {".pptx", ".ppt", ".ppsx"}
_DOC_EXT = {".docx", ".doc"}


def _ext_of(filename: str) -> str:
    """返回带点扩展名（如 .pptx），与 _NOTE_EXT/_PPT_EXT/_DOC_EXT 一致。"""
    name = filename or ""
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _bucket_of(filename: str) -> str:
    ext = _ext_of(filename)
    if ext in _NOTE_EXT:
        return "notes"
    if ext in _PPT_EXT:
        return "slides"
    if ext in _DOC_EXT:
        return "docs"
    return "notes"


def _retrieve(collection: str, query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """在指定 collection 检索，返回 [{file, page, excerpt, score}]。"""
    if not (query or "").strip():
        return []
    kb = _kb()
    if kb is None:
        return []
    try:
        hits = kb.locate(query, collection=collection, top_k=top_k)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for hit in hits or []:
        meta = getattr(hit, "metadata", None) or (hit.get("metadata") if isinstance(hit, dict) else None) or {}
        text = getattr(hit, "text", "") or (hit.get("text") if isinstance(hit, dict) else "") or ""
        score = getattr(hit, "score", 0.0) or (hit.get("score") if isinstance(hit, dict) else 0.0) or 0.0
        fname = str(meta.get("source") or "")
        if not fname:
            continue
        out.append(
            {
                "file": fname,
                "page": str(meta.get("page") or ""),
                "excerpt": _soft_clean(text),
                "score": float(score),
            }
        )
    return out


# ── 考点检索词 ────────────────────────────────────────────────

_WEAK_TOPIC = {
    "替换", "求极限", "一般方法", "分类", "概念", "辨析", "定义", "证明",
    "性质", "运算", "准则", "方法", "内容", "问题",
}


def _topic_tokens(point: dict[str, Any]) -> list[str]:
    """考点名拆成可对文件名/摘录的短词，便于命中专题课件和讲义。"""
    tokens: list[str] = []
    name = _clean(point.get("name"))
    if name:
        tokens.append(name)
        base = re.sub(r"（[^）]*）|\([^)]*\)", "", name).strip()
        if base:
            tokens.append(base)
        tokens.extend(
            part
            for part in re.split(r"[与和及、/（）() ]+", name)
            if len(part) >= 4 and part not in _WEAK_TOPIC
        )
    tokens.extend(_as_list(point.get("keywords")))
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        key = token.replace(" ", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def _retrieve_topic_files(collection: str, point: dict[str, Any]) -> list[dict[str, Any]]:
    """文件名对得上考点的专题课件/讲义，直接按文件取块，避免被总述笔记挤掉。"""
    kb = _kb()
    if kb is None:
        return []
    try:
        files = kb.list_files(collection) or []
    except Exception:
        return []
    tokens = [
        re.sub(r"[\s_\-]", "", token)
        for token in _topic_tokens(point)
        if len(re.sub(r"[\s_\-]", "", token)) >= 4
    ]
    if not tokens:
        return []
    hits: list[dict[str, Any]] = []
    for fname in files:
        compact = re.sub(r"[\s_\-]", "", str(fname))
        if not any(token in compact for token in tokens):
            continue
        try:
            chunks = kb.list_chunks(collection, filename=str(fname)) or []
        except Exception:
            chunks = []
        for chunk in chunks[:8]:
            if not isinstance(chunk, dict):
                continue
            meta = chunk.get("metadata") or {}
            text = _soft_clean(chunk.get("text"))
            if not text:
                continue
            hits.append(
                {
                    "file": str(fname),
                    "page": str(meta.get("page") or ""),
                    "excerpt": text,
                    "score": 1.0,
                }
            )
    return hits


def _on_topic(point: dict[str, Any], item: dict[str, Any]) -> bool:
    blob = f"{item.get('file') or ''} {item.get('excerpt') or ''}"
    compact = re.sub(r"\s+", "", blob)
    for token in _topic_tokens(point):
        key = re.sub(r"\s+", "", token)
        if len(key) >= 4 and (token in blob or key in compact):
            return True
    return False


# ── 来源排序 / 折叠 ───────────────────────────────────────────

_GENERIC_HEADS = (
    "本笔记系统覆盖",
    "期末复习总览",
    "考前自测清单",
    "必会题型",
    "高频考点",
)


def _source_relevance(point: dict[str, Any], item: dict[str, Any]) -> float:
    """专题文件名优先，其次摘录对题，总览段往后排。"""
    file = _clean(item.get("file") or "")
    excerpt = _clean(item.get("excerpt") or "")
    stem = file.rsplit(".", 1)[0] if "." in file else file
    compact_file = re.sub(r"[\s_\-]", "", stem)
    compact_excerpt = excerpt.replace(" ", "")
    score = float(item.get("score") or 0.0)
    for needle in _topic_tokens(point):
        compact = re.sub(r"[\s_\-]", "", needle)
        if not compact:
            continue
        if compact in compact_file or needle in file:
            score += 40 + min(len(compact), 16)
        if needle in excerpt or compact in compact_excerpt:
            score += 16 + min(len(compact), 12)
            continue
        parts = [p for p in re.split(r"[/、，,（）()；;：: ]+", needle) if len(p) >= 2]
        score += sum(3 for part in parts if part in excerpt or part in file)
    head = excerpt[:120]
    if any(tag in head for tag in _GENERIC_HEADS):
        score -= 18
    return score


def _rank_kb_sources(
    point: dict[str, Any],
    sources: dict[str, list[dict]] | None,
) -> list[tuple[float, str, dict[str, Any]]]:
    """按相关度排序，同文件去重，每种来源最多留两条。"""
    rows: list[tuple[float, str, dict[str, Any]]] = []
    for label, key in (("笔记", "notes"), ("课件", "slides"), ("文档", "docs")):
        for item in (sources or {}).get(key, []):
            if not _clean(item.get("excerpt")) and not item.get("file"):
                continue
            rows.append((_source_relevance(point, item), label, item))
    rows.sort(key=lambda row: -row[0])
    topical = [row for row in rows if _on_topic(point, row[2])]
    rows = topical or rows
    seen: set[tuple[str, str]] = set()
    file_count: dict[str, int] = {}
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for score, label, item in rows:
        file = str(item.get("file") or "")
        excerpt = _clean(item.get("excerpt"))[:48]
        key = (file, excerpt)
        if key in seen or file_count.get(file, 0) >= 2:
            continue
        seen.add(key)
        file_count[file] = file_count.get(file, 0) + 1
        ranked.append((score, label, item))
    return ranked[:8]


def _filename_hit(point: dict[str, Any], item: dict[str, Any]) -> bool:
    compact = re.sub(r"[\s_\-]", "", str(item.get("file") or ""))
    return any(
        re.sub(r"[\s_\-]", "", token) in compact
        for token in _topic_tokens(point)
        if len(re.sub(r"[\s_\-]", "", token)) >= 4
    )


def _pick_visible_kb(
    point: dict[str, Any],
    ranked: list[tuple[float, str, dict[str, Any]]],
    visible: int = 3,
) -> tuple[list[tuple[float, str, dict[str, Any]]], list[tuple[float, str, dict[str, Any]]]]:
    """前排展开：最相关 + 不同类型专题文件，其余折叠。"""
    if not ranked:
        return [], []
    rest = sorted(
        ranked[1:],
        key=lambda row: (_filename_hit(point, row[2]), row[0]),
        reverse=True,
    )
    picked: list[tuple[float, str, dict[str, Any]]] = [ranked[0]]
    used_types = {ranked[0][1]}
    used_ids = {id(ranked[0][2])}
    for row in rest:
        if len(picked) >= visible:
            break
        if row[1] in used_types:
            continue
        picked.append(row)
        used_types.add(row[1])
        used_ids.add(id(row[2]))
    for row in ranked[1:]:
        if len(picked) >= visible:
            break
        if id(row[2]) in used_ids:
            continue
        picked.append(row)
        used_ids.add(id(row[2]))
    extra = [row for row in ranked if id(row[2]) not in used_ids]
    return picked, extra


# ── 考点级聚合检索 ────────────────────────────────────────────

def _retrieve_point(collection: str, point: dict[str, Any]) -> dict[str, list[dict]]:
    """用检索词 + 名称 + 老师原话检索，按来源类型分组去重。

    兜底检索：keywords 为空或首轮全未命中时，从知识点名提取候选词
    （去掉括注的正式名 + 括号内别名），并用更大 top_k 再检索一次。
    返回 {"notes": [...], "slides": [...], "docs": [...], "all": [...]}
    """
    queries = list(_topic_tokens(point))
    name = _clean(point.get("name"))
    quote = _clean(point.get("quote"))
    if quote:
        queries.append(quote)
    buckets: dict[str, dict[str, dict[str, Any]]] = {
        "notes": {}, "slides": {}, "docs": {}
    }

    def _collect(q: str, top_k: int) -> None:
        for item in _retrieve(collection, q, top_k=top_k):
            key = (item["file"], item["page"], item["excerpt"][:24])
            prev = buckets[_bucket_of(item["file"])].get(key)
            if prev is None or float(item.get("score") or 0) > float(prev.get("score") or 0):
                buckets[_bucket_of(item["file"])][key] = item

    for q in queries:
        if not (q or "").strip():
            continue
        _collect(q, top_k=6)

    for item in _retrieve_topic_files(collection, point):
        key = (item["file"], item["page"], item["excerpt"][:24])
        prev = buckets[_bucket_of(item["file"])].get(key)
        if prev is None or float(item.get("score") or 0) > float(prev.get("score") or 0):
            buckets[_bucket_of(item["file"])][key] = item

    # 兜底：首轮全未命中且知识点名可用时，用名称更大召回再查一次
    if not any(buckets[b] for b in buckets) and name:
        _collect(name, top_k=8)

    ranked = {
        "notes": sorted(buckets["notes"].values(), key=lambda x: -_source_relevance(point, x))[:5],
        "slides": sorted(buckets["slides"].values(), key=lambda x: -_source_relevance(point, x))[:5],
        "docs": sorted(buckets["docs"].values(), key=lambda x: -_source_relevance(point, x))[:5],
    }
    ranked["all"] = sorted(
        [v for key in ("notes", "slides", "docs") for v in ranked[key]],
        key=lambda x: -_source_relevance(point, x),
    )[:8]
    return ranked


def _knowledge_blurb(
    point: dict[str, Any],
    sources: dict[str, list[dict]],
) -> dict[str, Any] | None:
    """知识描述：选最贴近当前考点的知识块，避免拿总述段当精讲。"""
    candidates = [v for key in ("docs", "slides", "notes") for v in sources.get(key, [])]
    usable = [
        item
        for item in candidates
        if _clean(item.get("excerpt")) and not _is_raw_dump(str(item.get("excerpt") or ""))
    ]
    pool = usable or [item for item in candidates if _clean(item.get("excerpt"))]
    if not pool:
        return None
    return max(pool, key=lambda item: _source_relevance(point, item))


__all__ = [
    "_as_list",
    "_clean",
    "_is_raw_dump",
    "_knowledge_blurb",
    "_on_topic",
    "_pick_visible_kb",
    "_rank_kb_sources",
    "_retrieve_point",
    "_retrieve_topic_files",
    "_soft_clean",
    "_source_relevance",
    "_strip_dump_tail",
    "_topic_tokens",
    "resolve_collection",
]
