"""把 Catalog 激活结果和 LLM 卡片合成复习清单草稿。"""
from __future__ import annotations

import re
from typing import Any

from .action import build_action_plan
from .select import _as_list, _clean, _hit_in, _needles, _sentences, _compact

_BANNED = re.compile(r"(必考概率|出题概率|\d+%\s*概率|百分之\d+)")
_MUST_WORDS = ("必考", "每届必出", "年年有", "一定出")


def _fallback_facts(row: dict[str, Any]) -> list[str]:
    items = _as_list(row.get("session_focus_items")) or _as_list(row.get("knowledge_items"))
    facts = [item for item in items[:6]]
    quotes = _as_list(row.get("session_quotes"))
    if quotes and quotes[0] not in facts:
        facts.append("老师原话：" + quotes[0][:60])
    return facts[:6]


def _fallback_explain(row: dict[str, Any], brief: bool = False) -> str:
    name = _clean(row.get("name"))
    must = _as_list(row.get("knowledge_items"))
    focus = _as_list(row.get("session_focus_items"))
    missing = _as_list(row.get("note_missing_items"))
    quotes = _as_list(row.get("session_quotes"))
    if brief:
        bits = [f"{name}这次只需抓住定义和限制条件。"]
        if focus:
            bits.append("老师点到：" + "、".join(focus[:3]) + "。")
        elif must:
            bits.append("先记住：" + "、".join(must[:3]) + "。")
        if quotes:
            bits.append(quotes[0][:70] + "。")
        return "".join(bits)
    kind = str(row.get("knowledge_type") or "concept")
    parts = [
        f"{name}是目录里已有的知识点，类型是{kind}。",
        "先把必须会的条目钉死：" + "、".join(must[:6] or [name]) + "。",
    ]
    if focus:
        parts.append("老师这次点到的是：" + "、".join(focus) + "，复习时按这些条目展开，不要另开新点。")
    elif quotes:
        parts.append("对照老师原话来用：" + quotes[0][:80] + "。")
    if missing:
        parts.append("笔记里还没写到：" + "、".join(missing[:4]) + "，对着目录 Item 补上即可，不代表没掌握。")
    parts.append("做题时先判断本题是不是在用它，再按方法步骤走，最后回代检查适用条件。")
    return "".join(parts)


def _fallback_method(row: dict[str, Any]) -> list[str]:
    kind = str(row.get("knowledge_type") or "concept")
    name = _clean(row.get("name"))
    focus = _as_list(row.get("session_focus_items")) or _as_list(row.get("knowledge_items"))[:3]
    if kind in {"method", "application"}:
        return [
            f"先判断本题是不是在用{name}",
            "按老师点到的类型选套路：" + "、".join(focus or ["先辨认再动手"]),
            "写出关键变形或中间步骤，不要跳步",
            "做完回看原题，检查适用条件和限制是否还成立",
            "用老师点过的易错点复查一遍",
        ]
    if kind == "formula":
        return [
            f"默写{name}的标准形式和成立条件",
            "检查变量是否满足公式前提",
            "先凑成标准形再代入，不要直接套裸公式",
            "代入后回代检查有没有改变原问题",
        ]
    return [
        f"用自己的话复述{name}的定义或结论，并写出一条限制条件",
        "对照老师点到的判断流程逐步核验：" + "、".join(focus or ["先看条件再下结论"]),
        "用一个正例确认能用，再用一个反例钉住边界",
        "若要写证明，按「构造 → 验证条件 → 下结论」的顺序落笔",
    ]


def _fallback_pitfalls(row: dict[str, Any]) -> list[str]:
    out = []
    err = _clean(row.get("session_error_signal"))
    if err:
        out.append(err)
    missing = _as_list(row.get("note_missing_items"))
    if missing:
        out.append("笔记缺：" + "、".join(missing[:3]) + "，容易漏条件，对着目录补。")
    kind = str(row.get("knowledge_type") or "")
    if kind == "formula" and not any("条件" in x for x in out):
        out.append("公式有成立条件，条件不满足时不能硬套。")
    return out[:4]


def _sanitize_exam(text: str, row: dict[str, Any], teacher: str) -> str:
    raw = _clean(text)
    allowed = any(mark in (teacher or "") for mark in _MUST_WORDS)
    if not allowed:
        raw = raw.replace("必考", "老师点到要抓")
    raw = _BANNED.sub("考试信号", raw)
    if not raw:
        signal = row.get("session_exam_signal") or row.get("exam_signal") or "none"
        if signal == "strong" and allowed:
            raw = "老师原话里有明确考试信号，按大题准备。"
        elif signal in {"medium", "strong"}:
            raw = "材料里有考试相关信号，按老师点到的题型准备，不估计具体占比。"
        else:
            raw = "老师本次没有给出明确考法，先把定义和限制条件钉死。"
    return raw


_STRATEGY_FILLER = ("多看书", "多做题", "多做练习", "认真复习", "好好复习", "努力", "多练")
_STRATEGY_JARGON = ("KP", "知识目录", "目录节点", "激活", "S/A 级", "级 KP", "档位")


def _clean_strategy(
    llm_draft: dict[str, Any] | None, *, has_teacher: bool
) -> list[str]:
    """取 LLM 复习策略并清洗：去空、去模板套话、去重，最多 4 条。

    丢弃含内部术语（KP/S级/知识目录等）的条目——复习策略是给用户看的，
    不能泄漏系统内部概念；无老师重点时额外过滤含「老师」字样的条目。
    """
    items = [
        item
        for item in ((llm_draft or {}).get("strategy") or [])
        if isinstance(item, str)
    ]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if len(text) < 6:
            continue
        if any(mark in text for mark in _STRATEGY_FILLER):
            continue
        if any(mark in text for mark in _STRATEGY_JARGON):
            continue
        if not has_teacher and "老师" in text:
            continue
        key = text.replace(" ", "").replace("\u3000", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= 4:
            break
    return out


def _clamp_rank(value: Any, default: int = 3) -> int:
    """importance/difficulty 归一化到 1-5；缺失或非法取默认 3，不误判。"""
    try:
        rank = int(str(value or "") or default)
    except (TypeError, ValueError):
        rank = default
    return max(1, min(5, rank))


def _build_priority_facts(rows: list[dict[str, Any]]) -> list[str]:
    """快赢优先 + 低价值后置：按 importance - difficulty 排执行顺序（纯规则）。

    条目格式可读：知识点 + 难度/重要性 + 适合怎么做；分组互斥（快赢/硬骨头/
    低价值），无老师也生效（字段来自 catalog）；少于 2 个点时跳过。
    """
    scored: list[tuple[str, int, int]] = []
    for r in rows:
        name = _clean(r.get("name"))
        if not name:
            continue
        scored.append((name, _clamp_rank(r.get("importance")), _clamp_rank(r.get("difficulty"))))
    if len(scored) < 2:
        return []
    quick = [n for n, imp, diff in scored if imp >= 4 and diff <= 2]
    hard = [n for n, imp, diff in scored if imp >= 4 and diff >= 4]
    low = [n for n, imp, diff in scored if imp <= 3 and diff >= 4]
    facts: list[str] = []
    if quick:
        facts.append(
            f"「{'、'.join(quick[:3])}」知识点：难度1-2、重要性4-5，"
            "重要且不难，适合最先复习、优先拿下"
        )
    if hard:
        facts.append(
            f"「{'、'.join(hard[:3])}」知识点：难度4-5、重要性4-5，"
            "重要但难度高，适合安排整块时间再复习"
        )
    if low:
        facts.append(
            f"「{'、'.join(low[:3])}」知识点：难度4-5、重要性1-3，"
            "难度高且重要性低，适合放最后、时间不够先了解即可"
        )
    return facts


def _build_strategy_facts(
    rows: list[dict[str, Any]], teacher: str
) -> list[str]:
    """从 session 数据抽「有理有据」的复习策略事实；无对应数据不生成。

    顺序指导（快赢优先/低价值后置）放最前，其余事实带依据（老师原话 /
    目录信号 / 笔记缺项）。没传老师重点时：不生成任何「老师重点/老师原话」相关内容。
    """
    has_teacher = bool((teacher or "").strip())
    facts = _build_priority_facts(rows)
    named = [r for r in rows if r.get("session_quotes")] if has_teacher else []
    if named:
        chapters: dict[str, int] = {}
        for r in named:
            ch = _clean(r.get("chapter")) or _clean(r.get("topic")) or "未分章"
            chapters[ch] = chapters.get(ch, 0) + 1
        top = "、".join(
            f"「{ch}」"
            for ch, _ in sorted(chapters.items(), key=lambda kv: -kv[1])[:3]
        )
        first_quote = _clean((named[0].get("session_quotes") or [""])[0])
        base = f"老师重点集中在{top}，共点名 {len(named)} 个知识点，优先主攻"
        if first_quote:
            base += f"（依据：老师原话「{first_quote[:40]}」）"
        facts.append(base)
    for r in rows:
        sig = str(r.get("session_exam_signal") or r.get("exam_signal") or "none")
        if sig != "strong":
            continue
        quotes = _as_list(r.get("session_quotes"))
        name = _clean(r.get("name"))
        if quotes and has_teacher:
            facts.append(
                f"{name} 有明确考试信号，按大题准备（依据：老师原话「{_clean(quotes[0])[:40]}」）"
            )
        else:
            facts.append(f"{name} 材料里有考试相关信号，按目录题型准备")
    for r in rows:
        hard = str(r.get("session_difficulty_signal") or "") == "hard"
        prove = str(r.get("knowledge_type") or "") == "prove"
        if hard or prove:
            facts.append(
                f"{_clean(r.get('name'))} 属于难点/证明类，建议独立推一遍完整流程"
            )
    missing: list[str] = []
    for r in rows:
        for item in _as_list(r.get("note_missing_items")):
            text = _clean(item)
            if text and text not in missing:
                missing.append(text)
    if missing:
        facts.append(
            f"笔记缺「{'、'.join(missing[:3])}」，先对着目录补上（依据：note_missing_items）"
        )
    for r in rows:
        err = _clean(r.get("session_error_signal"))
        if err:
            if has_teacher:
                facts.append(f"{_clean(r.get('name'))} 易错：{err[:40]}（依据：老师原话）")
            else:
                facts.append(f"{_clean(r.get('name'))} 易错：{err[:40]}")
    out: list[str] = []
    seen: set[str] = set()
    for item in facts:
        key = item.replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= 6:
            break
    return out


def _merge_strategy(facts: list[str], llm: list[str]) -> list[str]:
    """事实策略在前（有据），LLM 方向性策略在后；去重，最多 8 条。"""
    out = list(facts)
    seen = {f.replace(" ", "") for f in out}
    for item in llm:
        key = item.replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= 8:
            break
    return out


def assemble_checklist(
    catalog: dict[str, Any] | None,
    activated: list[dict[str, Any]],
    llm_draft: dict[str, Any] | None,
    teacher: str,
) -> dict[str, Any]:
    catalog = catalog or {}
    cards_in = {
        _clean(c.get("kp_id")): c
        for c in (llm_draft or {}).get("cards") or []
        if isinstance(c, dict) and _clean(c.get("kp_id"))
    }
    allowed = {_clean(r.get("id")) for r in activated}
    cards: list[dict[str, Any]] = []
    for row in activated:
        kid = _clean(row.get("id"))
        blob = cards_in.get(kid) or {}
        if kid not in allowed:
            continue
        grade = row.get("session_priority") or "C"
        brief = grade not in {"S", "A"}
        explain = _clean(blob.get("explain")) or _fallback_explain(row, brief=brief)
        if not brief and len(explain) < 120:
            explain = _fallback_explain(row, brief=False)
        methods = _as_list(blob.get("method_steps")) or _fallback_method(row)
        if not brief and len(methods) < 4:
            methods = _fallback_method(row)
        pitfalls = _as_list(blob.get("pitfalls")) or _fallback_pitfalls(row)
        facts = _as_list(blob.get("key_facts")) or _fallback_facts(row)
        if brief:
            facts = facts[:3]
            methods = methods[:3]
            pitfalls = pitfalls[:2]
            if len(explain) > 160:
                explain = explain[:157].rstrip("，。；;、 ") + "。"
        exam = _sanitize_exam(_clean(blob.get("exam_preview")), row, teacher)
        cards.append(
            {
                **{k: row.get(k) for k in (
                    "id", "name", "aliases", "chapter", "topic", "knowledge_type",
                    "knowledge_items", "importance", "difficulty", "foundational_level",
                    "note_coverage", "note_missing_items", "prerequisites", "related_points",
                    "practice_type", "completion_criteria", "learning_role", "risk_tags",
                    "session_emphasis", "session_focus_items", "session_exam_signal",
                    "session_error_signal", "session_difficulty_signal",
                    "session_related_points", "session_quotes", "session_priority",
                    "session_practice_count", "session_special_requirement", "_prereq_of",
                )},
                "exam_preview": exam,
                "key_facts": facts,
                "explain": explain,
                "method_steps": methods,
                "pitfalls": pitfalls,
                "detail": True,
            }
        )
    unmatched = _unmatched_quotes(teacher, activated) if (teacher or "").strip() else []
    has_teacher = bool((teacher or "").strip())
    strategy = _merge_strategy(
        _build_strategy_facts(activated, teacher),
        _clean_strategy(llm_draft, has_teacher=has_teacher),
    )
    plan = build_action_plan(cards, teacher, unmatched, strategy=strategy)
    return {
        "course": _clean(catalog.get("course")) or _clean((llm_draft or {}).get("course")) or "课程复习清单",
        "catalog_version": str(catalog.get("version") or ""),
        "cards": cards,
        "uncertain_quotes": plan.get("uncertain_quotes") or [],
        "strategy": plan.get("strategy") or [],
        "phases": plan.get("phases") or [],
    }


_UNMATCHED_HINT = (
    "必考", "重点", "了解", "注意", "要求", "定义", "概念", "公式",
    "定理", "方法", "计算题", "证明题", "选择", "简答",
)


def _unmatched_quotes(teacher: str, activated: list[dict[str, Any]]) -> list[str]:
    needles: list[str] = []
    for row in activated:
        needles.extend(_needles(row))
    out: list[str] = []
    for sent in _sentences(teacher):
        if len(sent) < 16 or sent.startswith(("同学们", "下课")):
            continue
        if re.match(r"^[一二三四五六七八九十]+、", sent):
            continue
        if not any(mark in sent for mark in _UNMATCHED_HINT):
            continue
        compact = _compact(sent)
        if any(_hit_in(sent, compact, needle) for needle in needles):
            continue
        if sent not in out:
            out.append(sent)
    return out[:6]


_PIE_MIN_PCT = 5.0
_PIE_REST = "·其余"
_PIE_WEIGHTS = {"S": 40.0, "A": 25.0, "B": 15.0, "C": 8.0}


def _pie_rows(buckets: dict[str, float]) -> list[dict[str, float]]:
    total = sum(buckets.values()) or 1.0
    rows = [
        {"label": name, "value": round(weight / total * 100, 1)}
        for name, weight in sorted(buckets.items(), key=lambda item: -item[1])
        if weight > 0
    ]
    if rows:
        drift = 100.0 - sum(row["value"] for row in rows)
        rows[-1]["value"] = round(rows[-1]["value"] + drift, 1)
    return rows


def _chapter_distribution(cards: list[dict[str, Any]]) -> list[dict[str, float]]:
    buckets: dict[str, float] = {}
    for card in cards:
        chapter = _clean(card.get("chapter")) or _clean(card.get("topic")) or "未分章"
        grade = str(card.get("session_priority") or "C")
        buckets[chapter] = buckets.get(chapter, 0.0) + _PIE_WEIGHTS.get(grade, 8.0)
    return _pie_rows(buckets)


def distribution(cards: list[dict[str, Any]]) -> list[dict[str, float]]:
    """饼图只画核心/重点（S/A）。扇区 ≥5% 单独成块，更小的按章归为「章名·其余」。

    没有核心/重点时退回按章分布。不再写死 Top10，也不用匿名「其他」。
    """
    core = [
        card
        for card in cards
        if str(card.get("session_priority") or "") in {"S", "A"}
    ]
    if not core:
        return _chapter_distribution(cards)

    named: dict[str, float] = {}
    chapter_of: dict[str, str] = {}
    for card in core:
        name = _clean(card.get("name")) or _clean(card.get("topic")) or "未命名"
        chapter = _clean(card.get("chapter")) or _clean(card.get("topic")) or "未分章"
        grade = str(card.get("session_priority") or "A")
        named[name] = named.get(name, 0.0) + _PIE_WEIGHTS.get(grade, 25.0)
        chapter_of.setdefault(name, chapter)

    total = sum(named.values()) or 1.0
    kept: dict[str, float] = {}
    rest_by_chapter: dict[str, float] = {}
    for name, weight in named.items():
        if weight / total * 100 >= _PIE_MIN_PCT:
            kept[name] = weight
        else:
            chapter = chapter_of.get(name) or "未分章"
            rest_by_chapter[chapter] = rest_by_chapter.get(chapter, 0.0) + weight
    for chapter, weight in rest_by_chapter.items():
        kept[f"{chapter}{_PIE_REST}"] = kept.get(f"{chapter}{_PIE_REST}", 0.0) + weight
    return _pie_rows(kept)
