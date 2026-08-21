"""catalog 展示：简要说明 + 保存复习清单要用的目录 JSON。"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from tools.knowledge.config import PROJECT_ROOT

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


def display_catalog_path(path: str | Path) -> str:
    target = Path(path)
    try:
        return target.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(target)


def _tree_counts(draft: dict[str, Any]) -> tuple[int, int, int]:
    chapters = 0
    topics = 0
    points = 0
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        chapters += 1
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            topics += 1
            points += sum(
                1
                for p in topic.get("knowledge_points") or []
                if isinstance(p, dict) and _clean(p.get("name"))
            )
    return chapters, topics, points


def _change_lines(draft: dict[str, Any]) -> list[str]:
    if _clean(draft.get("mode")) != "incremental_update":
        return []
    lines: list[str] = []
    for title, key in (
        ("新增章节", "added_chapters"),
        ("新增主题", "added_topics"),
        ("新增知识点", "added_knowledge_points"),
        ("更新知识点", "updated_knowledge_points"),
        ("合并节点", "merged_nodes"),
    ):
        items = _as_list(draft.get(key))
        if not items:
            continue
        if len(items) > 6:
            lines.append(f"{title} {len(items)} 项：{'、'.join(items[:6])} 等")
        else:
            lines.append(f"{title}：{'、'.join(items)}")
    return lines


def _tree_rows(draft: dict[str, Any]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        cname = _clean(chapter.get("name"))
        if cname:
            rows.append((0, cname))
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            tname = _clean(topic.get("name"))
            if tname:
                rows.append((1, tname))
            names = [
                _clean(p.get("name"))
                for p in topic.get("knowledge_points") or []
                if isinstance(p, dict) and _clean(p.get("name"))
            ]
            if names:
                rows.append((2, "、".join(names)))
    return rows


def build_catalog_markdown(draft: dict[str, Any], *, saved_path: str = "") -> str:
    draft = normalize_catalog_draft(draft)
    course = _clean(draft.get("course")) or "课程知识目录"
    version = _clean(draft.get("version")) or "1"
    mode_label = "增量更新" if _clean(draft.get("mode")) == "incremental_update" else "首次生成"
    n_ch, n_tp, n_kp = _tree_counts(draft)
    lines = [
        f"# {course} · 知识目录已保存",
        "",
    ]
    if saved_path:
        lines.append(f"目录文件：`{saved_path}`")
        lines.append("")
    lines.append(f"版本 v{version} · {mode_label}。共 {n_ch} 章、{n_tp} 个主题、{n_kp} 个知识点。")
    lines.append("这份 JSON 供复习清单自动读取，详细字段不用在这里展开。")
    lines.append("")
    changes = _change_lines(draft)
    if changes:
        lines.append("本次变更：")
        lines.extend(f"- {item}" for item in changes)
        lines.append("")
    if not (draft.get("chapters") or []):
        lines.append("这次没有整理出可用目录，已有目录文件不会被空结果覆盖。")
        return "\n".join(lines).strip() + "\n"
    lines.append("## 目录")
    lines.append("")
    for depth, text in _tree_rows(draft):
        lines.append(f"{'  ' * depth}- {text}")
    return "\n".join(lines).strip() + "\n"


def build_catalog_html(draft: dict[str, Any], *, saved_path: str = "") -> str:
    draft = normalize_catalog_draft(draft)
    course = escape(_clean(draft.get("course")) or "课程知识目录", quote=False)
    version = escape(_clean(draft.get("version")) or "1", quote=False)
    mode_label = "增量更新" if _clean(draft.get("mode")) == "incremental_update" else "首次生成"
    n_ch, n_tp, n_kp = _tree_counts(draft)
    rows = [
        "<style>",
        ".cat-doc{background:#fff;border:1px solid #d4d0c6;border-radius:10px;padding:22px 28px;line-height:1.7;}",
        ".cat-doc h1{margin:0 0 12px;font-size:1.45rem;}",
        ".cat-doc h2{margin:18px 0 8px;font-size:1.05rem;}",
        ".cat-doc p{margin:0 0 8px;}",
        ".cat-meta{font-size:.86rem;color:#6b6860;}",
        ".cat-doc ul{margin:6px 0 0;padding-left:1.25em;}",
        ".cat-doc li{margin:2px 0;}",
        ".cat-path{font-family:ui-monospace,Consolas,monospace;font-size:.86rem;}",
        "</style>",
        '<div class="cat-doc">',
        f"<h1>{course} · 知识目录已保存</h1>",
    ]
    if saved_path:
        rows.append(
            f'<p>目录文件：<span class="cat-path">{escape(saved_path, quote=False)}</span></p>'
        )
    rows.append(
        f'<p class="cat-meta">版本 v{version} · {escape(mode_label, quote=False)}。'
        f"共 {n_ch} 章、{n_tp} 个主题、{n_kp} 个知识点。</p>"
    )
    rows.append("<p class=\"cat-meta\">这份 JSON 供复习清单自动读取，详细字段不用在这里展开。</p>")
    changes = _change_lines(draft)
    if changes:
        rows.append("<h2>本次变更</h2><ul>")
        rows.extend(f"<li>{escape(item, quote=False)}</li>" for item in changes)
        rows.append("</ul>")
    if not (draft.get("chapters") or []):
        rows.append("<p>这次没有整理出可用目录，已有目录文件不会被空结果覆盖。</p></div>")
        return "\n".join(rows)
    rows.append("<h2>目录</h2>")
    rows.extend(_html_tree(draft))
    rows.append("</div>")
    return "\n".join(rows)


def _html_tree(draft: dict[str, Any]) -> list[str]:
    rows = ["<ul>"]
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        cname = _clean(chapter.get("name"))
        if not cname:
            continue
        rows.append(f"<li>{escape(cname, quote=False)}")
        topic_items: list[str] = []
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            tname = _clean(topic.get("name"))
            names = [
                _clean(p.get("name"))
                for p in topic.get("knowledge_points") or []
                if isinstance(p, dict) and _clean(p.get("name"))
            ]
            if tname and names:
                topic_items.append(
                    f"<li>{escape(tname, quote=False)}"
                    f"<ul><li>{escape('、'.join(names), quote=False)}</li></ul></li>"
                )
            elif tname:
                topic_items.append(f"<li>{escape(tname, quote=False)}</li>")
        if topic_items:
            rows.append("<ul>")
            rows.extend(topic_items)
            rows.append("</ul>")
        rows.append("</li>")
    rows.append("</ul>")
    return rows


def attach_catalog_artifacts(state: dict[str, Any]) -> None:
    from tools.domain_engine_text import line

    from .gather import subject_from_context, user_id_from_context
    from .store import save_catalog

    sub = line(state, "catalog")
    draft = normalize_catalog_draft(dict(sub.get("draft") or {}))
    extra = str((state.get("line_extra") or {}).get("catalog") or "")
    transcript = str(state.get("transcript") or "")
    context = f"{transcript}\n{extra}"
    saved = save_catalog(
        user_id=user_id_from_context(context),
        subject=subject_from_context(context),
        draft=draft,
    )
    shown = display_catalog_path(saved)
    draft["catalog_html"] = build_catalog_html(draft, saved_path=shown)
    sub["rendered"] = build_catalog_markdown(draft, saved_path=shown)
    sub["draft"] = draft
    sub["structure"] = draft.get("chapters") or []
