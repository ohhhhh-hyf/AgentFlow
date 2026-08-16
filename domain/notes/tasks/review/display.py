"""笔记审查：确定性总结、原文高亮、左右对照 HTML。"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from tools.domain_engine_text import line

ISSUE_KINDS: dict[str, tuple[str, str]] = {
    "incomplete": ("⚠", "知识点记录不完整"),
    "confusing": ("⚠", "概念容易混淆"),
    "missing_condition": ("⚠", "公式缺少适用条件"),
    "missing_example": ("＋", "内容建议补充例题"),
    "inaccurate": ("⚠", "记录不准确"),
}

_KIND_COUNT_LABELS: dict[str, tuple[str, str]] = {
    "incomplete": ("⚠", "个知识点记录不完整"),
    "confusing": ("⚠", "处概念容易混淆"),
    "missing_condition": ("⚠", "个公式缺少适用条件"),
    "missing_example": ("＋", "个内容建议补充例题"),
    "inaccurate": ("⚠", "处记录不准确"),
}

_MAX_MARK = 80
_MIN_QUOTE = 4


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def normalize_kind(kind: object) -> str:
    raw = _clean(kind)
    if raw in ISSUE_KINDS:
        return raw
    aliases = {
        "不完整": "incomplete",
        "混淆": "confusing",
        "易混": "confusing",
        "缺条件": "missing_condition",
        "缺少条件": "missing_condition",
        "缺例题": "missing_example",
        "例题": "missing_example",
        "不准确": "inaccurate",
        "错误": "inaccurate",
    }
    return aliases.get(raw, raw if raw in ISSUE_KINDS else "")


def _as_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _issue_items(draft: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in _as_list(draft.get("issues")):
        kind = normalize_kind(raw.get("kind"))
        quote = str(raw.get("quote") or "").strip()
        if not kind:
            continue
        out.append(
            {
                "quote": quote,
                "kind": kind,
                "problem": _clean(raw.get("problem")),
                "analysis": _clean(raw.get("analysis")),
                "suggestion": _clean(raw.get("suggestion")),
                "kb_file": _clean(raw.get("kb_file")),
                "kb_page": _clean(raw.get("kb_page")),
                "kb_excerpt": _clean(raw.get("kb_excerpt")),
                "kb_miss": bool(raw.get("kb_miss")),
            }
        )
    return out


def _knowledge_points(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return _as_list(draft.get("knowledge_points"))


def summarize_review(draft: dict[str, Any]) -> dict[str, int]:
    """从结构化结果计次，不信任模型口头报数。"""
    points = _knowledge_points(draft)
    issues = _issue_items(draft)
    counts = {
        "identified": len(points),
        "incomplete": 0,
        "confusing": 0,
        "missing_condition": 0,
        "missing_example": 0,
        "inaccurate": 0,
    }
    seen_incomplete: list[str] = []
    for point in points:
        status = str(point.get("complete") or "").strip().lower()
        if status not in {"partial", "no"}:
            continue
        keys = [_clean(point.get("title")), _clean(point.get("evidence"))]
        keys = [key for key in keys if key]
        if any(
            key in seen or seen in key
            for key in keys
            for seen in seen_incomplete
        ):
            continue
        seen_incomplete.extend(keys)
        counts["incomplete"] += 1
    for issue in issues:
        kind = issue["kind"]
        if kind == "incomplete":
            key = issue["quote"] or issue["problem"]
            if key and any(key in seen or seen in key for seen in seen_incomplete):
                continue
            if key:
                seen_incomplete.append(key)
            counts["incomplete"] += 1
            continue
        if kind in counts:
            counts[kind] += 1
    return counts


def format_summary_lines(counts: dict[str, int]) -> list[str]:
    lines = [f"✓ 识别 {int(counts.get('identified') or 0)} 个知识点"]
    order = (
        "incomplete",
        "confusing",
        "missing_condition",
        "missing_example",
        "inaccurate",
    )
    for kind in order:
        n = int(counts.get(kind) or 0)
        if n <= 0:
            continue
        mark, tail = _KIND_COUNT_LABELS[kind]
        lines.append(f"{mark} {n} {tail}")
    return lines


def format_summary_text(draft: dict[str, Any]) -> str:
    body = "\n".join(format_summary_lines(summarize_review(draft)))
    return f"先总结笔记：\n{body}"


def find_quote_span(notes: str, quote: str) -> tuple[int, int] | None:
    """只标连续原文。找不到就不标，禁止跨段模糊拼接。"""
    raw = (quote or "").strip()
    if len(raw) < _MIN_QUOTE or not notes:
        return None
    idx = notes.find(raw)
    if idx < 0:
        compact = re.sub(r"\s+", "", raw)
        if len(compact) < _MIN_QUOTE:
            return None
        window = compact[:40]
        # 在去空白映射上回找一小段连续汉字/符号
        stripped = []
        index_map: list[int] = []
        for i, ch in enumerate(notes):
            if not ch.isspace():
                stripped.append(ch)
                index_map.append(i)
        blob = "".join(stripped)
        hit = blob.find(window)
        if hit < 0:
            return None
        start = index_map[hit]
        end_idx = min(hit + len(window), len(index_map)) - 1
        end = index_map[end_idx] + 1
        return start, min(end, start + _MAX_MARK)
    end = idx + len(raw)
    if end - idx > _MAX_MARK:
        chunk = notes[idx : idx + _MAX_MARK]
        cut = _MAX_MARK
        for sep in ("。", "；", "，", "\n", "；"):
            pos = chunk.find(sep)
            if 8 <= pos < cut:
                cut = pos + (0 if sep == "\n" else 1)
        return idx, idx + cut
    return idx, end


def _paragraphs(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return []
    blocks = [part.strip() for part in re.split(r"\n\s*\n", raw) if part.strip()]
    rows: list[str] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 2:
            rows.extend(lines)
        else:
            rows.append(block)
    return rows or [raw]


def _issues_in_text(chunk: str, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for issue in issues:
        span = find_quote_span(chunk, issue.get("quote") or "")
        if span:
            hits.append(issue)
    return hits


def _collect_spans(
    chunk: str, indexed: list[tuple[int, dict[str, Any]]]
) -> list[tuple[int, int, int]]:
    spans: list[tuple[int, int, int]] = []
    for idx, issue in indexed:
        span = find_quote_span(chunk, issue.get("quote") or "")
        if not span:
            continue
        start, end = span
        if any(not (end <= s or start >= e) for s, e, _ in spans):
            continue
        spans.append((start, end, idx))
    spans.sort()
    return spans


def _mark_text(chunk: str, issues: list[dict[str, Any]]) -> str:
    indexed = list(enumerate(issues, 1))
    spans = _collect_spans(chunk, indexed)
    if not spans:
        return escape(chunk, quote=False)
    out: list[str] = []
    pos = 0
    for start, end, _idx in spans:
        out.append(escape(chunk[pos:start], quote=False))
        out.append(f'<span class="mem-mark">{escape(chunk[start:end], quote=False)}</span>')
        pos = end
    out.append(escape(chunk[pos:], quote=False))
    return "".join(out).replace("\n", "<br>\n")


def _mark_text_md(chunk: str, indexed: list[tuple[int, dict[str, Any]]]) -> str:
    """给前端渲染的 Markdown 高亮：<mark data-review="N">原文</mark>。"""
    spans = _collect_spans(chunk, indexed)
    if not spans:
        return chunk
    out: list[str] = []
    pos = 0
    for start, end, idx in spans:
        out.append(chunk[pos:start])
        out.append(f'<mark data-review="{idx}">{chunk[start:end]}</mark>')
        pos = end
    out.append(chunk[pos:])
    return "".join(out)


def _issue_card(issue: dict[str, Any]) -> str:
    kind = issue.get("kind") or ""
    label = ISSUE_KINDS.get(kind, ("·", kind or "问题"))[1]
    problem = issue.get("problem") or label
    analysis = issue.get("analysis") or ""
    suggestion = issue.get("suggestion") or ""
    parts = [
        '<div class="mem-card">',
        f'<div class="mem-card-title">{escape(problem, quote=False)}</div>',
        f'<div class="mem-card-meta">类型：{escape(label, quote=False)}</div>',
    ]
    if analysis:
        parts.append(
            f'<div class="review-analysis">{escape(analysis, quote=False)}</div>'
        )
    if suggestion:
        parts.append(
            f'<div class="review-fix">建议：{escape(suggestion, quote=False)}</div>'
        )
    cite = _cite_label(issue)
    if cite:
        parts.append(
            f'<div class="review-cite">出处：{escape(cite, quote=False)}</div>'
        )
        excerpt = issue.get("kb_excerpt") or ""
        if excerpt:
            parts.append(
                f'<div class="review-excerpt">库中原文：{escape(excerpt, quote=False)}</div>'
            )
    elif issue.get("kb_miss"):
        parts.append('<div class="review-cite">库中未找到</div>')
    parts.append("</div>")
    return "\n".join(parts)


def _cite_label(item: dict[str, Any]) -> str:
    fname = _clean(item.get("kb_file"))
    if not fname:
        return ""
    page = _clean(item.get("kb_page"))
    return f"{fname} 第{page}页" if page else fname


def build_review_html(original: str, draft: dict[str, Any]) -> str:
    """总结 + 左原文高亮 / 右问题分析，复用会议记忆对照的 class。"""
    issues = _issue_items(draft)
    points = _knowledge_points(draft)
    summary = format_summary_text(draft)
    heading = escape(summary, quote=False).replace("\n", "<br>\n")
    rows: list[str] = [
        '<div class="memory-review">',
        f'<div class="review-heading">{heading}</div>',
    ]
    paragraphs = _paragraphs(original) or [original or "（无笔记原文）"]
    for para in paragraphs:
        local = _issues_in_text(para, issues)
        left = _mark_text(para, local)
        supports = [
            point
            for point in points
            if point.get("kb_supported")
            and find_quote_span(para, str(point.get("evidence") or point.get("title") or ""))
        ]
        cards_html = [ _issue_card(item) for item in local ]
        cards_html.extend(_support_card(point) for point in supports)
        if cards_html:
            cards = "\n".join(cards_html)
        else:
            cards = '<div class="mem-empty"></div>'
        rows.extend(
            [
                '<div class="review-row">',
                f'<div class="review-left">{left}</div>',
                '<div class="review-rule"></div>',
                f'<div class="review-right">{cards}</div>',
                "</div>",
            ]
        )
    rows.append("</div>")
    return "\n".join(rows)


def build_review_markdown(original: str, draft: dict[str, Any]) -> str:
    """带批注的对照页（Markdown，给前端渲染）。不含订正全文。"""
    issues = _issue_items(draft)
    indexed = list(enumerate(issues, 1))
    parts = [format_summary_text(draft), "", "## 原文", ""]
    paragraphs = _paragraphs(original) or ([original] if original else [])
    if not paragraphs:
        parts.append("（无笔记原文）")
        parts.append("")
    else:
        for para in paragraphs:
            local = [(idx, issue) for idx, issue in indexed if find_quote_span(para, issue.get("quote") or "")]
            parts.append(_mark_text_md(para, local))
            parts.append("")
    if issues:
        parts.append("## 批注")
        parts.append("")
        for i, issue in indexed:
            label = ISSUE_KINDS.get(issue["kind"], ("·", issue["kind"]))[1]
            parts.append(f"### {i}. {label}")
            if issue["problem"]:
                parts.append(f"- 问题：{issue['problem']}")
            if issue["quote"]:
                parts.append(f"- 原文：{issue['quote']}")
            if issue["analysis"]:
                parts.append(f"- 分析：{issue['analysis']}")
            if issue["suggestion"]:
                parts.append(f"- 建议：{issue['suggestion']}")
            cite = _cite_label(issue)
            if cite:
                parts.append(f"- 出处：{cite}")
                if issue.get("kb_excerpt"):
                    parts.append(f"- 库中原文：{issue['kb_excerpt']}")
            elif issue.get("kb_miss"):
                parts.append("- 出处：库中未找到")
            parts.append("")
    supported = [
        point
        for point in _knowledge_points(draft)
        if point.get("kb_supported") and _cite_label(point)
    ]
    if supported:
        parts.append("## 有据（库内出处）")
        parts.append("")
        for point in supported:
            title = _clean(point.get("title")) or "知识点"
            parts.append(f"- {title}　出处：{_cite_label(point)}")
            if _clean(point.get("kb_excerpt")):
                parts.append(f"  库中原文：{point['kb_excerpt']}")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def build_corrected_markdown(draft: dict[str, Any]) -> str:
    """订正后的笔记（独立 Markdown）。没有订正稿则空串。"""
    return str(draft.get("corrected_notes") or "").strip()


def draft_from_context(approved_context: str) -> dict[str, Any]:
    blob = approved_context or ""
    for marker in ("已批准笔记审查草稿：", "已批准审查草稿："):
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


def original_from_context(approved_context: str) -> str:
    raw = approved_context or ""
    for marker in ("原文（最高事实来源）：", "原文："):
        if marker not in raw:
            continue
        body = raw.split(marker, 1)[1]
        for stop in (
            "\n\n用户画像：",
            "\n\n已审核笔记理解：",
            "\n\n已审核用户视角：",
            "\n\n已批准",
        ):
            if stop in body:
                body = body.split(stop, 1)[0]
                break
        return body.strip()
    return ""


def build_rewrite_user(original: str, draft: dict[str, Any]) -> str:
    issues = _issue_items(draft)
    lines = ["原始笔记：", original.strip() or "（空）", "", "审查问题清单："]
    if not issues:
        lines.append("（无问题。请在保持结构的前提下把笔记整理通顺，不要新增章节。）")
    else:
        for i, issue in enumerate(issues, 1):
            label = ISSUE_KINDS.get(issue["kind"], ("·", issue["kind"]))[1]
            lines.append(f"{i}. [{label}] {issue['problem']}")
            if issue["quote"]:
                lines.append(f"   原文片段：{issue['quote']}")
            if issue["analysis"]:
                lines.append(f"   分析：{issue['analysis']}")
            if issue["suggestion"]:
                lines.append(f"   建议：{issue['suggestion']}")
    prev = str(draft.get("corrected_notes") or "").strip()
    if prev:
        lines.extend(["", "上一版订正笔记（可作参考，但以问题清单为准）：", prev])
    lines.append("")
    lines.append("请输出订正后的完整笔记正文。")
    return "\n".join(lines)


def review_payload(original: str, draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "original_notes": original,
        "knowledge_points": _knowledge_points(draft),
        "issues": _issue_items(draft),
        "corrected_notes": str(draft.get("corrected_notes") or "").strip(),
        "summary": summarize_review(draft),
    }


def attach_library_hits(draft: dict[str, Any], kb: Any = None) -> dict[str, Any]:
    """有库则给每条主张钉出处；库空不动，走原来的挑刺。"""
    from tools.knowledge.cite import cite_text, library_has_docs, open_knowledge

    if kb is None:
        kb = open_knowledge()
    if not library_has_docs(kb):
        return draft
    issues = [dict(item) for item in _as_list(draft.get("issues"))]
    for issue in issues:
        query = str(issue.get("quote") or issue.get("problem") or "").strip()
        hits = cite_text(kb, query)
        if hits:
            issue["kb_file"] = hits[0]["file"]
            issue["kb_page"] = hits[0]["page"]
            issue["kb_excerpt"] = hits[0]["excerpt"]
            issue["kb_miss"] = False
        else:
            issue["kb_miss"] = True
            issue.pop("kb_file", None)
            issue.pop("kb_page", None)
            issue.pop("kb_excerpt", None)
    draft["issues"] = issues
    points = [dict(item) for item in _knowledge_points(draft)]
    for point in points:
        query = str(point.get("evidence") or point.get("title") or "").strip()
        hits = cite_text(kb, query)
        if hits:
            point["kb_file"] = hits[0]["file"]
            point["kb_page"] = hits[0]["page"]
            point["kb_excerpt"] = hits[0]["excerpt"]
            point["kb_supported"] = True
        else:
            point["kb_supported"] = False
    draft["knowledge_points"] = points
    return draft


def _support_card(point: dict[str, Any]) -> str:
    title = _clean(point.get("title")) or "有据"
    cite = _cite_label(point)
    excerpt = _clean(point.get("kb_excerpt"))
    parts = [
        '<div class="mem-card">',
        f'<div class="mem-card-title">{escape(title, quote=False)}</div>',
        '<div class="mem-card-meta">类型：有据</div>',
    ]
    if cite:
        parts.append(f'<div class="review-cite">出处：{escape(cite, quote=False)}</div>')
    if excerpt:
        parts.append(
            f'<div class="review-excerpt">库中原文：{escape(excerpt, quote=False)}</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def attach_review_artifacts(state: dict[str, Any]) -> None:
    """对照页 Markdown 进 rendered；订正稿留在 draft，默认不进对照页。"""
    sub = line(state, "review")
    draft = dict(sub.get("draft") or {})
    original = str(state.get("transcript") or "")
    attach_library_hits(draft)
    draft["original_notes"] = original
    draft["review_html"] = build_review_html(original, draft)
    sub["rendered"] = build_review_markdown(original, draft)
    sub["draft"] = draft


__all__ = [
    "ISSUE_KINDS",
    "attach_library_hits",
    "attach_review_artifacts",
    "build_corrected_markdown",
    "build_review_html",
    "build_review_markdown",
    "build_rewrite_user",
    "draft_from_context",
    "find_quote_span",
    "format_summary_text",
    "original_from_context",
    "review_payload",
    "summarize_review",
]
