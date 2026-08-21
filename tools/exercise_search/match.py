"""从笔记与用户选项里对齐高中科目、课本、题型、知识点。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .catalog import Course, HighSchoolCatalog, Keypoint, QuestionType, Textbook, Version

_GRADE_MAP = {
    "高一": 10,
    "高一年级": 10,
    "高一上": 10,
    "高一下": 10,
    "十年级": 10,
    "10": 10,
    "高二": 11,
    "高二年级": 11,
    "高二上": 11,
    "高二下": 11,
    "十一年级": 11,
    "11": 11,
    "高三": 12,
    "高三年级": 12,
    "高三上": 12,
    "高三下": 12,
    "十二年级": 12,
    "12": 12,
}

_GENERIC = {
    "函数",
    "公式",
    "应用",
    "性质",
    "定义",
    "概念",
    "计算",
    "判断",
    "求值",
    "其他",
    "问题",
    "方法",
    "已知",
    "利用",
    "根据",
    "及其",
    "求",
    "与",
}

_DOMAIN_LOCK = (
    "圆",
    "椭圆",
    "双曲线",
    "抛物线",
    "离心率",
    "向量",
    "数列",
    "概率",
    "贝叶斯",
    "复数",
    "立体几何",
    "排列",
    "组合",
)

_WEAK = {
    "对称",
    "原点",
    "坐标",
    "平面",
    "区间",
    "参数",
    "点",
    "最值",
    "大小",
    "比较",
    "综合",
    "其他",
    "类型",
    "关系",
    "图象",
    "变换",
}

_DIFFICULTY_MAP = {
    "容易": "容易",
    "简单": "容易",
    "易": "容易",
    "较易": "较易",
    "适中": "适中",
    "中等": "适中",
    "一般": "适中",
    "较难": "较难",
    "困难": "困难",
    "很难": "困难",
    "难": "困难",
    "4": "容易",
    "5": "较易",
    "6": "适中",
    "7": "较难",
    "8": "困难",
}

_DIFFICULTY_CODE = {
    "容易": 4,
    "较易": 5,
    "适中": 6,
    "较难": 7,
    "困难": 8,
}


@dataclass
class MatchedKeypoint:
    kp_id: str
    name: str
    depth: int
    score: int


_QUIZ_LEVEL = "期中备考"

_EDITION_ALIASES = (
    ("人教a版（2019）", "人教A版（2019）"),
    ("人教a版2019", "人教A版（2019）"),
    ("人教a2019", "人教A版（2019）"),
    ("人教a版", "人教A版（2019）"),
    ("人教a", "人教A版（2019）"),
    ("人教b版（2019）", "人教B版（2019）"),
    ("人教b版2019", "人教B版（2019）"),
    ("人教b版", "人教B版（2019）"),
    ("人教b", "人教B版（2019）"),
    ("北师大版（2019）", "北师大版（2019）"),
    ("北师大2019", "北师大版（2019）"),
    ("北师大", "北师大版（2019）"),
    ("苏教版（2019）", "苏教版（2019）"),
    ("苏教2019", "苏教版（2019）"),
    ("苏教", "苏教版（2019）"),
    ("湘教版（2019）", "湘教版（2019）"),
    ("湘教", "湘教版（2019）"),
    ("沪教版（2020）", "沪教版（2020）"),
    ("沪教", "沪教版（2020）"),
    ("统编版", "统编版"),
    ("统编", "统编版"),
)


@dataclass
class SearchSpec:
    course: Course | None = None
    grade_id: int | None = None
    version: Version | None = None
    textbook: Textbook | None = None
    difficulty: str = ""
    qtype: QuestionType | None = None
    keypoints: list[MatchedKeypoint] = field(default_factory=list)
    keyword: str = ""
    keywords: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    grade_label: str = ""
    edition_label: str = ""
    level: str = _QUIZ_LEVEL


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: object) -> str:
    value = re.sub(r"\s+", "", str(text or "")).strip().lower()
    return value.replace("图像", "图象")


def _too_generic(text: object) -> bool:
    return _compact(text) in _GENERIC


_TOKEN_PREFIX = re.compile(r"^(判断|证明|利用|根据|用|求|已知|由)")


def _name_tokens(name: str) -> list[str]:
    parts = re.split(r"[的与和或及、，,/\s]+", _clean(name))
    out: list[str] = []
    for part in parts:
        compact = _compact(part)
        peeled = _compact(_TOKEN_PREFIX.sub("", part))
        extras: list[str] = []
        for candidate in (peeled, compact):
            if candidate.startswith("函数") and len(candidate) > 2:
                extras.append(candidate[2:])
        for candidate in (peeled, compact, *extras):
            if len(candidate) < 2 or _too_generic(candidate):
                continue
            if candidate not in out:
                out.append(candidate)
    return out


def parse_grade(raw: object) -> int | None:
    text = _clean(raw)
    if not text:
        return None
    if text in _GRADE_MAP:
        return _GRADE_MAP[text]
    compact = _compact(text)
    if compact in _GRADE_MAP:
        return _GRADE_MAP[compact]
    for key, value in _GRADE_MAP.items():
        if key in text:
            return value
    if text.isdigit():
        number = int(text)
        if number in {10, 11, 12}:
            return number
    return None


def parse_difficulty(raw: object) -> str:
    text = _clean(raw)
    if not text:
        return ""
    if text in _DIFFICULTY_MAP:
        return _DIFFICULTY_MAP[text]
    compact = _compact(text)
    return _DIFFICULTY_MAP.get(compact, "")


def difficulty_code(raw: object) -> int | None:
    """/bank/v1/question 的 difficulty 必须是 4~8，不能传中文。"""
    name = parse_difficulty(raw)
    return _DIFFICULTY_CODE.get(name)


def collect_terms(
    notes: str,
    *,
    understanding: dict[str, Any] | None = None,
    concepts: Iterable[Any] | None = None,
) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        text = _clean(value)
        if len(text) < 2:
            return
        key = _compact(text)
        if not key or key in seen:
            return
        seen.add(key)
        terms.append(text)

    blob = understanding or {}
    for item in blob.get("key_terms") or []:
        add(item)
    for section in blob.get("sections") or []:
        if isinstance(section, dict):
            add(section.get("title"))
        else:
            add(section)
    add(blob.get("note_purpose"))
    for line in (notes or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            add(re.sub(r"^#+\s*", "", stripped))
    for item in concepts or []:
        if isinstance(item, dict):
            add(item.get("name"))
            add(item.get("note_hook"))
            add(item.get("prompt"))
            add(item.get("title"))
        else:
            add(item)
    return terms


def infer_course(
    catalog: HighSchoolCatalog,
    *,
    subject: str = "",
    notes: str = "",
    terms: list[str] | None = None,
) -> Course | None:
    if subject:
        hit = catalog.course_by_name(subject)
        if hit:
            return hit
        compact = _compact(subject)
        for course in catalog.courses:
            short = _compact(course.name).removeprefix("高中")
            if short and short in compact:
                return course
    hay = _compact(" ".join(terms or []) + " " + (notes or ""))
    scored: list[tuple[int, Course]] = []
    for course in catalog.courses:
        short = _compact(course.name).removeprefix("高中")
        if short and short in hay:
            scored.append((80 + len(short), course))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return _course_from_keypoints(catalog, notes, terms or [])


def _course_from_keypoints(
    catalog: HighSchoolCatalog, notes: str, terms: list[str]
) -> Course | None:
    hay = (notes or "") + "\n" + "\n".join(terms)
    if len(hay) < 4:
        return None
    buckets: dict[int, int] = {}
    for node in catalog.keypoints:
        if len(node.name) < 2 or node.name not in hay:
            continue
        buckets[node.subject_id] = buckets.get(node.subject_id, 0) + len(node.name) + node.depth
    if not buckets:
        return None
    subject_id = max(buckets, key=buckets.get)
    for course in catalog.courses:
        if course.subject_id == subject_id:
            return course
    return None


def match_version(catalog: HighSchoolCatalog, course: Course, edition: str) -> Version | None:
    text = _clean(edition)
    if not text:
        return None
    compact = _compact(text)
    options = catalog.versions_for(course.course_id)
    exact = [item for item in options if _compact(item.name) == compact]
    if exact:
        return exact[0]
    scored: list[tuple[int, Version]] = []
    for item in options:
        name = _compact(item.name)
        if compact in name or name in compact:
            scored.append((len(name), item))
    if scored:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1]
    return None


def match_textbook(version: Version | None, grade_id: int | None) -> Textbook | None:
    if version is None:
        return None
    books = list(version.textbooks)
    if grade_id is not None:
        books = [item for item in books if item.grade_id == grade_id]
    if not books:
        return None

    def rank(book: Textbook) -> tuple[int, int]:
        volume = book.volume
        prefer = 1 if ("必修" in volume and "选择性" not in volume and "选修" not in volume) else 0
        return (prefer, -book.textbook_id)

    books.sort(key=rank, reverse=True)
    return books[0]


def match_qtype(catalog: HighSchoolCatalog, course: Course, raw: str) -> QuestionType | None:
    text = _clean(raw)
    if not text:
        return None
    compact = _compact(text)
    options = catalog.types_for_subject(course.subject_id)
    for item in options:
        if _compact(item.name) == compact:
            return item
    scored: list[tuple[int, QuestionType]] = []
    for item in options:
        name = _compact(item.name)
        if compact in name or name in compact:
            scored.append((0 if not item.parent_name else 1, item))
    if scored:
        scored.sort(key=lambda pair: (pair[0], -len(pair[1].name)))
        return scored[0][1]
    return None


def _is_weak(token: str) -> bool:
    return token in _WEAK or _too_generic(token)


def _bare_name(compact: str) -> str:
    return re.sub(r"^(函数|已知)", "", compact)


def _score_keypoint(node: Keypoint, hay: str, compact_terms: list[str]) -> int:
    name = node.name
    compact = _compact(name)
    if len(compact) < 2 or _too_generic(compact):
        return 0
    if any(lock in compact for lock in _DOMAIN_LOCK) and not any(
        lock in hay for lock in _DOMAIN_LOCK
    ):
        return 0
    score = 0
    if compact in hay:
        score = 110 + min(len(compact), 24) * 2
    bare = _bare_name(compact)
    if bare != compact and len(bare) >= 4 and bare in hay:
        score = max(score, 105 + min(len(bare), 24) * 2)
    for term in compact_terms:
        if not term or _too_generic(term):
            continue
        if compact == term or bare == term:
            score = max(score, 130 + min(len(compact), 24))
        elif len(term) >= 4 and (term in compact or compact in term or term in bare):
            score = max(score, 80 + min(len(compact), len(term), 18))
    tokens = _name_tokens(name)
    hit_tokens = [token for token in tokens if token in hay]
    strong_hits = [token for token in hit_tokens if not _is_weak(token)]
    if hit_tokens and not strong_hits:
        return 0
    if strong_hits:
        token_score = 48 + sum(len(token) * 5 for token in strong_hits)
        if len(strong_hits) > 1:
            token_score += 22 * (len(strong_hits) - 1)
        if any(
            token in term or term in token
            for token in strong_hits
            for term in compact_terms
            if len(term) >= 2
        ):
            token_score += 30
        score = max(score, token_score)
    if score <= 0:
        return 0
    return score + node.depth + min(len(compact), 12)


def _topic_core(name: str, hay: str) -> str:
    tokens = [token for token in _name_tokens(name) if token in hay and not _is_weak(token)]
    if not tokens:
        tokens = [token for token in _name_tokens(name) if not _is_weak(token)]
    compact_name = _compact(name)
    shorter = [token for token in tokens if token != compact_name]
    pool = shorter or tokens
    return min(pool, key=len) if pool else compact_name


def _question_terms(terms: list[str]) -> list[str]:
    return [
        term
        for term in terms
        if any(mark in term for mark in ("为什么", "？", "有何", "区别", "吗"))
    ]


def _best_for_hay(
    nodes: list[Keypoint], hay: str, compact_terms: list[str]
) -> MatchedKeypoint | None:
    best: MatchedKeypoint | None = None
    for node in nodes:
        score = _score_keypoint(node, hay, compact_terms)
        if score <= 0:
            continue
        item = MatchedKeypoint(
            kp_id=node.kp_id, name=node.name, depth=node.depth, score=score
        )
        if best is None or (item.score, len(item.name)) > (best.score, len(best.name)):
            best = item
    return best


def match_keypoints(
    catalog: HighSchoolCatalog,
    course: Course,
    notes: str,
    terms: list[str],
    *,
    limit: int = 7,
) -> list[MatchedKeypoint]:
    nodes = catalog.keypoints_for_subject(course.subject_id)
    if not nodes:
        return []
    hay = _compact((notes or "") + "\n" + "\n".join(terms))
    compact_terms = [
        _compact(item)
        for item in terms
        if len(_clean(item)) >= 2 and not _too_generic(item)
    ]
    picked: list[MatchedKeypoint] = []
    used: set[str] = set()
    for question in _question_terms(terms):
        qhay = _compact(question)
        item = _best_for_hay(nodes, qhay, [_compact(question)])
        if item is None or item.kp_id in used:
            continue
        core = _topic_core(item.name, qhay)
        if core in used:
            continue
        picked.append(item)
        used.add(item.kp_id)
        used.add(core)
        if len(picked) >= limit:
            return picked
    scored: list[MatchedKeypoint] = []
    for node in nodes:
        if node.kp_id in used:
            continue
        score = _score_keypoint(node, hay, compact_terms)
        if score <= 0:
            continue
        scored.append(
            MatchedKeypoint(kp_id=node.kp_id, name=node.name, depth=node.depth, score=score)
        )
    scored.sort(key=lambda item: (item.score, item.depth, len(item.name)), reverse=True)
    for item in scored:
        core = _topic_core(item.name, hay)
        if item.kp_id in used or core in used:
            continue
        picked.append(item)
        used.add(item.kp_id)
        used.add(core)
        if len(picked) >= limit:
            break
    return picked


def _grade_label(grade_ids: list[int]) -> str:
    names = []
    mapping = {10: "高一", 11: "高二", 12: "高三"}
    for grade_id in grade_ids:
        name = mapping.get(grade_id)
        if name and name not in names:
            names.append(name)
    return " / ".join(names)


def _version_rank(version: Version) -> tuple[int, int, int, int]:
    name = _compact(version.name)
    modern = 1 if any(mark in name for mark in ("2019", "2020", "统编")) else 0
    pep_a = 1 if "人教a" in name else 0
    official = 1 if "统编" in name else 0
    return (modern, pep_a, official, -version.version_id)


def _edition_from_notes(catalog: HighSchoolCatalog, course: Course, hay: str) -> Version | None:
    compact = _compact(hay)
    if not compact:
        return None
    for alias, target in _EDITION_ALIASES:
        if alias in compact:
            hit = match_version(catalog, course, target)
            if hit:
                return hit
    return None


def _books_for_keypoint(
    catalog: HighSchoolCatalog, course: Course, name: str
) -> list[Textbook]:
    books = catalog.textbooks_covering(course.course_id, name, strict=True)
    if books:
        return books
    extra: list[Textbook] = []
    seen: set[int] = set()
    for token in _name_tokens(name):
        if _is_weak(token) or len(token) < 3:
            continue
        for book in catalog.textbooks_covering(course.course_id, token, strict=True):
            if book.textbook_id in seen:
                continue
            seen.add(book.textbook_id)
            extra.append(book)
    return extra


def infer_placement(
    catalog: HighSchoolCatalog,
    course: Course,
    keypoints: list[MatchedKeypoint],
    notes: str,
    terms: list[str],
) -> tuple[int | None, Version | None, Textbook | None, str, str]:
    """用对齐到的知识点反查课本章节，得到年级和课本版本。"""
    hay = (notes or "") + "\n" + "\n".join(terms)
    mentioned = _edition_from_notes(catalog, course, hay)
    grade_votes: dict[int, int] = {}
    version_votes: dict[int, int] = {}
    book_votes: dict[int, int] = {}
    ranked = [item for item in keypoints if item.score >= 90] or list(keypoints[:1])
    for item in ranked:
        weight = max(item.score, 1)
        for book in _books_for_keypoint(catalog, course, item.name):
            if book.course_id != course.course_id:
                continue
            if book.grade_id in {10, 11, 12}:
                grade_votes[book.grade_id] = grade_votes.get(book.grade_id, 0) + weight
            version_votes[book.version_id] = version_votes.get(book.version_id, 0) + weight
            book_votes[book.textbook_id] = book_votes.get(book.textbook_id, 0) + weight
    grade_ids = [
        grade_id
        for grade_id, _ in sorted(grade_votes.items(), key=lambda pair: pair[1], reverse=True)
    ]
    grade_id = grade_ids[0] if len(grade_ids) == 1 else None
    versions = catalog.versions_for(course.course_id)
    version = mentioned
    if version is None and version_votes:
        covered = [item for item in versions if item.version_id in version_votes]
        version = max(covered, key=_version_rank) if covered else None
    textbook = None
    if version is not None and book_votes:
        same_version = [
            book
            for textbook_id, _ in sorted(
                book_votes.items(), key=lambda pair: pair[1], reverse=True
            )
            if (book := catalog.textbook_by_id(textbook_id))
            and book.version_id == version.version_id
            and (grade_id is None or book.grade_id == grade_id)
        ]
        if len({book.textbook_id for book in same_version}) == 1:
            textbook = same_version[0]
        elif grade_id is not None:
            textbook = match_textbook(version, grade_id)
    elif version is not None:
        textbook = match_textbook(version, grade_id)
    if textbook is not None and grade_id is None and textbook.grade_id in {10, 11, 12}:
        grade_id = textbook.grade_id
    label_grades = [grade_id] if grade_id is not None else grade_ids
    return (
        grade_id,
        version,
        textbook,
        _grade_label(label_grades),
        version.name if version else "",
    )


def topic_keywords(points: list[MatchedKeypoint], hay: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for item in points:
        core = _topic_core(item.name, hay)
        for candidate in (core, item.name):
            text = _clean(candidate)
            compact = _compact(text)
            if len(compact) < 2 or _too_generic(compact) or compact in seen:
                continue
            seen.add(compact)
            keys.append(text)
            break
    return keys


def build_spec(
    catalog: HighSchoolCatalog,
    *,
    notes: str,
    understanding: dict[str, Any] | None = None,
    concepts: Iterable[Any] | None = None,
    subject: str = "",
    grade: str = "",
    edition: str = "",
    difficulty: str = "",
    qtype: str = "",
) -> SearchSpec:
    # grade / edition 参数保留兼容，检索不再听用户手选，只从知识点反推。
    del grade, edition
    terms = collect_terms(notes, understanding=understanding, concepts=concepts)
    course = infer_course(catalog, subject=subject, notes=notes, terms=terms)
    kind = match_qtype(catalog, course, qtype) if course else None
    points = match_keypoints(catalog, course, notes, terms) if course else []
    grade_id = None
    version = None
    textbook = None
    grade_label = ""
    edition_label = ""
    if course is not None:
        grade_id, version, textbook, grade_label, edition_label = infer_placement(
            catalog, course, points, notes, terms
        )
    hay = _compact((notes or "") + "\n" + "\n".join(terms))
    words = topic_keywords(points, hay)
    if not words:
        specific = [item for item in terms if not _too_generic(item)]
        if specific:
            words = [specific[0]]
    return SearchSpec(
        course=course,
        grade_id=grade_id,
        version=version,
        textbook=textbook,
        difficulty=parse_difficulty(difficulty),
        qtype=kind,
        keypoints=points,
        keyword=words[0] if words else "",
        keywords=words,
        terms=terms,
        grade_label=grade_label,
        edition_label=edition_label,
        level=_QUIZ_LEVEL,
    )


__all__ = [
    "MatchedKeypoint",
    "SearchSpec",
    "build_spec",
    "collect_terms",
    "infer_course",
    "infer_placement",
    "match_keypoints",
    "match_qtype",
    "match_textbook",
    "match_version",
    "parse_difficulty",
    "difficulty_code",
    "parse_grade",
    "topic_keywords",
]
