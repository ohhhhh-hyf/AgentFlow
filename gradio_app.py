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


def _hitl_ui(show_editor: bool, editor_value: str = ""):
    """可编辑模板区（Group）+ 运行按钮文案 的联动状态。"""
    compiled = gr.update(value=editor_value if show_editor else "")
    wrap = gr.update(visible=show_editor)
    run_btn = gr.update(
        value="确认模板并运行" if show_editor else "运行",
    )
    return compiled, wrap, run_btn


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
        [],
        EMPTY_DOWNLOAD,
    )


def reset_form():
    """清空输入、模板与结果，保留领域/任务，相当于不刷新的软重置。"""
    return (
        "已重置表单（领域/任务保留）。可重新上传或粘贴内容后再运行；无需刷新浏览器。",
        [],
        EMPTY_DOWNLOAD,
        gr.update(value=None),  # input_upload
        "",  # input_text
        gr.update(value=None),  # template_upload
        "",  # template_text
        *_hitl_ui(False),
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
        return (
            "请选择任务线。",
            [],
            EMPTY_DOWNLOAD,
            *_hitl_ui(False),
        )

    tasks = [_task_value(task_label)]
    profile_path = PROJECT_ROOT / "samples" / domain / "profile" / "object_profile.json"
    if not profile_path.exists():
        return (
            f"默认 profile 不存在：{profile_path}",
            [],
            EMPTY_DOWNLOAD,
            *_hitl_ui(False),
        )

    ctx = _ctx(domain)
    with tempfile.TemporaryDirectory(prefix="agentflow_gradio_") as temp_dir:
        temp_root = Path(temp_dir)
        input_file = _input_path(input_upload, input_text, temp_root, "input.txt")
        if input_file is None:
            return (
                "请上传输入文件，或直接在文本框里输入内容。",
                [],
                EMPTY_DOWNLOAD,
                *_hitl_ui(False),
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
                return (
                    f"自然语言模板编译失败：{exc}\n请检查 .env 中的 API Key 后重试。",
                    [],
                    EMPTY_DOWNLOAD,
                    *_hitl_ui(False),
                )
            if (
                not compiled
                or compiled == template_source
                or detect_template_kind(compiled) != "placeholder"
            ):
                return (
                    "未能编译为可编辑模板。请写得更具体一些，例如：\n"
                    "「约400字；第一行标题；纪要约200字；风险表约3行；待办表约3行」\n"
                    "也可直接粘贴带 [占位符] 的 Markdown 模板后再运行。",
                    [],
                    EMPTY_DOWNLOAD,
                    *_hitl_ui(False),
                )
            return (
                "【第 1 步完成】自然语言已编译为可编辑模板（见左侧灰框）。\n"
                "请检查/修改固定文字与 [占位符] 说明，满意后点击「确认模板并运行」。\n"
                "本次只完成编译，尚未生成结果。",
                [],
                EMPTY_DOWNLOAD,
                *_hitl_ui(True, compiled),
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
            f"{log}\n\n已生成 {len(files)} 个文件，可在右侧查看或下载。\n"
            "再测：改输入后直接再点「运行」即可（无需刷新）；"
            "右侧会换成新结果。仅想清屏可用「清空结果」，从头填表用「重置表单」。"
        )
    if show_editor and editor_value:
        log = (
            f"{log}\n\n"
            "本次结果按「可编辑模板」生成。"
            "可继续改模板后再次「确认模板并运行」；点「清除可编辑模板」才会重新从自然语言编译。"
        )
    return (
        log,
        _png_previews(files),
        _artifact_download_html(files),
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
/* 纸面工作台：中性灰、细线框、无渐变/大阴影 */
:root, .dark, .gradio-container {
  --body-background-fill: #f4f4f2 !important;
  --body-text-color: #1a1a1a !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #d8d8d4 !important;
  --block-label-background-fill: transparent !important;
  --block-label-text-color: #3a3a38 !important;
  --block-title-text-color: #1a1a1a !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #cfcfc9 !important;
  --input-placeholder-color: #8a8a84 !important;
  --border-color-primary: #d8d8d4 !important;
  --button-primary-background-fill: #2a2a28 !important;
  --button-primary-background-fill-hover: #1a1a1a !important;
  --button-primary-text-color: #fafaf9 !important;
  --button-secondary-background-fill: #ececea !important;
  --button-secondary-text-color: #1a1a1a !important;
  --neutral-950: #1a1a1a !important;
  --neutral-900: #2a2a28 !important;
  --neutral-800: #3a3a38 !important;
  --neutral-700: #5c5c58 !important;
  --neutral-600: #8a8a84 !important;
  --neutral-200: #d8d8d4 !important;
  --neutral-100: #ececea !important;
  --neutral-50: #f4f4f2 !important;
  --primary-500: #2a2a28 !important;
  --primary-600: #1a1a1a !important;
  --table-odd-background-fill: #e6e6e0 !important;
  --table-even-background-fill: #f0f0ea !important;
  --link-text-color: #1a1a1a !important;
  --link-text-color-hover: #000000 !important;
  --link-text-color-visited: #2a2a28 !important;
  --link-text-color-active: #000000 !important;
  --body-text-color-subdued: #5c5c58 !important;
}
html, body {
  background: #f4f4f2 !important;
  overflow-x: hidden !important;
}
.gradio-container {
  max-width: 1120px !important;
  margin: 0 auto !important;
  padding: 28px 20px 48px !important;
  color: #1a1a1a !important;
  font-family: "IBM Plex Sans", "Source Han Sans SC", "Noto Sans SC",
    "PingFang SC", "Microsoft YaHei", sans-serif !important;
  overflow-x: hidden !important;
}
/* 防止 flex 子项撑出横向滚动 */
#work-row, #col-input, #col-output,
#col-input > *, #col-output > *,
#tpl-box, #tpl-box * {
  min-width: 0 !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
}
/* 顶栏 */
#app-header {
  margin: 0 0 28px;
  padding: 0 0 18px;
  border-bottom: 1px solid #d0d0ca;
}
#app-header h1 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #1a1a1a;
  line-height: 1.3;
}
#app-header p {
  margin: 6px 0 0;
  font-size: 0.875rem;
  color: #5c5c58;
  line-height: 1.5;
  max-width: 36em;
}
/* 栏位 */
#work-row {
  gap: 20px !important;
  align-items: stretch !important;
}
#col-input, #col-output {
  border: 1px solid #d0d0ca;
  background: #fafaf9;
  border-radius: 2px;
  padding: 18px 18px 20px !important;
  box-shadow: none !important;
}
.panel-label {
  margin: 0 0 14px;
  padding: 0 0 8px;
  border-bottom: 1px solid #e4e4df;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #5c5c58;
}
.field-hint {
  margin: -4px 0 12px;
  font-size: 0.8rem;
  color: #8a8a84;
  line-height: 1.45;
}
/* 控件：领域 / 任务 / 文本框等统一白底 */
.gradio-container .block {
  background: #ffffff !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}
.gradio-container .form,
.gradio-container .wrap,
.gradio-container .wrap-inner,
.gradio-container .secondary-wrap,
.gradio-container .padded,
.gradio-container .block > .wrap {
  background: #ffffff !important;
}
.gradio-container label,
.gradio-container .label-wrap span {
  color: #3a3a38 !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
  background: transparent !important;
}
.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input:not([type="radio"]):not([type="checkbox"]),
.gradio-container select {
  color: #1a1a1a !important;
  background: #ffffff !important;
  border: 1px solid #cfcfc9 !important;
  border-radius: 2px !important;
  box-shadow: none !important;
}
.gradio-container textarea:focus,
.gradio-container input:focus {
  border-color: #8a8a84 !important;
  outline: none !important;
  box-shadow: none !important;
}
/* 下拉框本体白底 */
.gradio-container .dropdown-arrow,
.gradio-container [class*="container"] > .wrap {
  background: #ffffff !important;
}
/* Radio / checkbox：白底选项，选中浅灰描边 */
.gradio-container .checkbox-label,
.gradio-container .radio-label,
.gradio-container label:has(input[type="radio"]),
.gradio-container label:has(input[type="checkbox"]),
.gradio-container .wrap label {
  background: #ffffff !important;
  border: 1px solid #cfcfc9 !important;
  border-radius: 2px !important;
  color: #1a1a1a !important;
  box-shadow: none !important;
}
.gradio-container .checkbox-label:has(input:checked),
.gradio-container .radio-label:has(input:checked),
.gradio-container label:has(input[type="radio"]:checked),
.gradio-container label:has(input[type="checkbox"]:checked) {
  background: #f0f0ec !important;
  border-color: #8a8a84 !important;
  color: #1a1a1a !important;
}
.gradio-container input[type="radio"],
.gradio-container input[type="checkbox"] {
  accent-color: #2a2a28 !important;
}
/* 按钮 */
#run-btn,
button.primary,
.primary {
  background: #2a2a28 !important;
  color: #fafaf9 !important;
  border: 1px solid #2a2a28 !important;
  border-radius: 2px !important;
  min-height: 40px !important;
  font-weight: 500 !important;
  letter-spacing: 0.04em !important;
  box-shadow: none !important;
}
#run-btn:hover,
button.primary:hover {
  background: #1a1a1a !important;
}
#top-actions {
  gap: 10px !important;
  margin: 0 0 16px !important;
  align-items: center !important;
}
#top-actions .field-hint {
  margin: 0 !important;
  flex: 1 1 auto;
}
#clear-results-btn,
#reset-form-btn,
button.secondary {
  background: #ffffff !important;
  color: #1a1a1a !important;
  border: 1px solid #cfcfc9 !important;
  border-radius: 2px !important;
  box-shadow: none !important;
  min-height: 36px !important;
}
#clear-results-btn:hover,
#reset-form-btn:hover,
button.secondary:hover {
  background: #f0f0ec !important;
  border-color: #8a8a84 !important;
}
/* 下拉 */
.gradio-container [role="listbox"],
.gradio-container [role="option"] {
  background: #ffffff !important;
  color: #1a1a1a !important;
  border-color: #cfcfc9 !important;
}
.gradio-container [role="option"][aria-selected="true"],
.gradio-container [role="option"]:hover {
  background: #ececea !important;
  color: #1a1a1a !important;
}
/* 图库 */
.gradio-container .gallery {
  background: #ffffff !important;
  border: 1px solid #d0d0ca !important;
  border-radius: 2px !important;
  box-shadow: none !important;
}
/* 上传区：白底 + 深字，禁止横向滚动 */
.gradio-container .upload-container,
.gradio-container .wrap.default.full,
#col-input .block {
  max-width: 100% !important;
  overflow-x: hidden !important;
}
.gradio-container .upload-container {
  background: #ffffff !important;
  border: 1px solid #d0d0ca !important;
  border-radius: 2px !important;
  box-shadow: none !important;
  color: #1a1a1a !important;
}
/* 已上传文件列表（Gradio FilePreview 表格） */
.gradio-container .file-preview-holder {
  overflow-x: hidden !important;
  overflow-y: auto !important;
  max-width: 100% !important;
  background: #ffffff !important;
  border: 1px solid #b8b8b0 !important;
  border-radius: 2px !important;
  margin-top: 4px !important;
}
.gradio-container table.file-preview {
  width: 100% !important;
  max-width: 100% !important;
  table-layout: fixed !important;
  color: #1a1a1a !important;
  margin: 0 !important;
}
.gradio-container tr.file,
.gradio-container table.file-preview tbody > tr,
.gradio-container table.file-preview tbody > tr:nth-child(odd),
.gradio-container table.file-preview tbody > tr:nth-child(even) {
  display: flex !important;
  width: 100% !important;
  max-width: 100% !important;
  background: #e4e4dc !important;
  border-bottom: 1px solid #c8c8c0 !important;
  color: #111111 !important;
}
.gradio-container tr.file:hover {
  background: #d8d8d0 !important;
}
.gradio-container td.filename,
.gradio-container td.filename .stem,
.gradio-container td.filename .ext,
.gradio-container .file-preview-holder span {
  color: #111111 !important;
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
  color: #3a3a38 !important;
}
.gradio-container td.download a {
  color: #1a1a1a !important;
  text-decoration: none !important;
  font-weight: 500 !important;
}
.gradio-container td.download a:hover {
  text-decoration: underline !important;
  color: #000000 !important;
}
.gradio-container .label-clear-button {
  color: #3a3a38 !important;
}
/* 左栏 / 模板区：去掉横向滚动 */
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
#col-input textarea {
  max-width: 100% !important;
  overflow-x: hidden !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
/* 可编辑模板：编译后更醒目，强调第二步 */
#compiled-wrap {
  margin-top: 14px;
  padding: 12px 12px 4px;
  border: 1px solid #a8a8a0;
  background: #ffffff;
  border-radius: 2px;
}
#compiled-wrap .step-banner {
  margin: 0 0 8px;
  font-size: 0.8rem;
  color: #3a3a38;
  line-height: 1.5;
}
#compiled-wrap .step-banner strong {
  color: #111111;
  font-weight: 600;
}
#compiled-tpl textarea {
  background: #fafaf7 !important;
  border: 1px solid #a8a8a0 !important;
  min-height: 12rem !important;
  color: #111111 !important;
}
#clear-tpl-btn {
  margin-top: 4px !important;
}
/* 下载列表 */
.dl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid #d0d0ca;
  background: #ffffff;
}
.dl-item {
  border-bottom: 1px solid #e8e8e4;
}
.dl-item:last-child {
  border-bottom: none;
}
.dl-item a {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 10px 12px;
  text-decoration: none !important;
  color: #1a1a1a !important;
}
.dl-item a:hover {
  background: #f0f0ec;
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
  color: #8a8a84;
  font-variant-numeric: tabular-nums;
}
.dl-empty {
  margin: 0;
  padding: 16px 12px;
  border: 1px solid #e0e0da;
  background: #ffffff;
  color: #8a8a84;
  font-size: 0.875rem;
}
/* 日志区略紧凑 */
#log-box textarea {
  font-family: "IBM Plex Mono", "Cascadia Mono", "Consolas", monospace !important;
  font-size: 0.8rem !important;
  line-height: 1.45 !important;
}
@media (max-width: 900px) {
  .gradio-container {
    padding: 16px 12px 32px !important;
  }
  #col-input, #col-output {
    padding: 14px !important;
  }
}
"""


def build_app() -> gr.Blocks:
    initial_domain = "notes"
    initial_choices = _task_choices(initial_domain)
    with gr.Blocks(title="AgentFlow") as demo:
        gr.HTML(
            """
            <header id="app-header">
              <h1>AgentFlow</h1>
              <p>选择领域与任务，提供文本或文件，可选模板后运行。
              再次测试直接再点「运行」即可，无需刷新。</p>
            </header>
            """
        )
        # 第一行：清空 / 重置（再测入口，不埋在表单底部）
        with gr.Row(elem_id="top-actions"):
            clear_results_btn = gr.Button(
                "清空结果",
                variant="secondary",
                elem_id="clear-results-btn",
            )
            reset_form_btn = gr.Button(
                "重置表单",
                variant="secondary",
                elem_id="reset-form-btn",
            )
        gr.HTML(
            '<p class="field-hint" style="margin:-8px 0 14px">'
            "「清空结果」只清右侧；「重置表单」清空输入与模板（保留领域/任务）。"
            "改完直接再运行，无需刷新浏览器。"
            "</p>"
        )
        with gr.Row(elem_id="work-row", equal_height=False):
            with gr.Column(scale=5, elem_id="col-input"):
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
                gr.HTML('<div class="panel-label" style="margin-top:18px">输入</div>')
                gr.HTML(
                    '<p class="field-hint">文件与文本二选一；同时提供时优先使用文件。</p>'
                )
                input_upload = gr.File(
                    label="文本文件",
                    file_count="single",
                    file_types=[".txt"],
                    type="filepath",
                )
                input_text = gr.Textbox(
                    label="文本",
                    lines=7,
                    placeholder="粘贴会议记录或笔记原文…",
                )
                gr.HTML(
                    '<div class="panel-label" style="margin-top:18px">模板（可选）</div>'
                )
                gr.HTML(
                    '<p class="field-hint">'
                    "三种写法任选：① 带 [占位符] 的 Markdown；② 格式/结构说明；"
                    "③ 自然语言（如「约400字，标题+纪要+风险表3行+待办表3行」）。"
                    "自然语言会先编译成可编辑模板，确认后再生成。"
                    "</p>"
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
                        label="模板正文或自然语言",
                        lines=5,
                        max_lines=10,
                        placeholder=(
                            "自然语言示例：\n"
                            "约400字。第一行做标题；\n"
                            "纪要约200字；风险做成表格约3行；待办做成表格约3行。"
                        ),
                    )
                # 折叠区外：编译结果始终可见，形成清晰两步流
                with gr.Group(visible=False, elem_id="compiled-wrap") as compiled_wrap:
                    gr.HTML(
                        '<p class="step-banner">'
                        "<strong>第 2 步 · 确认模板</strong>　"
                        "可改固定文字与 [占位符] 说明，满意后点下方按钮生成结果。"
                        "若要重新用自然语言编译，先点「清除可编辑模板」。"
                        "</p>"
                    )
                    compiled_template = gr.Textbox(
                        label="可编辑模板",
                        lines=10,
                        max_lines=22,
                        elem_id="compiled-tpl",
                        placeholder="自然语言编译结果会出现在这里。",
                        show_label=True,
                    )
                    clear_tpl_btn = gr.Button(
                        "清除可编辑模板",
                        variant="secondary",
                        elem_id="clear-tpl-btn",
                        size="sm",
                    )
                run_button = gr.Button("运行", variant="primary", elem_id="run-btn")

            with gr.Column(scale=6, elem_id="col-output"):
                gr.HTML('<div class="panel-label">结果</div>')
                log_output = gr.Textbox(
                    label="日志",
                    lines=12,
                    elem_id="log-box",
                )
                image_output = gr.Gallery(
                    label="图片",
                    columns=2,
                    height=280,
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
        result_outputs = [log_output, image_output, files_output]
        run_button.click(
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
            outputs=[*result_outputs, *hitl_outputs],
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
            body_background_fill="#f4f4f2",
            body_background_fill_dark="#f4f4f2",
            block_background_fill="#ffffff",
            block_border_width="0px",
            block_shadow="none",
            button_primary_background_fill="#2a2a28",
            button_primary_background_fill_hover="#1a1a1a",
            button_primary_text_color="#fafaf9",
            border_color_primary="#d0d0ca",
            input_background_fill="#ffffff",
        ),
        css=CSS,
    )
