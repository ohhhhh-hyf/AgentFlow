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
        for sp in understanding.get("speakers") or []:
            if isinstance(sp, dict):
                _add(sp.get("name"))
            else:
                _add(sp)
        for hint in understanding.get("action_hints") or []:
            if isinstance(hint, dict):
                _add(hint.get("owner"))
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
    lines = (minutes_md or "").splitlines()
    has_legacy_topics = any(line.strip().startswith("# ") and "主要议题" in line for line in lines)
    in_legacy_topics = False

    for raw in lines:
        line = raw.strip()
        if has_legacy_topics:
            if line.startswith("# ") and "主要议题" in line:
                in_legacy_topics = True
                continue
            if in_legacy_topics and line.startswith("# ") and "主要议题" not in line:
                break
            if in_legacy_topics and line.startswith("## "):
                title = line[3:].strip()
                title = re.sub(r"^\d+[\.、．]\s*", "", title)
                if title:
                    headings.append(title)
        else:
            if line.startswith(("## ", "### ")):
                title = line.lstrip("#").strip()
                title = re.sub(r"^\d+[\.、．]\s*", "", title)
                if title and not any(k in title for k in ("会议概况", "会议概述", "内容总结", "关键决策", "行动项", "会议结论")):
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
        # 场景模板里小结标题名不一（议题小结/话题小结/类别小结），统一按「小结」收
        if "小结" in lines[i] and lines[i].lstrip().startswith("#"):
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

    会议概况 / 内容总结区除外：其正文保持成段文字（段落按行原样保留，不拆句、不加列表符）。
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
            sec_name = stripped.lstrip("#").strip()
            in_summary = any(k in sec_name for k in ("内容总结", "会议概况", "会议概述", "全景概览"))
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
            # 会议概况/内容总结段落：原样保留，不按句号拆行，不加列表符号
            out.append(raw.rstrip())
            continue
        if stripped.startswith(("-", "*", "+")):
            out.append(stripped)
            continue
        points = _split_points(stripped)
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
