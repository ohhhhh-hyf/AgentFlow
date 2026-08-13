"""从共享上下文里抽出场景模板包、关键点、笔记。"""
from __future__ import annotations

import re

from .align import parse_keypoints, parse_notes
from .scene import parse_scene_pack

_BLOCK = re.compile(
    r"【(场景模板包|用户关键点|用户笔记)】\s*\n(.*?)(?=\n【|\Z)",
    re.S,
)


def parse_trace_extras(context: str) -> dict[str, object]:
    blocks = {name: body.strip() for name, body in _BLOCK.findall(context or "")}
    pack_raw = blocks.get("场景模板包") or ""
    key_raw = blocks.get("用户关键点") or ""
    note_raw = blocks.get("用户笔记") or ""
    return {
        "pack": parse_scene_pack(pack_raw),
        "pack_raw": pack_raw,
        "keypoints": parse_keypoints(key_raw),
        "notes": parse_notes(note_raw),
        "key_raw": key_raw,
        "note_raw": note_raw,
    }


def understanding_src(context: str) -> str:
    """给场景分类用的短输入：优先会议理解，其次原文头。"""
    text = context or ""
    for marker in ("会议理解：", "已审核会议理解："):
        if marker in text:
            chunk = text.split(marker, 1)[1]
            for stop in ("\n用户", "\n原文", "\n【"):
                if stop in chunk:
                    chunk = chunk.split(stop, 1)[0]
            return chunk.strip()[:2000]
    if "原文：" in text:
        return text.split("原文：", 1)[1].strip()[:2000]
    return text[:2000]


__all__ = ["parse_trace_extras", "understanding_src"]
