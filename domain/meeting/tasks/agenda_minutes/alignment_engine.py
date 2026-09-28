"""alignment_engine.py -- 发言人真名锚定与智能双向对齐引擎。

核心机制：
1. TranscriptGrouper：按「议题分段/标题识别 + 发言人 + 时间戳」把转录全文结构化分块为 DiscussionBlock；
2. 议题标题与专名双向锚定：在实录中精确锚定各议题起始点，自适应处理乱序执行与替代汇报人；
3. 零证据确定性截断 (Zero-Evidence Cutoff)：
   若议题全场未见标题、专名、汇报人发言及相关审议，确定性标记为 skipped，切断幻觉通道；
4. 临时追加捕集 (Adhoc Discovery)：
   识别会议尾声或间歇中，由核心把关领导作出的重大指示与决策。
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

from .agenda_parser import AgendaItemParsed, AgendaPlan


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
    "版本", "发布", "评审", "商用", "补丁", "需求", "优化", "例会", "实践", "技术", "洞察",
    "service", "服务", "议题", "主题", "讨论", "分享", "进展", "同步"
}

_SPOKEN_MARKERS = {
    "各位评委", "我共享", "我来共享", "晚上好", "各位好", "在不在", "大家好", "稍等一下"
}


def _extract_title_keywords(title: str) -> list[str]:
    """从议题名称中提取核心技术关键词（版本号、服务名、英文简称等）。"""
    tokens = re.findall(r"[A-Za-z0-9_\-\.]{3,}", title)
    clean = re.sub(r"[版本发布评审商用补丁\s]", "", title)
    cn_words = [w for w in re.findall(r"[\u4e00-\u9fa5]{3,}", clean) if w]
    return list(dict.fromkeys(tokens + cn_words))


def extract_distinctive_tokens(text: str) -> list[str]:
    """提取排除了通用业务泛词的专有区分性词群。"""
    en_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z0-9_\-\.]{3,}", text)]
    en_distinct = [tok for tok in en_tokens if tok not in _GENERIC_TOKENS and not re.match(r"^\d+(?:\.\d+)*$", tok)]
    clean = re.sub(r"[A-Za-z0-9_\-\.\s:：\(\)（）【】]", "", text)
    cn_tokens = []
    chunks = re.findall(r"[\u4e00-\u9fa5]{2,}", clean)
    for c in chunks:
        if c not in _GENERIC_TOKENS:
            c_clean = c
            for g in _GENERIC_TOKENS:
                c_clean = c_clean.replace(g, "")
            if len(c_clean) >= 2:
                cn_tokens.append(c_clean)
    return list(dict.fromkeys(en_distinct + cn_tokens))


def clean_title_str(s: str) -> str:
    """去除序号与标点以便字符串对齐。"""
    s = re.sub(r"^(?:议题\s*[\d一二三四五六七八九十]+[：:、\.\s]*|No\.\s*\d+[\.\s]*|\d+[\.、\s]+)", "", s)
    s = re.sub(r"[\s\-_:：\(\)（）【】]", "", s)
    return s.lower()


def title_match_score(line: str, item_title: str) -> float:
    """计算转录行与议题标题的匹配度。"""
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
    """把转录实录聚合成连续的发言人讨论块，并精确识别议题标题断点。"""
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

        # 检查是否为议程标题独立行
        best_item = None
        if plan:
            scores = [(it, title_match_score(s, it.title)) for it in plan.items]
            scores = [sc for sc in scores if sc[1] >= 0.75]
            if scores:
                scores.sort(key=lambda x: x[1], reverse=True)
                best_item = scores[0][0]

        if best_item is not None:
            # 遇到新的议题标题行：结算前一个发言块，切断跨议题污染
            if cur_speaker and cur_lines:
                blocks.append(
                    DiscussionBlock(
                        speaker=cur_speaker,
                        timestamp=cur_ts,
                        content="\n".join(cur_lines).strip(),
                        index=idx,
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
                    )
                )
                idx += 1
            cur_speaker = m.group(1).strip()
            cur_ts = m.group(2).strip()
            cur_lines = []
            if pending_header_seq:
                cur_lines.append(f"__AGENDA_HEADER__{pending_header_seq}__")
                pending_header_seq = ""
        else:
            cur_lines.append(s)

    if cur_speaker and cur_lines:
        blocks.append(
            DiscussionBlock(
                speaker=cur_speaker,
                timestamp=cur_ts,
                content="\n".join(cur_lines).strip(),
                index=idx,
            )
        )

    # 兜底：如果转录稿未识别出时间戳，按段落切分
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


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
) -> AlignmentResult:
    """双向锚定对齐引擎：自适应处理乱序执行、替代汇报人与零证据确定性截断。"""
    blocks = group_transcript_blocks(transcript, plan=plan)
    all_speakers = set(b.speaker for b in blocks)

    speaker_first_intro: dict[str, int] = {}
    speaker_any_first: dict[str, int] = {}
    for b in blocks:
        if b.speaker not in speaker_any_first:
            speaker_any_first[b.speaker] = b.index
        if b.speaker not in speaker_first_intro and len(b.content) > 30:
            speaker_first_intro[b.speaker] = b.index

    # 1. 第一轮：从发言块中检索确凿的议题标题锚点 (__AGENDA_HEADER__{seq}__)
    topic_start_map: dict[str, int] = {}
    for b in blocks:
        m = re.search(r"__AGENDA_HEADER__(\w+)__", b.content)
        if m:
            seq = m.group(1)
            if seq not in topic_start_map:
                topic_start_map[seq] = b.index

    # 2. 第二轮：对未捕获到显式标题行的议题，按「专有关键词 + 汇报人」双向锚定
    claimed_starts = set(topic_start_map.values())
    for it in plan.items:
        if it.seq in topic_start_map:
            continue

        distinct_kws = extract_distinctive_tokens(it.title)
        kw_matched_indices = []
        if distinct_kws:
            for b in blocks:
                if any(kw.lower() in b.content.lower() for kw in distinct_kws if len(kw) >= 3):
                    kw_matched_indices.append(b.index)

        active_pres = [p for p in it.presenters if any(p in sp or sp in p for sp in all_speakers)]
        pres_start = -1
        if active_pres:
            starts = [speaker_first_intro[p] for p in active_pres if p in speaker_first_intro]
            if not starts:
                starts = [speaker_any_first[p] for p in active_pres if p in speaker_any_first]
            if starts:
                pres_start = min(starts)
            else:
                for b in blocks:
                    if any(p in b.speaker or b.speaker in p for p in active_pres):
                        pres_start = b.index
                        break

        best_start = -1
        if kw_matched_indices and pres_start != -1:
            best_start = min(kw_matched_indices[0], pres_start)
        elif kw_matched_indices:
            best_start = kw_matched_indices[0]
        elif pres_start != -1:
            # 只有当汇报人的出场发言未被其它议题的显式标题霸占时，才能作为锚点
            if pres_start not in claimed_starts:
                best_start = pres_start

        if best_start != -1:
            topic_start_map[it.seq] = best_start
            claimed_starts.add(best_start)

    # 3. 按实录中实际发生的先后时间（start_idx 升序）构建切片，彻底与议题单纸面顺序解耦
    sorted_topics = sorted(
        [(start_idx, it) for it in plan.items if (start_idx := topic_start_map.get(it.seq)) is not None],
        key=lambda x: x[0],
    )

    topic_slices: dict[str, tuple[int, int]] = {}
    for i, (start_idx, it) in enumerate(sorted_topics):
        if i + 1 < len(sorted_topics):
            end_idx = sorted_topics[i + 1][0]
        else:
            end_idx = len(blocks)
        topic_slices[it.seq] = (start_idx, end_idx)

    # 4. 组装最终结果（按 plan.items 原始官方法定顺序输出）
    alignments: list[AgendaAlignment] = []
    used_block_indices: set[int] = set()

    for it in plan.items:
        if it.seq in topic_slices:
            s_idx, e_idx = topic_slices[it.seq]
            matched = blocks[s_idx:e_idx]
            used_block_indices.update(range(s_idx, e_idx))

            # 提取证据文本并清洗标记
            lines_buf = []
            for b in matched:
                clean_content = re.sub(r"__AGENDA_HEADER__\w+__\n?", "", b.content).strip()
                lines_buf.append(f"{b.speaker} {b.timestamp}\n{clean_content}")
            evidence = "\n\n".join(lines_buf)

            topic_speakers = list(dict.fromkeys(b.speaker for b in matched))

            alignments.append(
                AgendaAlignment(
                    item=it,
                    status="discussed",
                    matched_speakers=topic_speakers,
                    matched_blocks=matched,
                    evidence_text=evidence,
                    start_index=s_idx,
                    end_index=e_idx,
                )
            )
        else:
            # 零证据确定性截断
            alignments.append(
                AgendaAlignment(
                    item=it,
                    status="skipped",
                    matched_speakers=[],
                    matched_blocks=[],
                    evidence_text="（本次会议录音转写未见本议题汇报或讨论记录）",
                    start_index=-1,
                    end_index=-1,
                )
            )

    # 临时追加事项捕集：未被分配到任何既定议程项的尾部讨论块（往往是高管总结）
    adhoc_blocks: list[DiscussionBlock] = []
    for b in blocks:
        if b.index not in used_block_indices and len(b.content) > 40:
            clean_b = DiscussionBlock(
                speaker=b.speaker,
                timestamp=b.timestamp,
                content=re.sub(r"__AGENDA_HEADER__\w+__\n?", "", b.content).strip(),
                index=b.index,
            )
            adhoc_blocks.append(clean_b)

    return AlignmentResult(
        plan=plan,
        alignments=alignments,
        all_speakers=all_speakers,
        adhoc_blocks=adhoc_blocks,
    )
