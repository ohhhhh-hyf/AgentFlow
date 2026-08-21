"""审核上下文：按草稿事实点切原文，避免整本再喂一遍。

原文仍是最高事实来源，只把审核需要对的句子送进去。
短原文不切；对不上足够事实点时回退到文首文末，避免误判。
"""
from __future__ import annotations

import json
import re

_SKIP_EXACT = {
    "high",
    "medium",
    "low",
    "explicit",
    "inferred",
    "approve",
    "revise",
    "reject",
    "pass",
    "fail",
    "true",
    "false",
    "null",
    "none",
    "objective",
    "personal",
    "commitment",
    "assignment",
    "directive",
    "rectification",
    "followup",
}
_SKIP_PREFIX = ("kp_", "ch_", "tp_")
_FULL_TRANSCRIPT_LIMIT = 3600
_WINDOW = 280
_MAX_SLICES = 18
_MAX_SLICE_CHARS = 9000
_MIN_NEEDLE = 4
_MIN_USEFUL = 6


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _is_useful_needle(text: str) -> bool:
    if len(text) < _MIN_NEEDLE:
        return False
    low = text.lower()
    if low in _SKIP_EXACT:
        return False
    if any(low.startswith(p) for p in _SKIP_PREFIX):
        return False
    if text.isdigit() and len(text) < 4:
        return False
    if re.fullmatch(r"[A-Za-z_]+", text) and len(text) < 8:
        return False
    return True


def collect_needles(value: object, *, limit: int = 80) -> list[str]:
    """从草稿/理解里抽出可回原文定位的短语，长的优先。"""
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        text = _clean(raw)
        if not _is_useful_needle(text):
            return
        if len(text) > 160:
            text = text[:160]
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        found.append(text)

    def walk(node: object, key_hint: str = "") -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                walk(child, str(key))
            return
        if isinstance(node, list):
            for child in node:
                walk(child, key_hint)
            return
        if isinstance(node, str):
            hint = (key_hint or "").lower()
            if hint in {"evidence", "source", "task", "risk", "action", "quote"}:
                add(node)
            elif hint in {"owner", "deadline", "title", "name"}:
                add(node)
            elif len(_clean(node)) >= _MIN_USEFUL:
                add(node)

    walk(value)
    found.sort(key=len, reverse=True)
    return found[:limit]


def _snap(text: str, start: int, end: int) -> tuple[int, int]:
    left = text.rfind("\n", 0, start)
    if left >= 0 and start - left < 80:
        start = left + 1
    right_nl = text.find("\n", end)
    if 0 <= right_nl - end < 80:
        end = right_nl
    for mark in ("。", "！", "？", ".", ";", "；"):
        pos = text.rfind(mark, max(0, start - 40), start)
        if pos >= 0:
            start = pos + 1
            break
    for mark in ("。", "！", "？", ".", ";", "；"):
        pos = text.find(mark, end, min(len(text), end + 40))
        if pos >= 0:
            end = pos + 1
            break
    return max(0, start), min(len(text), end)


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [spans[0]]
    for start, end in spans[1:]:
        prev_s, prev_e = out[-1]
        if start <= prev_e + 40:
            out[-1] = (prev_s, max(prev_e, end))
        else:
            out.append((start, end))
    return out


def slice_transcript(transcript: str, needles: list[str]) -> tuple[str, int, int]:
    """按短语回原文取窗口。返回 (摘录文本, 命中条数, 使用的原文跨度)。"""
    text = transcript or ""
    if not text.strip():
        return "", 0, 0
    if len(text) <= _FULL_TRANSCRIPT_LIMIT:
        return text, len(needles), len(text)

    spans: list[tuple[int, int]] = []
    hits = 0
    for needle in needles:
        start = 0
        matched = False
        while True:
            pos = text.find(needle, start)
            if pos < 0:
                break
            matched = True
            left = max(0, pos - _WINDOW // 4)
            right = min(len(text), pos + len(needle) + _WINDOW)
            spans.append(_snap(text, left, right))
            start = pos + max(len(needle), 1)
            if len(spans) >= _MAX_SLICES * 2:
                break
        if matched:
            hits += 1
        if len(spans) >= _MAX_SLICES * 2:
            break

    useful = [n for n in needles if len(n) >= _MIN_USEFUL]
    if useful and hits * 3 < len(useful):
        head = min(1600, len(text))
        tail = max(head, len(text) - 1600)
        spans.append((0, head))
        if tail < len(text):
            spans.append((tail, len(text)))

    merged = _merge_spans(spans)[:_MAX_SLICES]
    if not merged:
        keep = min(2400, len(text))
        return text[:keep], 0, keep

    parts: list[str] = []
    used = 0
    for i, (start, end) in enumerate(merged, start=1):
        chunk = text[start:end].strip()
        if not chunk:
            continue
        if used + len(chunk) > _MAX_SLICE_CHARS:
            remain = _MAX_SLICE_CHARS - used
            if remain < 80:
                break
            chunk = chunk[:remain].rstrip()
        used += len(chunk)
        parts.append(f"【原文摘录 {i}】\n{chunk}")
        if used >= _MAX_SLICE_CHARS:
            break
    return "\n\n".join(parts), hits, used


def summarize_understanding(understanding: object) -> str:
    """压缩核心理解：只留导航字段，不把讨论全文再贴一遍。"""
    if not isinstance(understanding, dict) or not understanding:
        return ""
    lines: list[str] = []
    purpose = _clean(
        understanding.get("meeting_purpose") or understanding.get("note_purpose")
    )
    if purpose:
        lines.append(f"目的：{purpose}")
    scene = _clean(understanding.get("scene"))
    if scene:
        lines.append(f"场景：{scene}")

    topics = understanding.get("topics") or understanding.get("sections") or []
    if isinstance(topics, list):
        titles: list[str] = []
        for item in topics[:16]:
            if not isinstance(item, dict):
                continue
            title = _clean(item.get("title"))
            if not title:
                continue
            conclusion = _clean(item.get("conclusion") or item.get("summary"))
            titles.append(f"{title}（{conclusion}）" if conclusion else title)
        if titles:
            lines.append("议题/章节：" + "；".join(titles))

    for label, key in (
        ("结论", "decisions"),
        ("未决", "open_questions"),
        ("风险摘要", "risks"),
        ("术语", "key_terms"),
    ):
        items = understanding.get(key) or []
        if isinstance(items, list):
            cleaned = [_clean(x) for x in items[:12] if _clean(x)]
            if cleaned:
                lines.append(f"{label}：" + "；".join(cleaned))

    hints = understanding.get("action_hints") or []
    if isinstance(hints, list):
        bits = []
        for item in hints[:16]:
            if not isinstance(item, dict):
                continue
            action = _clean(item.get("action"))
            if not action:
                continue
            owner = _clean(item.get("owner"))
            bits.append(f"{action}" + (f"（{owner}）" if owner else ""))
        if bits:
            lines.append("行动线索：" + "；".join(bits))

    risks = understanding.get("risk_hints") or []
    if isinstance(risks, list):
        bits = []
        for item in risks[:12]:
            if isinstance(item, dict):
                risk = _clean(item.get("risk"))
                if risk:
                    bits.append(risk)
        if bits:
            lines.append("风险线索：" + "；".join(bits))
    return "\n".join(lines)


def compact_profile(profile: object, *, empty_ok: bool = True) -> str:
    if not isinstance(profile, dict) or not profile:
        return "" if empty_ok else "{}"
    keep = (
        "name",
        "role",
        "perspective",
        "persona_type",
        "responsibilities",
        "interests",
        "focus_areas",
        "principles",
        "constraints",
        "output_style",
    )
    slim = {key: profile.get(key) for key in keep if profile.get(key) not in (None, "", [])}
    if not slim:
        return ""
    return json.dumps(slim, ensure_ascii=False)


def compact_perspective(profile: object) -> str:
    if not isinstance(profile, dict) or not profile:
        return ""
    keep = (
        "name",
        "inferred_role",
        "personal_summary",
        "attention_points",
        "responsibilities",
        "possible_actions",
        "concerns",
        "relevant_topics",
    )
    slim = {key: profile.get(key) for key in keep if profile.get(key) not in (None, "", [])}
    if not slim:
        return ""
    return json.dumps(slim, ensure_ascii=False, indent=2)


_REVIEW_LONG_TEXT = 60   # 超过此长度的字符串值截断（只留前 30 字 + 总长标记）
_REVIEW_LARGE_LIST = 8   # 内容型列表超过此条数改为计数（审核仍能核对"条数/厚薄"）


def _review_compact(node: object) -> object:
    """把草稿递归压成「审核用骨架」。

    规则（通用，不依赖具体字段名）：
    - 结构型列表（元素是含 id/name/kp_id 的 dict，如 chapters/topics/cards）
      → 保留全部元素，内部继续压缩；
    - 内容型列表（如 key_facts / items / 纯字符串列表）→ 短列表全留，长列表改为计数；
    - 长字符串（explain / summary 等）→ 截断为前 30 字并标注总长，
      让审核仍能判断「这段写了多厚」而不必读全文。
    """
    if isinstance(node, dict):
        return {k: _review_compact(v) for k, v in node.items()}
    if isinstance(node, list):
        if not node:
            return node
        if isinstance(node[0], dict) and (
            node[0].get("id") or node[0].get("name") or node[0].get("kp_id")
        ):
            return [_review_compact(x) for x in node]
        if len(node) <= _REVIEW_LARGE_LIST:
            return [_review_compact(x) for x in node]
        return [f"...（{len(node)} 条，已省略）"]
    if isinstance(node, str):
        if len(node) <= _REVIEW_LONG_TEXT:
            return node
        return node[:30] + f"...（共 {len(node)} 字）"
    return node


def compact_draft_for_review(draft: object) -> object:
    """supervisor 审核用草稿摘要：保留结构骨架与短字段，
    压缩大文本/大列表，显著降低审核输入 token 且不丢核对要素。"""
    return _review_compact(draft)


__all__ = [
    "collect_needles",
    "compact_draft_for_review",
    "compact_perspective",
    "compact_profile",
    "slice_transcript",
    "summarize_understanding",
]
