"""程序化渲染分段速览 Markdown。"""
from __future__ import annotations

from typing import List

from .models import SectionSummary


def _hard_break(line: str) -> str:
    """Markdown 的单个换行是软换行，行尾补两个空格才会渲染成换行。"""
    return f"{line}  "


def render_markdown(sections: List[SectionSummary]) -> str:
    """按「时间+标题(加粗) / 关键词(加粗) / 纪要(引用竖线)」渲染，段间空一行。"""
    blocks: List[str] = []
    for section in sections:
        lines = [_hard_break(f"**{section.time_start}  {section.title}**")]
        if section.key_words:
            lines.append(_hard_break(f"**关键词：{'、'.join(section.key_words)}**"))
        summary_raw = (section.section_summary or "").strip()
        if summary_raw:
            summary_lines = summary_raw.splitlines()
            quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in summary_lines)
            lines.append(quoted)
        blocks.append("\n".join(lines))

    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


__all__ = ["render_markdown"]
