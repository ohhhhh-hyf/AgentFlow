"""Gradio Web 前端 —— 零侵入，复用现有 MeetingAgentSystem。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from meeting_agent.config import load_env
from meeting_agent.logging_config import setup_logging
from meeting_agent.models import UserIdentity
from meeting_agent.orchestrator import MeetingAgentSystem

# ---- 初始化 -----------------------------------------------------------
load_env(PROJECT_ROOT / ".env")
setup_logging()


# ---- 核心逻辑 ---------------------------------------------------------
async def _run_agent(
    meeting_text: str,
    profile_json: str,
    objective_mode: bool,
    template: str,
    progress: gr.Progress,
) -> tuple[str, str]:
    """调用现有 Agent 系统，返回 (纪要, 待办)。"""
    # 1. 解析用户画像
    if objective_mode:
        user = UserIdentity(perspective="objective")
    else:
        if not profile_json.strip():
            return "❌ 请输入用户画像 JSON 或勾选「客观全员视角」", ""
        try:
            user = UserIdentity(**json.loads(profile_json))
        except (json.JSONDecodeError, TypeError) as exc:
            return f"❌ 用户画像 JSON 格式错误：{exc}", ""

    # 2. 校验会议文本
    if not meeting_text.strip():
        return "❌ 请输入会议内容", ""

    # 3. 进度回调
    steps_total = 8  # 预估值
    progress((0, steps_total), desc="启动 Agent 系统...")

    class _GradioProgress:
        def __init__(self, prog, total):
            self.prog = prog
            self.total = total
            self.index = 0

        def __call__(self, event, label):
            if "｜" in label:
                label = label.split("｜", 1)[1].strip()
            if event == "start":
                self.index += 1
                step = min(self.index, self.total)
                self.prog((step, self.total), desc=label)
            elif event == "done":
                self.prog((self.index, self.total), desc=f"✓ {label}")

    progress_handler = _GradioProgress(progress, steps_total)

    # 4. 运行
    system = MeetingAgentSystem(progress_handler=progress_handler)
    result = await system.run(meeting_text, user, template=template)

    # 5. 格式化输出
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
        minutes += f"\n\n⚠ {result.quality_warning}"

    progress((steps_total, steps_total), desc="✓ 完成")
    return minutes, actions


def generate(
    meeting_text: str, profile_json: str, objective_mode: bool,
    template: str = "", progress=gr.Progress(),
):
    """同步包装，供 Gradio 调用。"""
    return asyncio.run(
        _run_agent(
            meeting_text.strip(), profile_json.strip(), objective_mode,
            template.strip(), progress,
        )
    )


# ---- 文件读取 ---------------------------------------------------------
def load_text_file(file) -> str:
    if file is None:
        return ""
    return Path(file.name).read_text(encoding="utf-8")


# ---- UI ---------------------------------------------------------------
with gr.Blocks(title="会议纪要 Agent", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 📋 会议纪要多 Agent 系统
    输入会议文本和用户画像，AI 自动生成**个性化会议纪要**和**待办事项**。
    支持个人视角和客观全员视角两种模式。
    """)

    with gr.Row(equal_height=True):
        # ---- 左栏：会议输入 ----
        with gr.Column(scale=1):
            gr.Markdown("### 📝 会议内容")
            meeting_text = gr.Textbox(
                label="会议文本",
                placeholder="在此粘贴会议记录...\n\n示例：\n会议主题：XX小区活动筹备会\n时间：周一晚上7点\n\n王芳：目前有26个家庭报名...\n李明：我负责整理报名名单...",
                lines=16,
            )
            meeting_file = gr.File(label="📎 上传 .txt 文件", file_types=[".txt"])
            meeting_file.change(load_text_file, meeting_file, meeting_text)

        # ---- 右栏：画像 + 模式 ----
        with gr.Column(scale=1):
            gr.Markdown("### 👤 用户画像")
            profile_json = gr.Textbox(
                label="用户画像 JSON",
                placeholder='{\n  "name": "李明",\n  "role": "居民志愿者",\n  "department": "春风小区志愿者小组",\n  "responsibilities": ["报名信息整理", "现场签到"],\n  "interests": ["报名名单准确性", "现场秩序"],\n  "context": "希望明确活动前和活动当天需要完成的事项"\n}',
                lines=10,
            )
            profile_file = gr.File(label="📎 上传 .json 文件", file_types=[".json"])
            profile_file.change(load_text_file, profile_file, profile_json)
            objective_mode = gr.Checkbox(
                label="🌐 客观全员视角（不绑定个人，生成全量客观纪要）",
                value=False,
                info="勾选后忽略用户画像，生成覆盖全体参会人的中立纪要",
            )
            gr.Markdown("### 📐 输出模板（可选）")
            template_text = gr.Textbox(
                label="Markdown 模板",
                placeholder="不填则使用默认自由段落格式。\n模板中用 [描述] 作为占位符，系统将自动填充。\n\n示例见 template/project_progress.md",
                lines=6,
            )
            template_file = gr.File(label="📎 上传 .md 模板文件", file_types=[".md"])
            template_file.change(load_text_file, template_file, template_text)

    # ---- 生成按钮 ----
    generate_btn = gr.Button("🚀 生成纪要", variant="primary", size="lg")

    # ---- 输出 ----
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📄 会议纪要")
            minutes_output = gr.Textbox(
                label="",
                lines=18,
                interactive=False,
                placeholder="生成的会议纪要将显示在这里...",
            )
        with gr.Column():
            gr.Markdown("### ✅ 待办事项")
            actions_output = gr.Textbox(
                label="",
                lines=18,
                interactive=False,
                placeholder="提取的待办事项将显示在这里...",
            )

    generate_btn.click(
        generate,
        [meeting_text, profile_json, objective_mode, template_text],
        [minutes_output, actions_output],
    )


if __name__ == "__main__":
    demo.launch()
