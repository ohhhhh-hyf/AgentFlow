"""ExerciseSearchTool：按笔记对齐高中题库并取题。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .catalog import HighSchoolCatalog, default_catalog
from .client import get_questions
from .match import SearchSpec, build_spec, difficulty_code, _too_generic
from .tex import pretty_latex, replace_tex_html


GetQuestions = Callable[..., list[dict[str, Any]]]


@dataclass
class BankQuestion:
    id: Any
    prompt: str
    content_html: str
    question_type: str
    difficulty: str
    options: list[str] = field(default_factory=list)
    correct_answer: str = ""
    analysis: str = ""
    analysis_html: str = ""
    keypoints: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    paper: str = ""
    matched_keypoint: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "content_html": self.content_html,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "options": list(self.options),
            "correct_answer": self.correct_answer,
            "analysis": self.analysis,
            "analysis_html": self.analysis_html,
            "keypoints": list(self.keypoints),
            "sections": list(self.sections),
            "paper": self.paper,
            "matched_keypoint": self.matched_keypoint,
        }


@dataclass
class SearchBundle:
    questions: list[BankQuestion] = field(default_factory=list)
    query_label: str = ""
    message: str = ""
    spec: SearchSpec | None = None

    def as_dicts(self) -> list[dict[str, Any]]:
        return [item.as_dict() for item in self.questions]


def html_to_text(raw: object) -> str:
    import html
    import re

    text = "" if raw is None else str(raw)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", "", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", "", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = replace_tex_html(text)
    text = re.sub(
        r"(?is)<tex[^>]*>.*?</tex>",
        lambda m: pretty_latex(re.sub(r"<[^>]+>", "", m.group(0))),
        text,
    )
    text = re.sub(r"(?is)<(?:bk|blk)\b[^>]*>.*?</(?:bk|blk)>", "____", text)
    text = re.sub(r"(?i)<(?:bk|blk)\b[^>]*/?>", "____", text)
    text = re.sub(r"(?is)<img[^>]*>", "［图］", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    if "\\" in text:
        text = pretty_latex(text)
    return " ".join(text.split()).strip()


def _shape(raw: dict[str, Any], matched: str = "") -> BankQuestion:
    content = str(raw.get("content") or "")
    analysis = str(raw.get("analysis") or "")
    if not analysis:
        extras = [str(raw.get(key) or "").strip() for key in ("idea", "step")]
        analysis = "".join(item for item in extras if item)
    options = raw.get("options") or []
    if not isinstance(options, list):
        options = [str(options)]
    answer = raw.get("correct_answer")
    if isinstance(answer, list):
        answer = "；".join(str(item) for item in answer if str(item).strip())
    return BankQuestion(
        id=raw.get("id"),
        prompt=html_to_text(content) or content,
        content_html=content,
        question_type=str(raw.get("question_type") or "").strip(),
        difficulty=str(raw.get("difficulty") or "").strip(),
        options=[str(item) for item in options if str(item).strip()],
        correct_answer=str(answer or "").strip(),
        analysis=html_to_text(analysis),
        analysis_html=analysis,
        keypoints=list(raw.get("keypoints") or []),
        sections=list(raw.get("sections") or []),
        paper=str(raw.get("paper") or "").strip(),
        matched_keypoint=matched,
    )


def _query_label(spec: SearchSpec) -> str:
    bits: list[str] = []
    if spec.course:
        bits.append(spec.course.name)
    if spec.grade_label:
        bits.append(spec.grade_label)
    elif spec.grade_id == 10:
        bits.append("高一")
    elif spec.grade_id == 11:
        bits.append("高二")
    elif spec.grade_id == 12:
        bits.append("高三")
    if spec.edition_label:
        bits.append(spec.edition_label)
    elif spec.version:
        bits.append(spec.version.name)
    if spec.difficulty:
        bits.append(spec.difficulty)
    if spec.qtype:
        bits.append(spec.qtype.name)
    if spec.keypoints:
        bits.append("知识点：" + "、".join(item.name for item in spec.keypoints[:3]))
    return " · ".join(bits)


class ExerciseSearchTool:
    """高中题库检索。quiz 在生成推理题之后调用，失败不影响原卷。"""

    def __init__(
        self,
        *,
        catalog: HighSchoolCatalog | None = None,
        data_dir: Path | str | None = None,
        fetch: GetQuestions | None = None,
    ) -> None:
        if catalog is not None:
            self.catalog = catalog
        else:
            self.catalog = default_catalog(str(data_dir) if data_dir else None)
        self._fetch = fetch or get_questions

    def search_for_notes(
        self,
        notes: str,
        *,
        understanding: dict[str, Any] | None = None,
        concepts: Iterable[Any] | None = None,
        subject: str = "",
        grade: str = "",
        edition: str = "",
        difficulty: str = "",
        qtype: str = "",
        limit: int = 6,
    ) -> SearchBundle:
        spec = build_spec(
            self.catalog,
            notes=notes,
            understanding=understanding,
            concepts=concepts,
            subject=subject,
            grade=grade,
            edition=edition,
            difficulty=difficulty,
            qtype=qtype,
        )
        label = _query_label(spec)
        if spec.course is None:
            return SearchBundle(
                query_label=label,
                message="未能从笔记或选项对齐到高中科目，跳过题库检索。",
                spec=spec,
            )
        raw = self._fetch_with_fallback(spec, limit=limit)
        matched = spec.keypoints[0].name if spec.keypoints else ""
        questions = [_shape(item, matched) for item in raw[:limit]]
        if not questions:
            return SearchBundle(
                query_label=label,
                message="题库未命中相关题目，仍保留笔记推理题。",
                spec=spec,
            )
        return SearchBundle(
            questions=questions,
            query_label=label,
            message=f"按「{label}」命中 {len(questions)} 道带解析和答案的题库题。",
            spec=spec,
        )

    def _fetch_with_fallback(self, spec: SearchSpec, *, limit: int) -> list[dict[str, Any]]:
        course_id = spec.course.course_id if spec.course else 0
        page_size = min(max(limit * 2, 10), 20)
        common: dict[str, Any] = {
            "course_id": course_id,
            "page_size": page_size,
            "difficulty": difficulty_code(spec.difficulty),
            "qtype": spec.qtype.type_id if spec.qtype else None,
            "grade": spec.grade_id,
            "book_id": spec.textbook.textbook_id if spec.textbook else None,
            "order": 6,
            "truncate": 0,
        }
        attempts: list[dict[str, Any]] = []
        words = list(spec.keywords or [])
        if spec.keyword and spec.keyword not in words:
            words.append(spec.keyword)
        for item in spec.keypoints[:6]:
            attempts.append({**common, "keypoint": [item.kp_id]})
        for word in words[:5]:
            attempts.append({**common, "keyword": word, "keypoint": None})
        if words:
            rescue = {
                **common,
                "grade": None,
                "difficulty": None,
                "book_id": None,
                "keypoint": None,
                "order": 1,
            }
            for word in words[:5]:
                attempts.append({**rescue, "keyword": word})

        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_params: set[str] = set()
        last_error: Exception | None = None
        failed = 0
        tried = 0

        def _absorb(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                qid = str(row.get("id") or "")
                if not qid or qid in seen_ids:
                    continue
                if not _usable_question(row):
                    continue
                seen_ids.add(qid)
                merged.append(row)

        def _enough() -> bool:
            return len(merged) >= limit and any(
                _row_on_topic(row, spec) for row in merged
            )

        for params in attempts:
            fingerprint = repr(
                sorted((k, str(v)) for k, v in params.items() if k not in {"course_id", "page"})
            )
            if fingerprint in seen_params:
                continue
            seen_params.add(fingerprint)
            for page in (1, 2):
                if _enough():
                    break
                tried += 1
                try:
                    hits = self._fetch(**{**params, "page": page})
                except Exception as exc:  # noqa: BLE001 - 检索失败要降级，不能打断 quiz
                    last_error = exc
                    failed += 1
                    continue
                if hits:
                    if params.get("keypoint"):
                        _absorb(hits)
                    else:
                        _absorb([row for row in hits if _row_on_topic(row, spec)])
                if page == 1 and _enough():
                    break
            if _enough():
                break
        if last_error is not None and failed == tried:
            raise last_error
        topical = [row for row in merged if _row_on_topic(row, spec)] or merged
        return _mix_topics(topical, spec, limit)


def _has_answer(row: dict[str, Any]) -> bool:
    answer = row.get("correct_answer")
    if isinstance(answer, list):
        return any(str(item).strip() for item in answer)
    return bool(str(answer or "").strip())


def _has_analysis(row: dict[str, Any]) -> bool:
    for key in ("analysis", "idea", "step", "analysis_html"):
        text = str(row.get(key) or "").strip()
        if text and text not in {"（暂无文字解析）", "题库未返回解析。"}:
            return True
    return False


def _usable_question(row: dict[str, Any]) -> bool:
    return _has_analysis(row) and _has_answer(row)


def _mix_topics(rows: list[dict[str, Any]], spec: SearchSpec, limit: int) -> list[dict[str, Any]]:
    """每个对齐到的知识点先留一题，避免整卷都是同一类热门题。"""
    needles = [item.name for item in spec.keypoints] + list(spec.keywords)
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in needles if name}
    other: list[dict[str, Any]] = []
    for row in rows:
        blob = " ".join(
            [
                html_to_text(row.get("content")),
                " ".join(str(item) for item in (row.get("keypoints") or [])),
            ]
        )
        placed = False
        for name in needles:
            if name and name in blob:
                buckets.setdefault(name, []).append(row)
                placed = True
                break
        if not placed:
            other.append(row)
    mixed: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take(row: dict[str, Any]) -> None:
        qid = str(row.get("id") or "")
        if not qid or qid in seen:
            return
        seen.add(qid)
        mixed.append(row)

    while len(mixed) < limit:
        progressed = False
        for name in needles:
            pile = buckets.get(name) or []
            if not pile:
                continue
            take(pile.pop(0))
            progressed = True
            if len(mixed) >= limit:
                return mixed
        if other:
            take(other.pop(0))
            progressed = True
        if not progressed:
            break
    return mixed


def _row_on_topic(row: dict[str, Any], spec: SearchSpec) -> bool:
    blob = " ".join(
        [
            html_to_text(row.get("content")),
            " ".join(str(item) for item in (row.get("keypoints") or [])),
            " ".join(str(item) for item in (row.get("sections") or [])),
        ]
    )
    needles: list[str] = list(spec.keywords)
    needles.extend(item.name for item in spec.keypoints)
    needles.extend(spec.terms)
    if spec.keyword:
        needles.append(spec.keyword)
    for needle in needles:
        text = str(needle or "").strip()
        if len(text) < 2 or _too_generic(text):
            continue
        if text in blob:
            return True
    return False


def search_for_notes(
    notes: str,
    **kwargs: Any,
) -> SearchBundle:
    return ExerciseSearchTool().search_for_notes(notes, **kwargs)


__all__ = [
    "BankQuestion",
    "ExerciseSearchTool",
    "SearchBundle",
    "html_to_text",
    "search_for_notes",
]
