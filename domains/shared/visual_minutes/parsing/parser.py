"""Markdown 纪要 → 稳定 section 树。

只使用基础 Markdown 结构，不依赖具体业务标题或内容。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from markdown_it import MarkdownIt


@dataclass
class SectionNode:
    section_id: str
    heading: str
    level: int
    path: List[str]
    order: int
    markdown: str
    plain_text: str
    start_line: int
    end_line: int


@dataclass
class ParsedMinutes:
    document_title: str
    preamble_markdown: str
    sections: List[SectionNode] = field(default_factory=list)


def _plain_text(markdown: str) -> str:
    """粗粒度去 Markdown 标记，供 Planner 判断，不进入最终正文。"""
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[#>*+\-\d.\s]+", "", text, flags=re.M)
    text = re.sub(r"[*_~|]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _headings(markdown: str) -> list[tuple[int, int, str]]:
    """返回 (行号, 层级, 标题文本)。"""
    md = MarkdownIt("commonmark")
    tokens = md.parse(markdown)
    out: list[tuple[int, int, str]] = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or not token.map:
            continue
        title = ""
        if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
            title = tokens[i + 1].content.strip()
        out.append((token.map[0], int(token.tag[1]), title))
    return out


def _heading_paths(
    headings: list[tuple[int, int, str]],
    primary_level: int,
) -> dict[int, list[str]]:
    """按标题层级推导每个主 section 的祖先路径。"""
    stack: list[tuple[int, str]] = []
    paths: dict[int, list[str]] = {}
    for line, level, title in headings:
        while stack and stack[-1][0] >= level:
            stack.pop()
        if level == primary_level:
            paths[line] = [t for _, t in stack if t] + [title]
        stack.append((level, title))
    return paths


def parse_minutes(markdown: str) -> ParsedMinutes:
    """解析出主章节（存在 h2 时以 h2 为主，否则使用最浅标题）。

    子标题内容归入其所属主章节，保证每个主章节的 Markdown 连续、完整。
    """
    text = markdown or ""
    lines = text.splitlines()
    headings = _headings(text)

    if not headings and not text.strip():
        return ParsedMinutes(
            document_title="图文纪要",
            preamble_markdown="",
            sections=[],
        )

    if not headings:
        section = SectionNode(
            section_id="s1",
            heading="全文",
            level=1,
            path=["全文"],
            order=0,
            markdown=text.strip(),
            plain_text=_plain_text(text),
            start_line=0,
            end_line=len(lines),
        )
        return ParsedMinutes(
            document_title="图文纪要",
            preamble_markdown="",
            sections=[section],
        )

    levels = {level for _, level, _ in headings}
    primary_level = 2 if 2 in levels else min(levels)
    primary = [h for h in headings if h[1] == primary_level]

    document_title = next(
        (title for _, level, title in headings if level == 1 and title),
        primary[0][2] if primary else "图文纪要",
    )
    first_primary_line = primary[0][0] if primary else headings[0][0]
    preamble = "\n".join(lines[:first_primary_line]).strip()
    paths = _heading_paths(headings, primary_level)

    sections: List[SectionNode] = []
    for order, (start, level, title) in enumerate(primary):
        next_start = primary[order + 1][0] if order + 1 < len(primary) else len(lines)
        raw = "\n".join(lines[start:next_start]).strip()
        sections.append(
            SectionNode(
                section_id=f"s{order + 1}",
                heading=title,
                level=level,
                path=paths.get(start, [title]),
                order=order,
                markdown=raw,
                plain_text=_plain_text(raw),
                start_line=start,
                end_line=next_start,
            )
        )

    return ParsedMinutes(
        document_title=document_title or "图文纪要",
        preamble_markdown=preamble,
        sections=sections,
    )


__all__ = ["ParsedMinutes", "SectionNode", "parse_minutes"]
