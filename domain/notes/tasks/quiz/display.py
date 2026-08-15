"""自测题：筛掉可抄原文的题，并做成答案默认折叠的对照页。"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from tools.domain_engine_text import line

DIMENSIONS: dict[str, str] = {
    "cause": "因果",
    "contrast": "对比",
    "condition": "适用条件",
    "detail": "关键细节",
    "application": "迁移应用",
}

_COPY_STEMS = (
    "是什么",
    "是谁",
    "叫什么",
    "会怎样",
    "会导致什么",
    "结果是什么",
    "定义是",
)

_MIN_CHUNK = 8


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def format_quiz_context(
    subject: str | None = None,
    chapter: str | None = None,
    level: str | None = None,
) -> str:
    """可选上下文：只调难度与问法，不是另一份笔记。"""
    rows: list[str] = []
    if _clean(subject):
        rows.append(f"学科/课程：{_clean(subject)}")
    if _clean(chapter):
        rows.append(f"章节：{_clean(chapter)}")
    if _clean(level):
        rows.append(f"用户水平：{_clean(level)}")
    if not rows:
        return ""
    return "【出题上下文（只调难度与问法，不是另一份笔记）】\n" + "\n".join(rows)


def _as_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _answer_points(raw: object) -> list[str]:
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if not isinstance(raw, list):
        return []
    return [_clean(item) for item in raw if _clean(item)]


def normalize_dimension(value: object) -> str:
    raw = _clean(value)
    if raw in DIMENSIONS:
        return raw
    aliases = {
        "因果": "cause",
        "为什么": "cause",
        "对比": "contrast",
        "条件": "condition",
        "适用条件": "condition",
        "细节": "detail",
        "应用": "application",
        "迁移": "application",
    }
    return aliases.get(raw, "")


def _questions(draft: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in _as_list(draft.get("questions")):
        prompt = _clean(raw.get("prompt") or raw.get("question") or raw.get("title"))
        if not prompt:
            continue
        dim = normalize_dimension(raw.get("dimension"))
        out.append(
            {
                "prompt": prompt,
                "dimension": dim or "cause",
                "note_hook": _clean(raw.get("note_hook")),
                "answer_points": _answer_points(raw.get("answer_points")),
            }
        )
    return out


def _note_sentences(notes: str) -> list[str]:
    text = (notes or "").replace("\r\n", "\n")
    bits = re.split(r"[。！？!?\n；;]+", text)
    return [_clean(bit) for bit in bits if len(_clean(bit)) >= _MIN_CHUNK]


def looks_like_copy_question(prompt: str, notes: str) -> bool:
    """题干若基本是原文填空/复述结论，视为可抄，应丢掉。"""
    q = _clean(prompt)
    n = notes or ""
    if len(q) < 4 or not n:
        return False
    if q in n:
        return True
    compact_q = re.sub(r"\s+", "", q)
    compact_n = re.sub(r"\s+", "", n)
    if len(compact_q) >= _MIN_CHUNK and compact_q in compact_n:
        return True
    stripped = q
    for token in ("为什么", "为何", "请解释", "说明", "？", "?", "：", ":"):
        stripped = stripped.replace(token, "")
    stripped = _clean(stripped)
    if len(stripped) >= 12 and stripped in _clean(n):
        return True
    for stem in _COPY_STEMS:
        if stem not in q:
            continue
        prefix = _clean(q.split(stem, 1)[0])
        if len(prefix) >= 4 and prefix in _clean(n):
            return True
        for sent in _note_sentences(n):
            overlap = [ch for ch in sent if ch in q]
            if len(sent) >= 10 and len(overlap) / len(sent) >= 0.72:
                return True
    return False


_QUESTION_CAP = 8


def _pick_diverse(items: list[dict[str, Any]], cap: int = _QUESTION_CAP) -> list[dict[str, Any]]:
    """先各维度留一题，再按原文顺序补满，最多 cap 道。"""
    if len(items) <= cap:
        return items
    picked: list[dict[str, Any]] = []
    seen: set[int] = set()
    used_dims: set[str] = set()
    for item in items:
        dim = item.get("dimension") or ""
        if dim and dim not in used_dims:
            picked.append(item)
            used_dims.add(dim)
            seen.add(id(item))
        if len(picked) >= cap:
            return picked
    for item in items:
        if id(item) in seen:
            continue
        picked.append(item)
        if len(picked) >= cap:
            break
    return picked


def filter_questions(
    draft: dict[str, Any], notes: str = ""
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _questions(draft):
        key = item["prompt"]
        if key in seen:
            continue
        if looks_like_copy_question(item["prompt"], notes):
            continue
        points = item["answer_points"][:3]
        if len(points) < 2:
            continue
        item = dict(item)
        item["answer_points"] = points
        seen.add(key)
        kept.append(item)
    return _pick_diverse(kept)


def context_from_extra(extra: str) -> dict[str, str]:
    out = {"subject": "", "chapter": "", "level": ""}
    for line_text in (extra or "").splitlines():
        if line_text.startswith("学科/课程："):
            out["subject"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("章节："):
            out["chapter"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("用户水平："):
            out["level"] = line_text.split("：", 1)[1].strip()
    return out


def extra_from_context(approved_context: str) -> str:
    raw = approved_context or ""
    marker = "【出题上下文"
    if marker not in raw:
        return ""
    chunk = raw.split(marker, 1)[1]
    head = "【出题上下文" + chunk
    for stop in ("\n\n视角模式", "\n\n原文", "\n\n已批准"):
        if stop in head:
            head = head.split(stop, 1)[0]
    return head.strip()


def build_quiz_markdown(
    draft: dict[str, Any],
    *,
    notes: str = "",
    extra: str = "",
) -> str:
    questions = filter_questions(draft, notes)
    ctx = context_from_extra(extra)
    title = "自测题"
    bits = [v for v in (ctx.get("subject"), ctx.get("chapter"), ctx.get("level")) if v]
    if bits:
        title = f"自测题（{' · '.join(bits)}）"
    if not questions:
        return f"# {title}\n\n笔记里缺少必须推理才能回答的提问点，暂不出题。\n"
    lines = [f"# {title}", "", f"共 {len(questions)} 题。先自己答，再点开参考得分点。", ""]
    for i, item in enumerate(questions, 1):
        dim = DIMENSIONS.get(item["dimension"], item["dimension"])
        lines.append(f"### {i}. {item['prompt']}")
        lines.append("")
        lines.append(f"维度：{dim}")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>查看参考得分点</summary>")
        lines.append("")
        for point in item["answer_points"]:
            lines.append(f"- {point}")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_quiz_html(
    draft: dict[str, Any],
    *,
    notes: str = "",
    extra: str = "",
) -> str:
    questions = filter_questions(draft, notes)
    ctx = context_from_extra(extra)
    meta = [v for v in (ctx.get("subject"), ctx.get("chapter"), ctx.get("level")) if v]
    heading = f"自测题 · {len(questions)} 题"
    if meta:
        heading += " · " + " · ".join(meta)
    rows = [
        '<div class="quiz-sheet memory-review">',
        f'<div class="review-heading">{escape(heading, quote=False)}'
        '<div class="quiz-hint">先自己想，再点开参考得分点</div></div>',
    ]
    if not questions:
        rows.append(
            '<div class="quiz-empty">笔记里缺少必须推理才能回答的提问点，暂不出题。</div>'
        )
        rows.append("</div>")
        return "\n".join(rows)
    for i, item in enumerate(questions, 1):
        dim = DIMENSIONS.get(item["dimension"], item["dimension"])
        points = "".join(
            f"<li>{escape(point, quote=False)}</li>" for point in item["answer_points"]
        )
        rows.extend(
            [
                '<div class="quiz-item">',
                f'<div class="quiz-q">{i}. {escape(item["prompt"], quote=False)}</div>',
                f'<div class="quiz-dim">维度：{escape(dim, quote=False)}</div>',
                '<details class="quiz-answer">',
                "<summary>查看参考得分点</summary>",
                f"<ol>{points}</ol>",
                "</details>",
                "</div>",
            ]
        )
    rows.append("</div>")
    return "\n".join(rows)


def draft_from_context(approved_context: str) -> dict[str, Any]:
    blob = approved_context or ""
    for marker in ("已批准自测题草稿：", "已批准quiz草稿："):
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


def attach_quiz_artifacts(state: dict[str, Any]) -> None:
    sub = line(state, "quiz")
    draft = dict(sub.get("draft") or {})
    original = str(state.get("transcript") or "")
    extra = str((state.get("line_extra") or {}).get("quiz") or "")
    draft["quiz_html"] = build_quiz_html(draft, notes=original, extra=extra)
    if not str(sub.get("rendered") or "").strip():
        sub["rendered"] = build_quiz_markdown(draft, notes=original, extra=extra)
    else:
        # 渲染稿若把答案摊开，仍用折叠版覆盖，保证前端可点开
        sub["rendered"] = build_quiz_markdown(draft, notes=original, extra=extra)
    sub["draft"] = draft


__all__ = [
    "DIMENSIONS",
    "attach_quiz_artifacts",
    "build_quiz_html",
    "build_quiz_markdown",
    "draft_from_context",
    "extra_from_context",
    "filter_questions",
    "format_quiz_context",
    "looks_like_copy_question",
    "original_from_context",
]
