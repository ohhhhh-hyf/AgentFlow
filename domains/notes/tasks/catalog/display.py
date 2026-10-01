"""catalog 展示：简要说明 + 保存复习清单要用的目录 JSON。"""
from __future__ import annotations

import re
from html import escape
from typing import Any

from .gather import _is_noise_title, strip_heading_prefix
from core.graph.engine_text import scrape_draft

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
    return strip_heading_prefix(text)


def _compact(text: object) -> str:
    return re.sub(r"[\s:：,，。；;、（）()\[\]【】《》“”\"'·\-—_]+", "", str(text or "").lower())


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
    """从渲染上下文里抽出已批准草稿（实现见 domain_engine_text.scrape_draft）。"""
    return scrape_draft(approved_context, ('已批准知识目录草稿：', '已批准catalog草稿：'))


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


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value or "")))
    except (TypeError, ValueError):
        return default


def build_catalog_html(draft: dict[str, Any]) -> str:
    draft = normalize_catalog_draft(draft)
    course = _clean(draft.get("course")) or "课程知识目录"
    version = _clean(draft.get("version")) or "1"
    mode = _clean(draft.get("mode"))
    mode_text = "增量更新" if mode == "incremental_update" else "全量构建"

    chapters = draft.get("chapters") or []
    visible_chapters = [
        c
        for c in chapters
        if isinstance(c, dict)
        and _clean(c.get("name"))
        and not _is_noise_title(_clean(c.get("name")))
    ]
    total_topics = 0
    total_kps = 0
    for ch in visible_chapters:
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            tname = _clean(tp.get("name"))
            if tname and not _is_noise_title(tname):
                total_topics += 1
            for kp in tp.get("knowledge_points") or []:
                if (
                    isinstance(kp, dict)
                    and _clean(kp.get("name"))
                    and not _is_noise_title(_clean(kp.get("name")))
                ):
                    total_kps += 1

    lines = [
        '<div class="cat-doc">',
        '  <style>',
        '    .cat-doc {',
        '      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;',
        '      color: #1e293b;',
        '      line-height: 1.5;',
        '    }',
        '    .cat-meta-bar {',
        '      display: flex;',
        '      flex-wrap: wrap;',
        '      gap: 8px;',
        '      align-items: center;',
        '      margin: 10px 0 16px 0;',
        '      padding-bottom: 12px;',
        '      border-bottom: 1px solid #e2e8f0;',
        '    }',
        '    .cat-badge {',
        '      display: inline-flex;',
        '      align-items: center;',
        '      padding: 2px 10px;',
        '      font-size: 0.78rem;',
        '      font-weight: 500;',
        '      border-radius: 9999px;',
        '      background: #f1f5f9;',
        '      color: #475569;',
        '    }',
        '    .cat-badge-primary { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }',
        '    .cat-badge-success { background: #f0fdf4; color: #15803d; border: 1px solid #dcfce7; }',
        '    .cat-badge-stat { background: #f8fafc; color: #334155; border: 1px solid #e2e8f0; }',
        '    .cat-changes-box {',
        '      background: #eff6ff;',
        '      border-left: 4px solid #3b82f6;',
        '      padding: 10px 14px;',
        '      margin-bottom: 18px;',
        '      border-radius: 0 4px 4px 0;',
        '    }',
        '    .cat-changes-title {',
        '      font-weight: 600;',
        '      font-size: 0.85rem;',
        '      color: #1e40af;',
        '      margin-bottom: 4px;',
        '    }',
        '    .cat-changes-list {',
        '      margin: 0;',
        '      padding-left: 18px;',
        '      font-size: 0.82rem;',
        '      color: #1e3a8a;',
        '    }',
        '    .cat-section-header {',
        '      font-size: 0.95rem;',
        '      font-weight: 700;',
        '      color: #0f172a;',
        '      margin: 18px 0 8px 0;',
        '      display: flex;',
        '      align-items: center;',
        '      gap: 6px;',
        '    }',
        '    .cat-tree-view {',
        '      background: #f8fafc;',
        '      border: 1px solid #e2e8f0;',
        '      border-radius: 6px;',
        '      padding: 12px 16px;',
        '      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;',
        '      font-size: 0.82rem;',
        '      line-height: 1.6;',
        '      color: #334155;',
        '      white-space: pre-wrap;',
        '      overflow-x: auto;',
        '      margin-bottom: 20px;',
        '    }',
        '    .cat-chapter-card {',
        '      border: 1px solid #e2e8f0;',
        '      border-radius: 6px;',
        '      margin-bottom: 12px;',
        '      background: #ffffff;',
        '      overflow: hidden;',
        '    }',
        '    .cat-chapter-header {',
        '      background: #f8fafc;',
        '      padding: 8px 14px;',
        '      font-weight: 600;',
        '      font-size: 0.9rem;',
        '      color: #0f172a;',
        '      border-bottom: 1px solid #e2e8f0;',
        '    }',
        '    .cat-topic-group {',
        '      padding: 10px 14px;',
        '      border-bottom: 1px dashed #e2e8f0;',
        '    }',
        '    .cat-topic-group:last-child {',
        '      border-bottom: none;',
        '    }',
        '    .cat-topic-title {',
        '      font-weight: 600;',
        '      font-size: 0.84rem;',
        '      color: #334155;',
        '      margin-bottom: 6px;',
        '    }',
        '    .cat-kp-grid {',
        '      display: flex;',
        '      flex-direction: column;',
        '      gap: 6px;',
        '    }',
        '    .cat-kp-item {',
        '      padding: 6px 10px;',
        '      background: #f8fafc;',
        '      border: 1px solid #f1f5f9;',
        '      border-radius: 4px;',
        '      font-size: 0.8rem;',
        '    }',
        '    .cat-kp-main {',
        '      display: flex;',
        '      align-items: baseline;',
        '      justify-content: space-between;',
        '      gap: 8px;',
        '    }',
        '    .cat-kp-name {',
        '      font-weight: 500;',
        '      color: #0f172a;',
        '    }',
        '    .cat-kp-stars {',
        '      color: #eab308;',
        '      font-size: 0.75rem;',
        '      letter-spacing: 1px;',
        '    }',
        '    .cat-kp-tags {',
        '      display: flex;',
        '      flex-wrap: wrap;',
        '      gap: 4px;',
        '      margin-top: 4px;',
        '    }',
        '    .cat-tag {',
        '      display: inline-block;',
        '      font-size: 0.7rem;',
        '      padding: 1px 6px;',
        '      border-radius: 3px;',
        '    }',
        '    .cat-tag-id { background: #f1f5f9; color: #64748b; font-family: monospace; }',
        '    .cat-tag-role { background: #e0f2fe; color: #0284c7; }',
        '    .cat-tag-risk { background: #fee2e2; color: #dc2626; }',
        '    .cat-tag-practice { background: #fef3c7; color: #d97706; }',
        '    .cat-tag-criteria { background: #dcfce7; color: #16a34a; }',
        '    .cat-tag-rel { background: #f3e8ff; color: #9333ea; }',
        '    .cat-empty {',
        '      color: #64748b;',
        '      font-style: italic;',
        '      padding: 16px;',
        '      text-align: center;',
        '    }',
        '  </style>',
        '  <div class="cat-meta-bar">',
        f'    <span class="cat-badge" style="font-weight: 600; color: #0f172a;">{escape(course)}</span>',
        f'    <span class="cat-badge cat-badge-primary">版本: v{escape(str(version))}</span>',
        f'    <span class="cat-badge cat-badge-success">{escape(mode_text)}</span>',
        f'    <span class="cat-badge cat-badge-stat">{len(visible_chapters)} 章节 · {total_topics} 主题 · {total_kps} 知识点</span>',
        '  </div>',
    ]

    changes = _change_lines(draft)
    if changes:
        lines.append('  <div class="cat-changes-box">')
        lines.append('    <div class="cat-changes-title">本次变更说明</div>')
        lines.append('    <ul class="cat-changes-list">')
        for c_item in changes:
            lines.append(f'      <li>{escape(c_item)}</li>')
        lines.append('    </ul>')
        lines.append('  </div>')

    if not visible_chapters:
        lines.append('  <div class="cat-empty">这次没有整理出可用目录，已有目录文件不会被空结果覆盖。</div>')
        lines.append('</div>')
        return "\n".join(lines)

    tree_rows = _tree_rows(draft)
    if tree_rows:
        lines.append('  <div class="cat-section-header">📁 目录层级树</div>')
        lines.append(f'  <pre class="cat-tree-view">{escape(chr(10).join(tree_rows))}</pre>')

    lines.append('  <div class="cat-section-header">📚 知识点详情卡片</div>')
    for ch in visible_chapters:
        cname = _clean(ch.get("name"))
        topics_html: list[str] = []
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            tname = _clean(tp.get("name"))
            if _is_noise_title(tname):
                tname = ""
            kps_html: list[str] = []
            for kp in tp.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                kname = _clean(kp.get("name"))
                if not kname or _is_noise_title(kname):
                    continue
                kid = _clean(kp.get("id"))
                imp = max(1, min(5, _as_int(kp.get("importance"), 3)))
                stars = "★" * imp + "☆" * (5 - imp)

                tags: list[str] = []
                if kid:
                    tags.append(f'<span class="cat-tag cat-tag-id">{escape(kid)}</span>')
                role = str(kp.get("learning_role") or "").strip()
                if role in _ROLE:
                    tags.append(f'<span class="cat-tag cat-tag-role">{escape(_ROLE[role])}</span>')
                for pt in _as_list(kp.get("practice_type")):
                    if pt in _PRACTICE:
                        tags.append(f'<span class="cat-tag cat-tag-practice">{escape(_PRACTICE[pt])}</span>')
                for cr in _as_list(kp.get("completion_criteria")):
                    if cr in _CRITERIA:
                        tags.append(f'<span class="cat-tag cat-tag-criteria">{escape(_CRITERIA[cr])}</span>')
                for rt in _as_list(kp.get("risk_tags")):
                    if rt in _RISK:
                        tags.append(f'<span class="cat-tag cat-tag-risk">{escape(_RISK[rt])}</span>')
                for rel in kp.get("related_points") or []:
                    if isinstance(rel, dict) and _clean(rel.get("name")):
                        r_lbl = _RELATION.get(rel.get("relation"), "关联")
                        tags.append(f'<span class="cat-tag cat-tag-rel">{escape(r_lbl)}: {escape(_clean(rel.get("name")))}</span>')

                tags_markup = "".join(tags)
                kps_html.append(
                    f'        <div class="cat-kp-item">\n'
                    f'          <div class="cat-kp-main">\n'
                    f'            <span class="cat-kp-name">{escape(kname)}</span>\n'
                    f'            <span class="cat-kp-stars" title="重要性 {imp}/5">{stars}</span>\n'
                    f'          </div>\n'
                    + (f'          <div class="cat-kp-tags">{tags_markup}</div>\n' if tags_markup else "")
                    + f'        </div>'
                )
            if not tname and not kps_html:
                continue
            topic_header = f'      <div class="cat-topic-title">{escape(tname)}</div>\n' if tname else ""
            kps_grid = f'      <div class="cat-kp-grid">\n{"".join(kps_html)}\n      </div>\n' if kps_html else ""
            topics_html.append(f'    <div class="cat-topic-group">\n{topic_header}{kps_grid}    </div>')

        if topics_html:
            lines.append('  <div class="cat-chapter-card">')
            lines.append(f'    <div class="cat-chapter-header">{escape(cname)}</div>')
            lines.extend(topics_html)
            lines.append('  </div>')

    lines.append('</div>')
    return "\n".join(lines)


def attach_catalog_artifacts(state: dict[str, Any]) -> None:
    from core.graph.engine_text import line

    import logging

    logger = logging.getLogger(__name__)
    from .gather import (
        backfill_catalog_relations,
        backfill_catalog_trace,
        calibrate_catalog_relations,
        complement_catalog_coverage,
        compute_catalog_signals,
        order_catalog_by_source,
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
    # 输出侧流水线(均零 LLM):候选补缺 → 保序 → 规模合并 → 溯源/老师回填 → 粒度合并
    # → 关联校准(悬空引用归零) → **关系程序保底** → 重要性/信号计算
    draft = complement_catalog_coverage(draft, context)
    # 补缺会新建/追加节点（末尾），这里再保序一次，让"目录顺序 = 原文顺序"在补缺后仍成立
    draft = order_catalog_by_source(draft, context)
    draft = trim_catalog_scale(draft, context)
    # 规模合并会把节点并进父级，可能改动顺序，再保序一次
    draft = order_catalog_by_source(draft, context)
    draft = backfill_catalog_trace(draft, context)
    draft = compact_catalog_granularity(draft)
    draft = calibrate_catalog_relations(draft)
    # 关系保底必须排在"关联校准"之后（校准负责清理模型给的悬空引用）、
    # "信号计算"之前（importance 的结构分依赖关系密度）
    draft, relation_stats = backfill_catalog_relations(draft, context)
    draft = compute_catalog_signals(draft)
    if relation_stats and any(relation_stats.values()):
        logger.info("catalog relation backfill: %s", relation_stats)
    save_catalog(
        user_id=user_id_from_context(context),
        subject=subject_from_context(context),
        draft=draft,
    )
    draft["catalog_html"] = build_catalog_html(draft)
    sub["catalog_html"] = draft["catalog_html"]
    sub["rendered"] = build_catalog_markdown(draft)
    sub["draft"] = draft
    sub["structure"] = draft.get("chapters") or []
