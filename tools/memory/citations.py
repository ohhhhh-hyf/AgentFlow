"""Reusable memory citations for rendered Markdown outputs.

The functions here do not decide whether memory is true for the current run.
They only make already-injected memory visible: matching output lines receive a
small citation marker, and the used historical snippets are appended at the end.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

try:
    from .meeting import parse_recall_from_text
except Exception:  # pragma: no cover - keeps this module importable during scaffolding
    parse_recall_from_text = None  # type: ignore[assignment]


SECTION_TITLE = "历史记忆引用"
_MEMORY_SECTION_RE = re.compile(r"\n-{3,}\n\n## 历史记忆引用\b.*\Z", re.S)
_HAN = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_TAG_RE = re.compile(r"(?:<sup>)?\[记忆\d+\]\(#memory-\d+\)(?:</sup>)?|class=\"memory-link\"")
_DISPLAY_RE = re.compile(r"记忆摘录〔([^〕]+)〕：([^。\n]+(?:。|$))")
_SOURCE_RE = re.compile(
    r"^- 〔([^〕]+)〕(.+?)(?:｜场次：(第\d+场|未定位))?｜会议：(.+?)｜时间：(.+)$"
)
_LOW_VALUE_KINDS = {"目的", "场次"}


@dataclass(frozen=True)
class MemoryReference:
    """A historical memory snippet that can be cited from rendered text."""

    ref_id: str
    entity: str
    text: str
    source: str = "历史项目记忆"
    kind: str = "历史片段"
    meeting_title: str = ""
    meeting_time: str = ""
    session_label: str = ""


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


_SESSION_TAIL_RE = re.compile(r"（第\d+场）$")


def _split_kind(text: str) -> tuple[str, str]:
    body = _SESSION_TAIL_RE.sub("", _clean(text)).strip()
    for sep in ("：", ":"):
        if sep not in body:
            continue
        head, tail = body.split(sep, 1)
        head = _clean(head)
        tail = _clean(tail)
        if 1 <= len(head) <= 8 and tail:
            return head, tail
    return "历史片段", body


def _source_key(entity: str, kind: str, text: str) -> tuple[str, str, str]:
    return (_clean(entity), _clean(kind), _clean(text))


def _prune_references(refs: list["MemoryReference"], limit: int) -> list["MemoryReference"]:
    if not refs:
        return []
    specific = [ref for ref in refs if ref.kind not in _LOW_VALUE_KINDS]
    pool = specific or refs
    return pool[:limit]


def _extract_source_index(
    context: str,
) -> dict[tuple[str, str, str], tuple[str, str, str]]:
    raw = context or ""
    marker = "【记忆来源索引】"
    if marker not in raw:
        return {}
    chunk = raw.split(marker, 1)[1]
    out: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("【"):
            break
        match = _SOURCE_RE.match(stripped)
        if not match:
            continue
        entity = _clean(match.group(1))
        kind, body = _split_kind(match.group(2))
        slot = _clean(match.group(3) or "")
        title = _clean(match.group(4))
        at = _clean(match.group(5))
        out[_source_key(entity, kind, body)] = (title, at, slot)
    return out


def _han_ngrams(text: str, size: int = 3) -> set[str]:
    chars = "".join(ch for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")
    if len(chars) < size:
        return {chars} if chars else set()
    return {chars[i : i + size] for i in range(len(chars) - size + 1)}


def _related(left: str, right: str) -> bool:
    """判断正文行与记忆片段是否可能相关（保守，宁漏勿滥）。

    只接受强信号，避免弱相关被误标：
    - 整句互相包含且足够长（≥8 字）
    - 长分句（≥8 字）互相包含
    - 共享 ≥6 字的连续汉字片段
    不再接受：4 字短块互相包含、3-gram 重叠、拉丁术语任意出现。
    """
    a, b = _clean(left), _clean(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) >= 8
    a_terms = [x for x in re.split(r"[，。；;、\s]+", a) if len(x) >= 8]
    b_terms = [x for x in re.split(r"[，。；;、\s]+", b) if len(x) >= 8]
    if any(x in b or y in a for x in a_terms for y in b_terms):
        return True
    # 6 字连续汉字 n-gram 重叠（size=6，替代旧 3-gram 宽松判定）
    if len(_han_ngrams(a, size=6) & _han_ngrams(b, size=6)) >= 1:
        return True
    return False


def extract_memory_references(context: str, *, limit: int = 24) -> list[MemoryReference]:
    """Extract citeable memory snippets from a line_extra/shared context string."""
    if not (context or "").strip() or parse_recall_from_text is None:
        return []
    refs: list[MemoryReference] = []
    seen: set[tuple[str, str]] = set()
    source_index = _extract_source_index(context)
    for hit in parse_recall_from_text(context):
        entity = _clean(hit.get("entity")) or "项目"
        for item in hit.get("history") or []:
            text = _clean(item)
            if not text:
                continue
            kind, body = _split_kind(text)
            meeting_title, meeting_time, session_label = source_index.get(
                _source_key(entity, kind, body),
                ("", "", ""),
            )
            marker = (entity, text)
            if marker in seen:
                continue
            seen.add(marker)
            refs.append(
                MemoryReference(
                    ref_id=f"memory-{len(refs) + 1}",
                    entity=entity,
                    text=body,
                    kind=kind,
                    meeting_title=meeting_title,
                    meeting_time=meeting_time,
                    session_label=session_label,
                )
            )
            if len(refs) >= limit * 2:
                return _prune_references(refs, limit)
    return _prune_references(refs, limit)


def _extract_display_references(
    markdown: str,
    offset: int = 0,
    *,
    limit: int = 24,
    source_index: dict[tuple[str, str, str], tuple[str, str, str]] | None = None,
) -> list[MemoryReference]:
    refs: list[MemoryReference] = []
    seen: set[tuple[str, str]] = set()
    for match in _DISPLAY_RE.finditer(markdown or ""):
        entity = _clean(match.group(1)) or "项目"
        text = _clean(match.group(2))
        if not text:
            continue
        kind, body = _split_kind(text)
        meeting_title, meeting_time, session_label = (source_index or {}).get(
            _source_key(entity, kind, body),
            ("", "", ""),
        )
        marker = (entity, text)
        if marker in seen:
            continue
        seen.add(marker)
        refs.append(
            MemoryReference(
                ref_id=f"memory-{offset + len(refs) + 1}",
                entity=entity,
                text=body,
                kind=kind,
                meeting_title=meeting_title,
                meeting_time=meeting_time,
                session_label=session_label,
            )
        )
        if len(refs) >= limit * 2:
            break
    return _prune_references(refs, limit)


def _is_citeable_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "|", "```", "<a ")):
        return False
    if stripped in {"---", "***", "___"}:
        return False
    return True


def _underline_line(line: str, ref_id: str) -> str:
    label = escape(line, quote=False)
    return f'<a href="#{ref_id}" class="memory-link"><u>{label}</u></a>'


_MIN_ANCHOR = 8
_MAX_ANCHOR = 22


def _clip_anchor(text: str) -> str:
    """把锚点收到上限内，且不从拉丁词中间切断。"""
    text = _clean(text)
    if len(text) <= _MAX_ANCHOR:
        return text
    cut = text[:_MAX_ANCHOR]
    if re.search(r"[A-Za-z0-9_\-]$", cut) and re.match(r"[A-Za-z0-9_\-]", text[_MAX_ANCHOR:]):
        trimmed = re.sub(r"[A-Za-z0-9_\-]+$", "", cut).rstrip()
        if len(trimmed) >= _MIN_ANCHOR:
            return trimmed
    return cut


def _exact_span(line: str, needle: str) -> tuple[int, int] | None:
    needle = _clip_anchor(needle)
    if len(needle) < _MIN_ANCHOR:
        return None
    idx = line.find(needle)
    if idx < 0:
        return None
    return idx, idx + len(needle)


def _best_span(line: str, ref: MemoryReference) -> tuple[int, int] | None:
    """在正文行里找短锚点：连续原文，长度 8–22 字，禁止跨半句散标。"""
    ref_text = _clean(ref.text)
    if not line or not ref_text:
        return None
    candidates: list[str] = []
    for chunk in re.split(r"[，。；;、\s]+", ref_text):
        chunk = _clean(chunk)
        if len(chunk) >= _MIN_ANCHOR:
            candidates.append(_clip_anchor(chunk))
    if len(ref_text) >= _MIN_ANCHOR:
        candidates.append(_clip_anchor(ref_text))
    candidates.extend(
        token for token in _LATIN_TERM.findall(ref_text) if _MIN_ANCHOR <= len(token) <= _MAX_ANCHOR
    )
    seen: set[str] = set()
    ordered: list[str] = []

    def _anchor_rank(cand: str) -> tuple[int, int]:
        has_han = 1 if any("\u4e00" <= ch <= "\u9fff" for ch in cand) else 0
        return (has_han, len(cand))

    for cand in sorted(candidates, key=_anchor_rank, reverse=True):
        if cand and cand not in seen:
            seen.add(cand)
            ordered.append(cand)
    for cand in ordered:
        span = _exact_span(line, cand)
        if span:
            return span

    right = "".join(ch for ch in ref_text if "\u4e00" <= ch <= "\u9fff")
    for size in range(min(_MAX_ANCHOR, len(right)), _MIN_ANCHOR - 1, -1):
        for i in range(0, len(right) - size + 1):
            cand = right[i : i + size]
            span = _exact_span(line, cand)
            if span:
                return span
    return None


def _append_markers(
    line: str,
    refs: list[MemoryReference],
    already_used: set[str],
) -> tuple[str, list[str]]:
    if not refs or _TAG_RE.search(line):
        return line, []
    hits = [
        ref
        for ref in refs
        if ref.ref_id not in already_used and _related(line, ref.text)
    ]
    if not hits:
        return line, []
    spans: list[tuple[int, int, MemoryReference]] = []
    for ref in hits:
        span = _best_span(line, ref)
        if span is None:
            continue
        start, end = span
        if end <= start:
            continue
        if any(not (end <= s or start >= e) for s, e, _ in spans):
            continue
        spans.append((start, end, ref))
        if len(spans) >= 2:
            break
    if not spans:
        return line, []
    spans.sort(key=lambda item: item[0])
    out: list[str] = []
    pos = 0
    used: list[str] = []
    for start, end, ref in spans:
        out.append(escape(line[pos:start], quote=False))
        label = escape(line[start:end], quote=False)
        out.append(
            f'<a href="#{ref.ref_id}" class="memory-link"><u>{label}</u></a>'
        )
        used.append(ref.ref_id)
        pos = end
    out.append(escape(line[pos:], quote=False))
    return "".join(out), used


def apply_memory_citations(markdown: str, context: str) -> str:
    """Annotate rendered Markdown with memory citations and append references.

    This is intentionally deterministic and conservative. It never changes the
    factual wording of the output; it only appends citation markers.
    """
    text = _MEMORY_SECTION_RE.sub("", markdown or "").strip()
    source_index = _extract_source_index(context)
    refs = extract_memory_references(context)
    if not refs:
        refs = _extract_display_references(context, source_index=source_index)
    if not refs:
        refs = _extract_display_references(text)
    if not text or not refs:
        return markdown

    used: list[str] = []
    by_id = {ref.ref_id: ref for ref in refs}
    lines: list[str] = []
    for line in text.splitlines():
        if _is_citeable_line(line):
            line, ids = _append_markers(line, refs, set(used))
            for ref_id in ids:
                if ref_id not in used:
                    used.append(ref_id)
        lines.append(line)

    # 记忆确实命中（refs 非空）但正文没有任何可精确锚定的行时，
    # 把摘要开头的「记忆命中：…」声明行本身标成入口，指向第一条引用，
    # 避免「声称命中却无处溯源」（不再静默返回原稿）。
    if not used and refs:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("记忆命中") and "：" in stripped:
                head, _, tail = stripped.partition("：")
                label = f"{head}：{tail}" if tail else head
                lines[index] = _underline_line(label, refs[0].ref_id)
                used.append(refs[0].ref_id)
                break

    if not used:
        return markdown

    appendix = ["", "---", "", f"## {SECTION_TITLE}", ""]
    for ref_id in used:
        ref = by_id[ref_id]
        kind = ref.kind or "历史片段"
        title = ref.meeting_title or ref.source
        at = ref.meeting_time or "时间未记录"
        slot = ref.session_label or "未定位"
        appendix.extend(
            [
                f'<a id="{ref.ref_id}"></a>',
                f"> {ref.text}",
                f"时间：{at}　场次：{slot}　类型：{kind}　关联：{ref.entity}",
                f"来源会议：{title}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n" + "\n".join(appendix).rstrip()


def _parse_memory_sources(text: str) -> dict[str, str]:
    if f"## {SECTION_TITLE}" not in text:
        return {}
    appendix = text.split(f"## {SECTION_TITLE}", 1)[1]
    blocks = re.split(r'\n<a id="([^"]+)"></a>\n', appendix)
    out: dict[str, str] = {}
    for i in range(1, len(blocks), 2):
        ref_id = blocks[i]
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        if not lines:
            continue
        title = ""
        meta = ""
        quote = ""
        for line in lines:
            if line.startswith(">"):
                quote = line.lstrip("> ").strip()
            elif line.startswith("时间："):
                meta = line
            elif line.startswith("来源会议："):
                title = line.removeprefix("来源会议：").strip()
            elif line.startswith("**来自："):
                title = re.sub(r"^\*\*来自：|\*\*$", "", line).strip()
        card = (
            f'<div class="mem-card-title">{escape(quote or title)}</div>'
            f'<div class="mem-card-meta">{escape(meta)}</div>'
        )
        if title and quote:
            card += f'<div class="mem-card-source">{escape(title)}</div>'
        out[ref_id] = card
    return out


def memory_review_html(markdown: str) -> str:
    """Render memory-linked Markdown into a left-text/right-source review view."""
    text = markdown or ""
    if 'class="memory-link"' not in text:
        return ""
    main = text.split(f"\n---\n\n## {SECTION_TITLE}", 1)[0]
    sources = _parse_memory_sources(text)
    rows: list[str] = ['<div class="memory-review">']
    link_re = re.compile(r'<a href="#([^"]+)" class="memory-link"><u>(.*?)</u></a>')
    for raw in main.splitlines():
        line = raw.strip()
        if not line:
            continue
        ids = link_re.findall(line)
        cleaned = link_re.sub(lambda m: f'<span class="mem-mark">{m.group(2)}</span>', line)
        if line.startswith("#"):
            rows.append(f'<div class="review-heading">{escape(line.lstrip("# ").strip())}</div>')
            continue
        cards = []
        seen: set[str] = set()
        for ref_id, _ in ids:
            if ref_id in seen:
                continue
            seen.add(ref_id)
            if ref_id in sources:
                cards.append(f'<a class="mem-card" href="#{ref_id}">{sources[ref_id]}</a>')
        if not cards:
            cards.append('<div class="mem-empty"></div>')
        rows.append(
            '<div class="review-row">'
            f'<div class="review-left">{cleaned}</div>'
            '<div class="review-rule"></div>'
            f'<div class="review-right">{"".join(cards)}</div>'
            '</div>'
        )
    rows.append("</div>")
    return "\n".join(rows)


__all__ = [
    "MemoryReference",
    "SECTION_TITLE",
    "apply_memory_citations",
    "extract_memory_references",
    "memory_review_html",
]
