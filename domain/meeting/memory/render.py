"""会议记忆 v2 渲染：Markdown 记忆引用 + HTML 审阅栏。

数据源直接来自 ``build_memory_context`` 输出的【会议记忆】块
（延续事项 / 风险演变 / 历史决策 + 原文摘录），不再依赖旧
``tools.memory.citations`` 的【记忆命中 / 记忆来源索引】兼容格式。

- ``apply_memory_citations``：正文锚点标注 + 文末「历史记忆引用」区。
- ``memory_review_html``：左正文高亮 / 右记忆来源卡片（复用现有 review CSS）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any

SECTION_TITLE = "历史记忆引用"

# 记忆块总是追加在（生成/渲染）上下文末尾；贪婪到文末，小节头不参与块边界。
_MEMORY_BLOCK_RE = re.compile(r"【会议记忆】(.*)\Z", re.S)
_SECTION_RE = re.compile(r"【(延续事项|已闭环|风险演变|历史决策|历史对照素材)】")
_KIND_BY_SECTION = {
    "延续事项": "open",
    "已闭环": "closed",
    "风险演变": "risk",
    "历史决策": "decision",
}
_ITEM_RE = re.compile(r"^(?:[-*]|\d+[.)、])\s+(.+)$")
_QUOTE_RE = re.compile(r"^\s*原文摘录：(.+)$")
_SOURCE_RE = re.compile(r"^\s*来源会议：(.+)$")
_TIME_RE = re.compile(r"^\s*会议时间：(.+)$")
# 新 meta 协议（inject._open_meta 等）：括号内不再嵌套括号，字段词形固定，
# 这样 （[^（）()]*）$ 一定剥得掉——旧格式「（第1场（2026-09-01）起…）」嵌套括号
# 剥不掉，实测 15/15 条条目的正文混进内部 meta，卡片上出现「…（第1场（2026-09-01）起，最近第1场」。
_META_TAIL_RE = re.compile(r"[（(]([^（）()]*)[)）]\s*$")
_META_SINCE_RE = re.compile(r"(\S*?第\d+场(?:·[^，,]*)?)起")
_META_LAST_RE = re.compile(r"最近\s*(第\d+场(?:·[^，,]*)?)")
_META_STATUS_RE = re.compile(r"状态\s*([A-Za-z_]+)")
_META_OWNER_RE = re.compile(r"负责人\s*([^，,）)]+)")
_META_TIMING_RE = re.compile(r"时限\s*([^，,）)]+)")
_META_CLOSED_RE = re.compile(r"(第\d+场(?:·[^，,]*)?)关闭")
_META_DECIDED_RE = re.compile(r"(第\d+场(?:·[^，,]*)?)已决策")
_RISK_STATUS_RE = re.compile(r"^(active|mitigated|dormant)\b")
_STATUS_CN = {
    "open": "未闭环",
    "done": "已闭环",
    "closed": "已闭环",
    "active": "持续中",
    "mitigated": "已缓解",
    "dormant": "已沉寂",
    "reaffirmed": "已重申",
    "superseded": "已被取代",
}
# 旧格式兼容（历史块 / 外部注入）
_SINCE_RE = re.compile(r"自\s*([^\s，,]+)\s*，\s*最近\s*([^\s，,)）]+)")
_LAST_RE = re.compile(r"最近\s*([^\s，,)）]+)")
_SESSION_RE = re.compile(r"第\s*(\d+)\s*场")
_DECISION_LEAD_RE = re.compile(r"^(m_[A-Za-z0-9_-]+)：(.+)$")
_MEM_SECTION_RE = re.compile(r"\n(?:-{3,}\s*\n+)*## " + re.escape(SECTION_TITLE) + r"\b.*\Z", re.S)
COMPARISON_TITLE = "历史对照"
_COMPARISON_SECTION_RE = re.compile(
    r"\n(?:-{3,}\s*\n+)*## " + re.escape(COMPARISON_TITLE) + r"\b.*?(?=\n#{1,2} |\Z)", re.S
)
# 台账行：- 类别（主题｜场次说明）：内容 / - 类别（场次说明）：内容 / - 类别：内容
_LEDGER_LINE_RE = re.compile(
    r"^(新增决策|延续事项|已闭环|风险演变)(?:[（(]([^）)]*)[)）])?：(.*)$"
)
_TAG_RE = re.compile(
    r"(?:<sup>)?\[记忆\d+\]\(#memory-\d+\)(?:</sup>)?|class=\"memory-link\"|\[[^\]]+\]\(#memory-\d+\)"
)
_HAN = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_DATE_TERM = re.compile(r"\d{1,4}月\d{1,2}日")
_MIN_ANCHOR = 5
_MAX_ANCHOR = 22
# 数字/单位与高位数：会场里"400min""930""8~9万字"这类锚点精度最高，允许短到 3 字
_NUM_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?(?:min|ms|h|w|s|%|万|字|卡|路|场|小时|分钟|天|周|月|年|多)"
)
_NUM_LONG_RE = re.compile(r"\d{3,}")
_MIN_SCAN = 4  # 汉字词组锚点下限（整词，按标点分句切出来的）
_MIN_GRIND = 4  # 汉字公共子串兜底下限（放宽到 4：跨场复述本来就只剩 3–4 字重合，
#               5 字门槛实测把 13/15 条全挡在门外；命中片段会扩到句读边界再显示）
_MIN_TOKEN = 3  # 数字/拉丁 token 下限
# 泛化过程短语：本身及其任意子串都不能当锚点。2026-09-21 实测：
# 「下来找他们」把"现网流量数据"条目挂到了本场"微服务测试"那句上（挂错比挂不上更差）。
_GENERIC_NEEDLES = (
    "下来找他们", "下来再", "下来找", "对一下", "看一下", "再看一下", "问一下", "再问",
    "再对", "找他们", "找个", "群里", "这边", "那边", "这块", "后续", "待确认", "需确认",
    "再确认", "什么时候", "这个", "那个", "可以", "应该", "可能", "需要", "还没", "再看",
    "下来", "拉人", "一下", "以及", "同时", "另外",
)
from tools.core.text import clean_text as _clean
_MAX_NEEDLE_LINES = 3  # 同一锚点文本的行频上限（还会按篇幅放大：长文里 5 次不算泛）
# 单位词/英文虚词不能当锚点：数值锚点里的 "min" 会被单独抽成拉丁 token，
# 实测把"还差400min"条目挂到了另一句的 "49min" 上（同字不同事）。
_LATIN_SKIP = frozenset({
    "min", "mins", "sec", "secs", "ms", "hr", "hrs", "hour", "hours", "day", "days",
    "week", "weeks", "and", "the", "for", "with", "you", "not", "are", "was", "his",
    "her", "our", "its", "can", "has", "have", "will", "that", "this", "from", "they",
    "but", "all", "any", "one", "two", "new", "old", "now", "out",
})


@dataclass
class MemoryItem:
    """一条可溯源的历史记忆条目（含状态机字段）。"""

    kind: str  # open / closed / risk / decision
    text: str
    quote: str = ""
    meeting_id: str = ""  # 最近场次（open/risk 为 last_seen，decision 为 meeting_id）
    since: str = ""
    meeting_title: str = ""  # 最近场次会议标题（引用区"来源会议"）
    meeting_time: str = ""  # 该场会议时间（请求体 time；空则不展示）
    status: str = ""  # open / done / active / mitigated / dormant / reaffirmed …
    owner: str = ""  # 待办负责人（有则展示）
    timing: str = ""  # 时限（有则展示）


def _split_meta(body: str) -> tuple[str, str]:
    """把条目行拆成 (正文, meta)。

    新协议优先（括号内无嵌套 → 一次剥净）；旧协议退回"最后一个左括号"的启发式，
    只用于兼容历史块。
    """
    match = _META_TAIL_RE.search(body)
    if match and match.start() > 0:
        return body[: match.start()].strip(), match.group(1)
    idx = body.rfind("（")
    if idx > 0 and body.endswith("）"):
        meta = body[idx:]
        if "第" in meta or "状态" in meta or "已决策" in meta or "关闭" in meta:
            return body[:idx].strip(), meta
    return body, ""


def _meta_fields(meta: str) -> dict[str, str]:
    """从 meta 文本取 state 字段（新协议 + 旧格式兼容）。"""
    out: dict[str, str] = {}
    status = _META_STATUS_RE.search(meta)
    if not status:
        risk_status = _RISK_STATUS_RE.match(_clean(meta))
        status = risk_status if risk_status else None
    if status:
        out["status"] = status.group(1)
    owner = _META_OWNER_RE.search(meta)
    if owner:
        out["owner"] = _clean(owner.group(1))
    timing = _META_TIMING_RE.search(meta)
    if timing:
        out["timing"] = _clean(timing.group(1))
    since = _META_SINCE_RE.search(meta)
    if since:
        out["since"] = _clean(since.group(1))
    last = _META_LAST_RE.search(meta)
    if last:
        out["last"] = _clean(last.group(1))
    closed = _META_CLOSED_RE.search(meta)
    if closed:
        out["closed_at"] = _clean(closed.group(1))
        out.setdefault("status", "done")
    decided = _META_DECIDED_RE.search(meta)
    if decided:
        out["decided"] = _clean(decided.group(1))
    if "since" in out or "last" in out or "decided" in out:
        return out
    # 旧格式：自 X，最近 Y / 最近 Y
    legacy = _SINCE_RE.search(meta)
    if legacy:
        out["since"] = _clean(legacy.group(1))
        out["last"] = _clean(legacy.group(2))
        return out
    legacy_last = _LAST_RE.search(meta)
    if legacy_last:
        out["last"] = _clean(legacy_last.group(1))
        return out
    sessions = _SESSION_RE.findall(meta)
    if sessions:
        out["since"] = out.get("since") or f"第{sessions[0]}场"
        out["last"] = out.get("last") or f"第{sessions[-1]}场"
    return out


def parse_memory_items(context: str) -> list[MemoryItem]:
    """从【会议记忆】块解析出可溯源条目。

    兼容两种形态：
    - 新协议 ``- 文本（第2场·2026-09-08起，最近第2场·2026-09-08，状态 open，负责人 武思华）``
    - 旧协议 ``- 文本（自 X，最近 Y）`` / ``- m_xxx：文本``（历史块兼容）

    ``status/owner/timing`` 一并解析出来：状态机在 state 里维护齐全，但过去没有承载字段，
    卡片上永远看不到「已闭环/已缓解/已取代」。
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
            if section == "历史对照素材":
                continue
            body = _clean(item_match.group(1))
            meeting_id = ""
            lead = _DECISION_LEAD_RE.match(body)
            if lead:
                meeting_id = lead.group(1)
                body = _clean(lead.group(2))
            body, meta = _split_meta(body)
            fields = _meta_fields(meta)
            if not body:
                continue
            pending = MemoryItem(
                kind=_KIND_BY_SECTION.get(section, "history"),
                text=body,
                meeting_id=meeting_id or fields.get("last") or fields.get("decided") or "",
                since=fields.get("since") or "",
                status=fields.get("status") or "",
                owner=fields.get("owner") or "",
                timing=fields.get("timing") or "",
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
    """正文行与记忆条目是否可能相关（预筛，宁漏勿滥）。

    信号分级：整句互相包含（≥4 字）、共享拉丁专名或日期 token（强实体信号，
    如 minutes_trace / Gradio / 8月20日）、长分句互相包含（≥5 字）、
    共享 ≥4 字连续汉字片段。
    """
    a, b = _clean(line), _clean(item.text)
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) >= _MIN_GRIND
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


_SPAN_BOUNDARY = set("，。；;、：:！？!?）)】」》”\"' \t")


def _expand_span(
    line: str, start: int, end: int, cap: int = _MAX_ANCHOR
) -> tuple[int, int]:
    """把命中片段扩到句读边界（不超过 cap 字）：正文里读到的是完整短语。

    放宽到 4 字后若直接显示命中片段，会挂出「时候带上」这种半句碎片；
    扩到边界后同一处显示成「大概什么时候带上版本」，读者能看懂在引什么。
    """
    if end - start >= cap:
        return start, end
    left, right = start, end
    while left > 0 and (right - left) < cap and line[left - 1] not in _SPAN_BOUNDARY:
        left -= 1
    while right < len(line) and (right - left) < cap and line[right] not in _SPAN_BOUNDARY:
        right += 1
    return left, right


def _exact_span(
    line: str, needle: str, min_len: int = _MIN_ANCHOR
) -> tuple[int, int] | None:
    needle = _clip_anchor(needle)
    if len(needle) < min_len:
        return None
    idx = line.find(needle)
    if idx < 0:
        return None
    return idx, idx + len(needle)


def _is_generic(needle: str) -> bool:
    """泛化过程短语（含其任意子串）不能当锚点。"""
    return any(needle in g for g in _GENERIC_NEEDLES)


def _needles(text: str) -> list[str]:
    """按精度排序的候选锚点：数字/日期/拉丁专名 → 汉字词组（长的在前）。

    方向是"条目 → 本场证据"：先把条目里**精度最高**的串（数字、单位、专名）拿去正文里找，
    找不到再退到汉字词组。旧实现只按"最长"排序且没有精度概念，长短语一失配就一路降到
    5 字公共子串，于是"下来找他们"这种泛化短语成了唯一的命中项。
    """
    high: list[str] = []
    low: list[str] = []
    seen: set[str] = set()

    def _add(bucket: list[str], value: object, min_len: int) -> None:
        candidate = _clean(value)
        if len(candidate) < min_len or candidate in seen or _is_generic(candidate):
            return
        if candidate.lower() in _LATIN_SKIP:
            return
        seen.add(candidate)
        bucket.append(candidate)

    for pattern in (_DATE_TERM, _NUM_UNIT_RE, _NUM_LONG_RE):
        for token in pattern.findall(text):
            _add(high, token, _MIN_TOKEN)
    for token in _LATIN_TERM.findall(text):
        _add(high, token, _MIN_TOKEN)
    for chunk in re.split(r"[，。；;、\s]+", text):
        _add(low, chunk, _MIN_SCAN)
    low.sort(key=len, reverse=True)
    return high + low


class _NeedleStats:
    """锚点文本的正文行频：出现太多行说明是个泛词（满篇的 demo），不是证据。

    阈值随篇幅放大——126 行的纪要里 "WeLink" 出现 7 次仍是有意义的共同话题，
    固定 3 行会把这类真锚点一起误杀。
    """

    def __init__(self, lines: list[str], cap: int = _MAX_NEEDLE_LINES) -> None:
        self._lines = lines
        self._cap = max(cap, len(lines) // 8)
        self._cache: dict[str, bool] = {}

    def too_common(self, needle: str) -> bool:
        hit = self._cache.get(needle)
        if hit is None:
            hit = sum(1 for line in self._lines if needle in line) > self._cap
            self._cache[needle] = hit
        return hit


def _match_span(
    line: str,
    item: MemoryItem,
    stats: _NeedleStats | None = None,
) -> tuple[int, int, int] | None:
    """在正文行里找该条目的锚点，返回 ``(start, end, 命中长度)``（**未展开**）。

    命中长度是"有多硬"的证据：调用方用它让长命中优先占位，避免 4 字的弱命中
    把另一条 10 字的强命中挤掉（实测："是否默认开启记忆引用" 靠 4 字「记忆引用」
    抢先，结果把「补齐记忆引用来源字段」的锚点吞掉，卡片与正文对不上）。
    """
    ref_text = _clean(item.text)
    if not line or not ref_text:
        return None
    for needle in _needles(ref_text):
        if stats is not None and stats.too_common(needle):
            continue
        min_len = _MIN_TOKEN if not _HAN.search(needle) else _MIN_SCAN
        span = _exact_span(line, needle, min_len)
        if span:
            return span[0], span[1], len(needle)
    # 兜底：条目汉字里的连续子串（长的优先），4 字起且避开泛化短语/泛词
    right = "".join(ch for ch in ref_text if "\u4e00" <= ch <= "\u9fff")
    for size in range(min(_MAX_ANCHOR, len(right)), _MIN_GRIND - 1, -1):
        for i in range(0, len(right) - size + 1):
            candidate = right[i : i + size]
            if _is_generic(candidate):
                continue
            if stats is not None and stats.too_common(candidate):
                continue
            span = _exact_span(line, candidate, _MIN_GRIND)
            if span:
                return span[0], span[1], size
    return None


def _best_span(
    line: str,
    item: MemoryItem,
    stats: _NeedleStats | None = None,
) -> tuple[int, int] | None:
    """单条锚点（含句读边界展开）；供外部直接调用，条目间竞争见 ``_append_markers``。"""
    match = _match_span(line, item, stats)
    if match is None:
        return None
    return _expand_span(line, match[0], match[1])


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
    stats: _NeedleStats | None = None,
) -> tuple[str, list[MemoryItem]]:
    if not items or _TAG_RE.search(line):
        return line, []
    seen = seen or []
    # 同一记忆实体只在正文首次出现处锚定溯源，重复出现不再标注。
    hits = [item for item in items if item not in seen and _related(line, item)]
    if not hits:
        return line, []
    # 命中越长越硬，先占位；同样长按条目顺序。占位判定用**未展开**片段，
    # 展开只用于显示——否则 4 字弱命中扩成整句后会把别人的强命中吞掉。
    matched: list[tuple[int, int, int, int, MemoryItem]] = []
    for order, item in enumerate(hits):
        span = _match_span(line, item, stats)
        if span is None:
            continue
        matched.append((span[0], span[1], span[2], order, item))
    matched.sort(key=lambda row: (-row[2], row[3]))
    chosen: list[tuple[int, int, MemoryItem]] = []
    for start, end, _hard, _order, item in matched:
        if any(not (end <= s or start >= e) for s, e, _ in chosen):
            continue
        chosen.append((start, end, item))
        if len(chosen) >= 2:
            break
    if not chosen:
        return line, []
    chosen.sort(key=lambda row: row[0])
    spans: list[tuple[int, int, MemoryItem]] = []
    for index, (start, end, item) in enumerate(chosen):
        lo, hi = _expand_span(line, start, end)
        if index + 1 < len(chosen):
            hi = min(hi, chosen[index + 1][0])  # 不越过相邻锚点
        spans.append((lo, hi, item))
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


def history_comparison_section(lines: list[str]) -> str:
    """「历史对照」小节：程序算好的四类对照（不依赖词面重合，永远可见）。

    为什么单独成节：模型被明确要求"历史不写进正文"，而正文锚点只在**词面巧合**时
    才挂得上（实测第二场 15 条只挂上 2 条，且都是在泛词上）。对照是程序用条目+场次
    拼的确定性文本，落盘才有"记忆看得见"的兜底。
    """
    rows = [_clean(line) for line in (lines or []) if _clean(line)]
    if not rows:
        return ""
    return "\n".join(
        ["", f"## {COMPARISON_TITLE}", ""] + [f"- {row}" for row in rows]
    )


def _status_line(item: MemoryItem) -> str:
    """卡片上的状态行：``状态：未闭环（负责人 武思华，时限 8月19日前）``。"""
    status = (item.status or "").strip()
    bits: list[str] = []
    if item.owner:
        bits.append(f"负责人 {item.owner}")
    if item.timing:
        bits.append(f"时限 {item.timing}")
    if item.since and item.meeting_id and item.since != item.meeting_id:
        bits.append(f"{item.since} 起，最近 {item.meeting_id}")
    if not status and not bits:
        return ""
    label = _STATUS_CN.get(status, status) or "历史"
    tail = f"（{'，'.join(bits)}）" if bits else ""
    return f"状态：{label}{tail}"


def apply_memory_citations(
    markdown: str,
    context: str,
    comparison: list[str] | None = None,
) -> str:
    """给渲染后的纪要加记忆引用标注 + 「历史对照」小节 + 文末「历史记忆引用」区。

    保守锚定、不改事实措辞、只追加标记；上下文无【会议记忆】块时原样返回。
    ``comparison``：程序算好的历史对照（build_memory_context 的第二个返回值），
    无条件写成固定小节——它是零锚点时的唯一可见溯源。
    """
    body = markdown or ""
    comparison_section = history_comparison_section(list(comparison or []))
    # 幂等：先摘掉已有的对照/溯源小节（重复调用不再叠加）
    body = _COMPARISON_SECTION_RE.sub("", body)
    body = _MEM_SECTION_RE.sub("", body).strip()
    if not body:
        return markdown or ""

    items = parse_memory_items(context)
    if not items:
        return body + comparison_section

    citable = [line for line in body.splitlines() if _is_citeable_line(line)]
    stats = _NeedleStats(citable)
    used: list[MemoryItem] = []
    seen: list[MemoryItem] = []
    lines: list[str] = []
    for line in body.splitlines():
        if _is_citeable_line(line):
            line, found = _append_markers(line, items, seen, stats)
            for item in found:
                if item not in seen:
                    seen.append(item)
                    used.append(item)
        lines.append(line)

    # 正文没有任何可精确锚定的行时，不伪造溯源入口：既不声明命中，也不生成
    # 「历史记忆引用」区（宁可无引用，也不在正文插入「记忆命中」这类系统表达）。
    if not used:
        return "\n".join(lines) + comparison_section

    appendix = ["", f"## {SECTION_TITLE}", ""]
    for item in used:
        ref_id = f"memory-{items.index(item) + 1}"
        source = item.meeting_title or item.meeting_id or "历史会议"
        quote = item.quote or item.text
        rows = [
            f"#### 溯源 {ref_id}",
            f"> {quote}",
        ]
        status_line = _status_line(item)
        if status_line:
            rows.append(status_line)
        rows.append(f"来源会议：{source}")
        if item.meeting_time:
            rows.append(f"会议时间：{item.meeting_time}")
        appendix.extend(rows)
    return "\n".join(lines) + comparison_section + "\n" + "\n".join(appendix)


from tools.exports.html.paper_css import latex_paper_css as _latex_paper_css


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
        status = ""
        for line in lines:
            if line.startswith(">"):
                quote = line.lstrip("> ").strip()
            elif line.startswith("来源会议："):
                title = line.removeprefix("来源会议：").strip()
            elif line.startswith("会议时间："):
                mtime = line.removeprefix("会议时间：").strip()
            elif line.startswith("状态："):
                status = line.removeprefix("状态：").strip()
        out[ref_id] = {"quote": quote, "title": title, "time": mtime, "status": status}
    return out


_SELF_HEAD_RE = re.compile(r"^###\s+(?:\[|\()?.*(?:与我相关|本人|待我攻坚|待我解决)")
_SELF_GROUP_RE = re.compile(r"^\s*(?:-\s*)?\*\*(?:与我相关[^*]*|本人[^*]*|待我[^*]*)\*\*[：:]?\s*$")

_DEP_HEAD_RE = re.compile(r"^###\s+(?:\[|\()?.*(?:协同输入|关注人定调|前置依赖|外部依赖)")
_DEP_GROUP_RE = re.compile(r"^\s*(?:-\s*)?\*\*(?:协同输入[^*]*|关注人定调[^*]*|前置依赖[^*]*|外部依赖[^*]*)\*\*[：:]?\s*$")

_RISK_HEAD_RE = re.compile(r"^###\s+(?:\[|\()?.*(?:全局重大风险|全局风险|未决争议|外部阻塞)")
_RISK_GROUP_RE = re.compile(r"^\s*(?:-\s*)?\*\*(?:全局风险与未决[^*]*|全局重大风险[^*]*|外部阻塞[^*]*|未决争议[^*]*)\*\*[：:]?\s*$")

_OTHER_GROUP_RE = re.compile(r"^\s*(?:-\s*)?\*\*([^*:\n]{1,20})\*\*[：:]?\s*$")
_TASK_ITEM_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s*(.*)$")


def _format_inline_tags(text: str) -> str:
    """格式化纪要中的状态徽章、依赖标签与参数胶囊。"""
    text = re.sub(r"【(?:阻塞|阻碍)】", r'<span class="ck-tag-blocker">阻塞</span>', text)
    text = re.sub(r"【(高风险|中风险|低风险)】", r'<span class="ck-tag-risk">\1</span>', text)
    text = re.sub(r"【(?:待确认|待决)】", r'<span class="ck-tag-warn">待确认</span>', text)
    text = re.sub(r"[\[【]([\u4e00-\u9fff]{2,8}(?:依赖|定调|输入|输出|评审))[\]】]", r'<span class="ck-tag-dep">\1</span>', text)
    text = re.sub(r"（([^）\n]+(?:[｜|][^）\n]+)+)）", r'<span class="ck-param-capsule">（\1）</span>', text)
    text = re.sub(r"\(([^)\n]+(?:[｜|][^)\n]+)+)\)", r'<span class="ck-param-capsule">(\1)</span>', text)
    return text


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
    task_buf: list[tuple[bool, str]] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []
    active_block: str | None = None

    def flush_tasks() -> None:
        if task_buf:
            items_html = "".join(
                f'<li class="ck-task-item"><label class="ck-task-label">'
                f'<input type="checkbox" class="ck-task-checkbox"{" checked" if chk else ""}>'
                f'<span class="ck-task-text">{txt}</span></label></li>'
                for chk, txt in task_buf
            )
            out.append(f'<ul class="ck-task-list">{items_html}</ul>')
            task_buf.clear()

    def flush_ul() -> None:
        if list_buf:
            items_html = []
            for item in list_buf:
                if isinstance(item, dict):
                    subs_html = ""
                    if item.get("subs"):
                        subs_html = "<ul>" + "".join(f"<li>{s}</li>" for s in item["subs"]) + "</ul>"
                    items_html.append(f"<li>{item['text']}{subs_html}</li>")
                else:
                    items_html.append(f"<li>{item}</li>")
            out.append("<ul>" + "".join(items_html) + "</ul>")
            list_buf.clear()

    def flush_ol() -> None:
        if ol_buf:
            items_html = []
            for item in ol_buf:
                if isinstance(item, dict):
                    num_attr = f' value="{item["num"]}"' if item.get("num") else ""
                    subs_html = ""
                    if item.get("subs"):
                        subs_html = "<ul>" + "".join(f"<li>{s}</li>" for s in item["subs"]) + "</ul>"
                    items_html.append(f'<li{num_attr}>{item["text"]}{subs_html}</li>')
                else:
                    items_html.append(f"<li>{item}</li>")
            out.append("<ol>" + "".join(items_html) + "</ol>")
            ol_buf.clear()

    def flush_list() -> None:
        flush_tasks()
        flush_ul()
        flush_ol()

    def close_active_block() -> None:
        nonlocal active_block
        if active_block is not None:
            flush_list()
            out.append("</div>")
            active_block = None

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
        text = _format_inline_tags(text)
        return text

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        stripped = raw_line.strip()
        if not stripped:
            if ol_buf:
                next_is_ol = False
                for j in range(i + 1, len(lines)):
                    next_s = lines[j].strip()
                    if next_s:
                        if re.match(r"^\s*\d+[.)、]\s+", lines[j]):
                            next_is_ol = True
                        break
                if not next_is_ol:
                    flush_list()
            else:
                flush_list()
            i += 1
            continue

        if stripped.startswith("### "):
            h_text = stripped[4:].strip()
            if h_text.startswith("[") and h_text.endswith("]"):
                h_text = h_text[1:-1].strip()

            if _SELF_HEAD_RE.match(stripped):
                close_active_block()
                flush_list()
                active_block = "self"
                out.append(f'<div class="ck-self-block"><div class="ck-self-title"><strong>{inline_format(h_text)}</strong><span class="ck-self-badge">本人</span></div>')
                i += 1
                continue
            if _DEP_HEAD_RE.match(stripped):
                close_active_block()
                flush_list()
                active_block = "dep"
                out.append(f'<div class="ck-dep-block"><div class="ck-dep-title"><strong>{inline_format(h_text)}</strong><span class="ck-dep-badge">协同依赖</span></div>')
                i += 1
                continue
            if _RISK_HEAD_RE.match(stripped):
                close_active_block()
                flush_list()
                active_block = "risk"
                out.append(f'<div class="ck-risk-block"><div class="ck-risk-title"><strong>{inline_format(h_text)}</strong><span class="ck-risk-badge">全局风险</span></div>')
                i += 1
                continue

            close_active_block()
            flush_list()
            out.append(f'<h3 class="ck-doc-h3">{inline_format(h_text)}</h3>')
            i += 1
            continue

        if stripped.startswith("## "):
            close_active_block()
            flush_list()
            h_text = stripped[3:].strip()
            if h_text.startswith("[") and h_text.endswith("]"):
                h_text = h_text[1:-1].strip()
            out.append(f'<h2 class="ck-doc-h2">{inline_format(h_text)}</h2>')
            i += 1
            continue

        if stripped.startswith("# "):
            close_active_block()
            flush_list()
            h_text = stripped[2:].strip()
            if h_text.startswith("[") and h_text.endswith("]"):
                h_text = h_text[1:-1].strip()
            out.append(f'<h2>{inline_format(h_text)}</h2>')
            i += 1
            continue

        if _SELF_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "self"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "与我相关"
            out.append(f'<div class="ck-self-block"><div class="ck-self-title"><strong>{inline_format(g_title)}</strong><span class="ck-self-badge">本人</span></div>')
            i += 1
            continue

        if _DEP_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "dep"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "协同输入"
            out.append(f'<div class="ck-dep-block"><div class="ck-dep-title"><strong>{inline_format(g_title)}</strong><span class="ck-dep-badge">协同依赖</span></div>')
            i += 1
            continue

        if _RISK_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "risk"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "全局风险与未决"
            out.append(f'<div class="ck-risk-block"><div class="ck-risk-title"><strong>{inline_format(g_title)}</strong><span class="ck-risk-badge">全局风险</span></div>')
            i += 1
            continue

        if _OTHER_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            out.append(f'<p class="ck-person-group">{inline_format(stripped)}</p>')
            i += 1
            continue

        m_task = _TASK_ITEM_RE.match(raw_line)
        if m_task:
            flush_ul()
            flush_ol()
            is_chk = m_task.group(1).lower() == "x"
            item_text = m_task.group(2).strip()
            task_buf.append((is_chk, inline_format(item_text)))
            i += 1
            continue

        m_ol = re.match(r"^\s*(\d+)[.)、]\s+(.*)$", raw_line)
        if m_ol:
            flush_tasks()
            flush_ul()
            ol_buf.append({"num": m_ol.group(1), "text": inline_format(m_ol.group(2).strip()), "subs": []})
            i += 1
            continue

        if ol_buf and re.match(r"^\s{2,}[-*]\s+(.*)$", raw_line):
            m_sub = re.match(r"^\s{2,}[-*]\s+(.*)$", raw_line)
            ol_buf[-1]["subs"].append(inline_format(m_sub.group(1).strip()))
            i += 1
            continue

        if list_buf and re.match(r"^\s{2,}[-*]\s+(.*)$", raw_line):
            m_sub = re.match(r"^\s{2,}[-*]\s+(.*)$", raw_line)
            list_buf[-1]["subs"].append(inline_format(m_sub.group(1).strip()))
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", raw_line):
            flush_tasks()
            flush_ol()
            list_buf.append({"text": inline_format(re.sub(r"^\s*[-*]\s+", "", raw_line)), "subs": []})
            i += 1
            continue

        if stripped.startswith(">"):
            close_active_block()
            flush_list()
            out.append(f'<div class="ck-quote">{inline_format(stripped.lstrip("> "))}</div>')
            i += 1
            continue

        close_active_block()
        flush_list()
        out.append(f'<p>{inline_format(stripped)}</p>')
        i += 1

    flush_list()
    close_active_block()
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
      const ledger = listEl.querySelector('.ck-ledger');
      const ledgerUser = ledger ? (ledger.dataset.user || '') : '';
      const setLedgerOpen = (next) => {
        if (!ledger || ledger.open === next) return;
        // details 的 toggle 事件是异步派发的，busy 标志到那时已被清掉——用"程序意图"对比：
        // 收到与意图一致的 toggle 就认作程序所为，否则才算用户手动选择。
        ledger.dataset.prog = next ? 'open' : 'closed';
        ledger.open = next;
        ledger.dataset.auto = next ? '' : '1';
      };
      // 量高度前先展开「状态演进」（除非用户自己折了）；用户手动展开的一律尊重，不再自动折
      if (ledger && ledgerUser !== 'closed' && !ledger.open) setLedgerOpen(true);

      if (allEvs.length === 0 && !ledger) return;

      const leftContentHeight = getActualContentHeight(leftEl);
      const measure = (el) => {
        const r = el.getBoundingClientRect();
        return ((r && r.height > 0) ? r.height : el.offsetHeight) + 10;
      };

      if (ledger && isDesktop) {
        // 判据：对照**明显**比左栏还长才折（留 15% 容差，避免刚好擦边就折叠）；
        // 证据卡（带行内锚点）永远优先留可见，证据自己超高时由下面"查看更多"兜底。
        const ledgerHeight = ledger.getBoundingClientRect().height;
        const tooTall = ledgerHeight > leftContentHeight * 1.15;
        if (tooTall && ledgerUser !== 'open') {
          setLedgerOpen(false);
        } else if (!tooTall && ledger.dataset.auto === '1' && ledgerUser !== 'closed') {
          setLedgerOpen(true);           // 空间恢复（如放大窗口）再展开
        }
      }

      if (allEvs.length <= 1) return;

      let totalHeight = 0;
      const itemsToFold = [];

      allEvs.forEach((ev, idx) => {
        if (!isDesktop) {
          if (idx >= 3) itemsToFold.push(ev);
          return;
        }
        const evRect = ev.getBoundingClientRect();
        const evHeight = (evRect && evRect.height > 0) ? evRect.height + 10 : ev.offsetHeight + 10;
        // 「状态演进」已让位后仍超出，才折证据卡（最后手段）
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
        summary.innerHTML = `查看更多本场证据 (${itemsToFold.length}) ▾`;
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

  // 「状态演进」的展开/折叠：记下"用户手动选择"，自动折叠不覆盖它
  document.querySelectorAll('.ck-ledger').forEach((el) => {
    el.addEventListener('toggle', () => {
      const intent = el.dataset.prog || '';
      el.dataset.prog = '';
      const programmatic =
        (intent === 'open' && el.open) || (intent === 'closed' && !el.open);
      if (programmatic) return;
      el.dataset.user = el.open ? 'open' : 'closed';
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


def _parse_comparison_ledger(markdown: str) -> tuple[list[dict[str, str]], str]:
    """从「历史对照」小节解析「状态演进」清单，返回 (条目列表, 汇总行)。

    行格式：``- 延续事项（端侧待办｜自第1场·2026-09-01）：端侧大概什么时候带上版本``；
    新增决策可能没有主题（``- 新增决策：…``），此时只有类别。
    """
    raw = markdown or ""
    marker = f"## {COMPARISON_TITLE}"
    if marker not in raw:
        return [], ""
    chunk = raw.split(marker, 1)[1]
    chunk = re.split(r"\n#{1,2} ", chunk)[0]
    rows: list[dict[str, str]] = []
    summary = ""
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:].strip()
        if body.startswith("本场历史对照合计"):
            summary = body.split("：", 1)[-1].strip()
            continue
        match = _LEDGER_LINE_RE.match(body)
        if not match:
            continue
        kind, meta, text = match.group(1), _clean(match.group(2)), _clean(match.group(3))
        topic = ""
        tail = meta
        if "｜" in meta:
            topic, tail = (_clean(part) for part in meta.split("｜", 1))
        rows.append({"kind": kind, "topic": topic, "meta": tail, "text": text})
    return rows, summary


# 右栏「状态演进」只展示这三类，顺序固定（风险演变只保留在正文对照里）
_LEDGER_PANEL_ORDER = ("延续事项", "已闭环", "新增决策")


def _ledger_cards_html(rows: list[dict[str, str]]) -> str:
    """状态演进：**每类一张小灰卡，卡内条目各自编号 1. 2. 3.**。

    只展示三类，顺序固定 延续事项 → 已闭环 → 新增决策（风险演变不进右栏，只在正文
    「## 历史对照」里保留）。每卡卡头是类别 + 条数，卡内是该类的有序列表；整块灰底、
    无 [n] 序号（不冒充正文证据）。
    """
    keep = [row for row in rows if row.get("kind", "") in _LEDGER_PANEL_ORDER]
    if not keep:
        return ""
    keep.sort(key=lambda row: _LEDGER_PANEL_ORDER.index(row.get("kind", "")))
    groups: list[tuple[str, list[dict[str, str]]]] = []
    for row in keep:
        kind = row.get("kind", "")
        if groups and groups[-1][0] == kind:
            groups[-1][1].append(row)
        else:
            groups.append((kind, [row]))
    cards: list[str] = []
    for kind, items in groups:
        lis: list[str] = []
        for row in items:
            bits = [bit for bit in (row.get("topic"), row.get("meta")) if bit]
            meta_html = (
                f' <span class="ck-ledger-meta">（{escape(" · ".join(bits), quote=False)}）</span>'
                if bits
                else ""
            )
            lis.append(
                f'<li><span class="ck-ledger-text">{escape(row.get("text", ""), quote=False)}</span>'
                f"{meta_html}</li>"
            )
        cards.append(
            f'<aside class="ck-ledger-card" data-kind="{escape(kind, quote=True)}">'
            f'<div class="ck-ledger-k">'
            f'<span class="ck-ledger-badge">{escape(kind, quote=False)}</span>'
            f'<span class="ck-ledger-count">（{len(items)}）</span></div>'
            f'<ol class="ck-ledger-list">{"".join(lis)}</ol>'
            f"</aside>"
        )
    return (
        f'<details class="ck-ledger" open>'
        f'<summary class="ck-proof-toggle">状态演进（{len(keep)} 条）</summary>'
        f"{''.join(cards)}</details>"
    )


def memory_review_html(markdown: str, title: str = "") -> str:
    """把带记忆链接的纪要渲染为与 checklist 一致的 LaTeX Paper 风格 HTML。

    左侧：纪要正文排版，命中记忆的实体高亮并在后面附加蓝色 [1], [2] 序号标签。
    右侧：历史记忆溯源卡片，带有连续序号 [1], [2] 与来源会议/摘录/时间。
    交互：点击左侧实体或蓝色序号可点亮对应右侧记忆卡片并带光晕脉冲动画；右侧超出左侧高度时自适应折叠。
    
    若未命中记忆（无记忆链接），自动平滑降级为纯净单栏 LaTeX Paper 风格 HTML（无右侧卡片区）。
    """
    text = markdown or ""
    if "](#" not in text:
        return render_markdown_page_html(title or "会议纪要", text)

    splits = re.split(r"\n## " + re.escape(SECTION_TITLE) + r"\b", text, maxsplit=1)
    main = splits[0]
    sources = _parse_memory_sources(text)
    if not sources:
        return render_markdown_page_html(title or "会议纪要", main)

    # 「历史对照」在双栏页里改由右栏「状态演进」呈现（正文不再重复同一份清单）
    ledger_rows, _summary = _parse_comparison_ledger(text)
    main = _COMPARISON_SECTION_RE.sub("", main).strip()

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
    display_title = title or meeting_title or "会议纪要"

    cards_html: list[str] = []
    for ref_id in ordered_ref_ids:
        num = ref_id_to_num.get(ref_id, 1)
        info = sources.get(ref_id, {})
        m_title = info.get("title") or "历史会议"
        quote = info.get("quote") or ""
        mtime = info.get("time") or ""
        mstatus = info.get("status") or ""

        card = [
            f'<aside class="ck-ev ck-mem-card" id="card-{escape(ref_id, quote=True)}" data-mem="{escape(ref_id, quote=True)}" data-cite="{num}">',
            f'<div class="ck-ev-k"><a class="ck-ev-cite-tag" href="javascript:void(0);">[{num}]</a> <span class="ck-ev-kind-badge">历史会议</span></div>',
            f'<div class="ck-mem-title"><strong>{escape(m_title, quote=False)}</strong></div>',
        ]
        if quote:
            card.append(f'<div class="ck-ev-quote">“{escape(quote, quote=False)}”</div>')
        if mstatus:
            card.append(f'<div class="ck-ev-meta">状态：{escape(mstatus, quote=False)}</div>')
        if mtime:
            card.append(f'<div class="ck-ev-meta">会议时间：{escape(mtime, quote=False)}</div>')
        card.append("</aside>")
        cards_html.append("".join(card))

    # 右栏：证据卡（带行内锚点/[n]）+ 下方「状态演进」（无锚点）
    evidence_html = "".join(cards_html) + _ledger_cards_html(ledger_rows)

    page_html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(display_title, quote=False)}</title>
  <style>
{_latex_paper_css()}
  </style>
</head>
<body>
  <main class="page">
    <div class="ck-doc">
      <header class="ck-doc-header">
        <h1>{escape(display_title, quote=False)}</h1>
      </header>
      <div class="ck-review">
        <div class="ck-review-left">
          {left_html}
        </div>
        <div class="ck-review-rule"></div>
        <div class="ck-review-right">
          <div class="ck-ev-list">
            {evidence_html}
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


# ── 风险提取（Risks）、待办提取（Actions）与 无记忆纪要 LaTeX Paper 渲染 ────────


def _render_markdown_content(text: str) -> str:
    """把 Markdown 转换为符合 LaTeX Paper 风格的 HTML 片段（保留 Markdown 原始格式）。"""
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    task_buf: list[tuple[bool, str]] = []
    list_buf: list[str] = []
    ol_buf: list[str] = []
    active_block: str | None = None

    def flush_tasks() -> None:
        if task_buf:
            items_html = "".join(
                f'<li class="ck-task-item"><label class="ck-task-label">'
                f'<input type="checkbox" class="ck-task-checkbox"{" checked" if chk else ""}>'
                f'<span class="ck-task-text">{txt}</span></label></li>'
                for chk, txt in task_buf
            )
            out.append(f'<ul class="ck-task-list">{items_html}</ul>')
            task_buf.clear()

    def flush_ul() -> None:
        if list_buf:
            items_html = []
            for item in list_buf:
                if isinstance(item, dict):
                    subs_html = ""
                    if item.get("subs"):
                        subs_html = "<ul>" + "".join(f"<li>{s}</li>" for s in item["subs"]) + "</ul>"
                    items_html.append(f"<li>{item['text']}{subs_html}</li>")
                else:
                    items_html.append(f"<li>{item}</li>")
            out.append("<ul>" + "".join(items_html) + "</ul>")
            list_buf.clear()

    def flush_ol() -> None:
        if ol_buf:
            items_html = []
            for item in ol_buf:
                if isinstance(item, dict):
                    num_attr = f' value="{item["num"]}"' if item.get("num") else ""
                    subs_html = ""
                    if item.get("subs"):
                        subs_html = "<ul>" + "".join(f"<li>{s}</li>" for s in item["subs"]) + "</ul>"
                    items_html.append(f'<li{num_attr}>{item["text"]}{subs_html}</li>')
                else:
                    items_html.append(f"<li>{item}</li>")
            out.append("<ol>" + "".join(items_html) + "</ol>")
            ol_buf.clear()

    def flush_list() -> None:
        flush_tasks()
        flush_ul()
        flush_ol()

    def close_active_block() -> None:
        nonlocal active_block
        if active_block is not None:
            flush_list()
            out.append("</div>")
            active_block = None

    def inline(s: str) -> str:
        esc = escape(s, quote=False)
        esc = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', esc)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", esc)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        esc = _format_inline_tags(esc)
        return esc

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            if ol_buf:
                next_is_ol = False
                for j in range(i + 1, len(lines)):
                    next_s = lines[j].strip()
                    if next_s:
                        if re.match(r"^\s*\d+[.)、]\s+", lines[j]):
                            next_is_ol = True
                        break
                if not next_is_ol:
                    flush_list()
            else:
                flush_list()
            i += 1
            continue

        m_head = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m_head:
            level = len(m_head.group(1))
            h_text = m_head.group(2).strip()
            if h_text.startswith("[") and h_text.endswith("]"):
                h_text = h_text[1:-1].strip()

            if level == 3:
                if _SELF_HEAD_RE.match(stripped):
                    close_active_block()
                    flush_list()
                    active_block = "self"
                    out.append(f'<div class="ck-self-block"><div class="ck-self-title"><strong>{inline(h_text)}</strong><span class="ck-self-badge">本人</span></div>')
                    i += 1
                    continue
                if _DEP_HEAD_RE.match(stripped):
                    close_active_block()
                    flush_list()
                    active_block = "dep"
                    out.append(f'<div class="ck-dep-block"><div class="ck-dep-title"><strong>{inline(h_text)}</strong><span class="ck-dep-badge">协同依赖</span></div>')
                    i += 1
                    continue
                if _RISK_HEAD_RE.match(stripped):
                    close_active_block()
                    flush_list()
                    active_block = "risk"
                    out.append(f'<div class="ck-risk-block"><div class="ck-risk-title"><strong>{inline(h_text)}</strong><span class="ck-risk-badge">全局风险</span></div>')
                    i += 1
                    continue

            close_active_block()
            flush_list()
            cls_name = f"ck-doc-h{level}" if level in (1, 2, 3, 4) else ""
            cls_attr = f' class="{cls_name}"' if cls_name else ""
            out.append(f"<h{level}{cls_attr}>{inline(h_text)}</h{level}>")
            i += 1
            continue

        if _SELF_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "self"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "与我相关"
            out.append(f'<div class="ck-self-block"><div class="ck-self-title"><strong>{inline(g_title)}</strong><span class="ck-self-badge">本人</span></div>')
            i += 1
            continue

        if _DEP_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "dep"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "协同输入"
            out.append(f'<div class="ck-dep-block"><div class="ck-dep-title"><strong>{inline(g_title)}</strong><span class="ck-dep-badge">协同依赖</span></div>')
            i += 1
            continue

        if _RISK_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            active_block = "risk"
            m_g = re.match(r"^\s*(?:-\s*)?\*\*([^*:\n]+)\*\*[：:]?\s*$", stripped)
            g_title = m_g.group(1).strip() if m_g else "全局风险与未决"
            out.append(f'<div class="ck-risk-block"><div class="ck-risk-title"><strong>{inline(g_title)}</strong><span class="ck-risk-badge">全局风险</span></div>')
            i += 1
            continue

        if _OTHER_GROUP_RE.match(stripped):
            close_active_block()
            flush_list()
            out.append(f'<p class="ck-person-group">{inline(stripped)}</p>')
            i += 1
            continue

        if re.match(r"^\s*\|.*\|\s*$", line):
            close_active_block()
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

        m_task = _TASK_ITEM_RE.match(line)
        if m_task:
            flush_ul()
            flush_ol()
            is_chk = m_task.group(1).lower() == "x"
            item_text = m_task.group(2).strip()
            task_buf.append((is_chk, inline(item_text)))
            i += 1
            continue

        m_ol = re.match(r"^\s*(\d+)[.)、]\s+(.*)$", line)
        if m_ol:
            flush_tasks()
            flush_ul()
            ol_buf.append({"num": m_ol.group(1), "text": inline(m_ol.group(2).strip()), "subs": []})
            i += 1
            continue

        if ol_buf and re.match(r"^\s{2,}[-*]\s+(.*)$", line):
            m_sub = re.match(r"^\s{2,}[-*]\s+(.*)$", line)
            ol_buf[-1]["subs"].append(inline(m_sub.group(1).strip()))
            i += 1
            continue

        if list_buf and re.match(r"^\s{2,}[-*]\s+(.*)$", line):
            m_sub = re.match(r"^\s{2,}[-*]\s+(.*)$", line)
            list_buf[-1]["subs"].append(inline(m_sub.group(1).strip()))
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", line):
            flush_tasks()
            flush_ol()
            list_buf.append({"text": inline(re.sub(r"^\s*[-*]\s+", "", line)), "subs": []})
            i += 1
            continue

        if re.match(r"^\s*>\s?", line):
            close_active_block()
            flush_list()
            quote = re.sub(r"^\s*>\s?", "", line)
            out.append(f'<div class="ck-quote">{inline(quote)}</div>')
            i += 1
            continue

        close_active_block()
        flush_list()
        out.append(f"<p>{inline(stripped)}</p>")
        i += 1

    flush_list()
    close_active_block()
    return "".join(out)


def render_markdown_page_html(title: str, markdown: str) -> str:
    """按 LaTeX Paper 风格渲染纯 Markdown 文本为独立 HTML 文档。
    
    保留 Markdown 原始排版、序号与层级，呈现为纯净的单栏学术纸张排版（无右侧卡片区）。
    """
    text = (markdown or "").strip()
    lines = text.splitlines()
    display_title = title or "会议纪要"
    if lines and lines[0].strip().startswith("# "):
        first_head = lines[0].strip()[2:].strip()
        if first_head in ("内容总结", "主要议题", "会议概要", "会议总结"):
            display_title = title or "会议纪要"
        elif first_head == title or not title or title in ("会议纪要", "客观会议纪要", "会议分析报告", "个人视角纪要"):
            display_title = first_head or title or "会议纪要"
            text = "\n".join(lines[1:]).strip()
        else:
            display_title = title

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


def render_minutes_html(title: str, text: str) -> str:
    """渲染会议纪要 HTML：
    - 若命中记忆（包含记忆链接及来源），渲染为带右侧溯源卡片区的 LaTeX Paper 双栏审阅样式；
    - 若未命中或未开启记忆，渲染为与风险分析、待办提取一致的纯净单栏 LaTeX Paper 学术纸张样式（无右侧溯源区域）。
    """
    clean_text = str(text or "").strip()
    if "](#" in clean_text:
        return memory_review_html(clean_text, title=title)
    return render_markdown_page_html(title or "会议纪要", clean_text)


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
    "COMPARISON_TITLE",
    "MemoryItem",
    "SECTION_TITLE",
    "apply_memory_citations",
    "history_comparison_section",
    "memory_review_html",
    "parse_memory_items",
    "render_actions_html",
    "render_markdown_page_html",
    "render_minutes_html",
    "render_risks_html",
]
