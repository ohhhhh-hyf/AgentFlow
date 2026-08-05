"""Gradio Web 前端 —— 零侵入，复用现有 MeetingAgentSystem。"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from meeting_agent.config import load_env
from meeting_agent.logging_config import setup_logging
from meeting_agent.models import UserIdentity
from meeting_agent.orchestrator import MeetingAgentSystem


# ---- 核心逻辑 ---------------------------------------------------------
def _generate_stream(
    meeting_text: str,
    profile_json: str,
    objective_mode: bool,
    template: str = "",
):
    """生成器：先实时推送各 Agent 执行进度，完成后推送纪要+待办。"""
    # 1. 解析输入
    if objective_mode:
        user = UserIdentity(perspective="objective")
    else:
        if not profile_json.strip():
            yield "请输入用户画像 JSON 或勾选客观全员视角", "", ""
            return
        try:
            user = UserIdentity(**json.loads(profile_json))
        except (json.JSONDecodeError, TypeError) as exc:
            yield f"用户画像 JSON 格式错误：{exc}", "", ""
            return

    if not meeting_text.strip():
        yield "请输入会议内容", "", ""
        return

    # 2. 线程安全的进度收集
    progress_lines: list[str] = []
    lock = threading.Lock()
    index = 0

    def _on_progress(event: str, label: str) -> None:
        nonlocal index
        if "｜" in label:
            label = label.split("｜", 1)[1].strip()
        with lock:
            if event == "start":
                index += 1
                progress_lines.append(f"{index:02d}  {label}  ...")
            elif event == "done":
                progress_lines.append(f"{index:02d}  {label}  完成")

    # 3. 后台线程跑 Agent
    result_holder: dict = {}
    error_holder: dict = {}

    def _run() -> None:
        try:
            async def _inner() -> None:
                system = MeetingAgentSystem(progress_handler=_on_progress)
                result_holder["result"] = await system.run(
                    meeting_text, user, template=template,
                )
            asyncio.run(_inner())
        except Exception as exc:
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # 4. 轮询进度，实时推送到前端
    last_count = 0
    while thread.is_alive():
        with lock:
            current = len(progress_lines)
        if current > last_count:
            last_count = current
            with lock:
                text = "\n".join(progress_lines)
            yield text, "", ""
        time.sleep(0.1)

    thread.join()

    if error_holder:
        yield f"运行出错：{error_holder['error']}", "", ""
        return

    # 5. 格式化最终结果
    result = result_holder.get("result")
    if result is None:
        yield "未获取到结果", "", ""
        return

    minutes = result.personalized_minutes or "（暂无内容）"
    actions_list: list[str] = []
    if result.action_items:
        for i, item in enumerate(result.action_items, start=1):
            meta = []
            if item.get("owner"):
                meta.append(f"负责人：{item['owner']}")
            if item.get("deadline"):
                meta.append(f"截止：{item['deadline']}")
            suffix = f"（{'；'.join(meta)}）" if meta else ""
            actions_list.append(f"{i}. {item['task']}{suffix}")
    actions = "\n".join(actions_list) if actions_list else "暂无待办事项"
    if result.quality_warning:
        minutes += f"\n\n{result.quality_warning}"

    # 完成态：进度显示全部完成 + 纪要 + 待办
    with lock:
        progress_lines.append("")
        progress_lines.append("全部完成")
    yield "\n".join(progress_lines), minutes, actions


def load_text_file(file) -> str:
    if file is None:
        return ""
    return Path(file.name).read_text(encoding="utf-8")


# ---- UI ---------------------------------------------------------------
with gr.Blocks(title="会议纪要 Agent") as demo:
    gr.Markdown("# 会议纪要多 Agent 系统")

    with gr.Row():
        with gr.Column():
            meeting_text = gr.Textbox(
                label="会议内容",
                placeholder="在此粘贴会议记录，或使用下方上传按钮",
                lines=14,
            )
            meeting_file = gr.File(label="上传 .txt 文件", file_types=[".txt"])
            meeting_file.change(load_text_file, meeting_file, meeting_text)

        with gr.Column():
            profile_json = gr.Textbox(
                label="用户画像 (JSON)",
                placeholder='{"name": "李明", "role": "居民志愿者", ...}',
                lines=8,
            )
            profile_file = gr.File(label="上传 .json 文件", file_types=[".json"])
            profile_file.change(load_text_file, profile_file, profile_json)
            objective_mode = gr.Checkbox(label="客观全员视角", value=False)

    with gr.Accordion("输出模板（可选）", open=False):
        with gr.Row():
            template_text = gr.Textbox(
                label="Markdown 模板",
                placeholder="不填则使用默认格式。模板中用 [描述] 作为占位符，系统将自动填充。",
                lines=5,
            )
            template_file = gr.File(label="上传 .md 模板", file_types=[".md"])
            template_file.change(load_text_file, template_file, template_text)

    generate_btn = gr.Button("生成纪要", variant="primary")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 执行进度")
            progress_output = gr.Textbox(label="", lines=10, interactive=False)
        with gr.Column(scale=2):
            gr.Markdown("### 会议纪要")
            minutes_output = gr.Textbox(label="", lines=14, interactive=False)

    gr.Markdown("### 待办事项")
    actions_output = gr.Textbox(label="", lines=6, interactive=False)

    generate_btn.click(
        _generate_stream,
        [meeting_text, profile_json, objective_mode, template_text],
        [progress_output, minutes_output, actions_output],
    ).then(
        # 生成完成后关闭加载动画（如果有的话）
        None, None, None,
    )


if __name__ == "__main__":
    load_env(PROJECT_ROOT / ".env")
    setup_logging()
    demo.launch()
