"""核心知识点溯源：老师原话优先，再对齐知识库和笔记。不编出处。"""
from __future__ import annotations

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
    """给 S/A/B 卡片挂 claims + provenance。库空或对不上就留空，不编来源。"""
    cards = [c for c in (draft.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        return draft
    teacher_text = _clean(teacher) or teacher_from_context(context)
    user_id = user_id_from_context(context)
    subject = subject_from_context(context)
    chunks = _load_chunks(user_id=user_id, subject=subject)
    catalog_evidence = _load_catalog_evidence(user_id=user_id, subject=subject)
    out: list[dict[str, Any]] = []
    for card in cards:
        if str(card.get("session_priority") or "") == "C":
            out.append(card)
            continue
        out.append(_trace_card(card, teacher_text, chunks, catalog_evidence=catalog_evidence))
    draft["cards"] = out
    return draft


def _load_catalog_evidence(user_id: str = "", subject: str = "") -> dict[str, list[str]]:
    """从 catalog 加载每个 KP 的 evidence（建目录时标注的来源依据）。

    返回 {kp_name: [evidence, ...]}。catalog 不可用/无 subject 时返回空。
    """
    if not (user_id or "").strip() or not (subject or "").strip():
        return {}
    try:
        from domain.notes.tasks.catalog.store import load_catalog

        catalog = load_catalog(user_id=user_id, subject=subject)
    except Exception:  # noqa: BLE001
        return {}
    if not catalog:
        return {}
    out: dict[str, list[str]] = {}
    for ch in catalog.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            for kp in tp.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                name = str(kp.get("name") or "").strip()
                evs = [str(e).strip() for e in (kp.get("evidence") or []) if str(e or "").strip()]
                if name and evs:
                    out.setdefault(name, []).extend(evs)
    return out


def _trace_card(
    card: dict[str, Any],
    teacher: str,
    chunks: list[dict[str, Any]],
    *,
    catalog_evidence: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    next_card = dict(card)
    claims = _build_claims(next_card)
    teachers = _teacher_evidence(next_card, teacher, claims) if teacher else []
    kb_hits, note_hits = _library_evidence(next_card, claims, chunks)
    teachers, kb_hits, note_hits = _bind_claims(claims, teachers, kb_hits, note_hits)
    # catalog 依据兜底：卡片内容匹配不到知识库原文时，用 KP 建目录时标注的 evidence
    if not (teachers or kb_hits or note_hits) and catalog_evidence:
        name = str(next_card.get("name") or "").strip()
        evs = catalog_evidence.get(name) or []
        if not evs:
            for alias in _as_list(next_card.get("aliases")) + _as_list(next_card.get("knowledge_items")):
                if alias and catalog_evidence.get(str(alias)):
                    evs = catalog_evidence.get(str(alias))
                    break
        for text in evs[:3]:
            kb_hits.append(
                {
                    "evidence_id": f"catalog_{len(kb_hits) + 1:02d}",
                    "type": "catalog",
                    "label": "目录依据",
                    "text": str(text)[:200],
                    "supports": [c["claim_id"] for c in claims[:2]],
                    "strength": 2,
                }
            )
    next_card["claims"] = claims
    next_card["provenance"] = {
        "teacher_evidence": teachers,
        "knowledge_evidence": kb_hits,
        "note_evidence": note_hits,
        "evidence_status": _status(teachers, kb_hits, note_hits, next_card),
    }
    return next_card


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not chunks:
        return [], []
    query = _search_query(card)
    claim_texts = [_clean(c.get("text")) for c in claims if _clean(c.get("text"))]
    kb: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    scored: list[tuple[int, dict[str, Any]]] = []
    for chunk in chunks:
        role = str(chunk.get("role") or "")
        if role == ROLE_TEACHER:
            continue
        body = _clean(chunk.get("text"))
        if len(body) < 12:
            continue
        score = _align_score(query, body, card, claim_texts, notes=role == ROLE_NOTES)
        if score < 80:
            continue
        key = (str(chunk.get("source") or ""), _compact(body)[:40])
        if key in seen:
            continue
        seen.add(key)
        supports = _chunk_supports(body, claims)
        if not supports:
            continue
        item = {
            "type": "knowledge_base" if role != ROLE_NOTES else "student_note",
            "source": str(chunk.get("source") or ""),
            "section": str(chunk.get("section") or ""),
            "excerpt": _excerpt(body, query, limit=90),
            "full": _excerpt(body, query, limit=220),
            "supports": supports,
            "relevance": _relevance(score),
            "score": score,
        }
        if not item["source"]:
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


def _align_score(
    query: str,
    body: str,
    card: dict[str, Any],
    claim_texts: list[str],
    *,
    notes: bool = False,
) -> int:
    name = _clean(card.get("name"))
    name_score = _overlap_score(name, body) if name else 0
    item_score = 0
    for item in _as_list(card.get("session_focus_items")) + _as_list(card.get("knowledge_items")):
        item_score = max(item_score, _overlap_score(item, body))
    claim_score = 0
    for text in claim_texts:
        claim_score = max(claim_score, _overlap_score(text, body))
    query_score = _overlap_score(query, body)
    # 必须先对上 KP / Item，避免只靠讲解长句误命中
    if name_score < 60 and item_score < 80:
        return 0
    if notes and name_score < 80 and item_score < 120:
        return 0
    return name_score + item_score + min(200, claim_score) + min(120, query_score)


def _chunk_supports(body: str, claims: list[dict[str, Any]]) -> list[str]:
    supports: list[str] = []
    for claim in claims:
        if _overlap_score(claim.get("text") or "", body) >= 80:
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


def _excerpt(text: str, query: str, *, limit: int) -> str:
    body = _clean(text)
    if len(body) <= limit:
        return body
    q = _compact(query)[:12]
    compact = _compact(body)
    idx = compact.find(q) if len(q) >= 4 else -1
    if idx < 0:
        return body[: limit - 1] + "…"
    # 按紧凑串位置回切可见文本
    ratio = idx / max(1, len(compact))
    start = max(0, int(len(body) * ratio) - 16)
    clip = body[start : start + limit]
    if start > 0:
        clip = "…" + clip
    if start + limit < len(body):
        clip = clip.rstrip("，。；;、 ") + "…"
    return clip


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
        section = _clean(meta.get("heading") or meta.get("topic") or meta.get("chapter") or "")
        page = meta.get("page")
        if page not in (None, ""):
            section = f"{section} · 第{page}页" if section else f"第{page}页"
        out.append(
            {
                "text": str(chunk.get("text") or ""),
                "source": source,
                "role": role,
                "section": section,
            }
        )
    return out
