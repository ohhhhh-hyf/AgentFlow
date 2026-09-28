"""alignment_engine.py -- 发言人切换与议程人员网络匹配的通用对齐引擎。

核心机制（彻底摆脱文本标题行，面向真实 ASR 口语转录）：
1. group_transcript_blocks：按发言人与时间戳聚合为天然发言块（DiscussionBlock），绝不在正文中寻找伪标题行；
2. 会话转换标记与动力学感知：利用收尾信号（"谢谢各位/好，拜/先下"）与开场信号（"我来共享/能看到桌面/结论是go"）感知转场；
3. 议程人员网络与软亲和度打分：
   - 区分汇报人主权发言（+5.0/+3.0）、纪要人/团队成员答辩（+2.5）、点名（+2.0）；
   - 过滤全会中立枢纽人员（高雄、徐锋等全程评委/高频主持人）；
   - 文本相似度与专名提供软概率加成（+2.5/+2.0），绝不作为硬切断点；
4. 主讲人交接与会话状态机：支持跨议题换序（Permutations），当新议题主讲人强力接管时触发切换；
5. 程序化确定性核验（Zero-Evidence Grounding）：无人员发言且无专名讨论的议题确定性置空（skipped）；
6. 时序重构（Chronological Reconstruction）：已讨论议题按现场实际发言先后排序，未讨论议题排在最后。
"""
from __future__ import annotations

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
    header_seq: str = ""  # 保留字段以保持向后兼容


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

    @property
    def chronological_alignments(self) -> list[AgendaAlignment]:
        """已讨论议题按现场实际发言先后时序排列，未讨论议题置于末尾。"""
        discussed = [a for a in self.alignments if a.status == "discussed"]
        discussed.sort(key=lambda a: (a.start_index if a.start_index >= 0 else 999999))
        skipped = [a for a in self.alignments if a.status == "skipped"]
        return discussed + skipped


_SPEAKER_TS_PATTERN = re.compile(
    r"^([^\n\d:]{2,16})\s+(\d{1,2}:\d{2}(?::\d{2})?)",
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

_CLOSING_MARKERS = {
    "谢谢各位", "感谢各位", "多谢大家", "谢谢评委", "好，拜", "好的拜", "拜拜",
    "我先下", "你们先下", "可以先下", "先这样了", "归纳一下", "走评审电子流",
    "那就先散会", "辛苦各位", "闭环之后再发", "就这几个，今天", "散会", "好，拜。",
    "先下了", "就先这样", "多谢大家拜", "感谢大家", "那先这样", "拜拜。"
}

_OPENING_MARKERS = {
    "我来共享", "我共享", "我抢一下桌面", "能看到桌面", "能看到屏幕", "各位评委好",
    "各位评委晚上好", "这次版本主要", "本次版本主要", "整体结论是go", "结论是go",
    "看下一个", "切到下一个", "下面由我汇报", "单框架补丁", "我来介绍", "在不在",
    "大家看本次", "大家看一下", "各位好", "开始汇报", "我先共享", "我来汇报"
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


def _match_token_in_text(token: str, text: str) -> bool:
    """整词边界或安全子串匹配，防止如 'ids' 误伤其他英文单词。"""
    if not token or not text:
        return False
    if re.match(r"^[A-Za-z0-9_\-\.]+$", token):
        pattern = rf"\b{re.escape(token)}\b"
        return bool(re.search(pattern, text, re.IGNORECASE))
    if len(token) >= 2:
        return token.lower() in text.lower()
    return False


def group_transcript_blocks(
    transcript: str,
    plan: AgendaPlan | None = None,
) -> list[DiscussionBlock]:
    """把纯转录实录聚合成连续的发言人讨论块（彻底不依赖标题行断点）。"""
    raw_text = (transcript or "").strip()
    if not raw_text:
        return []

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_SPEAKER_TS_PATTERN.finditer(text))

    blocks: list[DiscussionBlock] = []
    if matches:
        for idx, m in enumerate(matches):
            sp = m.group(1).strip()
            ts = m.group(2).strip()
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
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [l.strip() for l in text.splitlines() if l.strip()]
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


def _identify_hub_speakers(plan: AgendaPlan, blocks: list[DiscussionBlock]) -> set[str]:
    """识别全会主持人、评委等中立枢纽人员（高雄、徐锋、索勋飞等）。"""
    hubs: set[str] = set()
    if plan.meta and plan.meta.attendees:
        m = re.search(r"全程与会人\s*[:：]?\s*([^;\n]+(?:;[^;\n]+)*)", plan.meta.attendees)
        if m:
            from .agenda_parser import clean_presenter_names
            for name in clean_presenter_names(m.group(1)):
                hubs.add(name)

    speaker_counts: dict[str, int] = {}
    for b in blocks:
        if b.speaker:
            speaker_counts[b.speaker] = speaker_counts.get(b.speaker, 0) + 1
    all_presenters = set(p for it in plan.items for p in it.presenters)
    for sp, cnt in speaker_counts.items():
        if cnt >= 25 and sp not in all_presenters:
            hubs.add(sp)
    return hubs


def _score_block_for_item(
    b: DiscussionBlock,
    it: AgendaItemParsed,
    tokens: list[str],
    hub_speakers: set[str],
    is_opening: bool,
) -> float:
    score = 0.0
    sp = b.speaker.strip()
    content = b.content

    # 1. 汇报人与团队身份匹配
    if sp and sp not in hub_speakers:
        if any(p in sp or sp in p for p in it.presenters):
            if len(content) >= 50 or is_opening:
                score += 5.0
            else:
                score += 3.0
        elif hasattr(it, "recorders") and any(r in sp for r in it.recorders):
            score += 2.5
        elif hasattr(it, "members") and any(m in sp for m in it.members):
            score += 2.5

    # 2. 正文点名该议题人员
    all_team = list(it.presenters)
    if hasattr(it, "recorders"):
        all_team.extend(it.recorders)
    if hasattr(it, "members"):
        all_team.extend(it.members)
    for name in all_team:
        if name and name in content:
            score += 2.0
            break

    # 3. 专有名词与区分性词群（软亲和度加成）
    for tok in tokens:
        if _match_token_in_text(tok, content):
            if re.match(r"^[A-Za-z0-9_\-\.]+$", tok):
                score += 2.5
            else:
                score += 2.0

    return score


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
) -> AlignmentResult:
    """基于发言人切换与议程人员网络匹配的通用对齐引擎。

    彻底解决：
    1. 真实转录中无任何议题标题行的问题；
    2. 会议现场换序（Permutations）或议题未讨论（Skips）问题；
    3. 全会高管评委在各议题穿插质询的精准归属；
    4. 最终纪要时序遵循现场研讨时间轴流淌。
    """
    blocks = group_transcript_blocks(transcript, plan=plan)
    all_speakers = set(b.speaker for b in blocks if b.speaker)

    item_tokens = {it.seq: extract_distinctive_tokens(it.title) for it in plan.items}
    hub_speakers = _identify_hub_speakers(plan, blocks)

    # ── 阶段 1：多维特征感知与主讲人交接状态机 ───────────────────────────
    assigned: dict[int, str | None] = {}
    active_seq: str | None = None
    session_closing: bool = False

    for b in blocks:
        is_closing = any(m in b.content for m in _CLOSING_MARKERS)
        is_opening = any(m in b.content for m in _OPENING_MARKERS)

        scores = {
            it.seq: _score_block_for_item(b, it, item_tokens[it.seq], hub_speakers, is_opening)
            for it in plan.items
        }
        best_seq, best_score = max(scores.items(), key=lambda x: x[1])

        if is_closing:
            session_closing = True

        if best_score >= 3.0:
            if best_seq != active_seq:
                if (
                    active_seq is None
                    or session_closing
                    or best_score >= 4.5
                    or (best_score >= scores.get(active_seq, 0) + 2.0)
                ):
                    active_seq = best_seq
                    session_closing = False
            assigned[b.index] = active_seq
        else:
            if active_seq is not None:
                has_conflict = False
                for seq, kws in item_tokens.items():
                    if seq != active_seq and scores.get(seq, 0) >= 2.5:
                        has_conflict = True
                        break
                if not has_conflict:
                    assigned[b.index] = active_seq
                else:
                    assigned[b.index] = None
            else:
                assigned[b.index] = None

        if is_opening and best_score >= 2.0:
            session_closing = False

    # ── 阶段 2：程序化确定性核验（缺项与有效讨论门禁判定）──────────────────
    alignments: list[AgendaAlignment] = []
    used_block_indices: set[int] = set()

    for it in plan.items:
        it_blocks = [b for b in blocks if assigned.get(b.index) == it.seq]
        evidence = "\n".join(b.content for b in it_blocks)

        all_team = list(it.presenters)
        if hasattr(it, "recorders"):
            all_team.extend(it.recorders)
        if hasattr(it, "members"):
            all_team.extend(it.members)

        has_team = any(any(p in b.speaker for p in all_team) for b in it_blocks)
        has_distinctive = any(_match_token_in_text(tok, evidence) for tok in item_tokens[it.seq])

        if (has_team and (len(it_blocks) >= 2 or len(evidence) >= 15 or has_distinctive)) or (
            len(it_blocks) >= 3 and has_distinctive
        ):
            used_block_indices.update(b.index for b in it_blocks)
            topic_speakers = list(dict.fromkeys(b.speaker for b in it_blocks if b.speaker))

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

    # ── 阶段 3：未归属的重要长发言块捕集为 Adhoc（高管总结/全局指示）─────────
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
