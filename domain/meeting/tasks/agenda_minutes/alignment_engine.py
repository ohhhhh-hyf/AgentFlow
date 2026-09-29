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

from .agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    match_presenter_name,
    reconcile_presenter_names,
)

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


_SPEAKER_LABEL_PATTERN = r"(?:[^\n:：\d]{1,16}|(?:发言者|说话人|发言人|主讲人|参会人|与会人|Speaker|User|Participant)\s*[\-_#]?\s*\d{1,4})"

_SPEAKER_TS_PATTERN = re.compile(
    rf"^(?:"
    rf"(?:\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)]?\s+({_SPEAKER_LABEL_PATTERN}))"
    rf"|"
    rf"(?:({_SPEAKER_LABEL_PATTERN})\s*(?:[:：])?\s+\[?(\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:\.\d+)?)\]?)"
    rf")(?:\s*[:：]|\s*$|\s+(?=\S))",
    re.M,
)

# ── 语义意图模式库（涵盖转折、串场、致谢消歧、设备闲聊） ───────────────────────

# 1. 主持人/评委串场交接（Host Handover Roadsign）
_HOST_HANDOVER_VERB_PATTERN = re.compile(
    r"(?:有请|交给|由|切到|听下|换到)\s*([^\s,，。:：]{2,6})\s*(?:来|给大家)?(?:汇报|分享|讲讲)?",
    re.IGNORECASE,
)
_HOST_DIRECT_INVITE_PATTERN = re.compile(
    r"(?:下一个|下一项|下一位|接下来的议题|下一议题)(?:\s*(?:是|由|有请|让))?\s*([^\s,，。:：]{2,15})?",
    re.IGNORECASE,
)
_HOST_NEXT_PHRASE_PATTERN = re.compile(
    r"(?:接下来|下面)\s*(?:有请|由|切到|听下|让|请)\s*([^\s,，。:：]{2,15})",
    re.IGNORECASE,
)
_HOST_GENERIC_PATTERN = re.compile(r"有请下一位", re.IGNORECASE)

# 2. 真实收尾信号（Closing Signals）
_CLOSING_PATTERNS = [
    re.compile(r"(?:谢谢|感谢|多谢)(?:各位|大家|评委|领导|各位老师|大家的时间)"),
    re.compile(r"(?:好[，,、]?\s*拜|好的拜|拜拜|先下了|我先下|你们先下|可以先下|先撤|先退了|退会了)"),
    re.compile(r"(?:先这样[吧了]|那就先这样|今天就[到这|这几个]|我就汇报这么多|以上是我的汇报|汇报完毕)"),
    re.compile(r"(?:走评审电子流|闭环之后再发|那就先散会|散会)"),
    re.compile(r"(?:整体|本次)?结论是\s*(?:go|通过|同意|通过评审)", re.IGNORECASE),
]

# 答辩/抗辩/反馈排除模式（语义消歧：谢谢评委指出的问题 -> 这是答辩，绝非收尾！）
_CLOSING_EXCLUSION_PATTERN = re.compile(
    r"(?:谢谢|感谢)(?:评委|老师|各位领导)?(?:提醒|指出|建议|提问|提的意见|指正|反馈|，我再|，我解释|，后续)"
)

# 3. 开场与宣讲就绪信号（Opening Signals）
_OPENING_PATTERNS = [
    re.compile(r"(?:我来共享|我共享|我抢一下桌面|能看到桌面|能看到屏幕|各位评委好|各位评委晚上好)"),
    re.compile(r"(?:这次版本主要|本次版本主要|看下一个|切到下一个|下面由我汇报)"),
    re.compile(r"(?:单框架补丁|我来介绍|大家看本次|大家看一下|各位好|开始汇报|我先共享|我来汇报|我就开始汇报|我快速过一下|今天我主要分享)"),
    re.compile(r"(?:我先|我来)\s*(?:共享|汇报|投屏|介绍)"),
]

# 4. 设备调试与过场闲聊（Equipment & Chitchat Noise）
_EQUIPMENT_CHITCHAT_PATTERNS = [
    re.compile(r"(?:喂喂|能听到吗|听得到吗|听得见吗|声音清晰|声音小|声音大|声音有点|麦克风|掉线|断网|卡了)"),
    re.compile(r"(?:能看到桌面吗|能看到屏幕吗|屏幕共享|投屏|抢一下桌面|稍等一下我共享|连一下线)"),
    re.compile(r"(?:去趟洗手间|倒杯水|喝口水|休息两分钟|稍等两分钟|点个外卖|打个电话)"),
]

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
    "各位评委晚上好", "这次版本主要", "本次版本主要",
    "看下一个", "切到下一个", "下面由我汇报", "单框架补丁", "我来介绍", "在不在",
    "大家看本次", "大家看一下", "各位好", "开始汇报", "我先共享", "我来汇报"
}


def _is_session_closing(content: str) -> bool:
    """判定是否为议题实质收尾信号，带上下文语义消歧（排除答辩抗辩致谢）。"""
    if not content:
        return False
    # 优先消歧：如果紧跟"指出/建议/我再解释"，属于答辩抗辩，绝非收尾
    if _CLOSING_EXCLUSION_PATTERN.search(content):
        return False
    if any(pat.search(content) for pat in _CLOSING_PATTERNS):
        return True
    return any(m in content for m in _CLOSING_MARKERS)


def _is_opening_signal(content: str) -> bool:
    """判定是否为新议题开场/共享桌面/就绪宣讲信号。"""
    if not content:
        return False
    if any(pat.search(content) for pat in _OPENING_PATTERNS):
        return True
    return any(m in content for m in _OPENING_MARKERS)


def _is_equipment_or_chitchat(content: str) -> bool:
    """判定是否为纯设备试音或过场闲聊（且无实质长篇内容）。"""
    if not content or len(content) > 120:
        return False
    return any(pat.search(content) for pat in _EQUIPMENT_CHITCHAT_PATTERNS)




def _detect_host_roadsign(
    speaker: str,
    content: str,
    plan: AgendaPlan,
    hub_speakers: set[str],
    dual_speakers: set[str] | None = None,
) -> tuple[str | None, bool]:
    """检测主持人/枢纽人员的串场交接信号（交通警察路标）。

    Returns:
        (target_seq, is_generic_handover)
        - target_seq: 若明确呼叫了某议题的主讲人或议题专名，返回对应 seq；
        - is_generic_handover: 若为泛指串场（如"有请下一位"、"接下来看下一项"），返回 True。
    """
    if not content:
        return None, False

    is_native_role = any(r in speaker for r in ["主持人", "会议主持", "执行主席", "大会主席", "评委", "MC", "会务"])
    is_hub = (
        speaker in hub_speakers
        or (dual_speakers and speaker in dual_speakers)
        or is_native_role
        or not speaker
        or speaker == "现场发言人"
    )
    if not is_hub:
        return None, False

    # 提取交接触发动词之后的子串，排除前半句致谢客套（如"辛苦刘工，下面有请林工"）
    target_snippet = ""
    for pat in [_HOST_NEXT_PHRASE_PATTERN, _HOST_HANDOVER_VERB_PATTERN, _HOST_DIRECT_INVITE_PATTERN]:
        m = pat.search(content)
        if m:
            target_snippet = content[m.start():]
            break

    has_handover_intent = bool(target_snippet or _HOST_GENERIC_PATTERN.search(content))
    if not has_handover_intent:
        return None, False

    search_scope = target_snippet if target_snippet else content

    # 1. 尝试匹配明确的目标议程人选或关键词
    for it in plan.items:
        all_team = list(it.presenters)
        if hasattr(it, "recorders"):
            all_team.extend(it.recorders)
        if hasattr(it, "members"):
            all_team.extend(it.members)

        for p in all_team:
            if not p:
                continue
            if p in search_scope or match_presenter_name(p, search_scope) >= 0.8:
                return it.seq, False
            if len(p) >= 2:
                surname = p[0]
                if re.search(rf"{re.escape(surname)}(?:工|老师|总|经理|博士|专家)", search_scope):
                    return it.seq, False

        tokens = extract_distinctive_tokens(it.title)
        for tok in tokens:
            if _match_token_in_text(tok, search_scope):
                return it.seq, False

    # 2. 如果包含串场意图但未提取出具体人选（如"有请下一位"、"下面切到下一项"）
    return None, True


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
    # 归一化连续多个空行（防止多空行打断切块）
    text = re.sub(r"\n{3,}", "\n\n", text)
    matches = list(_SPEAKER_TS_PATTERN.finditer(text))

    # 兼容非标准时间戳格式（如纯发言人冒号：张三： 或 【张三】）
    is_colon_mode = False
    if not matches:
        _SPEAKER_COLON_PATTERN = re.compile(
            r"^(?:【([^】\n]{2,16})】|([^\n\d:：]{2,16})\s*[:：])\s*",
            re.M,
        )
        matches = list(_SPEAKER_COLON_PATTERN.finditer(text))
        is_colon_mode = bool(matches)

    blocks: list[DiscussionBlock] = []
    if matches:
        for idx, m in enumerate(matches):
            if is_colon_mode:
                sp = (m.group(1) or m.group(2) or "").strip()
                ts = ""
            else:
                if m.group(1):
                    ts = m.group(1).strip()
                    sp = m.group(2).strip()
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


def _identify_hub_speakers(plan: AgendaPlan, blocks: list[DiscussionBlock]) -> tuple[set[str], set[str]]:
    """识别全会主持人、评委等中立枢纽人员（高雄、徐锋、索勋飞等），并检出双重身份人员。"""
    raw_hubs: set[str] = set()
    if plan.meta and plan.meta.attendees:
        from .agenda_parser import clean_presenter_names
        for role_prefix in [
            "全程与会人", "主持人", "会议主持", "评委", "评审组长", "主席", "评委组",
            "组织主席", "大会主席", "执行主席", "召集人", "Session Chair"
        ]:
            # 强化边界：匹配到换行、分段与会人/列席人标签、连字符、破折号时立即终止，防止单行穿透抓取汇报人
            m = re.search(rf"{role_prefix}\s*[:：]?\s*([^;\n\r—\-]+(?:[;；][^;\n\r—\-]+)*)", plan.meta.attendees)
            if m:
                for name in clean_presenter_names(m.group(1)):
                    raw_hubs.add(name)

    # 文本原生角色嗅探：转写文本中发言人若直接命名为“主持人/主席/评委”等，自动纳入枢纽池
    for b in blocks:
        if b.speaker and any(r in b.speaker for r in ["主持人", "会议主持", "执行主席", "大会主席", "评委", "MC", "会务"]):
            raw_hubs.add(b.speaker)

    speaker_counts: dict[str, int] = {}
    for b in blocks:
        if b.speaker:
            speaker_counts[b.speaker] = speaker_counts.get(b.speaker, 0) + 1

    all_team: set[str] = set()
    for it in plan.items:
        all_team.update(it.presenters)
        if hasattr(it, "recorders"):
            all_team.update(it.recorders)
        if hasattr(it, "members"):
            all_team.update(it.members)

    for sp, cnt in speaker_counts.items():
        if cnt >= 25 and not any(match_presenter_name(p, sp) >= 0.8 for p in all_team if p):
            raw_hubs.add(sp)

    if "现场发言人" in raw_hubs:
        raw_hubs.remove("现场发言人")

    # 汇报人身份互斥保护（核心免疫，支持模糊容错）：
    # 检出双重身份人员（如张晓雷既是组织主席，又是议题04主讲人）
    team_in_hubs = {h for h in raw_hubs if any(match_presenter_name(p, h) >= 0.8 for p in all_team if p)}
    dual_speakers = team_in_hubs
    # 凡是既定议题的汇报人/团队成员，绝不作为纯中立主持人（防止加分被彻底抹平）
    hub_speakers = raw_hubs.difference(team_in_hubs)

    return hub_speakers, dual_speakers


def _score_block_for_item(
    b: DiscussionBlock,
    it: AgendaItemParsed,
    tokens: list[str],
    hub_speakers: set[str],
    is_opening: bool,
    roadsign_seq: str | None = None,
    dual_speakers: set[str] | None = None,
) -> float:
    score = 0.0
    sp = b.speaker.strip()
    content = b.content

    # 0. 主持人路标强力引导分（Roadsign Boost）
    if roadsign_seq and roadsign_seq == it.seq:
        score += 4.5

    # 1. 汇报人与团队身份匹配
    is_presenter = False
    presenter_score = 0.0
    for p in it.presenters:
        if not p:
            continue
        sim = match_presenter_name(p, sp)
        if sim >= 1.0:
            is_presenter = True
            presenter_score = max(presenter_score, 5.0)
        elif sim >= 0.8:
            is_presenter = True
            presenter_score = max(presenter_score, 4.5)

    is_dual = bool(dual_speakers and any(match_presenter_name(d, sp) >= 0.8 for d in dual_speakers))

    if sp and (sp not in hub_speakers or is_dual):
        if is_presenter:
            if is_dual:
                # 双重身份（如张晓雷既是主席又是议题主讲人）：
                # 若发言过短且未命中该议题专有词，说明正在履行主持职责，不加主讲人分
                is_short_intro = len(content) < 100 and not any(_match_token_in_text(tok, content) for tok in tokens)
                if not is_short_intro:
                    score += presenter_score
            else:
                if len(content) >= 50 or is_opening:
                    score += presenter_score
                else:
                    score += max(3.0, presenter_score - 1.0)
        elif hasattr(it, "recorders") and any(r in sp for r in it.recorders if r):
            score += 2.5
        elif hasattr(it, "members") and any(m in sp for m in it.members if m):
            score += 2.5

    # 2. 正文点名该议题人员（支持全名、模糊形似名及 姓氏+工/老师/总）
    all_team = list(it.presenters)
    if hasattr(it, "recorders"):
        all_team.extend(it.recorders)
    if hasattr(it, "members"):
        all_team.extend(it.members)
    for name in all_team:
        if not name:
            continue
        if (name in content or match_presenter_name(name, content) >= 0.8) and name != sp:
            score += 2.0
            break
        if len(name) >= 2 and re.search(rf"{re.escape(name[0])}(?:工|老师|总|经理|博士|专家)", content):
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


def _is_anonymous_speaker(speaker: str) -> bool:
    """判定发言人是否为匿名/数字代号发言人（如 发言者 1、说话人 2、Speaker 1、现场发言人 等）。"""
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
    """自适应判定对齐策略：
    - Track A (NAMED): 既定议程中包含明确的汇报人姓名，且发言人列表中包含非匿名真实人名；
    - Track B (CONTENT): 议程单无主讲人，或者实录发言人中绝大多数（>=80%）为匿名代号。
    """
    has_plan_presenters = any(bool(it.presenters) for it in plan.items)
    if not has_plan_presenters:
        return "CONTENT"

    total_blocks = len(blocks)
    if total_blocks == 0:
        return "NAMED"

    anon_count = sum(1 for b in blocks if _is_anonymous_speaker(b.speaker))
    if anon_count / total_blocks >= 0.8:
        return "CONTENT"

    return "NAMED"


def _build_item_signals_for_content_track(it: AgendaItemParsed) -> list[str]:
    """为无主讲人模式（Track B）构建每个议题的高敏路标与核心语义特征词集。"""
    title = it.title or ""
    desc = getattr(it, "description", "") or ""
    signals: list[str] = []
    if title:
        signals.append(title.strip())
    if desc:
        signals.append(desc.strip())

    tokens = extract_distinctive_tokens(title) + (extract_distinctive_tokens(desc) if desc else [])
    for tok in tokens:
        if len(tok) >= 2:
            signals.append(tok)

    combined = f"{title} {desc}"

    # 角色与尊称提取（如 何刚总 -> 何刚总, 何刚, 何总）
    m_role = re.search(r"([\u4e00-\u9fa5]{1,4})(?:总|工|老师|主任|院长|博士|专家|主席)", combined)
    if m_role:
        leader_name = m_role.group(1)
        role_type = combined[m_role.end() - 1]
        signals.append(m_role.group(0))
        signals.append(leader_name)
        if len(leader_name) >= 2:
            surname = leader_name[0]
            signals.append(f"{surname}{role_type}")

    # 环节与领域关键词泛化
    if any(k in combined for k in ("致辞", "讲话", "开幕")):
        signals.extend(["致辞", "讲话"])
        if m_role:
            signals.append(f"{m_role.group(0)}致辞")
            if len(leader_name) >= 2:
                signals.append(f"{leader_name[0]}总致辞")
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


_TRANSITION_ROADSIGN_PATTERN = re.compile(
    r"(?:接下来|下面|现在|进入|进行|开启|有请|开始|议程|环节|仪式|请.*?移步|移步|尾声)"
)

_HIGH_CONFIDENCE_SIGNALS = {
    "全体合影", "全员合影", "任务令签署", "任务令签发", "签发仪式", "签署与授予",
    "团队交流", "互动交流", "领导致辞", "何刚总致辞"
}


def _align_by_topics_and_roadsigns(
    plan: AgendaPlan,
    blocks: list[DiscussionBlock],
    all_speakers: set[str],
) -> AlignmentResult:
    """Track B: 基于主持人路标、语义特征词密度与单向流动的匿名实录对齐引擎。"""
    items = plan.items
    if not items or not blocks:
        alignments = [
            AgendaAlignment(
                item=it,
                status="skipped",
                matched_speakers=[],
                matched_blocks=[],
                evidence_text="",
                start_index=-1,
                end_index=-1,
            )
            for it in items
        ]
        return AlignmentResult(plan=plan, alignments=alignments, all_speakers=all_speakers, adhoc_blocks=[])

    item_signals = {it.seq: _build_item_signals_for_content_track(it) for it in items}

    def _find_transition_candidate(b: DiscussionBlock, from_idx: int) -> tuple[str, int, str] | None:
        content = b.content
        has_trans_pattern = bool(_TRANSITION_ROADSIGN_PATTERN.search(content))
        # 优先从高序号向下扫描到当前序号，匹配最具体的新议题（单向流）
        for idx in range(len(items) - 1, from_idx - 1, -1):
            seq = items[idx].seq
            signals = item_signals[seq]
            for sig in signals:
                if sig in content:
                    if has_trans_pattern or sig in _HIGH_CONFIDENCE_SIGNALS:
                        return (seq, idx, sig)
        return None

    current_seq: str | None = None
    current_idx = 0
    assigned: dict[int, str | None] = {}

    for b in blocks:
        cand = _find_transition_candidate(b, current_idx)
        if cand:
            seq, idx, sig = cand
            if seq != current_seq:
                logger.info(
                    "[TRACK_B_ALIGNMENT] 发现路标切换: 块 %d [%s %s] 命中信号 '%s' -> 切换至议题 %s",
                    b.index,
                    b.speaker,
                    b.timestamp,
                    sig,
                    seq,
                )
                current_seq = seq
                current_idx = idx + 1
        assigned[b.index] = current_seq

    alignments: list[AgendaAlignment] = []
    used_indices: set[int] = set()

    for it in items:
        it_blocks = [b for b in blocks if assigned.get(b.index) == it.seq]
        if it_blocks and len(it_blocks) >= 1:
            used_indices.update(b.index for b in it_blocks)
            matched_sp = list(dict.fromkeys(b.speaker for b in it_blocks if b.speaker))
            lines_buf = [f"{b.speaker} {b.timestamp}\n{b.content.strip()}" for b in it_blocks]
            evidence_text = "\n\n".join(lines_buf)
            s_idx = it_blocks[0].index
            e_idx = it_blocks[-1].index + 1

            alignments.append(
                AgendaAlignment(
                    item=it,
                    status="discussed",
                    matched_speakers=matched_sp,
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

    adhoc_blocks = [b for b in blocks if b.index not in used_indices and len(b.content) > 40]

    return AlignmentResult(
        plan=plan,
        alignments=alignments,
        all_speakers=all_speakers,
        adhoc_blocks=adhoc_blocks,
    )


def align_agenda_with_transcript(
    plan: AgendaPlan,
    transcript: str,
) -> AlignmentResult:
    """基于发言人切换与议程人员网络匹配的通用对齐引擎。

    彻底解决：
    1. 真实转录中无任何议题标题行的问题；
    2. 会议现场换序（Permutations）或议题未讨论（Skips）问题；
    3. 全会高管评委在各议题穿插质询的精准归属；
    4. 最终纪要时序遵循现场研讨时间轴流淌；
    5. 主持人串场路标识别与转场闲聊/设备噪声隔离（三态状态机）。
    """
    reconcile_presenter_names(plan, transcript=transcript)
    blocks = group_transcript_blocks(transcript, plan=plan)
    all_speakers = set(b.speaker for b in blocks if b.speaker)

    track = _detect_alignment_track(plan, blocks)
    logger.info(
        "[AGENDA_ALIGNMENT] 启动对齐引擎，检测到策略轨迹: %s (总发言块: %d, 发言人总数: %d)",
        track,
        len(blocks),
        len(all_speakers),
    )
    if track == "CONTENT":
        return _align_by_topics_and_roadsigns(plan, blocks, all_speakers)

    item_tokens = {it.seq: extract_distinctive_tokens(it.title) for it in plan.items}
    hub_speakers, dual_speakers = _identify_hub_speakers(plan, blocks)
    logger.info(
        "[AGENDA_ALIGNMENT] 枢纽与主持人名单: %s | 双重身份(主持兼汇报人): %s",
        sorted(list(hub_speakers)),
        sorted(list(dual_speakers)),
    )

    # ── 阶段 1：多维特征感知与三态会话状态机 ───────────────────────────
    assigned: dict[int, str | None] = {}
    active_seq: str | None = None
    in_transition: bool = False
    pending_roadsign: str | None = None

    for b in blocks:
        is_closing = _is_session_closing(b.content)
        is_opening = _is_opening_signal(b.content)
        is_noise = _is_equipment_or_chitchat(b.content)

        roadsign_target, is_generic_handover = _detect_host_roadsign(
            b.speaker, b.content, plan, hub_speakers, dual_speakers=dual_speakers
        )

        if roadsign_target:
            pending_roadsign = roadsign_target
            in_transition = True
        elif is_generic_handover:
            in_transition = True

        if is_closing:
            in_transition = True

        scores = {
            it.seq: _score_block_for_item(
                b,
                it,
                item_tokens[it.seq],
                hub_speakers,
                is_opening,
                roadsign_seq=pending_roadsign,
                dual_speakers=dual_speakers,
            )
            for it in plan.items
        }
        best_seq, best_score = max(scores.items(), key=lambda x: x[1])

        # 状态机换轨决策
        if best_score >= 3.0:
            if best_seq != active_seq:
                if (
                    active_seq is None
                    or in_transition
                    or pending_roadsign == best_seq
                    or best_score >= 4.5
                    or (best_score >= scores.get(active_seq, 0) + 2.0)
                ):
                    active_seq = best_seq
                    in_transition = False
                    pending_roadsign = None
            assigned[b.index] = active_seq
        else:
            # 得分 < 3.0 的发言块处理（评委插话、简短回应、过场闲聊或设备调试）
            if in_transition:
                # 处于转场缓冲期（Transition Buffer）
                # 若为纯设备调试/杂音/或主持人过渡客套，进行隔离，绝不贪婪污染上一议题！
                is_host_or_dual = b.speaker in hub_speakers or (dual_speakers and b.speaker in dual_speakers and len(b.content) < 100)
                if is_noise or is_host_or_dual or len(b.content) < 30:
                    assigned[b.index] = None
                else:
                    # 检查是否仍然在对 active_seq 进行有实质意义的补充或质询
                    has_conflict = any(seq != active_seq and scores.get(seq, 0) >= 2.0 for seq in item_tokens)
                    if not has_conflict and active_seq is not None and scores.get(active_seq, 0) >= 1.0:
                        assigned[b.index] = active_seq
                        in_transition = False
                    else:
                        assigned[b.index] = None
            else:
                # 处于研讨态（IN_AGENDA）：无冲突时正常承接评委或团队短插话
                if active_seq is not None:
                    has_conflict = False
                    for seq in item_tokens:
                        if seq != active_seq and scores.get(seq, 0) >= 2.5:
                            has_conflict = True
                            break
                    if not has_conflict:
                        assigned[b.index] = active_seq
                    else:
                        assigned[b.index] = None
                else:
                    assigned[b.index] = None

        if is_opening and not is_closing and best_score >= 2.0:
            in_transition = False
            pending_roadsign = None

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
