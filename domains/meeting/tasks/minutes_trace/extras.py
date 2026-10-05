"""从共享上下文里抽出用户关键点、笔记。"""
from __future__ import annotations

import re

from .align import parse_keypoints, parse_notes

_BLOCK = re.compile(
    r"【(用户关键点|用户笔记)】\s*\n(.*?)(?=\n【|\Z)",
    re.S,
)


def parse_trace_extras(context: str) -> dict[str, object]:
    blocks = {name: body.strip() for name, body in _BLOCK.findall(context or "")}
    key_raw = blocks.get("用户关键点") or ""
    note_raw = blocks.get("用户笔记") or ""
    return {
        "keypoints": parse_keypoints(key_raw),
        "notes": parse_notes(note_raw),
        "key_raw": key_raw,
        "note_raw": note_raw,
    }


__all__ = ["parse_trace_extras"]
