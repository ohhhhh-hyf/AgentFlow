"""catalog 展示：目录树 Markdown / HTML，并补齐后续复习清单要用的索引字段。"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

_IMPORTANCE = {
    "1": "普通",
    "2": "次重点",
    "3": "重要",
    "4": "很重要",
    "5": "核心",
}
_DIFFICULTY = {
    "1": "简单",
    "2": "较简单",
    "3": "中等",
    "4": "较难",
    "5": "很难",
}
_EMPHASIS = {
    "0": "老师未提及",
    "1": "老师提及",
    "2": "老师明确强调",
    "3": "老师反复强调",
}
_COVERAGE = {
    "none": "笔记未覆盖",
    "mentioned": "笔记提及",
    "partial": "笔记部分覆盖",
    "detailed": "笔记较完整",
}
_TYPE = {
    "concept": "概念",
    "formula": "公式",
    "theorem": "定理",
    "method": "方法",
    "application": "应用",
    "mixed": "综合",
}
_FOUNDATION = {
    "1": "很少作前置",
    "2": "较弱前置",
    "3": "一般前置",
    "4": "重要前置",
    "5": "核心基础",
}
_EXAM = {
    "none": "无考试信号",
    "weak": "考试信号弱",
    "medium": "考试信号中",
    "strong": "考试信号强",
}
_RELATION = {
    "alternative": "替代方法",
    "used_with": "配合使用",
    "easily_confused": "容易混淆",
    "derived_from": "推导关系",
}
_PRACTICE = {
    "recall": "记忆复述",
    "distinguish": "概念辨析",
    "calculate": "计算训练",
    "prove": "证明训练",
    "apply": "应用训练",
    "choose_method": "方法选择",
    "mixed": "综合训练",
}
_CRITERIA = {
    "can_recall": "能复述",
    "can_explain": "能解释",
    "can_distinguish": "能辨析",
    "can_apply": "能应用",
    "can_choose_method": "能选题法",
    "can_solve_standard": "能做标准题",
    "can_solve_variant": "能做变形题",
    "can_prove": "能完成证明",
}
_ROLE = {
    "foundation": "基础前置",
    "core_concept": "核心概念",
    "core_method": "核心方法",
    "application": "应用知识",
    "integration": "综合连接",
}
_RISK = {
    "condition_check": "条件易漏",
    "concept_confusion": "概念易混",
    "formula_misuse": "公式误用",
    "method_selection": "方法易错",
    "calculation_error": "计算易错",
    "proof_format": "证明书写",
    "boundary_case": "边界遗漏",
}


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_clean(x) for x in value if _clean(x)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _related(value: object) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not isinstance(value, list):
        return out
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "relation": "used_with"})
            continue
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        rel = str(item.get("relation") or "used_with")
        if rel not in _RELATION:
            rel = "used_with"
        out.append({"name": name, "relation": rel})
    return out


def draft_from_context(approved_context: str) -> dict[str, Any]:
    blob = approved_context or ""
    for marker in ("已批准知识目录草稿：", "已批准catalog草稿："):
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


def normalize_catalog_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """补 id / chapter / topic，方便后续复习清单当索引用。"""
    data = dict(draft or {})
    chapters = data.get("chapters") or []
    if not isinstance(chapters, list):
        return data
    seq = 1
    used: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        cname = _clean(chapter.get("name"))
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            tname = _clean(topic.get("name"))
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                kid = _clean(point.get("id"))
                if not kid or kid in used:
                    while f"kp_{seq:03d}" in used:
                        seq += 1
                    kid = f"kp_{seq:03d}"
                    seq += 1
                used.add(kid)
                point["id"] = kid
                if not _clean(point.get("chapter")):
                    point["chapter"] = cname
                if not _clean(point.get("topic")):
                    point["topic"] = tname
                point["related_points"] = _related(point.get("related_points"))
                point["practice_type"] = [x for x in _as_list(point.get("practice_type")) if x in _PRACTICE]
                point["completion_criteria"] = [
                    x for x in _as_list(point.get("completion_criteria")) if x in _CRITERIA
                ]
                role = str(point.get("learning_role") or "").strip()
                point["learning_role"] = role if role in _ROLE else ""
                point["risk_tags"] = [x for x in _as_list(point.get("risk_tags")) if x in _RISK]
    data["chapters"] = chapters
    return data


def _point_marks(point: dict[str, Any]) -> str:
    bits = [
        _TYPE.get(str(point.get("knowledge_type") or ""), ""),
        _IMPORTANCE.get(str(point.get("importance") or ""), ""),
        _DIFFICULTY.get(str(point.get("difficulty") or ""), ""),
        _EMPHASIS.get(str(point.get("teacher_emphasis") or ""), ""),
        _EXAM.get(str(point.get("exam_signal") or ""), ""),
        _FOUNDATION.get(str(point.get("foundational_level") or ""), ""),
        _COVERAGE.get(str(point.get("note_coverage") or ""), ""),
        _ROLE.get(str(point.get("learning_role") or ""), ""),
    ]
    practice = "、".join(_PRACTICE[x] for x in _as_list(point.get("practice_type")) if x in _PRACTICE)
    if practice:
        bits.append(practice)
    return " · ".join(b for b in bits if b)


def _index_rows(draft: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict) or not _clean(point.get("name")):
                    continue
                rows.append(
                    {
                        "id": _clean(point.get("id")),
                        "name": _clean(point.get("name")),
                        "type": _TYPE.get(str(point.get("knowledge_type") or ""), str(point.get("knowledge_type") or "")),
                        "importance": _IMPORTANCE.get(str(point.get("importance") or ""), ""),
                        "difficulty": _DIFFICULTY.get(str(point.get("difficulty") or ""), ""),
                        "exam": _EXAM.get(str(point.get("exam_signal") or ""), ""),
                        "base": _FOUNDATION.get(str(point.get("foundational_level") or ""), ""),
                        "role": _ROLE.get(str(point.get("learning_role") or ""), ""),
                    }
                )
    return rows


def build_catalog_markdown(draft: dict[str, Any]) -> str:
    draft = normalize_catalog_draft(draft)
    course = _clean(draft.get("course")) or "课程知识目录"
    version = _clean(draft.get("version")) or "1"
    mode = _clean(draft.get("mode")) or "build"
    mode_label = "增量更新" if mode == "incremental_update" else "首次生成"
    lines = [
        f"# {course} · 知识目录",
        "",
        f"版本 v{version} · {mode_label}",
        "",
    ]
    changes = []
    for title, key in (
        ("新增章节", "added_chapters"),
        ("新增主题", "added_topics"),
        ("新增知识点", "added_knowledge_points"),
        ("更新知识点", "updated_knowledge_points"),
        ("合并节点", "merged_nodes"),
    ):
        items = _as_list(draft.get(key))
        if items:
            changes.append(f"- {title}：{'、'.join(items)}")
    if changes:
        lines.extend(["## 本次变更", ""] + changes + [""])
    index = _index_rows(draft)
    if index:
        lines.extend(
            [
                "## 知识点索引",
                "",
                "| ID | 名称 | 类型 | 重点 | 难度 | 考试信号 | 基础性 | 学习角色 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in index:
            lines.append(
                f"| {row['id']} | {row['name']} | {row['type']} | {row['importance']} | "
                f"{row['difficulty']} | {row['exam']} | {row['base']} | {row['role']} |"
            )
        lines.append("")
    chapters = draft.get("chapters") or []
    if not chapters:
        lines.append("暂未从资料中整理出稳定目录。")
        return "\n".join(lines)
    for ci, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        cname = _clean(chapter.get("name")) or f"第{ci}章"
        lines.append(f"## {ci}. {cname}")
        for ti, topic in enumerate(chapter.get("topics") or [], start=1):
            if not isinstance(topic, dict):
                continue
            tname = _clean(topic.get("name")) or f"主题{ti}"
            lines.append(f"### {ci}.{ti} {tname}")
            for pi, point in enumerate(topic.get("knowledge_points") or [], start=1):
                if not isinstance(point, dict):
                    continue
                pname = _clean(point.get("name"))
                if not pname:
                    continue
                kid = _clean(point.get("id"))
                marks = _point_marks(point)
                title = f"#### {ci}.{ti}.{pi} {pname}"
                if kid:
                    title += f"  `{kid}`"
                if marks:
                    title += f"  （{marks}）"
                lines.append(title)
                alias = "、".join(_as_list(point.get("aliases")))
                if alias:
                    lines.append(f"- 别名：{alias}")
                items = _as_list(point.get("knowledge_items"))
                focus = set(_as_list(point.get("teacher_focus_items")))
                covered = set(_as_list(point.get("note_covered_items")))
                if items:
                    for item in items:
                        tags = []
                        if item in focus:
                            tags.append("老师点到")
                        if item in covered:
                            tags.append("笔记有")
                        suffix = f"（{' · '.join(tags)}）" if tags else ""
                        lines.append(f"- {item}{suffix}")
                missing = _as_list(point.get("note_missing_items"))
                if missing:
                    lines.append(f"- 笔记未写到：{'、'.join(missing)}")
                prereq = _as_list(point.get("prerequisites"))
                if prereq:
                    lines.append(f"- 前置：{'、'.join(prereq)}")
                practice = [_PRACTICE[x] for x in _as_list(point.get("practice_type")) if x in _PRACTICE]
                if practice:
                    lines.append(f"- 怎么练：{'、'.join(practice)}")
                criteria = [_CRITERIA[x] for x in _as_list(point.get("completion_criteria")) if x in _CRITERIA]
                if criteria:
                    lines.append(f"- 过关：{'、'.join(criteria)}")
                risks = [_RISK[x] for x in _as_list(point.get("risk_tags")) if x in _RISK]
                if risks:
                    lines.append(f"- 风险：{'、'.join(risks)}")
                related = _related(point.get("related_points"))
                if related:
                    bits = [
                        f"{row['name']}（{_RELATION.get(row['relation'], row['relation'])}）"
                        for row in related
                    ]
                    lines.append(f"- 关联：{'；'.join(bits)}")
                evidence = _as_list(point.get("evidence"))
                if evidence:
                    lines.append(f"- 依据：{'；'.join(evidence)}")
            lines.append("")
        lines.append("")
    unmatched = _as_list(draft.get("unmatched_content"))
    uncertain = _as_list(draft.get("uncertain_nodes"))
    if unmatched:
        lines.extend(["## 未归入目录的内容", ""])
        lines.extend(f"- {item}" for item in unmatched)
        lines.append("")
    if uncertain:
        lines.extend(["## 暂不确定的节点", ""])
        lines.extend(f"- {item}" for item in uncertain)
    return "\n".join(lines).strip() + "\n"


def _badge(text: str, kind: str) -> str:
    return f'<span class="cat-badge cat-{kind}">{escape(text, quote=False)}</span>'


def build_catalog_html(draft: dict[str, Any]) -> str:
    draft = normalize_catalog_draft(draft)
    course = escape(_clean(draft.get("course")) or "课程知识目录", quote=False)
    rows = [
        "<style>",
        ".cat-doc{background:#fff;border:1px solid #d4d0c6;border-radius:10px;padding:22px 28px;line-height:1.7;}",
        ".cat-doc h1{margin:0 0 18px;font-size:1.7rem;}",
        ".cat-doc h2{margin:22px 0 10px;font-size:1.2rem;}",
        ".cat-doc h3{margin:16px 0 8px;font-size:1.05rem;color:#3a3832;}",
        ".cat-point{margin:10px 0 14px;padding:10px 12px;border:1px solid #ebe8e1;border-radius:8px;background:#fbfaf7;}",
        ".cat-point strong{font-size:1rem;}",
        ".cat-id{font-size:.74rem;color:#9a968c;margin-left:6px;}",
        ".cat-badge{display:inline-block;margin:0 6px 4px 0;padding:1px 8px;border-radius:10px;font-size:.74rem;background:#efece4;border:1px solid #d4d0c6;}",
        ".cat-imp5{background:#fff1ee;border-color:#e8b4ac;color:#b3402e;}",
        ".cat-imp4{background:#fff6e8;border-color:#e8d0a4;}",
        ".cat-teach{background:#eef4fb;border-color:#b7c9e0;}",
        ".cat-note{background:#eef7f1;border-color:#b7d4c4;}",
        ".cat-exam{background:#f3eef8;border-color:#c9b7d8;}",
        ".cat-type{background:#eef3f8;border-color:#b7c4d4;}",
        ".cat-point ul{margin:8px 0 0;padding-left:1.2em;}",
        ".cat-meta{font-size:.78rem;color:#6b6860;margin-top:6px;}",
        ".cat-index{width:100%;border-collapse:collapse;font-size:.82rem;margin:8px 0 18px;}",
        ".cat-index th,.cat-index td{border:1px solid #d4d0c6;padding:5px 8px;text-align:left;}",
        ".cat-index th{background:#f7f5f0;}",
        "</style>",
        '<div class="cat-doc">',
        f"<h1>{course} · 知识目录</h1>",
        f'<p class="cat-meta">版本 v{escape(_clean(draft.get("version")) or "1", quote=False)} · '
        f'{escape("增量更新" if _clean(draft.get("mode")) == "incremental_update" else "首次生成", quote=False)}</p>',
    ]
    change_bits = []
    for title, key in (
        ("新增章节", "added_chapters"),
        ("新增主题", "added_topics"),
        ("新增知识点", "added_knowledge_points"),
        ("更新知识点", "updated_knowledge_points"),
        ("合并节点", "merged_nodes"),
    ):
        items = _as_list(draft.get(key))
        if items:
            change_bits.append(f"<li>{escape(title, quote=False)}：{escape('、'.join(items), quote=False)}</li>")
    if change_bits:
        rows.append("<h2>本次变更</h2><ul>" + "".join(change_bits) + "</ul>")
    index = _index_rows(draft)
    if index:
        rows.append("<h2>知识点索引</h2>")
        rows.append(
            '<table class="cat-index"><thead><tr>'
            "<th>ID</th><th>名称</th><th>类型</th><th>重点</th><th>难度</th>"
            "<th>考试信号</th><th>基础性</th><th>学习角色</th></tr></thead><tbody>"
        )
        for row in index:
            cells = [
                row["id"],
                row["name"],
                row["type"],
                row["importance"],
                row["difficulty"],
                row["exam"],
                row["base"],
                row["role"],
            ]
            rows.append("<tr>" + "".join(f"<td>{escape(c, quote=False)}</td>" for c in cells) + "</tr>")
        rows.append("</tbody></table>")
    chapters = draft.get("chapters") or []
    if not chapters:
        rows.append("<p>暂未从资料中整理出稳定目录。</p></div>")
        return "\n".join(rows)
    for ci, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            continue
        rows.append(f"<h2>{ci}. {escape(_clean(chapter.get('name')), quote=False)}</h2>")
        for ti, topic in enumerate(chapter.get("topics") or [], start=1):
            if not isinstance(topic, dict):
                continue
            rows.append(
                f"<h3>{ci}.{ti} {escape(_clean(topic.get('name')), quote=False)}</h3>"
            )
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                name = _clean(point.get("name"))
                if not name:
                    continue
                badges = []
                ktype = str(point.get("knowledge_type") or "")
                if ktype in _TYPE:
                    badges.append(_badge(_TYPE[ktype], "type"))
                imp = str(point.get("importance") or "")
                if imp in _IMPORTANCE:
                    badges.append(_badge(_IMPORTANCE[imp], "imp5" if imp == "5" else "imp4" if imp == "4" else "plain"))
                diff = str(point.get("difficulty") or "")
                if diff in _DIFFICULTY:
                    badges.append(_badge(_DIFFICULTY[diff], "plain"))
                emp = str(point.get("teacher_emphasis") or "")
                if emp in {"2", "3"}:
                    badges.append(_badge(_EMPHASIS[emp], "teach"))
                exam = str(point.get("exam_signal") or "")
                if exam in {"medium", "strong"}:
                    badges.append(_badge(_EXAM[exam], "exam"))
                base = str(point.get("foundational_level") or "")
                if base in {"4", "5"}:
                    badges.append(_badge(_FOUNDATION[base], "plain"))
                cov = str(point.get("note_coverage") or "")
                if cov in {"partial", "detailed"}:
                    badges.append(_badge(_COVERAGE[cov], "note"))
                role = str(point.get("learning_role") or "")
                if role in _ROLE:
                    badges.append(_badge(_ROLE[role], "type"))
                kid = _clean(point.get("id"))
                rows.append('<div class="cat-point">')
                rows.append(
                    f"<strong>{escape(name, quote=False)}</strong>"
                    + (f'<span class="cat-id">{escape(kid, quote=False)}</span>' if kid else "")
                    + f" {' '.join(badges)}"
                )
                aliases = _as_list(point.get("aliases"))
                if aliases:
                    rows.append(
                        f'<div class="cat-meta">别名：{escape("、".join(aliases), quote=False)}</div>'
                    )
                items = _as_list(point.get("knowledge_items"))
                focus = set(_as_list(point.get("teacher_focus_items")))
                covered = set(_as_list(point.get("note_covered_items")))
                if items:
                    lis = []
                    for item in items:
                        tags = []
                        if item in focus:
                            tags.append("老师点到")
                        if item in covered:
                            tags.append("笔记有")
                        extra = f' <span class="cat-meta">{" · ".join(tags)}</span>' if tags else ""
                        lis.append(f"<li>{escape(item, quote=False)}{extra}</li>")
                    rows.append("<ul>" + "".join(lis) + "</ul>")
                missing = _as_list(point.get("note_missing_items"))
                if missing:
                    rows.append(
                        f'<div class="cat-meta">笔记未写到：{escape("、".join(missing), quote=False)}</div>'
                    )
                prereq = _as_list(point.get("prerequisites"))
                if prereq:
                    rows.append(
                        f'<div class="cat-meta">前置：{escape("、".join(prereq), quote=False)}</div>'
                    )
                practice = [_PRACTICE[x] for x in _as_list(point.get("practice_type")) if x in _PRACTICE]
                if practice:
                    rows.append(
                        f'<div class="cat-meta">怎么练：{escape("、".join(practice), quote=False)}</div>'
                    )
                criteria = [_CRITERIA[x] for x in _as_list(point.get("completion_criteria")) if x in _CRITERIA]
                if criteria:
                    rows.append(
                        f'<div class="cat-meta">过关：{escape("、".join(criteria), quote=False)}</div>'
                    )
                risks = [_RISK[x] for x in _as_list(point.get("risk_tags")) if x in _RISK]
                if risks:
                    rows.append(
                        f'<div class="cat-meta">风险：{escape("、".join(risks), quote=False)}</div>'
                    )
                related = _related(point.get("related_points"))
                if related:
                    bits = [
                        f"{row['name']}（{_RELATION.get(row['relation'], row['relation'])}）"
                        for row in related
                    ]
                    rows.append(
                        f'<div class="cat-meta">关联：{escape("；".join(bits), quote=False)}</div>'
                    )
                evidence = _as_list(point.get("evidence"))
                if evidence:
                    rows.append(
                        f'<div class="cat-meta">依据：{escape("；".join(evidence), quote=False)}</div>'
                    )
                rows.append("</div>")
    unmatched = _as_list(draft.get("unmatched_content"))
    uncertain = _as_list(draft.get("uncertain_nodes"))
    if unmatched:
        rows.append("<h2>未归入目录的内容</h2><ul>")
        rows.extend(f"<li>{escape(x, quote=False)}</li>" for x in unmatched)
        rows.append("</ul>")
    if uncertain:
        rows.append("<h2>暂不确定的节点</h2><ul>")
        rows.extend(f"<li>{escape(x, quote=False)}</li>" for x in uncertain)
        rows.append("</ul>")
    rows.append("</div>")
    return "\n".join(rows)


def attach_catalog_artifacts(state: dict[str, Any]) -> None:
    from tools.domain_engine_text import line

    from .gather import resolve_collection, subject_from_context, user_id_from_context
    from .store import save_catalog

    sub = line(state, "catalog")
    draft = normalize_catalog_draft(dict(sub.get("draft") or {}))
    extra = str((state.get("line_extra") or {}).get("catalog") or "")
    transcript = str(state.get("transcript") or "")
    context = f"{transcript}\n{extra}"
    collection = resolve_collection(
        user_id=user_id_from_context(context),
        subject=subject_from_context(context),
    )
    save_catalog(collection, draft)
    draft["catalog_html"] = build_catalog_html(draft)
    sub["rendered"] = build_catalog_markdown(draft)
    sub["draft"] = draft
    sub["structure"] = draft.get("chapters") or []
