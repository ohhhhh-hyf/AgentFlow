"""Notes 域简易 Gradio 测试平台。

启动后先运行后端服务，再运行本文件：

    python -m app.main
    python notes_gradio_app.py
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import gradio as gr


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_BACKEND = "http://127.0.0.1:8000"


def _clean_user_id(user_id: str) -> str:
    text = (user_id or "").strip()
    return text or "1"


def _clean_subject(subject: str) -> str:
    text = (subject or "").strip()
    return text or "默认学科"


def _upload_path(file_obj: Any) -> Path | None:
    if file_obj is None:
        return None
    if isinstance(file_obj, (str, Path)):
        path = Path(file_obj)
    else:
        path = Path(getattr(file_obj, "name", "") or getattr(file_obj, "path", ""))
    return path if path.is_file() else None


def _copy_uploads(user_id: str, files: list[Any] | None) -> list[str]:
    docs_dir = DATA_DIR / _clean_user_id(user_id) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for item in files or []:
        src = _upload_path(item)
        if src is None:
            continue
        name = src.name
        dst = docs_dir / name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        names.append(name)
    return names


def _read_text_file(file_obj: Any) -> str:
    path = _upload_path(file_obj)
    if path is None:
        return ""
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _request_id(task: str) -> str:
    return f"gradio-notes-{task}-{uuid.uuid4().hex[:8]}"


def _call_notes_api(
    backend_url: str,
    task: str,
    user_id: str,
    subject: str,
    *,
    docs: list[str] | None = None,
    teacher_focus: str = "",
) -> tuple[str, str, str]:
    backend = (backend_url or DEFAULT_BACKEND).rstrip("/")
    rid = _request_id(task)
    body: dict[str, Any] = {
        "docs": docs or [],
        "texts": {},
        "extra": {"subject": _clean_subject(subject)},
    }
    if teacher_focus.strip():
        body["texts"]["teacher_focus"] = teacher_focus.strip()
    req = Request(
        f"{backend}/api/v1/notes/{task}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Request-Id": rid,
            "X-User-Id": _clean_user_id(user_id),
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=900) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return "", "", f"HTTP {exc.code}\n{detail}"
    except URLError as exc:
        return "", "", f"无法连接后端服务：{exc.reason}"
    except TimeoutError:
        return "", "", "请求超时。资料入库/OCR 较慢时可以稍后重试。"
    except Exception as exc:  # noqa: BLE001 - UI 层展示错误即可
        return "", "", f"请求失败：{exc}"

    code = payload.get("code")
    message = payload.get("message") or ""
    data = payload.get("data") or {}
    monitor = payload.get("monitor") or {}
    text = data.get("text") or ""
    file_name = data.get("file_name") or ""
    status = (
        f"code={code}  message={message}\n"
        f"request_id={payload.get('request_id') or rid}\n"
        f"token_usage={monitor.get('token_usage', 0)}  "
        f"cache_hit={monitor.get('cache_hit', 0)}  "
        f"cost_time={monitor.get('cost_time', 0)}s\n"
        f"file_name={file_name or '-'}"
    )
    return text, file_name, status


def run_library(
    backend_url: str,
    user_id: str,
    subject: str,
    files: list[Any] | None,
) -> tuple[str, str]:
    docs = _copy_uploads(user_id, files)
    if not docs:
        return "", "请先上传要入库的文件。"
    text, _file_name, status = _call_notes_api(
        backend_url,
        "library",
        user_id,
        subject,
        docs=docs,
    )
    return text, status


def run_catalog(
    backend_url: str,
    user_id: str,
    subject: str,
) -> tuple[str, str, str]:
    text, file_name, status = _call_notes_api(
        backend_url,
        "catalog",
        user_id,
        subject,
    )
    return text, file_name, status


def run_checklist(
    backend_url: str,
    user_id: str,
    subject: str,
    catalog_file_from_state: str,
    catalog_file_manual: str,
    teacher_focus_file: Any,
    teacher_focus_text: str,
) -> tuple[str, str]:
    catalog_file = (catalog_file_manual or catalog_file_from_state or "").strip()
    if not catalog_file:
        return "", "请先生成目录，或手动填写 catalog 文件名。"
    teacher_focus = "\n\n".join(
        part for part in (_read_text_file(teacher_focus_file), teacher_focus_text or "") if part.strip()
    )
    text, _file_name, status = _call_notes_api(
        backend_url,
        "checklist",
        user_id,
        subject,
        docs=[catalog_file],
        teacher_focus=teacher_focus,
    )
    return text, status


with gr.Blocks(title="Notes 域测试平台") as demo:
    gr.Markdown("# Notes 域测试平台")
    gr.Markdown("三个标签页互相独立操作。上传文件会复制到当前项目的 `data/{user_id}/docs/`。")

    with gr.Row():
        backend_url = gr.Textbox(label="后端地址", value=DEFAULT_BACKEND)
        user_id = gr.Textbox(label="User ID", value="1")
        subject = gr.Textbox(label="Subject", value="数学")

    catalog_state = gr.State("")

    with gr.Tab("1. 知识入库"):
        library_files = gr.File(
            label="上传资料文件",
            file_count="multiple",
            type="filepath",
        )
        library_btn = gr.Button("开始入库", variant="primary")
        library_status = gr.Textbox(label="运行状态", lines=5)
        library_output = gr.Markdown(label="入库报告")
        library_btn.click(
            run_library,
            inputs=[backend_url, user_id, subject, library_files],
            outputs=[library_output, library_status],
        )

    with gr.Tab("2. 目录生成"):
        catalog_btn = gr.Button("生成知识目录", variant="primary")
        catalog_file = gr.Textbox(label="生成的 catalog 文件名", interactive=False)
        catalog_status = gr.Textbox(label="运行状态", lines=5)
        catalog_output = gr.Markdown(label="目录结果")
        catalog_btn.click(
            run_catalog,
            inputs=[backend_url, user_id, subject],
            outputs=[catalog_output, catalog_state, catalog_status],
        ).then(
            lambda name: name,
            inputs=[catalog_state],
            outputs=[catalog_file],
        )

    with gr.Tab("3. 复习清单"):
        manual_catalog = gr.Textbox(
            label="Catalog 文件名",
            placeholder="可留空，默认使用上一步生成的文件名",
        )
        teacher_file = gr.File(
            label="上传老师重点文本（可选，txt/md）",
            file_count="single",
            type="filepath",
        )
        teacher_text = gr.Textbox(label="老师重点文本（可选）", lines=6)
        checklist_btn = gr.Button("生成复习清单", variant="primary")
        checklist_status = gr.Textbox(label="运行状态", lines=5)
        checklist_output = gr.Markdown(label="复习清单")
        checklist_btn.click(
            run_checklist,
            inputs=[
                backend_url,
                user_id,
                subject,
                catalog_state,
                manual_catalog,
                teacher_file,
                teacher_text,
            ],
            outputs=[checklist_output, checklist_status],
        )


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7861)
