"""解析高中全量统计：科目/版本/课本、知识点树、题型。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import DEFAULT_DATA_DIR, STAGE_HIGH_SCHOOL

_COURSE_HEAD = re.compile(
    r"^##\s*(.+?)（course_id\s*=\s*(\d+)[，,]\s*subject\s*=\s*(\d+)）"
)
_VERSION_HEAD = re.compile(r"^###\s*(.+?)（version_id\s*=\s*(\d+)）")
_BOOK_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
)
_KP_SUBJECT = re.compile(r"^##\s*(.+?)（\d+\s*个节点）")
_KP_NODE = re.compile(r"^(.*?)（(?:id|textbook_catalog_id)\s*[=:]\s*(\d+)）\s*$")
_TYPE_SUBJECT = re.compile(r"^#{2,3}\s*(.+?)（\d+\s*个）")
_TYPE_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|")
_CHAPTER_SUBJECT = re.compile(r"^##\s*(.+?)（\d+\s*个(?:章节节点|本课本)")
_CHAPTER_BOOK = re.compile(
    r"^###\s*(.+?)\s*/\s*.+?（(?:book_id|textbook_id)\s*=\s*(\d+)"
)
_CHAPTER_NUM = re.compile(r"^[\d.．、\s]+")
_TOPIC_SPLIT = re.compile(r"[的与和或及、，,/\s]+")
_SKIP_TOPIC = {
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
    "综合",
    "类型",
    "关系",
    "图象",
    "变换",
    "求",
    "与",
}


@dataclass(frozen=True)
class Course:
    name: str
    course_id: int
    subject_id: int
    stage_id: int = STAGE_HIGH_SCHOOL


@dataclass(frozen=True)
class Textbook:
    textbook_id: int
    name: str
    grade_id: int
    volume: str
    term: str
    version_id: int
    version_name: str
    course_id: int


@dataclass(frozen=True)
class Version:
    version_id: int
    name: str
    course_id: int
    textbooks: tuple[Textbook, ...] = ()


@dataclass(frozen=True)
class Keypoint:
    kp_id: str
    name: str
    depth: int
    parent_id: str
    subject_name: str
    subject_id: int


@dataclass(frozen=True)
class QuestionType:
    type_id: str
    name: str
    parent_name: str
    subject_name: str
    subject_id: int


@dataclass
class HighSchoolCatalog:
    courses: list[Course] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)
    textbooks: list[Textbook] = field(default_factory=list)
    keypoints: list[Keypoint] = field(default_factory=list)
    question_types: list[QuestionType] = field(default_factory=list)
    _textbook_by_id: dict[int, Textbook] = field(default_factory=dict, repr=False)
    _chapter_index: dict[tuple[int, str], list[int]] = field(
        default_factory=dict, repr=False
    )

    def course_by_name(self, name: str) -> Course | None:
        text = _norm(name)
        for course in self.courses:
            if _norm(course.name) == text:
                return course
        for course in self.courses:
            short = _norm(course.name).removeprefix("高中")
            if short and (short == text or text.endswith(short) or short in text):
                return course
        return None

    def versions_for(self, course_id: int) -> list[Version]:
        return [item for item in self.versions if item.course_id == course_id]

    def keypoints_for_subject(self, subject_id: int) -> list[Keypoint]:
        return [item for item in self.keypoints if item.subject_id == subject_id]

    def types_for_subject(self, subject_id: int) -> list[QuestionType]:
        return [item for item in self.question_types if item.subject_id == subject_id]

    def textbook_by_id(self, textbook_id: int) -> Textbook | None:
        return self._textbook_by_id.get(textbook_id)

    def textbooks_covering(
        self, course_id: int, name: str, *, strict: bool = False
    ) -> list[Textbook]:
        """按课本章节名反查课本：笔记对齐到的知识点会落到这些书上。"""
        keys = _identity_keys(name) if strict else _topic_keys(name)
        ids: list[int] = []
        seen: set[int] = set()
        for key in keys:
            for textbook_id in self._chapter_index.get((course_id, key), ()):
                if textbook_id in seen:
                    continue
                seen.add(textbook_id)
                ids.append(textbook_id)
        return [
            book
            for textbook_id in ids
            if (book := self._textbook_by_id.get(textbook_id)) is not None
        ]

    def index_chapter(self, course_id: int, textbook_id: int, name: str) -> None:
        if not course_id or not textbook_id or not name:
            return
        for key in _topic_keys(name):
            bucket = self._chapter_index.setdefault((course_id, key), [])
            if textbook_id not in bucket:
                bucket.append(textbook_id)


def _norm(text: object) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _identity_keys(name: str) -> list[str]:
    compact = _norm(name)
    stripped = _norm(_CHAPTER_NUM.sub("", name))
    keys: list[str] = []
    seen: set[str] = set()
    for candidate in (compact, stripped, compact.replace("的", ""), stripped.replace("的", "")):
        if len(candidate) < 2 or candidate in seen:
            continue
        seen.add(candidate)
        keys.append(candidate)
    return keys


def _topic_keys(name: str) -> list[str]:
    keys = _identity_keys(name)
    seen = set(keys)
    seed = _norm(_CHAPTER_NUM.sub("", name)) or _norm(name)
    for part in _TOPIC_SPLIT.split(seed):
        token = _norm(part)
        if len(token) < 2 or token in _SKIP_TOPIC or token in seen:
            continue
        seen.add(token)
        keys.append(token)
    return keys


def _heading_name(raw: str) -> str:
    return re.sub(r"（\d+\s*个.*$", "", raw).strip()


def _subject_id_by_course_name(catalog: HighSchoolCatalog, heading: str) -> int:
    course = catalog.course_by_name(heading)
    return course.subject_id if course else 0


def _parse_courses(text: str, catalog: HighSchoolCatalog) -> None:
    course: Course | None = None
    version_name = ""
    version_id = 0
    books: list[Textbook] = []

    def flush_version() -> None:
        nonlocal books
        if course is None or not version_id:
            books = []
            return
        catalog.versions.append(
            Version(
                version_id=version_id,
                name=version_name,
                course_id=course.course_id,
                textbooks=tuple(books),
            )
        )
        catalog.textbooks.extend(books)
        for book in books:
            catalog._textbook_by_id[book.textbook_id] = book
        books = []

    for raw in text.splitlines():
        line = raw.rstrip()
        hit = _COURSE_HEAD.match(line)
        if hit:
            flush_version()
            course = Course(
                name=hit.group(1).strip(),
                course_id=int(hit.group(2)),
                subject_id=int(hit.group(3)),
            )
            catalog.courses.append(course)
            version_name = ""
            version_id = 0
            continue
        hit = _VERSION_HEAD.match(line)
        if hit and course is not None:
            flush_version()
            version_name = hit.group(1).strip()
            version_id = int(hit.group(2))
            continue
        hit = _BOOK_ROW.match(line)
        if hit and course is not None and version_id:
            books.append(
                Textbook(
                    textbook_id=int(hit.group(1)),
                    name=hit.group(2).strip(),
                    grade_id=int(hit.group(3)),
                    volume=hit.group(4).strip(),
                    term=hit.group(5).strip(),
                    version_id=version_id,
                    version_name=version_name,
                    course_id=course.course_id,
                )
            )
    flush_version()


def _parse_keypoints(text: str, catalog: HighSchoolCatalog) -> None:
    subject_name = ""
    subject_id = 0
    stack: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        head = _KP_SUBJECT.match(line)
        if head:
            subject_name = _heading_name(head.group(1))
            subject_id = _subject_id_by_course_name(catalog, subject_name)
            stack = []
            continue
        node = _KP_NODE.match(line)
        if not node or not subject_id:
            continue
        prefix, name_blob = node.group(1), node.group(1)
        kp_id = node.group(2)
        stripped = name_blob.lstrip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            depth = max(hashes - 2, 0)
            name = stripped.lstrip("#").strip()
        elif stripped.startswith(("-", "*")):
            indent = len(prefix) - len(prefix.lstrip(" "))
            depth = indent // 2 + 1
            name = stripped[1:].strip()
        else:
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        parent_id = stack[-1][1] if stack else ""
        catalog.keypoints.append(
            Keypoint(
                kp_id=kp_id,
                name=name,
                depth=depth,
                parent_id=parent_id,
                subject_name=subject_name,
                subject_id=subject_id,
            )
        )
        stack.append((depth, kp_id))


def _parse_types(text: str, catalog: HighSchoolCatalog) -> None:
    subject_name = ""
    subject_id = 0
    for raw in text.splitlines():
        line = raw.rstrip()
        head = _TYPE_SUBJECT.match(line)
        if head:
            subject_name = _heading_name(head.group(1))
            subject_id = _subject_id_by_course_name(catalog, subject_name)
            continue
        row = _TYPE_ROW.match(line)
        if not row or not subject_id:
            continue
        if row.group(1) == "id":
            continue
        parent = row.group(3).strip()
        catalog.question_types.append(
            QuestionType(
                type_id=row.group(1),
                name=row.group(2).strip(),
                parent_name="" if parent in {"-", "—", ""} else parent,
                subject_name=subject_name,
                subject_id=subject_id,
            )
        )


def _parse_chapters(text: str, catalog: HighSchoolCatalog) -> None:
    course_id = 0
    textbook_id = 0
    for raw in text.splitlines():
        line = raw.rstrip()
        head = _CHAPTER_SUBJECT.match(line)
        if head:
            course = catalog.course_by_name(_heading_name(head.group(1)))
            course_id = course.course_id if course else 0
            textbook_id = 0
            continue
        book = _CHAPTER_BOOK.match(line)
        if book:
            textbook_id = int(book.group(2))
            continue
        node = _KP_NODE.match(line)
        if not node or not course_id or not textbook_id:
            continue
        prefix = node.group(1)
        stripped = prefix.lstrip()
        if stripped.startswith("#"):
            name = stripped.lstrip("#").strip()
        elif stripped.startswith(("-", "*")):
            name = stripped[1:].strip()
        else:
            continue
        if name:
            catalog.index_chapter(course_id, textbook_id, name)


def load_catalog(data_dir: Path | None = None) -> HighSchoolCatalog:
    root = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    catalog = HighSchoolCatalog()
    courses_path = root / "01_科目与课本.md"
    points_path = root / "02_知识点.md"
    types_path = root / "03_题型与考试类型.md"
    if not types_path.exists():
        types_path = root / "03_题型.md"
    chapters_path = root / "04_章节.md"
    if courses_path.exists():
        _parse_courses(courses_path.read_text(encoding="utf-8"), catalog)
    if points_path.exists():
        _parse_keypoints(points_path.read_text(encoding="utf-8"), catalog)
    if types_path.exists():
        _parse_types(types_path.read_text(encoding="utf-8"), catalog)
    if chapters_path.exists():
        _parse_chapters(chapters_path.read_text(encoding="utf-8"), catalog)
    return catalog


@lru_cache(maxsize=4)
def default_catalog(data_dir: str | None = None) -> HighSchoolCatalog:
    return load_catalog(Path(data_dir) if data_dir else DEFAULT_DATA_DIR)


__all__ = [
    "Course",
    "HighSchoolCatalog",
    "Keypoint",
    "QuestionType",
    "Textbook",
    "Version",
    "default_catalog",
    "load_catalog",
]
