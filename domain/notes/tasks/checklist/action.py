"""行动清单：按 Catalog 字段 + 本次 session 信号聚合成固定四张卡。

展示层只渲染卡片数据，不在这里写课程特例。
"""
from __future__ import annotations

from typing import Any

from .select import _as_list, _clean

_CRITERIA = {
    "can_recall": "能独立复述 / 默写核心内容",
    "can_explain": "能用自己的话解释原理和条件",
    "can_distinguish": "能准确区分易混概念",
    "can_apply": "能在典型场景中正确应用",
    "can_choose_method": "能根据题目特征选对方法",
    "can_solve_standard": "能独立完成标准题",
    "can_solve_variant": "能处理常见变式",
    "can_prove": "能独立写出完整证明过程",
}
_CRITERIA_RANK = (
    "can_solve_variant",
    "can_prove",
    "can_choose_method",
    "can_distinguish",
    "can_solve_standard",
    "can_apply",
    "can_explain",
    "can_recall",
)
_FAMILY_SPECIAL = {
    "prove": "推理专项",
    "apply": "应用专项",
    "calc": "方法专项",
    "distinguish": "辨析专项",
    "recall": "要点专项",
}
_ACTION_TEMPLATES = {
    "calculate": "按标准流程把{names}做完",
    "choose_method": "先根据题目特征判断该用{names}里的哪一种做法",
    "prove": "独立写出{names}的完整推理结构",
    "distinguish": "对比{names}的易混点，并说清判断依据",
    "apply": "把{names}用到具体问题上",
    "recall": "复述{names}的核心定义和一条限制条件",
    "mixed": "把{names}串起来完成一道综合题",
}
_CARD_SPECS = (
    {
        "id": "card_1",
        "order": 1,
        "kind": "foundation",
        "title": "基础快速过关",
        "subtitle": "先确认后续核心内容真正依赖的定义和前提",
        "summary": "快速过一遍必要前置，确认能直接支撑后面的核心任务",
        "unit": "个基础确认",
        "empty_goal": "本次没有必须先过的前置，可以直接进入核心冲刺。",
    },
    {
        "id": "card_2",
        "order": 2,
        "kind": "core",
        "title": "核心冲刺",
        "subtitle": "集中处理老师本次点名的核心内容与方法",
        "summary": "把最重要的知识块练到会判断、会做、会变式",
        "unit": "个核心任务",
        "empty_goal": "本次没有单独列出的核心冲刺任务。",
    },
    {
        "id": "card_3",
        "order": 3,
        "kind": "special",
        "title": "重点专项突破",
        "subtitle": "把需要独立流程的重点能力单独练透",
        "summary": "专项突破完整流程，不和高频核心训练混在一起",
        "unit": "个专项",
        "empty_goal": "本次没有需要单独开练的专项。",
    },
    {
        "id": "card_4",
        "order": 4,
        "kind": "sweep",
        "title": "扫雷补漏",
        "subtitle": "最后集中检查易混点、使用条件和关键流程",
        "summary": "考前统一扫一遍最容易出错的地方，避免会做但丢分",
        "unit": "类扫雷",
        "empty_goal": "本次没有额外的扫雷项。",
    },
)


def _types(card: dict[str, Any]) -> list[str]:
    return [key for key in _as_list(card.get("practice_type")) if key]


def _family(card: dict[str, Any]) -> str:
    kinds = set(_types(card))
    role = str(card.get("learning_role") or "")
    if "prove" in kinds:
        return "prove"
    if kinds & {"calculate", "choose_method"}:
        return "calc"
    if "distinguish" in kinds:
        return "distinguish"
    if kinds & {"apply", "mixed"} or role in {"application", "integration"}:
        return "apply"
    return "recall"


def _needed_prereq_names(cards: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for card in cards:
        if card.get("session_priority") in {"S", "A"}:
            names.update(_as_list(card.get("prerequisites")))
    return names


def _foundation_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needed = _needed_prereq_names(cards)
    out: list[dict[str, Any]] = []
    for card in cards:
        if card.get("session_priority") in {"S", "A"}:
            continue
        name = _clean(card.get("name"))
        role = str(card.get("learning_role") or "")
        if name in needed or card.get("_prereq_of") or (
            role == "foundation" and card.get("session_priority") == "B"
        ):
            out.append(card)
    return out


def _uniq(items: list[str], limit: int = 8) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = _clean(item)
        key = text.replace(" ", "")
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _join(names: list[str], limit: int = 6) -> str:
    return "、".join(_uniq(names, limit))


def _clip(text: str, limit: int) -> str:
    raw = _clean(text)
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip("，。；;、 ") + "…"


def _pick_criteria(cards: list[dict[str, Any]], limit: int = 3) -> list[str]:
    have: set[str] = set()
    for card in cards:
        have.update(_as_list(card.get("completion_criteria")))
    picked = [_CRITERIA[key] for key in _CRITERIA_RANK if key in have]
    return picked[:limit]


def _count_of(cards: list[dict[str, Any]]) -> str:
    for card in cards:
        count = _clean(card.get("session_practice_count"))
        if count:
            return count
    return ""


def _relevant_missing(card: dict[str, Any]) -> list[str]:
    missing = _as_list(card.get("note_missing_items"))
    focus = {_clean(x) for x in _as_list(card.get("session_focus_items"))}
    return [
        item
        for item in missing
        if item not in focus
        and any(part and (part in item or item in part) for part in focus)
    ][:2]


def _primary_kinds(card: dict[str, Any], slot: str) -> list[str]:
    kinds = _types(card)
    if slot == "foundation":
        return []
    order = ("choose_method", "calculate", "prove", "distinguish", "apply", "mixed", "recall")
    prefer = [key for key in order if key in kinds]
    if slot == "core":
        prefer = [key for key in prefer if key != "recall"] or prefer
    if "choose_method" in prefer and "calculate" in prefer:
        prefer = ["choose_method", "calculate"] + [
            key for key in prefer if key not in {"choose_method", "calculate", "apply"}
        ]
    if "prove" in prefer:
        prefer = [key for key in prefer if key != "apply"]
    return prefer[:2]


def _merged_actions(cards: list[dict[str, Any]], slot: str) -> list[str]:
    kinds: list[str] = []
    focus: list[str] = []
    for card in cards:
        for key in _primary_kinds(card, slot):
            if key not in kinds:
                kinds.append(key)
        focus.extend(_as_list(card.get("session_focus_items")))
    focus = _uniq(focus, 4)
    names = _join([_clean(c.get("name")) for c in cards])
    count = _count_of(cards)
    actions: list[str] = []
    if "choose_method" in kinds and "calculate" in kinds:
        text = f"做{names}相关题时，先判断方法再做完"
        if focus:
            text += "，抓住：" + "、".join(focus[:3])
        if count:
            text += f"；完成 {count} 题"
        actions.append(text)
        kinds = [key for key in kinds if key not in {"choose_method", "calculate"}]
    for key in kinds:
        template = _ACTION_TEMPLATES.get(key)
        if not template:
            continue
        text = template.format(names=names)
        if focus and key in {"calculate", "prove", "apply", "mixed"}:
            text += "，抓住：" + "、".join(focus[:3])
        if count and key in {"calculate", "prove", "apply", "choose_method", "mixed"}:
            text += f"；完成 {count} 题"
        actions.append(text)
    return _uniq(actions, 2)


def _focus_line(cards: list[dict[str, Any]]) -> str:
    bits: list[str] = []
    for card in cards:
        name = _clean(card.get("name"))
        focus = _as_list(card.get("session_focus_items"))
        bits.append(f"{name}（{'、'.join(focus[:2])}）" if focus else name)
    return "本轮抓住：" + "、".join(bits)


def _critical_notes(cards: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for card in cards:
        name = _clean(card.get("name"))
        if _clean(card.get("session_error_signal")):
            focus = _as_list(card.get("session_focus_items"))
            notes.append(
                f"做{name}时先核限制"
                + (f"，尤其是{'、'.join(focus[:2])}" if focus else "")
            )
        if _clean(card.get("session_special_requirement")) == "writing":
            notes.append(f"{name}按完整书写落笔：条件、推理、结论都要有")
    return _uniq(notes, 2)


def _group_title(group: list[dict[str, Any]]) -> str:
    if len(group) == 1:
        return _clean(group[0].get("name"))
    topic = _clean(group[0].get("topic"))
    return topic or _clean(group[0].get("name"))


def _build_foundation(cards: list[dict[str, Any]]) -> dict[str, Any]:
    group = _foundation_cards(cards)
    confirm: list[str] = []
    for card in group:
        label = _clean(card.get("name"))
        items = _as_list(card.get("session_focus_items")) or _as_list(card.get("knowledge_items"))
        confirm.append(
            f"{label}：确认{'、'.join(items[:2])}" if items else f"{label}：能复述定义并说出一条限制"
        )
    return {
        "goal": "后面核心内容会直接用到这些定义和前提，先快速确认，不必重学整章。",
        "count": len(confirm),
        "sections": [
            {"type": "quick_check", "title": "快速确认", "items": _uniq(confirm, 6)},
            {
                "type": "pass_criteria",
                "title": "过关线",
                "items": ["能开口复述这些定义", "能指出一条后续会用到的限制条件"],
            },
        ]
        if confirm
        else [],
    }


def _build_core(cards: list[dict[str, Any]]) -> dict[str, Any]:
    cores = [c for c in cards if c.get("session_priority") == "S"]
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for card in cores:
        key = (_clean(card.get("topic")) or "核心", _family(card))
        buckets.setdefault(key, []).append(card)
    sections: list[dict[str, Any]] = []
    for group in buckets.values():
        notes = _critical_notes(group)
        sections.append(
            {
                "type": "task_group",
                "title": _group_title(group),
                "focus": _focus_line(group),
                "tasks": _merged_actions(group, "core"),
                "pass_criteria": _pick_criteria(group, 3),
                "reminder": "；".join(notes) or None,
            }
        )
    return {
        "goal": "把老师点名的核心块练到会判断、会做、会变式。",
        "count": len(sections),
        "sections": sections,
    }


def _build_specials(cards: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    specials = [c for c in cards if c.get("session_priority") == "A"]
    buckets: dict[str, list[dict[str, Any]]] = {}
    leftover: list[dict[str, Any]] = []
    for card in specials:
        family = _family(card)
        writing = _clean(card.get("session_special_requirement")) == "writing"
        if family == "prove" or writing:
            buckets.setdefault("prove", []).append(card)
        elif family in {"apply", "calc"}:
            buckets.setdefault(family, []).append(card)
        else:
            leftover.append(card)
    if leftover and not buckets:
        buckets["recall"] = leftover
        leftover = []
    sections: list[dict[str, Any]] = []
    for family, group in buckets.items():
        require: list[str] = []
        if any(_clean(c.get("session_special_requirement")) == "writing" for c in group):
            require.extend(["条件写完整", "关键推理不跳步", "最终结论明确"])
        sections.append(
            {
                "type": "special_training",
                "title": _FAMILY_SPECIAL.get(family, "重点专项"),
                "focus": _focus_line(group),
                "tasks": (_merged_actions(group, "special") or [_focus_line(group)]) + require,
                "pass_criteria": _pick_criteria(group, 3),
            }
        )
    return (
        {
            "goal": "单独练透需要完整流程的重点能力，不和高频核心训练混在一起。",
            "count": len(sections),
            "sections": sections,
        },
        leftover,
    )


def _confused_pairs(cards: list[dict[str, Any]]) -> list[str]:
    names = {_clean(c.get("name")) for c in cards}
    out: list[str] = []
    for card in cards:
        src = _clean(card.get("name"))
        for rel in card.get("related_points") or []:
            if not isinstance(rel, dict) or str(rel.get("relation") or "") != "easily_confused":
                continue
            dst = _clean(rel.get("name"))
            if dst in names:
                out.append(f"{src} 与 {dst}")
    return _uniq(out, 5)


def _build_sweep(cards: list[dict[str, Any]], leftover: list[dict[str, Any]]) -> dict[str, Any]:
    targets = [c for c in cards if c.get("session_priority") in {"S", "A"}] + leftover
    concept = _confused_pairs(targets)
    concept_names: list[str] = [_clean(c.get("name")) for c in leftover]
    condition_names: list[str] = []
    method_names: list[str] = []
    writing_names: list[str] = []
    missing_items: list[str] = []
    for card in targets:
        name = _clean(card.get("name"))
        risks = set(_as_list(card.get("risk_tags")))
        if "concept_confusion" in risks:
            concept_names.append(name)
        if risks & {"condition_check", "formula_misuse", "boundary_case"} or _clean(
            card.get("session_error_signal")
        ):
            condition_names.append(name)
        if risks & {"method_selection", "calculation_error"}:
            method_names.append(name)
        if "proof_format" in risks or _clean(card.get("session_special_requirement")) == "writing":
            writing_names.append(name)
        missing_items.extend(_relevant_missing(card))
    concept_items = list(concept)
    if concept_names:
        concept_items.append("分清容易混淆的概念：" + _join(concept_names))
    method_items: list[str] = []
    if condition_names:
        method_items.append("使用前核适用条件和边界：" + _join(condition_names))
    if method_names:
        method_items.append("多种做法并存时，先说明选择依据：" + _join(method_names))
    writing_items: list[str] = []
    if writing_names:
        writing_items.append("把书写和步骤走完整：" + _join(writing_names))
    writing_items.extend(f"把「{item}」独立走通一遍，确保能写出来" for item in _uniq(missing_items, 3))
    groups = [
        {"type": "risk_group", "title": "概念辨析", "items": _uniq(concept_items, 5)},
        {"type": "risk_group", "title": "条件 / 方法", "items": _uniq(method_items, 5)},
        {"type": "risk_group", "title": "书写 / 流程", "items": _uniq(writing_items, 5)},
    ]
    filled = [g for g in groups if g["items"]]
    return {
        "goal": "考前集中检查最容易丢分的地方，不再重新讲知识。",
        "count": len(filled),
        "sections": filled,
    }


def _pack_card(spec: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    sections = list(payload.get("sections") or [])
    count = int(payload.get("count") or 0)
    return {
        "id": spec["id"],
        "order": spec["order"],
        "title": spec["title"],
        "subtitle": _clip(spec["subtitle"], 35),
        "summary": _clip(spec["summary"], 45),
        "items_count": count,
        "count_label": f"{count} {spec['unit']}",
        "kind": spec["kind"],
        "detail": {
            "goal": payload.get("goal") or spec["empty_goal"],
            "sections": sections,
        },
    }


def build_action_plan(
    cards: list[dict[str, Any]],
    teacher: str,
    unmatched: list[str] | None = None,
) -> dict[str, Any]:
    del teacher, unmatched
    foundation = _build_foundation(cards)
    core = _build_core(cards)
    special, leftover = _build_specials(cards)
    sweep = _build_sweep(cards, leftover)
    payloads = {
        "foundation": foundation,
        "core": core,
        "special": special,
        "sweep": sweep,
    }
    packed = [_pack_card(spec, payloads[spec["kind"]]) for spec in _CARD_SPECS]
    return {
        "route": [card["title"] for card in packed],
        "phases": packed,
        "strategy": [],
        "uncertain_quotes": [],
    }


__all__ = ["build_action_plan"]
