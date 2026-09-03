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


def _latex_paper_css() -> str:
    return """
    body {
      margin: 0;
      padding: 32px 16px;
      background: #f6f5f0;
      color: #1a1a1a;
      font-family: "Latin Modern Roman", "Computer Modern Roman", "CMU Serif", "Times New Roman", Times, "Songti SC", "SimSun", "STSong", serif;
      -webkit-font-smoothing: antialiased;
    }
    .page { max-width: 1140px; margin: 0 auto; }
    .ck-doc {
      background: #ffffff;
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0,0,0,0.03);
      padding: 36px 44px;
      line-height: 1.75;
      font-size: 0.96rem;
    }
    .ck-doc h1 {
      margin: 0 0 10px;
      font-size: 1.85rem;
      font-weight: 700;
      letter-spacing: 0.4px;
      text-align: center;
      font-variant: small-caps;
      color: #111111;
    }
    .ck-doc-header {
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 2px solid #111111;
      text-align: center;
    }
    .ck-doc-meta {
      font-size: 0.85rem;
      color: #555555;
      font-style: italic;
    }
    .ck-doc h2, .ck-doc-h2 {
      margin: 28px 0 14px;
      font-size: 1.22rem;
      font-weight: 700;
      color: #111111;
      border-bottom: 1.5px solid #222222;
      padding-bottom: 5px;
      letter-spacing: 0.3px;
    }
    .ck-doc h3, .ck-doc-h3 {
      margin: 20px 0 10px;
      font-size: 1.05rem;
      font-weight: 700;
      color: #222222;
    }
    .ck-doc h4, .ck-doc-h4 {
      margin: 16px 0 8px;
      font-size: 0.98rem;
      font-weight: 700;
      color: #333333;
    }
    .ck-doc p {
      margin: 10px 0;
      line-height: 1.75;
      text-align: justify;
    }
    .ck-doc ul, .ck-doc ol {
      margin: 8px 0 12px;
      padding-left: 1.5em;
      line-height: 1.72;
    }
    .ck-doc li {
      margin: 4px 0;
    }
    .ck-doc blockquote, .ck-quote {
      margin: 10px 0 14px;
      padding: 8px 14px;
      background: #faf9f6;
      border-left: 3.5px solid #222222;
      border-radius: 2px;
      color: #222222;
      font-size: 0.92rem;
      font-style: italic;
    }
    .ck-doc code {
      background: #f3f0e8;
      border: 1px solid #e2ddd3;
      border-radius: 3px;
      padding: 1px 6px;
      font-family: "Latin Modern Mono", Consolas, monospace;
      font-size: 0.88em;
    }
    .ck-doc table, .ck-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
      margin: 14px 0;
      background: #ffffff;
      border-top: 2px solid #222222;
      border-bottom: 2px solid #222222;
    }
    .ck-doc table th, .ck-doc table td, .ck-table th, .ck-table td {
      padding: 9px 12px;
      text-align: left;
      vertical-align: middle;
      border-bottom: 1px solid #ede9e1;
    }
    .ck-doc table th, .ck-table th {
      background: #fbfaf7;
      border-bottom: 1.2px solid #222222;
      font-weight: 700;
      color: #111111;
      letter-spacing: 0.3px;
    }

    /* Roomy & Spacious Academic Risk Table */
    .ck-risk-table {
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0 28px;
      background: #ffffff;
      border-top: 2.2px solid #111111;
      border-bottom: 2.2px solid #111111;
      font-size: 0.93rem;
      line-height: 1.72;
    }
    .ck-risk-table th {
      background: #faf8f5;
      border-bottom: 1.5px solid #111111;
      padding: 15px 16px;
      font-weight: 700;
      color: #111111;
      letter-spacing: 0.3px;
      text-align: left;
      vertical-align: middle;
    }
    .ck-risk-table td {
      padding: 16px 16px;
      border-bottom: 1px solid #ede8e0;
      vertical-align: top;
      color: #1a1a1a;
      word-break: break-word;
    }
    .ck-risk-table tr:nth-child(even) td {
      background: #fdfcfb;
    }
    .ck-risk-table tr:hover td {
      background: #f6f3eb;
    }

    /* Review Grid */
    .ck-review {
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) 1px minmax(260px, 0.95fr);
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      overflow: hidden;
      margin: 14px 0 20px;
      background: #ffffff;
      box-shadow: 0 1px 4px rgba(0,0,0,0.03);
    }
    .ck-review-left {
      padding: 22px 26px;
      background: #ffffff;
      line-height: 1.75;
    }
    .ck-review-rule { background: #dcd8cf; }
    .ck-review-right {
      padding: 16px 18px;
      background: #faf9f6;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }
    .ck-ev-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    /* Entity Highlight in LaTeX Paper Style */
    .ck-cite-entity {
      background: #fff8db;
      border-bottom: 1.5px solid #b86a04;
      padding: 1px 4px;
      border-radius: 2px;
      cursor: pointer;
      transition: all 0.18s ease;
      color: #111111;
      font-weight: 600;
    }
    .ck-cite-entity:hover {
      background: #ffe58f;
      color: #000000;
    }
    .ck-cite-entity.is-on {
      background: #ffd54a;
      border-bottom-color: #0047ab;
      box-shadow: 0 0 0 2px rgba(0,71,171,0.25);
    }

    /* Blue Hyperref Citations [1], [2] */
    .ck-cite-ref {
      color: #0047ab;
      font-weight: 600;
      font-family: "Latin Modern Roman", "Computer Modern Roman", "Times New Roman", serif;
      text-decoration: none;
      cursor: pointer;
      padding: 0 2px;
      margin: 0 2px;
      border-radius: 2px;
      transition: all 0.15s ease;
      font-size: 0.92em;
      vertical-align: baseline;
      user-select: none;
    }
    .ck-cite-ref:hover {
      text-decoration: underline;
      background: #e8f0fe;
      color: #003380;
    }
    .ck-cite-ref.is-active {
      background: #d2e3fc;
      color: #002266;
      font-weight: 700;
      box-shadow: 0 0 0 1px #0047ab;
    }

    /* Right Memory Cards in LaTeX Paper Style */
    .ck-provenance-head {
      font-size: 0.82rem;
      font-weight: 700;
      color: #222222;
      margin: 0 0 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid #e0dcd4;
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }
    .ck-ref-icon { color: #0047ab; margin-right: 4px; }
    .ck-ev {
      display: block;
      margin: 0;
      padding: 10px 12px;
      border: 1px solid #dedad2;
      border-left: 3.5px solid #0047ab;
      border-radius: 2px;
      background: #ffffff;
      font-size: 0.82rem;
      line-height: 1.55;
      transition: all 0.2s ease;
      cursor: pointer;
    }
    .ck-ev:hover { border-color: #b5b0a5; }
    .ck-ev.is-on, .ck-ev.is-highlighted {
      border-color: #0047ab;
      box-shadow: 0 0 0 2px #0047ab, 0 3px 8px rgba(0,71,171,0.15);
      background: #f0f5ff;
    }
    @keyframes citePulse {
      0% { background: #dbeafe; box-shadow: 0 0 0 3px #0047ab; }
      50% { background: #bfdbfe; box-shadow: 0 0 0 4px #0047ab; }
      100% { background: #f0f5ff; box-shadow: 0 0 0 2px #0047ab; }
    }
    .ck-ev-k {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      color: #444444;
      margin-bottom: 5px;
      font-weight: 700;
    }
    .ck-ev-cite-tag {
      color: #0047ab;
      font-weight: 700;
      font-family: "Latin Modern Roman", serif;
      text-decoration: none;
    }
    .ck-ev-kind-badge {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 2px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.2px;
    }
    .ck-badge-keypoint {
      border: 1px solid #0047ab;
      color: #0047ab;
      background: #f0f5ff;
    }
    .ck-badge-note {
      border: 1px solid #b86a04;
      color: #b86a04;
      background: #fff8eb;
    }
    .ck-mem-title {
      font-weight: 700;
      color: #111111;
      font-size: 0.88rem;
      margin-bottom: 6px;
      line-height: 1.45;
    }
    .ck-ev-quote {
      color: #222222;
      font-style: normal;
      font-family: inherit;
      margin: 4px 0 6px;
      padding: 0;
      background: transparent;
      border: none;
      line-height: 1.6;
      font-size: 0.84rem;
    }
    .ck-ev-meta { font-size: 0.76rem; color: #666666; margin-top: 6px; }
    .ck-ev-more {
      margin-top: 2px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .ck-ev-more[open] { margin-top: 4px; }
    .ck-ev-more summary { margin-bottom: 6px; }
    .ck-proof-toggle {
      cursor: pointer;
      font-size: 0.82rem;
      color: #0047ab;
      user-select: none;
      font-family: inherit;
      padding: 2px 0;
    }
    .ck-proof-toggle:hover { text-decoration: underline; }

    @media(max-width: 860px) {
      .ck-doc { padding: 22px 18px; }
      .ck-review { grid-template-columns: 1fr; }
      .ck-review-rule { display: none; }
    }
"""


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


def _format_minutes_html(
    markdown_text: str,
    sources: dict[str, dict[str, str]],
    ref_id_to_num: dict[str, int],
) -> tuple[str, str]:
    """将纪要正文解析为带有实体高亮与蓝色 [i] 引用的 HTML。返回 (meeting_title, body_html)。"""
    lines = markdown_text.strip().splitlines()
    meeting_title = "会议纪要"
    if lines and lines[0].startswith("# "):
        meeting_title = lines[0][2:].strip()
        lines = lines[1:]

    out: list[str] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []

    def flush_list() -> None:
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()
        if ol_buf:
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in ol_buf) + "</ol>")
            ol_buf.clear()

    def inline_format(s: str) -> str:
        parts: list[str] = []
        pos = 0
        for m in re.finditer(r"\[([^\]]+)\]\(#(memory-\d+)\)", s):
            parts.append(escape(s[pos : m.start()], quote=False))
            entity = m.group(1)
            ref_id = m.group(2).strip()
            num = ref_id_to_num.get(ref_id, 1)
            info = sources.get(ref_id, {})
            source_title = info.get("title") or info.get("quote") or "历史会议"
            parts.append(
                f'<span class="ck-cite-entity" data-mem="{escape(ref_id, quote=True)}" data-cite="{num}">{escape(entity, quote=False)}</span>'
                f'<a href="javascript:void(0)" class="ck-cite-ref" data-target-mem="{escape(ref_id, quote=True)}" title="点击查看历史会议 [{num}] · {escape(source_title, quote=True)}">[{num}]</a>'
            )
            pos = m.end()
        parts.append(escape(s[pos:], quote=False))
        text = "".join(parts)

        # Markdown bold, italic, code
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        if not stripped:
            flush_list()
            i += 1
            continue

        if stripped.startswith("### "):
            flush_list()
            out.append(f'<h3 class="ck-doc-h3">{inline_format(stripped[4:])}</h3>')
            i += 1
            continue
        if stripped.startswith("## "):
            flush_list()
            out.append(f'<h2 class="ck-doc-h2">{inline_format(stripped[3:])}</h2>')
            i += 1
            continue
        if stripped.startswith("# "):
            flush_list()
            out.append(f'<h2>{inline_format(stripped[2:])}</h2>')
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", raw_line):
            if ol_buf:
                flush_list()
            list_buf.append(inline_format(re.sub(r"^\s*[-*]\s+", "", raw_line)))
            i += 1
            continue

        if re.match(r"^\s*\d+[.)、]\s+", raw_line):
            if list_buf:
                flush_list()
            ol_buf.append(inline_format(re.sub(r"^\s*\d+[.)、]\s+", "", raw_line)))
            i += 1
            continue

        if stripped.startswith(">"):
            flush_list()
            out.append(f'<div class="ck-quote">{inline_format(stripped.lstrip("> "))}</div>')
            i += 1
            continue

        flush_list()
        out.append(f'<p>{inline_format(stripped)}</p>')
        i += 1

    flush_list()
    return meeting_title, "".join(out)


_MEMORY_SCRIPT = """<script>
(function () {
  function getActualContentHeight(el) {
    const children = Array.from(el.children);
    if (!children.length) return el.scrollHeight;
    let top = Infinity;
    let bottom = -Infinity;
    children.forEach((child) => {
      const rect = child.getBoundingClientRect();
      if (rect.top < top) top = rect.top;
      if (rect.bottom > bottom) bottom = rect.bottom;
    });
    if (bottom > top && top !== Infinity) {
      return bottom - top;
    }
    return el.scrollHeight;
  }

  function adjustMemoryFolding() {
    const isDesktop = window.innerWidth > 860;
    document.querySelectorAll('.ck-review').forEach((row) => {
      const leftEl = row.querySelector('.ck-review-left');
      const rightEl = row.querySelector('.ck-review-right');
      const listEl = row.querySelector('.ck-ev-list');
      if (!leftEl || !rightEl || !listEl) return;

      // 还原之前已折叠的元素，重新获取自然高度
      const existingDetails = listEl.querySelector('.ck-ev-more');
      if (existingDetails) {
        const itemsInside = Array.from(existingDetails.querySelectorAll('.ck-ev'));
        itemsInside.forEach((ev) => existingDetails.before(ev));
        existingDetails.remove();
      }

      const allEvs = Array.from(listEl.querySelectorAll(':scope > .ck-ev'));
      if (allEvs.length <= 1) return;

      const leftContentHeight = getActualContentHeight(leftEl);

      let totalHeight = 0;
      const itemsToFold = [];

      allEvs.forEach((ev, idx) => {
        if (!isDesktop) {
          if (idx >= 3) itemsToFold.push(ev);
          return;
        }
        const evRect = ev.getBoundingClientRect();
        const evHeight = (evRect && evRect.height > 0) ? evRect.height + 10 : ev.offsetHeight + 10;
        // 当右侧卡片累积高度超过左侧正文纪要内容高度时，对超出的卡片进行折叠
        if (totalHeight + evHeight > leftContentHeight && idx >= 1) {
          itemsToFold.push(ev);
        } else {
          totalHeight += evHeight;
        }
      });

      if (itemsToFold.length > 0) {
        const details = document.createElement('details');
        details.className = 'ck-ev-more';
        const summary = document.createElement('summary');
        summary.className = 'ck-proof-toggle';
        summary.innerHTML = `查看更多历史会议 (${itemsToFold.length}) ▾`;
        details.appendChild(summary);

        itemsToFold[0].before(details);
        itemsToFold.forEach((ev) => details.appendChild(ev));
      }
    });
  }

  window.__adjustMemoryFolding = adjustMemoryFolding;

  document.querySelectorAll('.ck-review').forEach((row) => {
    const cites = row.querySelectorAll('.ck-cite-ref');
    const entities = row.querySelectorAll('.ck-cite-entity');
    const cards = row.querySelectorAll('.ck-ev');

    const clearHighlights = () => {
      entities.forEach((el) => el.classList.remove('is-on'));
      cards.forEach((el) => el.classList.remove('is-on', 'is-highlighted'));
      cites.forEach((c) => c.classList.remove('is-active'));
    };

    const highlightMem = (targetMemId) => {
      clearHighlights();
      let targetCard = null;
      row.querySelectorAll('.ck-ev').forEach((card) => {
        if (card.getAttribute('data-mem') === targetMemId) {
          targetCard = card;
          const parentDetails = card.closest('details');
          if (parentDetails) parentDetails.open = true;
          card.classList.add('is-on', 'is-highlighted');
          card.style.animation = 'none';
          void card.offsetHeight;
          card.style.animation = 'citePulse 1.2s ease';
        }
      });
      entities.forEach((ent) => {
        if (ent.getAttribute('data-mem') === targetMemId) {
          ent.classList.add('is-on');
        }
      });
      cites.forEach((c) => {
        if (c.getAttribute('data-target-mem') === targetMemId) {
          c.classList.add('is-active');
        }
      });
      if (targetCard) {
        targetCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    };

    cites.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const targetId = btn.getAttribute('data-target-mem');
        if (targetId) highlightMem(targetId);
      });
    });

    entities.forEach((ent) => {
      ent.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const targetId = ent.getAttribute('data-mem');
        if (targetId) highlightMem(targetId);
      });
    });

    row.addEventListener('click', (e) => {
      const card = e.target.closest('.ck-ev');
      if (card) {
        const memId = card.getAttribute('data-mem');
        if (memId) highlightMem(memId);
      }
    });
  });

  adjustMemoryFolding();
  window.addEventListener('load', adjustMemoryFolding);
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(adjustMemoryFolding, 100);
  });
})();
</script>"""


def memory_review_html(markdown: str) -> str:
    """把带记忆链接的纪要渲染为与 checklist 一致的 LaTeX Paper 风格 HTML。

    左侧：纪要正文排版，命中记忆的实体高亮并在后面附加蓝色 [1], [2] 序号标签。
    右侧：历史记忆溯源卡片，带有连续序号 [1], [2] 与来源会议/摘录/时间。
    交互：点击左侧实体或蓝色序号可点亮对应右侧记忆卡片并带光晕脉冲动画；右侧超出左侧高度时自适应折叠。
    """
    text = markdown or ""
    if "](#" not in text:
        return ""
    main, _appendix = re.split(r"\n## " + re.escape(SECTION_TITLE) + r"\b", text, maxsplit=1)
    sources = _parse_memory_sources(text)

    # 提取所有出现的 ref_id，按正文首次出现顺序赋予连续编号 [1], [2], [3]...
    ref_id_to_num: dict[str, int] = {}
    ordered_ref_ids: list[str] = []

    for m in re.finditer(r"\[([^\]]+)\]\(#(memory-\d+)\)", main):
        ref_id = m.group(2).strip()
        if ref_id not in ref_id_to_num:
            num = len(ordered_ref_ids) + 1
            ref_id_to_num[ref_id] = num
            ordered_ref_ids.append(ref_id)

    for ref_id in sources:
        if ref_id not in ref_id_to_num:
            num = len(ordered_ref_ids) + 1
            ref_id_to_num[ref_id] = num
            ordered_ref_ids.append(ref_id)

    meeting_title, left_html = _format_minutes_html(main, sources, ref_id_to_num)

    cards_html: list[str] = []
    for ref_id in ordered_ref_ids:
        num = ref_id_to_num.get(ref_id, 1)
        info = sources.get(ref_id, {})
        title = info.get("title") or "历史会议"
        quote = info.get("quote") or ""
        mtime = info.get("time") or ""

        card = [
            f'<aside class="ck-ev ck-mem-card" id="card-{escape(ref_id, quote=True)}" data-mem="{escape(ref_id, quote=True)}" data-cite="{num}">',
            f'<div class="ck-ev-k"><a class="ck-ev-cite-tag" href="javascript:void(0);">[{num}]</a> <span class="ck-ev-kind-badge">历史会议</span></div>',
            f'<div class="ck-mem-title"><strong>{escape(title, quote=False)}</strong></div>',
        ]
        if quote:
            card.append(f'<div class="ck-ev-quote">“{escape(quote, quote=False)}”</div>')
        if mtime:
            card.append(f'<div class="ck-ev-meta">会议时间：{escape(mtime, quote=False)}</div>')
        card.append("</aside>")
        cards_html.append("".join(card))

    doc_title = escape(f"{meeting_title} · 会议纪要", quote=False)
    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>
{_latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{escape(meeting_title, quote=False)}</h1>
      </header>
      <div class="ck-review">
        <div class="ck-review-left">
          {left_html}
        </div>
        <div class="ck-review-rule"></div>
        <div class="ck-review-right">
          <div class="ck-ev-list">
            {"".join(cards_html)}
          </div>
        </div>
      </div>
    </div>
  </main>
{_MEMORY_SCRIPT}
</body>
</html>
"""
    return page_html


# ── 风险提取（Risks）与 待办提取（Actions）LaTeX Paper 渲染 ─────────────────


def _render_markdown_content(text: str) -> str:
    """把 Markdown 转换为符合 LaTeX Paper 风格的 HTML 片段（保留 Markdown 原始格式）。"""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []

    def flush_ul() -> None:
        if list_buf:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_buf) + "</ul>")
            list_buf.clear()

    def flush_ol() -> None:
        if ol_buf:
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in ol_buf) + "</ol>")
            ol_buf.clear()

    def flush_list() -> None:
        flush_ul()
        flush_ol()

    def inline(s: str) -> str:
        esc = escape(s, quote=False)
        esc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', esc)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        return esc

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_list()
            i += 1
            continue

        m_head = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m_head:
            flush_list()
            level = len(m_head.group(1))
            cls_name = f"ck-doc-h{level}" if level in (2, 3, 4) else ""
            cls_attr = f' class="{cls_name}"' if cls_name else ""
            out.append(f"<h{level}{cls_attr}>{inline(m_head.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^\s*\|.*\|\s*$", line):
            flush_list()
            rows = []
            while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
                rows.append([c.strip() for c in lines[i].split("|")[1:-1]])
                i += 1
            if rows:
                head = rows[0]
                body_rows = [
                    r for r in rows[1:]
                    if not all(re.fullmatch(r":?-+:?", c) for c in r)
                ]
                out.append(
                    '<table class="ck-table"><thead><tr>'
                    + "".join(f"<th>{inline(c)}</th>" for c in head)
                    + "</tr></thead><tbody>"
                    + "".join(
                        "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                        for r in body_rows
                    )
                    + "</tbody></table>"
                )
            continue

        if re.match(r"^\s*[-*]\s+", line):
            flush_ol()
            list_buf.append(inline(re.sub(r"^\s*[-*]\s+", "", line)))
            i += 1
            continue

        if re.match(r"^\s*\d+[.)、]\s+", line):
            flush_ul()
            ol_buf.append(inline(re.sub(r"^\s*\d+[.)、]\s+", "", line)))
            i += 1
            continue

        if re.match(r"^\s*>\s?", line):
            flush_list()
            quote = re.sub(r"^\s*>\s?", "", line)
            out.append(f'<div class="ck-quote">{inline(quote)}</div>')
            i += 1
            continue

        flush_list()
        out.append(f"<p>{inline(stripped)}</p>")
        i += 1

    flush_list()
    return "".join(out)


def render_markdown_page_html(title: str, markdown: str) -> str:
    """按 LaTeX Paper 风格渲染纯 Markdown 文本为独立 HTML 文档。
    
    保留 Markdown 原始排版、序号与层级，标题采用指定中文名。
    """
    text = (markdown or "").strip()
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("# "):
        first_head = lines[0].strip()[2:].strip()
        if first_head == title or not title:
            title = first_head or title
            text = "\n".join(lines[1:]).strip()

    display_title = title or "会议分析报告"
    content_html = _render_markdown_content(text)
    doc_title = escape(display_title, quote=False)

    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>
{_latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{doc_title}</h1>
      </header>
      <div class="ck-doc-content">
        {content_html}
      </div>
    </div>
  </main>
</body>
</html>
"""
    return page_html


def _parse_risks_from_text(text: str) -> list[dict[str, Any]]:
    """从纯文本或 Markdown 清单中解析结构化风险条目。"""
    risks: list[dict[str, Any]] = []
    lines = (text or "").strip().splitlines()
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        m = re.match(r"^(\d+)[\.、\s]+(.+?)(?:（|\()(.*)(?:）|\))$", line_s)
        if m:
            desc = m.group(2).strip()
            meta_str = m.group(3).strip()
            sev = "medium"
            if re.search(r"\b高\b|高风险|high", meta_str, re.I):
                sev = "high"
            elif re.search(r"\b低\b|低风险|low", meta_str, re.I):
                sev = "low"

            source = ""
            impact = ""
            mitigation = ""
            owner = ""
            for seg in re.split(r"[；;]", meta_str):
                seg = seg.strip()
                if not seg:
                    continue
                if re.match(r"^来源[:：]", seg):
                    source = re.sub(r"^来源[:：]\s*", "", seg)
                elif re.match(r"^影响[:：]", seg):
                    impact = re.sub(r"^影响[:：]\s*", "", seg)
                elif re.match(r"^(?:应对|整改|措施)[:：]", seg):
                    mitigation = re.sub(r"^(?:应对|整改|措施)[:：]\s*", "", seg)
                elif re.match(r"^(?:负责人|责任人|责任主体)[:：]", seg):
                    owner = re.sub(r"^(?:负责人|责任人|责任主体)[:：]\s*", "", seg)
                elif seg in ("高", "中", "低", "高风险", "中风险", "低风险"):
                    if "高" in seg:
                        sev = "high"
                    elif "低" in seg:
                        sev = "low"
                    else:
                        sev = "medium"
            risks.append({
                "risk": desc,
                "severity": sev,
                "source": source,
                "impact": impact,
                "mitigation": mitigation,
                "owner": owner,
            })
        else:
            if line_s.startswith(("#", "```", "---")):
                continue
            clean_desc = re.sub(r"^[-*•\d\.\s]+", "", line_s).strip()
            if clean_desc:
                risks.append({
                    "risk": clean_desc,
                    "severity": "medium",
                    "source": "",
                    "impact": "",
                    "mitigation": "",
                    "owner": "",
                })
    return risks


def render_risks_html(title: str, text: str, data: dict | None = None) -> str:
    """渲染风险分析为宽敞优雅的 LaTeX Paper 风格学术三线表格。
    
    包含列：序号、风险描述、风险程度、来源、影响、应对。
    """
    raw_risks = (data or {}).get("risks")
    if isinstance(raw_risks, list) and raw_risks and isinstance(raw_risks[0], dict):
        risks = raw_risks
    else:
        risks = _parse_risks_from_text(text)

    display_title = "风险分析"

    sev_map = {
        "high": ("高", "ck-s"),
        "高": ("高", "ck-s"),
        "高风险": ("高", "ck-s"),
        "medium": ("中", "ck-a"),
        "中": ("中", "ck-a"),
        "中风险": ("中", "ck-a"),
        "low": ("低", "ck-b"),
        "低": ("低", "ck-b"),
        "低风险": ("低", "ck-b"),
    }

    rows_html = []
    for idx, item in enumerate(risks, start=1):
        sev_key = str(item.get("severity") or "medium").lower().strip()
        sev_cn, badge_cls = sev_map.get(sev_key, ("中", "ck-a"))
        risk_desc = escape(str(item.get("risk") or "").strip(), quote=False)
        source = escape(str(item.get("source") or "").strip(), quote=False)
        impact = escape(str(item.get("impact") or "").strip(), quote=False)
        mitigation = escape(str(item.get("mitigation") or "").strip(), quote=False)

        rows_html.append(
            f'<tr>'
            f'<td style="text-align: center; font-weight: 700; color: #333;">{idx}</td>'
            f'<td><strong style="color: #111111; line-height: 1.65; display: block;">{risk_desc}</strong></td>'
            f'<td style="text-align: center;"><span class="ck-badge {badge_cls}">{sev_cn}</span></td>'
            f'<td style="color: #444444; line-height: 1.6;">{source or "—"}</td>'
            f'<td style="color: #333333; line-height: 1.6;">{impact or "—"}</td>'
            f'<td style="line-height: 1.6;">{mitigation or "—"}</td>'
            f'</tr>'
        )

    empty_row = '<tr><td colspan="6" style="text-align:center; color:#888; padding: 28px;">暂无明确风险</td></tr>'
    table_body = "".join(rows_html) if rows_html else empty_row
    doc_title = escape(display_title, quote=False)

    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>
{_latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{doc_title}</h1>
      </header>
      <div class="ck-doc-content">
        <table class="ck-risk-table">
          <thead>
            <tr>
              <th style="width: 58px; text-align: center; white-space: nowrap;">序号</th>
              <th style="width: 26%; text-align: center;">风险描述</th>
              <th style="width: 72px; text-align: center; line-height: 1.35; white-space: nowrap;">风险<br>程度</th>
              <th style="width: 24%; text-align: center;">来源</th>
              <th style="width: 20%; text-align: center;">影响</th>
              <th style="width: 23%; text-align: center;">应对</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </div>
  </main>
</body>
</html>
"""
    return page_html


def _parse_actions_from_text(text: str) -> list[dict[str, Any]]:
    """从纯文本或 Markdown 清单中解析结构化待办条目。"""
    actions: list[dict[str, Any]] = []
    lines = (text or "").strip().splitlines()
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        m = re.match(r"^(\d+)[\.、\s]+(.+?)(?:（|\()(.*)(?:）|\))$", line_s)
        if m:
            task = m.group(2).strip()
            meta_str = m.group(3).strip()
            owner = ""
            deadline = ""
            prio = "medium"
            for seg in re.split(r"[；;]", meta_str):
                seg = seg.strip()
                if not seg:
                    continue
                if re.match(r"^(?:负责人|责任人|执行人)[:：]", seg):
                    owner = re.sub(r"^(?:负责人|责任人|执行人)[:：]\s*", "", seg)
                elif re.match(r"^(?:截止|截止时间|时间|交付)[:：]", seg):
                    deadline = re.sub(r"^(?:截止|截止时间|时间|交付)[:：]\s*", "", seg)
                elif re.search(r"高优先|高\b|high", seg, re.I):
                    prio = "high"
                elif re.search(r"低优先|低\b|low", seg, re.I):
                    prio = "low"
            actions.append({
                "task": task,
                "owner": owner,
                "deadline": deadline,
                "priority": prio,
            })
        else:
            if line_s.startswith(("#", "```", "---")):
                continue
            clean_task = re.sub(r"^[-*•\d\.\s]+", "", line_s).strip()
            if clean_task:
                actions.append({
                    "task": clean_task,
                    "owner": "",
                    "deadline": "",
                    "priority": "medium",
                })
    return actions


def render_actions_html(title: str, text: str, data: dict | None = None) -> str:
    """渲染待办提取为宽敞优雅的 LaTeX Paper 风格学术三线表格。
    
    包含列：序号、待办内容、负责人、截止时间。
    内容不存在时使用 "-" 居中展示。
    """
    raw_actions = (data or {}).get("actions")
    if isinstance(raw_actions, list) and raw_actions and isinstance(raw_actions[0], dict):
        actions = raw_actions
    else:
        actions = _parse_actions_from_text(text)

    display_title = "待办提取"

    rows_html = []
    for idx, item in enumerate(actions, start=1):
        task_desc = escape(str(item.get("task") or "").strip(), quote=False)
        owner = escape(str(item.get("owner") or "").strip(), quote=False)
        deadline = escape(str(item.get("deadline") or "").strip(), quote=False)

        owner_display = f'<div style="text-align: center;">{owner}</div>' if (owner and owner not in ("未分配", "null", "None", "无", "-")) else '<div style="text-align: center; color: #888;">-</div>'
        deadline_display = f'<div style="text-align: center; color: #b86a04; font-weight: 600;">{deadline}</div>' if (deadline and deadline not in ("待排期", "未指定", "null", "None", "无", "-")) else '<div style="text-align: center; color: #888;">-</div>'
        task_display = f'<strong style="color: #111111; line-height: 1.65; display: block;">{task_desc}</strong>' if task_desc else '<div style="text-align: center; color: #888;">-</div>'

        rows_html.append(
            f'<tr>'
            f'<td style="text-align: center; font-weight: 700; color: #333;">{idx}</td>'
            f'<td>{task_display}</td>'
            f'<td>{owner_display}</td>'
            f'<td>{deadline_display}</td>'
            f'</tr>'
        )

    empty_row = '<tr><td colspan="4" style="text-align:center; color:#888; padding: 28px;">暂无明确待办</td></tr>'
    table_body = "".join(rows_html) if rows_html else empty_row
    doc_title = escape(display_title, quote=False)

    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{doc_title}</title>
  <style>
{_latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{doc_title}</h1>
      </header>
      <div class="ck-doc-content">
        <table class="ck-risk-table">
          <thead>
            <tr>
              <th style="width: 58px; text-align: center; white-space: nowrap;">序号</th>
              <th style="width: 56%; text-align: center;">待办内容</th>
              <th style="width: 20%; text-align: center;">负责人</th>
              <th style="width: 20%; text-align: center;">截止时间</th>
            </tr>
          </thead>
          <tbody>
            {table_body}
          </tbody>
        </table>
      </div>
    </div>
  </main>
</body>
</html>
"""
    return page_html


__all__ = [
    "MemoryItem",
    "SECTION_TITLE",
    "apply_memory_citations",
    "memory_review_html",
    "parse_memory_items",
    "render_actions_html",
    "render_markdown_page_html",
    "render_risks_html",
]
