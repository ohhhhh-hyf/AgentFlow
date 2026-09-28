"""alignment_engine.py -- 发言人真名与专名驱动的发言块独立归属与对齐引擎。

核心机制（从抓标题定区间全面重构为以汇报人+专名密度的发言块独立路由）：
1. TranscriptGrouper：把转录全文结构化分块为 DiscussionBlock（带发言人、时间戳、上下文断点）；
2. BlockScorer & Router：对每一个发言块，综合计算「汇报人发言/点名(主权) + 专有名词密度(词法) + 标题锚点(候选边界)」亲和度得分；
   一块发言可以独立归属给任何议题，彻底打破连续区间切片的束缚；
3. 会话连续性平滑：在议题讨论进行中，专家质询、评委问答等未命名短块自动归入当前活跃议题，遇冲突专名或新汇报人立即换流；
4. 程序化确定性核验 (Programmatic Grounding Verification)：
   核对证据里是否有该议题的官方汇报人发言，或专属专名密度；若两项皆无，严格判定为 skipped（缺失）；
5. 临时追加捕集 (Adhoc Discovery)：
   未能归属到任何法定议题且字数充实的全局发言块（通常是高管散会决策），汇聚为临时追加事项。
"""
from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .agenda_parser import AgendaItemParsed, AgendaPlan

logger = logging.getLogger(__name__)


@dataclass
class DiscussionBlock:
    """连续单人发言块。"""

    speaker: str
    timestamp: str
    content: str
    index: int = 0
    header_seq: str = ""


@dataclass
class AgendaAlignment:
    """议程项与实录的对齐结果。"""

    item: AgendaItemParsed
    status: str  # "discussed" 或 "skipped"
    matched_speakers: list[str] = field(default_factory=list)
    matched_blocks: list[DiscussionBlock] = field(default_factory=list)
    evidence_text: str = ""
    start_index: int = -1
    end_index: int = -1


@dataclass
class AlignmentResult:
    """全会对齐总览。"""

    plan: AgendaPlan
    alignments: list[AgendaAlignment] = field(default_factory=list)
    all_speakers: set[str] = field(default_factory=set)
    adhoc_blocks: list[DiscussionBlock] = field(default_factory=list)

    @property
    def discussed_count(self) -> int:
        return sum(1 for a in self.alignments if a.status == "discussed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for a in self.alignments if a.status == "skipped")


_SPEAKER_TS_PATTERN = re.compile(
    r"^([^\n\d:]{2,12})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
    re.M,
)

_GENERIC_TOKENS = {
    # 英文泛词
    "for", "and", "the", "with", "from", "service", "cloud", "version", "review",
    "audio", "speech", "system", "project", "patch", "commercial", "release",
    # 中文泛词
    "版本", "发布", "评审", "商用", "补丁", "需求", "优化", "例会", "实践", "技术", "洞察",
    "服务", "议题", "主题", "讨论", "分享", "进展", "同步", "委员会", "方案", "架构",
    "测试", "开发", "上线", "业务", "系统", "管理", "平台"
}

_SPOKEN_MARKERS = {
    "各位评委", "我共享", "我来共享", "晚上好", "各位好", "在不在", "大家好", "稍等一下",
    "能听到吗", "可以听到", "打开来看一眼", "下一个", "散会"
}


def extract_distinctive_tokens(text: str) -> list[str]:
    """提取排除了通用业务泛词的专有区分性词群（支持整词边界与专名提炼）。"""
    en_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z0-9_\-\.]{3,}", text)]
    en_distinct = [
        tok for tok in en_tokens
        if tok not in _GENERIC_TOKENS and not re.match(r"^\d+(?:\.\d+)*$", tok)
    ]
    clean = re.sub(r"[A-Za-z0-9_\-\.\s:：\(\)（）【】]", "", text)
    cn_tokens = []
    chunks = re.findall(r"[\u4e00-\u9fa5]{2,}", clean)
    for c in chunks:
        if c not in _GENERIC_TOKENS:
            c_clean = c
            for g in _GENERIC_TOKENS:
                c_clean = c_clean.replace(g, "")
            if len(c_clean) >= 2 and c_clean not in _GENERIC_TOKENS:
                cn_tokens.append(c_clean)
    return list(dict.fromkeys(en_distinct + cn_tokens))


def clean_title_str(s: str) -> str:
    """去除序号与标点以便字符串对齐。"""
    s = re.sub(r"^(?:议题\s*[\d一二三四五六七八九十]+[：:、\.\s]*|No\.\s*\d+[\.\s]*|\d+[\.、\s]+)", "", s)
    s = re.sub(r"[\s\-_:：\(\)（）【】]", "", s)
    return s.lower()


def title_match_score(line: str, item_title: str) -> float:
    """计算转录行与议题标题的匹配度（仅用于边界候选提示，不作为唯一裁判）。"""
    s = line.strip()
    if not s or len(s) > 120 or s[-1] in "。？！，、；~…":
        return 0.0
    if any(m in s for m in _SPOKEN_MARKERS):
        return 0.0
    if _SPEAKER_TS_PATTERN.match(s):
        return 0.0

    c_line = clean_title_str(s)
    c_title = clean_title_str(item_title)
    if not c_line or not c_title:
        return 0.0

    if c_line == c_title:
        return 1.0

    seq_ratio = difflib.SequenceMatcher(None, c_line, c_title).ratio()
    tokens_l = extract_distinctive_tokens(s)
    tokens_t = extract_distinctive_tokens(item_title)
    common_tokens = [tok for tok in tokens_t if any(tok in tl or tl in tok for tl in tokens_l)]
    if tokens_t and len(common_tokens) == len(tokens_t):
        return max(seq_ratio, 0.9)
    if common_tokens and seq_ratio >= 0.6:
        return max(seq_ratio, 0.8)
    return seq_ratio


def group_transcript_blocks(
    transcript: str,
    plan: AgendaPlan | None = None,
) -> list[DiscussionBlock]:
    """把转录实录聚合成连续的发言人讨论块，并附带议题标题边界候选标记。"""
    lines = (transcript or "").strip().splitlines()
    blocks: list[DiscussionBlock] = []

    cur_speaker = ""
    cur_ts = ""
    cur_lines: list[str] = []
    idx = 0
    pending_header_seq = ""

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 检查是否为议程标题独立行（仅作为边界候选）
        best_item = None
        if plan:
            scores = [(it, title_match_score(s, it.title)) for it in plan.items]
            scores = [sc for sc in scores if sc[1] >= 0.75]
            if scores:
                scores.sort(key=lambda x: x[1], reverse=True)
                best_item = scores[0][0]

        if best_item is not None:
            if cur_speaker and cur_lines:
                blocks.append(
                    DiscussionBlock(
                        speaker=cur_speaker,
                        timestamp=cur_ts,
                        content="\n".join(cur_lines).strip(),
                        index=idx,
                        header_seq=pending_header_seq,
                    )
                )
                idx += 1
                cur_speaker = ""
                cur_ts = ""
                cur_lines = []
            pending_header_seq = best_item.seq
            continue

        m = _SPEAKER_TS_PATTERN.match(s)
        if m:
            if cur_speaker and cur_lines:
                blocks.append(
                    DiscussionBlock(
                        speaker=cur_speaker,
                        timestamp=cur_ts,
                        content="\n".join(cur_lines).strip(),
                        index=idx,
                        header_seq=pending_header_seq,
                    )
                )
                idx += 1
                pending_header_seq = ""
            cur_speaker = m.group(1).strip()
            cur_ts = m.group(2).strip()
            cur_lines = []
        else:
            cur_lines.append(s)

    if cur_speaker and cur_lines:
        blocks.append(
            DiscussionBlock(
                speaker=cur_speaker,
                timestamp=cur_ts,
                content="\n".join(cur_lines).strip(),
                index=idx,
                header_seq=pending_header_seq,
            )
        )

    # 兜底：未识别出时间戳时按非空段落聚合
    if not blocks and lines:
        for i, line in enumerate(lines):
            if line.strip():
                blocks.append(
                    DiscussionBlock(
                        speaker="现场发言人",
                        timestamp="",
                        content=line.strip(),
                        index=i,
                    )
                )

    return blocks


def _match_token_in_text(token: str, text: str) -> bool:
    """整词边界或安全子串匹配，防止如 'ids' 误伤其他英文单词。"""
    if not token or not text:
        return False
    # 纯英文或数字：要求严格整词边界匹配
    if re.match(r"^[A-Za-z0-9_\-\.]+$", token):
        pattern = rf"\b{re.escape(token)}\b"
        return bool(re.search(pattern, text, re.IGNORECASE))
    # 中文：至少 2 字符
    if len(token) >= 2:
        return token in text
    return False


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
) -> AlignmentResult:
    """以汇报人真名与专名密度驱动的发言块独立路由引擎。

    彻底解决：
    1. 误判标题劫持汇报人（如 test1 陆敬怡归入议题04，议题01如实留空）；
    2. 标题与发言错位导致切段穿透（如 test2 郑爽回到 IDS，陈啟锴回到 HAG）；
    3. 顺序严格按给定会前议程大盘输出，未讨论项确定性置空。
    """
    blocks = group_transcript_blocks(transcript, plan=plan)
    all_speakers = set(b.speaker for b in blocks if b.speaker)

    item_tokens = {it.seq: extract_distinctive_tokens(it.title) for it in plan.items}

    # ── 阶段 1：对转写中每个发言块执行多议题亲和度独立打分 ─────────────────────────
    # 规则：
    # 1. 官方汇报人主权发言：权重最高 (+5.0 / +3.0)；
    # 2. 文本中明确点名该汇报人：(+2.0)；
    # 3. 专有名词整词命中：(+2.0 / +1.5)；
    # 4. 标题行边界提示：(+1.2，低于汇报人权重，绝不抢占其它汇报人)。
    assigned: dict[int, str | None] = {}
    for b in blocks:
        best_seq = None
        best_score = 0.0
        for it in plan.items:
            score = 0.0

            # 汇报人身份匹配（最高优先级）
            is_presenter = False
            for p in it.presenters:
                if p and (p in b.speaker or b.speaker in p):
                    is_presenter = True
                    score += 5.0 if len(b.content) >= 30 else 3.0
                    break
                elif p and p in b.content:
                    score += 2.0

            # 专有名词与区分性词群（词法亲和度）
            for tok in item_tokens[it.seq]:
                if _match_token_in_text(tok, b.content):
                    score += 2.0 if re.match(r"^[A-Za-z0-9_\-\.]+$", tok) else 1.5

            # 候选标题行边界提示（弱权重，仅作辅助）
            if getattr(b, "header_seq", "") == it.seq:
                score += 1.2

            if score > best_score:
                best_score = score
                best_seq = it.seq

        if best_score >= 2.0:
            assigned[b.index] = best_seq
        else:
            assigned[b.index] = None

    # ── 阶段 2：会话连续性平滑（Active Session Fill）─────────────────────────
    # 在某个议题的汇报进行过程中，提问与短答辩（若无其它议题专名冲突）自动归属当前议题
    active: str | None = None
    for b in blocks:
        if assigned[b.index] is not None:
            active = assigned[b.index]
        elif active is not None:
            # 检查该块是否包含其它议程的专名冲突
            has_conflict = False
            for seq, kws in item_tokens.items():
                if seq != active:
                    if any(_match_token_in_text(tok, b.content) for tok in kws):
                        has_conflict = True
                        break
            if not has_conflict:
                assigned[b.index] = active

    # ── 阶段 3：程序化确定性核验（缺少汇报人或专名则改判缺失）─────────────────────
    alignments: list[AgendaAlignment] = []
    used_block_indices: set[int] = set()

    for it in plan.items:
        it_blocks = [b for b in blocks if assigned.get(b.index) == it.seq]
        evidence = "\n".join(b.content for b in it_blocks)

        has_pres = any(any(p in b.speaker for p in it.presenters) for b in it_blocks)
        has_distinctive = any(_match_token_in_text(tok, evidence) for tok in item_tokens[it.seq])

        # 核心核验门禁：有汇报人发言，或有 2 块以上充分讨论且命中核心专名
        if has_pres or (len(it_blocks) >= 2 and has_distinctive):
            used_block_indices.update(b.index for b in it_blocks)
            topic_speakers = list(dict.fromkeys(b.speaker for b in it_blocks if b.speaker))

            # 组装证据文本
            lines_buf = [f"{b.speaker} {b.timestamp}\n{b.content.strip()}" for b in it_blocks]
            evidence_text = "\n\n".join(lines_buf)

            s_idx = it_blocks[0].index if it_blocks else -1
            e_idx = it_blocks[-1].index + 1 if it_blocks else -1

            alignments.append(
                AgendaAlignment(
                    item=it,
                    status="discussed",
                    matched_speakers=topic_speakers,
                    matched_blocks=it_blocks,
                    evidence_text=evidence_text,
                    start_index=s_idx,
                    end_index=e_idx,
                )
            )
        else:
            # 严格判空：零证据确定性截断
            alignments.append(
                AgendaAlignment(
                    item=it,
                    status="skipped",
                    matched_speakers=[],
                    matched_blocks=[],
                    evidence_text="",
                    start_index=-1,
                    end_index=-1,
                )
            )

    # ── 阶段 4：未归属的重要长发言块捕集为 Adhoc（临时追加/高管总结）────────────
    adhoc_blocks: list[DiscussionBlock] = []
    for b in blocks:
        if b.index not in used_block_indices and len(b.content) > 40:
            adhoc_blocks.append(b)

    return AlignmentResult(
        plan=plan,
        alignments=alignments,
        all_speakers=all_speakers,
        adhoc_blocks=adhoc_blocks,
    )
