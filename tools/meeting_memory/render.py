"""会议记忆 v2 渲染：Markdown 记忆引用 + HTML 审阅栏。

数据源直接来自 ``build_memory_context`` 输出的【会议记忆】块
（延续事项 / 风险演变 / 历史决策 + 原文摘录），不再依赖旧
``tools.memory.citations`` 的【记忆命中 / 记忆来源索引】兼容格式。

- ``apply_memory_citations``：正文锚点标注 + 文末「历史记忆引用」区。
- ``memory_review_html``：左正文高亮 / 右记忆来源卡片（复用现有 review CSS）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

SECTION_TITLE = "历史记忆引用"

# 记忆块总是追加在（生成/渲染）上下文末尾；贪婪到文末，小节头不参与块边界。
_MEMORY_BLOCK_RE = re.compile(r"【会议记忆】(.*)\Z", re.S)
_SECTION_RE = re.compile(r"【(延续事项|风险演变|历史决策)】")
_KIND_BY_SECTION = {"延续事项": "open", "风险演变": "risk", "历史决策": "decision"}
_ITEM_RE = re.compile(r"^- (.+)$")
_QUOTE_RE = re.compile(r"^\s*原文摘录：(.+)$")
_SOURCE_RE = re.compile(r"^\s*来源会议：(.+)$")
_TIME_RE = re.compile(r"^\s*会议时间：(.+)$")
_SINCE_RE = re.compile(r"自\s*([^\s，,]+)\s*，\s*最近\s*([^\s，,)）]+)")
_LAST_RE = re.compile(r"最近\s*([^\s，,)）]+)")
_META_TAIL_RE = re.compile(r"（[^）]*）$")
_DECISION_LEAD_RE = re.compile(r"^(m_[A-Za-z0-9_-]+)：(.+)$")
_MEM_SECTION_RE = re.compile(r"\n(?:-{3,}\s*\n+)*## " + re.escape(SECTION_TITLE) + r"\b.*\Z", re.S)
_TAG_RE = re.compile(
    r"(?:<sup>)?\[记忆\d+\]\(#memory-\d+\)(?:</sup>)?|class=\"memory-link\"|\[[^\]]+\]\(#memory-\d+\)"
)
_HAN = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_DATE_TERM = re.compile(r"\d{1,4}月\d{1,2}日")
_MIN_ANCHOR = 5
_MAX_ANCHOR = 22


@dataclass
class MemoryItem:
    """一条可溯源的历史记忆条目。"""

    kind: str  # open / risk / decision
    text: str
    quote: str = ""
    meeting_id: str = ""  # 最近场次（open/risk 为 last_seen，decision 为 meeting_id）
    since: str = ""
    meeting_title: str = ""  # 最近场次会议标题（引用区"来源会议"）
    meeting_time: str = ""  # 该场会议时间（请求体 time；空则不展示）


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def parse_memory_items(context: str) -> list[MemoryItem]:
    """从【会议记忆】块解析出可溯源条目。

    兼容两种形态：
    - ``- 文本（自 X，最近 Y）`` + 缩进 ``原文摘录：…``（open / risk）
    - ``- m_xxx：文本`` + 缩进 ``原文摘录：…``（decision）
    """
    raw = context or ""
    match = _MEMORY_BLOCK_RE.search(raw)
    if not match:
        return []
    block = match.group(1)
    section = ""
    items: list[MemoryItem] = []
    pending: MemoryItem | None = None

    def _flush() -> None:
        nonlocal pending
        if pending is not None:
            items.append(pending)
        pending = None

    for line in block.splitlines():
        stripped = line.strip()
        section_match = _SECTION_RE.match(stripped)
        if section_match:
            _flush()
            section = section_match.group(1)
            continue
        if not section:
            continue
        quote_match = _QUOTE_RE.match(line)
        if quote_match:
            if pending is not None and not pending.quote:
                pending.quote = _clean(quote_match.group(1))
            continue
        source_match = _SOURCE_RE.match(line)
        if source_match:
            if pending is not None and not pending.meeting_title:
                pending.meeting_title = _clean(source_match.group(1))
            continue
        time_match = _TIME_RE.match(line)
        if time_match:
            if pending is not None and not pending.meeting_time:
                pending.meeting_time = _clean(time_match.group(1))
            continue
        item_match = _ITEM_RE.match(stripped)
        if item_match:
            _flush()
            body = _clean(item_match.group(1))
            meeting_id = ""
            since = ""
            if section == "历史决策":
                lead = _DECISION_LEAD_RE.match(body)
                if lead:
                    meeting_id = lead.group(1)
                    body = _clean(lead.group(2))
                body = _META_TAIL_RE.sub("", body).strip()
            else:
                since_match = _SINCE_RE.search(body)
                if since_match:
                    since = since_match.group(1)
                    meeting_id = since_match.group(2)
                else:
                    last_match = _LAST_RE.search(body)
                    if last_match:
                        meeting_id = last_match.group(1)
                body = _META_TAIL_RE.sub("", body).strip()
            if not body:
                continue
            pending = MemoryItem(
                kind=_KIND_BY_SECTION.get(section, "history"),
                text=body,
                meeting_id=meeting_id,
                since=since,
            )
    _flush()
    return items


# ── Markdown 引用标注 ────────────────────────────────────────


def _han_ngrams(text: str, size: int = 6) -> set[str]:
    chars = "".join(ch for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")
    if len(chars) < size:
        return {chars} if chars else set()
    return {chars[i : i + size] for i in range(len(chars) - size + 1)}


def _related(line: str, item: MemoryItem) -> bool:
    """正文行与记忆条目是否可能相关（保守，宁漏勿滥）。

    信号分级：整句互相包含（≥5 字）、共享拉丁专名或日期 token（强实体信号，
    如 minutes_trace / Gradio / 8月20日）、长分句互相包含（≥5 字）、
    共享 ≥4 字连续汉字片段。
    """
    a, b = _clean(line), _clean(item.text)
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) >= _MIN_ANCHOR
    a_tokens = set(_LATIN_TERM.findall(a)) | set(_DATE_TERM.findall(a))
    b_tokens = set(_LATIN_TERM.findall(b)) | set(_DATE_TERM.findall(b))
    if a_tokens & b_tokens:
        return True
    a_terms = [x for x in re.split(r"[，。；;、\s]+", a) if len(x) >= _MIN_ANCHOR]
    b_terms = [x for x in re.split(r"[，。；;、\s]+", b) if len(x) >= _MIN_ANCHOR]
    if any(x in b or y in a for x in a_terms for y in b_terms):
        return True
    return bool(_han_ngrams(a, size=4) & _han_ngrams(b, size=4))


def _clip_anchor(text: str) -> str:
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


def _best_span(line: str, item: MemoryItem) -> tuple[int, int] | None:
    """在正文行里找短锚点：连续原文 8–22 字，禁止跨半句散标。"""
    ref_text = _clean(item.text)
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
        token for token in _LATIN_TERM.findall(ref_text)
        if 3 <= len(token) <= _MAX_ANCHOR
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
            span = _exact_span(line, right[i : i + size])
            if span:
                return span
    return None


def _is_citeable_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "|", "```", "<a ")):
        return False
    if stripped in {"---", "***", "___"}:
        return False
    return True


def _append_markers(
    line: str,
    items: list[MemoryItem],
    seen: list[MemoryItem] | None = None,
) -> tuple[str, list[MemoryItem]]:
    if not items or _TAG_RE.search(line):
        return line, []
    seen = seen or []
    # 同一记忆实体只在正文首次出现处锚定溯源，重复出现不再标注。
    hits = [item for item in items if item not in seen and _related(line, item)]
    if not hits:
        return line, []
    spans: list[tuple[int, int, MemoryItem]] = []
    for item in hits:
        span = _best_span(line, item)
        if span is None:
            continue
        start, end = span
        if end <= start:
            continue
        if any(not (end <= s or start >= e) for s, e, _ in spans):
            continue
        spans.append((start, end, item))
        if len(spans) >= 2:
            break
    if not spans:
        return line, []
    spans.sort(key=lambda item: item[0])
    out: list[str] = []
    pos = 0
    used: list[MemoryItem] = []
    for start, end, item in spans:
        out.append(escape(line[pos:start], quote=False))
        label = escape(line[start:end], quote=False)
        ref_id = f"memory-{items.index(item) + 1}"
        out.append(f"[{label}](#{ref_id})")
        used.append(item)
        pos = end
    out.append(escape(line[pos:], quote=False))
    return "".join(out), used


def apply_memory_citations(markdown: str, context: str) -> str:
    """给渲染后的纪要加记忆引用标注并追加「历史记忆引用」区。

    与旧 ``tools.memory.citations.apply_memory_citations`` 行为等价：
    保守锚定、不改事实措辞、只追加标记；上下文无【会议记忆】块时原样返回。
    """
    items = parse_memory_items(context)
    if not items:
        return markdown or ""
    text = _MEM_SECTION_RE.sub("", markdown or "").strip()
    if not text:
        return markdown or ""

    used: list[MemoryItem] = []
    seen: list[MemoryItem] = []
    lines: list[str] = []
    for line in text.splitlines():
        if _is_citeable_line(line):
            line, found = _append_markers(line, items, seen)
            for item in found:
                if item not in seen:
                    seen.append(item)
                    used.append(item)
        lines.append(line)

    # 正文没有任何可精确锚定的行时，不伪造溯源入口：既不声明命中，也不生成
    # 「历史记忆引用」区（宁可无引用，也不在正文插入「记忆命中」这类系统表达）。
    if not used:
        return "\n".join(lines) if lines else markdown or ""

    appendix = ["", f"## {SECTION_TITLE}", ""]
    for idx, item in enumerate(used):
        ref_id = f"memory-{items.index(item) + 1}"
        source = item.meeting_title or item.meeting_id or "历史会议"
        quote = item.quote or item.text
        rows = [
            f"#### 溯源 {ref_id}",
            f"> {quote}",
            f"来源会议：{source}",
        ]
        if item.meeting_time:
            rows.append(f"会议时间：{item.meeting_time}")
        appendix.extend(rows)
    return "\n".join(lines) + "\n" + "\n".join(appendix)


# ── HTML 审阅栏 ─────────────────────────────────────────────


def _mark_line(line: str) -> tuple[str, list[str]]:
    """把 Markdown 记忆链接变成高亮，其余转义。"""
    parts: list[str] = []
    ids: list[str] = []
    pos = 0
    for match in re.finditer(r"\[([^\]]+)\]\(#(memory-\d+)\)", line):
        parts.append(escape(line[pos : match.start()], quote=False))
        ref_id = match.group(2).strip()
        parts.append(
            f'<mark class="mem-mark" data-mem="{escape(ref_id, quote=True)}">'
            f"{escape(match.group(1), quote=False)}</mark>"
        )
        ids.append(ref_id)
        pos = match.end()
    parts.append(escape(line[pos:], quote=False))
    return "".join(parts), ids


def _parse_memory_sources(markdown: str) -> dict[str, dict[str, str]]:
    """从「历史记忆引用」区解析各 memory-N 的来源卡片数据。"""
    raw = markdown or ""
    marker = f"## {SECTION_TITLE}"
    if marker not in raw:
        return {}
    chunk = raw.split(marker, 1)[1]
    blocks = re.split(r"\n#### 溯源\s*", chunk)
    out: dict[str, dict[str, str]] = {}
    for i in range(1, len(blocks)):
        ref_id = blocks[i].strip().splitlines()[0].strip()
        lines = [line.strip() for line in blocks[i].strip().splitlines()[1:] if line.strip()]
        if not ref_id or not lines:
            continue
        title = ""
        quote = ""
        mtime = ""
        for line in lines:
            if line.startswith(">"):
                quote = line.lstrip("> ").strip()
            elif line.startswith("来源会议："):
                title = line.removeprefix("来源会议：").strip()
            elif line.startswith("会议时间："):
                mtime = line.removeprefix("会议时间：").strip()
        out[ref_id] = {"quote": quote, "title": title, "time": mtime}
    return out


def _memory_card_html(ref_id: str, info: dict[str, str]) -> str:
    """渲染溯源卡片：标题 = 历史会议标题，正文为原文摘录，最下侧为会议时间（如有）。"""
    quote = info.get("quote") or ""
    title = info.get("title") or ""
    mtime = info.get("time") or ""
    card_title = title or quote or ref_id
    return (
        f'<aside class="mem-card" id="card-{escape(ref_id, quote=True)}" '
        f'data-mem="{escape(ref_id, quote=True)}">'
        f'<div class="mem-card-title">{escape(card_title, quote=False)}</div>'
        + (
            f'<div class="mem-card-quote">{escape(quote, quote=False)}</div>'
            if quote and title
            else ""
        )
        + (
            f'<div class="mem-card-time">{escape(f"会议时间：{mtime}", quote=False)}</div>'
            if mtime
            else ""
        )
        + "</aside>"
    )


_MEMORY_SCRIPT = """<script>
(function () {
  const root = document.querySelector('.memory-review');
  if (!root) return;
  const clear = () => {
    root.querySelectorAll('.is-on').forEach((el) => el.classList.remove('is-on'));
  };
  const activate = (id) => {
    if (!id) return;
    clear();
    root.querySelectorAll('[data-mem="' + id + '"]').forEach((el) => el.classList.add('is-on'));
    const card = root.querySelector('.mem-card[data-mem="' + id + '"]');
    if (card) card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };
  root.addEventListener('click', (ev) => {
    const hit = ev.target.closest('[data-mem]');
    if (!hit) { clear(); return; }
    activate(hit.getAttribute('data-mem') || '');
  });
})();
</script>"""


def memory_review_html(markdown: str) -> str:
    """把带记忆链接的纪要渲成左正文高亮 / 右记忆批注（Word 审阅栏）。

    只渲染已有 Markdown（``[原文片段](#memory-N)`` + 文末历史记忆引用），
    复用 outputs._html_document 的 review CSS 类名。无记忆链接时一律返回空串，
    调用方回退普通全宽纪要（.plain），不渲染左右骨架与"未命中"提示。
    """
    text = markdown or ""
    if "](#" not in text:
        return ""
    main, _appendix = re.split(r"\n## " + re.escape(SECTION_TITLE) + r"\b", text, maxsplit=1)
    sources = _parse_memory_sources(text)
    rows: list[str] = [
        '<div class="memory-shell">',
        '<p class="memory-legend">黄色高亮为命中的历史记忆，点击可对照右侧批注。</p>',
        '<div class="memory-review">',
        '<div class="review-head-row">',
        '<div class="review-left">本次纪要</div>',
        '<div class="review-rule"></div>',
        '<div class="review-right">记忆批注</div>',
        "</div>",
    ]
    for raw in main.splitlines():
        line = raw.strip()
        if not line:
            continue
        hashes = len(line) - len(line.lstrip("#"))
        if hashes and line.lstrip("#")[:1].isspace():
            title = _mark_line(line.lstrip("# ").strip())[0]
            rows.append(f'<div class="review-heading">{title}</div>')
            continue
        cleaned, ids = _mark_line(line)
        cards: list[str] = []
        seen: set[str] = set()
        for ref_id in ids:
            if ref_id in seen:
                continue
            seen.add(ref_id)
            info = sources.get(ref_id) or {
                "quote": "",
                "title": "",
            }
            cards.append(_memory_card_html(ref_id, info))
        right = "".join(cards) if cards else ""
        row_cls = "review-row has-mem" if cards else "review-row"
        rows.append(
            f'<div class="{row_cls}">'
            f'<div class="review-left">{cleaned}</div>'
            '<div class="review-rule"></div>'
            f'<div class="review-right">{right}</div>'
            "</div>"
        )
    rows.append("</div></div>")
    rows.append(_MEMORY_SCRIPT)
    return "\n".join(rows)


__all__ = [
    "MemoryItem",
    "SECTION_TITLE",
    "apply_memory_citations",
    "memory_review_html",
    "parse_memory_items",
]
