from __future__ import annotations

from typing import TypedDict


class MeetingState(TypedDict, total=False):
    """LangGraph 在一次运行中跨节点传递的共享上下文。"""

    transcript: str
    user: dict
    # 由画像 perspective=objective 判定，供展示与兜底拼装使用
    objective_perspective: bool
    meeting_understanding: dict
    perspective_profile: dict
    minutes_draft: dict
    extracted_action_items: dict
    supervisor_review: dict
    minutes_revision_feedback: list[str]
    actions_revision_feedback: list[str]
    revision_count: int
    # Supervisor 未批准时仍输出结果，标记为降级兜底
    quality_degraded: bool
    final_report: dict
    # 并行渲染结果：纪要正文 + 待办列表
    rendered_minutes: str
    formatted_actions: list[dict]
    # 流式模式：图内渲染节点跳过 LLM 调用，由 run_streaming 接管流式输出
    streaming: bool
    # 可选：最终纪要以此 Markdown 模板格式输出（占位符 [描述] 将被填充）
    template: str
