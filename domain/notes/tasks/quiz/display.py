"""自测题：筛掉可抄原文的题，并做成答案默认折叠的对照页。"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from tools.domain_engine_text import line
from tools.exercise_search.images import rewrite_images
from tools.exercise_search.tex import pretty_latex, replace_tex_html

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
    grade: str | None = None,
    edition: str | None = None,
    difficulty: str | None = None,
    qtype: str | None = None,
) -> str:
    """可选上下文：水平固定期中备考；年级/版本由知识点反推，不写进 extra。"""
    rows: list[str] = []
    if _clean(subject):
        rows.append(f"学科/课程：{_clean(subject)}")
    if _clean(chapter):
        rows.append(f"章节：{_clean(chapter)}")
    if _clean(level):
        rows.append(f"用户水平：{_clean(level)}")
    bank: list[str] = []
    if _clean(grade):
        bank.append(f"年级：{_clean(grade)}")
    if _clean(edition):
        bank.append(f"课本版本：{_clean(edition)}")
    if _clean(difficulty):
        bank.append(f"题目难度：{_clean(difficulty)}")
    if _clean(qtype):
        bank.append(f"题目类型：{_clean(qtype)}")
    parts: list[str] = []
    if rows:
        parts.append(
            "【出题上下文（只调难度与问法，不是另一份笔记）】\n" + "\n".join(rows)
        )
    if bank:
        parts.append(
            "【题库检索（只用来搜真题，不要改成本卷题型）】\n" + "\n".join(bank)
        )
    return "\n\n".join(parts)


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
                "kb_file": _clean(raw.get("kb_file")),
                "kb_page": _clean(raw.get("kb_page")),
                "kb_excerpt": _clean(raw.get("kb_excerpt")),
            }
        )
    return out


def _note_sentences(notes: str) -> list[str]:
    text = (notes or "").replace("\r\n", "\n")
    bits = re.split(r"[。！？!?\n；;]+", text)
    return [_clean(bit) for bit in bits if len(_clean(bit)) >= _MIN_CHUNK]


def _name_only_hook(hook: str) -> bool:
    """只有对象名或名词罗列、没有判断或步骤的条目，不够出题。"""
    text = _clean(hook)
    if not text:
        return False
    if "。" in text:
        return False
    if any(
        token in text
        for token in (
            "是",
            "为",
            "则",
            "所以",
            "因此",
            "=",
            "→",
            "等于",
            "先看",
            "先确认",
            "会",
            "导致",
            "不能",
            "必须",
        )
    ):
        return False
    return True


def looks_like_unwritten_given(prompt: str, notes: str, note_hook: str = "") -> bool:
    """挂钩只是一个名词罗列、笔记里没有可问关系时丢掉。"""
    del prompt
    if note_hook and _name_only_hook(note_hook):
        return bool(notes)
    return False


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


_QUESTION_CAP = 6


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
        if looks_like_unwritten_given(item["prompt"], notes, item.get("note_hook") or ""):
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
    out = {
        "subject": "",
        "chapter": "",
        "level": "",
        "grade": "",
        "edition": "",
        "difficulty": "",
        "qtype": "",
    }
    for line_text in (extra or "").splitlines():
        if line_text.startswith("学科/课程："):
            out["subject"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("章节："):
            out["chapter"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("用户水平："):
            out["level"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("年级："):
            out["grade"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("课本版本："):
            out["edition"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("题目难度："):
            out["difficulty"] = line_text.split("：", 1)[1].strip()
        elif line_text.startswith("题目类型："):
            out["qtype"] = line_text.split("：", 1)[1].strip()
    return out


def extra_from_context(approved_context: str) -> str:
    raw = approved_context or ""
    chunks: list[str] = []
    for marker in ("【出题上下文", "【题库检索"):
        if marker not in raw:
            continue
        chunk = raw.split(marker, 1)[1]
        head = marker + chunk
        for stop in ("\n\n视角模式", "\n\n原文", "\n\n已批准", "\n\n【出题", "\n\n【题库"):
            if stop in head and not head.startswith(stop.strip()):
                head = head.split(stop, 1)[0]
        chunks.append(head.strip())
    return "\n\n".join(chunks)


def _bank_questions(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return _as_list(draft.get("bank_questions"))


def _bank_meta(item: dict[str, Any]) -> str:
    bits = [
        _clean(item.get("question_type")),
        _clean(item.get("difficulty")),
        _clean(item.get("matched_keypoint")),
    ]
    return " · ".join(bit for bit in bits if bit)


def _render_bank_markdown(draft: dict[str, Any]) -> list[str]:
    items = _bank_questions(draft)
    status = _clean(draft.get("bank_status"))
    query = _clean(draft.get("bank_query"))
    if not items and not status:
        return []
    lines = ["## 题库相关题", ""]
    if query:
        lines.append(f"检索：{query}")
        lines.append("")
    if not items:
        if status:
            lines.append(status)
            lines.append("")
        return lines
    lines.append("来自高中题库，按笔记知识点检索。解析默认折叠。")
    lines.append("")
    for i, item in enumerate(items, 1):
        meta = _bank_meta(item)
        lines.append(f"### 库{i}.")
        lines.append("")
        if meta:
            lines.append(meta)
            lines.append("")
        stem = normalize_bank_html(item.get("content_html")) or escape(
            _clean(item.get("prompt")) or "（题干见图）", quote=False
        )
        lines.append(stem)
        lines.append("")
        for option in item.get("options") or []:
            rendered = normalize_bank_html(option) or _clean(option)
            if rendered:
                lines.append(f"- {rendered}")
        if item.get("options"):
            lines.append("")
        lines.append("<details>")
        lines.append("<summary>查看解析</summary>")
        lines.append("")
        if item.get("correct_answer"):
            lines.append(f"参考答案：{_clean(item.get('correct_answer'))}")
            lines.append("")
        analysis_html = normalize_bank_html(item.get("analysis_html"))
        analysis = _clean(item.get("analysis"))
        if analysis_html:
            lines.append(analysis_html)
        elif analysis:
            lines.append(analysis)
        else:
            lines.append("题库未返回解析。")
        if item.get("paper"):
            lines.append("")
            lines.append(f"来源：{_clean(item.get('paper'))}")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    if status:
        lines.append(status)
        lines.append("")
    return lines


def build_quiz_markdown(
    draft: dict[str, Any],
    *,
    notes: str = "",
    extra: str = "",
) -> str:
    questions = filter_questions(draft, notes)
    bank_lines = _render_bank_markdown(draft)
    ctx = context_from_extra(extra)
    title = "自测题"
    bits = [v for v in (ctx.get("subject"), ctx.get("chapter"), ctx.get("level")) if v]
    if bits:
        title = f"自测题（{' · '.join(bits)}）"
    if not questions and not bank_lines:
        return f"# {title}\n\n笔记里缺少必须推理才能回答的提问点，暂不出题。\n"
    lines = [f"# {title}", ""]
    if questions:
        lines.append(f"共 {len(questions)} 道笔记推理题。先自己答，再点开参考得分点。")
        lines.append("")
        lines.append("## 笔记推理题")
        lines.append("")
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
            cite = _quiz_cite(item)
            if cite:
                lines.append("")
                lines.append(f"出处：{cite}")
                if item.get("kb_excerpt"):
                    lines.append(f"库中原文：{item['kb_excerpt']}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
    elif bank_lines:
        lines.append("笔记里缺少可推理提问点；下面是题库检索到的相关题。")
        lines.append("")
    lines.extend(bank_lines)
    return "\n".join(lines).strip() + "\n"


_QUIZ_EMBED_STYLE = """<style>
.quiz-stem,.quiz-analysis,.quiz-opts{line-height:1.85;word-break:keep-all;overflow-wrap:anywhere;}
.quiz-stem p{margin:0 0 .45em;text-indent:0!important;}
.quiz-stem p:last-child{margin-bottom:0;}
.quiz-formula{display:inline!important;vertical-align:middle!important;height:1.45em;width:auto!important;max-width:none!important;max-height:2.6em;margin:0 1px;}
.quiz-figure{display:block;max-width:100%;height:auto;margin:8px 0;}
.quiz-blank{display:inline-block;min-width:4em;border-bottom:1px solid #1c1b19;line-height:1;margin:0 .15em;}
.quiz-tex{font-family:Cambria,Times New Roman,serif;}
.quiz-opts{list-style:none;margin:0 0 8px;padding:0;}
.quiz-opts li{margin:4px 0;line-height:1.8;}
</style>
"""


_BK_TAG = re.compile(
    r"<(?:bk|blk)\b[^>]*>.*?</(?:bk|blk)>|<(?:bk|blk)\b[^>]*/?>",
    re.I | re.S,
)
_TEX_TAG = re.compile(
    r'<tex\b[^>]*data-latex=(["\'])(.*?)\1[^>]*>.*?</tex>',
    re.I | re.S,
)
_P_OPEN = re.compile(r"<p\b[^>]*>", re.I)


def normalize_bank_html(raw: object) -> str:
    """保留公式图和配图，填空改成下划线，<tex> 公式转成可读文本。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    if "&lt;img" in text.lower():
        text = (
            text.replace("&lt;img", "<img")
            .replace("&lt;IMG", "<img")
            .replace("/&gt;", "/>")
            .replace("&gt;", ">")
        )
    text = _TEX_TAG.sub(
        lambda m: f'<span class="quiz-tex">{escape(pretty_latex(m.group(2)), quote=False)}</span>',
        text,
    )
    text = replace_tex_html(text)
    text = _BK_TAG.sub('<span class="quiz-blank">______</span>', text)
    text = _P_OPEN.sub("<p>", text)
    text = rewrite_images(text)
    text = text.replace("<script", "&lt;script").replace("javascript:", "")
    return text


def _render_bank_html(draft: dict[str, Any]) -> list[str]:
    items = _bank_questions(draft)
    status = _clean(draft.get("bank_status"))
    query = _clean(draft.get("bank_query"))
    if not items and not status:
        return []
    rows = ['<div class="quiz-section">题库相关题</div>']
    if query:
        rows.append(f'<div class="quiz-bank-query">检索：{escape(query, quote=False)}</div>')
    if not items:
        if status:
            rows.append(f'<div class="quiz-empty">{escape(status, quote=False)}</div>')
        return rows
    rows.append(
        '<div class="quiz-hint">来自高中题库。先自己做，再点开解析。</div>'
    )
    for i, item in enumerate(items, 1):
        meta = _bank_meta(item)
        stem = normalize_bank_html(item.get("content_html")) or escape(
            _clean(item.get("prompt")), quote=False
        )
        options = "".join(
            f"<li>{normalize_bank_html(option) or escape(_clean(option), quote=False)}</li>"
            for option in (item.get("options") or [])
            if str(option or "").strip()
        )
        analysis = normalize_bank_html(item.get("analysis_html")) or escape(
            _clean(item.get("analysis")) or "题库未返回解析。",
            quote=False,
        )
        raw_answer = item.get("correct_answer")
        answer_html = normalize_bank_html(raw_answer) if raw_answer else ""
        if not answer_html:
            answer_html = escape(_clean(raw_answer), quote=False)
        paper = _clean(item.get("paper"))
        body = ['<div class="quiz-item quiz-bank-item">']
        body.append(f'<div class="quiz-q">库{i}.</div>')
        if meta:
            body.append(f'<div class="quiz-dim">{escape(meta, quote=False)}</div>')
        body.append(f'<div class="quiz-stem">{stem}</div>')
        if options:
            body.append(f'<ol class="quiz-opts">{options}</ol>')
        body.append('<details class="quiz-answer">')
        body.append("<summary>查看解析</summary>")
        if answer_html:
            body.append(f'<div class="quiz-key">参考答案：{answer_html}</div>')
        body.append(f'<div class="quiz-analysis">{analysis}</div>')
        if paper:
            body.append(
                f'<div class="quiz-cite">来源：{escape(paper, quote=False)}</div>'
            )
        body.append("</details>")
        body.append("</div>")
        rows.extend(body)
    return rows


def build_quiz_html(
    draft: dict[str, Any],
    *,
    notes: str = "",
    extra: str = "",
) -> str:
    questions = filter_questions(draft, notes)
    bank_rows = _render_bank_html(draft)
    ctx = context_from_extra(extra)
    meta = [v for v in (ctx.get("subject"), ctx.get("chapter"), ctx.get("level")) if v]
    heading = f"自测题 · {len(questions)} 道推理题"
    if bank_rows:
        heading += f" · {len(_bank_questions(draft))} 道题库题"
    if meta:
        heading += " · " + " · ".join(meta)
    rows = [
        _QUIZ_EMBED_STYLE,
        '<div class="quiz-sheet memory-review">',
        f'<div class="review-heading">{escape(heading, quote=False)}'
        '<div class="quiz-hint">先自己想，再点开参考得分点 / 解析</div></div>',
    ]
    if questions:
        rows.append('<div class="quiz-section">笔记推理题</div>')
        for i, item in enumerate(questions, 1):
            dim = DIMENSIONS.get(item["dimension"], item["dimension"])
            points = "".join(
                f"<li>{escape(point, quote=False)}</li>" for point in item["answer_points"]
            )
            cite = _quiz_cite(item)
            if cite:
                points += (
                    f'<li class="quiz-cite">出处：{escape(cite, quote=False)}</li>'
                )
                if item.get("kb_excerpt"):
                    points += (
                        "<li class=\"quiz-cite\">库中原文："
                        f"{escape(item['kb_excerpt'], quote=False)}</li>"
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
    elif not bank_rows:
        rows.append(
            '<div class="quiz-empty">笔记里缺少必须推理才能回答的提问点，暂不出题。</div>'
        )
        rows.append("</div>")
        return "\n".join(rows)
    rows.extend(bank_rows)
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


def _quiz_cite(item: dict[str, Any]) -> str:
    fname = _clean(item.get("kb_file"))
    if not fname:
        return ""
    page = _clean(item.get("kb_page"))
    return f"{fname} 第{page}页" if page else fname


def attach_quiz_library(draft: dict[str, Any], kb=None) -> dict[str, Any]:
    from tools.knowledge.cite import cite_text, library_has_docs, open_knowledge

    if kb is None:
        kb = open_knowledge()
    if not library_has_docs(kb):
        return draft
    questions = [dict(item) for item in (draft.get("questions") or []) if isinstance(item, dict)]
    for item in questions:
        query = str(item.get("note_hook") or item.get("prompt") or "").strip()
        hits = cite_text(kb, query)
        if hits:
            item["kb_file"] = hits[0]["file"]
            item["kb_page"] = hits[0]["page"]
            item["kb_excerpt"] = hits[0]["excerpt"]
    draft["questions"] = questions
    return draft


def attach_quiz_bank(
    draft: dict[str, Any],
    *,
    notes: str = "",
    extra: str = "",
    understanding: dict[str, Any] | None = None,
    tool=None,
) -> dict[str, Any]:
    """按笔记对齐高中题库；失败只记说明，不影响推理题。"""
    ctx = context_from_extra(extra)
    try:
        if tool is None:
            from tools.exercise_search import ExerciseSearchTool

            tool = ExerciseSearchTool()
        bundle = tool.search_for_notes(
            notes,
            understanding=understanding,
            concepts=list(draft.get("concepts") or [])
            + list(draft.get("questions") or []),
            subject=ctx.get("subject") or "",
            grade=ctx.get("grade") or "",
            edition=ctx.get("edition") or "",
            difficulty=ctx.get("difficulty") or "",
            qtype=ctx.get("qtype") or "",
        )
    except Exception as exc:  # noqa: BLE001 - 搜题失败不得打断 quiz
        draft["bank_questions"] = []
        draft["bank_query"] = ""
        draft["bank_status"] = f"题库暂不可用：{exc}"
        return draft
    draft["bank_questions"] = bundle.as_dicts()
    draft["bank_query"] = bundle.query_label
    draft["bank_status"] = bundle.message
    return draft


def attach_quiz_artifacts(state: dict[str, Any]) -> None:
    sub = line(state, "quiz")
    draft = dict(sub.get("draft") or {})
    original = str(state.get("transcript") or "")
    extra = str((state.get("line_extra") or {}).get("quiz") or "")
    understanding = state.get("notes_understanding")
    if not isinstance(understanding, dict):
        understanding = {}
    attach_quiz_library(draft)
    attach_quiz_bank(
        draft,
        notes=original,
        extra=extra,
        understanding=understanding,
    )
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
    "attach_quiz_bank",
    "build_quiz_html",
    "build_quiz_markdown",
    "draft_from_context",
    "extra_from_context",
    "filter_questions",
    "format_quiz_context",
    "looks_like_copy_question",
    "normalize_bank_html",
    "original_from_context",
]
