"""agenda alignment -- 议题有效性判定与原文切片对齐引擎 (零旧代码依赖).

核心能力:
1. group_transcript_blocks: 兼容标准与非标准时间戳、冒号、括号发言人行，聚合为天然发言块 (DiscussionBlock);
2. 双轨对齐路由:
   - Track A (NAMED): 议程有明确主讲人且实录有实名发言，通过发言人网络与专名加权对齐;
   - Track B (CONTENT): 议程无主讲人或实录 >=80% 匿名代号，基于中文职场尊称泛化、转场路标与单调状态机对齐;
3. 实质性研讨保护与仪式性剪枝 (is_trivial_ceremonial_item):
   - 结合 _SUBSTANTIVE_KEYWORDS 与内容字数，保护致辞、交流、签约等实质性研讨;
   - 过滤纯动线、作息与空头过场仪式 (合影、开场视频播放等);
4. build_tagged_transcript_with_head_tail: 物理保护开场背景与会末定调，生成结构化切片实录;
5. process_agenda_for_minutes: 统一对外纯算法接口，无大模型调用，毫秒级完成对齐。
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .parser import (
    AgendaItemParsed,
    AgendaPlan,
    ensure_agenda_plan,
    match_presenter_name,
    normalize_lang,
)

logger = logging.getLogger("tasks.minutes.agenda.alignment")

# ── 基础数据结构 ─────────────────────────────────────────────────────────────


@dataclass
class DiscussionBlock:
    """连续单人发言块."""

    speaker: str
    timestamp: str
    content: str
    index: int = 0


@dataclass
class ValidAgendaItem:
    """经审核确认现场实际深入讨论的有效业务/技术议题."""

    seq: str
    title: str
    presenters: list[str] = field(default_factory=list)
    start_index: int = -1
    end_index: int = -1
    matched_blocks: list[DiscussionBlock] = field(default_factory=list)


@dataclass
class AgendaProcessResult:
    """议题提纯与全文打标综合处理结果."""

    has_valid_agenda: bool
    valid_agendas: list[ValidAgendaItem]
    tagged_transcript: str


# ── 转写分块与发言人解析正则 ─────────────────────────────────────────────────

_ENGLISH_NAME_PATTERN = r"[A-Z][A-Za-z.'’\-]*(?:\s+[A-Z][A-Za-z.'’\-]*){0,2}"
_SPEAKER_LABEL_PATTERN = (
    r"(?:[^\n:：\d]{1,16}"
    r"|(?:发言者|说话人|发言人|主讲人|参会人|与会人|Speaker|User|Participant)\s*[\-_#]?\s*\d{1,4}"
    rf"|{_ENGLISH_NAME_PATTERN})"
)

_SPEAKER_TS_PATTERN = re.compile(
    rf"^(?:"
    rf"(?:\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)]?\s+({_SPEAKER_LABEL_PATTERN}))"
    rf"|"
    rf"(?:({_SPEAKER_LABEL_PATTERN})\s*(?:[:：])?\s+\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)\]?)"
    rf")(?:\s*[:：]|\s*$|\s+(?=\S))",
    re.M,
)

_SPEAKER_COLON_PATTERN = re.compile(
    r"^(?:【([^】\n]{2,16})】|\[([A-Za-z][A-Za-z .'’\-]{1,31})\]|([^\n\d:：]{2,32})\s*[:：])\s*",
    re.M,
)


def group_transcript_blocks(transcript: str) -> list[DiscussionBlock]:
    """把纯转录实录聚合成连续的发言人讨论块 (彻底不依赖标题行断点)."""
    raw_text = (transcript or "").strip()
    if not raw_text:
        return []

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    # 归一化连续多个空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    matches = list(_SPEAKER_TS_PATTERN.finditer(text))

    is_colon_mode = False
    if not matches:
        matches = list(_SPEAKER_COLON_PATTERN.finditer(text))
        is_colon_mode = bool(matches)

    blocks: list[DiscussionBlock] = []
    if matches:
        for idx, m in enumerate(matches):
            if is_colon_mode:
                sp = (m.group(1) or m.group(2) or m.group(3) or "").strip()
                ts = ""
            else:
                if m.group(1):
                    ts = (m.group(1) or "").strip()
                    sp = (m.group(2) or "").strip()
                else:
                    sp = (m.group(3) or "").strip()
                    ts = (m.group(4) or "").strip()
            next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[m.end():next_start].strip()
            blocks.append(
                DiscussionBlock(
                    speaker=sp,
                    timestamp=ts,
                    content=body,
                    index=idx,
                )
            )
    else:
        # 无任何发言人标签时按自然段保底切分
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
        for i, p in enumerate(paragraphs):
            blocks.append(
                DiscussionBlock(
                    speaker="现场发言人",
                    timestamp="",
                    content=p,
                    index=i,
                )
            )

    return blocks


# ── 匿名发言人与自适应轨道判定 ───────────────────────────────────────────────

_ANON_RATIO_FOR_CONTENT_TRACK = 0.8


def _is_anonymous_speaker(speaker: str) -> bool:
    """判定发言人是否为匿名/数字代号发言人 (如 发言者 1、说话人 2、Speaker 1、现场发言人 等)."""
    s = (speaker or "").strip()
    if not s or s in {"现场发言人", "主持人", "评委", "MC", "会务"}:
        return True
    return bool(
        re.match(
            r"^(?:发言者|说话人|发言人|主讲人|参会人|与会人|Speaker|User|Participant)\s*[\-_#]?\s*\d+$",
            s,
            re.I,
        )
    )


def _detect_alignment_track(plan: AgendaPlan, blocks: list[DiscussionBlock]) -> str:
    """自适应判定对齐策略:
    - Track A (NAMED): 既定议程中包含明确的汇报人姓名，且发言人列表中包含非匿名真实人名;
    - Track B (CONTENT): 议程单无主讲人，或者实录发言人中绝大多数 (>=80%) 为匿名代号。
    """
    has_plan_presenters = any(bool(it.presenters) for it in plan.items)
    if not has_plan_presenters:
        return "CONTENT"

    total_blocks = len(blocks)
    if total_blocks == 0:
        return "NAMED"

    anon_count = sum(1 for b in blocks if _is_anonymous_speaker(b.speaker))
    if anon_count / total_blocks >= _ANON_RATIO_FOR_CONTENT_TRACK:
        return "CONTENT"

    return "NAMED"


# ── 特征词提取与泛化信号网络 (通用算法，零硬编码) ───────────────────────────

_GENERIC_TOKENS = {
    # 英文泛词
    "for", "and", "the", "with", "from", "service", "cloud", "version", "review",
    "audio", "speech", "system", "project", "patch", "commercial", "release",
    # 中文泛词
    "版本", "发布", "评审", "商用", "补丁", "需求", "优化", "例会", "实践", "技术", "洞察",
    "服务", "议题", "主题", "讨论", "分享", "进展", "同步", "委员会", "方案", "架构",
    "测试", "开发", "上线", "业务", "系统", "管理", "平台", "处理", "应用", "探索",
    "语音", "音频", "声学", "核心", "关键", "主要", "重点",
}

_CONTENT_EVENT_KEYWORDS_EN = (
    "keynote", "opening remarks", "speech", "address", "panel", "q&a",
    "discussion", "signing ceremony", "award", "group photo", "video",
    "break", "lunch", "tour", "demo",
)


def extract_distinctive_tokens(text: str) -> list[str]:
    """提取排除了通用业务泛词的专有区分性词群."""
    en_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z0-9_\-\.]{3,}", text)]
    en_distinct = [
        tok for tok in en_tokens
        if tok not in _GENERIC_TOKENS and not re.match(r"^\d+(?:\.\d+)*$", tok)
    ]
    segments = re.split(r"[与及和的在向从对关于、，,·\-_/\\|\s:：\(\)（）【】]+", text)
    cn_tokens = []
    for seg in segments:
        clean = re.sub(r"[A-Za-z0-9_\-\.\s:：\(\)（）【】]", "", seg)
        chunks = re.findall(r"[\u4e00-\u9fa5]{2,}", clean)
        for c in chunks:
            c_clean = c
            for g in sorted(_GENERIC_TOKENS, key=len, reverse=True):
                c_clean = c_clean.replace(g, "")
            if len(c_clean) >= 2 and c_clean not in _GENERIC_TOKENS:
                cn_tokens.append(c_clean)
                if len(c_clean) >= 4:
                    if c_clean[:2] not in _GENERIC_TOKENS:
                        cn_tokens.append(c_clean[:2])
                    if c_clean[-2:] not in _GENERIC_TOKENS:
                        cn_tokens.append(c_clean[-2:])
            elif len(c) >= 2 and c not in _GENERIC_TOKENS:
                cn_tokens.append(c)
    return list(dict.fromkeys(en_distinct + cn_tokens))


def _match_token_in_text(token: str, text: str) -> bool:
    """整词边界或安全子串匹配."""
    if not token or not text:
        return False
    if re.match(r"^[A-Za-z0-9_\-\.]+$", token):
        pattern = rf"\b{re.escape(token)}\b"
        return bool(re.search(pattern, text, re.IGNORECASE))
    if len(token) >= 2:
        return token.lower() in text.lower()
    return False


def _build_item_signals_for_content_track(
    it: AgendaItemParsed, *, lang: str = "zh"
) -> list[str]:
    """为无主讲人/匿名模式 (Track B) 构建高敏路标与核心语义特征词集 (纯通用规则)."""
    title = (it.title or "").strip()
    signals: list[str] = []
    if title:
        signals.append(title)

    tokens = extract_distinctive_tokens(title)
    for tok in tokens:
        if len(tok) >= 2:
            signals.append(tok)

    combined = title

    if normalize_lang(lang) == "en":
        combined_lower = combined.casefold()
        for keyword in _CONTENT_EVENT_KEYWORDS_EN:
            if keyword in combined_lower:
                signals.append(keyword)
        for role in ("CEO", "CTO", "CFO", "COO", "VP", "Director", "Manager", "Lead", "Head"):
            if re.search(rf"\b{re.escape(role)}\b", combined, re.IGNORECASE):
                signals.append(role)
        for match in re.finditer(r"\b(?:Dr|Prof)\.?\s+([A-Z][A-Za-z.'’\-]*)", combined, re.IGNORECASE):
            signals.append(match.group(0))
            signals.append(match.group(1))
        return list(dict.fromkeys(s for s in signals if s and len(s) >= 2))

    # 通用角色与尊称提取 (提取姓氏+尊称如 张总、李工、王主任等)
    m_role = re.search(r"([\u4e00-\u9fa5]{1,4})(?:总|工|老师|主任|院长|博士|专家|主席)", combined)
    if m_role:
        leader_name = m_role.group(1)
        role_type = combined[m_role.end() - 1]
        signals.append(m_role.group(0))
        signals.append(leader_name)
        if len(leader_name) >= 2:
            surname = leader_name[0]
            signals.append(f"{surname}{role_type}")

    # 环节与领域关键词通用泛化
    if any(k in combined for k in ("致辞", "讲话", "开幕")):
        signals.extend(["致辞", "讲话"])
        if m_role:
            signals.append(f"{m_role.group(0)}致辞")
            if len(leader_name) >= 2:
                signals.append(f"{leader_name[0]}{role_type}致辞")
    if any(k in combined for k in ("交流", "问答", "答疑", "互动", "讨论")):
        signals.extend(["团队交流", "互动交流", "现场问答", "自由交流", "互动答疑", "提问环节"])
    if any(k in combined for k in ("签署", "签发", "签约", "授予", "任务令")):
        signals.extend(["任务令", "签署仪式", "签发仪式", "签约仪式", "签署与授予"])
    if any(k in combined for k in ("合影", "拍照", "留念")):
        if any(k in combined for k in ("全体", "全员")):
            signals.extend(["全体合影", "全员合影", "全体参会人员", "全体与会人员", "移步进行", "移步"])
        else:
            signals.extend(["合影留念", "合影"])
    if any(k in combined for k in ("视频", "开场", "观看", "播放")):
        signals.extend(["视频观看", "开场视频", "视频播放"])

    return list(dict.fromkeys(s for s in signals if s and len(s) >= 2))


# ── 转场路标与高置信信号库 ───────────────────────────────────────────────────

_TRANSITION_ROADSIGN_PATTERN = re.compile(
    r"(?:接下来|下面|现在|进入|进行|开启|有请|开始|议程|环节|仪式|请.*?移步|移步|尾声)"
)

_HIGH_CONFIDENCE_SIGNALS = {
    "全体合影", "全员合影", "任务令签署", "任务令签发", "签发仪式", "签署与授予",
    "团队交流", "互动交流", "领导致辞",
}

_TRANSITION_ROADSIGN_PATTERN_EN = re.compile(
    r"\b(?:next|moving on|let'?s move|up next|switching to|going to|"
    r"start with|begin with|wrap up)\b",
    re.IGNORECASE,
)

_HIGH_CONFIDENCE_SIGNALS_EN = {
    "group photo", "signing ceremony", "q&a", "keynote", "opening remarks",
}


# ── 礼仪性/动线剪枝与实质性研讨保护规则 ─────────────────────────────────────

_CEREMONIAL_ITEM_PATTERN = re.compile(
    r"(?:"
    r"合影|拍照|留念|留影|"
    r"视频观看|开场视频|视频播放|播放视频|暖场视频|宣传片|短片观看|"
    r"午餐|晚餐|工作餐|就餐|用餐|茶歇|中歇|休息|自由活动|"
    r"乘车|漫步|步行|参访|参观|走进|集合|签到|领取资料|返程|签退"
    r")",
    re.I,
)

_SUBSTANTIVE_KEYWORDS = (
    "评审", "发布", "架构", "优化", "演进", "算法", "模型", "系统", "洞察",
    "研讨", "答辩", "方案", "技术", "代码", "指标", "时延", "版本", "立项", "排期",
    "致辞", "讲话", "报告", "演讲", "分享", "互动", "交流", "问答", "签署", "授予",
    "设计", "规划", "总结", "推进", "进展", "对齐", "拉通", "测试", "部署", "商用",
    "任务令", "动员", "表彰", "誓师",
)

_CEREMONIAL_ITEM_PATTERN_EN = re.compile(
    r"\b(?:"
    r"group photo|photo|video|warm[- ]up video|promo|"
    r"coffee break|break|lunch|dinner|refreshments|"
    r"tour|visit|walk|gather|sign[- ]in|registration|"
    r"collect materials|departure|check[- ]out"
    r")\b",
    re.IGNORECASE,
)

_SUBSTANTIVE_KEYWORDS_EN = (
    "review", "release", "architecture", "optimization", "evolution",
    "algorithm", "model", "system", "insight", "workshop", "defense",
    "proposal", "technical", "code", "metric", "latency", "version",
    "launch", "roadmap", "speech", "remarks", "report", "presentation",
    "share", "interaction", "exchange", "q&a", "signing", "award",
    "design", "planning", "summary", "progress", "alignment", "testing",
    "deployment", "commercial",
)

_PURE_LOGISTICS_KEYWORDS_EN = (
    "tour", "visit", "walk", "gather", "sign-in", "registration",
    "collect materials", "departure", "check-out", "break", "lunch", "dinner",
)


def is_trivial_ceremonial_item(
    item: AgendaItemParsed,
    matched_blocks: list[DiscussionBlock],
    *,
    lang: str = "zh",
) -> bool:
    """判定一个议程项是否为纯会务过场或低密度仪式性环节 (非实质性研讨项).

    保护判据:
    1. 纯物理动线或餐饮作息且无技术性词汇: 直接剔除;
    2. 零证据 (matched_blocks 为空): 纯仪式直接剔除;
    3. 低密度过场: 发言块 <= 3 且总字数 < 120 字且命中仪式词: 直接剔除;
    4. 实质性保护: 包含 _SUBSTANTIVE_KEYWORDS (如 致辞/讲话/互动/交流/签署/授予 等)
       且总字数 >= 120 字: 坚决保留!
    """
    title = (item.title or "").strip()
    combined = title
    block_count = len(matched_blocks)
    total_chars = sum(len(b.content) for b in matched_blocks)

    if normalize_lang(lang) == "en":
        has_ceremonial = bool(_CEREMONIAL_ITEM_PATTERN_EN.search(combined))
        has_substantive = any(_match_token_in_text(k, combined) for k in _SUBSTANTIVE_KEYWORDS_EN)

        if has_ceremonial:
            pure_logistics = any(_match_token_in_text(k, combined) for k in _PURE_LOGISTICS_KEYWORDS_EN)
            if pure_logistics and not any(_match_token_in_text(k, combined) for k in ("technical", "review", "report", "algorithm")):
                return True
            if block_count == 0:
                return True
            if block_count <= 3 and total_chars < 120:
                return True
            if has_substantive and total_chars >= 120:
                return False
            if total_chars < 150:
                return True

        if not item.presenters and not has_substantive and block_count <= 2 and total_chars < 60:
            return True
        return False

    # 中文判定
    has_ceremonial = bool(_CEREMONIAL_ITEM_PATTERN.search(combined))
    has_substantive = any(k in combined for k in _SUBSTANTIVE_KEYWORDS)

    if has_ceremonial:
        # A1: 纯物理动线或餐饮作息
        pure_logistics = any(k in combined for k in (
            "乘车", "漫步", "步行", "参访", "参观", "走进", "集合", "签到", "领取资料", "返程", "签退",
            "午餐", "晚餐", "工作餐", "就餐", "茶歇", "中歇", "休息", "自由活动",
        ))
        if pure_logistics and not any(k in combined for k in ("技术", "评审", "报告", "演进", "算法")):
            return True

        # A2: 零证据直接剔除 (避免出现"本次未讨论"的滑稽合影/视频)
        if block_count == 0:
            return True

        # A3: 低密度过场吆喝 (<= 3 块 且 < 120 字)
        if block_count <= 3 and total_chars < 120:
            return True

        # A4: 实质性保护 (如何刚总致辞、现场交流等，只要达到 120 字且含实质词，强制保留)
        if has_substantive and total_chars >= 120:
            return False

        if total_chars < 150:
            return True

    # 情况 B: 弱讨论且无主讲人、无实质技术词
    if not item.presenters and not has_substantive and block_count <= 2 and total_chars < 60:
        return True

    return False


# ── Track B: 基于语义信号与转场路标的单调状态机对齐引擎 ─────────────────────


def _align_by_topics_and_roadsigns(
    plan: AgendaPlan,
    blocks: list[DiscussionBlock],
    *,
    lang: str = "zh",
) -> list[ValidAgendaItem]:
    """Track B: 基于主持人路标、语义特征词与单向流动的匿名实录对齐引擎."""
    items = plan.items
    if not items or not blocks:
        return []

    lang_key = normalize_lang(lang)
    item_signals = {
        it.seq: _build_item_signals_for_content_track(it, lang=lang_key)
        for it in items
    }

    transition_pattern = (
        _TRANSITION_ROADSIGN_PATTERN_EN
        if lang_key == "en"
        else _TRANSITION_ROADSIGN_PATTERN
    )
    high_confidence = (
        _HIGH_CONFIDENCE_SIGNALS_EN
        if lang_key == "en"
        else _HIGH_CONFIDENCE_SIGNALS
    )

    def _find_transition_candidate(b: DiscussionBlock, from_idx: int) -> tuple[str, int, str] | None:
        content = b.content
        has_trans_pattern = bool(transition_pattern.search(content))
        cands: list[tuple[str, int, str]] = []

        for idx in range(from_idx, len(items)):
            seq = items[idx].seq
            signals = item_signals[seq]
            for sig in signals:
                matched = (
                    _match_token_in_text(sig, content)
                    if lang_key == "en"
                    else sig in content
                )
                if not matched:
                    continue
                normalized_sig = sig.casefold() if lang_key == "en" else sig
                if has_trans_pattern or normalized_sig in high_confidence:
                    cands.append((seq, idx, sig))

        if not cands:
            return None
        # 优先匹配专有度最高 (字长最长) 的路标，同长度优先最近未处理议题
        cands.sort(key=lambda x: (len(x[2]), -x[1]), reverse=True)
        return cands[0]

    current_seq: str | None = None
    current_idx = 0
    assigned: dict[int, str | None] = {}
    transitions: list[tuple[int, str, str, str, str]] = []

    for b in blocks:
        cand = _find_transition_candidate(b, current_idx)
        if cand:
            seq, idx, sig = cand
            if seq != current_seq:
                logger.debug(
                    "[TRACK_B_ALIGN] 发现路标切换: 块 %d [%s %s] 命中信号 '%s' -> 切换至议题 %s",
                    b.index, b.speaker, b.timestamp, sig, seq,
                )
                transitions.append((b.index, b.speaker, b.timestamp, sig, seq))
                current_seq = seq
                current_idx = idx + 1
        assigned[b.index] = current_seq

    if transitions:
        trans_summary = " -> ".join(f"议题{t[4]}('{t[3]}')" for t in transitions)
        logger.info(
            "[AGENDA_ALIGN] Track B 路标识别完成: 命中 %d 处转场信号 (%s)",
            len(transitions), trans_summary,
        )

    valid_agendas: list[ValidAgendaItem] = []

    for it in items:
        it_blocks = [b for b in blocks if assigned.get(b.index) == it.seq]
        total_len = sum(len(b.content) for b in it_blocks)

        # 过滤实质讨论不足或纯仪式过场项
        if not it_blocks or total_len < 40:
            continue
        if is_trivial_ceremonial_item(it, it_blocks, lang=lang_key):
            logger.info("[AGENDA_ALIGN] Track B 过滤仪式性过场议题: 《%s》", it.title)
            continue

        # 汇报人智能补全：若议程未列明汇报人，但标题中提取到了尊称角色 (如 何刚总致辞 -> 何刚)
        presenters = list(it.presenters or [])
        if not presenters:
            m_lead = re.search(r"([\u4e00-\u9fa5]{1,4})(?:总|工|老师|主任|院长|博士|专家|主席)", it.title or "")
            if m_lead:
                presenters = [m_lead.group(1)]

        start_idx = min(b.index for b in it_blocks)
        end_idx = max(b.index for b in it_blocks)

        valid_agendas.append(
            ValidAgendaItem(
                seq=it.seq,
                title=it.title,
                presenters=presenters,
                start_index=start_idx,
                end_index=end_idx,
                matched_blocks=it_blocks,
            )
        )

    return valid_agendas


# ── Track A: 基于主讲人与专名网络的对齐引擎 ──────────────────────────────────


def _align_by_named_speakers(
    plan: AgendaPlan,
    blocks: list[DiscussionBlock],
    *,
    lang: str = "zh",
) -> list[ValidAgendaItem]:
    """Track A: 面向具有明确主讲人的议程网络打分对齐."""
    items = plan.items
    lang_key = normalize_lang(lang)

    item_features: list[dict[str, Any]] = []
    for it in items:
        tokens = extract_distinctive_tokens(it.title)
        item_features.append({
            "item": it,
            "presenters": it.presenters or [],
            "tokens": tokens,
            "blocks": [],
        })

    for block in blocks:
        # 主持人/MC 等中立枢纽人员控场时不因偶发词汇占有议题，保留作为串场或头尾保护
        is_host = block.speaker in {"主持人", "MC", "会务", "评委", "现场发言人"}

        best_idx = -1
        best_score = 0.0

        for idx, feat in enumerate(item_features):
            score = 0.0
            presenters = feat["presenters"]

            # 1. 发言人完全或异体/拼音命中 (强主权: +5.0)
            is_presenter = False
            if block.speaker and presenters:
                for p in presenters:
                    if match_presenter_name(p, block.speaker) >= 0.8:
                        score += 5.0
                        is_presenter = True
                        break

            # 2. 正文中点名汇报人 (+2.0)
            if not is_presenter and presenters:
                for p in presenters:
                    if p and p in block.content:
                        score += 2.0
                        break

            # 3. 议题核心专名命中 (每命中一个专名 +2.0)
            token_hits = 0
            for tok in feat["tokens"]:
                if _match_token_in_text(tok, block.content):
                    score += 2.0
                    token_hits += 1

            # 阈值控制：若有明确主讲人且当前说话人不是主讲人，主持人仅在明确点名且有专名时才挂入；
            # 其他非主讲人发言块需达到较高置信度 (>= 4.0)
            if presenters and not is_presenter:
                if is_host:
                    # 主持人若未点名主讲人，坚决不占有议题
                    score = 0.0
                elif score < 4.0:
                    score = 0.0

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx != -1 and best_score >= 2.0:
            item_features[best_idx]["blocks"].append(block)

    valid_agendas: list[ValidAgendaItem] = []

    for feat in item_features:
        it: AgendaItemParsed = feat["item"]
        matched_blocks: list[DiscussionBlock] = feat["blocks"]
        total_len = sum(len(b.content) for b in matched_blocks)

        if not matched_blocks or total_len < 40:
            continue
        if is_trivial_ceremonial_item(it, matched_blocks, lang=lang_key):
            logger.info("[AGENDA_ALIGN] Track A 过滤仪式性过场议题: 《%s》", it.title)
            continue

        start_idx = min(b.index for b in matched_blocks)
        end_idx = max(b.index for b in matched_blocks)

        valid_agendas.append(
            ValidAgendaItem(
                seq=it.seq,
                title=it.title,
                presenters=list(it.presenters or []),
                start_index=start_idx,
                end_index=end_idx,
                matched_blocks=matched_blocks,
            )
        )

    return valid_agendas


# ── 对齐总入口 (自适应双轨分流) ──────────────────────────────────────────────


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
    *,
    lang: str = "zh",
) -> list[ValidAgendaItem]:
    """将既定议程与会议实录发言块进行双轨自适应对齐."""
    if not plan or not plan.items or not transcript.strip():
        return []

    blocks = group_transcript_blocks(transcript)
    if not blocks:
        return []

    track = _detect_alignment_track(plan, blocks)
    logger.info(
        "[AGENDA_ALIGN] 启动对齐引擎: track=%s (议题数=%d, 发言块=%d)",
        track, len(plan.items), len(blocks),
    )

    if track == "CONTENT":
        valid_agendas = _align_by_topics_and_roadsigns(plan, blocks, lang=lang)
    else:
        valid_agendas = _align_by_named_speakers(plan, blocks, lang=lang)

    # 按照现场实际开讲时序 (start_index) 排序
    valid_agendas.sort(key=lambda a: a.start_index)
    return valid_agendas


# ── 打标实录构建 ─────────────────────────────────────────────────────────────


def _format_block(b: DiscussionBlock) -> str:
    sp = (b.speaker or "").strip()
    ts = (b.timestamp or "").strip()
    content = (b.content or "").strip()
    if sp and ts:
        return f"{sp} {ts}：{content}"
    if sp:
        return f"{sp}：{content}"
    return content


def build_tagged_transcript_with_head_tail(
    all_blocks: list[DiscussionBlock],
    valid_agendas: list[ValidAgendaItem],
) -> str:
    """按议题切片打标，同时物理保护首个议题前的开场白与末个议题后的会末定调."""
    if not all_blocks:
        return ""
    if not valid_agendas:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    all_valid_indices: list[int] = []
    for a in valid_agendas:
        for b in a.matched_blocks:
            all_valid_indices.append(b.index)

    if not all_valid_indices:
        return "\n\n".join(_format_block(b) for b in all_blocks)

    min_start_idx = min(all_valid_indices)
    max_end_idx = max(all_valid_indices)

    parts: list[str] = []

    # 0. 现场审定的有效议题清单
    checklist_lines = [
        f"{i+1}. 议题：{a.title}（汇报人：{'、'.join(a.presenters) or '未指定'}）"
        for i, a in enumerate(valid_agendas)
    ]
    if checklist_lines:
        parts.append("【现场审定的有效议题清单】：\n" + "\n".join(checklist_lines))

    # 1. 头部保护：开场白与背景
    head_blocks = [b for b in all_blocks if b.index < min_start_idx]
    if head_blocks:
        head_text = "\n\n".join(_format_block(b) for b in head_blocks).strip()
        if head_text:
            parts.append(f"【会议开场背景与主线脉络】：\n{head_text}")

    # 2. 各有效议题切片
    for i, a in enumerate(valid_agendas, 1):
        item_text = "\n\n".join(_format_block(b) for b in a.matched_blocks).strip()
        pres_str = "、".join(a.presenters) if a.presenters else "未指定"
        parts.append(
            f"════════════════════════════════════════\n"
            f"【议题 {i}：{a.title}】（汇报人：{pres_str}）\n"
            f"{item_text}"
        )

    # 3. 尾部保护：会末定调
    tail_blocks = [b for b in all_blocks if b.index > max_end_idx]
    if tail_blocks:
        tail_text = "\n\n".join(_format_block(b) for b in tail_blocks).strip()
        if tail_text:
            parts.append(f"════════════════════════════════════════\n【会末收尾与全场定调】：\n{tail_text}")

    return "\n\n".join(parts)


# ── 顶层纯算法调用接口 ───────────────────────────────────────────────────────


def process_agenda_for_minutes(
    transcript: str,
    agenda: AgendaPlan | dict[str, Any] | str = "",
    *,
    lang: str = "zh",
) -> AgendaProcessResult:
    """提取有效讨论议题，并生成带头尾保护的打标实录 (纯 Python, 零 LLM 调用)."""
    t = (transcript or "").strip()
    if not t or (not agenda and agenda != 0):
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    plan = ensure_agenda_plan(agenda, transcript=t)
    if not plan or not plan.items:
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    valid_agendas = align_agenda_with_transcript(plan, t, lang=lang)
    if not valid_agendas:
        logger.info("[AGENDA] 实录中未对齐到任何实质讨论的有效议题，降级为普通纪要")
        return AgendaProcessResult(
            has_valid_agenda=False,
            valid_agendas=[],
            tagged_transcript=transcript or "",
        )

    all_blocks = group_transcript_blocks(t)
    tagged = build_tagged_transcript_with_head_tail(all_blocks, valid_agendas)
    return AgendaProcessResult(
        has_valid_agenda=True,
        valid_agendas=valid_agendas,
        tagged_transcript=tagged,
    )


def probe_valid_agendas(
    transcript: str,
    agenda: AgendaPlan | dict[str, Any] | str = "",
    *,
    lang: str = "zh",
) -> list[ValidAgendaItem]:
    """快速探测是否包含与会议转写实质对齐的有效讨论议题."""
    res = process_agenda_for_minutes(transcript, agenda, lang=lang)
    return res.valid_agendas if res.has_valid_agenda else []
