from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import io
import json
import os
import shutil
import sys
import re
import tempfile
from datetime import datetime
from pathlib import Path

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.memory.runtime import MEMORY_LINES  # noqa: E402
from tools.runtime_context import load_domain  # noqa: E402
from tools.runner import run  # noqa: E402
from tools.memory.citations import memory_review_html as render_memory_review_html  # noqa: E402
from tools.template_router import (  # noqa: E402
    LINE_SCHEMA_HINTS,
    detect_template_kind,
    maybe_compile_natural_template,
    preview_to_readable,
    readable_to_template,
    template_to_preview,
)
from tools.profiles import (  # noqa: E402
    default_profile_label,
    profile_choices,
    resolve_profile_entry,
)
from web.quiz_filters import (  # noqa: E402
    NONE as QUIZ_NONE,
    qtype_choices as quiz_qtype_choices,
    resolve_filters as resolve_quiz_filters,
)


DOMAIN_NAMES = ["meeting", "notes"]
DOMAIN_LABELS = {
    "meeting": "会议",
    "notes": "笔记",
}
DOMAIN_CHOICES = [(DOMAIN_LABELS[name], name) for name in DOMAIN_NAMES]
DOMAIN_BY_LABEL = {label: name for name, label in DOMAIN_LABELS.items()}

PERSPECTIVE_OBJECTIVE = "objective"
PERSPECTIVE_PERSONAL = "personal"
KNOWLEDGE_SCOPE_LINES = frozenset({"library", "last_class"})


def _ctx(domain: str):
    return load_domain(domain, PROJECT_ROOT)


def _task_choices(domain: str) -> list[tuple[str, str]]:
    """任务标签：(中文名, 线名)，Radio 回传线名。"""
    ctx = _ctx(domain)
    ordered: list[str] = []
    for line in ctx.line_cn_names:
        if line in ctx.task_lines:
            ordered.append(line)
    for line in ctx.task_lines:
        if line not in ordered:
            ordered.append(line)
    return [(ctx.line_cn_names.get(line, line), line) for line in ordered]


MULTI_STYLE_MODE_CHOICES = [
    "time - 时间线（叙事节奏）",
    "logic - 逻辑总分（归纳分类）",
    "causal - 因果推导（风险与动因）",
    "party - 主体责权（立场与博弈）",
    "urgency - 决策时效（执行倒计时）",
]
DEFAULT_MULTI_STYLE_MODE = MULTI_STYLE_MODE_CHOICES[0]

_TRACE_SIDECARS = (
    ("keypoints", ("user_keypoints.txt", "keypoints.txt")),
    ("notes", ("user_notes.txt", "notes.txt")),
)


def _task_value(label: str, domain: str | None = None) -> str:
    raw = (label or "").strip()
    if not raw:
        return ""
    if domain:
        ctx = _ctx(domain)
        if raw in ctx.task_lines:
            return raw
        alias = ctx.task_aliases.get(raw)
        if alias:
            return alias
    for separator in (" 路 ", " · ", " - "):
        if separator in raw:
            return raw.split(separator, 1)[0].strip()
    return raw


def _mode_value(label: str) -> str:
    """从「time - 时间顺序」这类下拉标签提取模式名。"""
    for separator in (" - ", " -", "-"):
        if separator in label:
            return label.split(separator, 1)[0].strip()
    return label.strip()


def _profile_dir(domain: str) -> Path:
    return PROJECT_ROOT / "samples" / domain / "profile"


def _profile_sample_path(domain: str, mode: str) -> Path:
    name = (
        "object_profile.json"
        if mode == PERSPECTIVE_OBJECTIVE
        else "personal_profile.json"
    )
    return _profile_dir(domain) / name


def _profile_dropdown_choices(domain: str) -> list[str]:
    return profile_choices(_profile_dir(domain))


def _profile_dropdown_default(domain: str) -> str:
    return default_profile_label(_profile_dir(domain))


def _load_profile_json_text(domain: str, mode: str = PERSPECTIVE_OBJECTIVE, label: str = "") -> str:
    if label:
        entry = resolve_profile_entry(_profile_dir(domain), label)
        if entry is not None:
            return json.dumps(entry["data"], ensure_ascii=False, indent=2)
    path = _profile_sample_path(domain, mode)
    if path.exists():
        return path.read_text(encoding="utf-8")
    # 兜底骨架
    if mode == PERSPECTIVE_OBJECTIVE:
        data = {
            "name": None,
            "role": "客观记录者",
            "department": None,
            "perspective": "objective",
            "responsibilities": ["完整还原原文事实与决策"],
            "interests": ["全员可用信息"],
            "context": "客观全员视角，不绑定个人。",
        }
    else:
        data = {
            "name": "用户",
            "role": "请填写角色",
            "department": None,
            "perspective": "personal",
            "responsibilities": ["请填写与输入相关的职责"],
            "interests": ["请填写关注点"],
            "context": "个人视角：优先保留与本人职责/被点名事项相关的内容。",
        }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _line_policy(domain: str, task: str):
    if not task:
        return None
    return _ctx(domain).line_policies.get(task)


def _task_uses_memory(task: str) -> bool:
    return task in MEMORY_LINES


TASK_BRIEFS: dict[str, dict[str, str]] = {
    "minutes_generation": {
        "inputs": "会议记录。可选：视角（默认客观全员）、用户 ID、项目 ID、模板",
        "outputs": "结构化纪要 Markdown + 网页 HTML",
        "purpose": (
            "把一场会议整理成可归档纪要（议题、结论、摘要），默认客观全员，可选真人或职业视角。"
            "特别之处：填用户 ID 开记忆，命中历史会议会打引用并展开对照卡片。"
        ),
    },
    "action_items": {
        "inputs": "会议记录。可选：模板",
        "outputs": "待办清单 Markdown",
        "purpose": (
            "抽出带负责人和截止时间的待办清单，方便会后跟进。"
            "特别之处：与纪要分开验证；只认明确分工，不把口头讨论当已分派任务。"
        ),
    },
    "risk": {
        "inputs": "会议记录。可选：模板",
        "outputs": "风险分析 Markdown",
        "purpose": (
            "把会上提到的风险抽成条目，标注严重度、责任人与应对提示。"
            "特别之处：风险与待办分开判定，只依据本场原文。"
        ),
    },
    "mindmap": {
        "inputs": "会议记录。可选：模板",
        "outputs": "可交互脑图 HTML（本机可另存 PNG）",
        "purpose": (
            "把会议要点铺成可点击思维导图，看议题结构与从属关系。"
            "特别之处：产物是可交互网页；不写项目记忆。"
        ),
    },
    "multi_styles": {
        "inputs": "会议记录、组织模式。可选：用户 ID、项目 ID、模板",
        "outputs": "指定风格纪要 Markdown",
        "purpose": (
            "同一场会按时间线、总分、因果、主体责权、决策时效五种组织方式重写。"
            "特别之处：换的是读法不是标题；填用户 ID 开记忆，可对照历史引用。"
        ),
    },
    "minutes_trace": {
        "inputs": "会议记录、用户关键点、用户笔记",
        "outputs": "带对齐戳的溯源纪要 Markdown",
        "purpose": (
            "生成段落回指会议原文的溯源纪要，并叠上用户关键点与笔记。"
            "特别之处：一条关键点可反复挂钉，核对有据可查。"
        ),
    },
    "knowledge_graph": {
        "inputs": "笔记原文。可选：用户 ID、学科、模板",
        "outputs": "图谱 SVG + 可点击 HTML + 学习地图 Markdown",
        "purpose": (
            "把笔记概念做成可点击知识图谱与按主题分组的学习地图。"
            "特别之处：点节点可在图上「学」（定义、原文摘录、关系、复习提示）；同用户按学科增量合并。"
        ),
    },
    "review": {
        "inputs": "笔记原文",
        "outputs": "带批注对照页 Markdown + 订正笔记（默认不展示）",
        "purpose": (
            "审查笔记：高亮问题句，并尽量钉到知识库出处。"
            "特别之处：库空则按原方式挑刺、不编出处；订正稿需确认后才展示。"
        ),
    },
    "library": {
        "inputs": "多份笔记/PPT/PDF/Word/Excel 或一个文件夹",
        "outputs": "信息熵报告：知识增量 + 冲突点（Markdown/HTML）",
        "purpose": (
            "一次把多份资料写入同一知识库，报告新增独立知识点与矛盾点。"
            "特别之处：只报增量与冲突不报页数；裁决哪份为准后，review/quiz 可引用该库。"
        ),
    },
    "last_class": {
        "inputs": "老师最后一课划重点文本。可选：用户 ID、学科（决定检索哪个知识库）",
        "outputs": "期末复习清单 Markdown/HTML（含知识库来源）",
        "purpose": (
            "把老师划的重点按知识点抽成复习清单：知识点、重要程度、题型、掌握要求，"
            "并检索你的知识库给每个知识点挂上出处。"
            "特别之处：老师原话 / 笔记出处 / 课件出处（含页码）分栏展示，"
            "必考/重点高亮；没入库时仅输出老师划重点内容。"
        ),
    },
    "quiz": {
        "inputs": "笔记原文。可选：难度、题型",
        "outputs": "自测题 HTML（答案/解析折叠）+ Markdown",
        "purpose": (
            "根据笔记内容设计思考题，检验是否真正理解（优先问「为什么 A 会导致 B」），"
            "同时提供对应题目供练习巩固。"
            "特别之处：题目围绕笔记知识点生成并附答案解析（点开才显示）；"
            "另从题库配约 6 道同知识点真题，边学边练。"
        ),
    },
}


def _task_brief_html(task: str) -> str:
    brief = TASK_BRIEFS.get(task)
    if not brief:
        return ""
    return (
        '<div class="task-brief">'
        f'<p><span class="k">输入：</span>{html.escape(brief["inputs"])}</p>'
        f'<p><span class="k">输出：</span>{html.escape(brief["outputs"])}</p>'
        f'<p><span class="k">用途：</span>{html.escape(brief["purpose"])}</p>'
        "</div>"
    )


def _scope_field_visibility(domain: str, task: str) -> tuple[bool, bool, bool]:
    """user_id / project_id / subject：按任务需要显示作用域字段。

    library / last_class 虽不写项目记忆，但需要 user_id + subject 确定知识库作用域。
    """
    uses = _task_uses_memory(task)
    knowledge_scoped = domain == "notes" and task in KNOWLEDGE_SCOPE_LINES
    needs_user = uses or knowledge_scoped
    needs_subject = uses or knowledge_scoped
    return (
        needs_user,
        uses and domain == "meeting",
        needs_subject and domain == "notes",
    )


_NOTE_SUFFIXES = {".txt", ".md"}
_LIBRARY_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".pptx", ".xlsx"}


def _upload_incompatible(task: str, upload) -> bool:
    if upload is None or upload == "":
        return False
    paths = _uploaded_paths(upload)
    if task == "library":
        return False
    if isinstance(upload, (list, tuple)):
        return True
    if not paths:
        return bool(upload)
    if len(paths) != 1:
        return True
    return paths[0].suffix.lower() not in _NOTE_SUFFIXES


def _upload_update(task: str, current_upload=None):
    """入库是多文件；其它任务是单份 txt。模式切换时清掉不兼容的旧文件，避免胶囊报错。"""
    knowledge_task = task == "library"
    kwargs: dict = {
        "label": (
            "资料文件（可多选或上传文件夹内文件）"
            if knowledge_task
            else "文本文件"
        ),
        "file_types": sorted(_LIBRARY_SUFFIXES) if knowledge_task else [".txt"],
        "file_count": "multiple" if knowledge_task else "single",
    }
    if _upload_incompatible(task, current_upload):
        kwargs["value"] = None
    return gr.update(**kwargs)


def _panel_updates(domain: str, task_label: str | None, current_upload=None):
    task = _task_value(task_label or "", domain)
    policy = _line_policy(domain, task)
    sidecar = bool(policy and policy.sidecar)
    show_user, show_project, show_subject = _scope_field_visibility(domain, task)
    show_quiz = task == "quiz"
    show_mode = bool(policy and policy.cli_mode)
    show_perspective = domain == "meeting" and task == "minutes_generation"
    show_config = show_mode or show_user or sidecar or show_quiz or show_perspective
    perspective_choices = _profile_dropdown_choices(domain) if show_perspective else []
    perspective_value = (
        _profile_dropdown_default(domain) if show_perspective else None
    )
    return (
        gr.update(value=_task_brief_html(task)),
        gr.update(visible=show_config),
        gr.update(visible=show_mode),
        gr.update(
            visible=show_perspective,
            choices=perspective_choices or ["客观 · 客观全员"],
            value=perspective_value or "客观 · 客观全员",
        ),
        gr.update(visible=show_user),
        gr.update(visible=show_project),
        gr.update(visible=show_subject),
        gr.update(visible=show_quiz),
        gr.update(visible=sidecar),
        gr.update(visible=bool(policy and policy.cli_template)),
        _upload_update(task, current_upload),
    )


def update_domain(domain_label: str, current_upload=None):
    domain = _domain_value(domain_label)
    choices = _task_choices(domain)
    selected = choices[0][1] if choices else None
    return (
        gr.update(choices=choices, value=selected),
        *_panel_updates(domain, selected, current_upload),
        *_hitl_ui(False),
    )


def update_task_panel(domain_label: str, task_label: str | None, current_upload=None):
    return (
        *_panel_updates(_domain_value(domain_label), task_label, current_upload),
        *_hitl_ui(False),
    )


def _quiz_notes_preview(upload, text: str | None) -> str:
    pasted = (text or "").strip()
    if pasted:
        return pasted
    path = _uploaded_path(upload)
    if path is None or not path.exists():
        return ""
    if path.suffix.lower() not in _NOTE_SUFFIXES:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _quiz_filter_updates(resolved: dict) -> tuple:
    hint = resolved.get("hint") or ""
    hint_html = (
        f'<div class="quiz-match-hint">{html.escape(hint)}</div>' if hint else ""
    )
    return (
        gr.update(
            choices=resolved["qtype_choices"],
            value=resolved["qtype"],
        ),
        hint_html,
    )


def on_quiz_notes_change(qtype, input_upload, input_text):
    """笔记变更后对齐知识点，刷新题型，并展示反推的年级/版本。"""
    try:
        notes = _quiz_notes_preview(input_upload, input_text)
        resolved = resolve_quiz_filters(notes, qtype or "")
        return _quiz_filter_updates(resolved)
    except Exception:
        return gr.update(), ""


def on_task_switch_quiz_filters(
    domain_label: str,
    task_label: str | None,
    qtype,
    input_upload,
    input_text,
):
    """只有切到自测题才按笔记对齐筛选项，避免入库残留文件把标签打成错误胶囊。"""
    task = _task_value(task_label or "", _domain_value(domain_label))
    if task != "quiz":
        return gr.skip(), gr.skip()
    return on_quiz_notes_change(qtype, input_upload, input_text)


def _output_files(domain: str, tasks: list[str]) -> set[Path]:
    root = PROJECT_ROOT / "output" / domain
    files: set[Path] = set()
    for task in tasks:
        folder = root / task
        if folder.exists():
            files.update(path.resolve() for path in folder.rglob("*") if path.is_file())
    return files


def _new_artifacts(domain: str, tasks: list[str], before: set[Path]) -> list[str]:
    after = _output_files(domain, tasks)
    # 容错：并发清理/移动时文件可能已消失，跳过即可
    new_files = sorted(
        (path for path in (after - before) if path.exists()),
        key=lambda path: path.stat().st_mtime,
    )
    return [str(path) for path in new_files]


def _png_previews(files: list[str]) -> list[str]:
    return [path for path in files if path.lower().endswith(".png")]


def _md_preview_text(files: list[str]) -> str:
    """收集本次生成的 .md 内容，供页面预览（优先 result_*.md）。"""
    paths: list[Path] = []
    rejected: list[Path] = []
    for file in files or []:
        path = Path(file)
        if path.suffix.lower() != ".md":
            continue
        if not path.is_file():
            continue
        if "_corrected" in path.name:
            continue
        if "_rejected" in path.name:
            rejected.append(path)
        else:
            paths.append(path)
    if not paths:
        paths = rejected
    if not paths:
        return ""
    paths.sort(
        key=lambda p: (
            0 if p.name.startswith("result_") else 1,
            -p.stat().st_mtime,
            p.name,
        )
    )
    parts: list[str] = []
    for path in paths:
        try:
            body = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not body:
            continue
        if "_corrected" in path.name:
            continue
        title = _clean_filename(path.name)
        parts.append(f"**{html.escape(title)}**\n\n{body}")
    return "\n\n---\n\n".join(parts)


def _gallery_update(files: list[str] | None = None):
    """有 PNG 才展示图库，否则隐藏。"""
    pngs = _png_previews(files or [])
    return gr.update(value=pngs, visible=bool(pngs))


def _has_quiz_html(files: list[str] | None) -> bool:
    for file in files or []:
        path = Path(file)
        if not (path.suffix.lower() == ".html" and path.is_file()):
            continue
        try:
            if "quiz-sheet" in path.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _md_update(files: list[str] | None = None):
    """有 Markdown 才展示预览，否则隐藏。自测题以折叠 HTML 为主，不再摊开答案。"""
    if _has_quiz_html(files):
        return EMPTY_MD
    text = _md_preview_text(files or [])
    return gr.update(value=text, visible=bool(text))


def _memory_review_html(files: list[str]) -> str:
    html_paths = [
        Path(file)
        for file in files
        if str(file).lower().endswith(".html")
        and Path(file).is_file()
        and Path(file).name.startswith("result")
    ]
    if html_paths:
        html_paths.sort(key=lambda p: (-p.stat().st_mtime, p.name))
        try:
            doc = html_paths[0].read_text(encoding="utf-8")
        except OSError:
            doc = ""
        match = re.search(r"<main[^>]*>(.*?)</main>", doc, re.S | re.I)
        body = match.group(1).strip() if match else doc.strip()
        if "memory-review" not in body and "quiz-sheet" not in body:
            return ""
        try:
            from tools.exercise_search.images import rewrite_images

            return rewrite_images(body)
        except Exception:
            return body
    text = _md_preview_text(files)
    if not text or 'class="memory-link"' not in text:
        return ""
    return render_memory_review_html(text)


def _memory_review_update(files: list[str] | None = None):
    body = _memory_review_html(files or [])
    return gr.update(value=body, visible=bool(body))


def _rewrite_btn_update(files: list[str] | None = None):
    has = any(
        str(file).endswith(".review.json") or "_corrected.md" in str(file)
        for file in (files or [])
    )
    return gr.update(
        visible=has,
        value="同意采用订正笔记",
    )


def _clean_filename(name: str) -> str:
    name = re.sub(r"_(\d{8})_(\d{6})(?:_\d{3})?(?=\.)", "", name)
    return name


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".html":
        return "text/html"
    if suffix == ".json":
        return "application/json"
    if suffix in {".md", ".txt"}:
        return "text/plain"
    return "application/octet-stream"


def _artifact_download_html(files: list[str]) -> str:
    visible_files = [
        file
        for file in (files or [])
        if Path(file).is_file() and not str(file).endswith(".review.json")
    ]
    if not visible_files:
        return '<p class="dl-empty">暂无生成文件</p>'
    rows = ['<ul class="dl-list">']
    for file in visible_files:
        path = Path(file)
        try:
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            continue
        clean_name = _clean_filename(path.name)
        if "_rejected" in path.name:
            clean_name = clean_name.replace("_rejected", "_草稿")
        suffix = path.suffix.lower().lstrip(".") or "file"
        href = f"data:{_mime_type(path)};base64,{payload}"
        rows.append(
            "<li class=\"dl-item\">"
            f'<a href="{href}" download="{html.escape(clean_name)}">'
            f'<span class="dl-name">{html.escape(clean_name)}</span>'
            f'<span class="dl-meta">{html.escape(path.parent.name)}'
            f" · {html.escape(suffix)}</span>"
            "</a></li>"
        )
    rows.append("</ul>")
    return "\n".join(rows)


def _download_files_update(files: list[str] | None = None):
    visible_files = [
        file
        for file in (files or [])
        if Path(file).is_file() and not str(file).endswith(".review.json")
    ]
    return gr.update(value=visible_files, visible=bool(visible_files))


def _domain_value(value: str) -> str:
    raw = (value or "").strip()
    if raw in DOMAIN_NAMES:
        return raw
    if raw in DOMAIN_BY_LABEL:
        return DOMAIN_BY_LABEL[raw]
    return _task_value(raw)


EMPTY_DOWNLOAD = '<p class="dl-empty">暂无生成文件</p>'
EMPTY_MD = gr.update(value="", visible=False)
EMPTY_GALLERY = gr.update(value=[], visible=False)
EMPTY_REVIEW = gr.update(value="", visible=False)
EMPTY_REWRITE = gr.update(visible=False)
EMPTY_FILES = gr.update(value=[], visible=False)

def _short_hint(hint: str) -> str:
    """把占位说明精简成用户看得懂的短标签。

    ``会议纪要正文，约300字；从会议讨论中提炼核心内容，无则写「未提及」``
    → ``会议纪要正文``：去掉字数、提炼要求、「无则写…」等编译期指令，
    这些指令在还原时从 ``template_raw`` 恢复，不展示给用户。
    """
    part = re.split(r"[；;，,]", str(hint or "").strip(), maxsplit=1)[0].strip()
    part = re.sub(
        r"[（(]?(?:本[段栏]|全文)?约?\s*\d+[-~至]?\s*\d*\s*字?[）)]?$", "", part
    )
    part = re.sub(r"约\d+[-~]\d+字$", "", part)
    return part.strip() or str(hint or "").strip()


def _friendly_template_state(template: str, *, source_kind: str = "placeholder") -> dict:
    """把占位模板转成用户能看懂的版式稿 + 隐藏的生成模板。"""
    preview = template_to_preview(template, default_rows=1)
    readable = preview_to_readable(preview)
    return {
        "template_raw": template,
        "source_kind": source_kind,
        "readable_template": readable,
    }


def _restore_full_hints(readable: str, template_raw: str) -> str:
    """把用户未填的短标签「【X】」恢复为 template_raw 的完整占位说明。

    短标签（展示用）只含语义词（如「会议纪要正文」）；完整说明（如
    「会议纪要正文，约300字；从会议讨论中提炼核心内容，无则写「未提及」」）
    藏在 template_raw 里。用户没填的空档按前缀/包含匹配找回完整说明，
    保证字数与「无则写…」指令在渲染时依然生效；用户填过的内容原样保留。
    """
    if "【" not in (readable or ""):
        return readable
    fulls = re.findall(r"\[([^\[\]]+)\]", template_raw or "")
    if not fulls:
        return readable

    def _sub(match: re.Match[str]) -> str:
        short = match.group(1).strip()
        for full in fulls:
            if short and (full.startswith(short) or short in full):
                return f"【填这里：{full}】"
        return match.group(0)

    return re.sub(r"【([^】]+)】", _sub, readable)


def _readable_to_generation_template(readable: str, template_raw: str) -> str:
    """友好模板回写成生成模板，并把未填写的空表格行恢复为占位行。

    ``readable`` 是用户编辑后的填空文档：未填的短标签「【X】」先恢复成
    ``template_raw`` 的完整占位说明，再由 ``readable_to_template`` 还原
    （「【填这里：提示】」→ ``[提示]``），用户填写的真实内容原样保留。
    """
    rendered = readable_to_template(
        _restore_full_hints(readable, template_raw), template_raw
    )
    if not template_raw or not rendered:
        return rendered

    raw_lines = template_raw.splitlines()
    table_patterns: list[tuple[str, str, str, int]] = []
    for i, line in enumerate(raw_lines):
        if "|" not in line or "[" not in line:
            continue
        if i < 2:
            continue
        header = raw_lines[i - 2].strip()
        sep = raw_lines[i - 1].strip()
        row = line.strip()
        if header.count("|") >= 2 and sep.count("|") >= 2 and row.count("|") >= 2:
            cols = len([c for c in row.strip("|").split("|")])
            table_patterns.append((header, sep, row, cols))

    if not table_patterns:
        return rendered

    out: list[str] = []
    lines = rendered.splitlines()
    i = 0
    while i < len(lines):
        matched = False
        for header, sep, raw_row, cols in table_patterns:
            if (
                i + 2 < len(lines)
                and lines[i].strip() == header
                and lines[i + 1].strip() == sep
            ):
                out.extend([lines[i], lines[i + 1]])
                i += 2
                saw_data = False
                inserted_placeholder = False
                while i < len(lines) and lines[i].count("|") >= 2:
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    if len(cells) == cols and not any(cells):
                        if not saw_data and not inserted_placeholder:
                            out.append(raw_row)
                            inserted_placeholder = True
                        i += 1
                        continue
                    saw_data = True
                    out.append(lines[i])
                    i += 1
                matched = True
                break
        if not matched:
            out.append(lines[i])
            i += 1
    return "\n".join(out).strip()


def _hitl_ui(
    show_editor: bool,
    editor_value: dict | str | None = None,
):
    """可编辑友好模板区 + 运行按钮联动。

    editor_value 兼容两种：
    - dict：包含 template_raw / readable_template 的状态
    - str：占位模板 → 自动转用户友好模板
    """
    state: dict | None = None
    readable = ""
    if show_editor:
        if isinstance(editor_value, dict):
            state = dict(editor_value)
            readable = str(state.get("readable_template") or "")
        elif isinstance(editor_value, str) and editor_value.strip():
            try:
                state = _friendly_template_state(editor_value)
                readable = str(state.get("readable_template") or "")
            except Exception:  # noqa: BLE001
                state = None
                readable = ""
    wrap = gr.update(visible=show_editor)
    friendly = gr.update(value=readable, visible=show_editor)
    state_update = gr.update(value=state)
    run_btn = gr.update(
        value="确认模板并运行" if show_editor else "运行",
        interactive=True,
    )
    return (friendly, state_update, wrap, run_btn)


def begin_run():
    """点击运行后立即反馈状态，并锁定按钮防止重复请求。"""
    return (
        "正在运行，请稍候…\n结果返回前请勿重复点击。",
        gr.update(interactive=False, value="运行中…"),
        gr.update(interactive=False),
        gr.update(interactive=False),
        gr.update(interactive=False),
    )


def clear_compiled_template():
    """清除可编辑预览，回到第一步（可重新从自然语言编译）。"""
    return (
        "已清除可编辑预览。若上方仍是自然语言描述，下次点击「运行」会重新编译。",
        *_hitl_ui(False, ""),
    )


def clear_results_only():
    """只清空右侧结果展示，保留左侧配置与输入，方便同一设置再测。"""
    return (
        "已清空结果区。左侧配置与输入仍保留，改完后直接再点「运行」即可，无需刷新页面。",
        EMPTY_GALLERY,
        EMPTY_REVIEW,
        EMPTY_REWRITE,
        EMPTY_MD,
        EMPTY_FILES,
        EMPTY_DOWNLOAD,
    )


def reset_form():
    """清空输入、模板与结果，保留领域和任务。"""
    return (
        "已重置表单（领域/任务保留）。纪要默认客观全员，可在配置里改视角。",
        EMPTY_GALLERY,
        EMPTY_REVIEW,
        EMPTY_REWRITE,
        EMPTY_MD,
        EMPTY_FILES,
        EMPTY_DOWNLOAD,
        gr.update(value=None),
        "",
        gr.update(value=None),
        "",
        DEFAULT_MULTI_STYLE_MODE,
        _profile_dropdown_default("meeting"),
        "",
        "",
        "",
        QUIZ_NONE,
        gr.update(value=QUIZ_NONE, choices=quiz_qtype_choices("")),
        "",
        gr.update(value=None),
        "",
        gr.update(value=None),
        "",
        *_hitl_ui(False),
    )


def _run_result(log, files_or_none=None, *hitl, files_html: str | None = None):
    """统一结果区输出：日志 / 图片(可隐藏) / MD预览(可隐藏) / 下载 / HITL / 解锁按钮。"""
    files = list(files_or_none or [])
    unlock = (
        gr.update(interactive=True),
        gr.update(interactive=True),
        gr.update(interactive=True),
    )
    return (
        log,
        _gallery_update(files),
        _memory_review_update(files),
        _rewrite_btn_update(files),
        _md_update(files),
        _download_files_update(files),
        files_html if files_html is not None else _artifact_download_html(files),
        *hitl,
        *unlock,
    )


def run_from_ui(
    domain_label: str,
    task_label: str | None,
    input_upload,
    input_text: str | None,
    template_upload,
    template_text: str | None,
    edit_state: dict | None,
    readable_template: str | None,
    *preview_args,
    **kwargs,
):
    """run_from_ui：*preview_args 承载模式/用户参数。

    Gradio 按位置传参（不会自动聚合 list），这里手动拆分：
    preview_args = [mode, user_id, project_id, subject, kp_upload, kp_text,
                    notes_upload, notes_text, quiz_difficulty, quiz_qtype,
                    perspective_choice]
    """
    mode_value, user_id, project_id, subject = preview_args[:4]
    keypoints_upload, keypoints_text, notes_upload, notes_text = preview_args[4:8]
    quiz_difficulty = preview_args[8] if len(preview_args) > 8 else ""
    quiz_qtype = preview_args[9] if len(preview_args) > 9 else ""
    perspective_choice = preview_args[10] if len(preview_args) > 10 else ""
    domain = _domain_value(domain_label)
    if not task_label:
        return _run_result(
            "请选择任务线。",
            None,
            *_hitl_ui(False),
            files_html=EMPTY_DOWNLOAD,
        )

    tasks = [_task_value(task_label, domain)]
    chapter = grade = edition = difficulty = qtype = None
    level = "期中备考" if tasks and tasks[0] == "quiz" else None
    if tasks[0] == "quiz":
        user_id = project_id = None
        subject = None
        chapter = None
        grade = None
        edition = None
        raw_diff = (quiz_difficulty or "").strip()
        difficulty = None if raw_diff in {"", QUIZ_NONE} else raw_diff
        raw_qtype = (quiz_qtype or "").strip()
        qtype = None if raw_qtype in {"", QUIZ_NONE} else raw_qtype
    elif not (_task_uses_memory(tasks[0]) or tasks[0] in KNOWLEDGE_SCOPE_LINES):
        user_id = project_id = subject = None
    if tasks[0] == "minutes_generation":
        profile_data = json.loads(
            _load_profile_json_text(domain, label=perspective_choice)
        )
    else:
        profile_data = json.loads(
            _load_profile_json_text(domain, PERSPECTIVE_OBJECTIVE)
        )
        profile_data["perspective"] = "objective"
    ctx = _ctx(domain)
    files: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentflow_gradio_") as temp_dir:
        temp_root = Path(temp_dir)
        profile_path = temp_root / "profile.json"
        profile_path.write_text(
            json.dumps(profile_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        input_file = _prepare_input(
            input_upload,
            input_text,
            temp_root,
            trace=bool(_line_policy(domain, tasks[0]) and _line_policy(domain, tasks[0]).sidecar),
            library=tasks[0] == "library",
            keypoints_upload=keypoints_upload,
            keypoints_text=keypoints_text,
            notes_upload=notes_upload,
            notes_text=notes_text,
        )
        if input_file is None:
            return _run_result(
                "请上传输入文件，或直接在文本框里输入内容。",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )

        # 须在自然语言模板编译之前加载 .env，否则 LLMClient 读不到 API Key
        load_env(PROJECT_ROOT / ".env")

        final_template = ""
        editor_value = ""
        show_editor = False
        if _line_policy(domain, tasks[0]) is None or _line_policy(domain, tasks[0]).cli_template:
            # ── 模板处理（Human-in-the-loop）────────────────────────────
            # 1) 自然语言：先编译成可编辑预览 → 展示给人填/改 → 确认后运行
            # 2) 已确认（edit_state 存在）：把用户友好模板还原成最终模板
            template_source = ""
            if template_upload is not None:
                uploaded = _uploaded_path(template_upload)
                if uploaded is not None and uploaded.exists():
                    template_source = uploaded.read_text(encoding="utf-8").strip()
            if not template_source:
                template_source = (template_text or "").strip()

            show_editor = bool(edit_state)

            # 情况 A：已有编辑模型（用户确认过预览）→ 合并组件值 → 组装最终模板
            if show_editor:
                readable = (readable_template or "").strip()
                if not readable:
                    readable = str((edit_state or {}).get("readable_template") or "").strip()
                base_template = (edit_state or {}).get("template_raw") or ""
                final_template = _readable_to_generation_template(readable, base_template)
                editor_value = dict(edit_state or {})
                editor_value["readable_template"] = readable
                if final_template:
                    editor_value["template_raw"] = final_template
            # 情况 B：源模板是自然语言 → 编译并渲染成可编辑预览，不停下等编辑
            elif template_source and detect_template_kind(template_source) == "natural":
                try:
                    compiled = asyncio.run(
                        maybe_compile_natural_template(
                            template_source,
                            domain=domain,
                            line_name=tasks[0],
                            schema_hint=LINE_SCHEMA_HINTS.get(tasks[0], ""),
                        )
                    ).strip()
                except Exception as exc:  # noqa: BLE001
                    return _run_result(
                        f"自然语言模板编译失败：{exc}\n请检查 .env 中的 API Key 后重试。",
                        None,
                        *_hitl_ui(False),
                        files_html=EMPTY_DOWNLOAD,
                    )
                if (
                    not compiled
                    or compiled == template_source
                    or detect_template_kind(compiled) != "placeholder"
                ):
                    return _run_result(
                        "未能理解这段描述，请写得更具体一些，例如：\n"
                        "「约400字；第一行标题；纪要约200字；风险表约3行；待办表约3行」\n"
                        "也可直接粘贴现成模板后再运行。",
                        None,
                        *_hitl_ui(False),
                        files_html=EMPTY_DOWNLOAD,
                    )
                # 占位模板 → 用户友好的编辑模型，进入确认状态
                editor_value = _friendly_template_state(
                    compiled,
                    source_kind="natural",
                )
                return _run_result(
                    "已按您的描述生成可编辑版式。\n"
                    "开头【版式】一行写清全文/某一段各多少字；下面是普通标题和表格，"
                    "空着的位置生成时填写。可改标题、列名、字数，满意后点「确认模板并运行」。",
                    None,
                    *_hitl_ui(True, editor_value),
                    files_html=EMPTY_DOWNLOAD,
                )
            # 情况 C：占位符 / 格式规范 / 空模板 → 直接运行
            else:
                final_template = template_source
                # 占位符模板也渲染成可编辑预览，方便用户看懂再确认
                if final_template and detect_template_kind(final_template) == "placeholder":
                    show_editor = True
                    editor_value = _friendly_template_state(final_template)

        templates: dict[str, Path] = {}
        if final_template:
            template_file = temp_root / "template.md"
            template_file.write_text(final_template, encoding="utf-8")
            templates[tasks[0]] = template_file

        before = _output_files(domain, tasks)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                modes: dict[str, str] = {}
                _pol = _line_policy(domain, tasks[0])
                if _pol and _pol.cli_mode and mode_value:
                    modes[tasks[0]] = _mode_value(mode_value)
                asyncio.run(
                    run(
                        ctx,
                        input_file,
                        profile_path,
                        PROJECT_ROOT / ".env",
                        templates,
                        tasks,
                        modes,
                        (user_id or "").strip() or None,
                        (project_id or "").strip() or None,
                        (subject or "").strip() or None,
                        chapter,
                        level,
                        grade,
                        edition,
                        difficulty,
                        qtype,
                        compile_natural=not show_editor,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - UI should show the error directly
            buffer.write(f"\n运行失败：{exc}\n")

        files = _new_artifacts(domain, tasks, before)
        log = _clean_log(buffer.getvalue().strip() or "运行完成。")

    if tasks[0] == "minutes_generation":
        view_label = (perspective_choice or "").strip() or _profile_dropdown_default(domain)
        log = f"【视角】{view_label}\n{log}"
    else:
        log = f"【视角】客观全员\n{log}"
    if files:
        rejected_only = files and all("_rejected" in Path(file).name for file in files)
        file_note = (
            "已生成草稿文件，可在右侧预览或下载。"
            if rejected_only
            else f"已生成 {len(files)} 个文件，可在右侧预览或下载。"
        )
        log = (
            f"{log}\n\n{file_note}\n"
            "再测：改输入/画像后直接再点「运行」即可（无需刷新）；"
            "右侧会换成新结果。仅想清屏可用「清空当前结果」，从头填表用「重置表单」。"
        )
    if show_editor and editor_value:
        log = (
            f"{log}\n\n"
            "本次结果按「可编辑模板」生成。"
            "可继续改模板后再次「确认模板并运行」；点「清除可编辑模板」才会重新从自然语言编译。"
        )
    return _run_result(
        log,
        files,
        *_hitl_ui(show_editor, editor_value if show_editor else ""),
    )


def _latest_review_payload() -> tuple[Path | None, dict | None]:
    folder = PROJECT_ROOT / "output" / "notes" / "review"
    if not folder.exists():
        return None, None
    files = sorted(
        folder.glob("result_*.review.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None, None
    try:
        return files[0], json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return files[0], None


def rewrite_notes_from_ui():
    """用户同意后才展示已生成的订正笔记；不同意则不改原稿。"""
    path, payload = _latest_review_payload()
    if not payload:
        return (
            "请先运行笔记审查。",
            EMPTY_MD,
            EMPTY_FILES,
            EMPTY_DOWNLOAD,
        )
    text = str(payload.get("corrected_notes") or "").strip()
    if not text:
        folder = PROJECT_ROOT / "output" / "notes" / "review"
        corr = sorted(
            folder.glob("result_*_corrected.md"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if corr:
            text = corr[0].read_text(encoding="utf-8").strip()
    if not text:
        return (
            "这次审查没有生成订正笔记，原稿未改动。",
            EMPTY_MD,
            EMPTY_FILES,
            EMPTY_DOWNLOAD,
        )
    if path is not None:
        payload["accepted"] = True
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out_dir = PROJECT_ROOT / "output" / "notes" / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    shown = out_dir / f"result_{stamp}_accepted.md"
    shown.write_text(text, encoding="utf-8")
    files = [str(shown)]
    if path is not None:
        files.append(str(path))
    return (
        "已同意采用订正笔记。若不同意，不要点这个按钮，原稿不会被改。",
        gr.update(value=text, visible=True),
        _download_files_update(files),
        _artifact_download_html(files),
    )


def _uploaded_path(upload) -> Path | None:
    if upload is None:
        return None
    if isinstance(upload, (list, tuple)):
        for item in upload:
            found = _uploaded_path(item)
            if found is not None:
                return found
        return None
    if isinstance(upload, (str, Path)):
        return Path(upload)
    name = getattr(upload, "name", None) or getattr(upload, "path", None)
    if name:
        return Path(name)
    if isinstance(upload, dict):
        for key in ("path", "name"):
            if upload.get(key):
                return Path(upload[key])
    return None


def _uploaded_paths(upload) -> list[Path]:
    if upload is None:
        return []
    if isinstance(upload, (list, tuple)):
        out: list[Path] = []
        for item in upload:
            found = _uploaded_path(item)
            if found is not None:
                out.append(found)
        return out
    found = _uploaded_path(upload)
    return [found] if found is not None else []


def _input_path(upload, text: str | None, temp_root: Path, filename: str) -> Path | None:
    uploaded = _uploaded_path(upload)
    if uploaded is not None:
        return uploaded
    if text and text.strip():
        path = temp_root / filename
        path.write_text(text.strip(), encoding="utf-8")
        return path
    return None


def _read_upload_or_text(upload, text: str | None) -> str:
    path = _uploaded_path(upload)
    if path is not None and path.exists():
        return path.read_text(encoding="utf-8").strip()
    return (text or "").strip()


def _prepare_input(
    input_upload,
    input_text: str | None,
    temp_root: Path,
    *,
    trace: bool,
    library: bool = False,
    keypoints_upload=None,
    keypoints_text: str | None = None,
    notes_upload=None,
    notes_text: str | None = None,
) -> Path | None:
    """普通任务写单文件；资料入库收多文件；溯源纪要把关键点/笔记放到同一目录。"""
    if library:
        return _prepare_library_input(input_upload, input_text, temp_root)
    if not trace:
        return _input_path(input_upload, input_text, temp_root, "input.txt")

    uploaded = _uploaded_path(input_upload)
    pasted = (input_text or "").strip()
    if uploaded is None and not pasted:
        return None

    work = temp_root / "trace_input"
    work.mkdir(parents=True, exist_ok=True)
    if uploaded is not None:
        shutil.copy(uploaded, work / uploaded.name)
        for _, names in _TRACE_SIDECARS:
            for name in names:
                sibling = uploaded.parent / name
                if sibling.is_file() and not (work / name).exists():
                    shutil.copy(sibling, work / name)
    else:
        (work / "input.txt").write_text(pasted, encoding="utf-8")

    extras = {
        "keypoints": _read_upload_or_text(keypoints_upload, keypoints_text),
        "notes": _read_upload_or_text(notes_upload, notes_text),
    }
    for key, names in _TRACE_SIDECARS:
        body = extras.get(key) or ""
        if body:
            (work / names[0]).write_text(body, encoding="utf-8")
    return work


def _prepare_library_input(
    input_upload, input_text: str | None, temp_root: Path
) -> Path | None:
    """把多份上传和粘贴文本收进一个临时目录，交给 library 展开入库。"""
    from tools.knowledge.document_processor import SUPPORTED_EXTS

    paths = _uploaded_paths(input_upload)
    pasted = (input_text or "").strip()
    if not paths and not pasted:
        return None
    work = temp_root / "library_input"
    work.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for src in paths:
        if src.is_dir():
            for child in sorted(src.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTS:
                    name = child.name
                    dest = work / name
                    n = 1
                    while dest.exists() or dest.name in used:
                        dest = work / f"{child.stem}_{n}{child.suffix}"
                        n += 1
                    shutil.copy(child, dest)
                    used.add(dest.name)
            continue
        dest = work / src.name
        n = 1
        while dest.exists() or dest.name in used:
            dest = work / f"{src.stem}_{n}{src.suffix}"
            n += 1
        shutil.copy(src, dest)
        used.add(dest.name)
    if pasted:
        dest = work / "notes.txt"
        n = 1
        while dest.exists() or dest.name in used:
            dest = work / f"notes_{n}.txt"
            n += 1
        dest.write_text(pasted, encoding="utf-8")
    return work


def _clean_log(text: str) -> str:
    # 兼容毫秒级时间戳（_HHMMSS_SSS 与旧版 _HHMMSS 均可）
    text = re.sub(r"knowledge_graph_\d{8}_\d{6}(?:_\d{3})?", "knowledge_graph", text)
    text = re.sub(r"mindmap_\d{8}_\d{6}(?:_\d{3})?", "mindmap", text)
    text = re.sub(r"report_\d{8}_\d{6}(?:_\d{3})?", "report", text)
    text = re.sub(r"result_\d{8}_\d{6}(?:_\d{3})?", "result", text)
    return text


CSS = """
/* 宽版工作台：暖灰纸面 + 细边框 + 充足留白 */
:root, .dark, .gradio-container {
  --body-background-fill: #f0eee9 !important;
  --body-text-color: #1c1b19 !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #ddd9d0 !important;
  --block-label-background-fill: transparent !important;
  --block-label-text-color: #4a4842 !important;
  --block-title-text-color: #1c1b19 !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #d4d0c6 !important;
  --input-placeholder-color: #9a968c !important;
  --border-color-primary: #ddd9d0 !important;
  --button-primary-background-fill: #2c2a26 !important;
  --button-primary-background-fill-hover: #1a1916 !important;
  --button-primary-text-color: #faf9f6 !important;
  --button-secondary-background-fill: #ebe8e1 !important;
  --button-secondary-text-color: #1c1b19 !important;
  --neutral-950: #1c1b19 !important;
  --neutral-900: #2c2a26 !important;
  --neutral-800: #4a4842 !important;
  --neutral-700: #6b6860 !important;
  --neutral-600: #9a968c !important;
  --neutral-200: #ddd9d0 !important;
  --neutral-100: #ebe8e1 !important;
  --neutral-50: #f0eee9 !important;
  --primary-500: #2c2a26 !important;
  --primary-600: #1a1916 !important;
  --table-odd-background-fill: #ebe8e1 !important;
  --table-even-background-fill: #f5f3ee !important;
  --link-text-color: #1c1b19 !important;
  --link-text-color-hover: #000000 !important;
  --link-text-color-visited: #2c2a26 !important;
  --link-text-color-active: #000000 !important;
  --body-text-color-subdued: #6b6860 !important;
}
html, body {
  background: #f0eee9 !important;
  overflow-x: hidden !important;
}
.gradio-container {
  max-width: min(1840px, 98vw) !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 10px 20px 24px !important;
  color: #1c1b19 !important;
  font-family: "IBM Plex Sans", "Source Han Sans SC", "Noto Sans SC",
    "PingFang SC", "Microsoft YaHei", system-ui, sans-serif !important;
  overflow-x: hidden !important;
}
#work-row, #col-input, #col-output,
#col-input > *, #col-output > *,
#tpl-box, #tpl-box * {
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}
/* 顶栏：标题左 + 领域开关右，不再叠两排标签 */
#chrome-row {
  align-items: center !important;
  justify-content: space-between !important;
  flex-wrap: nowrap !important;
  gap: 12px 20px !important;
  margin: 0 0 2px !important;
}
#chrome-row > * {
  min-width: 0 !important;
}
#chrome-row > *:first-child {
  flex: 1 1 auto !important;
  width: auto !important;
  max-width: none !important;
}
#chrome-row > #domain-switch {
  flex: 0 0 auto !important;
  flex-basis: auto !important;
  width: auto !important;
  max-width: none !important;
  display: flex !important;
  justify-content: flex-end !important;
}
#app-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  margin: 0;
  padding: 2px 0;
  border-bottom: none;
  text-align: left;
}
#app-header .brand {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  width: auto;
}
#app-header h1 {
  margin: 0;
  font-size: 1.18rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: #1c1b19;
  line-height: 1.2;
  text-align: left;
  width: auto;
}
#domain-switch {
  margin: 0 !important;
  padding: 0 !important;
}
#domain-switch .label-wrap,
#domain-switch > label,
#domain-switch span[data-testid="block-info"] {
  display: none !important;
}
#domain-switch .form,
#domain-switch .wrap,
#domain-switch .wrap-inner,
#domain-switch fieldset,
#domain-switch [class*="radio"] {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#domain-switch .wrap,
#domain-switch .form,
#domain-switch fieldset,
#domain-switch [class*="radio"] {
  display: inline-flex !important;
  flex-wrap: nowrap !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 5px !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 999px !important;
  background: #e8e4db !important;
}
#domain-switch label,
#domain-switch label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 132px !important;
  margin: 0 !important;
  padding: 10px 36px !important;
  border: none !important;
  border-radius: 999px !important;
  background: transparent !important;
  color: #6b6860 !important;
  font-size: 1.05rem !important;
  font-weight: 650 !important;
  letter-spacing: 0.08em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: static !important;
  top: auto !important;
}
#domain-switch label:has(input[type="radio"]:checked) {
  background: #2c2a26 !important;
  border: none !important;
  color: #faf9f6 !important;
  font-weight: 700 !important;
}
#domain-switch input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
/* 任务标签 + 轻量操作同一行 */
#nav-row {
  align-items: flex-end !important;
  justify-content: space-between !important;
  gap: 10px 16px !important;
  margin: 0 0 10px !important;
}
#nav-row > div {
  min-width: 0 !important;
}
#nav-tasks {
  flex: 1 1 auto !important;
}
#nav-actions {
  flex: 0 0 auto !important;
  width: auto !important;
  max-width: none !important;
  display: flex !important;
  align-items: center !important;
  justify-content: flex-end !important;
  gap: 8px !important;
  padding: 0 0 6px !important;
}
#nav-actions > div {
  width: auto !important;
  flex: 0 0 auto !important;
}
#task-tabs {
  margin: 0 !important;
  padding: 0 !important;
}
#task-tabs .label-wrap,
#task-tabs > label,
#task-tabs span[data-testid="block-info"] {
  display: none !important;
}
#task-tabs .form,
#task-tabs .wrap,
#task-tabs .wrap-inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#task-tabs .wrap,
#task-tabs .form,
#task-tabs fieldset,
#task-tabs [class*="radio"] {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: flex-end !important;
  gap: 0 !important;
  border: none !important;
  border-bottom: 1px solid #d4d0c6 !important;
  padding: 0 2px !important;
  background: transparent !important;
}
#task-tabs label,
#task-tabs label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 72px !important;
  margin: 0 4px 0 0 !important;
  padding: 7px 14px 8px !important;
  border: 1px solid #d4d0c6 !important;
  border-bottom: none !important;
  border-radius: 8px 8px 0 0 !important;
  background: #e8e4db !important;
  color: #6b6860 !important;
  font-size: 0.86rem !important;
  font-weight: 550 !important;
  letter-spacing: 0.02em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: relative !important;
  top: 1px !important;
}
#task-tabs label:has(input[type="radio"]:checked) {
  background: #faf9f6 !important;
  color: #1c1b19 !important;
  font-weight: 650 !important;
  z-index: 1 !important;
}
#task-tabs input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
#task-brief {
  margin: 0 0 12px !important;
  padding: 0 !important;
}
#task-brief .task-brief {
  padding: 12px 14px;
  background: #ffffff;
  border: 1px solid #e0dcd2;
  border-radius: 6px;
}
#task-brief .task-brief p {
  margin: 0 0 8px;
  font-size: 1.05rem;
  line-height: 1.6;
  color: #1c1b19;
}
#task-brief .task-brief p:last-child {
  margin-bottom: 0;
}
#task-brief .k {
  font-size: 1.05rem;
  font-weight: 700;
  color: #2c2a26;
}
#clear-results-btn,
#reset-form-btn {
  min-height: 30px !important;
  width: auto !important;
  min-width: 88px !important;
  padding: 0 12px !important;
  border-radius: 6px !important;
  font-weight: 550 !important;
  font-size: 0.8rem !important;
}
.btn-hint {
  margin: 0 !important;
  padding: 0 4px !important;
  font-size: 0.72rem !important;
  color: #9a968c !important;
  line-height: 1.3 !important;
  text-align: center !important;
  max-width: none !important;
  white-space: nowrap !important;
}
/* 紧跟顶栏两按钮：一行模板说明 */
.tpl-guide {
  margin: 0 0 8px !important;
  padding: 6px 10px !important;
  background: #ffffff;
  border: 1px solid #e0dcd2;
  border-radius: 6px;
  font-size: 0.76rem;
  color: #4a4842;
  line-height: 1.4;
}
.tpl-guide strong {
  color: #1c1b19;
  font-weight: 650;
}
.tpl-guide p {
  margin: 0 !important;
}
/* 主工作区 */
#work-row {
  gap: 10px !important;
  align-items: stretch !important;
}
#col-input, #col-output {
  border: 1px solid #d4d0c6;
  background: #faf9f6;
  border-radius: 8px;
  padding: 10px 12px 12px !important;
  box-shadow: none !important;
}
/* 与任务选项「knowledge_graph - 知识图谱」同字号 */
.panel-label {
  margin: 0 0 6px;
  padding: 0 0 4px;
  border-bottom: 1px solid #e6e2d8;
  font-size: 0.95rem;
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
  color: #1c1b19;
  font-family: inherit;
  line-height: 1.4;
}
.panel-label.spaced {
  margin-top: 8px;
}
#run-btn[disabled],
#run-btn:disabled,
button.primary:disabled {
  opacity: 0.65 !important;
  cursor: not-allowed !important;
}
/* 控件 */
.gradio-container .block {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin-bottom: 4px !important;
}
.gradio-container .form,
.gradio-container .wrap,
.gradio-container .wrap-inner,
.gradio-container .secondary-wrap,
.gradio-container .padded,
.gradio-container .block > .wrap {
  background: transparent !important;
}
.gradio-container label,
.gradio-container .label-wrap span,
.gradio-container .block > label,
.gradio-container span[data-testid="block-info"] {
  color: #1c1b19 !important;
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  background: transparent !important;
  line-height: 1.4 !important;
  font-family: inherit !important;
}
.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input:not([type="radio"]):not([type="checkbox"]),
.gradio-container select {
  color: #1c1b19 !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
.gradio-container textarea:focus,
.gradio-container input:focus {
  border-color: #8a867c !important;
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(44, 42, 38, 0.06) !important;
}
.gradio-container .dropdown-arrow,
.gradio-container [class*="container"] > .wrap {
  background: #ffffff !important;
}
.gradio-container .checkbox-label,
.gradio-container .radio-label,
.gradio-container label:has(input[type="radio"]),
.gradio-container label:has(input[type="checkbox"]),
.gradio-container .wrap label {
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  color: #1c1b19 !important;
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  line-height: 1.4 !important;
  box-shadow: none !important;
  transition: border-color 0.12s ease, background 0.12s ease;
}
/* 下拉（领域 meeting - 会议 等）与任务选项同字号 */
.gradio-container .wrap .single-select,
.gradio-container [class*="secondary-wrap"] span,
.gradio-container .dropdown-arrow + div,
.gradio-container input[type="text"],
.gradio-container [role="listbox"],
.gradio-container [role="option"],
.gradio-container [role="listbox"] *,
.gradio-container [role="option"] *,
.gradio-container .wrap.svelte-select-input,
.gradio-container .wrap .token,
.gradio-container .wrap .token > *,
.gradio-container .wrap input,
.gradio-container .secondary-wrap,
.gradio-container .secondary-wrap * {
  font-size: 0.95rem !important;
  font-weight: 500 !important;
  line-height: 1.4 !important;
  color: #1c1b19 !important;
  font-family: inherit !important;
}
.gradio-container .checkbox-label:has(input:checked),
.gradio-container .radio-label:has(input:checked),
.gradio-container label:has(input[type="radio"]:checked),
.gradio-container label:has(input[type="checkbox"]:checked) {
  background: #f3f1eb !important;
  border-color: #8a867c !important;
  color: #1c1b19 !important;
}
.gradio-container input[type="radio"],
.gradio-container input[type="checkbox"] {
  accent-color: #2c2a26 !important;
}
#task-tabs label:has(input[type="radio"]) {
  box-shadow: none !important;
}
#domain-switch label:has(input[type="radio"]) {
  background: transparent !important;
  border: none !important;
  border-radius: 999px !important;
  color: #6b6860 !important;
}
#domain-switch label:has(input[type="radio"]:checked) {
  background: #2c2a26 !important;
  border: none !important;
  color: #faf9f6 !important;
}
#task-tabs label:has(input[type="radio"]) {
  background: #e8e4db !important;
  border: 1px solid #d4d0c6 !important;
  border-bottom: none !important;
  border-radius: 8px 8px 0 0 !important;
  color: #6b6860 !important;
}
#task-tabs label:has(input[type="radio"]:checked) {
  background: #faf9f6 !important;
  border-color: #d4d0c6 !important;
  color: #1c1b19 !important;
}
/* 按钮 */
#run-btn,
button.primary,
.primary {
  background: #2c2a26 !important;
  color: #faf9f6 !important;
  border: 1px solid #2c2a26 !important;
  border-radius: 6px !important;
  min-height: 34px !important;
  font-weight: 550 !important;
  letter-spacing: 0.03em !important;
  box-shadow: none !important;
  margin-top: 4px !important;
}
#run-btn:hover,
button.primary:hover {
  background: #1a1916 !important;
}
#clear-results-btn,
#reset-form-btn,
button.secondary {
  background: #ffffff !important;
  color: #1c1b19 !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  min-height: 34px !important;
}
#clear-results-btn:hover,
#reset-form-btn:hover,
button.secondary:hover {
  background: #f3f1eb !important;
  border-color: #8a867c !important;
}
/* 下拉 */
.gradio-container [role="listbox"],
.gradio-container [role="option"] {
  background: #ffffff !important;
  color: #1c1b19 !important;
  border-color: #d4d0c6 !important;
}
.gradio-container [role="option"][aria-selected="true"],
.gradio-container [role="option"]:hover {
  background: #ebe8e1 !important;
  color: #1c1b19 !important;
}
/* 图库 */
.gradio-container .gallery {
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  box-shadow: none !important;
}
/* 上传：勿裁切文案；固定 height 容易遮挡，统一用 min-height */
#col-input .block,
#tpl-box .block {
  max-width: 100% !important;
  overflow: visible !important;
}
#col-input .block:has([data-testid="file"]),
#tpl-box .block:has([data-testid="file"]),
#col-input .block:has(.upload-container),
#tpl-box .block:has(.upload-container) {
  overflow: visible !important;
  min-height: 88px !important;
  height: auto !important;
  max-height: none !important;
}
.gradio-container [data-testid="file"],
.gradio-container [data-testid="file"] > .wrap,
.gradio-container [data-testid="file"] .upload-container,
.gradio-container .upload-container,
#col-input .upload-container,
#tpl-box .upload-container,
#tpl-file .upload-container {
  background: #ffffff !important;
  border: 1px dashed #c8c4b8 !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  color: #1c1b19 !important;
  min-height: 96px !important;
  height: auto !important;
  max-height: none !important;
  padding: 16px 12px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  overflow: visible !important;
  box-sizing: border-box !important;
}
/* 覆盖 Gradio 可能写入的固定高度 */
.gradio-container [data-testid="file"][style*="height"],
.gradio-container .upload-container[style*="height"] {
  height: auto !important;
  min-height: 96px !important;
  max-height: none !important;
}
.gradio-container .upload-container .wrap,
.gradio-container .upload-container .center,
.gradio-container .upload-container .wrap.center,
.gradio-container .upload-container .wrap.default,
.gradio-container .upload-container .wrap.full,
.gradio-container .upload-container > div {
  min-height: 56px !important;
  max-height: none !important;
  height: auto !important;
  padding: 6px 8px !important;
  margin: 0 !important;
  overflow: visible !important;
  white-space: normal !important;
  text-overflow: clip !important;
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 6px !important;
  line-height: 1.45 !important;
}
.gradio-container .upload-container svg,
.gradio-container .upload-container img {
  width: 16px !important;
  height: 16px !important;
  flex-shrink: 0 !important;
  margin: 0 !important;
}
.gradio-container .upload-container span,
.gradio-container .upload-container p,
.gradio-container .upload-container button,
.gradio-container .upload-container label,
.gradio-container .upload-container .or {
  font-size: 0.72rem !important;
  line-height: 1.45 !important;
  margin: 0 !important;
  padding: 0 !important;
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  word-break: keep-all !important;
  max-width: none !important;
  height: auto !important;
  max-height: none !important;
  color: #1c1b19 !important;
  opacity: 1 !important;
  visibility: visible !important;
}
/* 文本框可纵向拉伸；左侧「文本」与右侧「日志」初始同高对齐 */
#col-input textarea,
#log-box textarea,
#compiled-tpl textarea {
  resize: vertical !important;
  overflow: auto !important;
}
#input-text textarea,
#log-box textarea {
  min-height: 20rem !important;
  height: 20rem !important;
  max-height: none !important;
  font-size: 0.9rem !important;
  line-height: 1.45 !important;
  box-sizing: border-box !important;
}
#tpl-box textarea {
  min-height: 6rem !important;
}
.gradio-container .file-preview-holder {
  overflow-x: hidden !important;
  overflow-y: auto !important;
  max-width: 100% !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  margin-top: 4px !important;
}
.gradio-container table.file-preview {
  width: 100% !important;
  max-width: 100% !important;
  table-layout: fixed !important;
  color: #1c1b19 !important;
  margin: 0 !important;
}
.gradio-container tr.file,
.gradio-container table.file-preview tbody > tr,
.gradio-container table.file-preview tbody > tr:nth-child(odd),
.gradio-container table.file-preview tbody > tr:nth-child(even) {
  display: flex !important;
  width: 100% !important;
  max-width: 100% !important;
  background: #f0eee9 !important;
  border-bottom: 1px solid #ddd9d0 !important;
  color: #1c1b19 !important;
}
.gradio-container tr.file:hover {
  background: #e6e2d8 !important;
}
.gradio-container td.filename,
.gradio-container td.filename .stem,
.gradio-container td.filename .ext,
.gradio-container .file-preview-holder span {
  color: #1c1b19 !important;
  opacity: 1 !important;
  font-weight: 500 !important;
}
.gradio-container td.filename {
  flex: 1 1 auto !important;
  min-width: 0 !important;
  overflow: hidden !important;
}
.gradio-container td.filename .stem {
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  white-space: nowrap !important;
}
.gradio-container td.download {
  flex: 0 0 auto !important;
  min-width: 0 !important;
  width: auto !important;
  max-width: 7rem !important;
  color: #4a4842 !important;
}
.gradio-container td.download a {
  color: #1c1b19 !important;
  text-decoration: none !important;
  font-weight: 500 !important;
}
.gradio-container td.download a:hover {
  text-decoration: underline !important;
  color: #000000 !important;
}
.gradio-container .label-clear-button {
  color: #4a4842 !important;
}
#col-input,
#tpl-box,
#tpl-box > *,
#tpl-box .block {
  overflow-x: hidden !important;
  max-width: 100% !important;
}
#col-input,
#tpl-box,
.gradio-container .file-preview-holder {
  scrollbar-width: thin;
}
#col-input::-webkit-scrollbar:horizontal,
#tpl-box::-webkit-scrollbar:horizontal,
.gradio-container .file-preview-holder::-webkit-scrollbar:horizontal {
  height: 0 !important;
  display: none !important;
}
#tpl-box textarea,
#tpl-box input,
#col-input textarea,
#col-output textarea {
  max-width: 100% !important;
  overflow-x: hidden !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
/* 可编辑模板 */
#compiled-wrap {
  margin-top: 10px;
  padding: 10px 10px 6px;
  border: 1px solid #c8c4b8;
  background: #ffffff;
  border-radius: 8px;
}
#compiled-wrap .step-banner {
  margin: 0 0 8px;
  font-size: 0.78rem;
  color: #4a4842;
  line-height: 1.45;
}
#compiled-wrap .step-banner strong {
  color: #1c1b19;
  font-weight: 650;
}
#compiled-tpl textarea {
  background: #faf9f6 !important;
  border: 1px solid #d4d0c6 !important;
  min-height: 9rem !important;
  color: #1c1b19 !important;
  border-radius: 6px !important;
}
#friendly-template textarea {
  background: #fbfaf7 !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 6px !important;
  color: #1c1b19 !important;
  min-height: 14rem !important;
  line-height: 1.55 !important;
  font-size: 0.9rem !important;
  font-family: inherit !important;
}
#clear-tpl-btn {
  margin-top: 2px !important;
}
/* 下载列表 */
.dl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid #d4d0c6;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}
.dl-item {
  border-bottom: 1px solid #ebe8e1;
}
.dl-item:last-child {
  border-bottom: none;
}
.dl-item a {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 12px 14px;
  text-decoration: none !important;
  color: #1c1b19 !important;
}
.dl-item a:hover {
  background: #f3f1eb;
}
.dl-name {
  font-size: 0.9rem;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dl-meta {
  flex: 0 0 auto;
  font-size: 0.75rem;
  color: #9a968c;
  font-variant-numeric: tabular-nums;
}
.dl-empty {
  margin: 0;
  padding: 12px 10px;
  border: 1px solid #e6e2d8;
  background: #ffffff;
  color: #9a968c;
  font-size: 0.82rem;
  border-radius: 6px;
  text-align: center;
}
#log-box textarea {
  font-family: "IBM Plex Mono", "Cascadia Mono", "Consolas", monospace !important;
}
/* Markdown 预览区 */
#md-preview {
  margin: 8px 0 10px !important;
  padding: 12px 14px !important;
  background: #ffffff !important;
  border: 1px solid #d4d0c6 !important;
  border-radius: 8px !important;
  max-height: 28rem !important;
  overflow-y: auto !important;
  font-size: 0.9rem !important;
  line-height: 1.55 !important;
  color: #1c1b19 !important;
}
#md-preview h1, #md-preview h2, #md-preview h3 {
  margin: 0.6em 0 0.35em !important;
  font-weight: 650 !important;
}
#md-preview table {
  border-collapse: collapse !important;
  width: 100% !important;
  font-size: 0.85rem !important;
  margin: 0.5em 0 !important;
}
#md-preview th, #md-preview td {
  border: 1px solid #d4d0c6 !important;
  padding: 4px 8px !important;
}
#md-preview pre, #md-preview code {
  font-size: 0.82rem !important;
}
#memory-review {
  margin: 8px 0 10px !important;
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
}
.memory-review {
  display: flex;
  flex-direction: column;
  gap: 0;
  border: 1px solid #d4d0c6;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}
.review-heading {
  padding: 12px 16px 8px;
  font-weight: 650;
  color: #1c1b19;
  background: #faf9f6;
  border-bottom: 1px solid #ebe8e1;
}
.review-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 1px minmax(210px, 32%);
  gap: 0;
  border-bottom: 1px solid #ebe8e1;
}
.review-row:last-child {
  border-bottom: none;
}
.review-left {
  padding: 11px 14px;
  line-height: 1.65;
  color: #1c1b19;
  word-break: break-word;
}
.review-rule {
  background: #c8c4b8;
}
.review-right {
  padding: 9px 10px;
  background: #faf9f6;
}
.mem-mark {
  text-decoration: underline;
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
  background: #fff6c7;
  color: #1c1b19;
}
.mem-card {
  display: block;
  padding: 9px 10px;
  border-left: 3px solid #6b6860;
  background: #ffffff;
  color: #1c1b19 !important;
  text-decoration: none !important;
  border-radius: 4px;
}
.mem-card + .mem-card {
  margin-top: 8px;
}
.mem-card-title {
  font-size: 0.82rem;
  font-weight: 650;
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mem-card-meta {
  font-size: 0.74rem;
  color: #6b6860;
  line-height: 1.35;
  margin-bottom: 4px;
}
.mem-card-source {
  font-size: 0.72rem;
  color: #9a968c;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mem-empty {
  min-height: 1px;
}
.review-analysis {
  font-size: 0.8rem;
  color: #3a3832;
  line-height: 1.5;
  margin-top: 4px;
  white-space: pre-wrap;
}
.review-fix {
  font-size: 0.78rem;
  color: #6b6860;
  line-height: 1.45;
  margin-top: 4px;
}
.review-cite {
  font-size: 0.78rem;
  color: #3a3832;
  margin-top: 6px;
  font-weight: 650;
}
.review-excerpt {
  font-size: 0.76rem;
  color: #6b6860;
  margin-top: 4px;
  line-height: 1.45;
}
.quiz-hint {
  font-size: 0.78rem;
  font-weight: 400;
  color: #6b6860;
  margin-top: 4px;
}
.quiz-item {
  padding: 12px 16px;
  border-bottom: 1px solid #ebe8e1;
}
.quiz-item:last-child {
  border-bottom: none;
}
.quiz-q {
  font-weight: 650;
  line-height: 1.55;
  margin-bottom: 6px;
}
.quiz-dim {
  font-size: 0.76rem;
  color: #6b6860;
  margin-bottom: 8px;
}
.quiz-answer summary {
  cursor: pointer;
  color: #3a3832;
  font-size: 0.86rem;
  user-select: none;
}
.quiz-answer ol {
  margin: 8px 0 0 1.2em;
  padding: 0;
  line-height: 1.55;
}
.quiz-empty {
  padding: 14px 16px;
  color: #6b6860;
}
.quiz-section {
  padding: 12px 16px 4px;
  font-weight: 700;
  font-size: 0.92rem;
  color: #2c2a26;
  background: #f7f5f0;
  border-bottom: 1px solid #ebe8e1;
}
.quiz-bank-query {
  padding: 6px 16px 10px;
  font-size: 0.78rem;
  color: #6b6860;
}
.quiz-stem {
  line-height: 1.85;
  margin: 6px 0 8px;
  word-break: keep-all;
  overflow-wrap: anywhere;
}
.quiz-stem p {
  margin: 0 0 0.45em;
  text-indent: 0 !important;
}
.quiz-stem p:last-child {
  margin-bottom: 0;
}
.quiz-stem img.quiz-formula,
.quiz-opts img.quiz-formula,
.quiz-analysis img.quiz-formula,
#memory-review img.quiz-formula {
  display: inline !important;
  vertical-align: middle !important;
  height: 1.45em;
  width: auto !important;
  max-width: none !important;
  max-height: 2.6em;
  margin: 0 1px;
}
.quiz-stem img.quiz-figure,
.quiz-analysis img.quiz-figure {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 8px 0;
}
.quiz-blank {
  display: inline-block;
  min-width: 4em;
  border-bottom: 1px solid #1c1b19;
  line-height: 1;
  margin: 0 0.15em;
}
.quiz-opts {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  line-height: 1.8;
}
.quiz-opts li {
  margin: 4px 0;
}
.quiz-key {
  margin: 8px 0 6px;
  font-weight: 650;
}
.quiz-analysis {
  line-height: 1.55;
}
.quiz-analysis img {
  max-width: 100%;
  height: auto;
}
.quiz-match-hint {
  margin: 4px 2px 2px;
  padding: 8px 10px;
  font-size: 0.8rem;
  line-height: 1.45;
  color: #3a3832;
  background: #f4f1ea;
  border-radius: 8px;
}
.library-hero {
  padding: 28px 20px 22px;
  text-align: center;
  background: #faf9f6;
  border-bottom: 1px solid #ebe8e1;
}
.library-caption {
  margin: 0;
  font-size: 0.86rem;
  color: #6b6860;
}
.library-count {
  margin: 6px 0 0;
  font-size: 0.95rem;
  color: #1c1b19;
}
.library-count strong {
  display: block;
  font-size: 2.6rem;
  font-weight: 650;
  letter-spacing: -0.04em;
  line-height: 1.05;
}
.library-files, .library-items, .library-conflicts, .library-peace {
  padding: 12px 16px 16px;
}
.library-files ul, .library-items ul {
  margin: 0;
  padding-left: 1.2em;
  line-height: 1.6;
}
.library-items span {
  color: #9a968c;
  font-size: 0.78rem;
  margin-left: 8px;
}
.library-verdict {
  margin: 12px 0 0;
  padding: 12px 14px;
  border: 1px solid #ebe8e1;
  border-radius: 8px;
  background: #ffffff;
}
.library-verdict blockquote {
  margin: 8px 0;
  padding-left: 10px;
  border-left: 3px solid #c8c4b8;
  color: #4a4842;
  font-size: 0.86rem;
}
.library-ask {
  margin: 10px 0 8px;
  font-weight: 650;
}
.library-verdict button {
  margin: 0 8px 0 0;
  padding: 6px 12px;
  border: 1px solid #d4d0c6;
  border-radius: 6px;
  background: #faf9f6;
  color: #1c1b19;
  cursor: pointer;
}
.library-verdict button.is-on {
  background: #2c2a26;
  color: #faf9f6;
  border-color: #2c2a26;
}
.library-picked {
  min-height: 1.2em;
  font-size: 0.8rem;
  color: #6b6860;
  margin: 8px 0 0;
}
.library-peace {
  color: #6b6860;
}
@media (max-width: 820px) {
  .review-row {
    grid-template-columns: 1fr;
  }
  .review-rule {
    height: 1px;
  }
}
#img-gallery {
  margin: 0 0 10px !important;
}
@media (max-width: 1100px) {
  .gradio-container {
    max-width: 100% !important;
    padding: 12px 12px 24px !important;
  }
  #col-input, #col-output {
    padding: 10px !important;
  }
}
@media (max-width: 820px) {
  #chrome-row,
  #nav-row {
    flex-wrap: wrap !important;
  }
  #chrome-row > #domain-switch,
  #nav-actions {
    width: 100% !important;
  }
  #domain-switch .wrap,
  #domain-switch .form,
  #domain-switch fieldset {
    width: 100% !important;
  }
  #domain-switch label,
  #domain-switch label:has(input[type="radio"]) {
    flex: 1 1 0 !important;
  }
  #nav-actions {
    justify-content: flex-start !important;
    padding-bottom: 0 !important;
  }
  #work-row {
    flex-direction: column !important;
    flex-wrap: nowrap !important;
  }
  #col-input,
  #col-output {
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 auto !important;
  }
}
"""


def _build_theme() -> gr.themes.Base:
    return gr.themes.Base(
        primary_hue=gr.themes.colors.neutral,
        secondary_hue=gr.themes.colors.neutral,
        neutral_hue=gr.themes.colors.neutral,
    ).set(
        body_background_fill="#f0eee9",
        body_background_fill_dark="#f0eee9",
        block_background_fill="#ffffff",
        block_border_width="0px",
        block_shadow="none",
        button_primary_background_fill="#2c2a26",
        button_primary_background_fill_hover="#1a1916",
        button_primary_text_color="#faf9f6",
        border_color_primary="#d4d0c6",
        input_background_fill="#ffffff",
    )


def build_app() -> gr.Blocks:
    initial_domain = "meeting"
    initial_choices = _task_choices(initial_domain)
    initial_task = initial_choices[0][1] if initial_choices else None
    show_user, show_project, show_subject = _scope_field_visibility(
        initial_domain, initial_task or ""
    )
    initial_policy = _line_policy(initial_domain, initial_task or "")
    show_config = (
        bool(initial_policy and initial_policy.cli_mode)
        or show_user
        or bool(initial_policy and initial_policy.sidecar)
        or initial_task == "quiz"
        or initial_task == "minutes_generation"
    )
    with gr.Blocks(title="AgentFlow测试") as demo:
        with gr.Row(elem_id="chrome-row", equal_height=True):
            gr.HTML(
                """
                <header id="app-header">
                  <div class="brand">
                    <h1>AgentFlow测试</h1>
                  </div>
                </header>
                """
            )
            domain = gr.Radio(
                choices=DOMAIN_CHOICES,
                value=initial_domain,
                show_label=False,
                container=False,
                elem_id="domain-switch",
            )
        with gr.Row(elem_id="nav-row", equal_height=True):
            with gr.Column(scale=8, min_width=240, elem_id="nav-tasks"):
                tasks = gr.Radio(
                    choices=initial_choices,
                    value=initial_task,
                    show_label=False,
                    container=False,
                    elem_id="task-tabs",
                )
            with gr.Row(elem_id="nav-actions"):
                clear_results_btn = gr.Button(
                    "清空结果",
                    variant="secondary",
                    elem_id="clear-results-btn",
                    size="sm",
                )
                reset_form_btn = gr.Button(
                    "重置表单",
                    variant="secondary",
                    elem_id="reset-form-btn",
                    size="sm",
                )
        with gr.Row(elem_id="work-row", equal_height=False):
            with gr.Column(scale=5, min_width=420, elem_id="col-input"):
                config_label = gr.HTML(
                    '<div class="panel-label">配置</div>',
                    visible=show_config,
                )
                mode_dropdown = gr.Dropdown(
                    label="组织模式",
                    choices=MULTI_STYLE_MODE_CHOICES,
                    value=DEFAULT_MULTI_STYLE_MODE,
                    visible=False,
                    elem_id="mode-select",
                )
                perspective_dropdown = gr.Dropdown(
                    label="视角",
                    choices=_profile_dropdown_choices(initial_domain),
                    value=_profile_dropdown_default(initial_domain),
                    visible=initial_task == "minutes_generation",
                    elem_id="perspective-select",
                )
                user_id = gr.Textbox(
                    label="用户 ID（可选）",
                    lines=1,
                    max_lines=1,
                    placeholder="资料入库/期末划重点：同一用户使用自己的知识库",
                    visible=show_user,
                )
                project_id = gr.Textbox(
                    label="项目 ID（可选，会议记忆）",
                    lines=1,
                    max_lines=1,
                    placeholder="会议域：写入并绑定该项目",
                    visible=show_project,
                )
                subject = gr.Textbox(
                    label="学科（可选，知识库范围）",
                    lines=1,
                    max_lines=1,
                    placeholder="资料入库/期末划重点：同一用户 + 学科使用同一知识库",
                    visible=show_subject,
                )
                with gr.Group(visible=False, elem_id="quiz-box") as quiz_box:
                    quiz_difficulty = gr.Dropdown(
                        label="题目难度",
                        choices=["不指定", "容易", "较易", "适中", "较难", "困难"],
                        value="不指定",
                    )
                    quiz_qtype = gr.Dropdown(
                        label="题目类型",
                        choices=quiz_qtype_choices(""),
                        value=QUIZ_NONE,
                    )
                    quiz_match_hint = gr.HTML("")
                with gr.Group(visible=False, elem_id="trace-box") as trace_box:
                    gr.HTML(
                        '<div class="tpl-guide">'
                        "<strong>溯源材料</strong>：用户关键点、用户笔记。"
                        "上传会议文件所在目录若已有同名文件会自动带上；这里填写则覆盖。"
                        "</div>"
                    )
                    keypoints_upload = gr.File(
                        label="用户关键点文件",
                        file_count="single",
                        file_types=[".txt"],
                        type="filepath",
                    )
                    keypoints_text = gr.Textbox(
                        label="用户关键点",
                        lines=4,
                        max_lines=16,
                        placeholder="每行一条关键点",
                    )
                    notes_upload = gr.File(
                        label="用户笔记文件",
                        file_count="single",
                        file_types=[".txt"],
                        type="filepath",
                    )
                    notes_text = gr.Textbox(
                        label="用户笔记",
                        lines=4,
                        max_lines=16,
                        placeholder="原文片段 -> 用户批注",
                    )
                gr.HTML('<div class="panel-label spaced">输入</div>')
                input_upload = gr.File(
                    label="文本文件",
                    file_count="single",
                    file_types=[".txt"],
                    type="filepath",
                )
                input_text = gr.Textbox(
                    label="文本",
                    lines=12,
                    max_lines=40,
                    elem_id="input-text",
                    placeholder="粘贴会议记录或笔记原文…",
                )
                with gr.Group(visible=True, elem_id="render-template-wrap") as template_wrap:
                    gr.HTML('<div class="panel-label spaced">渲染模板（可选）</div>')
                    gr.HTML(
                        '<div class="tpl-guide">'
                        "给最终输出套一层版式。可写自然语言，例如"
                        "「分三段：纪要本段约200字；待办表约3行；风险表约3行」"
                        "或「全文约800字」。点「运行」后会变成能看懂的标题和表格，"
                        "改完再点「确认模板并运行」。"
                        "「纪要约200字」只限制那一段，「全文约800字」才限制整篇。"
                        "</div>"
                    )
                    with gr.Column(elem_id="tpl-box"):
                        template_upload = gr.File(
                            label="模板文件",
                            file_count="single",
                            file_types=[".md", ".txt"],
                            type="filepath",
                            elem_id="tpl-file",
                        )
                        template_text = gr.Textbox(
                            label="模板或自然语言描述",
                            lines=6,
                            max_lines=30,
                            placeholder=(
                                "示例：分三段。第一段纪要本段约200字；"
                                "第二段待办表约3行；第三段风险表约3行"
                            ),
                        )
                    with gr.Group(visible=False, elem_id="compiled-wrap") as compiled_wrap:
                        gr.HTML(
                            '<p class="step-banner">'
                            "<strong>可编辑版式</strong>　这是按你的描述排好的稿纸，"
                            "不是给机器看的占位符。"
                            "【版式】区分全文多少字和某一段多少字；"
                            "下面可改标题、表格列，空着的位置生成时填写。"
                            "</p>"
                        )
                        friendly_template = gr.Textbox(
                            label="可编辑版式（不是占位符）",
                            lines=10,
                            max_lines=40,
                            visible=True,
                            elem_id="friendly-template",
                            placeholder="自然语言模板生成后会显示在这里。",
                            interactive=True,
                        )
                        # 隐藏状态：保存原始占位模板，用于把友好模板还原后生成纪要
                        edit_state = gr.State(value=None)
                        clear_tpl_btn = gr.Button(
                            "清除预览",
                            variant="secondary",
                            elem_id="clear-tpl-btn",
                            size="sm",
                        )
                run_button = gr.Button("运行", variant="primary", elem_id="run-btn")

            with gr.Column(scale=8, min_width=480, elem_id="col-output"):
                gr.HTML('<div class="panel-label">结果</div>')
                task_brief = gr.HTML(
                    value=_task_brief_html(initial_task or ""),
                    elem_id="task-brief",
                )
                log_output = gr.Textbox(
                    label="日志",
                    lines=12,
                    max_lines=40,
                    elem_id="log-box",
                )
                html_kwargs = {
                    "value": "",
                    "label": "对照批注",
                    "elem_id": "memory-review",
                    "visible": False,
                }
                try:
                    memory_review = gr.HTML(**html_kwargs, sanitize_html=False)
                except TypeError:
                    try:
                        memory_review = gr.HTML(**html_kwargs, sanitize=False)
                    except TypeError:
                        memory_review = gr.HTML(**html_kwargs)
                rewrite_btn = gr.Button(
                    "同意采用订正笔记",
                    variant="secondary",
                    elem_id="rewrite-btn",
                    visible=False,
                )
                md_preview = gr.Markdown(
                    value="",
                    label="Markdown 预览",
                    elem_id="md-preview",
                    visible=False,
                )
                image_output = gr.Gallery(
                    label="图片",
                    columns=2,
                    height=200,
                    visible=False,
                    elem_id="img-gallery",
                )
                download_files = gr.File(
                    label="下载文件",
                    file_count="multiple",
                    visible=False,
                    elem_id="download-files",
                )
                files_output = gr.HTML(
                    label="文件",
                    value=EMPTY_DOWNLOAD,
                )

        hitl_outputs = [
            friendly_template,
            edit_state,
            compiled_wrap,
            run_button,
        ]
        result_outputs = [
            log_output,
            image_output,
            memory_review,
            rewrite_btn,
            md_preview,
            download_files,
            files_output,
        ]
        side_btns = [clear_results_btn, reset_form_btn, clear_tpl_btn]
        domain.change(
            update_domain,
            inputs=[domain, input_upload],
            outputs=[
                tasks,
                task_brief,
                config_label,
                mode_dropdown,
                perspective_dropdown,
                user_id,
                project_id,
                subject,
                quiz_box,
                trace_box,
                template_wrap,
                input_upload,
                *hitl_outputs,
            ],
        )
        tasks.change(
            update_task_panel,
            inputs=[domain, tasks, input_upload],
            outputs=[
                task_brief,
                config_label,
                mode_dropdown,
                perspective_dropdown,
                user_id,
                project_id,
                subject,
                quiz_box,
                trace_box,
                template_wrap,
                input_upload,
                *hitl_outputs,
            ],
        ).then(
            on_task_switch_quiz_filters,
            inputs=[
                domain,
                tasks,
                quiz_qtype,
                input_upload,
                input_text,
            ],
            outputs=[
                quiz_qtype,
                quiz_match_hint,
            ],
        )
        input_upload.change(
            on_quiz_notes_change,
            inputs=[
                quiz_qtype,
                input_upload,
                input_text,
            ],
            outputs=[
                quiz_qtype,
                quiz_match_hint,
            ],
        )
        input_text.blur(
            on_quiz_notes_change,
            inputs=[
                quiz_qtype,
                input_upload,
                input_text,
            ],
            outputs=[
                quiz_qtype,
                quiz_match_hint,
            ],
        )
        run_button.click(
            begin_run,
            inputs=[],
            outputs=[log_output, run_button, *side_btns],
            show_progress="hidden",
        ).then(
            run_from_ui,
            inputs=[
                domain,
                tasks,
                input_upload,
                input_text,
                template_upload,
                template_text,
                edit_state,
                friendly_template,
                mode_dropdown,
                user_id,
                project_id,
                subject,
                keypoints_upload,
                keypoints_text,
                notes_upload,
                notes_text,
                quiz_difficulty,
                quiz_qtype,
                perspective_dropdown,
            ],
            outputs=[*result_outputs, *hitl_outputs, *side_btns],
            show_progress="minimal",
        )
        clear_tpl_btn.click(
            clear_compiled_template,
            inputs=[],
            outputs=[log_output, *hitl_outputs],
        )
        rewrite_btn.click(
            rewrite_notes_from_ui,
            inputs=[],
            outputs=[log_output, md_preview, download_files, files_output],
            show_progress="minimal",
        )
        clear_results_btn.click(
            clear_results_only,
            inputs=[],
            outputs=result_outputs,
        )
        reset_form_btn.click(
            reset_form,
            inputs=[],
            outputs=[
                *result_outputs,
                input_upload,
                input_text,
                template_upload,
                template_text,
                mode_dropdown,
                perspective_dropdown,
                user_id,
                project_id,
                subject,
                quiz_difficulty,
                quiz_qtype,
                quiz_match_hint,
                keypoints_upload,
                keypoints_text,
                notes_upload,
                notes_text,
                *hitl_outputs,
            ],
        )
    _mount_bank_assets(demo)
    return demo


def _mount_bank_assets(demo) -> None:
    """把 /resources/aixue_paper/... 代理成可显示的图，避免打到 Gradio 本机 404。"""
    app = getattr(demo, "app", None)
    if app is None:
        return
    try:
        from fastapi.responses import Response
    except ImportError:
        return

    @app.get("/resources/{rest:path}")
    def _bank_resource(rest: str):
        from tools.exercise_search.images import fetch_image

        got = fetch_image("/resources/" + rest)
        if got is None:
            return Response(status_code=404)
        data, mime = got
        return Response(content=data, media_type=mime)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def main() -> None:
    build_app().launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=_env_int("GRADIO_SERVER_PORT", 7860),
        share=_env_bool("GRADIO_SHARE", False),
        theme=_build_theme(),
        css=CSS,
    )


if __name__ == "__main__":
    main()
