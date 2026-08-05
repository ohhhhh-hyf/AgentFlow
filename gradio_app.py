"""Gradio Web 前端 —— 展示 Agent 工作流架构与实时状态。"""
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

# ── Agent 架构定义 ────────────────────────────────────────────
# 每个 Agent: key(唯一标识), prefix(匹配progress label), label(中文名), layer(层级)
_AGENTS = [
    # Layer 1 — 并行
    {"key": "meeting_understanding", "prefix": "MeetingUnderstandingAgent", "label": "理解会议内容", "layer": 1, "core": True},
    {"key": "perspective_modeling", "prefix": "PerspectiveModelingAgent", "label": "建立用户视角", "layer": 1, "core": True},
    # Layer 2 — 并行
    {"key": "minutes_generation", "prefix": "MinutesGenerationAgent", "label": "生成纪要草稿", "layer": 2, "core": True},
    {"key": "action_items", "prefix": "ActionItemsAgent", "label": "提取待办事项", "layer": 2, "core": True},
    # Layer 3 — 串行
    {"key": "supervisor_review", "prefix": "SupervisorAgent", "label": "审核结果质量", "layer": 3, "core": True},
    # Layer 4 — 返工（条件触发）
    {"key": "revision", "prefix": "Revision", "label": "返工修正", "layer": 4, "core": False},
    # Layer 5 — 并行输出
    {"key": "render_minutes", "prefix": "RenderMinutes", "label": "渲染纪要正文", "layer": 5, "core": True},
    {"key": "format_actions", "prefix": "FormatActions", "label": "格式化待办事项", "layer": 5, "core": True},
    # Layer 5 — 降级路径（条件触发）
    {"key": "fallback_minutes", "prefix": "FallbackMinutes", "label": "降级渲染纪要", "layer": 5, "core": False},
    {"key": "fallback_actions", "prefix": "FallbackActions", "label": "降级提取待办", "layer": 5, "core": False},
]


def _key(label: str) -> str:
    for a in _AGENTS:
        if label.startswith(a["prefix"]):
            return a["key"]
    return "unknown"


def _build_pipeline(states: dict[str, str]) -> str:
    """构建工作流架构 HTML：按层排列，显示每个 Agent 的状态。"""
    max_layer = max(a["layer"] for a in _AGENTS)
    layers: dict[int, list[dict]] = {}
    for i in range(1, max_layer + 1):
        layers[i] = []
    for a in _AGENTS:
        s = states.get(a["key"], "pending")
        # 非核心 agent 从未触发则不显示 (revision / fallback)
        if not a.get("core", True) and s == "pending":
            continue
        layers[a["layer"]].append({**a, "status": s})

    # 状态样式
    def _dot(s):
        return {"pending": "#d1d5db", "running": "#3b82f6", "done": "#22c55e"}.get(s, "#d1d5db")
    def _bd(s):
        return {"pending": "#e5e7eb", "running": "#bfdbfe", "done": "#bbf7d0"}.get(s, "#e5e7eb")
    def _bg(s):
        return {"pending": "#fafafa", "running": "#f0f7ff", "done": "#f5fdf7"}.get(s, "#fafafa")
    def _text(s):
        return {"pending": "等待中", "running": "执行中", "done": "已完成"}.get(s, "等待中")
    def _txt_color(s):
        return {"pending": "#9ca3af", "running": "#1d4ed8", "done": "#15803d"}.get(s, "#9ca3af")

    rows: list[str] = []
    for layer_num in range(1, max_layer + 1):
        cards = layers[layer_num]
        if not cards:
            continue
        if rows:
            rows.append('<div style="text-align:center;line-height:1;margin:2px 0;">'
                        '<span style="color:#d1d5db;font-size:16px;">│</span></div>')
        items: list[str] = []
        for c in cards:
            s = c["status"]
            pulse = "animation:p 1.2s ease-in-out infinite;" if s == "running" else ""
            items.append(
                f'<div style="display:inline-flex;flex-direction:column;align-items:center;'
                f'margin:0 8px;padding:10px 18px;border-radius:8px;'
                f'background:{_bg(s)};border:1.5px solid {_bd(s)};{pulse}'
                f'min-width:130px;">'
                f'<span style="display:inline-block;width:10px;height:10px;'
                f'border-radius:50%;background:{_dot(s)};margin-bottom:6px;flex-shrink:0;"></span>'
                f'<span style="font-size:14px;font-weight:600;color:#1f2937;white-space:nowrap;">{c["label"]}</span>'
                f'<span style="font-size:11px;color:{_txt_color(s)};margin-top:3px;">{_text(s)}</span>'
                f'</div>'
            )
        rows.append('<div style="text-align:center;">' + "".join(items) + '</div>')

    return (
        '<style>@keyframes p{0%,100%{opacity:1}50%{opacity:.4}}</style>'
        '<div style="font-family:system-ui,sans-serif;padding:12px 0;">'
        + "".join(rows) +
        '</div>'
    )


# ── 主生成器 ──────────────────────────────────────────────────
def _generate(meeting_text: str, profile_json: str, template: str = ""):
    template = template or ""
    # 解析输入
    if not profile_json.strip():
        yield _build_pipeline({}), "请输入用户画像 JSON", ""
        return
    try:
        user = UserIdentity(**json.loads(profile_json))
    except (json.JSONDecodeError, TypeError) as exc:
        yield _build_pipeline({}), f"用户画像 JSON 格式错误：{exc}", ""
        return

    if not meeting_text.strip():
        yield _build_pipeline({}), "请输入会议内容", ""
        return

    # Agent 状态追踪
    agent_states: dict[str, str] = {}
    lock = threading.Lock()

    def _on_progress(event: str, label: str) -> None:
        k = _key(label)
        if k == "unknown":
            return
        with lock:
            if event == "start":
                agent_states[k] = "running"
            else:
                agent_states[k] = "done"

    # 后台运行
    result_holder: dict = {}
    error_holder: dict = {}

    def _run() -> None:
        try:
            async def _inner() -> None:
                s = MeetingAgentSystem(progress_handler=_on_progress)
                result_holder["result"] = await s.run(meeting_text, user, template=template)
            asyncio.run(_inner())
        except Exception as exc:
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    # 轮询推送
    last_snapshot = ""
    while thread.is_alive():
        with lock:
            cur = json.dumps(agent_states, sort_keys=True)
        if cur != last_snapshot:
            last_snapshot = cur
            with lock:
                sc = dict(agent_states)
            yield _build_pipeline(sc), "", ""
        time.sleep(0.15)
    thread.join()

    if error_holder:
        with lock:
            sc = dict(agent_states)
        yield _build_pipeline(sc), f"运行出错：{error_holder['error']}", ""
        return

    # 最终结果
    with lock:
        sc = dict(agent_states)
    html = _build_pipeline(sc)

    result = result_holder.get("result")
    if result is None:
        yield html, "未获取到结果", ""
        return

    minutes = result.personalized_minutes or "（暂无内容）"
    if result.quality_warning:
        minutes += f"\n\n{result.quality_warning}"

    if result.action_items:
        acts: list[str] = []
        _prio = {"high": "高优先", "medium": "中优先", "low": "低优先"}
        for i, item in enumerate(result.action_items, 1):
            meta = []
            prio = item.get("priority", "")
            if prio and prio in _prio:
                meta.append(_prio[prio])
            if item.get("owner"):
                meta.append(f"负责人：{item['owner']}")
            if item.get("deadline"):
                meta.append(f"截止：{item['deadline']}")
            suffix = f"（{'；'.join(meta)}）" if meta else ""
            acts.append(f"{i}. {item['task']}{suffix}")
        actions = "\n".join(acts)
    else:
        actions = "暂无待办事项"

    # 流式输出纪要文本（待办在首帧即展示，不等待纪要流结束）
    MINUTES_STREAM = True
    if MINUTES_STREAM and minutes:
        yield html, "", actions  # 待办结果即刻展示
        streamed = ""
        chunk_size = max(1, len(minutes) // 60)
        for i in range(0, len(minutes), chunk_size):
            streamed = minutes[: i + chunk_size]
            yield html, streamed, actions
            time.sleep(0.03)
    else:
        yield html, minutes, actions


def load_text_file(file) -> str:
    if file is None:
        return ""
    return Path(file.name).read_text(encoding="utf-8")


# ── UI ────────────────────────────────────────────────────────
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
                lines=14,
            )
            profile_file = gr.File(label="上传 .json 文件", file_types=[".json"])
            profile_file.change(load_text_file, profile_file, profile_json)

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

    gr.Markdown("### Agent 工作流")
    pipeline_output = gr.HTML(value=_build_pipeline({}))

    with gr.Row():
        with gr.Column():
            gr.Markdown("### 会议纪要")
            minutes_output = gr.Textbox(label="", lines=14, interactive=False)
        with gr.Column():
            gr.Markdown("### 待办事项")
            actions_output = gr.Textbox(label="", lines=14, interactive=False)

    generate_btn.click(
        _generate,
        [meeting_text, profile_json, template_text],
        [pipeline_output, minutes_output, actions_output],
    )


if __name__ == "__main__":
    load_env(PROJECT_ROOT / ".env")
    setup_logging()
    demo.launch()
