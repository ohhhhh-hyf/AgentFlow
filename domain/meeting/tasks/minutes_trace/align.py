"""对齐门禁：主张级匹配。只保留有据的关键点/笔记钉，不改正文，不写场次词表。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_ARROW = re.compile(r"\s*->\s*")
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；])\s*|\n+")
# 已有溯源钉标记（stamp_minutes 防重复插入用；兼容旧版带 (url) 的钉）
_TAG_RE = re.compile(r"###\[【[^】]*】\](?:\([^)]*\))?")


def parse_keypoints(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def parse_notes(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw or "->" not in raw:
            continue
        left, right = _ARROW.split(raw, maxsplit=1)
        left, right = left.strip(), right.strip()
        if left and right:
            rows.append((left, right))
    return rows


# ── 用户材料优先级（轻量启发式，不调 LLM）─────────────────────
# 高优先级：明确日期/数字、拉丁专名/模块、负责人、强决策/风险动作、right 强关注。
_PRI_STRONG_ACT_RE = re.compile(
    r"不再支持|必须|务必|不允许|已确认|已拍板|拍板|决定|要求|负责|必须移除|强制|承诺"
)
_PRI_RISK_RE = re.compile(
    r"存在.{0,10}风险|削弱|影响.{0,6}信任|信任.{0,4}受损|隐患|担忧"
)
_PRI_RIGHT_FOCUS_RE = re.compile(r"重点|必须|不要|别|风险|影响|注意|强调|担心|关注")
_PRI_LOW_RE = re.compile(
    r"结构(?:要|需|应|更|再)?(?:清楚|清晰|完整)|内容(?:要|需)?完整|表达(?:自然|通顺)|"
    r"体验(?:要)?好|用户(?:体验)?(?:要)?好|排版|美观|写清楚|再润色"
)


def classify_priority(text: str, right: str = "") -> str:
    """用户材料优先级：high / medium / low（启发式，供分槽落钉与排序）。"""
    blob = " ".join(x for x in (text or "", right or "") if x and x.strip())
    if not blob.strip():
        return "low"
    if re.search(r"\d", blob):  # 含数字/日期 → 强事实信号
        return "high"
    if re.search(r"[A-Za-z][A-Za-z0-9_\-]{2,}", blob):
        return "high"
    if _PRI_STRONG_ACT_RE.search(blob) or _PRI_RISK_RE.search(blob):
        return "high"
    if right and _PRI_RIGHT_FOCUS_RE.search(right):
        return "high"
    han = _han_only(blob)
    if _PRI_LOW_RE.search(blob) or len(han) <= 4:
        return "low"
    return "medium"


# 分槽位挂载上限：每材料按 priority → (全文条数上限, 同一 section 条数上限)
# keypoint: high 尽量覆盖(总4/节2)、medium 只挂直接(总2/节1)、low 仅强直接(总1/节1)
_PRI_KEYPOINT_CAP = {"high": (4, 2), "medium": (2, 1), "low": (1, 1)}
# note: high(总2/节1)、medium(总1/节1)、low 默认不挂，仅原文几乎复现时允许 1
_PRI_NOTE_CAP = {"high": (2, 1), "medium": (1, 1), "low": (1, 1)}

# note 保守链式判据参数（通用语言依据，非样例标定）：
#  - 3 字以上才算一段“实义复用”：更短的公共片段太常见，不足以证明正文复述了原话；
#  - 至少 2 段独立复用：同一主张被正文重述时会在多处留下相互分离的实义片段，
#    只撞上 1 段（单个业务词/词族）不足以排除偶合；
#  - token 覆盖下限 4：正文句至少复用原话 4 个归一 token（2-gram 或数字）才视为复述过。
_NOTE_PHRASE_MIN_LEN = 3
_NOTE_CHAIN_MIN_PHRASES = 2
_NOTE_CHAIN_MIN_TOKENS = 4

# 叠字压缩只应修正本词，不影响远处内容：只取叠字压缩点前后各 3 字的小窗找修复片段。
_STUTTER_CTX_BEFORE = 3
_STUTTER_CTX_AFTER = 3


@dataclass
class TraceIndex:
    """正文/原文预索引：集中计算句子、段落归属，供对齐与候选包复用。"""

    minutes_sentences: list[str]
    segments: list[tuple[str, list[str]]]
    sentence_sections: dict[str, str]
    topic_titles: list[str]
    understanding_pool: list[str]


def _han_only(text: str) -> str:
    return "".join(ch for ch in (text or "") if "\u4e00" <= ch <= "\u9fff")


def _han_ngrams(text: str, size: int = 3) -> set[str]:
    chars = _han_only(text)
    if len(chars) < size:
        return {chars} if chars else set()
    return {chars[i : i + size] for i in range(len(chars) - size + 1)}


_GENERIC_MORPHEME = re.compile(
    r"(今年|去年|明年|前年|本|上|下|半|年|月|日|周|季|度|个|次|条|第|"
    r"[0-9一二三四五六七八九十百千万两]|"
    # 会议高频半泛词 / 抽象后缀 / 轻动词：单独出现不足以证明同一主张
    r"验收|整改|跟进|事项|安排|问题|工作|会议|讨论|汇报|情况|内容|"
    r"相关|方面|环节|要求|计划|方案|项目|任务|进度|风险|进行|开展|"
    r"完成|落实|处理|解决|组织|准备|整体|部分|建议|需要|需|"
    r"意识|思维|能力|程度|水平|方式|方法|作用|意义|目标|目的|"
    r"树立|转变|培养|强调|认为|表示|指出|加强|提升|提高|"
    r"追踪|梳理|评估|判断)"
)
_ARABIC_NUM = re.compile(r"\d+(?:\.\d+)?")
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")
_LATIN_STOP = {
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "is",
    "be",
    "and",
    "the",
    "an",
    "as",
    "at",
    "by",
    "vs",
}
_NEG_CUE = re.compile(
    r"不足|缺乏|缺少|没有|未能|无法|不能|不可|禁止|难以|失败|"
    r"下降|降低|减少|降到|降至|未(?!来)"
)
_POS_CUE = re.compile(
    r"加强|提升|提高|增加|增长|增至|增到|升到|升至|改善|已完成|完成了"
)
_DUP_HAN = re.compile(r"([\u4e00-\u9fff])\1+")


def _is_generic_span(span: str) -> bool:
    """时间/数量/会议半泛词构成的跨度不能单独证明两句在说同一件事。

    剔除泛化语素后剩余 <2 个字符（即该片段几乎全由「今年/整改/跟进/事项」
    这类高频词构成，无特征性内容）→ 判定为泛化跨度，不作对齐证据。
    含特征词（如「验收计划调整」剔除后剩「调整」）不判泛化。
    """
    leftover = _GENERIC_MORPHEME.sub("", span or "")
    return len(leftover) < 2


def _best_span(left: str, right: str, min_size: int = 4) -> tuple[int, str]:
    a, b = _han_only(left), _han_only(right)
    if len(a) < min_size or len(b) < min_size:
        return 0, ""
    max_size = min(len(a), len(b), 16)
    for size in range(max_size, min_size - 1, -1):
        for i in range(len(a) - size + 1):
            piece = a[i : i + size]
            if piece in b and not _is_generic_span(piece):
                return size, piece
    return 0, ""


def _ngram_df(sentences: list[str]) -> dict[str, int]:
    df: dict[str, int] = {}
    for sentence in sentences:
        for gram in _han_ngrams(sentence):
            df[gram] = df.get(gram, 0) + 1
    return df


def _informative(grams: set[str], df: dict[str, int] | None, n_docs: int) -> set[str]:
    if not grams or not df or n_docs <= 2:
        return grams
    cap = max(2, int(n_docs * 0.35))
    kept = {gram for gram in grams if df.get(gram, 0) <= cap}
    return kept or grams


def _claim_score(
    source: str,
    sentence: str,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
) -> tuple[float, int, int]:
    """返回 (信息重叠比, 最长连续命中, 重叠 gram 数)。"""
    src = _normalize_match_text((source or "").strip())
    sent = _normalize_match_text((sentence or "").strip())
    if not src or not sent:
        return 0.0, 0, 0
    ha, hb = _han_only(src), _han_only(sent)
    if len(ha) >= 6 and ha in hb:
        return 1.0, len(ha), 99
    if len(hb) >= 8 and hb in ha:
        return 0.9, len(hb), 99
    span, _ = _best_span(src, sent, min_size=4)
    ga = _informative(_han_ngrams(src), df, n_docs)
    gb = _informative(_han_ngrams(sent), df, n_docs)
    inter = ga & gb
    denom = min(len(ga), len(gb)) or 1
    return len(inter) / denom, span, len(inter)


# 匹配用的口语填充词（仅删无信息量的虚词；不动可能承载语义的词；不进入正文与钉展示）
_DISCARD_WORDS = re.compile(
    r"(这个|那个|的话|呢|啊|呀|嘛|嗯|唉|就是|一个|一些|"
    r"然后|其实|目前|接下来|这一块|基本上|这边|那边|"
    r"这样的话|这样的|这种|这个这个|就是说是)"
)


def _normalize_match_text(text: str) -> str:
    """仅用于匹配：去口语填充词、合并连续重复汉字。不改正文，也不改钉上展示的原文。"""
    text = _collapse_stutter(text)
    return _DISCARD_WORDS.sub("", text or "")


def _collapse_stutter(text: str) -> str:
    return _DUP_HAN.sub(r"\1", text or "")


def _extract_numbers(text: str) -> set[str]:
    return set(_ARABIC_NUM.findall(text or ""))


def _extract_latin(text: str) -> set[str]:
    out: set[str] = set()
    for raw in _LATIN_TOKEN.findall(text or ""):
        tok = raw.lower()
        if tok not in _LATIN_STOP:
            out.add(tok)
    return out


def _informative_runs(text: str, min_len: int = 2) -> list[str]:
    spaced = _GENERIC_MORPHEME.sub(" ", text or "")
    return [
        part
        for part in re.findall(r"[\u4e00-\u9fff]+", spaced)
        if len(part) >= min_len
    ]


def _approx_in(piece: str, hay: str) -> bool:
    """连续命中，或整段只差 1 个字（多字/漏字/近形）。不是词表。"""
    if not piece or not hay:
        return False
    if piece in hay:
        return True
    n = len(piece)
    if n < 3:
        return False
    for i in range(len(hay) - n + 1):
        window = hay[i : i + n]
        if sum(a != b for a, b in zip(piece, window)) <= 1:
            return True
    for i in range(n):
        reduced = piece[:i] + piece[i + 1 :]
        if len(reduced) >= 2 and reduced in hay and not _is_generic_span(reduced):
            return True
    return False


def _run_covered(run: str, text: str, runs: list[str]) -> bool:
    if not run:
        return False
    hay = text or ""
    if _approx_in(run, hay) or run in hay:
        return True
    if any(run in other or other in run or _approx_in(run, other) for other in runs if other):
        return True
    if len(run) >= 2:
        for i in range(len(run) - 1):
            gram = run[i : i + 2]
            if gram in hay:
                return True
    return False


def _approx_run_hit(left: str, right: str) -> bool:
    hb = _han_only(_normalize_match_text(right))
    for run in _informative_runs(_normalize_match_text(left), min_len=3):
        if _is_generic_span(run):
            continue
        if _approx_in(run, hb):
            return True
    return False


def _shared_runs(left: str, right: str, min_len: int = 3) -> list[str]:
    other_han = _han_only(right)
    other_runs = _informative_runs(right, min_len)
    return [
        run
        for run in _informative_runs(left, min_len)
        if _run_covered(run, other_han, other_runs)
    ]


def _unique_runs(src: str, other: str, min_len: int = 3) -> list[str]:
    other_han = _han_only(other)
    other_runs = _informative_runs(other, min_len)
    return [
        run
        for run in _informative_runs(src, min_len)
        if not _run_covered(run, other_han, other_runs)
    ]


def _polarity_conflict(left: str, right: str) -> bool:
    if not _shared_runs(left, right, min_len=3):
        return False
    ln, lp = bool(_NEG_CUE.search(left or "")), bool(_POS_CUE.search(left or ""))
    rn, rp = bool(_NEG_CUE.search(right or "")), bool(_POS_CUE.search(right or ""))
    if (ln and not lp) and (rp and not rn):
        return True
    if (rn and not rp) and (lp and not ln):
        return True
    return False


def _distinctive_extras(runs: list[str]) -> list[str]:
    out: list[str] = []
    for run in runs:
        leftover = _GENERIC_MORPHEME.sub("", run or "")
        if len(leftover) >= 4 and not _is_generic_span(run):
            out.append(run)
    return out


def _object_spec_conflict(left: str, right: str) -> bool:
    """两边各自点名了对方没有的专名/数字，才判不是同一主张。

    一边比另一边更细（多写了修饰）不算冲突；短泛词差也不算。
    """
    shared = _shared_runs(left, right, min_len=3)
    left_extra = _distinctive_extras(_unique_runs(left, right, min_len=3))
    right_extra = _distinctive_extras(_unique_runs(right, left, min_len=3))
    ln, rn = _extract_numbers(left), _extract_numbers(right)
    if ln and rn and (ln & rn):
        return False
    if any(len(item) >= 4 for item in shared) and not ((ln - rn) and (rn - ln)):
        return False
    if shared:
        if left_extra and right_extra:
            return True
        if (ln - rn) and right_extra:
            return True
        if (rn - ln) and left_extra:
            return True
        return False
    return bool(left_extra and right_extra)


def _bare_number_conflict(src: str, sent: str) -> bool:
    """来源带了数字、句子完全对不上，又没有 4 字以上同指 → 不能只靠空指标词挂上。"""
    na, nb = _extract_numbers(src), _extract_numbers(sent)
    if not na or (na & nb):
        return False
    span, _ = _best_span(src, sent, min_size=3)
    if span >= 6:
        return False
    return not _shared_runs(src, sent, min_len=4)


def _claim_incompatible(left: str, right: str, *, for_note: bool = False) -> bool:
    """类型化冲突：数字、拉丁专名、极性；关键点再查对象指定。无场次词表。"""
    a = _normalize_match_text(left)
    b = _normalize_match_text(right)
    na, nb = _extract_numbers(a), _extract_numbers(b)
    if na and nb:
        # 存在共享数字即相容；"各带独有数字"不判冲突——
        # 来源可能是数量演进/对比口径，或句子补充分项等，均不判冲突。
        # 纯对不上由 _bare_number_conflict 兜底。
        if not (na & nb):
            return True
    la, lb = _extract_latin(a), _extract_latin(b)
    if la and lb and not (la & lb):
        return True
    if _polarity_conflict(a, b):
        return True
    span, _ = _best_span(a, b, min_size=6)
    if span >= 8:
        return False
    if not for_note and _bare_number_conflict(a, b):
        return True
    if not for_note and _object_spec_conflict(a, b):
        return True
    return False


def _related(
    left: str,
    right: str,
    *,
    min_grams: int = 2,
    min_span: int = 8,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
) -> bool:
    if _claim_incompatible(left, right):
        return False
    ratio, span, grams = _claim_score(left, right, df, n_docs)
    if span >= 5:
        return True
    if _distinctive_short_hit(left, right) or _approx_run_hit(left, right):
        return True
    if ratio >= 0.16 and grams >= min_grams:
        return True
    if ratio >= 0.35 and grams >= 1:
        return True
    a, b = (left or "").strip(), (right or "").strip()
    if a and b and (a in b or b in a):
        return len(_han_only(a)) >= 4 or len(a) >= min_span
    return False


def _distinctive_short_hit(left: str, right: str) -> bool:
    """3–5 字且去掉泛化语素后仍有特征的短锚；不是词表。"""
    ha = _han_only(_normalize_match_text(left))
    hb = _han_only(_normalize_match_text(right))
    if len(ha) < 3 or len(hb) < 3:
        return False
    max_size = min(5, len(ha))
    for size in range(max_size, 2, -1):
        for i in range(len(ha) - size + 1):
            piece = ha[i : i + size]
            if piece not in hb:
                continue
            leftover = _GENERIC_MORPHEME.sub("", piece)
            if len(leftover) >= 3 and not _is_generic_span(piece):
                return True
    return False


def _related_strong(
    left: str,
    right: str,
    *,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
) -> bool:
    """高相关且主张相容：长连续重合、短特征锚或高信息重叠。"""
    if _claim_incompatible(left, right):
        return False
    ratio, span, grams = _claim_score(left, right, df, n_docs)
    if span >= 6:
        return True
    if _distinctive_short_hit(left, right) or _approx_run_hit(left, right):
        return True
    if ratio >= 0.45 and grams >= 3:
        return True
    ha = _han_only(_normalize_match_text(left))
    hb = _han_only(_normalize_match_text(right))
    if len(ha) >= 6 and ha in hb:
        return True
    if len(hb) >= 8 and hb in ha:
        return True
    return False


def _stutter_collapsed_hit(left: str, sentence: str) -> bool:
    """左句存在叠字（语音识别把单字重复成叠字）：只认叠字压缩点附近的修复片段。

    不做全句扫描——整句去叠会把远处与叠字无关的共享业务词也当同指，造成误挂。
    """
    raw = _han_only(left)
    col = _han_only(_collapse_stutter(left))
    if not col or col == raw:
        return False
    hb = _han_only(_normalize_match_text(sentence))
    if not hb:
        return False
    # 定位压缩点：raw 中相邻重复字，在 col 中只保留一次的位置
    dup_pos: list[int] = []
    p = q = 0
    while p < len(raw) and q < len(col):
        ch = raw[p]
        if col[q] != ch:
            q += 1
            continue
        if p + 1 < len(raw) and raw[p + 1] == ch:
            dup_pos.append(q)
        p += 1
        q += 1
    if not dup_pos:
        return False
    for j in dup_pos:
        window = col[max(0, j - _STUTTER_CTX_BEFORE) : j + _STUTTER_CTX_AFTER + 1]
        for size in (4, 3, 2):
            for i in range(len(window) - size + 1):
                piece = window[i : i + size]
                leftover = _GENERIC_MORPHEME.sub("", piece)
                if (
                    piece in hb
                    and len(leftover) >= 2
                    and not _is_generic_span(piece)
                ):
                    return True
    return False


def _note_related(
    left: str,
    sentence: str,
    *,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
    bridge: str = "",
) -> bool:
    """笔记：原话、一字之差、叠字、同义改写；可用原文句给摘要宿主搭桥。"""
    if _claim_incompatible(left, sentence, for_note=True):
        return False
    if _quotes_note_left(left, sentence) or _note_almost_verbatim(left, sentence):
        return True
    if _object_spec_conflict(left, sentence):
        return False
    if _stutter_collapsed_hit(left, sentence):
        return True
    norm_left = _normalize_match_text(left)
    norm_sent = _normalize_match_text(sentence)
    _, span, _ = _claim_score(norm_left, norm_sent, df, n_docs)
    if span >= 8:
        return True
    # 保守链式：note 有原文证据（外层已查）+ 正文句承载足够实义 token 与片段
    # （≥2 个 ≥3 字段）→ 口语原话与提炼句的跨改写同指。token 少或片段单一
    # （单一业务词族的偶合）不放行，避免批注挂到不同事实的句上。
    if _note_chain_hit(left, sentence):
        return True
    return False


def _supporting_transcript_sentence(left: str, transcript: str) -> str:
    """原文中能否核对到与笔记左句同一事实。对不上返回空串。"""
    best_sent = ""
    best = (-1.0, -1, -1)
    for sentence in _sentences(transcript):
        if _claim_incompatible(left, sentence, for_note=True):
            continue
        if not (
            _related(left, sentence)
            or _note_almost_verbatim(left, sentence)
            or _stutter_collapsed_hit(left, sentence)
            or _approx_run_hit(left, sentence)
        ):
            continue
        score = _claim_score(left, sentence)
        if score > best:
            best = score
            best_sent = sentence
    return best_sent


def _note_supported_by_transcript(left: str, transcript: str) -> bool:
    if not (left or "").strip() or not (transcript or "").strip():
        return False
    if _contains_loose(transcript, left):
        return True
    collapsed = _normalize_match_text(left)
    if collapsed != left and _contains_loose(_normalize_match_text(transcript), collapsed):
        return True
    if _stutter_collapsed_hit(left, transcript):
        return True
    return bool(_supporting_transcript_sentence(left, transcript))


def _is_summary_like(sentence: str) -> bool:
    text = (sentence or "").strip()
    compact = re.sub(r"^[-*]\s*", "", text)
    return (
        compact.startswith("议题小结")
        or compact.startswith("状态：")
        or "未提出异议" in compact
    )


def _note_almost_verbatim(left: str, sentence: str) -> bool:
    ha = _han_only(_normalize_match_text(left))
    hb = _han_only(_normalize_match_text(sentence))
    if not ha or not hb:
        return False
    if ha in hb:
        return True
    need = max(10, int(len(ha) * 0.7))
    span, _ = _best_span(_normalize_match_text(left), _normalize_match_text(sentence), min_size=min(need, 16))
    return span >= need


def _quotes_note_left(left: str, sentence: str) -> bool:
    ha = _han_only(_normalize_match_text(left))
    hb = _han_only(_normalize_match_text(sentence))
    return bool(ha) and ha in hb


def _near_duplicate_sentences(left: str, right: str) -> bool:
    """两句是否在复述同一事实（议题一/二各写一遍）。"""
    ha, hb = _han_only(left), _han_only(right)
    if not ha or not hb:
        return False
    shorter, longer = (ha, hb) if len(ha) <= len(hb) else (hb, ha)
    if len(shorter) >= 12 and shorter in longer:
        return True
    span, _ = _best_span(left, right, min_size=10)
    if span >= 12 and span >= int(min(len(ha), len(hb)) * 0.75):
        return True
    return False


def _dedup_similar_hits(hits: list[str], *, keep: int = 2) -> list[str]:
    kept: list[str] = []
    for sentence in hits:
        similar_count = sum(
            1 for prev in kept if _near_duplicate_sentences(sentence, prev)
        )
        if similar_count >= keep:
            continue
        kept.append(sentence)
    return kept


def _has_evidence(transcript: str, evidence: str) -> bool:
    return bool((evidence or "").strip()) and _contains_loose(transcript, evidence)


def _understanding_pool(understanding: dict | None) -> list[str]:
    """会议理解中的规范化条目（决策/风险/未决/议题标题）作证据池：
    用户关键点是概括、与原文不逐字时，用这些提炼条目做同指桥。"""
    if not isinstance(understanding, dict):
        return []
    out: list[str] = []
    for key in ("decisions", "risks", "open_questions"):
        for text in understanding.get(key) or []:
            t = " ".join(str(text or "").split()).strip()
            if t and t not in out:
                out.append(t)
    for topic in understanding.get("topics") or []:
        if isinstance(topic, dict):
            t = " ".join(str(topic.get("title") or "").split()).strip()
            if t and t not in out:
                out.append(t)
    return out[:40]


def _resolve_keypoint_evidence(
    keypoint: str, transcript: str, pool: list[str]
) -> str:
    """关键点证据：优先原文直接定位；否则经证据池条目在原文回填。

    保证返回片段能在原文模糊匹配（不伪造依据）。找不到返回空串。
    """
    ev = _evidence_for(transcript, keypoint)
    if _has_evidence(transcript, ev):
        return ev
    for item in pool:
        if _related(keypoint, item) or _related_strong(keypoint, item):
            pev = _evidence_for(transcript, item)
            if _has_evidence(transcript, pev) and not _claim_incompatible(keypoint, pev):
                return pev
    return ""


def _note_targets_pool(left: str, pool: list[str]) -> bool:
    """笔记 left 与某条决策/风险/议题同指 → 批注针对具体结论，允许挂到总结/结论句。"""
    if not (left or "").strip():
        return False
    return any(
        (_related(left, item) or _related_strong(left, item)) for item in pool
    )


def _evidence_mode(source: str, evidence: str, transcript: str) -> str:
    """证据可信等级：direct=source 直接能在原文定位；bridged=经理解池条目回填。"""
    if not (source or "").strip() or not (evidence or "").strip():
        return "bridged"
    direct = _evidence_for(transcript, source)
    if direct and (
        direct == evidence or direct in evidence or evidence in direct
    ):
        return "direct"
    return "bridged"


def _evidence_candidates(
    source: str, transcript: str, pool: list[str], limit: int = 3
) -> list[dict[str, Any]]:
    """原文证据候选：source 直接匹配的原文句在前，理解池桥接回填次之（供候选包）。"""
    if not (source or "").strip():
        return []
    src_grams = _han_ngrams(source, size=2)
    rows: list[tuple[int, str]] = []
    if transcript:
        for sent in _SENTENCE_SPLIT.split(transcript):
            line = re.sub(r"^[-*]\s*", "", sent).strip()
            if not line:
                continue
            hits = len(src_grams & _han_ngrams(line, size=2))
            if hits >= 1:
                rows.append((hits, _clip(line, 120)))
    rows.sort(key=lambda r: (-r[0], len(r[1])))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hits, line in rows[:2]:
        if line in seen:
            continue
        seen.add(line)
        out.append({"kind": "direct", "text": line, "score": round(min(hits / 4, 1.0), 2)})
    for item in pool:
        if len(out) >= limit:
            break
        if _related(source, item) or _related_strong(source, item):
            pev = _evidence_for(transcript, item)
            if pev and pev not in seen:
                seen.add(pev)
                out.append({"kind": "bridged", "text": pev, "score": 0.6})
    return out[:limit]


def _sentence_candidates(
    source: str,
    sentences: list[str],
    df: dict[str, int],
    n_docs: int,
    limit: int = 5,
) -> list[str]:
    """正文句候选：按主张相似度排序取 top（供候选包，宽松交给 LLM 裁判）。"""
    scored: list[tuple[float, int, int, str]] = []
    for sentence in sentences:
        if _claim_incompatible(source, sentence):
            continue
        ratio, span, grams = _claim_score(source, sentence, df, n_docs)
        if ratio <= 0 and span < 3 and not _related(source, sentence, df=df, n_docs=n_docs):
            continue
        scored.append((ratio, span, grams, sentence))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], len(item[3])))
    out: list[str] = []
    for _, _, _, sentence in scored:
        if sentence not in out:
            out.append(sentence)
        if len(out) >= limit:
            break
    return out


def _high_confidence_keypoint_hit(
    source: str,
    sentence: str,
    evidence: str,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
) -> bool:
    """关键点落钉只收高置信：来源、正文句、原文证据三者需同指。"""
    if not evidence or _claim_incompatible(source, sentence):
        return False
    if _claim_incompatible(source, evidence):
        return False
    if _claim_incompatible(evidence, sentence):
        return False
    ratio, span, grams = _claim_score(source, sentence, df, n_docs)
    ev_ratio, ev_span, ev_grams = _claim_score(source, evidence)
    # 链式同指：evidence 是按 source 从原文定位出的依据（source↔evidence 有据），
    # 三对冲突均已查过。故正文句只要逐字/近字承载 source（span≥6）即可置信，
    # 不再苛求 evidence↔正文句的字面 tie——正文常是口语原文的复合改写，字面会稀释。
    if span >= 6:
        return True
    if ratio >= 0.35 and grams >= 3 and ev_ratio >= 0.20 and ev_grams >= 2:
        return True
    if _related_strong(source, sentence, df=df, n_docs=n_docs) and (
        _related(source, evidence) or _related_strong(source, evidence)
    ):
        return True
    return False


def _cap_similar_keypoint_pins(
    items: list[dict[str, str]], *, keep: int = 2
) -> list[dict[str, str]]:
    """同一关键点钉在近重复句子上时最多保留 keep 条，按相关度优先。"""
    others: list[dict[str, str]] = []
    by_source: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for item in items:
        if item.get("kind") != "keypoint":
            others.append(item)
            continue
        src = item.get("source") or ""
        if src not in by_source:
            order.append(src)
            by_source[src] = []
        by_source[src].append(item)
    capped: list[dict[str, str]] = []
    for src in order:
        group = by_source[src]
        group.sort(
            key=lambda it: _claim_score(src, it.get("sentence") or ""),
            reverse=True,
        )
        sents = _dedup_similar_hits(
            [it.get("sentence") or "" for it in group], keep=keep
        )
        seen_sents = set()
        for it in group:
            sent = it.get("sentence") or ""
            if sent not in sents or sent in seen_sents:
                continue
            seen_sents.add(sent)
            capped.append(it)
    return others + capped


def _cap_sentence_pins(
    items: list[dict[str, str]], *, max_sources: int = 2
) -> list[dict[str, str]]:
    """限制单句钉子数量，保留更同指的来源，避免相邻主题堆到一句上。"""
    by_sentence: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for item in items:
        sent = item.get("sentence") or ""
        if sent not in by_sentence:
            order.append(sent)
            by_sentence[sent] = []
        by_sentence[sent].append(item)
    out: list[dict[str, str]] = []
    for sent in order:
        group = by_sentence[sent]
        group.sort(
            key=lambda it: (
                it.get("kind") == "note",
                *_claim_score(it.get("source") or "", sent),
            ),
            reverse=True,
        )
        out.extend(group[:max_sources])
    return out


def _contains_loose(haystack: str, needle: str) -> bool:
    text, bit = haystack or "", (needle or "").strip()
    if not bit:
        return False
    if bit in text:
        return True
    compact_h = re.sub(r"\s+", "", text)
    compact_n = re.sub(r"\s+", "", bit)
    return bool(compact_n) and compact_n in compact_h


def _best_keypoint(source: str, keypoints: list[str]) -> str:
    src = (source or "").strip()
    if src in keypoints:
        return src
    scored = [(len(_han_ngrams(src) & _han_ngrams(k)), k) for k in keypoints]
    scored = [item for item in scored if item[0] >= 3 or src in item[1] or item[1] in src]
    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], -len(item[1])))
    return scored[0][1]


def _best_note(source: str, notes: list[tuple[str, str]]) -> tuple[str, str] | None:
    src = (source or "").strip()
    for left, right in notes:
        packed = f"{left} **用户批注** {right}"
        if src == left or src == packed or src == f"{left} -> {right}":
            return left, right
    scored: list[tuple[int, str, str]] = []
    for left, right in notes:
        score = len(_han_ngrams(src) & _han_ngrams(left))
        if score >= 3 or _related(src, left):
            scored.append((score, left, right))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -len(item[1])))
    return scored[0][1], scored[0][2]


def gate_alignments(
    alignments: list[Any],
    minutes_md: str,
    transcript: str,
    keypoints: list[str],
    notes: list[tuple[str, str]],
    topic_titles: list[str] | None = None,
    understanding: dict | None = None,
) -> list[dict[str, str]]:
    """丢掉无据对齐。返回可落钉的规范化条目。

    topic_titles：meeting_core 议题标题列表（主题桥用）；传入后启用
    主题一致性闸门（同主题弱相关放行、跨主题必须强相关），提升召回且守住精度。
    understanding：会议理解条目作证据池，概括型关键点经池同指放行（②）。
    """
    kept: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    corpus = _sentences(minutes_md)
    df = _ngram_df(corpus)
    n_docs = len(corpus)
    segments = segment_minutes(minutes_md) if topic_titles else []
    titles = list(topic_titles or [])
    pool = _understanding_pool(understanding)
    for raw in alignments or []:
        if not isinstance(raw, dict):
            continue
        sentence = " ".join(str(raw.get("sentence") or "").split()).strip()
        kind = str(raw.get("kind") or "").strip().lower()
        source = str(raw.get("source") or "").strip()
        evidence = " ".join(str(raw.get("evidence") or "").split()).strip()
        if not sentence or not source:
            continue
        if not _contains_loose(minutes_md, sentence) and sentence not in minutes_md:
            continue
        if kind in {"keypoint", "关键点", "keypoints"}:
            key = _best_keypoint(source, keypoints)
            if not key:
                continue
            if not _related(sentence, key, df=df, n_docs=n_docs):
                continue
            if titles and not _same_topic(sentence, key, segments, titles):
                continue
            stamp = key
            kind = "keypoint"
        elif kind in {"note", "笔记", "user_note", "notes"}:
            hit = _best_note(source, notes)
            if hit is None:
                continue
            left, right = hit
            if not _note_supported_by_transcript(left, transcript):
                continue
            if _is_summary_like(sentence) and not (
                _note_targets_pool(left, pool)
                or _note_almost_verbatim(left, sentence)
                or _related_strong(left, sentence, df=df, n_docs=n_docs)
            ):
                continue
            if not (_is_summary_like(sentence) and _note_targets_pool(left, pool)) and not _note_related(
                left,
                sentence,
                df=df,
                n_docs=n_docs,
                bridge=_supporting_transcript_sentence(left, transcript),
            ):
                continue
            if titles and not _same_topic(sentence, left, segments, titles):
                continue
            stamp = f"{left} **用户批注** {right}"
            kind = "note"
        else:
            continue
        # 2C：evidence 必须能在原文中模糊匹配，否则置空（不伪造依据）
        if evidence and not _contains_loose(transcript, evidence):
            evidence = ""
        if kind == "keypoint":
            evidence = evidence or _resolve_keypoint_evidence(stamp, transcript, pool)
            if not _high_confidence_keypoint_hit(
                stamp, sentence, evidence, df=df, n_docs=n_docs
            ):
                continue
        marker = (sentence, kind, stamp)
        if marker in seen:
            continue
        seen.add(marker)
        kept.append(
            {
                "sentence": sentence,
                "kind": kind,
                "source": stamp,
                "evidence": evidence,
            }
        )
    return kept


def _sentences(markdown: str) -> list[str]:
    out: list[str] = []
    for raw in _SENTENCE_SPLIT.split(markdown or ""):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s*", "", line).strip()
        if line:
            out.append(line)
    return out


def _minutes_sentences(minutes_md: str) -> list[str]:
    """正文挂载候选句：按行取，跳过标题与「内容总结」段落区。

    内容总结是概况综述（成段文字），不作为溯源挂载目标——挂载只发生在
    议题正文与动态章节的具体句子上。行内含多个分句时整行保留（不按句号再拆），
    避免把一条完整事实拆碎。
    """
    out: list[str] = []
    in_summary = False
    for raw in (minutes_md or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            in_summary = line.lstrip("#").strip() == "内容总结"
            continue
        if in_summary:
            continue
        if line.startswith(">") or line.startswith("---"):
            continue
        line = re.sub(r"^[-*]\s*", "", line).strip()
        if line and not line.startswith("###[【"):
            out.append(line)
    return out


# ── 主题桥：段落分段 + 议题主题匹配（2A/2B）────────────────────

def _clip(text: str, limit: int = 120) -> str:
    """截断文本到 limit 字符（保留整句边界，超出补省略号）。"""
    text = " ".join((text or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"

def segment_minutes(minutes_md: str) -> list[tuple[str, list[str]]]:
    """把纪要正文按 `## ` 议题标题分段：[(标题, [句子...]), ...]。

    一级标题（`# `）与表格/分隔行不计入段落；无标题的内容（如内容总结）
    归入空标题段。返回顺序与正文一致。
    """
    segments: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for raw in (minutes_md or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            if heading or lines:
                segments.append((heading, lines))
            heading = stripped[3:].strip()
            lines = []
        elif stripped.startswith("# "):
            if heading or lines:
                segments.append((heading, lines))
            heading = ""
            lines = []
        elif stripped and not stripped.startswith("|"):
            for part in _SENTENCE_SPLIT.split(stripped):
                part = re.sub(r"^[-*+]\s*", "", part).strip()
                if part:
                    lines.append(part)
    if heading or lines:
        segments.append((heading, lines))
    return [(h, [s for s in ss if s]) for h, ss in segments if h or ss]


def _segment_of(sentence: str, segments: list[tuple[str, list[str]]]) -> str:
    """返回句子所属段落标题；找不到返回空串。"""
    sent = " ".join((sentence or "").split()).strip()
    if not sent:
        return ""
    compact = re.sub(r"\s+", "", sent)
    for heading, sentences in segments:
        for s in sentences:
            cs = re.sub(r"\s+", "", s)
            if sent == s or (sent and sent in s) or (s and s in sent) or (
                compact and compact in cs
            ):
                return heading
    return ""


def _topic_score(source: str, heading: str, topic_titles: list[str]) -> int:
    """来源与段落标题的主题相关度：直接 2-gram 重叠 + 议题标题桥接重叠。

    主题桥：仅当来源与某议题标题（meeting_core topics.title）**直接匹配**
    （≥1 个 2-gram 重叠，如「验收」「排期」）时，才允许该标题与段落标题
    的重叠加分——否则桥接会因"来源同时弱匹配多个标题"把无关段落抬高。

    用 2-gram 而非 3-gram：标题/关键点措辞差异大时 3-gram 太脆
    （「验收计划」vs「验收时间」零重叠），2-gram 的「验收」即可命中。
    """
    if not heading:
        return 0
    src_grams = _han_ngrams(source, size=2)
    best = len(src_grams & _han_ngrams(heading, size=2))
    for title in topic_titles or []:
        t = (title or "").strip()
        if not t:
            continue
        src_title = len(src_grams & _han_ngrams(t, size=2))
        if src_title < 1:
            continue  # 来源与该议题标题不直接相关，不做桥接
        bridge = src_title + len(
            _han_ngrams(t, size=2) & _han_ngrams(heading, size=2)
        )
        if bridge > best:
            best = bridge
    return best


def _best_segment(
    source: str,
    segments: list[tuple[str, list[str]]],
    topic_titles: list[str],
) -> list[str] | None:
    """找与来源同主题的段落句子列表。

    规则：来源必须**明确**指向某一主题——该段得分 ≥2，且比次高段
    至少高 2 分（区分度），避免常见词（需要/问题/安排）造成跨主题误配。
    """
    scored: list[tuple[int, list[str]]] = []
    for heading, sentences in segments:
        if not heading:
            continue
        score = _topic_score(source, heading, topic_titles)
        if score > 0:
            scored.append((score, sentences))
    if not scored:
        return None
    scored.sort(key=lambda item: -item[0])
    best_score, best_pool = scored[0]
    if best_score < 2:
        return None
    if len(scored) >= 2 and best_score - scored[1][0] < 2:
        return None  # 主题区分度不足，不冒险挂
    return best_pool


def _same_topic(
    sentence: str,
    source: str,
    segments: list[tuple[str, list[str]]],
    topic_titles: list[str],
) -> bool:
    """主题闸只拦「明确跨主题且主张也不强」的情况。

    - 无段落标题（如内容总结）或来源对不上任何议题 → 不因主题拦截
    - 标题就是来源最匹配的议题 → 通过
    - 明确属于另一个议题 → 必须主张强相关才挂
    - 主题分不清 → 交给上游的主张匹配
    """
    heading = _segment_of(sentence, segments)
    if not heading:
        return True
    scored = sorted(
        (
            (score, h)
            for h, _ in segments
            if h and (score := _topic_score(source, h, topic_titles)) > 0
        ),
        key=lambda item: -item[0],
    )
    if not scored:
        return True
    best_score, best_heading = scored[0]
    unambiguous = best_score >= 2 and (
        len(scored) == 1 or best_score - scored[1][0] >= 2
    )
    if heading == best_heading:
        return True
    if not unambiguous:
        return True
    if _claim_incompatible(source, sentence):
        return False
    ratio, span, _ = _claim_score(source, sentence)
    return span >= 6 or ratio >= 0.4 or _distinctive_short_hit(source, sentence)


def _best_sentences(
    source: str,
    candidates: list[str],
    limit: int = 2,
    df: dict[str, int] | None = None,
    n_docs: int = 0,
    *,
    require_strong: bool = False,
) -> list[str]:
    scored: list[tuple[float, int, int, str]] = []
    for sentence in candidates:
        if require_strong:
            if not _related_strong(source, sentence, df=df, n_docs=n_docs):
                continue
        elif not _related(source, sentence, df=df, n_docs=n_docs):
            continue
        ratio, span, grams = _claim_score(source, sentence, df, n_docs)
        scored.append((ratio, span, grams, sentence))
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], len(item[3])))
    out: list[str] = []
    cap = len(scored) if limit <= 0 else limit
    for _, _, _, sentence in scored:
        if sentence not in out:
            out.append(sentence)
        if len(out) >= cap:
            break
    return out


def backfill_alignments(
    alignments: list[dict[str, str]],
    minutes_md: str,
    transcript: str,
    keypoints: list[str],
    notes: list[tuple[str, str]],
    topic_titles: list[str] | None = None,
    understanding: dict | None = None,
    audit: dict | None = None,
) -> list[dict[str, str]]:
    """补挂明显相关的来源。只追加钉子，不改正文，不引入用户批注为事实。

    topic_titles：启用主题桥——先在关键点/笔记同主题的段落内找句（2A），
    找不到再回退全局；补挂的 evidence 用原文片段回填（2C），不再留空。
    understanding：会议理解条目作证据池，概括型关键点/针对结论的笔记经池同指放行。
    audit：可选 dict，收集 dropped 原因与 summary 统计（阶段 A debug，不写正式文件）。
    执行顺序：先证据成立 → 再正文候选 → 后三方一致 + 分槽位 cap（按材料优先级）。
    """
    kept = gate_alignments(
        alignments, minutes_md, transcript, keypoints, notes, topic_titles, understanding
    )
    index = TraceIndex(
        minutes_sentences=_minutes_sentences(minutes_md),
        segments=segment_minutes(minutes_md),
        sentence_sections={},
        topic_titles=list(topic_titles or []),
        understanding_pool=_understanding_pool(understanding),
    )
    for sent in index.minutes_sentences:
        index.sentence_sections[sent] = _segment_of(sent, index.segments)
    candidates = index.minutes_sentences
    df = _ngram_df(candidates)
    n_docs = len(candidates)
    segments = index.segments
    titles = index.topic_titles
    pool = index.understanding_pool
    seen = {
        (item.get("sentence", ""), item.get("kind", ""), item.get("source", ""))
        for item in kept
    }
    audit_sum = audit.setdefault("summary", {}) if isinstance(audit, dict) else {}
    audit_drops = audit.setdefault("dropped", []) if isinstance(audit, dict) else None

    def _drop(source: str, reason: str, priority: str) -> None:
        if audit_drops is not None:
            audit_drops.append({"source": source, "reason": reason, "priority": priority})

    # ── keypoint：先证据 → 再正文候选 → 三方一致 + 分槽 cap ──
    kp_total = len(keypoints)
    kp_supported = 0
    kp_pinned = 0
    for keypoint in keypoints:
        pri = classify_priority(keypoint)
        total_cap, section_cap = _PRI_KEYPOINT_CAP.get(pri, (2, 1))
        evidence = _resolve_keypoint_evidence(keypoint, transcript, pool)
        if not _has_evidence(transcript, evidence):
            _drop(keypoint, "no_transcript_evidence", pri)
            continue
        kp_supported += 1
        # ②正文候选：low 只收强相关；high/medium 强相关优先 + 主题桥放宽
        if pri == "low":
            hits = _best_sentences(
                keypoint, candidates, limit=total_cap, df=df, n_docs=n_docs,
                require_strong=True,
            )
        else:
            strong = _best_sentences(
                keypoint, candidates, limit=total_cap, df=df, n_docs=n_docs,
                require_strong=True,
            )
            search_pool = candidates
            if segments:
                same_topic = _best_segment(keypoint, segments, titles)
                if same_topic:
                    search_pool = list(dict.fromkeys([*same_topic, *candidates]))
            related = _best_sentences(
                keypoint, search_pool, limit=total_cap, df=df, n_docs=n_docs
            )
            hits = []
            for sentence in [*strong, *related]:
                if sentence not in hits:
                    hits.append(sentence)
                if len(hits) >= total_cap:
                    break
        hits = _dedup_similar_hits(hits, keep=4)
        # ③三方一致 + 同 section 分槽
        section_counts: dict[str, int] = {}
        pinned_here = 0
        for sentence in hits:
            if pinned_here >= total_cap:
                break
            if not _high_confidence_keypoint_hit(
                keypoint, sentence, evidence, df=df, n_docs=n_docs
            ):
                continue
            sec = index.sentence_sections.get(sentence, "")
            if sec and section_counts.get(sec, 0) >= section_cap:
                continue
            marker = (sentence, "keypoint", keypoint)
            if marker in seen:
                continue
            seen.add(marker)
            section_counts[sec] = section_counts.get(sec, 0) + 1
            pinned_here += 1
            kept.append(
                {
                    "sentence": sentence,
                    "kind": "keypoint",
                    "source": keypoint,
                    "evidence": evidence,
                    "confidence": _evidence_mode(keypoint, evidence, transcript),
                }
            )
        kp_pinned += pinned_here
        if pinned_here == 0:
            _drop(keypoint, "weak_minutes_match", pri)

    # ── note：只用 left 找证据；right 只影响优先级；low 仅原文几乎复现 ──
    note_total = len(notes)
    note_supported = 0
    note_pinned = 0
    for left, right in notes:
        pri = classify_priority(left, right)
        total_cap, section_cap = _PRI_NOTE_CAP.get(pri, (1, 1))
        if not _note_supported_by_transcript(left, transcript):
            _drop(f"{left} -> {right}", "note_left_no_transcript_evidence", pri)
            continue
        note_supported += 1
        if pri == "low":
            # low 笔记默认不挂，仅当正文有几乎原文复现的句子
            strong_verbatim = [
                s for s in candidates
                if _note_almost_verbatim(left, s) or _quotes_note_left(left, s)
            ]
            if not strong_verbatim:
                _drop(f"{left} -> {right}", "low_priority_skipped", pri)
                continue
            scan = strong_verbatim
        else:
            scan = candidates
        bridge = _supporting_transcript_sentence(left, transcript)
        targets_pool = _note_targets_pool(left, pool)
        scored: list[tuple[int, float, int, str]] = []
        for sentence in scan:
            if _is_summary_like(sentence) and not (
                targets_pool
                or _note_almost_verbatim(left, sentence)
                or _related_strong(
                    _normalize_match_text(left),
                    _normalize_match_text(sentence),
                    df=df,
                    n_docs=n_docs,
                )
            ):
                continue
            if not (_is_summary_like(sentence) and targets_pool) and not _note_related(
                left, sentence, df=df, n_docs=n_docs, bridge=bridge
            ):
                continue
            norm_left = _normalize_match_text(left)
            norm_sent = _normalize_match_text(sentence)
            if _quotes_note_left(left, sentence):
                rank = 2
            elif (
                _stutter_collapsed_hit(left, sentence)
                or _approx_run_hit(left, sentence)
                or _related_strong(norm_left, norm_sent, df=df, n_docs=n_docs)
            ):
                rank = 1
            else:
                rank = 0
            ratio, span, _ = _claim_score(norm_left, norm_sent, df, n_docs)
            scored.append((rank, ratio, span, sentence))
        scored.sort(key=lambda item: (-item[0], -item[1], -item[2], len(item[3])))
        raw_picked = _dedup_similar_hits([item[3] for item in scored], keep=2)
        source = f"{left} **用户批注** {right}"
        sec_counts: dict[str, int] = {}
        pinned_here = 0
        for sentence in raw_picked:
            if pinned_here >= total_cap:
                break
            sec = index.sentence_sections.get(sentence, "")
            if sec and sec_counts.get(sec, 0) >= section_cap:
                continue
            marker = (sentence, "note", source)
            if marker in seen:
                continue
            seen.add(marker)
            sec_counts[sec] = sec_counts.get(sec, 0) + 1
            pinned_here += 1
            kept.append(
                {
                    "sentence": sentence,
                    "kind": "note",
                    "source": source,
                    "evidence": _evidence_for(transcript, left) or left,
                    "confidence": "direct",
                }
            )
        note_pinned += pinned_here
        if pinned_here == 0:
            _drop(f"{left} -> {right}", "weak_minutes_match", pri)

    if isinstance(audit, dict):
        audit_sum.update(
            {
                "keypoint_total": kp_total,
                "keypoint_supported": kp_supported,
                "keypoint_pinned": kp_pinned,
                "note_total": note_total,
                "note_supported": note_supported,
                "note_pinned": note_pinned,
            }
        )
    return _cap_sentence_pins(_cap_similar_keypoint_pins(kept, keep=3), max_sources=2)


def _match_tokens(text: str) -> set[str]:
    """匹配用 token 集：汉字 2-gram ∪ 数字 token。

    数字带 # 前缀作为独立 token 与汉字 gram 同权参与交集，无任何专门阈值；
    共享数字即共享 token，凑满判中数才会命中。
    """
    tokens = set(_han_ngrams(text or "", size=2))
    for n in _extract_numbers(text or ""):
        tokens.add(f"#{n}")
    return tokens


def _shared_phrase_count(left: str, right: str, min_len: int = _NOTE_PHRASE_MIN_LEN) -> int:
    """双方归一后汉字串中互不重叠的公共连续段（≥min_len）数量。

    度量“正文句复用了原话多少处实义表达”：只撞上单一业务词族只能凑 1 段，
    同事实改写通常留下 ≥2 段独立复用。
    """
    ha = _han_only(_normalize_match_text(left or ""))
    hb = _han_only(_normalize_match_text(right or ""))
    if not ha or not hb:
        return 0
    shorter, longer = (ha, hb) if len(ha) <= len(hb) else (hb, ha)
    segs: list[tuple[int, int]] = []
    for i in range(len(shorter) - min_len + 1):
        longest = 0
        for size in range(min_len, min(len(shorter) - i, len(longer)) + 1):
            if shorter[i : i + size] in longer:
                longest = size
            else:
                break
        if longest >= min_len:
            segs.append((i, longest))
    segs.sort()
    count = 0
    last_end = -1
    for i, length in segs:
        if i >= last_end:
            count += 1
            last_end = i + length
        else:
            last_end = max(last_end, i + length)
    return count


def _note_chain_hit(left: str, sentence: str) -> bool:
    """note 保守链式同指：正文句复用原话 ≥4 个匹配 token，且 ≥2 段独立实义复用。"""
    lt = _match_tokens(_normalize_match_text(left or ""))
    ls = _match_tokens(_normalize_match_text(sentence or ""))
    if not lt or not ls:
        return False
    if len(lt & ls) < _NOTE_CHAIN_MIN_TOKENS:
        return False
    return _shared_phrase_count(left, sentence) >= _NOTE_CHAIN_MIN_PHRASES


def _evidence_snippet(line: str) -> str:
    """evidence 截断为原文子串（不加省略号，保证能在原文中复核到）。"""
    line = " ".join((line or "").split()).strip()
    return line[:120] if len(line) > 120 else line


def _evidence_for(transcript: str, source: str) -> str:
    """从原文中找与来源最相关的句子作为依据；找不到返回空串。

    2C：不再补挂空 evidence——逐句扫描取 token 重叠最多的原文句，
    并还原该句中与来源重合的连续片段（保留标点），保证可溯源。
    token 集 = 汉字 2-gram ∪ 数字 token（数字同权参与匹配，无任何专门阈值；
    口语/提炼常只共享数字也能被定位，数字与汉字一样至少凑满 2 个才判中）。
    """
    src = _normalize_match_text(" ".join((source or "").split()).strip())
    if not src or not transcript:
        return ""
    src_tokens = _match_tokens(src)
    best_line = ""
    best_hits = 0
    for sent in _SENTENCE_SPLIT.split(transcript or ""):
        line = re.sub(r"^[-*]\s*", "", sent).strip()
        if not line:
            continue
        hits = len(src_tokens & _match_tokens(_normalize_match_text(line)))
        if hits > best_hits:
            best_hits = hits
            best_line = line
    if best_hits >= 2 and best_line:
        return _evidence_snippet(best_line)
    # 弱匹配回退：最长公共连续片段（含标点还原）
    span, piece = _best_span(transcript, source, min_size=6)
    return piece if span >= 6 else ""


def format_tag(source: str) -> str:
    # 溯源钉为结构化标记，不带超链接；前端如需跳转由客户端按 source 定位。
    return f"###[【{source}】]"


def stamp_minutes(minutes_md: str, alignments: list[dict[str, str]]) -> str:
    """在命中句末追加钉。对不上的句子原样保留。

    3A：按句逐行精确匹配（先长句后短句，避免短句是长句子串时先插入
    破坏长句）；只替换整句匹配处（行内第一个出现位置），
    短句子串且周围仍是汉字/字母时不插（防 tag 插进词中）。
    """
    text = minutes_md or ""
    if not text or not alignments:
        return text
    grouped: dict[str, list[str]] = {}
    for item in alignments:
        sent = item.get("sentence") or ""
        src = item.get("source") or ""
        if not sent or not src:
            continue
        tag = format_tag(src)
        bucket = grouped.setdefault(sent, [])
        if tag not in bucket:
            bucket.append(tag)
    if not grouped:
        return text

    # 按句长降序处理：短句是长句子串时，长句先落钉，短句周围被 tag 隔开
    ordered = sorted(grouped.items(), key=lambda kv: -len(kv[0]))
    lines = text.splitlines()
    han_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

    def _is_word_char(ch: str) -> bool:
        if not ch:
            return False
        if ch in han_chars:
            return True
        return "\u4e00" <= ch <= "\u9fff"

    for sent, tags in ordered:
        suffix = "".join(tags)
        compact_sent = re.sub(r"\s+", "", sent)
        for i, line in enumerate(lines):
            if not line:
                continue
            # 只处理包含整句的行：原句（去空白后）出现，且该行未被标记过
            if _TAG_RE.search(line):
                continue
            compact_line = re.sub(r"\s+", "", line)
            if sent not in line and compact_sent not in compact_line:
                continue
            # 在原行中定位句子的精确起止（优先原句，其次去空白对齐）
            start = line.find(sent)
            if start < 0:
                # 去空白定位：逐字符对齐 compact_sent 到 compact_line
                start = compact_line.find(compact_sent)
                if start < 0:
                    continue
                end = start + len(compact_sent)
            else:
                end = start + len(sent)
            # 前后边界检查：若前/后紧邻词字符（汉字/字母/数字），说明是子串而非整句
            before = line[start - 1] if start > 0 else ""
            after = line[end] if end < len(line) else ""
            if _is_word_char(before) or _is_word_char(after):
                continue
            # 行内替换该句并追加钉
            lines[i] = line[:end] + suffix + line[end:]
    return "\n".join(lines)


__all__ = [
    "backfill_alignments",
    "format_tag",
    "gate_alignments",
    "parse_keypoints",
    "parse_notes",
    "stamp_minutes",
]
