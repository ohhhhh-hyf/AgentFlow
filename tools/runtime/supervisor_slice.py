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
_WINDOW = 180
_MAX_SLICES = 18
_MAX_SLICE_CHARS = 5500
_MIN_NEEDLE = 4
_MIN_USEFUL = 6

# 泛词表（与 minutes_trace/align.py 的 _GENERIC_MORPHEME 同源）：
# 时间/数量词、会议高频半泛词、抽象后缀、轻动词。
# 用于模糊定位 needle 时剔除高频词，剩余连续中文字符即"信息性片段"。
_GENERIC_MORPHEME = re.compile(
    r"(今年|去年|明年|前年|本|上|下|半|年|月|日|周|季|度|个|次|条|第|"
    r"[0-9一二三四五六七八九十百千万两]|"
    r"验收|整改|跟进|事项|安排|问题|工作|会议|讨论|汇报|情况|内容|"
    r"相关|方面|环节|要求|计划|方案|项目|任务|进度|风险|进行|开展|"
    r"完成|落实|处理|解决|组织|准备|整体|部分|"
    r"意识|思维|能力|程度|水平|方式|方法|作用|意义|目标|目的|"
    r"树立|转变|培养|强调|认为|表示|指出|"
    r"追踪|梳理|评估|判断)"
)


def _informative_runs(text: str, min_len: int = 4) -> list[str]:
    """剔除非中文与泛词后，剩余连续中文字符片段（needle 模糊定位用）。"""
    spaced = _GENERIC_MORPHEME.sub(" ", text or "")
    return [
        part
        for part in re.findall(r"[\u4e00-\u9fff]+", spaced)
        if len(part) >= min_len
    ]


def _fuzzy_fragments(
    needle: str, win: int = 6, step: int = 3, max_frags: int = 6
) -> list[str]:
    """needle 的信息性片段集：泛词剔除后的 runs 切成 6 字滑动窗口。

    长 run 若整体逐字查找，概述改写的任何一字之差都会 miss；
    切成短窗口后单窗口命中率高，多个窗口聚集即可定位。
    """
    runs = _informative_runs(needle, min_len=4)
    frags: list[str] = []
    for run in runs:
        if len(run) <= win:
            frags.append(run)
        else:
            frags.extend(
                run[i : i + win] for i in range(0, len(run) - win + 1, step)
            )
    seen: set[str] = set()
    out: list[str] = []
    for frag in frags:
        if frag in seen:
            continue
        seen.add(frag)
        out.append(frag)
        if len(out) >= max_frags:
            break
    return out


def _fuzzy_locate(text: str, needle: str) -> int:
    """精确 miss 后，用多个信息性片段聚集投票定位（容概述改写的一字之差）。

    每个片段在原文中取前 3 个命中位置；得分 = 400 字符内其他命中
    片段的长度和（多个片段聚集 = 强证据），返回得分最高的位置。
    """
    frags = _fuzzy_fragments(needle)
    if not frags:
        return -1
    positions: list[tuple[int, int]] = []
    for frag in frags:
        start = 0
        for _ in range(3):  # 每片段最多 3 个位置，防高频片段失控
            pos = text.find(frag, start)
            if pos < 0:
                break
            positions.append((len(frag), pos))
            start = pos + 1
    if not positions:
        return -1
    best_pos = positions[0][1]
    best_score = -1
    for _, pos in positions:
        score = sum(
            flen for flen, pos2 in positions if abs(pos2 - pos) <= 400
        )
        if score > best_score:
            best_score = score
            best_pos = pos
    return best_pos


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
    if "记忆摘录" in text or "历史｜" in text:
        # 记忆摘录/历史条目是历史场次内容，不在本次原文中，作 needle 必然 miss
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
        if not matched:
            # 精确 miss（理解层概述改写，措辞与原文不一致）：
            # 用信息性片段聚集投票定位，窗口以定位位置为中心。
            pos = _fuzzy_locate(text, needle)
            if pos >= 0:
                matched = True
                left = max(0, pos - _WINDOW // 4)
                right = min(len(text), pos + len(needle) + _WINDOW)
                spans.append(_snap(text, left, right))
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
    return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))


_REVIEW_LONG_TEXT = 60   # 超过此长度的字符串值截断（只留前 30 字 + 总长标记）
_REVIEW_LARGE_LIST = 8
_REVIEW_HEAD_ITEMS = 6
_REVIEW_TAIL_ITEMS = 2
# 程序内部字段，审核对质量判断没有增量
_REVIEW_DROP_KEYS = frozenset({
    "content_fingerprint",
    "source_chunk_ids",
    "_prereq_of",
    "detail",
    "session_practice_count",
})
_REVIEW_KEEP_ALL_LIST_KEYS = frozenset({
    "actions",
    "action_hints",
    "alignments",
    "cards",
    "decisions",
    "delegated_actions",
    "key_decisions",
    "my_actions",
    "open_questions",
    "risks",
    "risks_and_blockers",
    "risk_hints",
    "sections",
    "topics",
    "unassigned_actions",
})


def _review_compact(node: object, *, key: str = "") -> object:
    """把草稿递归压成「审核用骨架」。

    规则（通用，不依赖具体字段名）：
    - dict 元素列表（结构型如 chapters/topics/cards，条目型如 actions/risks 的
      task/owner 条目）→ 保留全部元素，内部继续压缩——条目必须可见，
      否则「覆盖不足/是否编造」这类核对在条目层面无法执行；
    - 审核关键字段列表（actions/risks/decisions/alignments/sections/cards 等）
      → 保留全部条目，内部压缩，避免 supervisor 看不到具体条目；
    - 普通纯字符串/标量长列表 → 保留前 6 条 + 省略计数 + 后 2 条，
      让审核仍能看到内容样本，而不是只看到一个计数；
    - 长字符串（explain / summary 等）→ 截断为前 30 字并标注总长，
      让审核仍能判断「这段写了多厚」而不必读全文。
    """
    if isinstance(node, dict):
        return {
            k: _review_compact(v, key=str(k))
            for k, v in node.items()
            if k not in _REVIEW_DROP_KEYS
        }
    if isinstance(node, list):
        if not node:
            return node
        if isinstance(node[0], dict) or key in _REVIEW_KEEP_ALL_LIST_KEYS:
            return [_review_compact(x, key=key) for x in node]
        if len(node) <= _REVIEW_LARGE_LIST:
            return [_review_compact(x, key=key) for x in node]
        omitted = len(node) - _REVIEW_HEAD_ITEMS - _REVIEW_TAIL_ITEMS
        head = [_review_compact(x, key=key) for x in node[:_REVIEW_HEAD_ITEMS]]
        tail = [_review_compact(x, key=key) for x in node[-_REVIEW_TAIL_ITEMS:]]
        return head + [f"...（中间 {omitted} 条已省略，共 {len(node)} 条）"] + tail
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
