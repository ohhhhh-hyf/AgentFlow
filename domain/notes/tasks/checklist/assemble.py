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
    unmatched = _unmatched_quotes(teacher, activated)
    plan = build_action_plan(cards, teacher, unmatched)
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


def distribution(cards: list[dict[str, Any]]) -> list[dict[str, float]]:
    """按知识点（card.name）分组累加权重，取 Top10，其余并入「其他」。

    复习重点分布按「知识点」而非章节展示：重点知识点不能太多，
    超出 10 个的部分在饼图中合并为「其他」一节。
    """
    weights = {"S": 40.0, "A": 25.0, "B": 15.0, "C": 8.0}
    buckets: dict[str, float] = {}
    for card in cards:
        label = _clean(card.get("name")) or _clean(card.get("topic")) or "未命名"
        buckets[label] = buckets.get(label, 0.0) + weights.get(
            card.get("session_priority") or "C", 8.0
        )
    total = sum(buckets.values()) or 1.0
    ranked = sorted(buckets.items(), key=lambda kv: -kv[1])
    top = ranked[:10]
    others = sum(v for _, v in ranked[10:])
    rows = [{"label": k, "value": round(v / total * 100, 1)} for k, v in top]
    if others > 0:
        rows.append({"label": "其他", "value": round(others / total * 100, 1)})
    if rows:  # 归一化 round 误差到末项
        drift = 100.0 - sum(r["value"] for r in rows)
        rows[-1]["value"] = round(rows[-1]["value"] + drift, 1)
    return rows
