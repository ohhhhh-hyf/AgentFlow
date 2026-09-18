from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields as dc_fields

from client import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_SYSTEM_PROMPT,
)
from .contracts import MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT


def _trim_instruction(focus_line: str, skip_fields: Iterable[str]) -> str:
    """裁剪指令：放在用户消息最前，让模型先看到再读原文。

    两张名单都按契约字段动态生成——「可空」= 本次跳过的字段，「必须写全」=
    契约字段减去跳过项——避免各写一份名单时互相矛盾（曾出现 risk_hints 同时
    被列为「可空」和「必须写全」）。字段顺序取契约声明序，保证同输入复跑稳定。
    无可跳过的字段时返回空串，由调用方决定不拼接。
    """
    order = [field.name for field in dc_fields(MeetingUnderstanding)]
    skipped = {str(field).strip() for field in skip_fields if str(field).strip()}
    blank = [name for name in order if name in skipped]
    keep = [name for name in order if name not in skipped]
    if not blank:
        return ""
    return (
        "【本次输出裁剪】\n"
        f"本次会议理解仅供 {focus_line or '本任务'} 线使用。"
        f"以下字段**键名必须保留、值给空数组 []**：{'、'.join(blank)}（不要省略键名）。\n"
        f"除上述字段外，其余字段（{'、'.join(keep)}）必须照常按会议原文完整、准确输出，"
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
        instruction = _trim_instruction(focus_line, skip_fields)
        if instruction:
            user = f"{instruction}\n\n{user}"
        skipped = {
            str(field).strip() for field in skip_fields if str(field).strip()
        }
        # speakers 常年为空（原文本来就没有姓名）→ 缺键不该触发重试：提示词仍要求它照常输出，
        # 但校验侧允许缺键补 []（与裁剪字段同一条经验：2026-09-18 实测 risk_hints，缺键 +20s）。
        missable = skipped | {"speakers"}
        return await self.client.structured(
            MEETING_UNDERSTANDING_SYSTEM_PROMPT,
            user,
            MeetingUnderstanding,
            MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
            label="core/meeting_understanding",
            # 裁剪字段允许缺键：模型常把"输出 []"理解成"整个键不用写"，缺键会让严格校验
            # 失败并白跑一次针对性重试（2026-09-18 实测 risk_hints，+20s）
            allow_missing=missable,
        )

