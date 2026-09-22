"""本用户命中表：程序判定"这场会里哪些条目是他"，零 LLM。

为什么需要（P0-B）：下游要按人裁剪（视角裁剪、待办 owner、跨场记忆、审核），
但"他是谁"以前完全靠模型在理解/建模里自觉——实测同一个人被写成「发言者1 / 小赵 / 赵工」，
个人模式分工栏因对不上姓名而选空、程序又回退全量（"赵衡视角"输出全员待办）。
这里把"谁被点名、哪些待办是他的、哪些决策点了他"变成**可复核的程序结论**（带依据）。

匹配口径（与提示词里的称呼表配套，从严）：
- 称呼表 = 全称 + 别称（≥2 字；role/department 值不当称呼，见 preferences.address_aliases）
- 强命中：``action_hints[].owner`` / ``speakers[].name`` 与称呼**精确相等**
- 弱命中：决策/风险/未决/议题文本里出现**全称**（无边界要求）或**别称**（前一字须是标点/功能词，
  挡"小组赵工"、认"他说小赵"）
- 编号发言人（发言者1、发言人A）**不自动绑定**：只有别称表里显式写了该编号才可能命中
- 每条命中都带依据（字段路径 + 原样片段），供草稿直接抄、审核复核
"""
from __future__ import annotations

from difflib import SequenceMatcher

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .preferences import address_aliases

_WORD_CHAR_RE = re.compile(r"[\w\u4e00-\u9fff]")

STRONG = "strong"
WEAK = "weak"


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


# 别称前一字：标点/空白/功能词才说明它是句中的独立称呼；若是名词性汉字（"小组赵工"的"组"），
# 多为更长词/别人姓名里的片段。中文没有词边界，这里用"前一字白名单 + 前一字是标点"近似，
# 宁可漏（少认一个别称）也不误认（把别人的事写成他的）。
_ALLOW_BEFORE = set(
    "的是说在和跟给把被让叫问与及并且后其此那这我你他她它也都又还再就才只已没不"
    "，。；：、！？()（）【】《》「」“”‘’"
) | {" ", "\t", "\n"}


def _has_boundary(text: str, needle: str) -> bool:
    """纯拉丁称呼用两侧词边界（Alice / alice 大小写不敏感）。"""
    if not needle:
        return False
    for match in re.finditer(re.escape(needle), text, re.I):
        left = text[match.start() - 1] if match.start() > 0 else ""
        right = text[match.end()] if match.end() < len(text) else ""
        if not (_WORD_CHAR_RE.match(left) or _WORD_CHAR_RE.match(right)):
            return True
    return False


def _alias_mention(text: str, alias: str) -> bool:
    """别称是否作为"独立称呼"出现在文本里（中文看前一字，拉丁看两侧边界）。"""
    if not alias:
        return False
    if alias.isascii():
        return _has_boundary(text, alias)
    for match in re.finditer(re.escape(alias), text):
        if match.start() == 0 or text[match.start() - 1] in _ALLOW_BEFORE:
            return True
    return False


def _equals(value: object, addresses: list[str]) -> bool:
    text = _clean(value)
    if not text:
        return False
    return any(text == addr or (addr.isascii() and text.lower() == addr.lower()) for addr in addresses)


def _mentions(value: object, addresses: list[str], full_name: str = "") -> str:
    """文本里出现哪个称呼（返回命中的称呼，没有返回空串）。

    口径差异是刻意的：**全称不带边界要求**（"赵衡那边的双录还没确认" 是正常点名，要它命中）；
    **别称按 ``_alias_mention`` 判定**（"小组赵工"里的"赵工"不算，但"他说小赵"算）。
    代价是别人姓名里含你的全称（"赵衡宇"）会算弱命中——弱命中只影响文本归属提示，
    强命中（owner / speakers）是精确相等，不会因此张冠李戴。
    """
    text = _clean(value)
    if full_name and text and full_name in text:
        return full_name
    for addr in addresses:
        if addr and addr != full_name and _alias_mention(text, addr):
            return addr
    return ""


def _item_text(value: object) -> str:
    """risks/decisions/open_questions 契约上是字符串列表；LLM 漂移成对象时取 text。

    命中块是提示词：不归一化就会把 ``{'text': …}`` 的 Python 字面量塞进正文指令，
    模型和审核都读不出条目是什么。
    """
    if isinstance(value, dict):
        return _clean(value.get("text") or value.get("item"))
    return _clean(value)


def foreign_only(
    text: object,
    addresses: list[str],
    others: list[str],
    *,
    full_name: str = "",
) -> bool:
    """该条是不是"别人为主语、且完全没提到他"（真人模式裁素材用）。

    装配轮没有审核，模板栏位会把会议理解的条目直接变成正文条目——实测「武思华明天找他们
    要数据」就是这么进「行动项与分工」的，写作纪律压不住。裁素材只丢"别人为主语"的条目：
    提到他的留（如"问题单找武思华核一下"是他的事）、无人称的全局事实留（数字、结论）。
    """
    clean = _clean(text)
    if not clean:
        return False
    if _mentions(clean, addresses, full_name or (addresses[0] if addresses else "")):
        return False
    return any(name and name in clean for name in others)


@dataclass
class Hit:
    where: str       # 依据位置：action_hints[0].owner / speakers[1].name / risks[2]
    snippet: str     # 原样片段（不改写）
    strength: str    # strong / weak
    matched: str = ""  # 命中的称呼（全称或某个别称）


@dataclass
class HitTable:
    name: str = ""
    addresses: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    my_actions: list[str] = field(default_factory=list)   # owner 命中的待办原文（带时限）
    my_risks: list[str] = field(default_factory=list)
    my_decisions: list[str] = field(default_factory=list)
    my_open_questions: list[str] = field(default_factory=list)
    my_topics: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> str:
        if any(hit.strength == STRONG for hit in self.hits):
            return "high"
        return "medium" if self.hits else "none"

    @property
    def matched(self) -> bool:
        return bool(self.hits)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = self.confidence
        return data

    def evidence(self) -> list[str]:
        rows: list[str] = []
        for hit in self.hits:
            label = "" if hit.snippet == hit.matched else f"（{hit.matched}）"
            rows.append(f"{hit.where}：{hit.snippet}{label}")
        return rows


def build_hit_table(user: dict[str, Any] | None, understanding: dict[str, Any] | None) -> HitTable:
    """扫理解层输出，算本用户命中表（纯函数，不调模型）。

    客观/职业模板/无姓名 → 空表（不针对个人；职业名不是人名）。
    """
    profile = user if isinstance(user, dict) else {}
    if str(profile.get("perspective") or "").strip().lower() == "objective":
        return HitTable()
    if str(profile.get("persona_type") or "").strip().lower() == "role_template":
        return HitTable()
    name = _clean(profile.get("name"))
    if not name:
        return HitTable()
    addresses = [name, *address_aliases(profile)]
    data = understanding if isinstance(understanding, dict) else {}
    table = HitTable(name=name, addresses=addresses)

    for index, item in enumerate(data.get("action_hints") or []):
        if not isinstance(item, dict):
            continue
        snippet = _clean(item.get("text"))
        owner = _clean(item.get("owner"))
        if _equals(owner, addresses):
            table.hits.append(Hit(f"action_hints[{index}].owner", snippet or owner, STRONG, owner))
            timing = _clean(item.get("timing"))
            table.my_actions.append(f"{snippet}（{timing}）" if snippet and timing else (snippet or owner))
            # 挂在他条目上的风险也算他的：risks 是全场字符串列表，只有 action_hints 这侧带 owner，
            # 不在这里收，个人纪要的"他的风险"就只能靠风险文本里恰好写了他名字。
            risk_text = _item_text(item.get("risk"))
            if risk_text and risk_text not in table.my_risks:
                table.my_risks.append(risk_text)
            continue
        matched = _mentions(snippet, addresses, name)
        if matched:
            table.hits.append(Hit(f"action_hints[{index}]", snippet, WEAK, matched))

    for index, speaker in enumerate(data.get("speakers") or []):
        if not isinstance(speaker, dict):
            continue
        speaker_name = _clean(speaker.get("name"))
        if _equals(speaker_name, addresses):
            table.hits.append(Hit(f"speakers[{index}].name", speaker_name, STRONG, speaker_name))

    for key, bucket in (
        ("risks", table.my_risks),
        ("decisions", table.my_decisions),
        ("open_questions", table.my_open_questions),
    ):
        for index, text in enumerate(data.get(key) or []):
            item = _item_text(text)
            matched = _mentions(item, addresses, name)
            if matched:
                table.hits.append(Hit(f"{key}[{index}]", item, WEAK, matched))
                bucket.append(item)

    for index, topic in enumerate(data.get("topics") or []):
        if not isinstance(topic, dict):
            continue
        matched = _mentions(topic.get("title"), addresses, name)
        for person in topic.get("participants") or []:
            if _equals(person, addresses):
                matched = matched or _clean(person)
        if matched:
            title = _clean(topic.get("title"))
            table.hits.append(Hit(f"topics[{index}]", title or matched, WEAK, matched))
            if title:
                table.my_topics.append(title)
    return table


_SPEAKER_LINE_RE = re.compile(r"^\s*([^\s]{1,12})[ \t]+(\d{1,2}:\d{2}(?::\d{2})?)\s*$")
_OMIT_TEMPLATE = "……（此处省略 {n} 段与本人无关的发言）"


def speaker_blocks(transcript: str) -> list[tuple[str, str]]:
    """按「姓名 HH:MM:SS」发言行把原文切成块 → ``[(发言人称谓, 块文本)]``。

    与 :func:`slice_transcript_for_person` 共用同一发言行正则（``_SPEAKER_LINE_RE``）；
    题头（首个发言行之前）不返回，没有发言行结构时返回空表。
    """
    blocks: list[list[str]] = []
    for line in (transcript or "").splitlines():
        match = _SPEAKER_LINE_RE.match(line)
        if match:
            blocks.append([match.group(1), line])
            continue
        if blocks:
            blocks[-1][1] = f"{blocks[-1][1]}\n{line}"
    return [(speaker, block) for speaker, block in blocks]


_NORM_DROP_RE = re.compile(r"\W")  # 去掉所有非单词字符（空白/中英标点/符号/emoji）
# 归属判定门槛：与原文的最长公共连续子串至少这么多字、且覆盖条目这么多比例（见 _MATCH_NUM/_MATCH_DEN）
_MIN_MATCH_CHARS = 8  # 部分匹配（最长公共片段）门槛
_MIN_EXACT_CHARS = 6  # 完全包含也要求的最小长度（防两三个字的碎片乱命中）
_MATCH_NUM, _MATCH_DEN = 2, 5  # 覆盖率门槛 = 2/5（40%）


def _compact_for_match(text: str) -> str:
    """归一化：去掉所有非单词字符（空白、中英标点、符号、emoji 一并去掉，
    只留字母/数字/下划线与汉字）——转写与索引条目的标点常不一致，逐一点名标点不可维护。"""
    return _NORM_DROP_RE.sub("", text or "")


def _longest_common_run(left: str, right: str) -> int:
    """两串最长公共**连续子串**的长度（stdlib difflib）。

    用最长公共片段而不是整条包含：条目常被轻度改写（如「影响我这边」→「影响测试」），
    "整条包含"会全错过；而"最长公共片段"能对上改写点两侧的内容。
    """
    if not left or not right:
        return 0
    match = SequenceMatcher(None, left, right).find_longest_match(
        0, len(left), 0, len(right)
    )
    return match.size


def attribute_to_speaker(
    transcript: str,
    items: list[str],
    *,
    self_addresses: list[str] | None = None,
    self_name: str = "",
) -> dict[str, str]:
    """给每条文本找它在原文里出自哪位发言人 → ``{条目原文: 称谓}``（对不上就不出现）。

    用途：把"这条风险/未决是谁提出、谁在跟"变成**可照抄的事实**，而不是让模型去推理
    （2026-09-22 实测：契约要求按人分组，但上游 risks 无归属、模型又受"措辞用上游原文"
    约束，三轮真链路都没分组）。只在**能对上**时才给：条目按去标点归一化后被某个发言块
    包含、或与之的最长公共连续子串达到 ``_MIN_MATCH_CHARS`` 且覆盖条目
    ``_MATCH_NUM/_MATCH_DEN`` 以上）才返回该块首称呼；对不上一律不给（调用方按
    "看不出归属"处理）。块首属于 ``self_addresses``（全称/别称）时统一返回 ``self_name``。
    """
    blocks = speaker_blocks(transcript)
    if not blocks or not items:
        return {}
    norm = [(speaker, _compact_for_match(block)) for speaker, block in blocks]
    addresses = [a for a in (self_addresses or []) if a]

    def _canonical(speaker: str) -> str:
        if addresses and _equals(speaker, addresses):
            return self_name or speaker
        return speaker

    out: dict[str, str] = {}
    for item in items:
        key = _clean(item)
        probe = _compact_for_match(key)
        if not probe:
            continue
        hit = ""
        probe_chars = set(probe)
        best = 0
        for speaker, block in norm:
            if probe in block:  # 完全包含：直接命中（短条目也能算，只需过 _MIN_EXACT_CHARS）
                hit, best = speaker, len(probe)
                break
            if len(probe_chars & set(block)) * 2 < len(probe_chars):
                continue  # 字符重合太低，不可能有长公共片段（省掉昂贵的比对）
            size = _longest_common_run(probe, block)
            if size > best:
                hit, best = speaker, size
        if not hit:
            continue
        if best == len(probe):  # 完全包含
            if best >= _MIN_EXACT_CHARS:
                out[key] = _canonical(hit)
            continue
        if best >= _MIN_MATCH_CHARS and best * _MATCH_DEN >= len(probe) * _MATCH_NUM:
            out[key] = _canonical(hit)
    return out


_GROUPS_TITLE = "本用户分栏分组骨架"
_MAX_GROUPS = 6


def render_action_groups_block(
    user: dict[str, Any] | None,
    understanding: dict[str, Any] | None,
    *,
    limit: int = _MAX_GROUPS,
) -> str:
    """「分栏分组骨架」块：给模型一份**可直接照抄**的组名行清单（程序判定）。

    为什么（2026-09-22 两个模型实测）：契约与纪律都只是"描述"按人分块的形态，
    而模型擅长复制、不擅长重排 ⇒ 组名行始终写不出来。这里把"要出现哪些
    组名行"变成清单（与命中块同一机制），模型只需把条目填进对应块。
    末尾三栏（结论与决定 / 行动项与分工 / 待确认与风险）共用这一份骨架。

    他人侧优先取待办 owner（理解层 action_hints；单线纪要会被裁掉），
    退回与会发言人（speakers）；本人那行固定 ``SELF_GROUP_ROW``（`**与我相关**：`）。
    没有姓名（客观/无档案）时返回空串 ⇒ 不注入。
    """
    from .preferences import SELF_GROUP_ROW, address_aliases, extract_supervisors

    profile = user if isinstance(user, dict) else {}
    name = _clean(profile.get("name"))
    if not name:
        return ""
    addresses = [item for item in (name, *address_aliases(profile)) if item]
    pack = understanding if isinstance(understanding, dict) else {}

    def _is_self(value: object) -> bool:
        text = _clean(value)
        return bool(text) and (text in addresses or bool(_mentions(text, addresses, name)))

    # 他人组名 = 待办 owner ∪ 与会发言人：三栏共用一份骨架，而结论/风险里的条目可能挂在
    # 任何一位发言人名下（不只是有待办的人）。多出的行使"没有内容的组不出现"兜住，不会硬凑。
    others: list[str] = []
    for row in pack.get("action_hints") or []:
        if not isinstance(row, dict):
            continue
        owner = _clean(row.get("owner"))
        if not owner or _is_self(owner) or owner in others:
            continue
        others.append(owner)
    for row in pack.get("speakers") or []:
        if not isinstance(row, dict):
            continue
        who = _clean(row.get("name"))
        if not who or _is_self(who) or who in others:
            continue
        others.append(who)

    # 上级优先：画像中声明的上级若在参会/分工名单中，提到他人组名最前
    supervisors = extract_supervisors(profile)
    for sup in reversed(supervisors):
        if sup in others:
            others.remove(sup)
            others.insert(0, sup)
        elif any(sup in str(row.get("name") if isinstance(row, dict) else row) for row in (pack.get("speakers") or [])):
            others.insert(0, sup)

    lines = [
        f"【{_GROUPS_TITLE}（程序判定；末尾三栏「结论与决定」「行动项与分工」「待确认与风险」"
        "都按它分块——组名行**照抄**、把条目填到对应块里）】",
        SELF_GROUP_ROW,
    ]
    lines.extend(f"**{who}**：" for who in others[:limit])
    lines.append("（没有内容的组不出现；组名行独占一行、不加 `- `）")
    return "\n".join(lines)


def slice_transcript_for_person(
    transcript: str,
    addresses: list[str],
    *,
    full_name: str = "",
    min_keep_chars: int = 200,
    self_label: str = "",
) -> tuple[str, dict[str, Any]]:
    """按人裁原文：只留**他发言的段**与**提到他的段**，其余折叠成一行省略说明。

    为什么要在原文这一层动手（2026-09-21 实测两轮）：模板路径的正文由通用填充器逐栏写，
    【内容来源】里放着整场原文，模板栏名又是「全文摘要 / 分段速览」——写作纪律写在消息
    开头（691 字）也压不过眼前两万字原文，真人模式照样输出整场（实测「你」10 次、
    「申家坤」23 次、正文 9082 字，提及他的段落只占 12%）。把原文按人裁掉，栏位就没得抄。

    形如 ``姓名 HH:MM:SS`` 的发言行分块；块首称呼能对上（全称/别称）或块内提到他 → 留。
    ``self_label`` 非空时把他自己的块首称呼换成该字样（默认由调用方传「你」）：原文里
    满屏「申家坤 00:35:20」会把模型拽回第三人称，实测同一份上下文两轮，一轮「你」37 次、
    另一轮只剩 11 次。
    返回 ``(文本, 统计)``；``统计["fallback"]`` 为真表示"裁不了/裁完太少"，调用方应退回整篇。
    """
    text = transcript or ""
    stats: dict[str, Any] = {"kept": 0, "dropped": 0, "fallback": False, "chars": len(text)}
    addresses = [a for a in (addresses or []) if a]
    if not text.strip() or not addresses:
        stats["fallback"] = True
        return text, stats

    blocks: list[list[str]] = []  # [块首称呼, 整块文本]
    head: list[str] = []          # 首个发言行之前的题头
    for line in text.splitlines():
        match = _SPEAKER_LINE_RE.match(line)
        if match:
            blocks.append([match.group(1), line])
            continue
        if blocks:
            blocks[-1][1] = f"{blocks[-1][1]}\n{line}"
        else:
            head.append(line)
    if len(blocks) < 2:  # 没有稳定的发言行结构，裁不动
        stats["fallback"] = True
        return text, stats

    out: list[str] = list(head)
    pending = 0  # 连续被丢掉的块数
    kept_chars = 0
    for speaker, block in blocks:
        keep = _equals(speaker, addresses) or bool(
            _mentions(block, addresses, full_name or addresses[0])
        )
        if keep:
            if pending:
                out.append(_OMIT_TEMPLATE.format(n=pending))
                pending = 0
            if self_label and _equals(speaker, addresses):
                head_line, sep, rest = block.partition("\n")
                block = f"{self_label}{head_line[len(speaker):]}{sep}{rest}"
            out.append(block)
            kept_chars += len(block)
            stats["kept"] += 1
        else:
            pending += 1
            stats["dropped"] += 1
    if pending:
        out.append(_OMIT_TEMPLATE.format(n=pending))
    if not stats["kept"] or kept_chars < min_keep_chars:
        stats["fallback"] = True  # 裁完太少：宁可用整篇，也不让正文没料
        return text, stats
    stats["chars"] = len("\n".join(out))
    return "\n".join(out), stats


def render_hit_block(table: HitTable) -> str:
    """给草稿/审核看的命中块（程序结论 + 依据，措辞明确"不是模型推断"）。"""
    if not table.name:
        return ""
    if not table.hits:
        return (
            f"【本用户命中（程序判定）】{table.name}：本场**没有任何条目命中他**"
            "（没有待办挂他名下、speakers 里没有他、决策/风险/未决也没点他名）。\n"
            "不要把他写成负责人、相关方或发言人；分工栏可以为空。"
        )
    lines = [f"【本用户命中（程序判定，带依据）】{table.name}：命中 {len(table.hits)} 处。"]
    for hit in table.hits[:8]:
        label = "强" if hit.strength == STRONG else "弱"
        lines.append(f"- [{label}] {hit.where}：{hit.snippet}")
    if table.my_actions:
        lines.append("- 他的待办（原文承诺，直接可用）：" + "；".join(table.my_actions[:6]))
    if table.my_risks:
        lines.append("- 点了他的风险：" + "；".join(table.my_risks[:4]))
    if table.my_topics:
        lines.append("- 他参与的议题：" + "；".join(table.my_topics[:4]))
    lines.append("没有列在这里的条目不算他的——不要凭职业或关注域把别人的条写成他的。")
    return "\n".join(lines)


# ── 真人模式末尾三栏确定性规范化 ──────────────────────────────
_DEFAULT_ONLY_RE = re.compile(
    r"^(?:原文|本次|本栏|文中|此处)?(?:也|均|尚|暂|都)?(?:未提及|未明确|未提供|未给出|没有提及|无提及|暂无|待定|不明确|未涉及|未写|无)[。.；;]?$"
)


def _is_default_only_text(s: str) -> bool:
    t = re.sub(r"[\s*`>#|()（）\[\]【】]+", "", s or "")
    if not t:
        return True
    return bool(_DEFAULT_ONLY_RE.match(t))


_TARGET_SECTION_KEYWORDS = (
    ("结论", "决定", "决策"),
    ("行动", "分工", "待办", "任务"),
    ("待确认", "风险", "未决", "阻塞"),
)


def _is_target_section(title: str) -> bool:
    t = str(title or "").strip()
    return any(any(k in t for k in group) for group in _TARGET_SECTION_KEYWORDS)


def _normalize_section_body(
    body: str,
    addresses: list[str],
    self_name: str,
    supervisors: list[str] | None = None,
) -> str:
    lines = [ln.rstrip() for ln in body.splitlines()]
    non_empty = [ln for ln in lines if ln.strip()]
    if not non_empty:
        return body

    if len(non_empty) == 1 and _is_default_only_text(non_empty[0]):
        return body

    group_header_re = re.compile(r"^\s*(?:-\s*)?\*\*([^*:\n]{1,20})\*\*[：:]?\s*$")
    inline_group_re = re.compile(r"^\s*(?:-\s*)?\*\*([^*:\n]{1,20})\*\*[：:]\s*(.+)$")
    inline_plain_re = re.compile(r"^\s*-\s+([^\s：:]{2,6})[：:]\s*(.+)$")

    global_items: list[str] = []
    groups: dict[str, list[str]] = {}
    current_group: str | None = None
    active_supervisors = list(supervisors or [])

    def _is_self_group(gname: str) -> bool:
        gn = gname.strip()
        return (
            gn in addresses
            or gn in {"与我相关", "本人", "我的待办", "自己"}
            or bool(self_name and gn == self_name)
        )

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 1. 独立组名行：**组名**：或 - **组名**：
        m_hdr = group_header_re.match(s)
        if m_hdr:
            gname = m_hdr.group(1).strip()
            if _is_self_group(gname):
                current_group = "**与我相关**："
            else:
                current_group = f"**{gname}**："
            if current_group not in groups:
                groups[current_group] = []
            continue

        # 2. 单行内嵌组名：- **姓名**：内容 或 - 姓名：内容
        m_inline = inline_group_re.match(s) or inline_plain_re.match(s)
        if m_inline:
            gname = m_inline.group(1).strip()
            content = m_inline.group(2).strip()
            if _is_self_group(gname):
                grp = "**与我相关**："
            else:
                grp = f"**{gname}**："
            if grp not in groups:
                groups[grp] = []
            current_group = grp
            item = content if content.startswith("- ") else f"- {content}"
            groups[grp].append(item)
            continue

        # 3. 缩进子条（如   - 细节）
        if line.startswith(("  -", "    -", "\t-")):
            if current_group is not None and current_group in groups:
                if not groups[current_group]:
                    groups[current_group].append(re.sub(r"^\s*-\s*", "- ", line))
                else:
                    groups[current_group].append(line)
            else:
                global_items.append(line)
            continue

        # 4. 普通条目行
        raw_content = re.sub(r"^\s*[-*+•]\s*", "", s).strip()
        if not raw_content:
            continue

        if current_group is not None:
            content = raw_content
            if current_group == "**与我相关**：":
                for addr in addresses:
                    if content.startswith(f"{addr}：") or content.startswith(f"{addr}:"):
                        content = content[len(addr) + 1:].strip()
                    elif content.startswith(f"{addr} "):
                        content = content[len(addr) + 1:].strip()
            groups[current_group].append(f"- {content}")
        else:
            matched_who = None
            for addr in addresses:
                if (
                    raw_content.startswith(f"{addr}：")
                    or raw_content.startswith(f"{addr}:")
                    or raw_content.startswith(f"{addr} ")
                ):
                    matched_who = "self"
                    content = re.sub(rf"^{re.escape(addr)}[：:\s]+", "", raw_content)
                    break
            if not matched_who and active_supervisors:
                for sup in active_supervisors:
                    if (
                        raw_content.startswith(f"{sup}：")
                        or raw_content.startswith(f"{sup}:")
                        or raw_content.startswith(f"{sup} ")
                    ):
                        matched_who = sup
                        content = re.sub(rf"^{re.escape(sup)}[：:\s]+", "", raw_content)
                        break

            if matched_who == "self":
                grp = "**与我相关**："
                if grp not in groups:
                    groups[grp] = []
                current_group = grp
                groups[grp].append(f"- {content}")
            elif matched_who:
                grp = f"**{matched_who}**："
                if grp not in groups:
                    groups[grp] = []
                current_group = grp
                groups[grp].append(f"- {content}")
            else:
                global_items.append(f"- {raw_content}")

    ordered_groups: list[tuple[str, list[str]]] = []
    if "**与我相关**：" in groups and groups["**与我相关**："]:
        ordered_groups.append(("**与我相关**：", groups["**与我相关**："]))

    for sup in active_supervisors:
        s_key = f"**{sup}**："
        if s_key in groups and groups[s_key]:
            ordered_groups.append((s_key, groups[s_key]))

    for grp, items in groups.items():
        if grp != "**与我相关**：" and grp not in [k for k, _ in ordered_groups] and items:
            ordered_groups.append((grp, items))

    if not ordered_groups:
        if global_items:
            return "\n".join(global_items)
        return body

    chunks: list[str] = []
    if global_items:
        chunks.append("\n".join(global_items))
    for grp_header, items in ordered_groups:
        chunks.append(f"{grp_header}\n" + "\n".join(items))

    return "\n\n".join(chunks)


def normalize_personal_sections(
    text: str,
    addresses: list[str],
    self_name: str = "",
    supervisors: list[str] | None = None,
) -> str:
    """真人模式下对末尾三栏（结论与决定/行动项与分工/待确认与风险）做确定性规范化。

    将平铺的 `- 姓名：内容` 或混入 bullet 的 `- **与我相关**：` 规范化为统一的
    独占行组名（**与我相关**：/ **姓名**：）及下方分条，并确保本人在前、上级紧随其后。
    """
    if not text or not text.strip():
        return text

    parts = re.split(r"(?m)^(#{2,3}\s+[^\n]+)$", text)
    if len(parts) < 3:
        return text

    new_parts: list[str] = [parts[0]]
    i = 1
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        m = re.match(r"^#{2,3}\s+(.+)$", header.strip())
        title = m.group(1).strip() if m else ""
        if _is_target_section(title):
            norm_body = _normalize_section_body(
                body,
                addresses=addresses,
                self_name=self_name,
                supervisors=supervisors,
            )
            new_parts.append(header)
            new_parts.append(norm_body if norm_body.startswith("\n") else f"\n{norm_body}\n\n")
        else:
            new_parts.append(header)
            new_parts.append(body)
        i += 2

    return "".join(new_parts)


__all__ = [
    "Hit",
    "HitTable",
    "STRONG",
    "WEAK",
    "attribute_to_speaker",
    "build_hit_table",
    "normalize_personal_sections",
    "render_action_groups_block",
    "render_hit_block",
    "speaker_blocks",
]
