"""checklist 展示：复习重点分布、导图、关系图、卡片、行动清单。"""
from __future__ import annotations

import json
from html import escape
from typing import Any

from .mindmap import build_checklist_mindmap_outline
from .select import _as_list, _clean

_GRADE = {"S": "核心", "A": "重点", "B": "简要", "C": "补充"}
_STAR = {"S": 5, "A": 4, "B": 3, "C": 2}
_GRADE_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3}
_GRADE_VALUE = {"S": 45, "A": 30, "B": 18, "C": 8}
_REL = {
    "alternative": "替代",
    "used_with": "配合",
    "easily_confused": "易混",
    "derived_from": "推导",
    "prerequisite": "前置",
}


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value or "") or default)
    except (TypeError, ValueError):
        return default


def _review_value(card: dict[str, Any]) -> int:
    """展示用复习价值，不影响 checklist 的实际分档。"""
    grade = str(card.get("session_priority") or "B")
    importance = max(1, min(5, _as_int(card.get("importance"), 3)))
    difficulty = max(1, min(5, _as_int(card.get("difficulty"), 3)))
    emphasis = max(0, min(3, _as_int(card.get("session_emphasis"), 0)))
    exam = {"none": 0, "weak": 5, "medium": 10, "strong": 18}.get(
        str(card.get("session_exam_signal") or card.get("exam_signal") or "none"),
        0,
    )
    missing = min(12, len(_as_list(card.get("note_missing_items"))) * 4)
    teacher = 8 if _as_list(card.get("session_quotes")) else 0
    prereq = 6 if card.get("_prereq_of") else 0
    return max(
        1,
        _GRADE_VALUE.get(grade, 12)
        + importance * 7
        + difficulty * 2
        + emphasis * 7
        + exam
        + missing
        + teacher
        + prereq,
    )


def _review_reason(card: dict[str, Any]) -> str:
    parts: list[str] = []
    if _as_list(card.get("session_quotes")):
        parts.append("老师点名")
    if _as_int(card.get("session_emphasis")) >= 2:
        parts.append("明确强调")
    sig = str(card.get("session_exam_signal") or card.get("exam_signal") or "none")
    if sig in {"medium", "strong"}:
        parts.append("考试信号")
    if _as_int(card.get("importance"), 3) >= 4:
        parts.append(f"重要性{_as_int(card.get('importance'), 3)}")
    if card.get("_prereq_of"):
        parts.append("前置补齐")
    if _as_list(card.get("note_missing_items")):
        parts.append("笔记缺项")
    return " / ".join(parts[:3]) or "结构复习"


def _make_leaf(card: dict[str, Any]) -> dict[str, Any]:
    kid = _clean(card.get("id")) or _clean(card.get("kp_id")) or _clean(card.get("name"))
    name = _clean(card.get("name")) or "未命名"
    chapter = _clean(card.get("chapter")) or "未分章"
    topic = _clean(card.get("topic")) or chapter
    grade = str(card.get("session_priority") or "B")
    value = _review_value(card)
    return {
        "id": kid,
        "name": name,
        "value": value,
        "ratio": 0.0,
        "depth": 3,
        "parent_id": f"topic::{chapter}::{topic}",
        "source_node_ids": [kid],
        "aggregation_type": "none",
        "session_priority": grade if grade in _GRADE else "B",
        "reason": _review_reason(card),
        "chapter": chapter,
        "topic": topic,
        "children": [],
    }


def _parent_priority(children: list[dict[str, Any]]) -> str:
    grades = [str(c.get("session_priority") or "B") for c in children]
    return min(grades or ["B"], key=lambda g: _GRADE_ORDER.get(g, 9))


def _rollup_node(
    parent: dict[str, Any],
    children: list[dict[str, Any]],
    *,
    aggregation_type: str,
    name: str | None = None,
) -> dict[str, Any]:
    value = sum(float(c.get("value") or 0) for c in children)
    source_ids: list[str] = []
    reasons: list[str] = []
    for child in children:
        for sid in child.get("source_node_ids") or []:
            if sid not in source_ids:
                source_ids.append(str(sid))
        reason = _clean(child.get("reason"))
        if reason and reason not in reasons:
            reasons.append(reason)
    return {
        "id": f"{aggregation_type}::{parent.get('id')}::{'|'.join(source_ids[:6])}",
        "name": name or _clean(parent.get("name")) or "知识块",
        "value": value,
        "ratio": 0.0,
        "depth": parent.get("depth", 1),
        "parent_id": parent.get("parent_id") or "",
        "source_node_ids": source_ids,
        "aggregation_type": aggregation_type,
        "session_priority": _parent_priority(children),
        "reason": " / ".join(reasons[:2]) or "语义回卷",
        "chapter": _clean(parent.get("chapter")) or _clean(parent.get("name")),
        "topic": _clean(parent.get("topic")) or "",
        "children": children,
    }


def _build_review_tree(cards: list[dict[str, Any]]) -> dict[str, Any]:
    root = {"id": "root", "name": "本次复习", "depth": 0, "children": []}
    chapters: dict[str, dict[str, Any]] = {}
    topics: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        if str(card.get("session_priority") or "") == "C":
            continue
        leaf = _make_leaf(card)
        chapter = leaf["chapter"]
        topic = leaf["topic"]
        ch = chapters.get(chapter)
        if ch is None:
            ch = {
                "id": f"chapter::{chapter}",
                "name": chapter,
                "depth": 1,
                "parent_id": "root",
                "chapter": chapter,
                "topic": "",
                "children": [],
            }
            chapters[chapter] = ch
            root["children"].append(ch)
        tp_key = (chapter, topic)
        tp = topics.get(tp_key)
        if tp is None:
            tp = {
                "id": f"topic::{chapter}::{topic}",
                "name": topic,
                "depth": 2,
                "parent_id": ch["id"],
                "chapter": chapter,
                "topic": topic,
                "children": [],
            }
            topics[tp_key] = tp
            ch["children"].append(tp)
        tp["children"].append(leaf)

    def fill(node: dict[str, Any]) -> float:
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        if children:
            value = sum(fill(child) for child in children)
            node["value"] = value
            node["source_node_ids"] = [
                sid
                for child in children
                for sid in (child.get("source_node_ids") or [])
            ]
            node["session_priority"] = _parent_priority(children)
            node["reason"] = "语义回卷"
            return value
        return float(node.get("value") or 0)

    fill(root)
    return root


def _semantic_rollup(root: dict[str, Any]) -> list[dict[str, Any]]:
    total = float(root.get("value") or 0) or 1.0
    candidates = list(root.get("children") or [])
    target_min, target_max = 4, 8
    max_slice_ratio, min_slice_ratio = 0.45, 0.05
    max_expand_count = 20

    while True:
        expandable: list[tuple[float, dict[str, Any]]] = []
        for node in candidates:
            children = [c for c in node.get("children") or [] if isinstance(c, dict)]
            if not children:
                continue
            ratio = float(node.get("value") or 0) / total
            if len(candidates) < target_min or ratio > max_slice_ratio:
                score = ratio * 100 + len(children)
                expandable.append((score, node))
        if not expandable:
            break
        expandable.sort(key=lambda item: -item[0])
        node = expandable[0][1]
        children = [c for c in node.get("children") or [] if isinstance(c, dict)]
        if len(candidates) - 1 + len(children) > max_expand_count:
            break
        candidates.remove(node)
        candidates.extend(children)

    while len(candidates) > target_max:
        small = [
            node for node in candidates
            if float(node.get("value") or 0) / total < min_slice_ratio
        ]
        if not small:
            break
        groups: dict[str, list[dict[str, Any]]] = {}
        for node in small:
            groups.setdefault(str(node.get("parent_id") or ""), []).append(node)
        parent_id, group = max(
            groups.items(),
            key=lambda item: (len(item[1]), sum(float(n.get("value") or 0) for n in item[1])),
        )
        if not group:
            break
        parent = _find_tree_node(root, parent_id) or {
            "id": parent_id,
            "name": "补充知识块",
            "depth": 1,
            "parent_id": "root",
        }
        for node in group:
            if node in candidates:
                candidates.remove(node)
        siblings = [
            node for node in candidates
            if str(node.get("parent_id") or "") == parent_id
        ]
        aggregation = "rollup" if not siblings else "partial_rollup"
        name = _clean(parent.get("name")) if aggregation == "rollup" else f"{_clean(parent.get('name'))}·其余"
        candidates.append(_rollup_node(parent, group, aggregation_type=aggregation, name=name))

    while len(candidates) > target_max:
        candidates.sort(key=lambda n: float(n.get("value") or 0))
        group = candidates[:2]
        parent_id = str(group[0].get("parent_id") or "")
        parent = _find_tree_node(root, parent_id) or {
            "id": parent_id,
            "name": _clean(group[0].get("chapter")) or "补充知识块",
            "depth": 1,
            "parent_id": "root",
        }
        for node in group:
            candidates.remove(node)
        candidates.append(
            _rollup_node(parent, group, aggregation_type="partial_rollup", name=f"{_clean(parent.get('name'))}·其余")
        )

    for node in candidates:
        node["ratio"] = round(float(node.get("value") or 0) / total, 4)
    return sorted(
        candidates,
        key=lambda n: (_GRADE_ORDER.get(str(n.get("session_priority") or ""), 9), -float(n.get("value") or 0)),
    )


def _find_tree_node(node: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    if str(node.get("id") or "") == node_id:
        return node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found = _find_tree_node(child, node_id)
            if found is not None:
                return found
    return None


def _review_overview(cards: list[dict[str, Any]]) -> dict[str, Any]:
    root = _build_review_tree(cards)
    items = _semantic_rollup(root) if root.get("children") else []
    bar_items = sorted(
        items,
        key=lambda n: (_GRADE_ORDER.get(str(n.get("session_priority") or ""), 9), -float(n.get("value") or 0)),
    )[:12]
    return {
        "root": {"id": root.get("id"), "name": root.get("name")},
        "metric": "review_value",
        "total_value": root.get("value") or 0,
        "items": items,
        "bar_items": bar_items,
        "treemap": {"items": items},
    }


def draft_from_context(approved_context: str) -> dict[str, Any]:
    blob = approved_context or ""
    for marker in ("已批准复习清单草稿：", "已批准checklist草稿："):
        if marker in blob:
            blob = blob.split(marker, 1)[1]
            break
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def importance_stars(card: dict[str, Any]) -> str:
    grade = str(card.get("session_priority") or "C")
    filled = _STAR.get(grade, 2)
    try:
        catalog = int(str(card.get("importance") or 0) or 0)
    except (TypeError, ValueError):
        catalog = 0
    if catalog >= filled:
        filled = min(5, catalog)
    filled = max(1, min(5, filled))
    return "★" * filled + "☆" * (5 - filled)


def _grade_label(card: dict[str, Any]) -> str:
    return _GRADE.get(str(card.get("session_priority") or ""), "简要")


def _draft_has_teacher(draft: dict[str, Any], has_teacher: bool | None = None) -> bool:
    if has_teacher is not None:
        return bool(has_teacher)
    if "has_teacher_focus" in draft:
        return bool(draft.get("has_teacher_focus"))
    return any(
        _as_list(card.get("session_quotes"))
        for card in (draft.get("cards") or [])
        if isinstance(card, dict)
    )


def _nav_groups(cards: list[dict[str, Any]], *, has_teacher: bool) -> dict[str, list[dict[str, Any]]]:
    """没传老师重点时，C 档并进主表，不再单独「补充」表/列表。"""
    focus = [c for c in cards if c.get("session_priority") in {"S", "A"}]
    brief = [c for c in cards if c.get("session_priority") == "B"]
    extra = [c for c in cards if c.get("session_priority") == "C"]
    if has_teacher:
        main = [c for c in cards if c.get("session_priority") in {"S", "A", "B"}]
        return {"focus": focus, "brief": brief, "extra": extra, "main": main}
    return {"focus": focus, "brief": brief, "extra": [], "main": list(cards)}


def build_checklist_markdown(draft: dict[str, Any], *, has_teacher: bool | None = None) -> str:
    course = _clean(draft.get("course")) or "复习清单"
    cards = [c for c in (draft.get("cards") or []) if isinstance(c, dict)]
    lines = [f"# {course} · 复习清单", ""]
    if not cards:
        lines.append("没有可复习的知识点。请先运行 catalog / 资料入库；若提供了老师重点，请确认文本能对上目录名称。")
        return "\n".join(lines)

    groups = _nav_groups(cards, has_teacher=_draft_has_teacher(draft, has_teacher))
    focus, brief, extra, main_cards = groups["focus"], groups["brief"], groups["extra"], groups["main"]
    # 结构总览数据（md 不再展示文本表；章节复习权重补充进「三、复习策略」）
    overview = _review_overview(main_cards)
    lines.extend(["## 一、全局导航", ""])
    lines.extend(["| 优先级 | 知识点 | 重要程度 | 所属章节 |", "| --- | --- | --- | --- |"])
    for card in main_cards:
        lines.append(
            f"| {_grade_label(card)} | {_clean(card.get('name'))} | {importance_stars(card)} | {_clean(card.get('chapter')) or '—'} |"
        )
    if extra:
        lines.extend(["", "**补充**（老师未重点点、但知识结构中需要了解的）", "", "| 知识点 | 重要程度 | 所属章节 |", "| --- | --- | --- |"])
        for card in extra:
            lines.append(
                f"| {_clean(card.get('name'))} | {importance_stars(card)} | {_clean(card.get('chapter')) or '—'} |"
            )
    outline = draft.get("mindmap_outline") or build_checklist_mindmap_outline(draft, cards)
    lines.extend(["", "### 1. 思维导图", "", outline, "", "### 2. 考点知识图谱", ""])
    for src, rel, dst in _edges(cards):
        lines.append(f"- {src} —{rel}→ {dst}")

    lines.extend(["", "## 二、知识点", ""])
    for card in focus:
        facts = _as_list(card.get("key_facts"))[:6]
        steps = _as_list(card.get("method_steps"))[:6]
        pits = _as_list(card.get("pitfalls"))[:4]
        lines.append(f"### {_clean(card.get('name'))}  （{_grade_label(card)} · {importance_stars(card)}）")
        lines.append(f"- 考法预判：{_math_text(card.get('exam_preview'))}")
        if facts:
            lines.append("- 必须先会：")
            lines.extend(f"  - {_math_text(item)}" for item in facts)
        lines.append(f"- 知识点讲解：{_math_text(card.get('explain'))}")
        if steps:
            lines.append("- 方法步骤：")
            lines.extend(f"  {i}. {_math_text(step)}" for i, step in enumerate(steps, start=1))
        if pits:
            lines.append("- 易错提醒：")
            lines.extend(f"  - {_math_text(p)}" for p in pits)
        lines.extend(_trace_markdown(card))
        lines.append("")
    if brief:
        lines.append("### 简要过一下")
        lines.append("")
        for card in brief:
            lines.append(
                f"- {_clean(card.get('name'))}（{importance_stars(card)}）："
                f"{_clean(card.get('exam_preview')) or '知道定义和一条限制即可'}"
            )
        lines.append("")
    if extra:
        lines.append("### 补充")
        lines.append("")
        for card in extra:
            kb_src = ""
            for ev in (_trace_pack(card).get("kb") or [])[:1]:
                src = _clean(ev.get("source")) or _clean(ev.get("excerpt"))[:40]
                if src:
                    kb_src = f"　溯源：{src}"
            lines.append(
                f"- {_clean(card.get('name'))}（{importance_stars(card)}）："
                f"{_clean(card.get('exam_preview')) or '结构了解即可'}{kb_src}"
            )
        lines.append("")

    lines.extend(_strategy_markdown(draft, overview))
    lines.extend(_action_markdown(draft))
    return "\n".join(lines).strip() + "\n"


def _action_cards(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (draft.get("phases") or []) if isinstance(p, dict) and p.get("id")]


def _strategy_cards(draft: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [
        c for c in (draft.get("cards") or []) if isinstance(c, dict) and _clean(c.get("name"))
    ]
    return sorted(cards, key=_strategy_sort_key)


def _strategy_sort_key(c: dict[str, Any]) -> tuple[int, int, int, str]:
    grade = str(c.get("session_priority") or "B")
    imp = max(1, min(5, _as_int(c.get("importance"), 3)))
    diff = max(1, min(5, _as_int(c.get("difficulty"), 3)))
    exam = {"none": 0, "weak": 1, "medium": 2, "strong": 3}.get(
        str(c.get("session_exam_signal") or c.get("exam_signal") or "none"),
        0,
    )
    teacher = 1 if _as_list(c.get("session_quotes")) else 0
    prereq = 1 if c.get("prerequisites") or c.get("_prereq_of") else 0
    value = _GRADE_VALUE.get(grade, 12) + imp * 8 + exam * 8 + teacher * 6 + prereq * 4
    return (-value, diff, -imp, _clean(c.get("name")))


def _matrix_bucket(card: dict[str, Any]) -> tuple[str, str]:
    imp = max(1, min(5, _as_int(card.get("importance"), 3)))
    diff = max(1, min(5, _as_int(card.get("difficulty"), 3)))
    imp_key = "high" if imp >= 4 else "mid" if imp == 3 else "low"
    diff_key = "hard" if diff >= 4 else "easy"
    return imp_key, diff_key


def _names(cards: list[dict[str, Any]], limit: int = 5) -> list[str]:
    out: list[str] = []
    for card in cards:
        name = _clean(card.get("name"))
        if name and name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out


def _strategy_matrix(cards: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    matrix: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for card in cards:
        matrix.setdefault(_matrix_bucket(card), []).append(card)
    return matrix


def _stage(
    title: str,
    cards: list[dict[str, Any]],
    why: str,
    action: str,
    check: str,
) -> dict[str, Any] | None:
    names = _names(cards, 6)
    if not names:
        return None
    return {"title": title, "names": names, "why": why, "action": action, "check": check}


def _strategy_stages(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix = _strategy_matrix(cards)
    stages: list[dict[str, Any]] = []
    easy_core = matrix.get(("high", "easy"), [])
    hard_core = matrix.get(("high", "hard"), [])
    easy_mid = matrix.get(("mid", "easy"), []) + matrix.get(("low", "easy"), [])
    hard_mid = matrix.get(("mid", "hard"), [])
    hard_tail = matrix.get(("low", "hard"), [])
    prereq = [c for c in cards if c.get("prerequisites") or c.get("_prereq_of")]
    missing = [c for c in cards if _as_list(c.get("note_missing_items"))]
    pitfalls = [
        c for c in cards
        if _as_list(c.get("pitfalls")) or _clean(c.get("session_error_signal"))
    ]
    for item in (
        _stage(
            "先拿分",
            easy_core,
            "重要度高、难度不高，最适合先建立信心和基础分。",
            "每个点按“定义/公式一句话 → 适用条件 → 一个典型问法 → 一个易错点”快速闭卷复述。",
            "能不看卡片写出核心结论，并说出至少一个使用条件。",
        ),
        _stage(
            "攻核心",
            hard_core,
            "重要且难，是本轮真正拉开差距的部分。",
            "拆成“结论 → 推导/步骤 → 条件 → 变形题入口”四栏，逐点慢推，不要只背结果。",
            "能独立写出主公式或证明骨架，并解释每一步为什么成立。",
        ),
        _stage(
            "快速补齐",
            easy_mid,
            "难度不高但容易散落，适合用短时间扫完，避免丢基础分。",
            "用对比表整理定义、符号、适用范围和常见问法，只保留能直接用于答题的句子。",
            "看到题干能判断是否相关，能说出定义和一条限制。",
        ),
        _stage(
            "抓框架",
            hard_mid,
            "有一定重要性但难度偏高，不适合一开始硬啃。",
            "先抓定义、关键结论、适用条件和一条典型问法；复杂证明先画出结构，不急着补细节。",
            "能说清它解决什么问题，并知道遇到题时从哪一步开始。",
        ),
        _stage(
            "补洞复查",
            prereq + missing + pitfalls,
            "这些点牵涉前置、笔记缺项或易错边界，不补会影响后面的题。",
            "把缺项补到对应卡片里；每张卡最后写一个“我最可能错在哪里”的反例或边界条件。",
            "能指出前置关系，且能用易错点反查自己的答案。",
        ),
        _stage(
            "最后兜底",
            hard_tail,
            "难度偏高但当前优先级没那么靠前，时间紧时不宜抢占核心时间。",
            "只抓定义、关键结论、适用条件和一条典型问法；复杂推导先留标记。",
            "至少能识别题型，不把它和核心点混淆。",
        ),
    ):
        if item:
            stages.append(item)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for stage in stages:
        key = "、".join(stage["names"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(stage)
    return unique[:6]


def _strategy_markdown(draft: dict[str, Any], overview: dict[str, Any] | None = None) -> list[str]:
    """复习路线：用矩阵和阶段卡片表达，不消耗额外 LLM token。"""
    del overview
    cards = _strategy_cards(draft)
    if not cards:
        return []
    matrix = _strategy_matrix(cards)
    stages = _strategy_stages(cards)
    lines = ["## 三、复习策略", ""]
    lines.extend(["### 优先级矩阵", ""])
    labels = {
        ("high", "easy"): "先拿下",
        ("high", "hard"): "集中攻克",
        ("mid", "easy"): "快速扫过",
        ("mid", "hard"): "抓框架",
        ("low", "easy"): "有空再看",
        ("low", "hard"): "最后兜底",
    }
    rows = [("重要高", "high"), ("重要中", "mid"), ("重要低", "low")]
    lines.extend(["|  | 难度低/中 | 难度高 |", "| --- | --- | --- |"])
    for title, imp_key in rows:
        cells: list[str] = []
        for diff_key in ("easy", "hard"):
            names = _names(matrix.get((imp_key, diff_key), []), 4)
            label = labels[(imp_key, diff_key)]
            cells.append(f"{label}：" + ("、".join(names) if names else "—"))
        lines.append(f"| {title} | {cells[0]} | {cells[1]} |")
    if stages:
        lines.extend(["", "### 今日复习路线", ""])
        for i, stage in enumerate(stages, start=1):
            lines.append(f"#### {i}. {stage['title']}")
            lines.append(f"- 知识点：{'、'.join(stage['names'])}")
            lines.append(f"- 为什么这样排：{stage['why']}")
            lines.append(f"- 怎么复习：{stage['action']}")
            lines.append(f"- 过关标准：{stage['check']}")
            lines.append("")
    lines.append("")
    return lines


def _render_task_object(task: dict[str, Any], *, markdown: bool) -> str:
    action = _clean(task.get("action"))
    target = _clean(task.get("target"))
    output = _clean(task.get("output"))
    check = _clean(task.get("check"))
    source = _clean(task.get("source_label"))
    head = f"{action}{target}" if action and target else action or target
    parts = [head]
    if output:
        parts.append(f"产出：{output}")
    if check:
        parts.append(f"检查：{check}")
    text = "；".join(part for part in parts if part)
    if source:
        text += f"（依据：{source}）"
    return text if markdown else escape(text, quote=False)


def _render_section_tasks(section: dict[str, Any], *, markdown: bool = True) -> list[str]:
    task_objects = [
        task for task in (section.get("task_objects") or []) if isinstance(task, dict)
    ]
    if task_objects:
        return [_render_task_object(task, markdown=markdown) for task in task_objects]
    return [str(x) for x in (section.get("tasks") or []) if str(x).strip()]


def _action_markdown(draft: dict[str, Any]) -> list[str]:
    cards = _action_cards(draft)
    lines = ["## 四、行动清单", ""]
    if cards:
        lines.append(" → ".join(f"{c.get('order')} {c.get('title')}" for c in cards))
        lines.append("")
        for card in cards:
            lines.append(f"### {card.get('order')}. {card.get('title')}")
            if card.get("subtitle"):
                lines.append(card.get("subtitle"))
            if card.get("summary"):
                lines.append(f"摘要：{card.get('summary')}")
            if card.get("count_label"):
                lines.append(f"（{card.get('count_label')}）")
            lines.append("")
        lines.append("---")
        lines.append("")
    for card in cards:
        detail = card.get("detail") if isinstance(card.get("detail"), dict) else {}
        lines.append(f"### 展开 · {card.get('title')}")
        lines.append("")
        if detail.get("goal"):
            lines.append(f"目标：{detail.get('goal')}")
            lines.append("")
        for section in detail.get("sections") or []:
            if not isinstance(section, dict):
                continue
            stype = str(section.get("type") or "")
            title = section.get("title") or ""
            if stype in {"quick_check", "pass_criteria", "risk_group"}:
                if title:
                    lines.append(f"#### {title}")
                rendered_items = _render_section_tasks(section)
                if not rendered_items:
                    rendered_items = [str(x) for x in (section.get("items") or []) if str(x).strip()]
                lines.extend(f"- {item}" for item in rendered_items)
                lines.append("")
                continue
            if title:
                lines.append(f"#### {title}")
            if section.get("focus"):
                lines.append(f"本轮重点：{section.get('focus')}")
            rendered_tasks = _render_section_tasks(section)
            if rendered_tasks:
                lines.append("本次任务：" if stype == "task_group" else "重点训练：")
                lines.extend(f"- {item}" for item in rendered_tasks)
            if section.get("pass_criteria"):
                lines.append("过关线：")
                lines.extend(f"- {item}" for item in section.get("pass_criteria") or [])
            if section.get("reminder"):
                lines.append(f"必要提醒：{section.get('reminder')}")
            lines.append("")
    return lines


def _edges(cards: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    names = {_clean(c.get("name")) for c in cards}
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for card in cards:
        src = _clean(card.get("name"))
        for pre in _as_list(card.get("prerequisites")):
            if pre in names:
                key = (pre, "前置", src)
                if key not in seen:
                    seen.add(key)
                    edges.append(key)
        for rel in card.get("related_points") or []:
            if not isinstance(rel, dict):
                continue
            dst = _clean(rel.get("name"))
            if dst in names:
                label = _REL.get(str(rel.get("relation") or ""), "关联")
                key = (src, label, dst)
                if key not in seen:
                    seen.add(key)
                    edges.append(key)
        for dst in _as_list(card.get("session_related_points")):
            if dst in names and dst != src:
                key = (src, "组合", dst)
                reverse = (dst, "组合", src)
                if key not in seen and reverse not in seen:
                    seen.add(key)
                    edges.append(key)
    return edges


def _graph_payload(cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    for card in cards:
        name = _clean(card.get("name"))
        if not name:
            continue
        facts = _as_list(card.get("key_facts")) or _as_list(card.get("knowledge_items"))
        definition = _clean(card.get("explain")) or "；".join(facts[:4])
        nodes.append(
            {
                "name": name,
                "section": _clean(card.get("topic")) or _grade_label(card),
                "definition": definition[:280],
            }
        )
    edges = [
        {"source": src, "target": dst, "relation": rel}
        for src, rel, dst in _edges(cards)
    ]
    return nodes, edges


def _checks(items: list[str]) -> str:
    return "<ul class=\"ck-check\">" + "".join(
        f"<li>□ {escape(item, quote=False)}</li>" for item in items
    ) + "</ul>"


def _plain_list(items: list[str]) -> str:
    return "<ul class=\"ck-task-list\">" + "".join(
        f"<li><label><input class=\"ck-task-box\" type=\"checkbox\"><span>{item}</span></label></li>" for item in items
    ) + "</ul>"


def _math_text(text: object) -> str:
    r"""Markdown 文本的公式归一化（修复 $ 定界与不成对 \left/\right）。"""
    from tools.ocr.mathmd import normalize_markdown_math

    return normalize_markdown_math(str(text or "")).strip()


def _math_escape(text: object) -> str:
    from tools.ocr.mathmd import normalize_markdown_math

    raw = normalize_markdown_math(str(text or ""))
    return escape(raw, quote=False)


def _section_html(section: dict[str, Any]) -> str:
    stype = str(section.get("type") or "")
    title = escape(str(section.get("title") or ""), quote=False)
    if stype in {"quick_check", "pass_criteria", "risk_group"}:
        items = _render_section_tasks(section, markdown=False)
        if not items:
            items = [escape(str(x), quote=False) for x in (section.get("items") or []) if str(x).strip()]
        if not items:
            return ""
        head = f"<h4>{title}</h4>" if title else ""
        return head + _plain_list(items)
    body = ['<div class="ck-task">']
    if title:
        body.append(f"<strong>{title}</strong>")
    if section.get("focus"):
        body.append(f'<p><b>本轮重点</b> {escape(str(section.get("focus")), quote=False)}</p>')
    tasks = _render_section_tasks(section, markdown=False)
    if tasks:
        label = "本次任务" if stype == "task_group" else "重点训练"
        body.append(
            f"<p><b>{label}</b></p>" + _plain_list(tasks)
        )
    criteria = [str(x) for x in (section.get("pass_criteria") or []) if str(x).strip()]
    if criteria:
        body.append("<p><b>过关线</b></p>" + _checks(criteria))
    if section.get("reminder"):
        body.append(f'<p><b>必要提醒</b> {escape(str(section.get("reminder")), quote=False)}</p>')
    body.append("</div>")
    return "".join(body)


def _strategy_html(draft: dict[str, Any], overview: dict[str, Any] | None = None) -> list[str]:
    del overview
    cards = _strategy_cards(draft)
    if not cards:
        return []
    matrix = _strategy_matrix(cards)
    stages = _strategy_stages(cards)

    def cell(imp_key: str, diff_key: str, label: str) -> str:
        names = _names(matrix.get((imp_key, diff_key), []), 4)
        chips = "".join(f"<span>{escape(name, quote=False)}</span>" for name in names)
        if not chips:
            chips = '<em>—</em>'
        return f"<td><b>{label}</b><div>{chips}</div></td>"

    rows = [
        "<h2>三、复习策略</h2>",
        '<section class="ck-strategy-panel" aria-label="复习策略">',
        '<div class="ck-strategy-head"><span>优先级矩阵</span><em>重要程度 × 难度</em></div>',
        '<table class="ck-priority-matrix">',
        "<thead><tr><th></th><th>难度低/中</th><th>难度高</th></tr></thead>",
        "<tbody>",
        "<tr><th>重要高</th>" + cell("high", "easy", "先拿下") + cell("high", "hard", "集中攻克") + "</tr>",
        "<tr><th>重要中</th>" + cell("mid", "easy", "快速扫过") + cell("mid", "hard", "抓框架") + "</tr>",
        "<tr><th>重要低</th>" + cell("low", "easy", "有空再看") + cell("low", "hard", "最后兜底") + "</tr>",
        "</tbody></table>",
    ]
    if stages:
        rows.extend([
            '<div class="ck-strategy-head ck-strategy-route"><span>今日复习路线</span><em>按学生实际下手顺序</em></div>',
            '<ol class="ck-strategy">',
        ])
    for i, stage in enumerate(stages, start=1):
        chips = "".join(
            f"<span>{escape(name, quote=False)}</span>" for name in stage["names"]
        )
        rows.append(
            "<li>"
            f'<span class="ck-strategy-no">{i:02d}</span>'
            '<div class="ck-strategy-text">'
            f"<h3>{escape(str(stage['title']), quote=False)}</h3>"
            f'<div class="ck-strategy-chips">{chips}</div>'
            f"<p><b>为什么这样排</b> {escape(str(stage['why']), quote=False)}</p>"
            f"<p><b>怎么复习</b> {escape(str(stage['action']), quote=False)}</p>"
            f"<p><b>过关标准</b> {escape(str(stage['check']), quote=False)}</p>"
            "</div>"
            "</li>"
        )
    if stages:
        rows.append("</ol>")
    rows.append("</section>")
    return rows


def _action_html(draft: dict[str, Any]) -> list[str]:
    cards = _action_cards(draft)
    if not cards:
        return []
    rows = [
        "<h2>四、行动清单</h2>",
        '<p class="ck-note" style="margin-bottom:10px">按路线点开卡片看这一阶段要做什么。</p>',
        '<div class="ck-action">',
        '<div class="ck-progress" aria-label="行动清单完成度">',
        '<div class="ck-progress-top"><strong>完成度</strong><span><b data-ck-done>0</b>/<b data-ck-total>0</b> · <b data-ck-percent>0%</b></span></div>',
        '<div class="ck-progress-track"><span data-ck-bar style="width:0%"></span></div>',
        "</div>",
        '<div class="ck-action-grid">',
    ]
    for card in cards:
        cid = escape(str(card.get("id") or ""), quote=True)
        rows.append(
            f'<button type="button" class="ck-stage{" is-on" if card.get("order") == 1 else ""}" data-ck-card="{cid}">'
            f'<span class="ck-stage-no">{escape(str(card.get("order") or ""), quote=False)}</span>'
            f'<span class="ck-stage-title">{escape(str(card.get("title") or ""), quote=False)}</span>'
            f'<span class="ck-stage-sub">{escape(str(card.get("subtitle") or ""), quote=False)}</span>'
            f'<span class="ck-stage-sum">{escape(str(card.get("summary") or ""), quote=False)}</span>'
            f'<span class="ck-stage-count">{escape(str(card.get("count_label") or ""), quote=False)}</span>'
            "</button>"
        )
    rows.append("</div>")
    for card in cards:
        cid = escape(str(card.get("id") or ""), quote=True)
        hidden = "" if card.get("order") == 1 else " hidden"
        detail = card.get("detail") if isinstance(card.get("detail"), dict) else {}
        rows.append(f'<div class="ck-action-detail" data-ck-detail="{cid}"{hidden}>')
        rows.append(f"<h3>{escape(str(card.get('title') or ''), quote=False)}</h3>")
        if detail.get("goal"):
            rows.append(f'<p><b>目标</b> {escape(str(detail.get("goal")), quote=False)}</p>')
        for section in detail.get("sections") or []:
            if isinstance(section, dict):
                html = _section_html(section)
                if html:
                    rows.append(html)
        if not (detail.get("sections") or []):
            rows.append('<p class="ck-note">这一阶段暂无必须单独展开的任务，进入下一张卡片即可。</p>')
        rows.append("</div>")
    rows.append("</div>")
    rows.append(
        """<script>
(function () {
  const root = document.currentScript && document.currentScript.previousElementSibling;
  const box = root && root.classList && root.classList.contains('ck-action')
    ? root
    : document.querySelector('.ck-action');
  if (!box) return;
  const buttons = Array.from(box.querySelectorAll('[data-ck-card]'));
  const panels = Array.from(box.querySelectorAll('[data-ck-detail]'));
  const checks = Array.from(box.querySelectorAll('.ck-task-box'));
  const doneEl = box.querySelector('[data-ck-done]');
  const totalEl = box.querySelector('[data-ck-total]');
  const pctEl = box.querySelector('[data-ck-percent]');
  const barEl = box.querySelector('[data-ck-bar]');
  const updateProgress = () => {
    const total = checks.length;
    const done = checks.filter((item) => item.checked).length;
    const pct = total ? Math.round(done / total * 100) : 0;
    if (doneEl) doneEl.textContent = String(done);
    if (totalEl) totalEl.textContent = String(total);
    if (pctEl) pctEl.textContent = pct + '%';
    if (barEl) barEl.style.width = pct + '%';
  };
  const show = (id) => {
    buttons.forEach((btn) => btn.classList.toggle('is-on', btn.getAttribute('data-ck-card') === id));
    panels.forEach((panel) => {
      const on = panel.getAttribute('data-ck-detail') === id;
      if (on) panel.removeAttribute('hidden');
      else panel.setAttribute('hidden', '');
    });
  };
  buttons.forEach((btn) => {
    btn.addEventListener('click', () => show(btn.getAttribute('data-ck-card')));
  });
  checks.forEach((item) => item.addEventListener('change', updateProgress));
  updateProgress();
})();
</script>"""
    )
    return rows


def _widget_css() -> str:
    return """
.ck-stars{color:#b86a04;letter-spacing:1.5px;font-size:.88rem;white-space:nowrap;}
.ck-quote{margin:8px 0 12px;padding:8px 12px;background:#faf9f6;border-left:3.5px solid #222222;border-radius:2px;color:#222222;font-size:.88rem;font-style:italic;}

/* Knowledge Graph in LaTeX Paper Style */
.lc-kg{margin:12px 0 20px;border:1px solid #222222;border-radius:2px;overflow:hidden;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.03);}
.lc-kg-shell{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,32%);min-height:560px;}
#lc-cy{width:100%;height:560px;background:#ffffff;}
.lc-kg-aside{border-left:1px solid #222222;background:#faf9f6;padding:16px 14px;overflow:auto;}
.lc-kg-aside h3{margin:0 0 8px;font-size:1rem;font-weight:700;color:#111;}
.lc-kg-meta,.lc-kg-ev{color:#555555;font-size:.78rem;line-height:1.6;font-style:italic;}
.lc-kg-label{font-size:.76rem;color:#222222;margin:14px 0 6px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;}
.lc-kg-detail{border:1px solid #d4d0c7;border-radius:2px;padding:12px;background:#ffffff;font-size:.86rem;line-height:1.6;}
.lc-kg-name{font-weight:700;margin-bottom:8px;font-size:.96rem;color:#111;}
.lc-kg-block{margin-top:8px;}
.lc-kg-k{color:#555555;font-size:.74rem;margin-bottom:3px;font-weight:700;}
.lc-kg-rel{margin-top:6px;padding:6px 8px;border:1px solid #e0dcd4;border-radius:2px;background:#faf9f6;}
.lc-kg-chips{display:flex;flex-wrap:wrap;gap:6px;}
.lc-kg-chip{display:inline-block;padding:1px 8px;border-radius:2px;background:#ede9e1;border:1px solid #d4d0c7;font-size:.74rem;color:#222;}
.lc-kg-legend{display:grid;gap:6px;}
.lc-kg-legend-item{display:flex;align-items:center;gap:8px;font-size:.8rem;}
.lc-kg-swatch{width:10px;height:10px;border-radius:2px;}

/* Mindmap in LaTeX Paper Style */
.lc-mm{position:relative;margin:12px 0 20px;border:1px solid #222222;border-radius:2px;overflow:hidden;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.03);}
.lc-mm-bar{display:flex;align-items:center;gap:8px;padding:8px 14px;border-bottom:1px solid #222222;background:#faf9f6;flex-wrap:wrap;}
.lc-mm-bar strong{font-size:.95rem;font-weight:700;color:#111;}
.lc-mm-hint{color:#666666;font-size:.78rem;flex:1 1 180px;font-style:italic;}
.lc-mm-bar button{border:1px solid #333333;background:#ffffff;border-radius:2px;padding:4px 12px;font-size:.8rem;font-family:inherit;font-weight:600;cursor:pointer;transition:all .15s;}
.lc-mm-bar button:hover{background:#eeebe3;}
.lc-mm-bar button.lc-mm-save{background:#111111;color:#ffffff;border-color:#111111;}
.lc-mm-bar button.lc-mm-save:hover{background:#333333;}
.lc-mm-body{display:grid;grid-template-columns:1fr;height:560px;min-height:560px;}
.lc-mm-body.editing{grid-template-columns:minmax(200px,34%) 1fr;}
#lc-mm-editor{display:none;width:100%;height:100%;border:0;border-right:1px solid #222222;padding:12px;resize:none;font:13px/1.6 "Latin Modern Mono",Consolas,monospace;box-sizing:border-box;background:#faf9f6;}
.lc-mm-body.editing #lc-mm-editor{display:block;}
.lc-mm-canvas{position:relative;min-height:560px;height:100%;background:#ffffff;}
#lc-mindmap{position:absolute;inset:0;width:100%;height:100%;display:block;}
.lc-mm-fallback{padding:14px 20px 16px;overflow:auto;height:100%;font-family:inherit;}
.lc-mm-tree{margin:0;padding-left:1.2em;line-height:1.7;}
.lc-mm-tree ul{margin:.2em 0;padding-left:1.1em;}
@media(max-width:860px){.lc-kg-shell{grid-template-columns:1fr}.lc-mm-body.editing{grid-template-columns:1fr}#lc-cy{height:420px}.lc-mm-body,.lc-mm-canvas{height:420px;min-height:420px}}
"""


_SUPPORT_CN = {
    "priority": "优先级",
    "exam_prediction": "考法预判",
    "explanation": "知识点讲解",
    "method_steps": "方法步骤",
    "error_warning": "易错提醒",
}


def _trace_pack(card: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw = card.get("provenance") if isinstance(card.get("provenance"), dict) else {}
    teachers = [e for e in (raw.get("teacher_evidence") or []) if isinstance(e, dict)]
    kb = [e for e in (raw.get("knowledge_evidence") or []) if isinstance(e, dict)]
    notes = [e for e in (raw.get("note_evidence") or []) if isinstance(e, dict)]
    return {"teacher": teachers, "kb": kb, "note": notes}


def _supports_label(ev: dict[str, Any]) -> str:
    labels = [_SUPPORT_CN.get(str(x), "") for x in (ev.get("supports") or [])]
    return " / ".join(x for x in labels if x)


def _prepare_card_evidence(
    card: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    """为卡片关联的所有依据分配连续编号 [1], [2]... 并按字段建立索引。"""
    pack = _trace_pack(card)
    teachers = pack["teacher"]
    kb = pack["kb"]
    notes = pack["note"]
    all_raw = [("teacher", ev) for ev in teachers] + [("kb", ev) for ev in kb] + [("note", ev) for ev in notes]

    field_to_evs: dict[str, list[dict[str, Any]]] = {
        "priority": [],
        "exam_prediction": [],
        "explanation": [],
        "method_steps": [],
        "error_warning": [],
    }

    all_evs: list[dict[str, Any]] = []

    for idx, (kind, ev) in enumerate(all_raw, start=1):
        ev_copy = dict(ev)
        ev_copy["cite_num"] = idx
        ev_copy["kind"] = kind
        supports = [str(x) for x in (ev.get("supports") or []) if str(x)]
        if not supports:
            supports = ["explanation"]
        for sup in supports:
            if sup in field_to_evs:
                field_to_evs[sup].append(ev_copy)
        all_evs.append(ev_copy)

    return field_to_evs, all_evs


def _cite_tags(ev_list: list[dict[str, Any]]) -> str:
    """生成学术论文样式的蓝色高亮引用标签 [1], [2]。"""
    if not ev_list:
        return ""
    seen: set[int] = set()
    tags: list[str] = []
    for ev in ev_list:
        cnum = ev.get("cite_num")
        if not cnum or cnum in seen:
            continue
        seen.add(cnum)
        eid = escape(str(ev.get("evidence_id") or ""), quote=True)
        kind = str(ev.get("kind") or "")
        head = "老师原话" if kind == "teacher" else ("知识库" if kind == "kb" else ("笔记" if kind == "note" else "依据"))
        source = _clean(ev.get("source"))
        label = f"{head}: {source}" if source and kind != "teacher" else head
        tags.append(
            f'<a href="javascript:void(0)" class="ck-cite-ref" data-target-ev="{eid}" title="点击查看出处 [{cnum}] · {escape(label, quote=True)}">[{cnum}]</a>'
        )
    return "".join(tags)


def _evidence_html(kind: str, ev: dict[str, Any]) -> str:
    eid = escape(str(ev.get("evidence_id") or ""), quote=True)
    cnum = ev.get("cite_num") or 1
    supports = " ".join(str(x) for x in (ev.get("supports") or []) if x)
    klass = {"teacher": "ck-ev-teacher", "kb": "ck-ev-kb", "note": "ck-ev-note"}.get(kind, "")
    head = {
        "teacher": "老师原话",
        "kb": "知识库依据",
        "note": "学生笔记",
    }.get(kind, "依据")
    rows = [
        f'<div class="ck-ev {klass}" data-ev="{eid}" data-cite="{cnum}" data-supports="{escape(supports, quote=True)}">',
        f'<div class="ck-ev-k"><a class="ck-ev-cite-tag" href="javascript:void(0);">[{cnum}]</a> <span class="ck-ev-kind-badge">{escape(str(head), quote=False)}</span></div>',
    ]
    if kind == "teacher":
        rows.append(f'<div class="ck-ev-quote">“{_math_escape(_clean(ev.get("text")))}”</div>')
        items = _as_list(ev.get("matched_items"))
        if items:
            rows.append(
                f'<div class="ck-ev-meta">对应：{escape("、".join(items[:4]), quote=False)}</div>'
            )
    else:
        source = _clean(ev.get("source"))
        section = _clean(ev.get("section"))
        if source:
            loc = f"{source}" + (f" · {section}" if section else "")
            rows.append(f'<div class="ck-ev-meta">{escape(loc, quote=False)}</div>')
        excerpt = _clean(ev.get("excerpt"))
        full = _clean(ev.get("full")) or excerpt
        if excerpt:
            rows.append(f'<div class="ck-ev-quote">{_math_escape(excerpt)}</div>')
        if full and full != excerpt:
            rows.append(
                "<details><summary class=\"ck-proof-toggle\">完整片段 ▾</summary>"
                f'<div class="ck-ev-quote">{_math_escape(full)}</div></details>'
            )
    sup = _supports_label(ev)
    if sup:
        rows.append(f'<div class="ck-ev-sup">支撑：{escape(sup, quote=False)}</div>')
    rows.append("</div>")
    return "".join(rows)


def _trace_html(card: dict[str, Any], all_evs: list[dict[str, Any]]) -> str:
    if not all_evs:
        status = ""
        raw = card.get("provenance") if isinstance(card.get("provenance"), dict) else {}
        if raw.get("evidence_status") == "insufficient":
            status = "这条判断缺少直接依据，未编造出处。"
        return f'<div class="ck-ev-empty">{status or "暂无足够依据"}</div>'
    rows = [
        '<div class="ck-provenance-head"><span class="ck-ref-icon">§</span> 来源与证据溯源 (References)</div>',
        '<div class="ck-ev-list">',
    ]
    rows.extend(_evidence_html(str(ev.get("kind") or "kb"), ev) for ev in all_evs)
    rows.append('</div>')
    return "".join(rows)


def _card_html(card: dict[str, Any], card_idx: int = 1) -> str:
    grade = str(card.get("session_priority") or "B")
    brief = grade not in {"S", "A"}
    badge = "ck-s" if grade == "S" else "ck-a" if grade == "A" else "ck-b"
    card_theme_class = "is-s" if grade == "S" else "is-a" if grade == "A" else "is-b"
    thm_type = "Definition" if grade == "S" else "Theorem" if grade == "A" else "Remark"

    field_to_evs, all_evs = _prepare_card_evidence(card)

    facts = _as_list(card.get("key_facts"))[: 3 if brief else 6]
    steps = _as_list(card.get("method_steps"))[: 3 if brief else 6]
    pits = _as_list(card.get("pitfalls"))[: 2 if brief else 4]

    exam_cites = _cite_tags(field_to_evs.get("exam_prediction", []))
    explain_cites = _cite_tags(field_to_evs.get("explanation", []))
    method_cites = _cite_tags(field_to_evs.get("method_steps", []))
    error_cites = _cite_tags(field_to_evs.get("error_warning", []))
    prio_cites = _cite_tags(field_to_evs.get("priority", []))

    name = escape(_clean(card.get("name")), quote=False)

    left = [
        f'<div class="ck-card {card_theme_class}">',
        '<div class="ck-card-header">',
        f'<span class="ck-badge {badge}">{escape(_grade_label(card), quote=False)}</span>',
        f'<span class="ck-stars">{importance_stars(card)}</span> ',
        f'<span class="ck-thm-title"><strong>{thm_type} {card_idx} ({name})</strong></span>',
        f'{prio_cites}',
        '</div>',
        '<div class="ck-field" data-field="exam_prediction">',
        f"<p><b class=\"ck-thm-label\">考法预判.</b> {_math_escape(_clean(card.get('exam_preview')))} {exam_cites}</p></div>",
    ]
    if facts:
        left.append(
            "<div class=\"ck-field\"><p><b class=\"ck-thm-label\">必须先会.</b></p><ul class=\"ck-thm-list\">"
            + "".join(f"<li>{_math_escape(item)}</li>" for item in facts)
            + "</ul></div>"
        )
    left.append(
        '<div class="ck-field" data-field="explanation">'
        f"<p><b class=\"ck-thm-label\">知识点讲解.</b> {_math_escape(_clean(card.get('explain')))} {explain_cites}</p></div>"
    )
    if steps:
        left.append(
            '<div class="ck-field" data-field="method_steps"><p><b class=\"ck-thm-label\">方法步骤.</b> '
            + f'{method_cites}</p><ol class="ck-thm-enum">'
            + "".join(f"<li>{_math_escape(step)}</li>" for step in steps)
            + "</ol></div>"
        )
    if pits:
        left.append(
            '<div class="ck-field" data-field="error_warning"><div class="ck-remark-box"><p><b class=\"ck-thm-label\">易错提醒.</b> '
            + f'{error_cites}</p><ul class="ck-thm-list">'
            + "".join(f"<li>{escape(item, quote=False)}</li>" for item in pits)
            + "</ul></div></div>"
        )
    left.append("</div>")

    return (
        '<div class="ck-review">'
        f'<div class="ck-review-left">{"".join(left)}</div>'
        '<div class="ck-review-rule"></div>'
        f'<div class="ck-review-right">{_trace_html(card, all_evs)}</div>'
        "</div>"
    )


def _trace_markdown(card: dict[str, Any]) -> list[str]:
    pack = _trace_pack(card)
    if not any(pack.values()):
        return []
    lines = ["- 溯源"]
    for ev in pack["teacher"][:3]:
        lines.append(f"  - 老师原话：{_math_text(ev.get('text'))}")
    for ev in pack["kb"][:2]:
        src = _clean(ev.get("source"))
        excerpt = _math_text(ev.get("excerpt"))
        lines.append(f"  - 知识库：{src} — {excerpt}" if src else f"  - 知识库：{excerpt}")
    for ev in pack["note"][:2]:
        lines.append(f"  - 笔记：{_math_text(ev.get('excerpt'))}")
    return lines


# 必须用 raw 字符串：Python '\\[' 写进 HTML 会变成 JS 的 '\['，JS 再把 \[ 读成 [，
# 对易子 [A,B] 就会被当成独立公式块，整行被拆成「如 / =B / + / C」。
_MATHJAX_SCRIPT = r"""<script>
(function () {
  const onReady = () => {
    if (window.__adjustEvidenceFolding) window.__adjustEvidenceFolding();
  };
  if (window.MathJax && window.MathJax.typesetPromise) {
    window.MathJax.typesetPromise().then(onReady);
    return;
  }
  window.MathJax = {
    tex: {inlineMath: [['$', '$'], ['\\(', '\\)']], displayMath: [['$$', '$$'], ['\\[', '\\]']]},
    options: {skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']},
    startup: {
      pageReady: () => {
        return MathJax.startup.defaultPageReady().then(onReady);
      }
    }
  };
  var s = document.createElement('script');
  s.src = 'https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js';
  s.async = true;
  document.head.appendChild(s);
})();
</script>"""


def _trace_script() -> str:
    return """<script>
(function () {
  function adjustEvidenceFolding() {
    const isDesktop = window.innerWidth > 860;
    document.querySelectorAll('.ck-review').forEach((row) => {
      const leftEl = row.querySelector('.ck-review-left');
      const rightEl = row.querySelector('.ck-review-right');
      const listEl = row.querySelector('.ck-ev-list');
      if (!leftEl || !rightEl || !listEl) return;

      // 还原之前已折叠的元素，重新获取自然高度
      const existingDetails = listEl.querySelector('.ck-ev-more');
      if (existingDetails) {
        const itemsInside = Array.from(existingDetails.querySelectorAll('.ck-ev'));
        itemsInside.forEach((ev) => existingDetails.before(ev));
        existingDetails.remove();
      }

      const allEvs = Array.from(listEl.querySelectorAll(':scope > .ck-ev'));
      if (allEvs.length <= 1) return;

      const headEl = rightEl.querySelector('.ck-provenance-head');
      const headHeight = headEl ? headEl.offsetHeight + 14 : 36;
      const leftHeight = leftEl.offsetHeight;

      let totalHeight = headHeight;
      const itemsToFold = [];

      allEvs.forEach((ev, idx) => {
        if (!isDesktop) {
          if (idx >= 3) itemsToFold.push(ev);
          return;
        }
        const evHeight = ev.offsetHeight + 10;
        // 只有当右侧依据累积高度明显超过左侧知识点卡片高度（留 20px 余量）且至少展示了 1 条时，才折叠超出部分
        if (totalHeight + evHeight > leftHeight + 20 && idx >= 1) {
          itemsToFold.push(ev);
        } else {
          totalHeight += evHeight;
        }
      });

      if (itemsToFold.length > 0) {
        const details = document.createElement('details');
        details.className = 'ck-ev-more';
        const summary = document.createElement('summary');
        summary.className = 'ck-proof-toggle';
        summary.innerHTML = `查看更多依据 (${itemsToFold.length}) ▾`;
        details.appendChild(summary);

        itemsToFold[0].before(details);
        itemsToFold.forEach((ev) => details.appendChild(ev));
      }
    });
  }

  window.__adjustEvidenceFolding = adjustEvidenceFolding;

  document.querySelectorAll('.ck-review').forEach((row) => {
    const cites = row.querySelectorAll('.ck-cite-ref');
    const fields = row.querySelectorAll('[data-field]');
    const evs = row.querySelectorAll('.ck-ev');

    const clearHighlights = () => {
      fields.forEach((el) => el.classList.remove('is-on'));
      evs.forEach((el) => el.classList.remove('is-on', 'is-highlighted'));
      cites.forEach((c) => c.classList.remove('is-active'));
    };

    const highlightEv = (targetEvId) => {
      clearHighlights();
      let targetEl = null;
      row.querySelectorAll('.ck-ev').forEach((ev) => {
        if (ev.getAttribute('data-ev') === targetEvId) {
          targetEl = ev;
          const parentDetails = ev.closest('details');
          if (parentDetails) parentDetails.open = true;
          ev.classList.add('is-on', 'is-highlighted');
          ev.style.animation = 'none';
          void ev.offsetHeight;
          ev.style.animation = 'citePulse 1.2s ease';
        }
      });
      cites.forEach((c) => {
        if (c.getAttribute('data-target-ev') === targetEvId) {
          c.classList.add('is-active');
        }
      });
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    };

    cites.forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const targetId = btn.getAttribute('data-target-ev');
        if (targetId) highlightEv(targetId);
      });
    });

    fields.forEach((field) => {
      field.addEventListener('click', (e) => {
        if (e.target.closest('.ck-cite-ref')) return;
        const key = field.getAttribute('data-field') || '';
        clearHighlights();
        field.classList.add('is-on');
        row.querySelectorAll('.ck-ev').forEach((ev) => {
          const bag = ' ' + (ev.getAttribute('data-supports') || '') + ' ';
          if (key && bag.indexOf(' ' + key + ' ') >= 0) {
            const parentDetails = ev.closest('details');
            if (parentDetails) parentDetails.open = true;
            ev.classList.add('is-on');
          }
        });
      });
    });

    row.addEventListener('click', (e) => {
      const ev = e.target.closest('.ck-ev');
      if (ev) {
        const eid = ev.getAttribute('data-ev');
        if (eid) highlightEv(eid);
      }
    });
  });

  // 初始自适应计算与延时校验
  adjustEvidenceFolding();
  window.addEventListener('load', adjustEvidenceFolding);
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(adjustEvidenceFolding, 100);
  });
})();
</script>"""


def build_checklist_html(draft: dict[str, Any], *, has_teacher: bool | None = None) -> str:
    from tools.graph import _CYTOSCAPE_CDN, build_graph_embed
    from tools.mindmap import _D3_CDN, _MARKMAP_VIEW_CDN, build_editable_mindmap_embed

    course = _clean(draft.get("course")) or "复习清单"
    cards = [c for c in (draft.get("cards") or []) if isinstance(c, dict)]
    body: list[str] = [
        '<div class="ck-doc">',
        '<header class="ck-doc-header">',
        f"<h1>{escape(course, quote=False)} · 复习清单</h1>",
        '<div class="ck-doc-meta"><span>知识复习与考点全景分析报告</span> · <span>Generated by AgentFlow</span></div>',
        '</header>',
    ]
    if not cards:
        body.append("<p>没有可复习的知识点。请先运行 catalog / 资料入库；若提供了老师重点，请确认文本能对上目录名称。</p></div>")
    else:
        groups = _nav_groups(cards, has_teacher=_draft_has_teacher(draft, has_teacher))
        focus, brief, extra, main_cards = groups["focus"], groups["brief"], groups["extra"], groups["main"]
        outline = draft.get("mindmap_outline") or build_checklist_mindmap_outline(draft, cards)
        nodes, edges = _graph_payload(cards)
        body.append("<h2>一、全局导航</h2>")
        body.append('<div class="ck-overview-wrap" id="ck-review">')
        body.append(
            '<div class="ck-table-panel">'
            '<div class="ck-overview-title"><span>知识点清单与掌握度</span><span class="ck-overview-hint">Table 1 · 知识点多维检索与掌握状态管理</span></div>'
            '<div class="ck-filter-row">'
            '<select id="ck-f-grade"><option value="">全部档位</option>'
            '<option value="S">核心 S</option><option value="A">重点 A</option>'
            '<option value="B">简要 B</option><option value="C">补充 C</option></select>'
            '<select id="ck-f-chapter"><option value="">全部章节</option></select>'
            '<select id="ck-f-type"><option value="">全部类型</option>'
            '<option value="concept">概念</option><option value="formula">公式</option>'
            '<option value="theorem">定理</option><option value="method">方法</option>'
            '<option value="application">应用</option></select>'
            '<span class="ck-mastery-track"><span id="ck-mastery-fill"></span></span>'
            '<span id="ck-mastery-text">已掌握 0/0</span></div>'
            '<table class="ck-table" id="ck-main-table"><thead><tr>'
            '<th class="ck-th-check">掌握</th>'
            '<th class="ck-th-grade" data-sort="grade">优先级 ↕</th>'
            '<th class="ck-th-name" data-sort="name">知识点 ↕</th>'
            '<th class="ck-th-imp" data-sort="importance">重要程度 ↕</th>'
            '<th class="ck-th-diff" data-sort="difficulty">难度 ↕</th>'
            '<th class="ck-th-chap" data-sort="chapter">所属章节 ↕</th>'
            '</tr></thead><tbody>'
        )
        for card in main_cards:
            body.append(_dynamic_row(card))
        body.append("</tbody></table></div>")
        body.append(_review_dynamic_script())
        body.append("</div>")
        if extra:
            body.append(
                '<div class="ck-subtitle">补充（老师未重点点、但知识结构中需要了解的）</div>'
                '<table class="ck-table"><thead><tr><th>知识点</th><th>重要程度</th><th>所属章节</th></tr></thead><tbody>'
            )
            for card in extra:
                body.append(
                    "<tr>"
                    f"<td>{escape(_clean(card.get('name')), quote=False)}</td>"
                    f'<td><span class="ck-stars">{importance_stars(card)}</span></td>'
                    f"<td>{escape(_clean(card.get('chapter')) or '—', quote=False)}</td>"
                    "</tr>"
                )
            body.append("</tbody></table>")
        body.append("<h3>2. 思维导图</h3>")
        body.append(build_editable_mindmap_embed(outline, title=f"{course} · 复习思维导图"))
        body.append("<h3>3. 考点知识图谱</h3>")
        if nodes:
            body.append(build_graph_embed(nodes, edges, title="考点知识图谱"))
        else:
            body.append("<p>本次激活点之间没有可画的关系图。</p>")
        body.append("<h2>二、知识点</h2>")
        for i, card in enumerate(focus, start=1):
            body.append(_card_html(card, card_idx=i))
        if brief:
            body.append('<div class="ck-brief"><h3>简要过一下</h3><ul>')
            for card in brief:
                preview = _clean(card.get("exam_preview")) or "知道定义和一条限制即可"
                body.append(
                    "<li>"
                    f'<span class="ck-stars">{importance_stars(card)}</span> '
                    f"<strong>{escape(_clean(card.get('name')), quote=False)}</strong>"
                    f" {_math_escape(preview)}"
                    "</li>"
                )
            body.append("</ul></div>")
        if extra:
            body.append('<div class="ck-brief"><h3>补充</h3><ul>')
            for card in extra:
                preview = _clean(card.get("exam_preview")) or "结构了解即可"
                kb_src = ""
                for ev in (_trace_pack(card).get("kb") or [])[:1]:
                    src = _clean(ev.get("source")) or _clean(ev.get("excerpt"))[:40]
                    if src:
                        kb_src = (
                            f' <span style="color:#0047ab;font-size:0.8rem;">'
                            f"[溯源：{escape(src, quote=False)}]</span>"
                        )
                body.append(
                    "<li>"
                    f'<span class="ck-stars">{importance_stars(card)}</span> '
                    f"<strong>{escape(_clean(card.get('name')), quote=False)}</strong>"
                    f" {_math_escape(preview)}{kb_src}"
                    "</li>"
                )
            body.append("</ul></div>")
        body.append(_trace_script())
        body.extend(_strategy_html(draft, _review_overview(main_cards)))
        body.extend(_action_html(draft))
        body.append("</div>")

    title = escape(f"{course} · 复习清单")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      padding: 32px 16px;
      background: #f6f5f0;
      color: #1a1a1a;
      font-family: "Latin Modern Roman", "Computer Modern Roman", "CMU Serif", "Times New Roman", Times, "Songti SC", "SimSun", "STSong", serif;
      -webkit-font-smoothing: antialiased;
    }}
    .page {{ max-width: 1140px; margin: 0 auto; }}
    .ck-doc {{
      background: #ffffff;
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0,0,0,0.03);
      padding: 36px 44px;
      line-height: 1.72;
      font-size: 0.96rem;
    }}
    .ck-doc h1 {{
      margin: 0 0 10px;
      font-size: 1.85rem;
      font-weight: 700;
      letter-spacing: 0.4px;
      text-align: center;
      font-variant: small-caps;
      color: #111111;
    }}
    .ck-doc-header {{
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 2px solid #111111;
      text-align: center;
    }}
    .ck-doc-meta {{
      font-size: 0.85rem;
      color: #555555;
      font-style: italic;
    }}
    .ck-doc h2 {{
      margin: 32px 0 16px;
      font-size: 1.25rem;
      font-weight: 700;
      color: #111111;
      border-bottom: 1.5px solid #222222;
      padding-bottom: 5px;
      letter-spacing: 0.3px;
    }}
    .ck-doc h3 {{
      margin: 20px 0 10px;
      font-size: 1.05rem;
      font-weight: 700;
      color: #222222;
    }}
    .ck-note {{ color: #555555; font-size: 0.86rem; font-style: italic; }}
    
    /* Booktabs Table Style */
    .ck-table-panel {{
      border: 1px solid #dcd8cf;
      border-radius: 4px;
      background: #ffffff;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
      padding: 18px 20px;
      box-sizing: border-box;
    }}
    .ck-overview-wrap {{ margin: 14px 0 24px; display: flex; flex-direction: column; gap: 16px; }}
    .ck-overview-title {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid #e7e4dc;
      font-family: inherit;
    }}
    .ck-overview-title span:first-child {{
      font-size: 0.96rem;
      font-weight: 700;
      color: #111111;
      letter-spacing: 0.3px;
    }}
    .ck-overview-hint {{ font-size: 0.78rem; color: #666666; font-style: italic; }}
    .ck-filter-row {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 0 0 14px; }}
    .ck-filter-row select {{
      padding: 4px 10px;
      border: 1px solid #888888;
      border-radius: 3px;
      font-size: 0.82rem;
      background: #ffffff;
      font-family: inherit;
      color: #111111;
    }}
    .ck-mastery-track {{ flex: 1; min-width: 140px; height: 8px; border-radius: 4px; background: #e5e2da; overflow: hidden; border: 1px solid #ccc; }}
    #ck-mastery-fill {{ display: block; height: 100%; width: 0; background: #0047ab; transition: width .2s; }}
    #ck-mastery-text {{ font-size: 0.82rem; color: #444444; white-space: nowrap; font-weight: 600; font-family: inherit; }}
    .ck-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
      margin: 0;
      background: #ffffff;
      border-top: 2px solid #222222;
      border-bottom: 2px solid #222222;
    }}
    .ck-table th, .ck-table td {{
      padding: 9px 12px;
      text-align: left;
      vertical-align: middle;
    }}
    .ck-table th {{
      background: #fbfaf7;
      border-bottom: 1.2px solid #222222;
      font-weight: 700;
      color: #111111;
      white-space: nowrap;
      user-select: none;
      font-size: 0.83rem;
      letter-spacing: 0.3px;
    }}
    .ck-table th[data-sort] {{ cursor: pointer; }}
    .ck-table th[data-sort]:hover {{ background: #f0ede6; }}
    .ck-table td {{ border-bottom: 1px solid #ede9e1; }}
    .ck-table tbody tr:hover {{ background: #faf8f5; }}
    .ck-th-check {{ width: 54px; text-align: center !important; }}
    .ck-th-grade {{ width: 90px; text-align: center !important; }}
    .ck-th-name {{ min-width: 260px; }}
    .ck-th-imp {{ width: 110px; text-align: center !important; }}
    .ck-th-diff {{ width: 80px; text-align: center !important; }}
    .ck-th-chap {{ width: 170px; }}
    .ck-cell-center {{ text-align: center !important; }}
    .ck-mastery {{ width: 16px; height: 16px; accent-color: #0047ab; cursor: pointer; vertical-align: middle; }}
    
    /* LaTeX Academic Badges */
    .ck-pill {{
      display: inline-flex;
      align-items: center;
      padding: 1px 7px;
      border-radius: 2px;
      font-size: 0.74rem;
      font-weight: 700;
      line-height: 1.4;
      white-space: nowrap;
      font-family: inherit;
      border: 1px solid #666;
    }}
    .ck-pill.ck-grade-s {{ background: #fff1f0; color: #a8071a; border-color: #cf1322; }}
    .ck-pill.ck-grade-a {{ background: #fffbe6; color: #ad4e00; border-color: #d46b08; }}
    .ck-pill.ck-grade-b {{ background: #e6f4ff; color: #0958d9; border-color: #1677ff; }}
    .ck-pill.ck-grade-c {{ background: #f5f5f5; color: #595959; border-color: #8c8c8c; }}
    
    .ck-badge {{
      display: inline-block;
      margin-right: 6px;
      padding: 1px 8px;
      border-radius: 2px;
      font-size: 0.74rem;
      font-weight: 700;
      font-family: inherit;
      border: 1px solid #222;
    }}
    .ck-s {{ background: #fff1f0; border-color: #cf1322; color: #a8071a; }}
    .ck-a {{ background: #fffbe6; border-color: #d46b08; color: #ad4e00; }}
    .ck-b {{ background: #e6f4ff; border-color: #1677ff; color: #0958d9; }}
    
    .ck-stars {{ color: #b86a04; white-space: nowrap; letter-spacing: 1.5px; font-size: 0.88rem; }}
    .ck-diff-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 1px 6px;
      border-radius: 2px;
      background: #fbfaf7;
      font-size: 0.76rem;
      font-weight: 700;
      color: #444;
      border: 1px solid #ccc;
      white-space: nowrap;
    }}
    .ck-chap-tag {{ display: inline-block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #555555; font-size: 0.82rem; }}
    .ck-kp-name {{ font-weight: 700; color: #111111; }}
    .ck-row-preview {{ font-weight: 400; color: #666666; font-size: 0.76rem; margin-top: 3px; line-height: 1.45; }}
    
    /* Section 2: LaTeX Review & Card Styles */
    .ck-review {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) 1px minmax(260px, 0.95fr);
      border: 1px solid #d4d0c7;
      border-radius: 4px;
      overflow: hidden;
      margin: 14px 0 20px;
      background: #ffffff;
      box-shadow: 0 1px 4px rgba(0,0,0,0.03);
    }}
    .ck-review-left {{ padding: 18px 22px; background: #ffffff; }}
    .ck-review-rule {{ background: #dcd8cf; }}
    .ck-review-right {{
      padding: 14px 16px;
      background: #faf9f6;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
    }}
    .ck-ev-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    
    /* Theorem & Definition Boxes as seen in img.png */
    .ck-card {{
      margin: 0;
      padding: 0;
      border: 0;
      background: transparent;
    }}
    .ck-card.is-s {{
      border: 1.5px solid #222222;
      padding: 14px 16px;
      background: #ffffff;
      border-radius: 2px;
    }}
    .ck-card.is-a {{
      border: 1px solid #e0dcd4;
      border-left: 4px solid #222222;
      padding: 14px 16px;
      background: #fdfdfc;
      border-radius: 2px;
    }}
    .ck-card.is-b {{
      border: 1px solid #e0dcd4;
      border-left: 3px solid #666666;
      padding: 12px 14px;
      background: #faf9f6;
      border-radius: 2px;
    }}
    .ck-card-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid #ede9e1;
    }}
    .ck-thm-title {{
      font-size: 1.02rem;
      font-weight: 700;
      color: #111111;
    }}
    .ck-thm-label {{
      font-weight: 700;
      color: #111111;
      margin-right: 4px;
      font-family: inherit;
    }}
    .ck-thm-list, .ck-thm-enum {{
      margin: 4px 0 8px;
      padding-left: 1.4em;
      line-height: 1.68;
    }}
    .ck-thm-list li, .ck-thm-enum li {{
      margin: 3px 0;
    }}
    .ck-remark-box {{
      margin: 8px 0;
      padding: 8px 12px;
      background: #fbfaf7;
      border-left: 3px solid #b86a04;
      border-radius: 2px;
      font-size: 0.92rem;
    }}
    
    /* Blue Hyperref Citations */
    .ck-cite-ref {{
      color: #0047ab;
      font-weight: 600;
      font-family: "Latin Modern Roman", "Computer Modern Roman", "Times New Roman", serif;
      text-decoration: none;
      cursor: pointer;
      padding: 0 2px;
      margin: 0 1px;
      border-radius: 2px;
      transition: all 0.15s ease;
      font-size: 0.92em;
      vertical-align: baseline;
      user-select: none;
    }}
    .ck-cite-ref:hover {{
      text-decoration: underline;
      background: #e8f0fe;
      color: #003380;
    }}
    .ck-cite-ref.is-active {{
      background: #d2e3fc;
      color: #002266;
      font-weight: 700;
      box-shadow: 0 0 0 1px #0047ab;
    }}
    
    .ck-field {{
      border-radius: 3px;
      padding: 4px 6px;
      margin: 4px -6px;
      transition: background 0.18s ease;
      cursor: pointer;
    }}
    .ck-field:hover {{ background: #faf8f0; }}
    .ck-field.is-on {{ background: #fff8db; border-left: 2px solid #b86a04; }}
    
    /* Right Provenance Panel */
    .ck-provenance-head {{
      font-size: 0.82rem;
      font-weight: 700;
      color: #222222;
      margin: 0 0 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid #e0dcd4;
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }}
    .ck-ref-icon {{ color: #0047ab; margin-right: 4px; }}
    .ck-ev {{
      display: block;
      margin: 0;
      padding: 9px 11px;
      border: 1px solid #dedad2;
      border-left: 3.5px solid #888888;
      border-radius: 2px;
      background: #ffffff;
      font-size: 0.82rem;
      line-height: 1.55;
      transition: all 0.2s ease;
      cursor: pointer;
    }}
    .ck-ev-more {{
      margin-top: 2px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .ck-ev-more[open] {{
      margin-top: 4px;
    }}
    .ck-ev-more summary {{
      margin-bottom: 6px;
    }}
    .ck-ev:hover {{ border-color: #b5b0a5; }}
    .ck-ev-teacher {{ border-left-color: #b32424; background: #fffcfc; }}
    .ck-ev-kb {{ border-left-color: #0047ab; background: #fdfdfe; }}
    .ck-ev-note {{ border-left-color: #1e7e34; background: #fbfdfb; }}
    
    .ck-ev.is-on, .ck-ev.is-highlighted {{
      border-color: #0047ab;
      box-shadow: 0 0 0 2px #0047ab, 0 3px 8px rgba(0,71,171,0.15);
      background: #f0f5ff;
    }}
    @keyframes citePulse {{
      0% {{ background: #dbeafe; box-shadow: 0 0 0 3px #0047ab; }}
      50% {{ background: #bfdbfe; box-shadow: 0 0 0 4px #0047ab; }}
      100% {{ background: #f0f5ff; box-shadow: 0 0 0 2px #0047ab; }}
    }}
    .ck-ev-k {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      color: #444444;
      margin-bottom: 4px;
      font-weight: 700;
    }}
    .ck-ev-cite-tag {{
      color: #0047ab;
      font-weight: 700;
      font-family: "Latin Modern Roman", serif;
      text-decoration: none;
    }}
    .ck-ev-kind-badge {{ color: #333333; }}
    .ck-ev-teacher .ck-ev-kind-badge {{ color: #b32424; }}
    .ck-ev-kb .ck-ev-kind-badge {{ color: #0047ab; }}
    .ck-ev-note .ck-ev-kind-badge {{ color: #1e7e34; }}
    
    .ck-ev-quote {{ color: #222222; font-style: italic; font-family: inherit; }}
    .ck-ev-meta, .ck-ev-sup {{ font-size: 0.74rem; color: #555555; margin-top: 4px; }}
    .ck-ev-empty {{ font-size: 0.78rem; color: #888888; padding: 6px 2px; font-style: italic; }}
    .ck-ev-more {{ margin-top: 8px; }}
    .ck-proof-toggle {{
      cursor: pointer;
      font-size: 0.82rem;
      color: #0047ab;
      user-select: none;
      font-family: inherit;
      padding: 2px 0;
    }}
    .ck-proof-toggle:hover {{ text-decoration: underline; }}
    
    /* Brief & Extra sections */
    .ck-brief {{
      margin: 12px 0 20px;
      padding: 14px 18px;
      border: 1px solid #d4d0c7;
      border-left: 4px solid #666666;
      border-radius: 2px;
      background: #faf9f6;
    }}
    .ck-brief h3 {{ margin: 0 0 8px; font-size: 1.02rem; font-weight: 700; }}
    .ck-brief ul {{ margin: 0; padding-left: 1.2em; }}
    .ck-subtitle {{ margin: 16px 0 6px; font-size: 0.92rem; font-weight: 700; color: #444444; }}
    .ck-brief li {{ margin: 6px 0; line-height: 1.6; }}
    
    /* Section 3: Review Strategy */
    .ck-strategy-panel {{
      margin: 12px 0 20px;
      border: 1px solid #d4d0c7;
      border-radius: 3px;
      background: #ffffff;
      overflow: hidden;
    }}
    .ck-strategy-head {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      padding: 10px 16px;
      border-bottom: 1px solid #dcd8cf;
      background: #faf9f6;
    }}
    .ck-strategy-head span {{ font-weight: 700; color: #111111; font-size: 0.95rem; }}
    .ck-strategy-head em {{ font-style: italic; color: #666666; font-size: 0.78rem; }}
    .ck-strategy-route {{ border-top: 1.5px solid #222222; }}
    .ck-priority-matrix {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      font-size: 0.85rem;
      border-top: 2px solid #222222;
      border-bottom: 2px solid #222222;
    }}
    .ck-priority-matrix th, .ck-priority-matrix td {{
      border: 1px solid #ede9e1;
      padding: 10px 12px;
      vertical-align: top;
      text-align: left;
    }}
    .ck-priority-matrix th {{ width: 88px; background: #faf9f6; color: #111; font-weight: 700; border-bottom: 1.2px solid #222222; }}
    .ck-priority-matrix td b {{ display: block; margin-bottom: 5px; color: #111111; }}
    .ck-priority-matrix td div {{ display: flex; gap: 5px; flex-wrap: wrap; }}
    .ck-priority-matrix td span, .ck-strategy-chips span {{
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      padding: 1px 7px;
      border: 1px solid #b5b0a5;
      border-radius: 2px;
      background: #faf9f6;
      color: #222222;
      font-size: 0.75rem;
      line-height: 1.45;
    }}
    .ck-priority-matrix td em {{ font-style: italic; color: #888888; }}
    
    .ck-strategy {{ list-style: none; margin: 0; padding: 12px 14px; display: grid; gap: 10px; }}
    .ck-strategy li {{
      display: grid;
      grid-template-columns: 32px minmax(0, 1fr);
      gap: 12px;
      align-items: start;
      padding: 11px 13px;
      border: 1px solid #dedad2;
      border-left: 3.5px solid #0047ab;
      border-radius: 2px;
      background: #ffffff;
    }}
    .ck-strategy-no {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      border-radius: 2px;
      background: #0047ab;
      color: #ffffff;
      font-size: 0.75rem;
      font-weight: 700;
      line-height: 1;
      font-family: inherit;
    }}
    .ck-strategy-text {{ font-size: 0.9rem; line-height: 1.65; color: #222222; }}
    .ck-strategy-text h3 {{ margin: 0 0 5px; font-size: 0.98rem; font-weight: 700; color: #111; }}
    .ck-strategy-text p {{ margin: 5px 0 0; }}
    .ck-strategy-chips {{ display: flex; gap: 5px; flex-wrap: wrap; margin: 0 0 7px; }}
    
    /* Section 4: Action Checklist */
    .ck-action {{ margin: 10px 0 8px; }}
    .ck-progress {{ margin: 0 0 14px; padding: 12px 14px; border: 1px solid #d4d0c7; border-radius: 3px; background: #faf9f6; }}
    .ck-progress-top {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; font-size: 0.88rem; }}
    .ck-progress-top span {{ color: #555555; font-size: 0.82rem; font-family: inherit; }}
    .ck-progress-track {{ height: 8px; border-radius: 4px; background: #e0dcd4; overflow: hidden; border: 1px solid #ccc; }}
    .ck-progress-track span {{ display: block; height: 100%; border-radius: 4px; background: #0047ab; transition: width .18s ease; }}
    .ck-action-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0 0 14px; }}
    .ck-stage {{
      display: grid;
      gap: 6px;
      text-align: left;
      padding: 12px 12px 14px;
      border: 1px solid #d4d0c7;
      border-radius: 3px;
      background: #faf9f6;
      cursor: pointer;
      min-height: 160px;
      font-family: inherit;
      transition: all 0.15s ease;
    }}
    .ck-stage:hover {{ background: #f4f1ea; }}
    .ck-stage.is-on {{
      background: #ffffff;
      border-color: #0047ab;
      border-width: 1.5px;
      box-shadow: 0 0 0 1px #0047ab;
    }}
    .ck-stage-no {{
      width: 22px;
      height: 22px;
      border-radius: 2px;
      background: #e8e4db;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .ck-stage.is-on .ck-stage-no {{ background: #0047ab; color: #ffffff; }}
    .ck-stage-title {{ font-weight: 700; font-size: 0.96rem; color: #111; }}
    .ck-stage-sub, .ck-stage-sum {{ color: #555555; font-size: 0.78rem; line-height: 1.45; }}
    .ck-stage-count {{ font-size: 0.76rem; color: #222222; font-weight: 700; }}
    .ck-action-detail {{ border: 1px solid #dedad2; border-radius: 3px; padding: 16px 18px; background: #ffffff; }}
    .ck-action-detail[hidden] {{ display: none; }}
    .ck-phase {{ margin: 12px 0 18px; }}
    .ck-phase h4 {{ margin: 0 0 8px; }}
    .ck-task {{ margin: 10px 0; padding: 11px 13px; border: 1px solid #dedad2; border-radius: 2px; background: #faf9f6; }}
    .ck-meta, .ck-k {{ font-size: 0.86rem; color: #555555; margin: 8px 0 4px; }}
    .ck-k {{ font-weight: 700; color: #111111; }}
    .ck-task-list {{ list-style: none; margin: 0 0 8px; padding: 0; display: grid; gap: 6px; }}
    .ck-task-list li {{ margin: 0; line-height: 1.65; }}
    .ck-task-list label {{ display: grid; grid-template-columns: 16px minmax(0, 1fr); gap: 8px; align-items: start; cursor: pointer; }}
    .ck-task-list input {{ width: 15px; height: 15px; margin: 5px 0 0; accent-color: #0047ab; cursor: pointer; }}
    .ck-task-list input:checked + span {{ color: #777777; text-decoration: line-through; text-decoration-thickness: 1px; }}
    .ck-check {{ margin: 0 0 8px; padding-left: 1.2em; }}
    .ck-check li {{ margin: 3px 0; }}
    
    @media(max-width: 860px) {{
      .ck-doc {{ padding: 22px 18px; }}
      .ck-review {{ grid-template-columns: 1fr; }}
      .ck-review-rule {{ display: none; }}
      .ck-action-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    {_widget_css()}
  </style>
  <script src="{_CYTOSCAPE_CDN}"></script>
  <script src="{_D3_CDN}"></script>
  <script src="{_MARKMAP_VIEW_CDN}"></script>
</head>
<body>
  <main class="page">
{"".join(body)}
  </main>
  {_MATHJAX_SCRIPT}
</body>
</html>
"""


def attach_checklist_artifacts(state: dict[str, Any]) -> None:
    from tools.domain_engine_text import line

    from .gather import teacher_from_context
    from .trace import attach_card_provenance

    sub = line(state, "checklist")
    draft = dict(sub.get("draft") or {})
    extra = str((state.get("line_extra") or {}).get("checklist") or "")
    context = f"{state.get('transcript') or ''}\n{extra}"
    teacher = teacher_from_context(context)
    has_teacher = bool(teacher.strip())
    draft = attach_card_provenance(draft, context, teacher)
    cards = [c for c in (draft.get("cards") or []) if isinstance(c, dict)]
    draft["mindmap_outline"] = build_checklist_mindmap_outline(draft, cards)
    draft["checklist_html"] = build_checklist_html(draft, has_teacher=has_teacher)
    sub["rendered"] = build_checklist_markdown(draft, has_teacher=has_teacher)
    sub["draft"] = draft
    sub["structure"] = cards


# ── 复习结构总览（语义回卷 / 过滤 / 排序 / 展开 / 掌握度）────

def _dynamic_row(card: dict[str, Any]) -> str:
    """动态表格行：携带排序/过滤属性 + 掌握度勾选 + 优雅列排版。"""
    name = _clean(card.get("name"))
    kid = _clean(card.get("id")) or _clean(card.get("kp_id")) or name
    grade = str(card.get("session_priority") or "B")
    chapter = _clean(card.get("chapter")) or "—"
    ktype = _clean(card.get("knowledge_type")) or ""
    try:
        importance = int(str(card.get("importance") or 3) or 3)
    except (TypeError, ValueError):
        importance = 3
    try:
        difficulty = int(str(card.get("difficulty") or 3) or 3)
    except (TypeError, ValueError):
        difficulty = 3
    preview = _clean(card.get("exam_preview")) or ""
    badge_class = f"ck-pill ck-grade-{grade.lower()}" if grade.lower() in {"s", "a", "b"} else "ck-pill"
    badge_label = f"{_grade_label(card)} {grade}".strip()
    return (
        f'<tr data-id="{escape(kid, quote=False)}" data-grade="{escape(grade, quote=False)}" data-name="{escape(name, quote=False)}" '
        f'data-chapter="{escape(chapter, quote=False)}" data-type="{escape(ktype, quote=False)}" '
        f'data-importance="{importance}" data-difficulty="{difficulty}">'
        f'<td class="ck-cell-center"><input type="checkbox" class="ck-mastery" data-name="{escape(name, quote=False)}" title="标记为已掌握"></td>'
        f'<td class="ck-cell-center"><span class="{badge_class}">{badge_label}</span></td>'
        f'<td class="ck-kp-name">{escape(name, quote=False)}'
        f'<div class="ck-row-preview">{escape(preview[:75], quote=False)}</div></td>'
        f'<td class="ck-cell-center"><span class="ck-stars">{importance_stars(card)}</span></td>'
        f'<td class="ck-cell-center"><span class="ck-diff-badge">Lv.{difficulty}</span></td>'
        f'<td><span class="ck-chap-tag" title="{escape(chapter, quote=False)}">{escape(chapter, quote=False)}</span></td>'
        f'</tr>'
    )


def _review_dynamic_script() -> str:
    """知识点表格交互脚本：档位/章节/类型筛选 / 排序 / 掌握度勾选。"""
    template = """<script>
(function () {
  const wrap = document.getElementById('ck-review');
  if (!wrap) return;
  const table = document.getElementById('ck-main-table');
  const rows = table ? Array.from(table.tBodies[0].rows) : [];
  const fGrade = document.getElementById('ck-f-grade');
  const fChapter = document.getElementById('ck-f-chapter');
  const fType = document.getElementById('ck-f-type');
  let gradeFilter = '', chapterFilter = '', typeFilter = '';

  function applyFilters() {
    if (!table) return;
    rows.forEach((row) => {
      const okGrade = !gradeFilter || row.getAttribute('data-grade') === gradeFilter;
      const okChapter = !chapterFilter || row.getAttribute('data-chapter') === chapterFilter;
      const okType = !typeFilter || row.getAttribute('data-type') === typeFilter;
      row.style.display = (okGrade && okChapter && okType) ? '' : 'none';
    });
  }

  if (fGrade) fGrade.addEventListener('change', () => { gradeFilter = fGrade.value; applyFilters(); });
  if (fChapter) fChapter.addEventListener('change', () => { chapterFilter = fChapter.value; applyFilters(); });
  if (fType) fType.addEventListener('change', () => { typeFilter = fType.value; applyFilters(); });

  if (fChapter && rows.length) {
    const chapters = [];
    rows.forEach((r) => {
      const c = r.getAttribute('data-chapter');
      if (c && chapters.indexOf(c) < 0) chapters.push(c);
    });
    chapters.sort().forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c; opt.textContent = c;
      fChapter.appendChild(opt);
    });
  }

  if (table) {
    table.querySelectorAll('th[data-sort]').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort');
        const tbody = table.tBodies[0];
        Array.from(tbody.rows)
          .filter((r) => r.style.display !== 'none')
          .sort((a, b) => {
            let va = a.getAttribute('data-' + key) || '', vb = b.getAttribute('data-' + key) || '';
            if (key === 'importance' || key === 'difficulty') { va = Number(va) || 0; vb = Number(vb) || 0; }
            return va < vb ? -1 : va > vb ? 1 : 0;
          })
          .forEach((r) => tbody.appendChild(r));
      });
    });
    rows.forEach((row) => {
      row.addEventListener('click', (ev) => {
        if (ev.target && ev.target.type === 'checkbox') return;
        const detail = row.querySelector('.ck-row-detail');
        if (detail) detail.hidden = !detail.hidden;
      });
    });
  }

  // 掌握度勾选（localStorage 按复习清单课程记忆）
  const storageKey = 'ck-mastery-' + encodeURIComponent(String((document.title || '').split(' ')[0]));
  let mastered = {};
  try { mastered = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch (e) {}
  const fill = document.getElementById('ck-mastery-fill');
  const textEl = document.getElementById('ck-mastery-text');
  const refreshMastery = () => {
    const boxes = Array.from(wrap.querySelectorAll('.ck-mastery'));
    const done = boxes.filter((b) => b.checked).length;
    if (fill) fill.style.width = boxes.length ? (done / boxes.length * 100) + '%' : '0%';
    if (textEl) textEl.textContent = '已掌握 ' + done + '/' + boxes.length;
  };
  wrap.querySelectorAll('.ck-mastery').forEach((box) => {
    const name = box.getAttribute('data-name');
    box.checked = !!mastered[name];
    box.addEventListener('change', () => {
      mastered[name] = box.checked;
      try { localStorage.setItem(storageKey, JSON.stringify(mastered)); } catch (e) {}
      refreshMastery();
    });
  });
  refreshMastery();
})();
</script>"""
    return template

def build_checklist_summary(
    course: str,
    catalog_version: str,
    cards: list[dict],
) -> str:
    """清单速览摘要（API data.text 用）：统计 + 卡片列表，不含卡片正文。

    完整内容见产物 checklist.html（交互页）与 result.md（全量存档）。
    """
    from .assemble import _clean

    del catalog_version
    graded: dict[str, list[dict]] = {"S": [], "A": [], "B": [], "C": []}
    for card in cards:
        if not isinstance(card, dict):
            continue
        name = _clean(card.get("name"))
        if not name:
            continue
        graded.setdefault(str(card.get("session_priority") or "B"), []).append(card)
    total = sum(len(v) for v in graded.values())
    if not total:
        return "暂无复习卡片。\n"
    labels = {"S": "核心", "A": "重点", "B": "简要", "C": "补充"}
    lines = [
        f"# {course or '知识'} · 复习清单",
        f"本次清单：{total} 张卡（"
        + " · ".join(f"{labels[k]} {len(v)}" for k, v in graded.items() if v)
        + "）",
        "",
    ]
    for grade in ("S", "A", "B", "C"):
        rows = graded.get(grade) or []
        if not rows:
            continue
        lines.append(f"## {labels[grade]}（{len(rows)}）")
        for card in rows:
            name = _clean(card.get("name"))
            chapter = _clean(card.get("chapter")) or _clean(card.get("topic")) or ""
            lines.append(f"- {name}" + (f" —— {chapter}" if chapter else ""))
        lines.append("")
    lines.append("完整内容见产物 checklist.html（交互页）与 result.md。")
    return "\n".join(lines)
