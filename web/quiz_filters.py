"""自测题筛选项：难度和题型可选；科目/年级/版本从笔记对齐的知识点反推。"""
from __future__ import annotations

from typing import Any

from tools.exercise_search.catalog import default_catalog
from tools.exercise_search.match import (
    build_spec,
    collect_terms,
    infer_course,
    match_keypoints,
)

NONE = "不指定"
_GENERIC_QTYPES = ["单选题", "多选题", "填空题", "解答题", "判断题"]


def _catalog():
    return default_catalog()


def qtype_choices(subject: str = "") -> list[str]:
    course = _catalog().course_by_name(subject) if _usable(subject) else None
    if course is None:
        return [NONE] + list(_GENERIC_QTYPES)
    roots: list[str] = []
    children: list[str] = []
    seen: set[str] = set()
    for item in _catalog().types_for_subject(course.subject_id):
        if item.name in seen:
            continue
        seen.add(item.name)
        if item.parent_name:
            children.append(item.name)
        else:
            roots.append(item.name)
    return [NONE] + roots + children


def _usable(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text != NONE


def _keep(current: object, choices: list[str]) -> str:
    text = str(current or "").strip()
    if text in choices:
        return text
    return NONE


def resolve_filters(
    notes: str = "",
    qtype: str = "",
) -> dict[str, Any]:
    """按笔记对齐知识点，反推年级/版本，并刷新题型列表。"""
    catalog = _catalog()
    spec = None
    if (notes or "").strip():
        spec = build_spec(catalog, notes=notes, qtype=qtype if _usable(qtype) else "")
    course = spec.course if spec is not None else infer_course(catalog, notes=notes)
    display = course.name if course is not None else ""
    types = qtype_choices(display)
    hint = ""
    if spec is not None and spec.keypoints:
        names = "、".join(item.name for item in spec.keypoints[:4])
        bits = [spec.course.name if spec.course else ""]
        if spec.grade_label:
            bits.append(spec.grade_label)
        if spec.edition_label:
            bits.append(spec.edition_label)
        aligned = " · ".join(item for item in bits if item)
        hint = f"已按笔记对齐知识点：{names}"
        if aligned:
            hint += f" → {aligned}"
    elif course is not None and (notes or "").strip():
        hits = match_keypoints(catalog, course, notes, collect_terms(notes))
        if hits:
            names = "、".join(item.name for item in hits[:4])
            hint = f"已按笔记对齐：{course.name} · 知识点 {names}"
        else:
            hint = f"已按笔记对齐科目：{course.name}"
    return {
        "qtype": _keep(qtype, types),
        "qtype_choices": types,
        "hint": hint,
    }
