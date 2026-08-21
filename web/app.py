from __future__ import annotations
from .theme import CSS

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
    KIND_OBJECTIVE,
    SHARED_PROFILE_DIR,
    SHARED_ROLE_DIR,
    list_profile_entries_multi,
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
MONITOR_ON = "on"
MONITOR_OFF = "off"
MONITOR_CHOICES = [("关", MONITOR_OFF), ("监控", MONITOR_ON)]

PERSPECTIVE_OBJECTIVE = "objective"
KNOWLEDGE_SCOPE_LINES = frozenset({"library", "catalog", "checklist"})
OCR_TASK = "ocr_recognition"


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
    choices = [(ctx.line_cn_names.get(line, line), line) for line in ordered]
    if domain == "notes":
        choices.append(("OCR识别", OCR_TASK))
    return choices


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


def _profile_dirs(domain: str) -> list[Path]:
    """该 domain 可见的画像目录：域名下优先（客观/真人），公共客观画像与职业模板在后。"""
    dirs: list[Path] = []
    domain_dir = _profile_dir(domain)
    if domain_dir.is_dir():
        dirs.append(domain_dir)
    if SHARED_PROFILE_DIR.is_dir():
        dirs.append(SHARED_PROFILE_DIR)
    if SHARED_ROLE_DIR.is_dir():
        dirs.append(SHARED_ROLE_DIR)
    return dirs


def _profile_sample_path(domain: str, mode: str) -> Path:
    name = (
        "object_profile.json"
        if mode == PERSPECTIVE_OBJECTIVE
        else "personal_profile.json"
    )
    return _profile_dir(domain) / name


def _profile_dropdown_choices(domain: str) -> list[str]:
    return [item["label"] for item in list_profile_entries_multi(_profile_dirs(domain))]


def _profile_dropdown_default(domain: str) -> str:
    entries = list_profile_entries_multi(_profile_dirs(domain))
    for item in entries:
        if item["kind"] == KIND_OBJECTIVE:
            return item["label"]
    return entries[0]["label"] if entries else "客观 · 客观全员"


def _load_profile_json_text(domain: str, mode: str = PERSPECTIVE_OBJECTIVE, label: str = "") -> str:
    entries = list_profile_entries_multi(_profile_dirs(domain))
    if label:
        for item in entries:
            if item["label"] == label:
                return json.dumps(item["data"], ensure_ascii=False, indent=2)
        entry = next(
            (item for item in entries if item["kind"] == KIND_OBJECTIVE), None
        )
        if entry is not None:
            return json.dumps(entry["data"], ensure_ascii=False, indent=2)
    path = _profile_sample_path(domain, mode)
    if path.exists():
        return path.read_text(encoding="utf-8")
    # 客观画像已抽到跨域公共目录：domain 目录没有时回退
    if mode == PERSPECTIVE_OBJECTIVE:
        shared = SHARED_PROFILE_DIR / "object_profile.json"
        if shared.exists():
            return shared.read_text(encoding="utf-8")
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
        "inputs": "用户 ID、学科，以及多份课件/讲义/笔记（PPT/PDF/Word 等）",
        "outputs": "信息熵报告：知识增量 + 冲突点（Markdown/HTML）",
        "purpose": (
            "写入该用户该学科的知识库。课件定骨架，笔记标覆盖。"
            "不用指定 collection 名；同一用户 + 学科就是同一个库。"
        ),
    },
    "catalog": {
        "inputs": "用户 ID、学科。可选：老师划重点文本。课件和笔记不用再传",
        "outputs": "简要目录说明（章/主题/知识点数量与结构），正式目录写入该用户该学科的 JSON 文件",
        "purpose": (
            "从已入库知识库抽资料骨架和学生笔记，老师文本只用来标重点。"
            "不要上传目录 JSON；有历史目录则增量更新。"
        ),
    },
    "checklist": {
        "inputs": "用户 ID、学科、老师本次划重点文本。不要上传目录 JSON",
        "outputs": "复习清单 Markdown + HTML（重点分布、导图、图谱、知识点卡片、行动清单）",
        "purpose": (
            "按用户 ID + 学科自动读取已生成的知识目录，再用老师文本激活本次复习。"
            "不新建知识点、不改长期目录。"
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
    OCR_TASK: {
        "inputs": "PNG / JPG / JPEG 图片",
        "outputs": "服务器原始 OCR 文本、审校版 Markdown",
        "purpose": "把图片识别成可入库的 Markdown。生成的 LLM Markdown 可继续上传到资料入库。",
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

    library / catalog / checklist 虽不写项目记忆，但需要 user_id + subject 确定知识库作用域。
    """
    uses = _task_uses_memory(task)
    knowledge_scoped = domain == "notes" and task in KNOWLEDGE_SCOPE_LINES
    ocr_scoped = domain == "notes" and task == OCR_TASK
    needs_user = uses or knowledge_scoped
    needs_subject = uses or knowledge_scoped or ocr_scoped
    return (
        needs_user or ocr_scoped,
        uses and domain == "meeting",
        needs_subject and domain == "notes",
    )


_NOTE_SUFFIXES = {".txt", ".md"}
_LIBRARY_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".pptx", ".xlsx"}
_TEACHER_TEXT_TASKS = frozenset({"catalog", "checklist"})


def _scope_labels(task: str) -> tuple[dict[str, str], dict[str, str]]:
    if task in KNOWLEDGE_SCOPE_LINES or task == OCR_TASK:
        return (
            {
                "label": "用户 ID（必填）",
                "placeholder": "用来定位你的知识库，例如 user_001",
            },
            {
                "label": "学科（必填）",
                "placeholder": "用来定位这门课的知识库，例如 数学",
            },
        )
    return (
        {
            "label": "用户 ID（可选）",
            "placeholder": "填了则写入/读取该用户的记忆或知识库",
        },
        {
            "label": "学科（可选，知识库范围）",
            "placeholder": "同一用户 + 学科使用同一知识库",
        },
    )


def _input_copy(task: str) -> dict[str, str]:
    if task == OCR_TASK:
        return {
            "upload_label": "图片文件",
            "text_label": "文本",
            "text_placeholder": "OCR识别只需要上传图片。",
        }
    if task == "library":
        return {
            "upload_label": "资料文件（可多选：课件 / 讲义 / 笔记）",
            "text_label": "补充说明（可选）",
            "text_placeholder": "一般不用填。课件和笔记请用上面上传。",
        }
    if task == "catalog":
        return {
            "upload_label": "老师划重点文本（可选）",
            "text_label": "老师划重点（可选，也可粘贴）",
            "text_placeholder": "课件和笔记不用再传，会从已入库知识库读取。这里只填老师本次划重点。",
        }
    if task == "checklist":
        return {
            "upload_label": "老师本次划重点文本（必填）",
            "text_label": "老师本次划重点（必填，也可粘贴）",
            "text_placeholder": "目录 JSON 不用上传。系统按用户 ID + 学科自动读取已生成目录。这里只填老师本次划重点。",
        }
    return {
        "upload_label": "文本文件",
        "text_label": "文本",
        "text_placeholder": "粘贴会议记录或笔记原文…",
    }


def _upload_incompatible(task: str, upload) -> bool:
    if upload is None or upload == "":
        return False
    paths = _uploaded_paths(upload)
    if task == OCR_TASK:
        return any(path.suffix.lower() not in {".png", ".jpg", ".jpeg"} for path in paths)
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
    ocr_task = task == OCR_TASK
    copy = _input_copy(task)
    kwargs: dict = {
        "label": copy["upload_label"],
        "file_types": (
            [".png", ".jpg", ".jpeg"]
            if ocr_task
            else sorted(_LIBRARY_SUFFIXES) if knowledge_task else [".txt", ".md"]
        ),
        "file_count": "multiple" if knowledge_task else "single",
    }
    if _upload_incompatible(task, current_upload):
        kwargs["value"] = None
    return gr.update(**kwargs)


def _input_text_update(task: str):
    copy = _input_copy(task)
    lines = 2 if task == OCR_TASK else (8 if task in _TEACHER_TEXT_TASKS else (6 if task == "library" else 12))
    return gr.update(
        label=copy["text_label"],
        placeholder=copy["text_placeholder"],
        lines=lines,
        visible=task != OCR_TASK,
    )


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
    user_copy, subject_copy = _scope_labels(task)
    return (
        gr.update(value=_task_brief_html(task)),
        gr.update(visible=show_config),
        gr.update(visible=show_mode),
        gr.update(
            visible=show_perspective,
            choices=perspective_choices or ["客观 · 客观全员"],
            value=perspective_value or "客观 · 客观全员",
        ),
        gr.update(visible=show_user, **user_copy),
        gr.update(visible=show_project),
        gr.update(visible=show_subject, **subject_copy),
        gr.update(visible=show_quiz),
        gr.update(visible=sidecar),
        gr.update(visible=bool(policy and policy.cli_template)),
        _upload_update(task, current_upload),
        _input_text_update(task),
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


def _output_files(domain: str, tasks: list[str], user_id: str = "") -> set[Path]:
    root = _output_root(domain, user_id)
    files: set[Path] = set()
    for task in tasks:
        folder = root / task
        if folder.exists():
            files.update(path.resolve() for path in folder.rglob("*") if path.is_file())
    return files


def _output_root(domain: str, user_id: str = "") -> Path:
    """产物根：有 user 时 ``output/{user_id}/{domain}``，否则旧路径。"""
    if (user_id or "").strip():
        from tools.memory.store import safe_id

        return PROJECT_ROOT / "output" / safe_id(user_id) / domain
    return PROJECT_ROOT / "output" / domain


def _new_artifacts(domain: str, tasks: list[str], before: set[Path], user_id: str = "") -> list[str]:
    after = _output_files(domain, tasks, user_id)
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
    ocr_preview = _ocr_preview_text(files)
    if ocr_preview:
        return ocr_preview
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
    ocr_llm_paths = [
        path for path in paths
        if path.parent.parent.name == "ocr" and path.name.endswith("_llmv2.md")
    ]
    if ocr_llm_paths:
        paths = ocr_llm_paths
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


def _ocr_preview_text(files: list[str]) -> str:
    paths = [Path(file) for file in files or [] if Path(file).is_file()]
    ocr_files = [path for path in paths if path.parent.parent.name == "ocr"]
    if not ocr_files:
        return ""
    by_suffix = {suffix: "" for suffix in ("_ocr.txt", "_llmv2.md")}
    for suffix in list(by_suffix):
        matches = [path for path in ocr_files if path.name.endswith(suffix)]
        if not matches:
            continue
        matches.sort(key=lambda path: (-path.stat().st_mtime, path.name))
        try:
            by_suffix[suffix] = matches[0].read_text(encoding="utf-8").strip()
        except OSError:
            by_suffix[suffix] = ""
    if not any(by_suffix.values()):
        return ""
    sections = [
        ("服务器原始 OCR 文本", by_suffix["_ocr.txt"]),
        ("审校版 Markdown", by_suffix["_llmv2.md"]),
    ]
    return "\n\n---\n\n".join(
        f"## {title}\n\n{body or '（无内容）'}" for title, body in sections
    )


def _gallery_update(files: list[str] | None = None):
    """有 PNG 才展示图库，否则隐藏。"""
    pngs = _png_previews(files or [])
    return gr.update(value=pngs, visible=bool(pngs))


def _has_rich_html(files: list[str] | None) -> bool:
    """右侧已有交互/对照 HTML 时，不再重复摊开 Markdown。"""
    markers = (
        "quiz-sheet",
        "ck-doc",
        "cat-doc",
        "library-hero",
    )
    for file in files or []:
        path = Path(file)
        if not (path.suffix.lower() == ".html" and path.is_file()):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(marker in text for marker in markers):
            return True
    return False


def _md_update(files: list[str] | None = None):
    """有 Markdown 才展示预览，否则隐藏。自测题/清单等以 HTML 为主，不再摊开正文。"""
    if _has_rich_html(files):
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
        if "ck-doc" in doc:
            return (
                '<iframe class="lc-standalone-frame" title="复习清单" '
                f'srcdoc="{html.escape(doc)}"></iframe>'
            )
        match = re.search(r"<main[^>]*>(.*?)</main>", doc, re.S | re.I)
        body = match.group(1).strip() if match else doc.strip()
        if not any(
            marker in body
            for marker in ("memory-review", "quiz-sheet", "cat-doc", "library-hero")
        ):
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
EMPTY_MONITOR = gr.update(value="", visible=False)

_MONITOR_LAYER_NAMES = {
    "core/perspective_modeling": "视角建模",
    "core/meeting_understanding": "会议理解",
    "core/notes_understanding": "笔记理解",
    "template/compile": "模板编译",
    "schema_repair": "结构修复",
}
_MONITOR_ROLE_NAMES = {
    "agent": "生成",
    "supervisor": "审核",
    "render": "排版",
}
_MONITOR_DECISION = {
    "approve": "通过",
    "revise": "返工",
    "reject": "未通过",
}



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
                    # 可读化占位单元格：含「生成时填写」/「约N行」/「填这里」→ 视为未填写的占位行
                    is_placeholder_row = bool(cells) and all(
                        not c
                        or "生成时填写" in c
                        or "填这里" in c
                        or re.match(r"^约\s*\d+\s*行", c)
                        for c in cells
                    )
                    if len(cells) == cols and (not any(cells) or is_placeholder_row):
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
    state_update = gr.update(
        value=json.dumps(state, ensure_ascii=False) if state else ""
    )
    run_btn = gr.update(
        value="确认模板并运行" if show_editor else "运行",
        interactive=True,
    )
    return (friendly, state_update, wrap, run_btn)


def begin_run():
    """点击运行后立即反馈状态，并锁定按钮防止重复请求。"""
    return (
        "正在运行，请稍候…\n结果返回前请勿重复点击。",
        EMPTY_MONITOR,
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
        EMPTY_MONITOR,
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
        EMPTY_MONITOR,
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
        MONITOR_ON,
        *_hitl_ui(False),
    )


def _fmt_int(value: object) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number >= 10000:
        text = f"{number / 10000:.1f}".rstrip("0").rstrip(".")
        return f"{text}万"
    return f"{number:,}"


def _fmt_seconds(value: object) -> str:
    try:
        seconds = float(value or 0)
    except (TypeError, ValueError):
        return "0s"
    if seconds >= 60:
        minutes = int(seconds // 60)
        rest = seconds - minutes * 60
        return f"{minutes}:{rest:04.1f}"
    if seconds >= 10:
        return f"{seconds:.0f}s"
    return f"{seconds:.1f}s"


def _layer_caption(label: str, line_names: dict[str, str]) -> str:
    if label in _MONITOR_LAYER_NAMES:
        return _MONITOR_LAYER_NAMES[label]
    if "/" in (label or ""):
        line, role = label.split("/", 1)
        head = line_names.get(line, line)
        tail = _MONITOR_ROLE_NAMES.get(role, role)
        return f"{head} · {tail}"
    return label or "未分层"


def _monitor_update(html: str):
    text = (html or "").strip()
    return gr.update(value=text, visible=bool(text))


def _latest_monitor(task: str, user_id: str = "") -> dict | None:
    if (user_id or "").strip():
        from tools.memory.store import safe_id

        folder = PROJECT_ROOT / "output" / safe_id(user_id) / "monitor"
    else:
        folder = PROJECT_ROOT / "output" / "monitor"
    if not folder.exists() or not task:
        return None
    files = sorted(
        folder.glob(f"{task}_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not files:
        return None
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _monitor_plain(text: str) -> str:
    return f'<span class="mon-plain">{html.escape(text)}</span>'


def _knowledge_story(kb: dict) -> str:
    parts: list[str] = []
    files = int(kb.get("ingest_files") or 0)
    added = int(kb.get("chunks_added") or 0)
    removed = int(kb.get("chunks_removed") or 0)
    unchanged = int(kb.get("chunks_unchanged") or 0)
    if files or added:
        bit = f"写入了 {files} 份资料，新增 {added} 个知识块"
        extras = []
        if removed:
            extras.append(f"删掉 {removed} 个过时块")
        if unchanged:
            extras.append(f"{unchanged} 个块内容没变")
        if extras:
            bit += "（" + "，".join(extras) + "）"
        parts.append(bit + "。")
    searches = int(kb.get("search_calls") or 0)
    hits = int(kb.get("search_hits") or 0)
    empty = int(kb.get("search_empty") or 0)
    if searches:
        bit = f"检索了 {searches} 次，找到 {hits} 条相关内容"
        if empty:
            bit += f"，其中 {empty} 次没有结果"
        parts.append(bit + "。")
    scans = int(kb.get("scan_chunks") or 0)
    if int(kb.get("scan_calls") or 0):
        parts.append(f"从库里通读了 {scans} 个知识块。")
    cites = int(kb.get("cite_calls") or 0)
    if cites:
        parts.append(f"按原文核对出处 {cites} 次。")
    collection = str(kb.get("collection") or "").strip()
    if collection:
        parts.append(f"当前知识库：{collection}。")
    return "".join(parts)


def _memory_story(mem: dict) -> str:
    bound = int(mem.get("bound") or 0) > 0
    created = int(mem.get("created") or 0) > 0
    unbound = int(mem.get("unbound") or 0) > 0 or int(mem.get("prepare_calls") or 0) > 0
    wrote = int(mem.get("persist_ok") or 0) > 0
    skipped = int(mem.get("persist_skip") or 0) > 0
    inject = int(mem.get("inject_chars") or 0)
    run_n = int(mem.get("run_count") or 0)
    project = str(mem.get("project_id") or "").strip()
    strong = int(mem.get("strong") or 0)
    hits = int(mem.get("hits") or 0)
    embed_calls = int(mem.get("embed_calls") or 0)
    embed_hits = int(mem.get("embed_hits") or 0)
    embed_fail = int(mem.get("embed_fail") or 0)
    if not (bound or unbound or wrote or skipped or embed_calls or embed_hits or embed_fail):
        return ""

    parts: list[str] = []
    if bound:
        who = f"项目「{project}」" if project else "已有项目"
        if created:
            parts.append(f"按新项目建档（{who}）。")
        else:
            parts.append(f"对上了{who}，读入了历史记忆。")
        if inject:
            parts.append(f"注入了 {inject} 字旧内容供对照。")
        elif strong:
            parts.append("这次和历史项目对得比较明确。")
        elif hits:
            parts.append("这次和历史项目只有较弱关联。")
    elif unbound:
        if created and wrote:
            parts.append("开始时还没有可对照的历史项目，所以没读旧记忆。")
        else:
            parts.append("没有对上已有项目，因此没有读入历史记忆。")

    if wrote:
        if run_n <= 1:
            parts.append("结束后已新建档案，这是第 1 次写入。")
        else:
            parts.append(f"结束后已写回档案，这是第 {run_n} 次更新。")
        if project and not bound:
            parts.append(f"新档案编号：{project}。")
    elif skipped:
        parts.append("这次没有把结果写入记忆。")
    if embed_calls or embed_hits or embed_fail:
        bit = f"记忆向量检索 {embed_calls} 次"
        if embed_hits:
            bit += f"，命中 {embed_hits} 条"
        if embed_fail:
            bit += f"，失败 {embed_fail} 次"
        parts.append(bit + "。")
    return "".join(parts)


def _embed_totals(payload: dict) -> tuple[int, int]:
    kb = payload.get("knowledge") or {}
    mem = payload.get("memory") or {}
    calls = int(kb.get("embed_calls") or 0) + int(mem.get("embed_calls") or 0)
    tokens = int(kb.get("embed_tokens") or 0)
    return calls, tokens


def _monitor_io_rows(payload: dict) -> list[str]:
    rows: list[str] = []
    embed_calls, embed_tokens = _embed_totals(payload)
    if embed_calls or embed_tokens:
        text = f"向量模型调用 {embed_calls} 次"
        if embed_tokens:
            text += f"，约 {_fmt_int(embed_tokens)} token，与上方对话 token 分开计算"
        rows.append(f'<div class="mon-io-row"><em>向量</em>{_monitor_plain(text + "。")}</div>')
    kb_text = _knowledge_story(payload.get("knowledge") or {})
    mem_text = _memory_story(payload.get("memory") or {})
    if kb_text:
        rows.append(f'<div class="mon-io-row"><em>知识库</em>{_monitor_plain(kb_text)}</div>')
    if mem_text:
        rows.append(f'<div class="mon-io-row"><em>记忆</em>{_monitor_plain(mem_text)}</div>')
    return rows


def _monitor_html(payload: dict | None, *, line_names: dict[str, str] | None = None) -> str:
    if not payload:
        return ""
    names = line_names or {}
    usage = payload.get("usage") or {}
    layers = payload.get("usage_by_label") or {}
    latency = payload.get("latency_by_label") or {}
    pipeline = payload.get("pipeline") or {}
    quality = payload.get("quality") or {}
    scope = payload.get("scope") or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    calls = int(usage.get("calls") or 0)
    retries = int(payload.get("retries") or 0)
    failures = int(payload.get("failures") or 0)
    cache_hits = int(usage.get("cache_hits") or 0)
    cache_hit_tokens = int(usage.get("cache_hit_tokens") or 0)
    duration = payload.get("duration_seconds") or 0
    ok = bool(payload.get("ok"))
    warning = quality.get("warning")
    fallback = bool(quality.get("fallback"))
    if not ok or payload.get("error"):
        stamp = "失败"
        stamp_kind = "bad"
    elif fallback or warning:
        stamp = "降级"
        stamp_kind = "warn"
    else:
        stamp = "完成"
        stamp_kind = "ok"

    stats = [
        (_fmt_seconds(duration), "耗时"),
    ]
    if total_tokens or calls:
        stats.append((_fmt_int(total_tokens), "对话token"))
        stats.append((str(calls), "对话次"))
    if retries:
        stats.append((str(retries), "重试"))
    if failures:
        stats.append((str(failures), "失败"))
    if cache_hits:
        stats.append((str(cache_hits), "缓存"))
    if cache_hit_tokens:
        stats.append((_fmt_int(cache_hit_tokens), "缓存token"))
    embed_calls, embed_tokens = _embed_totals(payload)
    if embed_tokens:
        stats.append((_fmt_int(embed_tokens), "向量token"))
    elif embed_calls:
        stats.append((str(embed_calls), "向量次"))

    started = str(payload.get("started_at") or "")
    finished = str(payload.get("finished_at") or "")
    clock = ""
    if started and finished and len(started) >= 19 and len(finished) >= 19:
        clock = f"{started[11:19]}–{finished[11:19]}"
    elif started:
        clock = started
    meta_bits = []
    if clock:
        meta_bits.append(clock)
    if scope.get("user_id"):
        meta_bits.append(str(scope["user_id"]))
    if scope.get("subject"):
        meta_bits.append(str(scope["subject"]))

    rows: list[str] = [
        f'<section class="mon-sheet mon-{stamp_kind}">',
        '<div class="mon-head">',
        f'<span class="mon-stamp">{stamp}</span>',
        '<ul class="mon-stats">',
    ]
    for value, label in stats:
        rows.append(
            f'<li><strong>{html.escape(str(value))}</strong><span>{label}</span></li>'
        )
    rows.append("</ul>")
    if pipeline:
        rows.append('<div class="mon-pipe">')
        for line, info in pipeline.items():
            if not isinstance(info, dict):
                continue
            decision = _MONITOR_DECISION.get(str(info.get("decision") or ""), "")
            revisions = int(info.get("revision_count") or 0)
            if info.get("fallback"):
                chip = "改用兜底结果"
            elif decision == "通过":
                chip = "审核通过"
            elif decision == "未通过":
                chip = "审核未通过"
            elif decision == "返工":
                chip = "需要返工"
            else:
                chip = "已完成"
            extra = f"，返工 {revisions} 次" if revisions else ""
            kind = "warn" if info.get("fallback") else "ok" if decision == "通过" else "plain"
            rows.append(
                f'<span class="mon-chip mon-chip-{kind}">'
                f"{html.escape(names.get(str(line), str(line)))}：{chip}{extra}"
                "</span>"
            )
        rows.append("</div>")
    if meta_bits:
        rows.append(f'<p class="mon-meta">{html.escape(" · ".join(meta_bits))}</p>')
    rows.append("</div>")

    if warning:
        rows.append(f'<p class="mon-note">{html.escape(str(warning))}</p>')
    if payload.get("error"):
        rows.append(f'<p class="mon-note mon-error">{html.escape(str(payload["error"]))}</p>')

    io_rows = _monitor_io_rows(payload)
    if io_rows:
        rows.append('<div class="mon-io">')
        rows.extend(io_rows)
        rows.append("</div>")

    if layers:
        ranked = sorted(
            layers.items(),
            key=lambda item: int((item[1] or {}).get("total_tokens") or 0),
            reverse=True,
        )
        many = sum(1 for _, slot in ranked if isinstance(slot, dict)) >= 4
        rows.append(f'<div class="mon-layers{" mon-layers-2" if many else ""}">')
        for label, slot in ranked:
            if not isinstance(slot, dict):
                continue
            tokens = int(slot.get("total_tokens") or 0)
            lat = latency.get(label) or {}
            width = 6 if total_tokens <= 0 else max(6, min(100, round(100 * tokens / total_tokens)))
            time_bit = _fmt_seconds(lat.get("total_seconds") or 0) if lat else ""
            rows.append(
                '<div class="mon-layer">'
                f'<span class="mon-layer-name">{html.escape(_layer_caption(label, names))}</span>'
                f'<span class="mon-track"><i style="width:{width}%"></i></span>'
                f'<em>{_fmt_int(tokens)}{(" · " + time_bit) if time_bit else ""}</em>'
                "</div>"
            )
        rows.append("</div>")
    rows.append("</section>")
    return "\n".join(rows)


def _run_result(
    log,
    files_or_none=None,
    *hitl,
    files_html: str | None = None,
    monitor_html: str = "",
):
    """统一结果区输出：日志 / 图片(可隐藏) / MD预览(可隐藏) / 下载 / 监控 / HITL / 解锁按钮。"""
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
        _monitor_update(monitor_html),
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
    edit_state: str | dict | None,
    readable_template: str | None,
    *preview_args,
    **kwargs,
):
    """run_from_ui：*preview_args 承载模式/用户参数。

    Gradio 按位置传参（不会自动聚合 list），这里手动拆分：
    preview_args = [mode, user_id, project_id, subject, kp_upload, kp_text,
                    notes_upload, notes_text, quiz_difficulty, quiz_qtype,
                    perspective_choice, monitor_enabled]
    """
    # 兼容 gradio 5.49：edit_state 可能是隐藏 Textbox 传来的 JSON 字符串
    if isinstance(edit_state, str) and edit_state.strip():
        try:
            edit_state = json.loads(edit_state)
        except (json.JSONDecodeError, TypeError):
            edit_state = None
    elif not isinstance(edit_state, dict):
        edit_state = None
    mode_value, user_id, project_id, subject = preview_args[:4]
    keypoints_upload, keypoints_text, notes_upload, notes_text = preview_args[4:8]
    quiz_difficulty = preview_args[8] if len(preview_args) > 8 else ""
    quiz_qtype = preview_args[9] if len(preview_args) > 9 else ""
    perspective_choice = preview_args[10] if len(preview_args) > 10 else ""
    raw_monitor = preview_args[11] if len(preview_args) > 11 else MONITOR_ON
    monitor_enabled = str(raw_monitor).strip().lower() not in {
        "",
        "0",
        "off",
        "false",
        "关",
        "no",
        "disable",
        "disabled",
    }
    domain = _domain_value(domain_label)
    if not task_label:
        return _run_result(
            "请选择任务线。",
            None,
            *_hitl_ui(False),
            files_html=EMPTY_DOWNLOAD,
        )

    tasks = [_task_value(task_label, domain)]
    if domain == "notes" and tasks[0] == OCR_TASK:
        uid = (user_id or "").strip()
        subj = (subject or "").strip()
        if not uid or not subj:
            return _run_result(
                "OCR识别请填写用户 ID 和学科。系统会把识别结果保存到该用户的 OCR 文件夹。",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )
        image_path = _uploaded_path(input_upload)
        if image_path is None or not image_path.exists():
            return _run_result(
                "请上传 PNG / JPG / JPEG 图片。",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )
        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            return _run_result(
                "OCR识别暂只支持 PNG / JPG / JPEG 图片。",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )
        try:
            _raw_txt, _no_llm_md, _llm_md, files = _recognize_ocr_image(
                image_path,
                user_id=uid,
                subject=subj,
            )
        except Exception as exc:  # noqa: BLE001
            return _run_result(
                f"OCR识别失败：{exc}",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )
        return _run_result(
            "OCR识别完成。右侧展示服务器原始 OCR 文本和审校版 Markdown。"
            "文件已保存到该用户的 OCR 文件夹。若要进入知识库，请把审校版 Markdown 上传到「资料入库」。",
            files,
            *_hitl_ui(False),
        )
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
    uid = (user_id or "").strip()
    subj = (subject or "").strip()
    if tasks[0] in KNOWLEDGE_SCOPE_LINES and (not uid or not subj):
        return _run_result(
            "请填写用户 ID 和学科。"
            "系统用这两个值定位该用户该学科的知识库"
            + (
                "和已生成的知识目录"
                if tasks[0] in {"catalog", "checklist"}
                else ""
            )
            + "，不用再填 collection，也不用上传目录 JSON。",
            None,
            *_hitl_ui(False),
            files_html=EMPTY_DOWNLOAD,
        )
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
    monitor_html = ""
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
        if input_file is None and tasks[0] != "catalog":
            if tasks[0] == "checklist":
                missing = (
                    "复习清单必须提供老师本次划重点文本：请上传 txt/md，或在文本框里粘贴。"
                    "目录 JSON 不用上传，系统会按用户 ID + 学科自动读取已生成目录。"
                )
            elif tasks[0] == "library":
                missing = "资料入库请上传课件 / 讲义 / 笔记（可多选），或在文本框粘贴补充文本。"
            else:
                missing = "请上传输入文件，或直接在文本框里输入内容。"
            return _run_result(
                missing,
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

        before = _output_files(domain, tasks, user_id)
        buffer = io.StringIO()
        monitor_payload = None
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                modes: dict[str, str] = {}
                _pol = _line_policy(domain, tasks[0])
                if _pol and _pol.cli_mode and mode_value:
                    modes[tasks[0]] = _mode_value(mode_value)
                monitor_payload = asyncio.run(
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
                        monitor=monitor_enabled,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - UI should show the error directly
            monitor_payload = getattr(exc, "monitor_payload", None)
            buffer.write(f"\n运行失败：{exc}\n")

        files = _new_artifacts(domain, tasks, before, user_id)
        log = _clean_log(buffer.getvalue().strip() or "运行完成。")
        if monitor_enabled and not monitor_payload:
            monitor_payload = _latest_monitor("+".join(tasks), user_id)
        monitor_html = (
            _monitor_html(monitor_payload, line_names=ctx.line_cn_names)
            if monitor_enabled
            else ""
        )

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
        monitor_html=monitor_html,
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


def _recognize_ocr_image(
    image_path: Path,
    *,
    user_id: str,
    subject: str,
) -> tuple[str, str, str, list[str]]:
    from tools.ocr import server_ocr_image_recognize
    from tools.memory.store import safe_id

    raw_txt, no_llm_md, llm_md, reviewed_md, review_notes = server_ocr_image_recognize(str(image_path))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out_dir = PROJECT_ROOT / "data" / safe_id(user_id) / "ocr" / safe_id(subject)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", image_path.stem).strip("._") or "image"
    raw_path = out_dir / f"{stem}_{stamp}_ocr.txt"
    review_notes_path = out_dir / f"{stem}_{stamp}_review.md"
    llm_path = out_dir / f"{stem}_{stamp}_llm.md"
    reviewed_path = out_dir / f"{stem}_{stamp}_llmv2.md"
    raw_path.write_text(raw_txt, encoding="utf-8")
    _ = no_llm_md
    llm_path.write_text(llm_md, encoding="utf-8")
    reviewed_path.write_text(reviewed_md, encoding="utf-8")
    review_notes_path.write_text("# OCR 审校说明\n\n" + review_notes.strip(), encoding="utf-8")
    return raw_txt, no_llm_md, reviewed_md, [
        str(raw_path),
        str(review_notes_path),
        str(llm_path),
        str(reviewed_path),
    ]


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
    text = re.sub(r"任务监控完成[^\n]*\n?", "", text)
    return text




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
    user_init, subject_init = _scope_labels(initial_task or "")
    input_init = _input_copy(initial_task or "")
    with gr.Blocks(title="AgentFlow测试", theme=_build_theme(), css=CSS) as demo:
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
            with gr.Row(elem_id="chrome-controls"):
                domain = gr.Radio(
                    choices=DOMAIN_CHOICES,
                    value=initial_domain,
                    show_label=False,
                    container=False,
                    elem_id="domain-switch",
                )
                monitor_checkbox = gr.Radio(
                    choices=MONITOR_CHOICES,
                    value=MONITOR_ON,
                    show_label=False,
                    container=False,
                    elem_id="monitor-switch",
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
                    label=user_init["label"],
                    lines=1,
                    max_lines=1,
                    placeholder=user_init["placeholder"],
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
                    label=subject_init["label"],
                    lines=1,
                    max_lines=1,
                    placeholder=subject_init["placeholder"],
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
                        file_types=[".txt", ".md"],
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
                        file_types=[".txt", ".md"],
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
                    label=input_init["upload_label"],
                    file_count="single",
                    file_types=[".txt", ".md"],
                    type="filepath",
                )
                input_text = gr.Textbox(
                    label=input_init["text_label"],
                    lines=12,
                    max_lines=40,
                    elem_id="input-text",
                    placeholder=input_init["text_placeholder"],
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
                        # 隐藏状态：保存原始占位模板（gradio 5.49 对 gr.State 的 gr.update 不生效，改用隐藏 Textbox 承载 JSON 状态）
                        edit_state = gr.Textbox(value="", visible=False, elem_id="edit-state")
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
                html_monitor_kwargs = {
                    "value": "",
                    "elem_id": "monitor-panel",
                    "visible": False,
                }
                try:
                    monitor_panel = gr.HTML(**html_monitor_kwargs, sanitize_html=False)
                except TypeError:
                    try:
                        monitor_panel = gr.HTML(**html_monitor_kwargs, sanitize=False)
                    except TypeError:
                        monitor_panel = gr.HTML(**html_monitor_kwargs)
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
            monitor_panel,
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
                input_text,
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
                input_text,
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
            outputs=[log_output, monitor_panel, run_button, *side_btns],
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
                monitor_checkbox,
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
                monitor_checkbox,
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


def main(host: str | None = None, port: int | None = None) -> None:
    """启动 Gradio 服务。host/port 由调用方（gradio_app.py）传入，
    未传时回退环境变量 GRADIO_SERVER_NAME / GRADIO_SERVER_PORT。"""
    build_app().launch(
        server_name=host or os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=port or _env_int("GRADIO_SERVER_PORT", 7860),
        share=_env_bool("GRADIO_SHARE", False),
    )


if __name__ == "__main__":
    main()
