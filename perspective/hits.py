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


__all__ = ["Hit", "HitTable", "STRONG", "WEAK", "build_hit_table", "render_hit_block"]
