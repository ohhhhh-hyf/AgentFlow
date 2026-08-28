from __future__ import annotations

from collections.abc import Iterable

from client import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_SYSTEM_PROMPT,
)
from .contracts import MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT


def _trim_instruction(focus_line: str, skip_fields: Iterable[str]) -> str:
    """裁剪指令：放在用户消息最前，让模型先看到再读原文。

    双向约束：只允许列出的字段输出 []，其余字段必须照常完整输出
    （防止模型把「仅供某线使用」过度泛化成清空其它字段）。
    字段契约不变，下游读取代码零改动。
    """
    names = "、".join(str(field) for field in skip_fields)
    return (
        "【本次输出裁剪】\n"
        f"本次会议理解仅供 {focus_line or '本任务'} 线使用。"
        f"只允许以下字段输出空数组 []：{names}。\n"
        "除上述字段外，其余字段（meeting_brief、meeting_purpose、scene、decisions、"
        "action_hints、risk_hints、dependencies）必须照常按会议原文完整、准确输出，"
        "不得省略、不得清空。\n"
        "裁剪字段输出 [] 是预期行为，不要为了完整性自检把它们填回内容。"
    )


class MeetingUnderstandingAgent:
    """从会议原文中提取议题、决策、风险和未决问题。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(
        self,
        transcript: str,
        *,
        focus_line: str = "",
        skip_fields: Iterable[str] = (),
    ) -> MeetingUnderstanding:
        user = f"会议原文：\n{transcript}"
        fields = [str(field) for field in skip_fields if str(field).strip()]
        if fields:
            user = f"{_trim_instruction(focus_line, fields)}\n\n{user}"
        return await self.client.structured(
            MEETING_UNDERSTANDING_SYSTEM_PROMPT,
            user,
            MeetingUnderstanding,
            MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
            label="core/meeting_understanding",
        )

