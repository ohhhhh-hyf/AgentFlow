from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields as dc_fields

from infra.llm import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_SYSTEM_PROMPT,
)
from .contracts import (
    MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
    build_core_contract_for_tasks,
)


def _trim_instruction(focus_line: str, skip_fields: Iterable[str]) -> str:
    """裁剪指令：放在用户消息最前，让模型先看到再读原文。

    两张名单都按契约字段动态生成——「可空」= 本次跳过的字段，「必须写全」=
    契约字段减去跳过项——避免各写一份名单时互相矛盾（曾出现 risk_hints 同时
    被列为「可空」和「必须写全」）。字段顺序取契约声明序，保证同输入复跑稳定。
    无可跳过的字段时返回空串，由调用方决定不拼接。
    """
    order = [field.name for field in dc_fields(MeetingUnderstanding)]
    skipped = {str(field).strip() for field in skip_fields if str(field).strip()}
    if not skipped:
        return ""
    blank = [name for name in order if name in skipped]
    extra_blank = [name for name in sorted(skipped) if name not in blank]
    all_blank = blank + extra_blank
    keep = [name for name in order if name not in skipped]
    return (
        "【本次输出裁剪】\n"
        f"本次会议理解仅供 {focus_line or '本任务'} 线使用。"
        f"以下字段**键名必须保留、值给空数组 []**：{'、'.join(all_blank)}（不要省略键名）。\n"
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
        active_tasks: Iterable[str] | None = None,
        template_text: str = "",
        memory_on: bool = False,
        focus_line: str = "",
        skip_fields: Iterable[str] = (),
        user_channel: str = "",
    ) -> MeetingUnderstanding:
        """运行会议理解抽取。

        根据 active_tasks 动态组装输出契约，不抽取的字段由底层自动补齐默认空值，
        避免强制模型生成冗余空数组带来的输出延时与 Token 消耗。
        """
        tasks = list(active_tasks) if active_tasks is not None else ([focus_line] if focus_line else None)
        contract_str, omitted = build_core_contract_for_tasks(
            tasks,
            template_text=template_text,
            memory_on=memory_on,
        )

        # 组织用户消息：原文及裁剪指令、用户信道
        if len(transcript) > 45000:
            sampled_text = (
                transcript[:26000]
                + "\n\n...[超长会议中段讨论，此处略去部分细节发言]...\n\n"
                + transcript[-18000:]
            )
            user = f"会议原文：\n{sampled_text}"
        else:
            user = f"会议原文：\n{transcript}"

        if (user_channel or "").strip():
            user = f"{user_channel.strip()}\n\n{user}"

        instruction = _trim_instruction(focus_line, skip_fields)
        if instruction:
            user = f"{instruction}\n\n{user}"

        skipped = {
            str(field).strip() for field in skip_fields if str(field).strip()
        }
        missable = skipped | {"speakers"}
        if omitted:
            missable = missable | omitted

        target_contract = contract_str if active_tasks is not None else (
            contract_str if omitted else MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT
        )

        result = await self.client.structured(
            MEETING_UNDERSTANDING_SYSTEM_PROMPT,
            user,
            MeetingUnderstanding,
            target_contract,
            label="core/meeting_understanding",
            allow_missing=missable,
        )

        # 双向兼容投影：时序分段与旧版议题相互保真映射
        if hasattr(result, "session_segments") and hasattr(result, "topics"):
            if result.session_segments and not result.topics:
                result.topics = [
                    {
                        "module": str(seg.get("segment_title") or "").strip(),
                        "title": str(seg.get("segment_title") or "").strip(),
                        "discussion": str(seg.get("context_and_reasoning") or "").strip(),
                        "context_and_debate": str(seg.get("context_and_reasoning") or "").strip(),
                        "key_points": [str(f) for f in (seg.get("key_facts") or []) if str(f).strip()],
                        "debates": [],
                        "conclusion": "",
                        "participants": [],
                    }
                    for seg in result.session_segments
                    if isinstance(seg, dict)
                ]
            elif result.topics and not result.session_segments:
                result.session_segments = [
                    {
                        "segment_title": str(top.get("module") or top.get("title") or "").strip(),
                        "context_and_reasoning": str(top.get("context_and_debate") or top.get("discussion") or "").strip(),
                        "key_facts": [str(p) for p in (top.get("key_points") or top.get("key_metrics") or []) if str(p).strip()],
                    }
                    for top in result.topics
                    if isinstance(top, dict)
                ]

            # 辩论/争议交锋双向兼容
            if hasattr(result, "debates") and not result.debates and result.topics:
                top_debates = []
                for t in result.topics:
                    if isinstance(t, dict):
                        for d in (t.get("debates") or []):
                            if isinstance(d, dict) and d not in top_debates:
                                top_debates.append(d)
                if top_debates:
                    result.debates = top_debates

        return result
