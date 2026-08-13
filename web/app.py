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
from pathlib import Path
from typing import Any

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.runtime_context import load_domain  # noqa: E402
from tools.runner import run  # noqa: E402
from tools.memory.citations import memory_review_html as render_memory_review_html  # noqa: E402
from tools.template_router import (  # noqa: E402
    LINE_SCHEMA_HINTS,
    detect_template_kind,
    maybe_compile_natural_template,
)


DOMAIN_NAMES = ["meeting", "notes"]
DOMAIN_LABELS = {
    "meeting": "会议",
    "notes": "笔记",
}
DOMAIN_CHOICES = [(DOMAIN_LABELS[name], name) for name in DOMAIN_NAMES]
DOMAIN_BY_LABEL = {label: name for name, label in DOMAIN_LABELS.items()}

# 视角模式：默认客观全员；可切换个人视角做多视角裁剪
PERSPECTIVE_PERSONAL = "personal"
PERSPECTIVE_OBJECTIVE = "objective"
PERSPECTIVE_CHOICES = [
    ("客观全员（不绑定个人）", PERSPECTIVE_OBJECTIVE),
    ("个人视角（按用户画像裁剪）", PERSPECTIVE_PERSONAL),
]


def _ctx(domain: str):
    return load_domain(domain, PROJECT_ROOT)


def _task_choices(domain: str) -> list[str]:
    ctx = _ctx(domain)
    ordered: list[str] = []
    for line in ctx.line_cn_names:
        if line in ctx.task_lines:
            ordered.append(line)
    for line in ctx.task_lines:
        if line not in ordered:
            ordered.append(line)
    return [
        f"{line} - {ctx.line_cn_names.get(line, line)}"
        for line in ordered
    ]


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


def _task_value(label: str) -> str:
    for separator in (" 路 ", " · ", " - "):
        if separator in label:
            return label.split(separator, 1)[0].strip()
    return label.strip()


def _mode_value(label: str) -> str:
    """从「time - 时间顺序」这类下拉标签提取模式名。"""
    for separator in (" - ", " -", "-"):
        if separator in label:
            return label.split(separator, 1)[0].strip()
    return label.strip()


def _profile_sample_path(domain: str, mode: str) -> Path:
    name = (
        "object_profile.json"
        if mode == PERSPECTIVE_OBJECTIVE
        else "personal_profile.json"
    )
    return PROJECT_ROOT / "samples" / domain / "profile" / name


def _load_profile_json_text(domain: str, mode: str) -> str:
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


def _parse_profile_payload(
    mode: str,
    profile_upload,
    profile_json: str | None,
) -> dict[str, Any]:
    """解析画像：上传 JSON > 文本框 JSON；并与所选视角模式对齐。"""
    raw = ""
    uploaded = _uploaded_path(profile_upload)
    if uploaded is not None and uploaded.exists():
        raw = uploaded.read_text(encoding="utf-8").strip()
    if not raw:
        raw = (profile_json or "").strip()
    if not raw:
        raise ValueError("请填写或上传用户画像 JSON（个人视角为核心能力，不可为空）。")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"用户画像不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("用户画像 JSON 必须是对象（dict）。")

    if mode == PERSPECTIVE_OBJECTIVE:
        data["perspective"] = "objective"
    else:
        # 个人视角：禁止误带 objective
        if str(data.get("perspective") or "").strip().lower() == "objective":
            data["perspective"] = "personal"
        elif not data.get("perspective"):
            data["perspective"] = "personal"
        name = str(data.get("name") or "").strip()
        role = str(data.get("role") or "").strip()
        if not name and not role:
            raise ValueError(
                "个人视角需在画像中填写 name 或 role，否则无法做多视角裁剪。"
            )
    return data


def _panel_updates(domain: str, task_label: str | None):
    task = _task_value(task_label or "")
    return (
        gr.update(visible=task == "multi_styles"),
        gr.update(visible=domain == "meeting"),
        gr.update(visible=domain == "notes"),
        gr.update(visible=task == "minutes_trace"),
        gr.update(visible=task != "minutes_trace"),
    )


def update_domain(domain_label: str):
    domain = _domain_value(domain_label)
    choices = _task_choices(domain)
    selected = choices[0] if choices else None
    return (
        gr.update(choices=choices, value=selected),
        *_panel_updates(domain, selected),
        *_hitl_ui(False),
    )


def update_task_panel(domain_label: str, task_label: str | None):
    return (
        *_panel_updates(_domain_value(domain_label), task_label),
        *_hitl_ui(False),
    )


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
    for file in files or []:
        path = Path(file)
        if path.suffix.lower() != ".md":
            continue
        if "_rejected" in path.name:
            continue
        if not path.is_file():
            continue
        paths.append(path)
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
        title = _clean_filename(path.name)
        parts.append(f"**{html.escape(title)}**\n\n{body}")
    return "\n\n---\n\n".join(parts)


def _gallery_update(files: list[str] | None = None):
    """有 PNG 才展示图库，否则隐藏。"""
    pngs = _png_previews(files or [])
    return gr.update(value=pngs, visible=bool(pngs))


def _md_update(files: list[str] | None = None):
    """有 Markdown 才展示预览，否则隐藏。"""
    text = _md_preview_text(files or [])
    return gr.update(value=text, visible=bool(text))


def _parse_memory_sources(text: str) -> dict[str, str]:
    if "## 历史记忆引用" not in text:
        return {}
    appendix = text.split("## 历史记忆引用", 1)[1]
    blocks = re.split(r'\n<a id="([^"]+)"></a>\n', appendix)
    out: dict[str, str] = {}
    for i in range(1, len(blocks), 2):
        ref_id = blocks[i]
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        lines = [line.strip() for line in body.strip().splitlines() if line.strip()]
        if not lines:
            continue
        title = re.sub(r"^\*\*来自：|\*\*$", "", lines[0]).strip()
        meta = lines[1] if len(lines) > 1 else ""
        quote = ""
        for line in lines[2:]:
            if line.startswith(">"):
                quote = line.lstrip("> ").strip()
                break
        card = (
            f'<div class="mem-card-title">{html.escape(title)}</div>'
            f'<div class="mem-card-meta">{html.escape(meta)}</div>'
        )
        if quote:
            card += f'<div class="mem-card-quote">{html.escape(quote)}</div>'
        out[ref_id] = card
    return out


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
        return body if "memory-review" in body else ""
    text = _md_preview_text(files)
    if not text or 'class="memory-link"' not in text:
        return ""
    return render_memory_review_html(text)


def _memory_review_update(files: list[str] | None = None):
    body = _memory_review_html(files or [])
    return gr.update(value=body, visible=bool(body))


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
    if not files:
        return '<p class="dl-empty">暂无生成文件</p>'
    rows = ['<ul class="dl-list">']
    for file in files:
        path = Path(file)
        try:
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            continue
        clean_name = _clean_filename(path.name)
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


def _hitl_ui(show_editor: bool, editor_value: str = ""):
    """可编辑模板区（Group）+ 运行按钮文案 的联动状态。"""
    compiled = gr.update(value=editor_value if show_editor else "")
    wrap = gr.update(visible=show_editor)
    run_btn = gr.update(
        value="确认模板并运行" if show_editor else "运行",
        interactive=True,
    )
    return compiled, wrap, run_btn


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
    """清除可编辑模板，回到第一步（可重新从自然语言编译）。"""
    return (
        "已清除可编辑模板。若上方仍是自然语言描述，下次点击「运行」会重新编译。",
        *_hitl_ui(False),
    )


def clear_results_only():
    """只清空右侧结果展示，保留左侧配置与输入，方便同一设置再测。"""
    return (
        "已清空结果区。左侧配置与输入仍保留，改完后直接再点「运行」即可，无需刷新页面。",
        EMPTY_GALLERY,
        EMPTY_REVIEW,
        EMPTY_MD,
        EMPTY_DOWNLOAD,
    )


def reset_form():
    """清空输入、模板与结果，保留领域和任务。"""
    return (
        "已重置表单（领域/任务保留）。视角固定为客观全员，无需填写画像。",
        EMPTY_GALLERY,
        EMPTY_REVIEW,
        EMPTY_MD,
        EMPTY_DOWNLOAD,
        gr.update(value=None),
        "",
        gr.update(value=None),
        "",
        DEFAULT_MULTI_STYLE_MODE,
        "",
        "",
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
        _md_update(files),
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
    compiled_template: str | None,
    mode_value: str | None,
    user_id: str | None,
    project_id: str | None,
    subject: str | None,
    keypoints_upload,
    keypoints_text: str | None,
    notes_upload,
    notes_text: str | None,
):
    domain = _domain_value(domain_label)
    if not task_label:
        return _run_result(
            "请选择任务线。",
            None,
            *_hitl_ui(False),
            files_html=EMPTY_DOWNLOAD,
        )

    tasks = [_task_value(task_label)]
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
            trace=tasks[0] == "minutes_trace",
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
        if tasks[0] != "minutes_trace":
            # ── 模板处理（Human-in-the-loop）────────────────────────────
            # 1) 自然语言：先编译成易读模板 → 展示给人改 → 本次不跑任务
            # 2) 人已改编译框 / 直接给了占位符或格式模板：用该模板真正运行
            template_source = ""
            if template_upload is not None:
                uploaded = _uploaded_path(template_upload)
                if uploaded is not None and uploaded.exists():
                    template_source = uploaded.read_text(encoding="utf-8").strip()
            if not template_source:
                template_source = (template_text or "").strip()

            confirmed = (compiled_template or "").strip()
            editor_value = confirmed  # 运行后仍回填编辑框，避免 HITL 状态丢失
            show_editor = bool(confirmed)

            # 情况 A：下方「可编辑模板」已有内容 → 用户已确认/修改，真正跑任务
            if confirmed:
                final_template = confirmed
                show_editor = True
                editor_value = confirmed
            # 情况 B：源模板是自然语言 → 只编译展示，不跑任务
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
                        "未能编译为可编辑模板。请写得更具体一些，例如：\n"
                        "「约400字；第一行标题；纪要约200字；风险表约3行；待办表约3行」\n"
                        "也可直接粘贴带 [占位符] 的 Markdown 模板后再运行。",
                        None,
                        *_hitl_ui(False),
                        files_html=EMPTY_DOWNLOAD,
                    )
                return _run_result(
                    "【第 1 步完成】自然语言已编译为可编辑模板（见左侧灰框）。\n"
                    "请检查/修改固定文字与 [占位符] 说明，满意后点击「确认模板并运行」。\n"
                    "本次只完成编译，尚未生成结果。",
                    None,
                    *_hitl_ui(True, compiled),
                    files_html=EMPTY_DOWNLOAD,
                )
            # 情况 C：占位符 / 格式规范 / 空模板 → 直接运行
            else:
                final_template = template_source
                # 占位符模板也放进编辑框，方便下一轮微调
                if final_template and detect_template_kind(final_template) == "placeholder":
                    show_editor = True
                    editor_value = final_template

        templates: dict[str, Path] = {}
        if final_template:
            template_file = temp_root / "template.md"
            template_file.write_text(final_template, encoding="utf-8")
            templates[tasks[0]] = template_file

        before = _output_files(domain, tasks)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                # 组织模式：仅 multi_styles（多样式纪要）线消费
                modes: dict[str, str] = {}
                if tasks[0] == "multi_styles" and mode_value:
                    modes["multi_styles"] = _mode_value(mode_value)
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
                    )
                )
        except Exception as exc:  # noqa: BLE001 - UI should show the error directly
            buffer.write(f"\n运行失败：{exc}\n")

        files = _new_artifacts(domain, tasks, before)
        log = _clean_log(buffer.getvalue().strip() or "运行完成。")

    log = f"【视角】客观全员（前端不展示画像）\n{log}"
    if files:
        log = (
            f"{log}\n\n已生成 {len(files)} 个文件，可在右侧预览或下载。\n"
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


def _uploaded_path(upload) -> Path | None:
    if upload is None:
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
    keypoints_upload=None,
    keypoints_text: str | None = None,
    notes_upload=None,
    notes_text: str | None = None,
) -> Path | None:
    """普通任务写单文件；溯源纪要把关键点/笔记放到同一目录。"""
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
  max-width: min(1480px, 96vw) !important;
  width: 100% !important;
  margin: 0 auto !important;
  padding: 10px 16px 20px !important;
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
/* 顶栏 */
#app-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px 24px;
  margin: 0;
  padding: 0 0 6px;
  border-bottom: none;
  text-align: center;
}
#app-header .brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 100%;
}
#app-header h1 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 650;
  letter-spacing: 0.02em;
  color: #1c1b19;
  line-height: 1.2;
  text-align: center;
  width: 100%;
}
/* 领域：浏览器式标签，不占配置栏 */
#domain-tabs {
  margin: 0 0 8px !important;
  padding: 0 !important;
}
#domain-tabs .label-wrap,
#domain-tabs > label,
#domain-tabs span[data-testid="block-info"] {
  display: none !important;
}
#domain-tabs .form,
#domain-tabs .wrap,
#domain-tabs .wrap-inner {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}
#domain-tabs .wrap,
#domain-tabs .form,
#domain-tabs fieldset,
#domain-tabs [class*="radio"] {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: flex-end !important;
  gap: 0 !important;
  border: none !important;
  border-bottom: 1px solid #d4d0c6 !important;
  padding: 0 2px !important;
  background: transparent !important;
}
#domain-tabs label,
#domain-tabs label:has(input[type="radio"]) {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-width: 88px !important;
  margin: 0 4px 0 0 !important;
  padding: 8px 20px 9px !important;
  border: 1px solid #d4d0c6 !important;
  border-bottom: none !important;
  border-radius: 8px 8px 0 0 !important;
  background: #e8e4db !important;
  color: #6b6860 !important;
  font-size: 0.92rem !important;
  font-weight: 550 !important;
  letter-spacing: 0.04em !important;
  box-shadow: none !important;
  cursor: pointer !important;
  position: relative !important;
  top: 1px !important;
}
#domain-tabs label:has(input[type="radio"]:checked) {
  background: #faf9f6 !important;
  color: #1c1b19 !important;
  font-weight: 650 !important;
  z-index: 1 !important;
}
#domain-tabs input[type="radio"] {
  position: absolute !important;
  opacity: 0 !important;
  width: 0 !important;
  height: 0 !important;
  pointer-events: none !important;
}
/* 顶栏操作：左右各一，按钮同宽对齐，说明在下 */
#top-actions {
  gap: 12px !important;
  margin: 0 0 6px !important;
  align-items: stretch !important;
  justify-content: space-between !important;
  width: 100% !important;
}
#top-actions > div {
  flex: 1 1 0 !important;
  min-width: 0 !important;
  max-width: none !important;
}
#top-actions .action-cell {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: flex-start !important;
  gap: 4px !important;
  width: 100% !important;
  text-align: center !important;
}
#top-actions .action-cell .block,
#top-actions .action-cell button {
  width: 100% !important;
  max-width: 180px !important;
  margin-left: auto !important;
  margin-right: auto !important;
}
#clear-results-btn,
#reset-form-btn {
  min-height: 32px !important;
  width: 100% !important;
  max-width: 180px !important;
  border-radius: 6px !important;
  font-weight: 550 !important;
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
.gradio-container .secondary-wrap *,
#domain-select,
#domain-select *,
#domain-select span,
#domain-select input {
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
"""


def build_app() -> gr.Blocks:
    initial_domain = "meeting"
    initial_choices = _task_choices(initial_domain)
    theme = gr.themes.Base(
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
    with gr.Blocks(title="小艺慧记Agent测试", theme=theme, css=CSS) as demo:
        gr.HTML(
            """
            <header id="app-header">
              <div class="brand">
                <h1>小艺慧记Agent测试</h1>
              </div>
            </header>
            """
        )
        domain = gr.Radio(
            choices=DOMAIN_CHOICES,
            value=initial_domain,
            show_label=False,
            container=False,
            elem_id="domain-tabs",
        )
        with gr.Row(elem_id="top-actions", equal_height=True):
            with gr.Column(scale=1, elem_classes=["action-cell"]):
                clear_results_btn = gr.Button(
                    "清空当前结果",
                    variant="secondary",
                    elem_id="clear-results-btn",
                )
            with gr.Column(scale=1, elem_classes=["action-cell"]):
                reset_form_btn = gr.Button(
                    "重置表单",
                    variant="secondary",
                    elem_id="reset-form-btn",
                )
        with gr.Row(elem_id="work-row", equal_height=False):
            with gr.Column(scale=5, min_width=380, elem_id="col-input"):
                gr.HTML('<div class="panel-label">配置</div>')
                tasks = gr.Radio(
                    label="任务",
                    choices=initial_choices,
                    value=initial_choices[0] if initial_choices else None,
                )
                mode_dropdown = gr.Dropdown(
                    label="组织模式",
                    choices=MULTI_STYLE_MODE_CHOICES,
                    value=DEFAULT_MULTI_STYLE_MODE,
                    visible=False,
                    elem_id="mode-select",
                )
                user_id = gr.Textbox(
                    label="用户 ID（可选，开启记忆）",
                    lines=1,
                    max_lines=1,
                    placeholder="同一用户多次运行可对照历史",
                )
                project_id = gr.Textbox(
                    label="项目 ID（可选，会议记忆）",
                    lines=1,
                    max_lines=1,
                    placeholder="会议域：写入并绑定该项目",
                    visible=True,
                )
                subject = gr.Textbox(
                    label="学科（可选，笔记记忆）",
                    lines=1,
                    max_lines=1,
                    placeholder="笔记域：同一用户 + 学科增量合并图谱",
                    visible=False,
                )
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
                        "给最终输出套一层版式。支持自然语言描述"
                        "（如「分三段：纪要约200字；待办表；风险表」），"
                        "点「运行」后生成可编辑模板，改完再确认；"
                        "也可上传或粘贴现成模板。"
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
                                "示例：分三段：纪要约200字；待办表；风险表"
                            ),
                        )
                    with gr.Group(visible=False, elem_id="compiled-wrap") as compiled_wrap:
                        gr.HTML(
                            '<p class="step-banner">'
                            "<strong>可编辑模板</strong>　可改；确认后运行；清除后可重编。"
                            "</p>"
                        )
                        compiled_template = gr.Textbox(
                            label="可编辑模板",
                            lines=10,
                            max_lines=40,
                            elem_id="compiled-tpl",
                            placeholder="编译结果出现在这里，可直接编辑。",
                            show_label=True,
                        )
                        clear_tpl_btn = gr.Button(
                            "清除可编辑模板",
                            variant="secondary",
                            elem_id="clear-tpl-btn",
                            size="sm",
                        )
                run_button = gr.Button("运行", variant="primary", elem_id="run-btn")

            with gr.Column(scale=7, min_width=380, elem_id="col-output"):
                gr.HTML('<div class="panel-label">结果</div>')
                log_output = gr.Textbox(
                    label="日志",
                    lines=12,
                    max_lines=40,
                    elem_id="log-box",
                )
                md_preview = gr.Markdown(
                    value="",
                    label="Markdown 预览",
                    elem_id="md-preview",
                    visible=False,
                )
                memory_review = gr.HTML(
                    value="",
                    label="历史会议批注",
                    elem_id="memory-review",
                    visible=False,
                )
                image_output = gr.Gallery(
                    label="图片",
                    columns=2,
                    height=200,
                    visible=False,
                    elem_id="img-gallery",
                )
                files_output = gr.HTML(
                    label="文件",
                    value=EMPTY_DOWNLOAD,
                )

        hitl_outputs = [compiled_template, compiled_wrap, run_button]
        result_outputs = [log_output, image_output, memory_review, md_preview, files_output]
        side_btns = [clear_results_btn, reset_form_btn, clear_tpl_btn]
        domain.change(
            update_domain,
            inputs=domain,
            outputs=[
                tasks,
                mode_dropdown,
                project_id,
                subject,
                trace_box,
                template_wrap,
                *hitl_outputs,
            ],
        )
        tasks.change(
            update_task_panel,
            inputs=[domain, tasks],
            outputs=[
                mode_dropdown,
                project_id,
                subject,
                trace_box,
                template_wrap,
                *hitl_outputs,
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
                compiled_template,
                mode_dropdown,
                user_id,
                project_id,
                subject,
                keypoints_upload,
                keypoints_text,
                notes_upload,
                notes_text,
            ],
            outputs=[*result_outputs, *hitl_outputs, *side_btns],
            show_progress="minimal",
        )
        clear_tpl_btn.click(
            clear_compiled_template,
            inputs=[],
            outputs=[log_output, *hitl_outputs],
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
                user_id,
                project_id,
                subject,
                keypoints_upload,
                keypoints_text,
                notes_upload,
                notes_text,
                *hitl_outputs,
            ],
        )
    return demo


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
    )


if __name__ == "__main__":
    main()
