"""Markdown 纪要 → 稳定 section 树（多级自适应语义切分版）。

不仅支持扁平标题，更能智能识别容器型主章节（如“要点梳理”、“主要议题”），
将真正承载讨论内容的子议题提升为独立的实质 SectionNode。
确保 100% 原始 Markdown 完整保真，不丢行、不改字。
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


def parse_minutes(markdown: str) -> ParsedMinutes:
    """自适应解析出实质性章节。

    - 存在容器型章节（如 ## 要点梳理 下包含多个 ### 子议题）时，自动将子议题提升为独立评判单元；
    - 扁平章节保持原样切分；
    - 100% 原始 Markdown 行无损保留。
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

    # 确定基准层级
    levels = {level for _, level, _ in headings}
    base_level = 2 if 2 in levels else min(levels)

    document_title = next(
        (title for _, level, title in headings if level == 1 and title),
        headings[0][2] if headings else "图文纪要",
    )

    # 自适应提取实质性 section 边界
    # 策略：扫描 base_level 标题，若该标题下包含 >= 2 个 base_level + 1 子标题，
    # 则将子标题提升为独立 section（容器标题附属在首个子标题顶部）
    sections_meta: list[tuple[int, int, str, list[str]]] = []
    i = 0
    while i < len(headings):
        line, level, title = headings[i]
        if level == base_level:
            children = []
            j = i + 1
            while j < len(headings) and headings[j][1] > base_level:
                if headings[j][1] == base_level + 1:
                    children.append((headings[j][0], headings[j][1], headings[j][2]))
                j += 1

            if len(children) >= 2:
                # 容器型标题：提升子标题为独立 section
                for c_idx, (c_line, c_level, c_title) in enumerate(children):
                    sec_start = line if c_idx == 0 else c_line
                    sec_path = [title, c_title]
                    sections_meta.append((sec_start, c_level, c_title, sec_path))
                i = j
                continue
            else:
                sections_meta.append((line, level, title, [title]))
                i += 1
        elif level < base_level:
            # 高于基准层级（如单独的 H1 标题）
            sections_meta.append((line, level, title, [title]))
            i += 1
        else:
            # 孤立的深层标题
            sections_meta.append((line, level, title, [title]))
            i += 1

    if not sections_meta:
        sections_meta = [(headings[0][0], headings[0][1], headings[0][2], [headings[0][2]])]

    # 计算前导文本（Preamble）
    first_sec_line = sections_meta[0][0]
    preamble = "\n".join(lines[:first_sec_line]).strip()

    # 构建连续且无损的 SectionNode 列表
    sections: List[SectionNode] = []
    for order, (start, level, title, path) in enumerate(sections_meta):
        next_start = (
            sections_meta[order + 1][0]
            if order + 1 < len(sections_meta)
            else len(lines)
        )
        raw = "\n".join(lines[start:next_start]).strip()
        sections.append(
            SectionNode(
                section_id=f"s{order + 1}",
                heading=title,
                level=level,
                path=path,
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
