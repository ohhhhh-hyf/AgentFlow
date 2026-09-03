"""检测按人成章、机械小结；只依据当前会议里的称呼，不写死主题词。"""
from __future__ import annotations

import re
from typing import Any

_STATUS = ("已确认", "方向明确", "待验证", "存在分歧", "待跟进", "未形成结论")
_PERSON_CHAPTER = re.compile(
    r"(发言者\s*\d+"
    r"|对.{1,12}的(建议|点评|质询|回应)"
    r"|[\u4e00-\u9fff]{2,3}的(汇报|点评|质询|回应)"
    r"|同事建议|领导点评|各成员汇报)"
)
_TITLE = re.compile(r"[\u4e00-\u9fff]{1,3}(总|经理|老师|总监|主任)")
_SPEAKER = re.compile(r"发言者\s*\d+")


def collect_people(understanding: Any, transcript: str = "") -> list[str]:
    names: list[str] = []

    def _add(raw: object) -> None:
        text = str(raw or "").strip()
        if not text or text in names:
            return
        if text.startswith("发言") or text.startswith("speaker"):
            return
        if 1 <= len(text) <= 12:
            names.append(text)

    if isinstance(understanding, dict):
        for topic in understanding.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for person in topic.get("participants") or []:
                _add(person)
    for match in _TITLE.finditer(transcript or ""):
        _add(match.group(0))
    return names


def topic_headings(minutes_md: str) -> list[str]:
    headings: list[str] = []
    in_topics = False
    for raw in (minutes_md or "").splitlines():
        line = raw.strip()
        if line.startswith("# ") and "主要议题" in line:
            in_topics = True
            continue
        if in_topics and line.startswith("# ") and "主要议题" not in line:
            break
        if in_topics and line.startswith("## "):
            title = line[3:].strip()
            title = re.sub(r"^\d+[\.、．]\s*", "", title)
            if title:
                headings.append(title)
    return headings


def person_chapter_headings(minutes_md: str, people: list[str]) -> list[str]:
    hits: list[str] = []
    for heading in topic_headings(minutes_md):
        if any(name and len(name) >= 2 and name in heading for name in people):
            hits.append(heading)
            continue
        if _PERSON_CHAPTER.search(heading) or _SPEAKER.search(heading):
            hits.append(heading)
    return hits


def _closing_blocks(minutes_md: str) -> list[str]:
    blocks: list[str] = []
    lines = (minutes_md or "").splitlines()
    i = 0
    while i < len(lines):
        if "议题小结" in lines[i] and lines[i].lstrip().startswith("#"):
            chunk: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("#"):
                text = lines[i].strip().lstrip("-* ").strip()
                if text:
                    chunk.append(text)
                i += 1
            if chunk:
                blocks.append("".join(chunk))
            continue
        i += 1
    return blocks


_SENT_CUT = re.compile(r"(?<=[。！？；;])\s*")
_LIST_MARK = re.compile(r"^([-*+]|\d+[\.、．)])\s+")


def _split_points(text: str) -> list[str]:
    body = _LIST_MARK.sub("", (text or "").strip())
    if not body:
        return []
    parts = [item.strip() for item in _SENT_CUT.split(body) if item.strip()]
    return parts or [body]


def bulletize_minutes(minutes_md: str) -> str:
    """把粘在一起的正文拆成 Markdown 列表，不改事实、不动表格和标题。

    内容总结区除外：其正文保持成段文字（段落按行原样保留，不拆句、不加列表符）。
    """
    out: list[str] = []
    in_table = False
    in_summary = False
    for raw in (minutes_md or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("|"):
            in_table = True
            out.append(raw.rstrip())
            continue
        if in_table:
            if not stripped:
                in_table = False
                out.append("")
            else:
                out.append(raw.rstrip())
            continue
        if stripped.startswith("#"):
            in_summary = stripped.lstrip("#").strip() == "内容总结"
            out.append(raw.rstrip())
            continue
        if (
            not stripped
            or stripped.startswith(">")
            or stripped.startswith("---")
        ):
            out.append(raw.rstrip())
            continue
        if in_summary:
            # 内容总结段落：原样保留，不按句号拆行，不加列表符号
            out.append(raw.rstrip())
            continue
        points = _split_points(stripped)
        if len(points) == 1 and stripped.startswith(("-", "*", "+")):
            out.append(f"- {points[0]}")
            continue
        for point in points:
            out.append(f"- {point}")
    text = "\n".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def mechanical_closings(minutes_md: str) -> bool:
    """所有小结都只剩同一个状态词、没有依据时视为机械套话。"""
    blocks = _closing_blocks(minutes_md)
    if len(blocks) < 3:
        return False
    statuses: list[str] = []
    bare = True
    for block in blocks:
        hit = next((label for label in _STATUS if label in block), "")
        if not hit:
            return False
        statuses.append(hit)
        rest = block
        for label in _STATUS:
            rest = rest.replace(label, "")
        rest = re.sub(r"[：:。．.\s]", "", rest)
        if len(rest) >= 8:
            bare = False
    return bare and len(set(statuses)) == 1


__all__ = [
    "bulletize_minutes",
    "collect_people",
    "mechanical_closings",
    "person_chapter_headings",
    "topic_headings",
]
