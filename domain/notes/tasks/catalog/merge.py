"""把本次 LLM 目录合并进已有目录：复用 ID，旧章不丢，证据追加。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_COVERAGE_RANK = {"none": 0, "mentioned": 1, "partial": 2, "detailed": 3}
_EXAM_RANK = {"none": 0, "weak": 1, "medium": 2, "strong": 3}
_EMPHASIS_RANK = {"0": 0, "1": 1, "2": 2, "3": 3}
_PRACTICE = {
    "recall",
    "distinguish",
    "calculate",
    "prove",
    "apply",
    "choose_method",
    "mixed",
}
_CRITERIA = {
    "can_recall",
    "can_explain",
    "can_distinguish",
    "can_apply",
    "can_choose_method",
    "can_solve_standard",
    "can_solve_variant",
    "can_prove",
}
_ROLES = {
    "foundation",
    "core_concept",
    "core_method",
    "application",
    "integration",
}
_RISKS = {
    "condition_check",
    "concept_confusion",
    "formula_misuse",
    "method_selection",
    "calculation_error",
    "proof_format",
    "boundary_case",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_clean(x) for x in value if _clean(x)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _enum_list(value: object, allowed: set[str]) -> list[str]:
    return [item for item in _uniq(_as_list(value)) if item in allowed]


def _uniq(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.replace(" ", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _names_of(node: dict[str, Any]) -> set[str]:
    names = {_clean(node.get("name"))}
    names.update(_as_list(node.get("aliases")))
    return {n for n in names if n}


def _next_id(prefix: str, used: set[str]) -> str:
    seq = 1
    while True:
        candidate = f"{prefix}_{seq:03d}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        seq += 1


def _match_node(incoming: dict[str, Any], existing_nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    iid = _clean(incoming.get("id"))
    if iid:
        for node in existing_nodes:
            if _clean(node.get("id")) == iid:
                return node
    names = _names_of(incoming)
    if not names:
        return None
    for node in existing_nodes:
        if _names_of(node) & names:
            return node
    return None


def _max_rank(old: str, new: str, ranks: dict[str, int], default: str) -> str:
    old_v = old if old in ranks else default
    new_v = new if new in ranks else default
    return old_v if ranks[old_v] >= ranks[new_v] else new_v


def _merge_point(old: dict[str, Any], new: dict[str, Any], stamp: str) -> tuple[dict[str, Any], bool]:
    merged = dict(old)
    changed = False

    def put_list(key: str) -> None:
        nonlocal changed
        combined = _uniq(_as_list(old.get(key)) + _as_list(new.get(key)))
        if combined != _as_list(old.get(key)):
            changed = True
        merged[key] = combined

    new_name = _clean(new.get("name"))
    old_name = _clean(old.get("name"))
    if new_name and new_name != old_name:
        merged["name"] = new_name
        merged["aliases"] = _uniq(_as_list(old.get("aliases")) + _as_list(new.get("aliases")) + [old_name])
        changed = True
    else:
        put_list("aliases")

    put_list("knowledge_items")
    put_list("teacher_focus_items")
    put_list("note_covered_items")
    put_list("note_missing_items")
    put_list("prerequisites")
    put_list("sources")
    put_list("evidence")
    put_list("source_documents")

    for key, allowed in (
        ("practice_type", _PRACTICE),
        ("completion_criteria", _CRITERIA),
        ("risk_tags", _RISKS),
    ):
        combined = _enum_list(list(_as_list(old.get(key))) + list(_as_list(new.get(key))), allowed)
        if combined != _enum_list(old.get(key), allowed):
            changed = True
        merged[key] = combined
    old_role = str(old.get("learning_role") or "").strip()
    new_role = str(new.get("learning_role") or "").strip()
    if old_role in _ROLES:
        merged["learning_role"] = old_role
    elif new_role in _ROLES:
        merged["learning_role"] = new_role
        changed = True
    else:
        merged["learning_role"] = old_role or ""

    old_rel = old.get("related_points") or []
    new_rel = new.get("related_points") or []
    rel_seen: set[tuple[str, str]] = set()
    rel_out: list[dict[str, str]] = []
    for item in list(old_rel) + list(new_rel):
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        rel = str(item.get("relation") or "used_with")
        key = (name, rel)
        if not name or key in rel_seen:
            continue
        rel_seen.add(key)
        rel_out.append({"name": name, "relation": rel})
    if rel_out != (old.get("related_points") or []):
        changed = True
    merged["related_points"] = rel_out

    merged["teacher_emphasis"] = _max_rank(
        str(old.get("teacher_emphasis") or "0"),
        str(new.get("teacher_emphasis") or "0"),
        _EMPHASIS_RANK,
        "0",
    )
    if merged["teacher_emphasis"] != str(old.get("teacher_emphasis") or "0"):
        changed = True
    merged["exam_signal"] = _max_rank(
        str(old.get("exam_signal") or "none"),
        str(new.get("exam_signal") or "none"),
        _EXAM_RANK,
        "none",
    )
    if merged["exam_signal"] != str(old.get("exam_signal") or "none"):
        changed = True
    new_cov = str(new.get("note_coverage") or "")
    old_cov = str(old.get("note_coverage") or "none")
    if new_cov in _COVERAGE_RANK and _COVERAGE_RANK[new_cov] >= _COVERAGE_RANK.get(old_cov, 0):
        if new_cov != old_cov:
            changed = True
        merged["note_coverage"] = new_cov

    # importance / difficulty / 类型：增量时保持旧值，避免每次重评
    merged["importance"] = old.get("importance") or new.get("importance")
    merged["difficulty"] = old.get("difficulty") or new.get("difficulty")
    merged["foundational_level"] = old.get("foundational_level") or new.get("foundational_level")
    merged["knowledge_type"] = old.get("knowledge_type") or new.get("knowledge_type")

    if changed:
        merged["updated_at"] = stamp
        merged["change_type"] = "updated"
    else:
        merged["change_type"] = "unchanged"
    merged["node_status"] = str(old.get("node_status") or "active")
    merged["id"] = _clean(old.get("id"))
    merged["created_at"] = _clean(old.get("created_at")) or stamp
    return merged, changed


def _fresh_point(point: dict[str, Any], kid: str, stamp: str) -> dict[str, Any]:
    out = dict(point)
    out["id"] = kid
    out["created_at"] = stamp
    out["updated_at"] = stamp
    out["node_status"] = "active"
    out["change_type"] = "added"
    out["source_documents"] = _as_list(point.get("source_documents"))
    out["practice_type"] = _enum_list(point.get("practice_type"), _PRACTICE)
    out["completion_criteria"] = _enum_list(point.get("completion_criteria"), _CRITERIA)
    role = str(point.get("learning_role") or "").strip()
    out["learning_role"] = role if role in _ROLES else ""
    out["risk_tags"] = _enum_list(point.get("risk_tags"), _RISKS)
    return out


def merge_catalog(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    """有历史目录就增量合并；没有则当作首次生成。"""
    stamp = _now()
    incoming = dict(incoming or {})
    if not existing or not (existing.get("chapters") or existing.get("course")):
        result = _assign_tree_ids(incoming, used_ch=set(), used_tp=set(), used_kp=set(), stamp=stamp, first=True)
        result["version"] = "1"
        result["mode"] = "build"
        result["course"] = _clean(incoming.get("course")) or _clean(existing.get("course") if existing else "") or "课程知识目录"
        result.update(_empty_changes())
        result["added_chapters"] = [_clean(ch.get("name")) for ch in result.get("chapters") or [] if _clean(ch.get("name"))]
        result["added_knowledge_points"] = [
            _clean(p.get("name"))
            for ch in result.get("chapters") or []
            for tp in ch.get("topics") or []
            for p in tp.get("knowledge_points") or []
            if _clean(p.get("name"))
        ]
        result["unmatched_content"] = _as_list(incoming.get("unmatched_content"))
        result["uncertain_nodes"] = _as_list(incoming.get("uncertain_nodes"))
        return result

    used_ch, used_tp, used_kp = _collect_ids(existing)
    merged_chapters: list[dict[str, Any]] = []
    changes = _empty_changes()
    incoming_chapters = [c for c in (incoming.get("chapters") or []) if isinstance(c, dict)]
    old_chapters = [c for c in (existing.get("chapters") or []) if isinstance(c, dict)]
    consumed_old: set[int] = set()

    for new_ch in incoming_chapters:
        old_ch = _match_node(new_ch, [c for i, c in enumerate(old_chapters) if i not in consumed_old])
        if old_ch is None:
            built = _assign_chapter(new_ch, used_ch, used_tp, used_kp, stamp, first=False)
            built["change_type"] = "added"
            merged_chapters.append(built)
            changes["added_chapters"].append(_clean(built.get("name")))
            for tp in built.get("topics") or []:
                changes["added_topics"].append(_clean(tp.get("name")))
                for p in tp.get("knowledge_points") or []:
                    changes["added_knowledge_points"].append(_clean(p.get("name")))
            continue
        consumed_old.add(old_chapters.index(old_ch))
        merged_ch, ch_changes = _merge_chapter(old_ch, new_ch, used_tp, used_kp, stamp)
        merged_chapters.append(merged_ch)
        _extend_changes(changes, ch_changes)

    for i, old_ch in enumerate(old_chapters):
        if i in consumed_old:
            continue
        kept = dict(old_ch)
        kept["change_type"] = "unchanged"
        merged_chapters.append(kept)

    try:
        version = int(str(existing.get("version") or "1"))
    except ValueError:
        version = 1
    result = {
        "course": _clean(existing.get("course")) or _clean(incoming.get("course")) or "课程知识目录",
        "version": str(version + 1),
        "mode": "incremental_update",
        "chapters": merged_chapters,
        "unmatched_content": _uniq(
            _as_list(existing.get("unmatched_content")) + _as_list(incoming.get("unmatched_content"))
        ),
        "uncertain_nodes": _as_list(incoming.get("uncertain_nodes")),
        **changes,
    }
    return result


def _empty_changes() -> dict[str, list[str]]:
    return {
        "added_chapters": [],
        "added_topics": [],
        "added_knowledge_points": [],
        "updated_knowledge_points": [],
        "merged_nodes": [],
    }


def _extend_changes(dst: dict[str, list[str]], src: dict[str, list[str]]) -> None:
    for key, values in src.items():
        dst.setdefault(key, []).extend(values)


def _collect_ids(catalog: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    ch, tp, kp = set(), set(), set()
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        if _clean(chapter.get("id")):
            ch.add(_clean(chapter.get("id")))
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            if _clean(topic.get("id")):
                tp.add(_clean(topic.get("id")))
            for point in topic.get("knowledge_points") or []:
                if isinstance(point, dict) and _clean(point.get("id")):
                    kp.add(_clean(point.get("id")))
    return ch, tp, kp


def _assign_tree_ids(
    catalog: dict[str, Any],
    *,
    used_ch: set[str],
    used_tp: set[str],
    used_kp: set[str],
    stamp: str,
    first: bool,
) -> dict[str, Any]:
    out = dict(catalog)
    chapters = []
    for chapter in catalog.get("chapters") or []:
        if isinstance(chapter, dict):
            chapters.append(_assign_chapter(chapter, used_ch, used_tp, used_kp, stamp, first))
    out["chapters"] = chapters
    return out


def _assign_chapter(
    chapter: dict[str, Any],
    used_ch: set[str],
    used_tp: set[str],
    used_kp: set[str],
    stamp: str,
    first: bool,
) -> dict[str, Any]:
    out = dict(chapter)
    cid = _clean(chapter.get("id"))
    if not cid or cid in used_ch:
        cid = _next_id("ch", used_ch)
    else:
        used_ch.add(cid)
    out["id"] = cid
    out["created_at"] = _clean(chapter.get("created_at")) or stamp
    out["updated_at"] = stamp
    out["node_status"] = str(chapter.get("node_status") or "active")
    out["change_type"] = "added" if not first else "added"
    out["source_documents"] = _as_list(chapter.get("source_documents"))
    topics = []
    for topic in chapter.get("topics") or []:
        if isinstance(topic, dict):
            topics.append(_assign_topic(topic, used_tp, used_kp, stamp, first, _clean(out.get("name"))))
    out["topics"] = topics
    return out


def _assign_topic(
    topic: dict[str, Any],
    used_tp: set[str],
    used_kp: set[str],
    stamp: str,
    first: bool,
    chapter_name: str,
) -> dict[str, Any]:
    out = dict(topic)
    tid = _clean(topic.get("id"))
    if not tid or tid in used_tp:
        tid = _next_id("tp", used_tp)
    else:
        used_tp.add(tid)
    out["id"] = tid
    out["change_type"] = "added"
    points = []
    for point in topic.get("knowledge_points") or []:
        if not isinstance(point, dict):
            continue
        kid = _clean(point.get("id"))
        if not kid or kid in used_kp:
            kid = _next_id("kp", used_kp)
        else:
            used_kp.add(kid)
        fresh = _fresh_point(point, kid, stamp)
        if not _clean(fresh.get("chapter")):
            fresh["chapter"] = chapter_name
        if not _clean(fresh.get("topic")):
            fresh["topic"] = _clean(out.get("name"))
        points.append(fresh)
    out["knowledge_points"] = points
    return out


def _merge_chapter(
    old: dict[str, Any],
    new: dict[str, Any],
    used_tp: set[str],
    used_kp: set[str],
    stamp: str,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    changes = _empty_changes()
    merged = dict(old)
    merged["id"] = _clean(old.get("id"))
    merged["source_documents"] = _uniq(_as_list(old.get("source_documents")) + _as_list(new.get("source_documents")))
    old_topics = [t for t in (old.get("topics") or []) if isinstance(t, dict)]
    new_topics = [t for t in (new.get("topics") or []) if isinstance(t, dict)]
    consumed: set[int] = set()
    topics: list[dict[str, Any]] = []
    for new_tp in new_topics:
        old_tp = _match_node(new_tp, [t for i, t in enumerate(old_topics) if i not in consumed])
        if old_tp is None:
            built = _assign_topic(new_tp, used_tp, used_kp, stamp, False, _clean(merged.get("name")))
            topics.append(built)
            changes["added_topics"].append(_clean(built.get("name")))
            for p in built.get("knowledge_points") or []:
                changes["added_knowledge_points"].append(_clean(p.get("name")))
            continue
        consumed.add(old_topics.index(old_tp))
        merged_tp, tp_changes = _merge_topic(old_tp, new_tp, used_kp, stamp, _clean(merged.get("name")))
        topics.append(merged_tp)
        _extend_changes(changes, tp_changes)
    for i, old_tp in enumerate(old_topics):
        if i in consumed:
            continue
        kept = dict(old_tp)
        kept["change_type"] = "unchanged"
        topics.append(kept)
    merged["topics"] = topics
    merged["change_type"] = "updated" if any(changes.values()) else "unchanged"
    if merged["change_type"] == "updated":
        merged["updated_at"] = stamp
    return merged, changes


def _merge_topic(
    old: dict[str, Any],
    new: dict[str, Any],
    used_kp: set[str],
    stamp: str,
    chapter_name: str,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    changes = _empty_changes()
    merged = dict(old)
    merged["id"] = _clean(old.get("id"))
    old_points = [p for p in (old.get("knowledge_points") or []) if isinstance(p, dict)]
    new_points = [p for p in (new.get("knowledge_points") or []) if isinstance(p, dict)]
    consumed: set[int] = set()
    points: list[dict[str, Any]] = []
    for new_p in new_points:
        old_p = _match_node(new_p, [p for i, p in enumerate(old_points) if i not in consumed])
        if old_p is None:
            kid = _next_id("kp", used_kp)
            fresh = _fresh_point(new_p, kid, stamp)
            if not _clean(fresh.get("chapter")):
                fresh["chapter"] = chapter_name
            if not _clean(fresh.get("topic")):
                fresh["topic"] = _clean(merged.get("name"))
            points.append(fresh)
            changes["added_knowledge_points"].append(_clean(fresh.get("name")))
            continue
        consumed.add(old_points.index(old_p))
        merged_p, changed = _merge_point(old_p, new_p, stamp)
        points.append(merged_p)
        if changed:
            changes["updated_knowledge_points"].append(_clean(merged_p.get("name")))
    for i, old_p in enumerate(old_points):
        if i in consumed:
            continue
        kept = dict(old_p)
        kept["change_type"] = "unchanged"
        points.append(kept)
    merged["knowledge_points"] = points
    merged["change_type"] = "updated" if any(changes.values()) else "unchanged"
    return merged, changes
