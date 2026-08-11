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
    new_files = sorted(after - before, key=lambda path: path.stat().st_mtime)
    return [str(path) for path in new_files]


def _png_previews(files: list[str]) -> list[str]:
    return [path for path in files if path.lower().endswith(".png")]


def _clean_filename(name: str) -> str:
    name = re.sub(r"_(\d{8})_(\d{6})(?=\.)", "", name)
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
        return '<div class="download-empty">暂无生成文件</div>'
    cards = ['<div class="download-list">']
    for file in files:
        path = Path(file)
        try:
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            continue
        clean_name = _clean_filename(path.name)
        suffix = path.suffix.lower().lstrip(".") or "file"
        href = f"data:{_mime_type(path)};base64,{payload}"
        cards.append(
            '<a class="download-card" '
            f'href="{href}" download="{html.escape(clean_name)}">'
            '<span class="download-main">'
            f'<span class="download-name">{html.escape(clean_name)}</span>'
            f'<span class="download-path">{html.escape(path.parent.name)}</span>'
            "</span>"
            f'<span class="download-badge">{html.escape(suffix.upper())}</span>'
            "</a>"
        )
    cards.append("</div>")
    return "\n".join(cards)


def update_domain(domain_label: str):
    domain = _domain_value(domain_label)
    choices = _task_choices(domain)
    selected_task = choices[0] if choices else None
    return gr.update(choices=choices, value=selected_task)


def _domain_value(value: str) -> str:
    if value in DOMAIN_NAMES:
        return value
    return _task_value(value)


def run_from_ui(
    domain_label: str,
    task_label: str | None,
    input_upload,
    input_text: str | None,
    template_upload,
    template_text: str | None,
):
    domain = _domain_value(domain_label)
    if not task_label:
        return "请选择任务线。", [], '<div class="download-empty">暂无生成文件</div>'

    tasks = [_task_value(task_label)]
    profile_path = PROJECT_ROOT / "samples" / domain / "profile" / "object_profile.json"
    if not profile_path.exists():
        return f"默认 profile 不存在：{profile_path}", [], '<div class="download-empty">暂无生成文件</div>'

    ctx = _ctx(domain)
    with tempfile.TemporaryDirectory(prefix="agentflow_gradio_") as temp_dir:
        temp_root = Path(temp_dir)
        input_file = _input_path(input_upload, input_text, temp_root, "input.txt")
        if input_file is None:
            return "请上传输入文件，或直接在文本框里输入内容。", [], '<div class="download-empty">暂无生成文件</div>'

        templates: dict[str, Path] = {}
        template_file = _input_path(template_upload, template_text, temp_root, "template.md")
        if template_file is not None:
            templates[tasks[0]] = template_file

        load_env(PROJECT_ROOT / ".env")
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
        log = f"{log}\n\n已生成 {len(files)} 个文件，可在右侧直接查看或下载。"
    return log, _png_previews(files), _artifact_download_html(files)


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
    text = re.sub(r"knowledge_graph_\d{8}_\d{6}", "knowledge_graph", text)
    text = re.sub(r"mindmap_\d{8}_\d{6}", "mindmap", text)
    text = re.sub(r"report_\d{8}_\d{6}", "report", text)
    text = re.sub(r"result_\d{8}_\d{6}", "result", text)
    return text


CSS = """
:root, .dark, .gradio-container {
  --body-background-fill: #edf3f6 !important;
  --body-text-color: #111827 !important;
  --block-background-fill: #ffffff !important;
  --block-border-color: #d5dde6 !important;
  --block-label-background-fill: #ffffff !important;
  --block-label-text-color: #24313a !important;
  --input-background-fill: #ffffff !important;
  --input-border-color: #c8d3de !important;
  --input-placeholder-color: #64748b !important;
  --neutral-950: #111827 !important;
  --neutral-900: #1f2937 !important;
  --neutral-800: #334155 !important;
  --neutral-700: #475569 !important;
  --neutral-600: #64748b !important;
  --neutral-100: #f1f5f9 !important;
  --neutral-50: #f8fafc !important;
}
.gradio-container {
  max-width: 1180px !important;
  margin: 0 auto !important;
  color: #111827;
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
}
body {
  background: #edf3f6 !important;
}
#title-block, #config-panel, #result-panel {
  border: 1px solid #cbd5e1;
  background: #ffffff;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.10);
  border-radius: 14px;
}
#title-block {
  padding: 22px 26px;
  margin: 18px 0 16px;
}
#title-block h1 {
  font-size: 28px;
  line-height: 1.25;
  margin: 0;
  color: #0f172a;
  font-weight: 700;
  letter-spacing: 0;
  text-align: center;
}
#title-block p {
  margin: 10px 0 0;
  color: #475569;
  font-size: 14px;
  text-align: center;
}
#config-panel, #result-panel {
  padding: 20px;
}
#config-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
#config-panel .form {
  gap: 14px !important;
}
.section-title {
  margin: 4px 0 -4px;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}
button.primary, .primary {
  background: #1f4e5f !important;
  border-color: #1f4e5f !important;
  min-height: 44px !important;
  border-radius: 10px !important;
  font-weight: 700 !important;
}
label, .wrap span {
  color: #0f172a !important;
}
.gradio-container textarea,
.gradio-container input,
.gradio-container select {
  color: #111827 !important;
  background: #ffffff !important;
  border-color: #cbd5e1 !important;
}
.gradio-container .block,
.gradio-container .form,
.gradio-container .wrap,
.gradio-container .panel,
.gradio-container .input-container {
  background: #ffffff !important;
  color: #111827 !important;
  border-color: #d5dde6 !important;
}
.gradio-container .block label,
.gradio-container .block span,
.gradio-container .block p,
.gradio-container .block div {
  color: #111827;
}
.gradio-container .checkbox-label,
.gradio-container .checkbox-label span,
.gradio-container .radio-label,
.gradio-container .radio-label span {
  background: #eef3f7 !important;
  color: #10202a !important;
  border-color: #9fb0bf !important;
}
.gradio-container .checkbox-label:has(input:checked),
.gradio-container .checkbox-label:has(input:checked) span,
.gradio-container .radio-label:has(input:checked),
.gradio-container .radio-label:has(input:checked) span {
  background: #1f4e5f !important;
  color: #ffffff !important;
  border-color: #1f4e5f !important;
}
.gradio-container .checkbox-label input,
.gradio-container .radio-label input {
  accent-color: #1f4e5f !important;
}
.gradio-container [role="listbox"],
.gradio-container [role="option"] {
  background: #ffffff !important;
  color: #111827 !important;
}
.gradio-container [role="option"][aria-selected="true"],
.gradio-container [role="option"]:hover {
  background: #dbeafe !important;
  color: #0f172a !important;
}
.gradio-container .gallery,
.gradio-container .file-preview-holder {
  background: #f8fafc !important;
  border-color: #d5dde6 !important;
}
.download-list {
  display: grid;
  gap: 10px;
}
.download-empty {
  padding: 18px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
}
.download-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 15px;
  border: 1px solid #d5dde6;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  color: #0f172a !important;
  text-decoration: none !important;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
}
.download-card:hover {
  border-color: #1f4e5f;
  box-shadow: 0 10px 24px rgba(31, 78, 95, 0.14);
  transform: translateY(-1px);
}
.download-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}
.download-name {
  color: #0f172a;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.download-path {
  color: #64748b;
  font-size: 12px;
}
.download-badge {
  flex: 0 0 auto;
  min-width: 52px;
  text-align: center;
  padding: 5px 9px;
  border-radius: 999px;
  background: #1f4e5f;
  color: #ffffff;
  font-size: 12px;
  font-weight: 700;
}
@media (max-width: 860px) {
  #title-block {
    margin-top: 10px;
  }
  #config-panel, #result-panel {
    padding: 16px;
  }
}
"""


def build_app() -> gr.Blocks:
    initial_domain = "notes"
    initial_choices = _task_choices(initial_domain)
    with gr.Blocks(title="AgentFlow 协作式 Agent 系统") as demo:
        gr.HTML(
            """
            <div id="title-block">
              <h1>XiaoYi-TaskAgent</h1>
              <p>选择领域和任务线，上传文件或直接输入内容后运行，支持图片预览和文件下载。</p>
            </div>
            """
        )
        with gr.Row(equal_height=True):
            with gr.Column(scale=4, elem_id="config-panel"):
                gr.HTML('<div class="section-title">任务配置</div>')
                domain = gr.Dropdown(
                    label="领域",
                    choices=DOMAIN_CHOICES,
                    value=initial_domain,
                )
                tasks = gr.Radio(
                    label="任务线",
                    choices=initial_choices,
                    value=initial_choices[0] if initial_choices else None,
                )
                gr.HTML('<div class="section-title">输入内容</div>')
                input_upload = gr.File(
                    label="输入文件",
                    file_count="single",
                    file_types=[".txt"],
                    type="filepath",
                )
                input_text = gr.Textbox(
                    label="或直接输入文本",
                    lines=8,
                    placeholder="上传文件和输入文本二选一；如果两者都填写，优先使用上传文件。",
                )
                gr.HTML('<div class="section-title">模板（可选）</div>')
                template_upload = gr.File(
                    label="模板文件",
                    file_count="single",
                    file_types=[".md", ".txt"],
                    type="filepath",
                )
                template_text = gr.Textbox(
                    label="或直接输入模板",
                    lines=6,
                    placeholder="可上传模板文件，或把模板内容粘贴到这里。",
                )
                run_button = gr.Button("运行", variant="primary")
            with gr.Column(scale=5, elem_id="result-panel"):
                log_output = gr.Textbox(label="运行记录", lines=10)
                image_output = gr.Gallery(
                    label="图片预览",
                    columns=2,
                    height=320,
                )
                files_output = gr.HTML(
                    label="下载后查看",
                    value='<div class="download-empty">暂无生成文件</div>',
                )

        domain.change(
            update_domain,
            inputs=domain,
            outputs=tasks,
        )
        run_button.click(
            run_from_ui,
            inputs=[
                domain,
                tasks,
                input_upload,
                input_text,
                template_upload,
                template_text,
            ],
            outputs=[log_output, image_output, files_output],
            show_progress="minimal",
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
        theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
        css=CSS,
    )
