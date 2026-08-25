"""把本次 LLM 目录合并进已有目录：复用 ID，旧章不丢，证据追加。"""
from __future__ import annotations

import re
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
        return _fill_empty_topics(result, stamp)

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
    return _fill_empty_topics(result, stamp)


def _fill_empty_topics(catalog: dict[str, Any], stamp: str) -> dict[str, Any]:
    """主题有名字但 0 个 KP 时，用节标题回退生成 1 个点，避免切丢一节。"""
    _used_ch, _used_tp, used_kp = _collect_ids(catalog)
    added: list[str] = []
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter_name = _clean(chapter.get("name"))
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            name = _clean(topic.get("name"))
            points = [
                point
                for point in (topic.get("knowledge_points") or [])
                if isinstance(point, dict) and _clean(point.get("name"))
            ]
            if points or not name:
                topic["knowledge_points"] = points or topic.get("knowledge_points") or []
                continue
            kid = _next_id("kp", used_kp)
            topic["knowledge_points"] = [
                _fresh_point(
                    {
                        "name": name,
                        "chapter": chapter_name,
                        "topic": name,
                        "knowledge_type": "mixed",
                        "knowledge_items": [name],
                        "importance": "3",
                        "difficulty": "3",
                        "note_coverage": "mentioned",
                        "sources": ["学生笔记"],
                        "evidence": [f"学生笔记：{name}"],
                    },
                    kid,
                    stamp,
                )
            ]
            added.append(name)
    if added:
        catalog["added_knowledge_points"] = _uniq(
            _as_list(catalog.get("added_knowledge_points")) + added
        )
    return catalog


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


# ── 枚举/数值归一化（消除模型输出的表面差异，提升同输入稳定性）──

_CHANGE_TYPE_MAP = {
    "added": "added", "新增": "added", "new": "added",
    "unchanged": "unchanged", "未变": "unchanged", "不变": "unchanged",
    "updated": "updated", "更新": "updated",
    "merged": "merged", "合并": "merged",
    "moved": "moved", "移动": "moved",
}
_KNOWLEDGE_TYPE_MAP = {
    "concept": "concept", "概念": "concept",
    "formula": "formula", "公式": "formula",
    "theorem": "theorem", "定理": "theorem",
    "method": "method", "方法": "method",
    "application": "application", "应用": "application",
    "mixed": "mixed", "混合": "mixed", "综合": "mixed",
}
_EXAM_SIGNAL_MAP = {
    "none": "none", "无": "none",
    "weak": "weak", "弱": "weak",
    "medium": "medium", "中": "medium",
    "strong": "strong", "强": "strong",
}
_COVERAGE_MAP = {
    "none": "none", "无": "none",
    "mentioned": "mentioned", "提及": "mentioned",
    "partial": "partial", "部分": "partial",
    "detailed": "detailed", "详细": "detailed",
}


def _norm_enum(value: object, mapping: dict[str, str], default: str) -> str:
    raw = str(value or "").strip().lower()
    return mapping.get(raw, default)


def _norm_rank(value: object, lo: int, hi: int) -> str:
    try:
        n = int(str(value or "").strip())
    except (TypeError, ValueError):
        return str(lo)
    return str(max(lo, min(hi, n)))


def normalize_catalog_enums(catalog: dict[str, Any]) -> dict[str, Any]:
    """把目录树里的枚举/数值字段归一到契约合法值（确定性）。

    LLM 偶发输出中文枚举（"概念"）、越界数值或非标准值，会让同一
    批数据的两次结果表面差异大；此处统一映射，保持输出骨架稳定。
    未知枚举取契约默认值，越界数值钳制到范围；ID 由 merge 层处理。
    """
    out = dict(catalog)
    chapters: list[dict[str, Any]] = []
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter = dict(chapter)
        chapter["change_type"] = _norm_enum(
            chapter.get("change_type"), _CHANGE_TYPE_MAP, "unchanged"
        )
        topics: list[dict[str, Any]] = []
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            topic = dict(topic)
            topic["change_type"] = _norm_enum(
                topic.get("change_type"), _CHANGE_TYPE_MAP, "unchanged"
            )
            points: list[dict[str, Any]] = []
            for kp in topic.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                kp = dict(kp)
                kp["knowledge_type"] = _norm_enum(
                    kp.get("knowledge_type"), _KNOWLEDGE_TYPE_MAP, "concept"
                )
                kp["importance"] = _norm_rank(kp.get("importance"), 1, 5)
                kp["difficulty"] = _norm_rank(kp.get("difficulty"), 1, 5)
                kp["foundational_level"] = _norm_rank(
                    kp.get("foundational_level"), 1, 5
                )
                kp["teacher_emphasis"] = _norm_rank(
                    kp.get("teacher_emphasis"), 0, 3
                )
                kp["exam_signal"] = _norm_enum(
                    kp.get("exam_signal"), _EXAM_SIGNAL_MAP, "none"
                )
                kp["note_coverage"] = _norm_enum(
                    kp.get("note_coverage"), _COVERAGE_MAP, "none"
                )
                points.append(kp)
            topic["knowledge_points"] = points
            topics.append(topic)
        chapter["topics"] = topics
        chapters.append(chapter)
    out["chapters"] = chapters
    return compact_catalog_granularity(out)


_FINE_GRAIN_RE = re.compile(
    r"(使用条件|适用条件|成立条件|边界条件|限制条件|条件检查|"
    r"常见变形|变形技巧|计算技巧|替换规则|判断步骤|判断流程|证明步骤|"
    r"例题|典型例子|题型|选择题|填空题|计算题|证明题|综合题|"
    r"注意|易错|误区|陷阱|提醒|小结|总结|变量含义|符号说明)"
)


def _norm_name(text: object) -> str:
    return re.sub(r"[\s:：,，。；;、（）()\[\]【】《》“”\"'·\-—_]+", "", str(text or "").lower())


def _base_of_fine_point(name: str) -> str:
    text = _clean(name)
    for sep in ("的", "之"):
        if sep in text:
            head, tail = text.split(sep, 1)
            if head and _FINE_GRAIN_RE.search(tail):
                return head
    for mark in ("使用条件", "适用条件", "成立条件", "常见变形", "计算技巧", "例题", "易错", "注意"):
        if text.endswith(mark) and len(text) > len(mark) + 1:
            return text[: -len(mark)]
    return ""


def _is_fine_point(point: dict[str, Any]) -> bool:
    name = _clean(point.get("name"))
    if not name:
        return False
    if _FINE_GRAIN_RE.search(name):
        return True
    kind = str(point.get("knowledge_type") or "")
    role = str(point.get("learning_role") or "")
    if kind == "formula" and len(_as_list(point.get("knowledge_items"))) <= 1:
        return bool(re.search(r"(变量|条件|变形|形式|写法|符号)", name))
    return role == "application" and bool(re.search(r"(题型|例题|练习)", name))


def _merge_into_point(parent: dict[str, Any], child: dict[str, Any]) -> None:
    child_name = _clean(child.get("name"))
    items = _as_list(parent.get("knowledge_items"))
    child_items = _as_list(child.get("knowledge_items"))
    if child_name and child_name != _clean(parent.get("name")):
        items.append(child_name)
    items.extend(child_items)
    parent["knowledge_items"] = _uniq(items)
    for key in (
        "teacher_focus_items",
        "note_covered_items",
        "note_missing_items",
        "prerequisites",
        "sources",
        "evidence",
        "source_documents",
    ):
        parent[key] = _uniq(_as_list(parent.get(key)) + _as_list(child.get(key)))
    for key, allowed in (
        ("practice_type", _PRACTICE),
        ("completion_criteria", _CRITERIA),
        ("risk_tags", _RISKS),
    ):
        parent[key] = _enum_list(_as_list(parent.get(key)) + _as_list(child.get(key)), allowed)
    parent["teacher_emphasis"] = _max_rank(
        str(parent.get("teacher_emphasis") or "0"),
        str(child.get("teacher_emphasis") or "0"),
        _EMPHASIS_RANK,
        "0",
    )
    parent["exam_signal"] = _max_rank(
        str(parent.get("exam_signal") or "none"),
        str(child.get("exam_signal") or "none"),
        _EXAM_RANK,
        "none",
    )
    parent["note_coverage"] = _max_rank(
        str(parent.get("note_coverage") or "none"),
        str(child.get("note_coverage") or "none"),
        _COVERAGE_RANK,
        "none",
    )
    parent["change_type"] = "updated"


def _find_parent_point(child: dict[str, Any], siblings: list[dict[str, Any]]) -> dict[str, Any] | None:
    child_name = _clean(child.get("name"))
    child_norm = _norm_name(child_name)
    base_norm = _norm_name(_base_of_fine_point(child_name))
    for point in siblings:
        if point is child:
            continue
        name = _clean(point.get("name"))
        norm = _norm_name(name)
        if not norm:
            continue
        if base_norm and (base_norm == norm or base_norm in norm or norm in base_norm):
            return point
        if norm != child_norm and (norm in child_norm or child_norm in norm):
            return point
    return None


def _compact_topic_points(
    points: list[dict[str, Any]],
    chapter_name: str,
    topic_name: str,
    merged_nodes: list[str],
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for point in points:
        name_key = _norm_name(point.get("name"))
        if name_key and name_key in by_name:
            parent = by_name[name_key]
            _merge_into_point(parent, point)
            merged_nodes.append(f"{_clean(point.get('name'))} → {_clean(parent.get('name'))}")
            continue
        kept.append(point)
        if name_key:
            by_name[name_key] = point

    out: list[dict[str, Any]] = []
    for point in list(kept):
        parent = _find_parent_point(point, kept)
        if parent is not None and _is_fine_point(point):
            _merge_into_point(parent, point)
            merged_nodes.append(f"{_clean(point.get('name'))} → {_clean(parent.get('name'))}")
            continue
        out.append(point)

    if len(out) > 1:
        compacted: list[dict[str, Any]] = []
        for point in out:
            same_as_container = _norm_name(point.get("name")) in {
                _norm_name(chapter_name),
                _norm_name(topic_name),
            }
            parent = next(
                (
                    other
                    for other in out
                    if other is not point
                    and _norm_name(other.get("name")) != _norm_name(point.get("name"))
                ),
                None,
            )
            if same_as_container and parent is not None:
                _merge_into_point(parent, point)
                merged_nodes.append(f"{_clean(point.get('name'))} → {_clean(parent.get('name'))}")
                continue
            compacted.append(point)
        out = compacted or out
    return out


def compact_catalog_granularity(catalog: dict[str, Any]) -> dict[str, Any]:
    """把过细 KP 降级进父 KP 的 items，并合并同层重复点。"""
    out = dict(catalog or {})
    merged_nodes = _as_list(out.get("merged_nodes"))
    chapters: list[dict[str, Any]] = []
    for chapter in out.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapter = dict(chapter)
        chapter_name = _clean(chapter.get("name"))
        topics: list[dict[str, Any]] = []
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            topic = dict(topic)
            topic_name = _clean(topic.get("name"))
            points = [
                dict(point)
                for point in topic.get("knowledge_points") or []
                if isinstance(point, dict) and _clean(point.get("name"))
            ]
            topic["knowledge_points"] = _compact_topic_points(
                points, chapter_name, topic_name, merged_nodes
            )
            topics.append(topic)
        chapter["topics"] = topics
        chapters.append(chapter)
    out["chapters"] = chapters
    out["merged_nodes"] = _uniq(merged_nodes)
    if out.get("added_knowledge_points"):
        active = {
            _clean(point.get("name"))
            for chapter in chapters
            for topic in chapter.get("topics") or []
            for point in topic.get("knowledge_points") or []
            if isinstance(point, dict)
        }
        out["added_knowledge_points"] = [
            name for name in _as_list(out.get("added_knowledge_points")) if name in active
        ]
    return out
