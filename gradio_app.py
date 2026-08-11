from __future__ import annotations

import asyncio
import base64
import contextlib
import html
import io
import os
import sys
import re
from pathlib import Path

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.runtime_context import load_domain  # noqa: E402
from tools.runner import run  # noqa: E402


DOMAIN_NAMES = ["meeting", "notes"]
DOMAIN_LABELS = {
    "meeting": "meeting · 会议",
    "notes": "notes · 笔记",
}
DOMAIN_CHOICES = [(DOMAIN_LABELS[name], name) for name in DOMAIN_NAMES]


def _ctx(domain: str):
    return load_domain(domain, PROJECT_ROOT)


def _task_choices(domain: str) -> list[str]:
    ctx = _ctx(domain)
    return [
        f"{line} · {ctx.line_cn_names.get(line, line)}"
        for line in ctx.task_lines
    ]


def _sample_choices(domain: str, kind: str) -> list[tuple[str, str]]:
    folder = PROJECT_ROOT / "samples" / domain / kind
    if not folder.exists():
        return []
    files = sorted(path for path in folder.iterdir() if path.is_file())
    return [(path.name, str(path)) for path in files]


def _template_choices(domain: str, task_label: str | None) -> list[tuple[str, str]]:
    if not task_label:
        return []
    task = _task_value(task_label)
    return _sample_choices(domain, f"{task}_template")


def _task_value(label: str) -> str:
    return label.split(" · ", 1)[0].strip()


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
    file_choices = _sample_choices(domain, "file")
    profile_choices = _sample_choices(domain, "profile")
    template_choices = _template_choices(domain, selected_task)
    return (
        gr.update(choices=choices, value=selected_task),
        gr.update(choices=file_choices, value=file_choices[0][1] if file_choices else None),
        gr.update(choices=profile_choices, value=profile_choices[0][1] if profile_choices else None),
        gr.update(choices=template_choices, value=None),
    )


def update_template_choices(domain_label: str, task_label: str):
    domain = _domain_value(domain_label)
    choices = _template_choices(domain, task_label)
    return gr.update(choices=choices, value=None)


def _domain_value(value: str) -> str:
    if value in DOMAIN_NAMES:
        return value
    return value.split(" · ", 1)[0].strip()


def run_from_ui(
    domain_label: str,
    task_labels: list[str],
    server_file_path: str | None,
    server_profile_path: str | None,
    server_template_path: str | None,
):
    domain = _domain_value(domain_label)
    if not task_labels:
        return "请选择任务线。", [], '<div class="download-empty">暂无生成文件</div>'
    tasks = [_task_value(task_labels)]
    input_file = server_file_path
    input_profile = server_profile_path
    input_template = server_template_path
    if not input_file:
        return "请选择服务器输入文本。", [], '<div class="download-empty">暂无生成文件</div>'
    if not input_profile:
        return "请选择服务器用户画像。", [], '<div class="download-empty">暂无生成文件</div>'

    ctx = _ctx(domain)
    templates: dict[str, Path] = {}
    if input_template:
        templates[tasks[0]] = Path(input_template)

    load_env(PROJECT_ROOT / ".env")
    before = _output_files(domain, tasks)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            asyncio.run(
                run(
                    ctx,
                    Path(input_file),
                    Path(input_profile),
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
    initial_file_choices = _sample_choices(initial_domain, "file")
    initial_profile_choices = _sample_choices(initial_domain, "profile")
    initial_template_choices = _template_choices(
        initial_domain,
        initial_choices[0] if initial_choices else None,
    )
    with gr.Blocks(title="AgentFlow 协作式Agent系统") as demo:
        gr.HTML(
            """
            <div id="title-block">
              <h1>XiaoYi-TaskAgent</h1>
              <p>选择领域和任务线，添加服务器样例后运行，支持图片预览或下载预览。</p>
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
                gr.HTML('<div class="section-title">服务器样例</div>')
                server_file = gr.Dropdown(
                    label="服务器输入文本",
                    choices=initial_file_choices,
                    value=initial_file_choices[0][1] if initial_file_choices else None,
                )
                server_profile = gr.Dropdown(
                    label="服务器用户画像",
                    choices=initial_profile_choices,
                    value=initial_profile_choices[0][1] if initial_profile_choices else None,
                )
                server_template = gr.Dropdown(
                    label="服务器模板文件",
                    choices=initial_template_choices,
                    value=None,
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
            outputs=[tasks, server_file, server_profile, server_template],
        )
        tasks.change(
            update_template_choices,
            inputs=[domain, tasks],
            outputs=server_template,
        )
        run_button.click(
            run_from_ui,
            inputs=[
                domain,
                tasks,
                server_file,
                server_profile,
                server_template,
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
