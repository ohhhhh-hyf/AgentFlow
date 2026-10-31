"""程序化渲染分段速览 Markdown。"""
from __future__ import annotations

from typing import List

from .models import SectionSummary


def render_markdown(sections: List[SectionSummary]) -> str:
    """按「时间+标题 / 关键词 / 纪要」渲染，段间空一行。"""
    blocks: List[str] = []
    for section in sections:
        lines = [f"{section.time_start}  {section.title}"]
        if section.key_words:
            lines.append("关键词：" + "、".join(section.key_words))
        lines.append(section.section_summary)
        blocks.append("\n".join(lines))

    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


__all__ = ["render_markdown"]
