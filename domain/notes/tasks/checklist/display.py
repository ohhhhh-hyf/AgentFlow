"""checklist 展示：复习重点分布、导图、关系图、卡片、行动清单。"""
from __future__ import annotations

import json
import re
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
    if draft.get("catalog_version"):
        lines.append(f"基于 Knowledge Catalog v{draft.get('catalog_version')}，不改长期目录。")
        lines.append("")
    if not cards:
        lines.append("没有可复习的知识点。请先运行 catalog / 资料入库；若提供了老师重点，请确认文本能对上目录名称。")
        return "\n".join(lines)

    groups = _nav_groups(cards, has_teacher=_draft_has_teacher(draft, has_teacher))
    focus, brief, extra, main_cards = groups["focus"], groups["brief"], groups["extra"], groups["main"]
    overview = _review_overview(main_cards)
    total_val = float(overview.get("total_value") or 0) or 1.0
    lines.extend(["## 一、全局导航", "", "### 1. 本次复习结构总览", ""])
    for item in overview.get("bar_items") or []:
        grade = _GRADE.get(str(item.get("session_priority") or ""), "简要")
        reason = _clean(item.get("reason"))
        val = float(item.get("value") or 0)
        pct = max(0.1, val / total_val * 100)
        lines.append(
            f"- {grade}｜{_clean(item.get('name'))}：{pct:.1f}%"
            + (f"（{reason}）" if reason else "")
        )
    lines.extend(["", "| 优先级 | 知识点 | 重要程度 | 所属章节 |", "| --- | --- | --- | --- |"])
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
    lines.extend(["", "### 2. 思维导图", "", outline, "", "### 3. 考点知识图谱", ""])
    for src, rel, dst in _edges(cards):
        lines.append(f"- {src} —{rel}→ {dst}")

    lines.extend(["", "## 二、知识点", ""])
    for card in focus:
        facts = _as_list(card.get("key_facts"))[:6]
        steps = _as_list(card.get("method_steps"))[:6]
        pits = _as_list(card.get("pitfalls"))[:4]
        lines.append(f"### {_clean(card.get('name'))}  （{_grade_label(card)} · {importance_stars(card)}）")
        lines.append(f"- 考法预判：{_clean(card.get('exam_preview'))}")
        if facts:
            lines.append("- 必须先会：")
            lines.extend(f"  - {item}" for item in facts)
        lines.append(f"- 知识点讲解：{_clean(card.get('explain'))}")
        if steps:
            lines.append("- 方法步骤：")
            lines.extend(f"  {i}. {step}" for i, step in enumerate(steps, start=1))
        if pits:
            lines.append("- 易错提醒：")
            lines.extend(f"  - {p}" for p in pits)
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

    lines.extend(_strategy_markdown(draft))
    lines.extend(_action_markdown(draft))
    return "\n".join(lines).strip() + "\n"


def _action_cards(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (draft.get("phases") or []) if isinstance(p, dict) and p.get("id")]


def _strategy_markdown(draft: dict[str, Any]) -> list[str]:
    items = [
        s for s in (draft.get("strategy") or []) if isinstance(s, str) and s.strip()
    ]
    if not items:
        return []
    lines = ["## 三、复习策略", ""]
    lines.extend(f"- {item}" for item in items)
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


_MATH_HINT_RE = re.compile(
    r"(?<![$\\])("
    r"\\(?:frac|sqrt|sum|int|lim|alpha|beta|gamma|theta|lambda|mu|sigma|omega|Delta|partial|nabla)\b"
    r"|[A-Za-z0-9]+(?:\s*[_^]\s*[A-Za-z0-9{}]+)+"
    r"|[A-Za-z0-9{}\\^_+\-*/(), ]+\s*(?:=|≤|≥|\\le|\\ge|\\neq|≈)\s*[A-Za-z0-9{}\\^_+\-*/(), ]+"
    r")"
)


def _math_escape(text: object) -> str:
    from tools.ocr.mathmd import normalize_markdown_math

    raw = normalize_markdown_math(str(text or ""))
    if "$" not in raw:
        raw = _MATH_HINT_RE.sub(lambda m: f"${m.group(1).strip()}$", raw)
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


def _strategy_html(draft: dict[str, Any]) -> list[str]:
    items = [
        s for s in (draft.get("strategy") or []) if isinstance(s, str) and s.strip()
    ]
    if not items:
        return []
    rows = [
        "<h2>三、复习策略</h2>",
        '<section class="ck-strategy-panel" aria-label="复习策略">',
        '<div class="ck-strategy-head"><span>复习顺序</span><em>按重点和难度排好先后</em></div>',
        '<ol class="ck-strategy">',
    ]
    for i, item in enumerate(items, start=1):
        rows.append(
            "<li>"
            f'<span class="ck-strategy-no">{i:02d}</span>'
            f'<span class="ck-strategy-text">{escape(str(item), quote=False)}</span>'
            "</li>"
        )
    rows.extend(["</ol>", "</section>"])
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
.ck-stars{color:#c98a2d;letter-spacing:1px;font-size:.95rem;}
.ck-card p{margin:8px 0;}
.ck-card ol,.ck-card ul{margin:6px 0 10px;padding-left:1.3em;}
.ck-card li{margin:4px 0;line-height:1.7;}
.ck-quote{margin:8px 0 12px;padding:8px 10px;background:#f7f5f0;border-left:3px solid #c8c4b8;border-radius:4px;color:#4a4842;font-size:.88rem;}
.lc-kg{margin:8px 0;border:1px solid #ebe8e1;border-radius:12px;overflow:hidden;background:#fff;}
.lc-kg-shell{display:grid;grid-template-columns:minmax(0,1fr) minmax(240px,32%);min-height:560px;}
#lc-cy{width:100%;height:560px;background:linear-gradient(135deg,#ffffff 0%,#f5fbff 48%,#eef7ff 100%);}
.lc-kg-aside{border-left:1px solid #e2e8f0;background:#faf9f6;padding:14px 12px;overflow:auto;}
.lc-kg-aside h3{margin:0 0 8px;font-size:1rem;}
.lc-kg-meta,.lc-kg-ev{color:#64748b;font-size:.78rem;line-height:1.6;}
.lc-kg-label{font-size:.76rem;color:#475569;margin:14px 0 6px;}
.lc-kg-detail{border:1px solid #e2e8f0;border-radius:8px;padding:10px;background:#fff;font-size:.86rem;line-height:1.6;}
.lc-kg-name{font-weight:700;margin-bottom:8px;}
.lc-kg-block{margin-top:8px;}
.lc-kg-k{color:#64748b;font-size:.72rem;margin-bottom:3px;}
.lc-kg-rel{margin-top:6px;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;}
.lc-kg-chips{display:flex;flex-wrap:wrap;gap:6px;}
.lc-kg-chip{display:inline-block;padding:1px 8px;border-radius:999px;background:#e2e8f0;font-size:.74rem;}
.lc-kg-legend{display:grid;gap:6px;}
.lc-kg-legend-item{display:flex;align-items:center;gap:8px;font-size:.8rem;}
.lc-kg-swatch{width:10px;height:10px;border-radius:50%;}
.lc-mm{position:relative;margin:8px 0;border:1px solid #ebe8e1;border-radius:12px;overflow:hidden;background:#fff;}
.lc-mm-bar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid #e2e8f0;background:#f8fafc;flex-wrap:wrap;}
.lc-mm-hint{color:#64748b;font-size:.76rem;flex:1 1 180px;}
.lc-mm-bar button{border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:4px 10px;font-size:.8rem;cursor:pointer;}
.lc-mm-bar button.lc-mm-save{background:#0f172a;color:#fff;border-color:#0f172a;}
.lc-mm-body{display:grid;grid-template-columns:1fr;height:560px;min-height:560px;}
.lc-mm-body.editing{grid-template-columns:minmax(200px,34%) 1fr;}
#lc-mm-editor{display:none;width:100%;height:100%;border:0;border-right:1px solid #e2e8f0;padding:10px;resize:none;font:13px/1.55 ui-monospace,Consolas,monospace;}
.lc-mm-body.editing #lc-mm-editor{display:block;}
.lc-mm-canvas{position:relative;min-height:560px;height:100%;background:#fff;}
#lc-mindmap{position:absolute;inset:0;width:100%;height:100%;display:block;}
.lc-mm-fallback{padding:12px 20px 16px;overflow:auto;height:100%;}
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


def _split_visible(pack: dict[str, list[dict[str, Any]]]) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    """默认：老师原话优先 + 1～2 条知识库 + 至多 1 条笔记，其余折叠。"""
    visible: list[tuple[str, dict[str, Any]]] = []
    hidden: list[tuple[str, dict[str, Any]]] = []
    teachers = pack["teacher"]
    if teachers:
        visible.extend(("teacher", ev) for ev in teachers[:2])
        hidden.extend(("teacher", ev) for ev in teachers[2:])
    kb = pack["kb"]
    kb_show = 2 if not teachers else 1
    visible.extend(("kb", ev) for ev in kb[:kb_show])
    hidden.extend(("kb", ev) for ev in kb[kb_show:])
    notes = pack["note"]
    if notes:
        visible.append(("note", notes[0]))
        hidden.extend(("note", ev) for ev in notes[1:])
    return visible, hidden


def _supports_label(ev: dict[str, Any]) -> str:
    labels = [_SUPPORT_CN.get(str(x), "") for x in (ev.get("supports") or [])]
    return " / ".join(x for x in labels if x)


def _evidence_html(kind: str, ev: dict[str, Any]) -> str:
    eid = escape(str(ev.get("evidence_id") or ""), quote=True)
    supports = " ".join(str(x) for x in (ev.get("supports") or []) if x)
    klass = {"teacher": "ck-ev-teacher", "kb": "ck-ev-kb", "note": "ck-ev-note"}.get(kind, "")
    head = {
        "teacher": "老师原话",
        "kb": "知识库依据",
        "note": "学生笔记",
    }.get(kind, "依据")
    rows = [
        f'<div class="ck-ev {klass}" data-ev="{eid}" data-supports="{escape(supports, quote=True)}">',
        f'<div class="ck-ev-k">{escape(str(head), quote=False)}</div>',
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
                "<details><summary>完整片段</summary>"
                f'<div class="ck-ev-quote">{_math_escape(full)}</div></details>'
            )
    sup = _supports_label(ev)
    if sup:
        rows.append(f'<div class="ck-ev-sup">支撑：{escape(sup, quote=False)}</div>')
    rows.append("</div>")
    return "".join(rows)


def _trace_html(card: dict[str, Any]) -> str:
    pack = _trace_pack(card)
    visible, hidden = _split_visible(pack)
    if not visible and not hidden:
        status = ""
        raw = card.get("provenance") if isinstance(card.get("provenance"), dict) else {}
        if raw.get("evidence_status") == "insufficient":
            status = "这条判断缺少直接依据，未编造出处。"
        return f'<div class="ck-ev-empty">{status or "暂无足够依据"}</div>'
    rows = [_evidence_html(kind, ev) for kind, ev in visible]
    if hidden:
        rows.append('<details class="ck-ev-more"><summary>查看更多依据</summary>')
        rows.extend(_evidence_html(kind, ev) for kind, ev in hidden)
        rows.append("</details>")
    return "".join(rows)


def _card_html(card: dict[str, Any]) -> str:
    grade = str(card.get("session_priority") or "")
    brief = grade not in {"S", "A"}
    badge = "ck-s" if grade == "S" else "ck-a" if grade == "A" else "ck-b"
    facts = _as_list(card.get("key_facts"))[: 3 if brief else 6]
    steps = _as_list(card.get("method_steps"))[: 3 if brief else 6]
    pits = _as_list(card.get("pitfalls"))[: 2 if brief else 4]
    left = [
        '<div class="ck-card">',
        f'<span class="ck-badge {badge}">{escape(_grade_label(card), quote=False)}</span>'
        f'<span class="ck-stars">{importance_stars(card)}</span> '
        f"<strong>{escape(_clean(card.get('name')), quote=False)}</strong>",
        '<div class="ck-field" data-field="exam_prediction">'
        f"<p><b>考法预判</b> {escape(_clean(card.get('exam_preview')), quote=False)}</p></div>",
    ]
    if facts:
        left.append(
            "<p><b>必须先会</b></p><ul>"
            + "".join(f"<li>{escape(item, quote=False)}</li>" for item in facts)
            + "</ul>"
        )
    left.append(
        '<div class="ck-field" data-field="explanation">'
        f"<p><b>知识点讲解</b> {escape(_clean(card.get('explain')), quote=False)}</p></div>"
    )
    if steps:
        left.append(
            '<div class="ck-field" data-field="method_steps"><p><b>方法步骤</b></p><ol>'
            + "".join(f"<li>{escape(step, quote=False)}</li>" for step in steps)
            + "</ol></div>"
        )
    if pits:
        left.append(
            '<div class="ck-field" data-field="error_warning"><p><b>易错提醒</b></p><ul>'
            + "".join(f"<li>{escape(item, quote=False)}</li>" for item in pits)
            + "</ul></div>"
        )
    left.append("</div>")
    return (
        '<div class="ck-review">'
        f'<div class="ck-review-left">{"".join(left)}</div>'
        '<div class="ck-review-rule"></div>'
        f'<div class="ck-review-right">{_trace_html(card)}</div>'
        "</div>"
    )


def _trace_markdown(card: dict[str, Any]) -> list[str]:
    pack = _trace_pack(card)
    if not any(pack.values()):
        return []
    lines = ["- 溯源"]
    for ev in pack["teacher"][:3]:
        lines.append(f"  - 老师原话：{_clean(ev.get('text'))}")
    for ev in pack["kb"][:2]:
        src = _clean(ev.get("source"))
        excerpt = _clean(ev.get("excerpt"))
        lines.append(f"  - 知识库：{src} — {excerpt}" if src else f"  - 知识库：{excerpt}")
    for ev in pack["note"][:1]:
        lines.append(f"  - 笔记：{_clean(ev.get('excerpt'))}")
    return lines


_MATHJAX_SCRIPT = """<script>
(function () {
  if (window.MathJax && window.MathJax.typesetPromise) {
    window.MathJax.typesetPromise();
    return;
  }
  window.MathJax = {
    tex: {inlineMath: [['$', '$'], ['\\(', '\\)']], displayMath: [['$$', '$$'], ['\\[', '\\]']]},
    options: {skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']}
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
  document.querySelectorAll('.ck-review').forEach((row) => {
    const fields = row.querySelectorAll('[data-field]');
    const evs = row.querySelectorAll('[data-supports]');
    const clear = () => {
      fields.forEach((el) => el.classList.remove('is-on'));
      evs.forEach((el) => el.classList.remove('is-on'));
    };
    fields.forEach((field) => {
      field.addEventListener('click', () => {
        const key = field.getAttribute('data-field') || '';
        clear();
        field.classList.add('is-on');
        evs.forEach((ev) => {
          const bag = ' ' + (ev.getAttribute('data-supports') || '') + ' ';
          if (key && bag.indexOf(' ' + key + ' ') >= 0) ev.classList.add('is-on');
        });
      });
    });
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
        f"<h1>{escape(course, quote=False)} · 复习清单</h1>",
    ]
    if draft.get("catalog_version"):
        body.append(
            f'<p class="ck-note">基于 Knowledge Catalog v{escape(str(draft.get("catalog_version")), quote=False)}，本次不改长期目录。</p>'
        )
    if not cards:
        body.append("<p>没有可复习的知识点。请先运行 catalog / 资料入库；若提供了老师重点，请确认文本能对上目录名称。</p></div>")
    else:
        groups = _nav_groups(cards, has_teacher=_draft_has_teacher(draft, has_teacher))
        focus, brief, extra, main_cards = groups["focus"], groups["brief"], groups["extra"], groups["main"]
        outline = draft.get("mindmap_outline") or build_checklist_mindmap_outline(draft, cards)
        nodes, edges = _graph_payload(cards)
        body.append("<h2>一、全局导航</h2><h3>1. 本次复习结构总览</h3>")
        overview = _review_overview(main_cards)
        body.append('<div class="ck-overview-wrap" id="ck-review">')
        body.append(_overview_html(overview))
        body.append(
            '<div class="ck-table-panel">'
            '<div class="ck-overview-title">知识点清单与掌握度</div>'
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
            '<th>掌握</th><th data-sort="grade">优先级</th><th data-sort="name">知识点</th>'
            '<th data-sort="importance">重要程度</th><th data-sort="difficulty">难度</th>'
            '<th data-sort="chapter">所属章节</th></tr></thead><tbody>'
        )
        for card in main_cards:
            body.append(_dynamic_row(card))
        body.append("</tbody></table></div>")
        body.append(_review_dynamic_script(overview))
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
        for card in focus:
            body.append(_card_html(card))
        if brief:
            body.append('<div class="ck-brief"><h3>简要过一下</h3><ul>')
            for card in brief:
                preview = _clean(card.get("exam_preview")) or "知道定义和一条限制即可"
                body.append(
                    "<li>"
                    f'<span class="ck-stars">{importance_stars(card)}</span> '
                    f"<strong>{escape(_clean(card.get('name')), quote=False)}</strong>"
                    f" {escape(preview, quote=False)}"
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
                            f' <span style="color:#6b6860;font-size:0.78rem;">'
                            f"溯源：{escape(src, quote=False)}</span>"
                        )
                body.append(
                    "<li>"
                    f'<span class="ck-stars">{importance_stars(card)}</span> '
                    f"<strong>{escape(_clean(card.get('name')), quote=False)}</strong>"
                    f" {escape(preview, quote=False)}{kb_src}"
                    "</li>"
                )
            body.append("</ul></div>")
        body.append(_trace_script())
        body.extend(_strategy_html(draft))
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
    body {{ margin: 0; padding: 24px; background: #f0eee9; color: #1c1b19; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; }}
    .page {{ max-width: 1100px; margin: 0 auto; }}
    .ck-doc{{background:#fff;border:1px solid #d4d0c6;border-radius:10px;padding:22px 28px;line-height:1.7;}}
    .ck-doc h1{{margin:0 0 8px;font-size:1.7rem;}}
    .ck-doc h2{{margin:22px 0 10px;font-size:1.2rem;}}
    .ck-doc h3{{margin:16px 0 8px;font-size:1.05rem;}}
    .ck-note{{color:#6b6860;font-size:.86rem;}}
    .ck-review{{margin:10px 0;}}
    .ck-overview-wrap{{margin:12px 0 24px;display:flex;flex-direction:column;gap:16px;}}
    .ck-bar-panel,.ck-table-panel{{border:1px solid #e7e4dc;border-radius:12px;background:#ffffff;box-shadow:0 1px 4px rgba(0,0,0,0.03);padding:16px 18px;box-sizing:border-box;}}
    .ck-overview-title{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid #f0eee9;}}
    .ck-overview-title span:first-child{{font-size:.95rem;font-weight:750;color:#1c1b19;letter-spacing:0.2px;}}
    .ck-overview-hint{{font-size:.76rem;color:#8a867c;font-weight:400;}}
    .ck-bar-panel{{display:grid;gap:10px;align-content:start;}}
    .ck-bar-item{{display:flex;flex-direction:column;gap:6px;width:100%;border:1px solid #ebe8e1;border-radius:9px;background:#faf9f6;padding:10px 14px;text-align:left;cursor:pointer;font:inherit;box-sizing:border-box;transition:all .2s cubic-bezier(0.16, 1, 0.3, 1);}}
    .ck-bar-item:hover{{border-color:#395f8a;background:#fff;transform:translateY(-1.5px);box-shadow:0 4px 12px rgba(0,0,0,0.05);}}
    .ck-bar-item.is-on{{border-color:#b3402e;background:#fff;box-shadow:0 0 0 1.5px #b3402e, 0 4px 12px rgba(179,64,46,0.1);}}
    .ck-bar-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;}}
    .ck-bar-name{{font-weight:700;font-size:.88rem;color:#1c1b19;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
    .ck-bar-pct{{font-size:.88rem;font-weight:800;color:#2c2a26;letter-spacing:-0.2px;font-variant-numeric:tabular-nums;}}
    .ck-bar-track{{width:100%;height:7px;border-radius:999px;background:#eae7df;overflow:hidden;}}
    .ck-bar-fill{{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#497a78,#5c9896);transition:width .4s cubic-bezier(0.4, 0, 0.2, 1);}}
    .ck-bar-fill.ck-grade-s{{background:linear-gradient(90deg,#ff7875,#d9363e);}}
    .ck-bar-fill.ck-grade-a{{background:linear-gradient(90deg,#ffc069,#d46b08);}}
    .ck-bar-fill.ck-grade-b{{background:linear-gradient(90deg,#69c0ff,#1890ff);}}
    .ck-bar-bottom{{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:.74rem;color:#8a867c;}}
    .ck-pill{{display:inline-flex;align-items:center;padding:1px 7px;border-radius:6px;font-size:.72rem;font-weight:700;line-height:1.4;white-space:nowrap;}}
    .ck-pill.ck-grade-s{{background:#fff1f0;color:#cf1322;border:1px solid #ffa39e;}}
    .ck-pill.ck-grade-a{{background:#fffbe6;color:#d46b08;border:1px solid #ffe58f;}}
    .ck-pill.ck-grade-b{{background:#e6f7ff;color:#096dd9;border:1px solid #91d5ff;}}
    .ck-filter-row{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 12px;}}
    .ck-filter-row select{{padding:4px 8px;border:1px solid #d4d0c6;border-radius:6px;font-size:.82rem;background:#fff;}}
    .ck-mastery-track{{flex:1;min-width:120px;height:8px;border-radius:999px;background:#e8e4da;overflow:hidden;}}
    #ck-mastery-fill{{display:block;height:100%;width:0;background:#497a78;transition:width .2s;}}
    #ck-mastery-text{{font-size:.78rem;color:#6b6860;white-space:nowrap;}}
    .ck-kp-name{{font-weight:600;}}
    .ck-row-preview{{font-weight:400;color:#8a867c;font-size:.76rem;margin-top:2px;}}
    .ck-row-detail{{font-size:.8rem;color:#3a3832;line-height:1.55;padding:6px 2px;}}
    .ck-dot{{width:10px;height:10px;border-radius:50%;}}
    .ck-table{{width:100%;border-collapse:collapse;font-size:.86rem;margin:0;}}
    .ck-table th,.ck-table td{{border:1px solid #e7e4dc;padding:8px 10px;text-align:left;}}
    .ck-table th{{background:#f7f5f0;font-weight:700;color:#3a3832;}}
    .ck-review{{display:grid;grid-template-columns:minmax(0,1fr) 1px minmax(240px,34%);border:1px solid #ebe8e1;border-radius:10px;overflow:hidden;margin:10px 0 16px;background:#fff;}}
    .ck-review-left{{padding:12px 14px;background:#fbfaf7;}}
    .ck-review-rule{{background:#c8c4b8;}}
    .ck-review-right{{padding:10px 10px 12px;background:#faf9f6;}}
    .ck-card{{margin:0;padding:0;border:0;background:transparent;}}
    .ck-field{{border-radius:6px;padding:2px 0;}}
    .ck-field.is-on{{background:#fff6c7;}}
    .ck-ev{{display:block;margin:0 0 8px;padding:8px 9px;border-left:3px solid #c8c4b8;border-radius:4px;background:#fff;font-size:.82rem;line-height:1.55;}}
    .ck-ev.is-on{{box-shadow:0 0 0 1px #b3402e55;}}
    .ck-ev-teacher{{border-left-color:#b3402e;}}
    .ck-ev-kb{{border-left-color:#395f8a;}}
    .ck-ev-note{{border-left-color:#497a78;}}
    .ck-ev-k{{font-size:.72rem;color:#6b6860;margin-bottom:4px;font-weight:650;}}
    .ck-ev-teacher .ck-ev-k{{color:#b3402e;}}
    .ck-ev-quote{{color:#4a4842;}}
    .ck-ev-meta,.ck-ev-sup{{font-size:.74rem;color:#6b6860;margin-top:4px;}}
    .ck-ev-empty{{font-size:.78rem;color:#9a968c;padding:6px 2px;}}
    .ck-ev-more{{margin-top:6px;}}
    .ck-ev-more summary{{cursor:pointer;font-size:.78rem;color:#3a3832;user-select:none;}}
    .ck-brief{{margin:8px 0 16px;padding:12px 14px;border:1px dashed #d4d0c6;border-radius:10px;background:#fbfaf7;}}
    .ck-brief h3{{margin:0 0 8px;font-size:1.02rem;}}
    .ck-brief ul{{margin:0;padding-left:1.2em;}}
    .ck-subtitle{{margin:14px 0 6px;font-size:0.9rem;font-weight:650;color:#6b6860;}}
    .ck-brief li{{margin:6px 0;line-height:1.55;}}
    @media(max-width:860px){{.ck-review{{grid-template-columns:1fr}}.ck-review-rule{{display:none}}}}
    .ck-badge{{display:inline-block;margin-right:6px;padding:1px 8px;border-radius:10px;font-size:.74rem;background:#efece4;border:1px solid #d4d0c6;}}
    .ck-s{{background:#fff1ee;border-color:#e8b4ac;color:#b3402e;}}
    .ck-a{{background:#fff6e8;border-color:#e8d0a4;}}
    .ck-b{{background:#f3f6f6;border-color:#c5d0cf;color:#497a78;}}
    .ck-strategy-panel{{margin:10px 0 18px;border:1px solid #d4d0c6;border-radius:8px;background:#fbfaf7;overflow:hidden;}}
    .ck-strategy-head{{display:flex;align-items:baseline;gap:10px;padding:10px 14px;border-bottom:1px solid #ebe8e1;background:#f7f5f0;}}
    .ck-strategy-head span{{font-weight:750;color:#1c1b19;}}
    .ck-strategy-head em{{font-style:normal;color:#6b6860;font-size:.78rem;}}
    .ck-strategy{{list-style:none;margin:0;padding:8px 12px 12px;display:grid;gap:8px;}}
    .ck-strategy li{{display:grid;grid-template-columns:34px minmax(0,1fr);gap:10px;align-items:start;padding:9px 10px;border:1px solid #ebe8e1;border-radius:8px;background:#fff;}}
    .ck-strategy-no{{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#497a78;color:#fff;font-size:.72rem;font-weight:800;line-height:1;}}
    .ck-strategy-text{{font-size:.9rem;line-height:1.65;color:#2c2a26;}}
    .ck-action{{margin:8px 0 6px;}}
    .ck-progress{{margin:0 0 12px;padding:11px 12px;border:1px solid #d4d0c6;border-radius:8px;background:#fbfaf7;}}
    .ck-progress-top{{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;font-size:.88rem;}}
    .ck-progress-top span{{color:#6b6860;font-size:.82rem;}}
    .ck-progress-track{{height:9px;border-radius:999px;background:#ebe8e1;overflow:hidden;}}
    .ck-progress-track span{{display:block;height:100%;border-radius:999px;background:#497a78;transition:width .18s ease;}}
    .ck-action-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 14px;}}
    .ck-stage{{display:grid;gap:6px;text-align:left;padding:12px 12px 14px;border:1px solid #d4d0c6;border-radius:12px;background:#fbfaf7;cursor:pointer;min-height:168px;}}
    .ck-stage.is-on{{background:#fff;border-color:#b3402e;box-shadow:0 0 0 1px #b3402e33;}}
    .ck-stage-no{{width:22px;height:22px;border-radius:50%;background:#efece4;display:inline-flex;align-items:center;justify-content:center;font-size:.78rem;font-weight:700;}}
    .ck-stage.is-on .ck-stage-no{{background:#b3402e;color:#fff;}}
    .ck-stage-title{{font-weight:700;font-size:.98rem;}}
    .ck-stage-sub,.ck-stage-sum{{color:#6b6860;font-size:.78rem;line-height:1.45;}}
    .ck-stage-count{{font-size:.76rem;color:#3a3832;font-weight:650;}}
    .ck-action-detail{{border:1px solid #ebe8e1;border-radius:12px;padding:14px 16px;background:#fff;}}
    .ck-action-detail[hidden]{{display:none;}}
    .ck-phase{{margin:12px 0 18px;}}
    .ck-phase h4{{margin:0 0 8px;}}
    .ck-task{{margin:10px 0;padding:10px 12px;border:1px solid #ebe8e1;border-radius:8px;background:#fbfaf7;}}
    .ck-meta,.ck-k{{font-size:.86rem;color:#6b6860;margin:8px 0 4px;}}
    .ck-k{{font-weight:650;color:#3a3832;}}
    .ck-task-list{{list-style:none;margin:0 0 8px;padding:0;display:grid;gap:6px;}}
    .ck-task-list li{{margin:0;line-height:1.65;}}
    .ck-task-list label{{display:grid;grid-template-columns:16px minmax(0,1fr);gap:8px;align-items:start;cursor:pointer;}}
    .ck-task-list input{{width:15px;height:15px;margin:5px 0 0;accent-color:#497a78;cursor:pointer;}}
    .ck-task-list input:checked + span{{color:#6b6860;text-decoration:line-through;text-decoration-thickness:1px;}}
    .ck-check{{margin:0 0 8px;padding-left:1.2em;}}
    .ck-check li{{margin:3px 0;}}
    @media(max-width:860px){{.ck-action-grid{{grid-template-columns:1fr 1fr}}}}
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
    """动态表格行：携带排序/过滤属性 + 掌握度勾选 + 行内详情（点击展开）。"""
    name = _clean(card.get("name"))
    kid = _clean(card.get("id")) or _clean(card.get("kp_id")) or name
    grade = str(card.get("session_priority") or "")
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
    explain = _clean(card.get("explain")) or ""
    method = "；".join(_as_list(card.get("method_steps"))) or ""
    pitfalls = "；".join(_as_list(card.get("pitfalls"))) or ""
    detail = explain[:200] if explain else ""
    if method:
        detail += f"<br>方法：{escape(method[:120], quote=False)}"
    if pitfalls:
        detail += f"<br>易错：{escape(pitfalls[:120], quote=False)}"
    return (
        f'<tr data-id="{escape(kid, quote=False)}" data-grade="{escape(grade, quote=False)}" data-name="{escape(name, quote=False)}" '
        f'data-chapter="{escape(chapter, quote=False)}" data-type="{escape(ktype, quote=False)}" '
        f'data-importance="{importance}" data-difficulty="{difficulty}">'
        f'<td><input type="checkbox" class="ck-mastery" data-name="{escape(name, quote=False)}"></td>'
        f'<td>{escape(_grade_label(card), quote=False)}</td>'
        f'<td class="ck-kp-name">{escape(name, quote=False)}'
        f'<div class="ck-row-preview">{escape(preview[:70], quote=False)}</div></td>'
        f'<td><span class="ck-stars">{importance_stars(card)}</span></td>'
        f'<td>{difficulty}</td>'
        f'<td>{escape(chapter, quote=False)}</td>'
        f'<td class="ck-row-detail" hidden>{detail}</td>'
        "</tr>"
    )


def _overview_html(overview: dict[str, Any]) -> str:
    bar_items = [i for i in (overview.get("bar_items") or []) if isinstance(i, dict)]
    total = float(overview.get("total_value") or 0) or 1.0
    rows = ['<div class="ck-bar-panel">']
    rows.append(
        '<div class="ck-overview-title">'
        '<span>优先复习排序</span>'
        '<span class="ck-overview-hint">按复习价值与重点信号计算占比（点击可联动筛选下方表格）</span>'
        '</div>'
    )
    if not bar_items:
        rows.append('<p class="ck-note">暂无可展示的复习重点。</p>')
    for item in bar_items:
        value = float(item.get("value") or 0)
        pct = max(0.1, min(100.0, value / total * 100))
        grade = str(item.get("session_priority") or "B")
        label = _clean(item.get("name"))
        reason = _clean(item.get("reason"))
        chapter = _clean(item.get("chapter"))
        source_ids_list = [str(x) for x in (item.get("source_node_ids") or []) if x]
        source_ids = " ".join(source_ids_list)
        count_desc = f"包含 {len(source_ids_list)} 个考点" if len(source_ids_list) > 1 else ""
        tooltip_parts = [f"复习占比：{pct:.1f}%", f"档位：{_GRADE.get(grade, '简要')} ({grade})"]
        if chapter:
            tooltip_parts.append(f"章节：{chapter}")
        if reason:
            tooltip_parts.append(f"依据：{reason}")
        if count_desc:
            tooltip_parts.append(count_desc)
        tooltip = " ｜ ".join(tooltip_parts)

        grade_class = f"ck-grade-{grade.lower()}"
        rows.append(
            f'<button type="button" class="ck-bar-item {grade_class}" '
            f'data-grade="{escape(grade, quote=True)}" '
            f'data-source-ids="{escape(source_ids, quote=True)}" '
            f'title="{escape(tooltip, quote=True)}">'
            '<div class="ck-bar-top">'
            f'<span class="ck-pill {grade_class}">{escape(_GRADE.get(grade, "简要"), quote=False)} {grade}</span>'
            f'<span class="ck-bar-name">{escape(label, quote=False)}</span>'
            f'<span class="ck-bar-pct">{pct:.1f}%</span>'
            '</div>'
            '<div class="ck-bar-track">'
            f'<span class="ck-bar-fill {grade_class}" style="width:{pct:.1f}%"></span>'
            '</div>'
            '<div class="ck-bar-bottom">'
            f'<span class="ck-bar-meta">{escape(chapter or "通用章节", quote=False)}'
            + (f' · {escape(reason, quote=False)}' if reason else '')
            + '</span>'
            + (f'<span class="ck-bar-count">{count_desc}</span>' if count_desc else '')
            + '</div>'
            '</button>'
        )
    rows.append("</div>")
    return "".join(rows)


def _review_dynamic_script(overview: dict[str, Any]) -> str:
    """复习结构总览交互脚本：条形图/Treemap 过滤 / 排序 / 展开 / 掌握度勾选。

    使用 __OVERVIEW__ 占位符注入数据，避免 f-string 与 JS 花括号冲突。
    """
    import json as _json

    data = _json.dumps(overview, ensure_ascii=False).replace("</", "<\\/")
    template = """<script>
(function () {
  const OVERVIEW = __OVERVIEW__;
  const wrap = document.getElementById('ck-review');
  if (!wrap) return;
  const table = document.getElementById('ck-main-table');
  const rows = table ? Array.from(table.tBodies[0].rows) : [];
  const fGrade = document.getElementById('ck-f-grade');
  const fChapter = document.getElementById('ck-f-chapter');
  const fType = document.getElementById('ck-f-type');
  let gradeFilter = '', chapterFilter = '', typeFilter = '', sourceFilter = [];

  function applyFilters() {
    if (!table) return;
    rows.forEach((row) => {
      const okGrade = !gradeFilter || row.getAttribute('data-grade') === gradeFilter;
      const okChapter = !chapterFilter || row.getAttribute('data-chapter') === chapterFilter;
      const okType = !typeFilter || row.getAttribute('data-type') === typeFilter;
      const name = row.getAttribute('data-id') || row.getAttribute('data-name') || '';
      const okSource = !sourceFilter.length || sourceFilter.indexOf(name) >= 0;
      row.style.display = (okGrade && okChapter && okType && okSource) ? '' : 'none';
    });
  }

  function selectOverviewItem(el) {
    const ids = String(el.getAttribute('data-source-ids') || '').split(/\\s+/).filter(Boolean);
    sourceFilter = ids;
    gradeFilter = el.getAttribute('data-grade') || '';
    if (fGrade) fGrade.value = gradeFilter;
    wrap.querySelectorAll('.ck-bar-item').forEach((x) => x.classList.toggle('is-on', x === el));
    applyFilters();
  }

  wrap.querySelectorAll('.ck-bar-item').forEach((el) => {
    el.addEventListener('click', () => selectOverviewItem(el));
  });

  if (fGrade) fGrade.addEventListener('change', () => { gradeFilter = fGrade.value; sourceFilter = []; applyFilters(); });
  if (fChapter) fChapter.addEventListener('change', () => { chapterFilter = fChapter.value; sourceFilter = []; applyFilters(); });
  if (fType) fType.addEventListener('change', () => { typeFilter = fType.value; sourceFilter = []; applyFilters(); });

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
    return template.replace("__OVERVIEW__", data)
