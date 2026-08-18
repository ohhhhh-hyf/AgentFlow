"""入库资料角色与标题层级。

资料（课件/讲义）定目录骨架，笔记做覆盖，老师划重点只标重点，不单独当骨架。
"""
from __future__ import annotations

import re
from pathlib import Path

ROLE_MATERIAL = "material"
ROLE_NOTES = "notes"
ROLE_TEACHER = "teacher"

_TEACHER_MARKS = ("teacher", "划重点", "focus", "最后一课")
_NOTES_MARKS = ("note", "笔记", "notebook", "错题本")

_CHAPTER = re.compile(
    r"^(?:#{1,2}\s+)?第[一二三四五六七八九十百零0-9]+章\s*[：:\s]*(.+)$"
)
_SECTION = re.compile(
    r"^(?:#{1,3}\s+)?(?:第[一二三四五六七八九十百零0-9]+节|[一二三四五六七八九十]+、)\s*(.+)$"
)
_MD_HEAD = re.compile(r"^(#{1,4})\s+(.+)$")
_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(.+)$")


def classify_source_role(filename: str) -> str:
    name = Path(filename or "").name.lower()
    stem = Path(filename or "").stem.lower()
    blob = f"{name} {stem}"
    if any(mark in blob for mark in _TEACHER_MARKS):
        return ROLE_TEACHER
    if any(mark in blob for mark in _NOTES_MARKS):
        return ROLE_NOTES
    return ROLE_MATERIAL


def heading_level(line: str) -> tuple[int, str] | None:
    """返回 (层级, 标题)。1=章, 2=主题, 3=知识点候选。"""
    text = " ".join(str(line or "").split()).strip()
    if not text or len(text) > 80:
        return None
    md = _MD_HEAD.match(text)
    if md:
        return min(len(md.group(1)), 3), md.group(2).strip()
    chapter = _CHAPTER.match(text)
    if chapter:
        title = chapter.group(1).strip() or text
        return 1, title
    section = _SECTION.match(text)
    if section:
        return 2, section.group(1).strip()
    numbered = _NUM_HEAD.match(text)
    if numbered:
        depth = numbered.group(1).count(".") + 1
        return min(depth, 3), numbered.group(2).strip()
    return None


def outline_from_text(text: str, *, source: str = "", role: str = "") -> list[dict[str, str]]:
    """从正文抽标题路径，供入库元数据和 catalog 骨架。"""
    chapter = ""
    topic = ""
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in str(text or "").splitlines():
        hit = heading_level(raw)
        if not hit:
            continue
        level, title = hit
        if not title:
            continue
        if level == 1:
            chapter = title
            topic = ""
        elif level == 2:
            topic = title
        key = (chapter, topic, title if level >= 3 else "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source": source,
                "role": role or classify_source_role(source),
                "chapter": chapter,
                "topic": topic,
                "heading": title,
                "level": str(level),
            }
        )
    return rows
