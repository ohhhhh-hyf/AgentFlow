"""核心知识点溯源：老师原话优先，再对齐知识库和笔记。不编出处。"""
from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from tools.knowledge.cite import _overlap_score, open_knowledge
from tools.knowledge.source_role import ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER, classify_source_role

from domain.notes.tasks.catalog.gather import subject_from_context, user_id_from_context

from .gather import teacher_from_context
from .select import _as_list, _clean, _compact, _hit_in, _sentences


_EXAM_MARKS = ("必考", "每届必出", "年年有", "一定出", "出大题", "重点", "着重")
_ERROR_MARKS = ("不能", "不要", "陷阱", "反例", "慎", "容易错", "混淆", "误用", "漏")
_METHOD_MARKS = ("方法", "套路", "步骤", "流程", "先判断", "判断流程")
_TYPE_MARKS = ("大题", "选择题", "填空", "证明题", "计算题", "简答", "判断题")


def attach_card_provenance(
    draft: dict[str, Any],
    context: str = "",
    teacher: str = "",
    *,
    collection: str = "",
) -> dict[str, Any]:
    """给 S/A/B 卡片挂 claims + provenance。库空或对不上就留空，不编来源。

    溯源走分层候选池（锚点 → 章节 → 源文件 → 向量 → 全库兜底），
    每张卡记录命中层与候选池大小；汇总统计挂 draft["trace_stats"]。
    """
    cards = [c for c in (draft.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        return draft
    teacher_text = _clean(teacher) or teacher_from_context(context)
    user_id = user_id_from_context(context)
    subject = subject_from_context(context)
    kb = open_knowledge(user_id=user_id)
    chunks = _load_chunks(user_id=user_id, subject=subject)
    indexed = _chunk_index(chunks) if chunks else None
    stats: dict[str, Any] = {
        "layers": {},
        "pool_sizes": [],
        "full_fallback": 0,
        "cards": 0,
        "no_source": 0,
    }
    out: list[dict[str, Any]] = []
    for card in cards:
        if str(card.get("session_priority") or "") == "C":
            out.append(card)
            continue
        traced, meta = _trace_card(
            card, teacher_text, chunks, indexed=indexed, kb=kb, user_id=user_id, subject=subject
        )
        stats["cards"] += 1
        layer = str(meta.get("layer") or "none")
        stats["layers"][layer] = stats["layers"].get(layer, 0) + 1
        stats["pool_sizes"].append(int(meta.get("pool_size") or 0))
        if layer == "full":
            stats["full_fallback"] += 1
        if not traced.get("provenance", {}).get("knowledge_evidence"):
            stats["no_source"] += 1
        out.append(traced)
    draft["cards"] = out
    draft["trace_stats"] = _finalize_trace_stats(stats)
    return draft


def _trace_card(
    card: dict[str, Any],
    teacher: str,
    chunks: list[dict[str, Any]],
    *,
    indexed: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    kb: Any = None,
    user_id: str = "",
    subject: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    next_card = dict(card)
    claims = _build_claims(next_card)
    teachers = _teacher_evidence(next_card, teacher, claims) if teacher else []
    kb_hits, note_hits, meta = _library_evidence(
        next_card, claims, chunks, indexed=indexed, kb=kb, user_id=user_id, subject=subject
    )
    teachers, kb_hits, note_hits = _bind_claims(claims, teachers, kb_hits, note_hits)
    next_card["claims"] = claims
    next_card["provenance"] = {
        "teacher_evidence": teachers,
        "knowledge_evidence": kb_hits,
        "note_evidence": note_hits,
        "evidence_status": _status(teachers, kb_hits, note_hits, next_card),
    }
    return next_card, meta


def _finalize_trace_stats(stats: dict[str, Any]) -> dict[str, Any]:
    pools = [int(x) for x in (stats.get("pool_sizes") or []) if isinstance(x, int) or str(x).isdigit()]
    out = dict(stats)
    out["avg_pool_size"] = round(sum(pools) / len(pools), 2) if pools else 0
    out["max_pool_size"] = max(pools) if pools else 0
    return out


def _build_claims(card: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    idx = 1

    def add(field: str, text: str) -> None:
        nonlocal idx
        body = _clean(text)
        if not body:
            return
        claims.append(
            {
                "claim_id": f"claim_{idx:03d}",
                "field": field,
                "text": body,
                "evidence_ids": [],
            }
        )
        idx += 1

    grade = str(card.get("session_priority") or "")
    if grade in {"S", "A"}:
        add("priority", f"本次列为{_grade_word(grade)}")
    add("exam_prediction", card.get("exam_preview") or "")
    explain = _clean(card.get("explain"))
    if explain:
        for sent in _sentences(explain)[:3] or [explain]:
            add("explanation", sent)
    for step in _as_list(card.get("method_steps"))[:5]:
        add("method_steps", step)
    for pit in _as_list(card.get("pitfalls"))[:4]:
        add("error_warning", pit)
    return claims


def _grade_word(grade: str) -> str:
    return {"S": "核心", "A": "重点", "B": "简要"}.get(grade, "复习点")


def _teacher_evidence(
    card: dict[str, Any],
    teacher: str,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quotes = [_clean(q) for q in _as_list(card.get("session_quotes")) if _quote_belongs(q, card)]
    if not quotes and teacher:
        quotes = _fallback_quotes(card, teacher)
    items = list(dict.fromkeys(_as_list(card.get("knowledge_items")) + _as_list(card.get("session_focus_items"))))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, quote in enumerate(quotes, start=1):
        key = _compact(quote)
        if len(key) < 4 or key in seen:
            continue
        seen.add(key)
        matched = [item for item in items if _hit_in(quote, _compact(quote), item)]
        supports = _teacher_supports(quote, claims)
        out.append(
            {
                "evidence_id": f"teacher_{i:02d}",
                "type": "teacher",
                "label": "老师原话",
                "text": quote,
                "matched_items": matched,
                "supports": supports,
                "strength": _teacher_strength(quote),
            }
        )
        if len(out) >= 5:
            break
    return out


def _quote_belongs(quote: str, card: dict[str, Any]) -> bool:
    text = _clean(quote)
    if len(text) < 6:
        return False
    names = [
        _clean(card.get("name")),
        *_as_list(card.get("aliases")),
        *_as_list(card.get("knowledge_items")),
        *_as_list(card.get("session_focus_items")),
    ]
    return any(_hit_in(text, _compact(text), name) for name in names if len(_clean(name)) >= 2)


def _fallback_quotes(card: dict[str, Any], teacher: str) -> list[str]:
    hits: list[str] = []
    for sent in _sentences(teacher):
        if _quote_belongs(sent, card):
            hits.append(sent)
    return hits[:3]


def _teacher_strength(text: str) -> str:
    if any(mark in text for mark in ("必考", "每届必出", "年年有", "一定出", "务必", "必须")):
        return "strong"
    if any(mark in text for mark in ("重点", "容易错", "不能", "大题")):
        return "strong"
    return "related"


def _teacher_supports(quote: str, claims: list[dict[str, Any]]) -> list[str]:
    supports: list[str] = []
    if any(mark in quote for mark in _EXAM_MARKS):
        supports.extend(["priority", "exam_prediction"])
    if any(mark in quote for mark in _ERROR_MARKS):
        supports.append("error_warning")
    if any(mark in quote for mark in _METHOD_MARKS):
        supports.append("method_steps")
    if any(mark in quote for mark in _TYPE_MARKS) and "exam_prediction" not in supports:
        supports.append("exam_prediction")
    if not supports:
        for claim in claims:
            if _overlap_score(quote, claim.get("text") or "") >= 80:
                field = str(claim.get("field") or "")
                if field and field not in supports:
                    supports.append(field)
        if not supports:
            supports.append("exam_prediction")
    return supports


def _library_evidence(
    card: dict[str, Any],
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    indexed: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    kb: Any = None,
    user_id: str = "",
    subject: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if not chunks:
        return [], [], {"layer": "none", "pool_size": 0}
    if indexed is None:
        indexed = _chunk_index(chunks)  # 独立调用兜底：一次性建索引
    for layer, pool in _candidate_layers(card, indexed, chunks, kb=kb, user_id=user_id, subject=subject):
        if not pool:
            continue
        kb_hits, note_hits = _rank_library_evidence(card, claims, pool, layer=layer)
        if kb_hits or note_hits:
            return kb_hits, note_hits, {"layer": layer, "pool_size": len(pool)}
    return [], [], {"layer": "none", "pool_size": 0}


def _chunk_index(chunks: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """一次性建多键索引：source#heading（L1）/ (chapter, topic)（L2）/ source（L3）。

    同时为每个 chunk 预计算 clean/compact 文本（本批次所有卡共用，
    避免重复正则清洗；向量层召回的 chunk 无预计算字段时按需兜底）。
    """
    by_cid: dict[str, list[dict[str, Any]]] = {}
    by_topic: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_source: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        raw_text = str(chunk.get("text") or "")
        chunk["_clean"] = _clean(raw_text)
        chunk["_compact"] = _compact(chunk["_clean"])
        for key in _as_list(chunk.get("source_chunk_id")):
            cid = _clean(key)
            if cid:
                by_cid.setdefault(cid, []).append(chunk)
        chapter = _compact(_clean(chunk.get("chapter")))
        topic = _compact(_clean(chunk.get("topic")))
        by_topic.setdefault((chapter, topic), []).append(chunk)
        source = str(chunk.get("source") or "")
        if source:
            by_source.setdefault(source, []).append(chunk)
    return {"by_cid": by_cid, "by_topic": by_topic, "by_source": by_source}


def _candidate_layers(
    card: dict[str, Any],
    indexed: dict[str, dict[str, list[dict[str, Any]]]],
    chunks: list[dict[str, Any]],
    *,
    kb: Any = None,
    user_id: str = "",
    subject: str = "",
):
    """分层候选池（只缩小扫描范围，候选仍须过重合校验）：

    L1 source_chunk_ids 精确锚点 → L2 chapter+topic → L3 源文件+标题 →
    L4 向量 topK 召回 → L5 全库（仅当前四层全空时兜底）。
    任一层校验出结果即停；池空或校验无结果降级下一层。
    池按需惰性计算：前层命中时，后续层（尤其向量检索）不执行。
    """
    anchored = _anchored_chunks(card, indexed)
    yield "anchored", anchored
    topic_pool = _topic_chunks(card, indexed)
    yield "chapter_topic", topic_pool
    src_pool = _source_heading_chunks(card, indexed)
    yield "source_heading", src_pool
    vec_pool = _vector_chunks(card, kb, user_id=user_id, subject=subject)
    yield "vector", vec_pool
    if not (anchored or topic_pool or src_pool or vec_pool):
        yield "full", chunks


def _anchored_chunks(
    card: dict[str, Any],
    indexed: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    by_cid = indexed["by_cid"]
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for cid in _as_list(card.get("source_chunk_ids")):
        for chunk in by_cid.get(_clean(cid), []):
            key = (str(chunk.get("source") or ""), _compact(chunk.get("text") or "")[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(chunk)
    return out


def _topic_chunks(
    card: dict[str, Any],
    indexed: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """L2：catalog 的 (chapter, topic) 精确匹配 chunk 的 (chapter, topic)。"""
    chapter = _compact(_clean(card.get("chapter")))
    topic = _compact(_clean(card.get("topic")))
    if not chapter and not topic:
        return []
    pool = []
    if chapter and topic:
        pool = indexed["by_topic"].get((chapter, topic)) or []
    if not pool and chapter:
        pool = indexed["by_topic"].get((chapter, "")) or []
    if not pool and topic:
        pool = indexed["by_topic"].get(("", topic)) or []
    return pool


def _source_heading_chunks(
    card: dict[str, Any],
    indexed: dict[str, dict[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    """L3：卡片 sources 文件内，heading 与 topic/name/aliases 互相包含。"""
    sources = [s for s in _as_list(card.get("sources")) if _clean(s)]
    if not sources:
        return []
    names = [
        _compact(x)
        for x in [_clean(card.get("topic")), _clean(card.get("name")), *_as_list(card.get("aliases"))]
        if _compact(x)
    ]
    if not names:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for src in sources:
        for chunk in indexed["by_source"].get(src, []):
            heading = _compact(_clean(chunk.get("heading")))
            if not heading:
                continue
            if not any(n and (n in heading or heading in n) for n in names):
                continue
            key = (src, _compact(chunk.get("text") or "")[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append(chunk)
    return out


def _vector_chunks(
    card: dict[str, Any],
    kb: Any,
    *,
    user_id: str = "",
    subject: str = "",
) -> list[dict[str, Any]]:
    """L4：向量检索 topK 召回（召回后仍走重合校验，不直接采信）。"""
    if kb is None or not hasattr(kb, "search"):
        return []
    query = _search_query(card)
    if len(_compact(query)) < 6:
        return []
    try:
        hits = kb.search(query, collection="default", top_k=5, user_id=user_id, subject=subject)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for hit in hits or []:
        meta = hit.metadata if isinstance(hit.metadata, dict) else {}
        meta = meta or {}
        text = str(hit.text or "")
        if len(_clean(text)) < 12:
            continue
        source = str(meta.get("source") or "")
        heading = _clean(meta.get("heading") or "")
        role = str(meta.get("role") or "").strip()
        if role not in {ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER}:
            role = classify_source_role(source)
        section = heading
        page = meta.get("page")
        if page not in (None, ""):
            section = f"{section} · 第{page}页" if section else f"第{page}页"
        out.append(
            {
                "text": text,
                "source": source,
                "source_chunk_id": f"{source}#{heading}" if source and heading else source,
                "role": role,
                "section": section,
                "heading": heading,
                "chapter": _clean(meta.get("chapter") or ""),
                "topic": _clean(meta.get("topic") or ""),
            }
        )
    return out


def _rank_library_evidence(
    card: dict[str, Any],
    claims: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    *,
    layer: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    query = _search_query(card)
    query_c = _compact(query)
    name_c = _compact(_clean(card.get("name")))
    item_cs = [
        _compact(item)
        for item in _as_list(card.get("session_focus_items")) + _as_list(card.get("knowledge_items"))
    ]
    claim_texts = [_clean(c.get("text")) for c in claims if _clean(c.get("text"))]
    claim_cs = [_compact(text) for text in claim_texts]
    kb: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    scored: list[tuple[int, dict[str, Any]]] = []
    for chunk in chunks:
        role = str(chunk.get("role") or "")
        if role == ROLE_TEACHER:
            continue
        body = chunk.get("_clean")
        if body is None:
            body = _clean(chunk.get("text"))
        if len(body) < 12:
            continue
        body_c = chunk.get("_compact")
        if body_c is None:
            body_c = _compact(body)
        score = _align_score(query_c, body_c, name_c, item_cs, claim_cs, notes=role == ROLE_NOTES)
        if score < 80:
            continue
        key = (str(chunk.get("source") or ""), body_c[:40])
        if key in seen:
            continue
        seen.add(key)
        supports = _chunk_supports(body, body_c, claims, claim_cs)
        if not supports:
            continue
        item = {
            "type": "knowledge_base" if role != ROLE_NOTES else "student_note",
            "source": str(chunk.get("source") or ""),
            "section": str(chunk.get("section") or ""),
            "excerpt": _excerpt(body, body_c, query_c, limit=90),
            "full": _excerpt(body, body_c, query_c, limit=220),
            "supports": supports,
            "relevance": _relevance(score),
            "score": score,
            "anchor": layer,
        }
        if not item["source"] or not _has_informative_excerpt(item["excerpt"]):
            continue
        scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    kb_i = 1
    note_i = 1
    for _score, item in scored:
        if item["type"] == "student_note":
            if note_i > 3:
                continue
            item["evidence_id"] = f"note_{note_i:02d}"
            note_i += 1
            notes.append(item)
        else:
            if kb_i > 5:
                continue
            item["evidence_id"] = f"kb_{kb_i:02d}"
            kb_i += 1
            kb.append(item)
    return kb, notes


def _search_query(card: dict[str, Any]) -> str:
    parts = [_clean(card.get("name"))]
    parts.extend(_as_list(card.get("session_focus_items"))[:6])
    parts.extend(_as_list(card.get("knowledge_items"))[:6])
    parts.extend(_as_list(card.get("method_steps"))[:3])
    parts.extend(_as_list(card.get("pitfalls"))[:2])
    explain = _clean(card.get("explain"))
    if explain:
        parts.append(explain[:80])
    return " ".join(p for p in parts if p)


def _has_informative_excerpt(text: object) -> bool:
    compact = _compact(str(text or "").replace("…", ""))
    if len(compact) < 6:
        return False
    return bool(re.search(r"[\w\u4e00-\u9fff]", compact))


@lru_cache(maxsize=1024)
def _grams(text: str, size: int) -> frozenset:
    """固定串的 n-gram 集合缓存：同卡片的 query/name/items/claims 只建一次。"""
    return frozenset(text[i : i + size] for i in range(0, len(text) - size + 1))


def _overlap_pre(q: str, e: str) -> int:
    """等价 tools.knowledge.cite._overlap_score，输入须为已 compact 文本。

    预计算版本：同批次多张卡反复比较同一批 chunk 时，避免每次重跑正则 compact；
    q 的 n-gram 集合按 q 缓存，跨 chunk 复用。
    """
    if not q or not e:
        return 0
    if q in e or e in q:
        return 1000 + min(len(q), len(e))
    limit = min(16, len(q), len(e))
    for size in range(limit, 3, -1):
        grams = _grams(q, size)
        hit = sum(1 for gram in grams if gram in e)
        if hit:
            return size * 20 + hit
    return 0


def _align_score(
    query_c: str,
    body_c: str,
    name_c: str,
    item_cs: list[str],
    claim_cs: list[str],
    *,
    notes: bool = False,
) -> int:
    name_score = _overlap_pre(name_c, body_c) if name_c else 0
    item_score = 0
    for item_c in item_cs:
        item_score = max(item_score, _overlap_pre(item_c, body_c))
    claim_score = 0
    for claim_c in claim_cs:
        claim_score = max(claim_score, _overlap_pre(claim_c, body_c))
    query_score = _overlap_pre(query_c, body_c)
    # 必须先对上 KP / Item，避免只靠讲解长句误命中
    if name_score < 60 and item_score < 80:
        return 0
    if notes and name_score < 80 and item_score < 120:
        return 0
    return name_score + item_score + min(200, claim_score) + min(120, query_score)


def _chunk_supports(
    body: str, body_c: str, claims: list[dict[str, Any]], claim_cs: list[str]
) -> list[str]:
    supports: list[str] = []
    for claim, claim_c in zip(claims, claim_cs):
        if _overlap_pre(claim_c, body_c) >= 80:
            field = str(claim.get("field") or "")
            if field and field not in supports:
                supports.append(field)
    if not supports:
        if any(mark in body for mark in _ERROR_MARKS):
            supports.append("error_warning")
        if any(mark in body for mark in _METHOD_MARKS):
            supports.append("method_steps")
        if not supports:
            supports.append("explanation")
    return supports


def _relevance(score: int) -> str:
    if score >= 1400:
        return "high"
    if score >= 400:
        return "mid"
    return "low"


def _excerpt(text: str, body_compact: str, query_compact: str, *, limit: int) -> str:
    body = _clean(text)
    if len(body) <= limit:
        return _safe_math_excerpt(body)
    q = query_compact[:12]
    idx = body_compact.find(q) if len(q) >= 4 else -1
    if idx < 0:
        return _safe_math_excerpt(body[: limit - 1] + "…")
    # 按紧凑串位置回切可见文本
    ratio = idx / max(1, len(body_compact))
    start = max(0, int(len(body) * ratio) - 16)
    clip = body[start : start + limit]
    if start > 0:
        clip = "…" + clip
    if start + limit < len(body):
        clip = clip.rstrip("，。；;、 ") + "…"
    return _safe_math_excerpt(clip)


def _safe_math_excerpt(text: str) -> str:
    """让截断后的溯源片段不把半截公式交给 Markdown/MathJax。"""
    from tools.ocr.mathmd import normalize_markdown_math

    cleaned = re.sub(r"\\[A-Za-z]{0,24}…$", "…", text)
    cleaned = _drop_unclosed_math_tail(cleaned)
    return normalize_markdown_math(cleaned)


def _drop_unclosed_math_tail(text: str) -> str:
    """摘录若截断在 $/$$ 公式内部，删除最后一段未闭合公式。"""
    in_math = False
    open_pos = -1
    open_token = ""
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        token = ""
        if text.startswith("$$", i):
            token = "$$"
        elif text[i] == "$":
            token = "$"
        if not token:
            i += 1
            continue
        if not in_math:
            in_math = True
            open_pos = i
            open_token = token
            i += len(token)
            continue
        if token == open_token or open_token == "$":
            in_math = False
            open_pos = -1
            open_token = ""
        i += len(token)
    if in_math and open_pos >= 0:
        return text[:open_pos].rstrip("，。；;、 ") + "…"
    return text


def _bind_claims(
    claims: list[dict[str, Any]],
    teachers: list[dict[str, Any]],
    kb: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    by_field: dict[str, list[str]] = {}
    for ev in teachers + kb + notes:
        eid = str(ev.get("evidence_id") or "")
        for field in ev.get("supports") or []:
            by_field.setdefault(str(field), []).append(eid)
    for claim in claims:
        field = str(claim.get("field") or "")
        ids = list(dict.fromkeys(by_field.get(field) or []))
        text = claim.get("text") or ""
        ranked: list[str] = []
        for ev in teachers + kb + notes:
            eid = str(ev.get("evidence_id") or "")
            if eid not in ids:
                continue
            if _overlap_score(text, ev.get("text") or ev.get("excerpt") or "") >= 60 or eid.startswith("teacher_"):
                ranked.append(eid)
        claim["evidence_ids"] = ranked[:4] or ids[:3]
    return teachers, kb, notes


def _status(
    teachers: list[dict[str, Any]],
    kb: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    card: dict[str, Any],
) -> str:
    if teachers or kb or notes:
        return "ok"
    strong = str(card.get("session_exam_signal") or "") == "strong" or str(card.get("session_priority") or "") == "S"
    return "insufficient" if strong else "none"


def _load_chunks(user_id: str = "", subject: str = "") -> list[dict[str, Any]]:
    kb = open_knowledge(user_id=user_id)
    if kb is None:
        return []
    try:
        files = kb.list_files(user_id=user_id, subject=subject)
    except Exception:
        files = []
    if not files:
        return []
    try:
        raw = kb.list_chunks(user_id=user_id, subject=subject)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for chunk in raw or []:
        meta = chunk.get("metadata") if isinstance(chunk, dict) else {}
        meta = meta or {}
        source = str(meta.get("source") or "")
        role = str(meta.get("role") or "").strip()
        if role not in {ROLE_MATERIAL, ROLE_NOTES, ROLE_TEACHER}:
            role = classify_source_role(source)
        section_base = _clean(meta.get("heading") or meta.get("topic") or meta.get("chapter") or "")
        section = section_base
        page = meta.get("page")
        if page not in (None, ""):
            section = f"{section} · 第{page}页" if section else f"第{page}页"
        out.append(
            {
                "text": str(chunk.get("text") or ""),
                "source": source,
                "source_chunk_id": f"{source}#{section_base}" if source and section_base else "",
                "role": role,
                "section": section,
                "heading": section_base,
                "chapter": _clean(meta.get("chapter") or ""),
                "topic": _clean(meta.get("topic") or ""),
            }
        )
    return out
