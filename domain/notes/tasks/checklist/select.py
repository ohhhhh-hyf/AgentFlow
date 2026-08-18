"""把老师重点映射到已有 Catalog KP，并算出本次 S/A/B/C。"""
from __future__ import annotations

import re
from typing import Any

_SENT_SPLIT = re.compile(r"(?<=[。！？；;\n])")
_STRONG = ("必考", "一定出", "每届必出", "必须背", "务必掌握", "拉开分差", "一定要会", "年年有")
_MEDIUM = ("重点", "考到的概率", "考到概率", "着重", "要会")
_LIGHT = ("了解一下", "了解即可", "有印象", "了解就行", "有个印象")
_EXAM_STRONG = ("必考", "每届必出", "年年有", "一定出", "出大题")
_EXAM_MID = ("选择题", "填空", "选择填空", "出现过", "证明题", "计算题")
_ERROR = ("不能", "不要", "陷阱", "反例", "慎", "容易错", "混淆", "误用", "漏")
_COUNT_RE = re.compile(r"([0-9]+|十[一二三四五六七八九]?|[一二三四五六七八九两])\s*道")
_CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_EXAM_RANK = {"none": 0, "weak": 1, "medium": 2, "strong": 3}


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _norm(text: object) -> str:
    return re.sub(r"[的地得与和及/]", "", _compact(text))


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_clean(x) for x in value if _clean(x)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def flatten_points(catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    if not catalog:
        return points
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                if str(point.get("node_status") or "active") in {"merged", "deprecated"}:
                    continue
                if not _clean(point.get("id")) or not _clean(point.get("name")):
                    continue
                row = dict(point)
                row["chapter"] = _clean(point.get("chapter")) or _clean(chapter.get("name"))
                row["topic"] = _clean(point.get("topic")) or _clean(topic.get("name"))
                points.append(row)
    return points


def _stems(name: str) -> list[str]:
    raw = _clean(name)
    out = [raw]
    for suffix in ("的定义", "的概念", "的性质", "的分类", "的一般方法"):
        if raw.endswith(suffix) and len(raw) - len(suffix) >= 3:
            out.append(raw[: -len(suffix)])
    return out


def _needles(point: dict[str, Any]) -> list[str]:
    names = [_clean(point.get("name")), *_as_list(point.get("aliases"))]
    names.extend(_as_list(point.get("knowledge_items")))
    expanded: list[str] = []
    for name in names:
        expanded.extend(_stems(name))
    out: list[str] = []
    seen: set[str] = set()
    for name in expanded:
        key = _compact(name)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _hit_in(text: str, compact: str, needle: str) -> bool:
    raw = _clean(needle)
    if len(raw) < 2:
        return False
    if raw in text:
        return True
    key = _compact(raw)
    if len(key) >= 2 and key in compact:
        return True
    folded = _norm(raw)
    return len(folded) >= 2 and folded in _norm(text)


def _sentences(teacher: str) -> list[str]:
    parts = [_clean(p) for p in _SENT_SPLIT.split(teacher or "")]
    return [p for p in parts if len(p) >= 4]


def _emphasis(sentences: list[str]) -> int:
    blob = "".join(sentences)
    if any(mark in blob for mark in _LIGHT) and not any(mark in blob for mark in _STRONG):
        return 1
    if any(mark in blob for mark in _STRONG):
        return 3
    if any(mark in blob for mark in _MEDIUM):
        return 2
    return 1 if sentences else 0


def _exam_signal(sentences: list[str]) -> str:
    blob = "".join(sentences)
    if any(mark in blob for mark in _EXAM_STRONG):
        return "strong"
    if any(mark in blob for mark in _EXAM_MID):
        return "medium"
    if sentences:
        return "weak"
    return "none"


def _errors(sentences: list[str]) -> str:
    hits = [sent for sent in sentences if any(mark in sent for mark in _ERROR)]
    return " ".join(hits[:2])


def _focus_items(point: dict[str, Any], sentences: list[str]) -> list[str]:
    blob = "".join(sentences)
    compact = _compact(blob)
    found: list[str] = []
    for item in _as_list(point.get("knowledge_items")):
        if _hit_in(blob, compact, item) and item not in found:
            found.append(item)
    return found


def _is_light(blob: str) -> bool:
    if any(mark in blob for mark in _LIGHT):
        return True
    return bool(re.search(r"了解.{0,12}(一下|即可|就行|就好)", blob or ""))


def _needle_span(sent: str, point: dict[str, Any]) -> int:
    compact = _compact(sent)
    spans = [len(_compact(n)) for n in _needles(point) if _hit_in(sent, compact, n)]
    return max(spans) if spans else 0


def _owned_sentences(sentences: list[str], points: list[dict[str, Any]]) -> dict[str, list[str]]:
    """一句老师原话归最长命中针的 KP，避免短词误抢别人的句子。"""
    owned: dict[str, list[str]] = {_clean(p.get("id")): [] for p in points}
    for sent in sentences:
        scored = [(p, _needle_span(sent, p)) for p in points]
        scored = [(p, span) for p, span in scored if span > 0]
        if not scored:
            continue
        best = max(span for _p, span in scored)
        for point, span in scored:
            if span == best:
                owned.setdefault(_clean(point.get("id")), []).append(sent)
    return owned


def activate_points(catalog: dict[str, Any] | None, teacher: str) -> list[dict[str, Any]]:
    """匹配老师文本，写 session_* 并给出 S/A/B/C。不创建新 KP。"""
    points = flatten_points(catalog)
    teacher = teacher or ""
    compact_teacher = _compact(teacher)
    sentences = _sentences(teacher)
    owned = _owned_sentences(sentences, points)
    activated: list[dict[str, Any]] = []

    for point in points:
        hits = list(owned.get(_clean(point.get("id"))) or [])
        if not hits:
            if any(_hit_in(teacher, compact_teacher, n) for n in [_clean(point.get("name")), *_as_list(point.get("aliases"))]):
                hits = [teacher[:80]]
            else:
                continue
        row = dict(point)
        row["session_emphasis"] = str(_emphasis(hits))
        row["session_focus_items"] = _focus_items(point, hits)
        row["session_exam_signal"] = _exam_signal(hits)
        err_sents = [
            sent
            for sent in hits
            if any(mark in sent for mark in _ERROR)
        ]
        row["session_error_signal"] = _errors(err_sents or hits)
        row["session_difficulty_signal"] = (
            "hard" if any(x in "".join(hits) for x in ("拉开分差", "较难", "难点")) else ""
        )
        row["session_related_points"] = _related_in_hits(point, hits, points)
        row["session_quotes"] = [_clean(sent) for sent in hits[:3] if _clean(sent)]
        row["session_practice_count"] = ""
        row["session_special_requirement"] = ""
        blob = "".join(hits)
        row["_light"] = _is_light(blob) and not any(mark in blob for mark in _STRONG)
        row["_score"] = _raw_score(row)
        activated.append(row)

    selected_ids = {_clean(p.get("id")) for p in activated}
    # 老师点到的 KP 的前置，至少进入清单
    extra: list[dict[str, Any]] = []
    for row in list(activated):
        for name in _as_list(row.get("prerequisites")):
            prereq = _find_by_name(points, name)
            if not prereq or _clean(prereq.get("id")) in selected_ids:
                continue
            add = dict(prereq)
            add["session_emphasis"] = "0"
            add["session_focus_items"] = []
            add["session_exam_signal"] = "none"
            add["session_error_signal"] = ""
            add["session_difficulty_signal"] = ""
            add["session_related_points"] = []
            add["session_quotes"] = []
            add["session_practice_count"] = ""
            add["session_special_requirement"] = ""
            add["_light"] = False
            add["_prereq_of"] = _clean(row.get("name"))
            add["_score"] = _raw_score(add) + 8
            extra.append(add)
            selected_ids.add(_clean(add.get("id")))
    activated.extend(extra)
    _assign_priority(activated)
    _attach_session_practice(activated, teacher)
    activated.sort(key=lambda p: ({"S": 0, "A": 1, "B": 2, "C": 3}.get(p.get("session_priority"), 9), -p.get("_score", 0)))
    return activated


def _related_in_hits(
    point: dict[str, Any], hits: list[str], points: list[dict[str, Any]]
) -> list[str]:
    """同一句老师原话里点到的其他 Catalog KP，用作本次组合关系。"""
    mine = _clean(point.get("id"))
    found: list[str] = []
    for sent in hits:
        compact = _compact(sent)
        for other in points:
            if _clean(other.get("id")) == mine:
                continue
            names = [_clean(other.get("name")), *_as_list(other.get("aliases"))]
            if any(_hit_in(sent, compact, name) for name in names):
                label = _clean(other.get("name"))
                if label and label not in found:
                    found.append(label)
    return found


def _find_by_name(points: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    want = _compact(name)
    for point in points:
        if _compact(point.get("name")) == want:
            return point
        if want in {_compact(a) for a in _as_list(point.get("aliases"))}:
            return point
    return None


def _raw_score(point: dict[str, Any]) -> int:
    emph = int(str(point.get("session_emphasis") or 0) or 0)
    importance = int(str(point.get("importance") or 3) or 3)
    hist = int(str(point.get("teacher_emphasis") or 0) or 0)
    exam = _EXAM_RANK.get(str(point.get("session_exam_signal") or "none"), 0)
    catalog_exam = _EXAM_RANK.get(str(point.get("exam_signal") or "none"), 0)
    missing = min(4, len(_as_list(point.get("note_missing_items"))))
    return emph * 40 + importance * 8 + hist * 5 + exam * 8 + catalog_exam * 4 + missing * 3


def _assign_priority(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        emph = int(str(row.get("session_emphasis") or 0) or 0)
        importance = int(str(row.get("importance") or 3) or 3)
        exam = str(row.get("session_exam_signal") or "none")
        if row.get("_light"):
            row["session_priority"] = "B"
            continue
        if emph >= 3:
            row["session_priority"] = "S"
        elif emph >= 2 or (emph >= 1 and exam == "strong") or (emph >= 1 and importance >= 5):
            row["session_priority"] = "A"
        elif emph >= 1 or row.get("_prereq_of") or int(str(row.get("foundational_level") or 0) or 0) >= 4:
            row["session_priority"] = "B"
        else:
            row["session_priority"] = "C"
    for row in rows:
        if row.get("_prereq_of") and row.get("session_priority") not in {"S", "A"}:
            row["session_priority"] = "B"


def _to_count(raw: str) -> str:
    text = (raw or "").strip()
    if text.isdigit():
        return str(int(text))
    if text in _CN_NUM:
        return str(_CN_NUM[text])
    return ""


def _attach_session_practice(rows: list[dict[str, Any]], teacher: str) -> None:
    """从老师原话里抽题量和书写要求，按命中句或强调档挂到对应 KP。"""
    for row in rows:
        row["session_practice_count"] = row.get("session_practice_count") or ""
        row["session_special_requirement"] = row.get("session_special_requirement") or ""
    for sent in _sentences(teacher):
        compact = _compact(sent)
        hit_rows = [
            row
            for row in rows
            if any(_hit_in(sent, compact, needle) for needle in _needles(row))
        ]
        if any(mark in sent for mark in ("书写", "规范")):
            for row in hit_rows:
                row["session_special_requirement"] = "writing"
        for match in _COUNT_RE.finditer(sent):
            count = _to_count(match.group(1))
            if not count:
                continue
            if hit_rows:
                for row in hit_rows:
                    row["session_practice_count"] = count
                continue
            left = sent[: match.start()]
            last_strong = max((left.rfind(mark) for mark in _STRONG), default=-1)
            last_medium = max((left.rfind(mark) for mark in _MEDIUM), default=-1)
            if last_strong < 0 and last_medium < 0:
                continue
            grade = "S" if last_strong > last_medium else "A"
            for row in rows:
                if row.get("session_priority") == grade and not row.get("session_practice_count"):
                    row["session_practice_count"] = count


def catalog_index(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_clean(p.get("id")): p for p in points}
