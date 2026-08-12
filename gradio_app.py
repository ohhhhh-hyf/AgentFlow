from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import io
import os
import sys
import re
import tempfile
from pathlib import Path

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.runtime_context import load_domain  # noqa: E402
from tools.runner import run  # noqa: E402
from tools.template_router import (  # noqa: E402
    LINE_SCHEMA_HINTS,
    detect_template_kind,
    maybe_compile_natural_template,
)


DOMAIN_NAMES = ["meeting", "notes"]
DOMAIN_LABELS = {
    "meeting": "meeting - 会议",
    "notes": "notes - 笔记",
}
DOMAIN_CHOICES = [(DOMAIN_LABELS[name], name) for name in DOMAIN_NAMES]


def _ctx(domain: str):
    return load_domain(domain, PROJECT_ROOT)


def _task_choices(domain: str) -> list[str]:
    ctx = _ctx(domain)
    return [
        f"{line} - {ctx.line_cn_names.get(line, line)}"
        for line in ctx.task_lines
    ]


def _task_value(label: str) -> str:
    for separator in (" 路 ", " · ", " - "):
        if separator in label:
            return label.split(separator, 1)[0].strip()
    return label.strip()


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


def update_domain(domain_label: str):
    domain = _domain_value(domain_label)
    choices = _task_choices(domain)
    selected_task = choices[0] if choices else None
    return gr.update(choices=choices, value=selected_task)


def _domain_value(value: str) -> str:
    if value in DOMAIN_NAMES:
        return value
    return _task_value(value)


EMPTY_DOWNLOAD = '<p class="dl-empty">暂无生成文件</p>'
EMPTY_MD = gr.update(value="", visible=False)
EMPTY_GALLERY = gr.update(value=[], visible=False)


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
        EMPTY_MD,
        EMPTY_DOWNLOAD,
    )


def reset_form():
    """清空输入、模板与结果，保留领域/任务，相当于不刷新的软重置。"""
    return (
        "已重置表单（领域/任务保留）。可重新上传或粘贴内容后再运行；无需刷新浏览器。",
        EMPTY_GALLERY,
        EMPTY_MD,
        EMPTY_DOWNLOAD,
        gr.update(value=None),  # input_upload
        "",  # input_text
        gr.update(value=None),  # template_upload
        "",  # template_text
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
    profile_path = PROJECT_ROOT / "samples" / domain / "profile" / "object_profile.json"
    if not profile_path.exists():
        return _run_result(
            f"默认 profile 不存在：{profile_path}",
            None,
            *_hitl_ui(False),
            files_html=EMPTY_DOWNLOAD,
        )

    ctx = _ctx(domain)
    files: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentflow_gradio_") as temp_dir:
        temp_root = Path(temp_dir)
        input_file = _input_path(input_upload, input_text, temp_root, "input.txt")
        if input_file is None:
            return _run_result(
                "请上传输入文件，或直接在文本框里输入内容。",
                None,
                *_hitl_ui(False),
                files_html=EMPTY_DOWNLOAD,
            )

        # 须在自然语言模板编译之前加载 .env，否则 LLMClient 读不到 API Key
        load_env(PROJECT_ROOT / ".env")

        # ── 模板处理（Human-in-the-loop）────────────────────────────────
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
                asyncio.run(
                    run(
                        ctx,
                        input_file,
                        profile_path,
                        PROJECT_ROOT / ".env",
                        templates,
                        tasks,
                    )
                )
        except Exception as exc:  # noqa: BLE001 - UI should show the error directly
            buffer.write(f"\n运行失败：{exc}\n")

        files = _new_artifacts(domain, tasks, before)
        log = _clean_log(buffer.getvalue().strip() or "运行完成。")

    if files:
        log = (
            f"{log}\n\n已生成 {len(files)} 个文件，可在右侧预览 Markdown 或下载。\n"
            "再测：改输入后直接再点「运行」即可（无需刷新）；"
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
  margin: 0 0 8px;
  padding: 0 0 8px;
  border-bottom: 1px solid #d4d0c6;
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
/* 下拉选中值与任务选项同字号 */
.gradio-container .wrap .single-select,
.gradio-container [class*="secondary-wrap"] span,
.gradio-container .dropdown-arrow + div,
.gradio-container input[type="text"] {
  font-size: 0.95rem !important;
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
    with gr.Blocks(title="小艺慧记Agent测试") as demo:
        gr.HTML(
            """
            <header id="app-header">
              <div class="brand">
                <h1>小艺慧记Agent测试</h1>
              </div>
            </header>
            """
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
                domain = gr.Dropdown(
                    label="领域",
                    choices=DOMAIN_CHOICES,
                    value=initial_domain,
                )
                tasks = gr.Radio(
                    label="任务",
                    choices=initial_choices,
                    value=initial_choices[0] if initial_choices else None,
                )
                gr.HTML('<div class="panel-label spaced">输入</div>')
                input_upload = gr.File(
                    label="文本文件",
                    file_count="single",
                    file_types=[".txt"],
                    type="filepath",
                    # 不用固定 height，避免文案被裁切；高度由 CSS min-height 控制
                )
                input_text = gr.Textbox(
                    label="文本",
                    lines=12,
                    max_lines=40,
                    elem_id="input-text",
                    placeholder="粘贴会议记录或笔记原文…",
                )
                gr.HTML('<div class="panel-label spaced">模板（可选）</div>')
                gr.HTML(
                    '<div class="tpl-guide">'
                    "支持用自然语言描述模板（如「分三段：纪要约200字；待办表；风险表」），"
                    "点「运行」后自动生成可编辑模板，可直接修改后再确认生成结果；"
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

        domain.change(
            update_domain,
            inputs=domain,
            outputs=tasks,
        )
        hitl_outputs = [compiled_template, compiled_wrap, run_button]
        result_outputs = [log_output, image_output, md_preview, files_output]
        side_btns = [clear_results_btn, reset_form_btn, clear_tpl_btn]
        # 先锁按钮并写入「运行中」状态，再执行任务，避免重复请求
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


if __name__ == "__main__":
    build_app().launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=_env_int("GRADIO_SERVER_PORT", 7860),
        share=_env_bool("GRADIO_SHARE", False),
        theme=gr.themes.Base(
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
        ),
        css=CSS,
    )
