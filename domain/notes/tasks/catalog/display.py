"""catalog 展示：简要说明 + 保存复习清单要用的目录 JSON。"""
from __future__ import annotations

import json
import re
from typing import Any

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


_HEADING_PREFIX_RE = re.compile(
    r"^(?:"
    r"[一二三四五六七八九十百]+[、.．:：\s]\s*"
    r"|[（(][一二三四五六七八九十百\d]+[）)][、.．:：\s]*"
    r"|\d+(?:\.\d+)*[、.．:：\s]\s*"
    r"|[IVXLCDMivxlcdm]+[、.．:：\s]\s*"
    r"|第[0-9一二三四五六七八九十百]+[章节部分讲课项点步阶段周单元][、.．:：\s]*"
    r")"
)
_NOISE_TITLE_RE = re.compile(
    r"(华中科技大学|科技大学|大学|university|wuhan|hubei|tel[:：]?|"
    r"印刷厂|附属印刷|第\s*\d+\s*页|^\s*页\s*$)",
    re.I,
)
_NOISE_SHORT_TITLES = {"科技", "大学", "学院", "学校", "页", "目录"}


def strip_heading_prefix(text: object) -> str:
    """剔除章节/主题/知识点名称中的序号前缀（如：'四、xxxxx'、'（五）xxxx'、'1. xxxx'、'第3节 xxxx'）。"""
    raw = " ".join(str(text or "").split()).strip()
    if not raw:
        return ""
    cleaned = raw
    while True:
        m = _HEADING_PREFIX_RE.match(cleaned)
        if m:
            remainder = cleaned[m.end():].strip()
            if remainder:
                cleaned = remainder
                continue
        break
    return cleaned or raw


def _clean(text: object) -> str:
    return strip_heading_prefix(text)


def _compact(text: object) -> str:
    return re.sub(r"[\s:：,，。；;、（）()\[\]【】《》“”\"'·\-—_]+", "", str(text or "").lower())


def _is_noise_title(text: object) -> bool:
    raw = _clean(text)
    if not raw:
        return True
    if _compact(raw) in {_compact(item) for item in _NOISE_SHORT_TITLES}:
        return True
    return bool(_NOISE_TITLE_RE.search(raw))


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


def _tree_rows(draft: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    visible_chapters: list[tuple[str, list[dict[str, Any]]]] = []
    for chapter in draft.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        cname = _clean(chapter.get("name"))
        chapter_noise = _is_noise_title(cname)
        topics = [topic for topic in chapter.get("topics") or [] if isinstance(topic, dict)]
        if cname and not chapter_noise:
            visible_chapters.append((cname, topics))
        elif topics:
            visible_chapters.append(("", topics))

    for ch_idx, (cname, topics) in enumerate(visible_chapters):
        ch_last = ch_idx == len(visible_chapters) - 1
        ch_prefix = "└─ " if ch_last else "├─ "
        child_prefix = "   " if ch_last else "│  "
        if cname:
            rows.append(f"{ch_prefix}{cname}")
        else:
            child_prefix = ""
        visible_topics: list[tuple[str, list[str], bool]] = []
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            tname = _clean(topic.get("name"))
            if _is_noise_title(tname):
                tname = ""
            names = [
                _clean(p.get("name"))
                for p in topic.get("knowledge_points") or []
                if isinstance(p, dict)
                and _clean(p.get("name"))
                and not _is_noise_title(p.get("name"))
            ]
            uniq_names: list[str] = []
            seen: set[str] = set()
            for name in names:
                key = _compact(name)
                if not key or key in seen:
                    continue
                seen.add(key)
                uniq_names.append(name)
            # 同名容器是 catalog 内部层级，不在 text 里重复展示成两行。
            same_single = bool(tname and len(uniq_names) == 1 and _compact(tname) == _compact(uniq_names[0]))
            if tname or uniq_names:
                visible_topics.append((tname, uniq_names, same_single))
        for tp_idx, (tname, uniq_names, same_single) in enumerate(visible_topics):
            tp_last = tp_idx == len(visible_topics) - 1
            tp_prefix = "└─ " if tp_last else "├─ "
            kp_prefix = "   " if tp_last else "│  "
            if same_single:
                rows.append(f"{child_prefix}{tp_prefix}{uniq_names[0]}")
                continue
            if tname:
                rows.append(f"{child_prefix}{tp_prefix}{tname}")
            if uniq_names:
                names_line = "、".join(uniq_names)
                if tname:
                    rows.append(f"{child_prefix}{kp_prefix}└─ {names_line}")
                else:
                    rows.append(f"{child_prefix}{tp_prefix}{names_line}")
    return rows


def build_catalog_markdown(draft: dict[str, Any]) -> str:
    draft = normalize_catalog_draft(draft)
    course = _clean(draft.get("course")) or "课程知识目录"
    lines = [
        f"# {course} · 知识目录",
        "",
    ]
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
    lines.extend(_tree_rows(draft))
    return "\n".join(lines).strip() + "\n"


def attach_catalog_artifacts(state: dict[str, Any]) -> None:
    from tools.domain_engine_text import line

    from .gather import (
        backfill_catalog_trace,
        complement_catalog_coverage,
        compute_catalog_signals,
        subject_from_context,
        trim_catalog_scale,
        user_id_from_context,
    )
    from .merge import compact_catalog_granularity
    from .store import save_catalog

    sub = line(state, "catalog")
    draft = normalize_catalog_draft(dict(sub.get("draft") or {}))
    extra = str((state.get("line_extra") or {}).get("catalog") or "")
    transcript = str(state.get("transcript") or "")
    context = f"{transcript}\n{extra}"
    # 输出侧流水线(均零 LLM):候选补缺 → 规模合并 → 溯源/老师回填 → 重要性计算
    draft = complement_catalog_coverage(draft, context)
    draft = trim_catalog_scale(draft, context)
    draft = backfill_catalog_trace(draft, context)
    draft = compact_catalog_granularity(draft)
    draft = compute_catalog_signals(draft)
    save_catalog(
        user_id=user_id_from_context(context),
        subject=subject_from_context(context),
        draft=draft,
    )
    sub["rendered"] = build_catalog_markdown(draft)
    sub["draft"] = draft
    sub["structure"] = draft.get("chapters") or []
