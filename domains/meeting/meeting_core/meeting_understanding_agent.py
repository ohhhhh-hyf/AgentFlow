from __future__ import annotations

from collections.abc import Iterable

from infra.llm import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_SYSTEM_PROMPT,
    MEETING_UNDERSTANDING_LIGHTWEIGHT_SYSTEM_PROMPT,
)
from .contracts import (
    MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
    build_core_contract_for_tasks,
    is_actions_risks_only_tasks,
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

        # 组织用户消息：原文及用户信道
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

        missable = {"speakers"}
        if omitted:
            missable = missable | omitted

        target_contract = contract_str if active_tasks is not None else (
            contract_str if omitted else MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT
        )

        is_lightweight = is_actions_risks_only_tasks(tasks, memory_on=memory_on)
        system_prompt = (
            MEETING_UNDERSTANDING_LIGHTWEIGHT_SYSTEM_PROMPT
            if is_lightweight
            else MEETING_UNDERSTANDING_SYSTEM_PROMPT
        )

        result = await self.client.structured(
            system_prompt,
            user,
            MeetingUnderstanding,
            target_contract,
            label="core/meeting_understanding",
            allow_missing=missable,
        )

        # 兼容老数据输入：若仅有旧版 topics 则投影至 session_segments
        if hasattr(result, "session_segments") and hasattr(result, "topics"):
            if result.topics and not result.session_segments:
                result.session_segments = [
                    {
                        "segment_title": str(top.get("module") or top.get("title") or "").strip(),
                        "context_and_reasoning": str(top.get("context_and_debate") or top.get("discussion") or "").strip(),
                        "key_facts": [str(p) for p in (top.get("key_points") or top.get("key_metrics") or []) if str(p).strip()],
                    }
                    for top in result.topics
                    if isinstance(top, dict)
                ]

            # 辩论/争议交锋兼容
            if hasattr(result, "debates") and not result.debates and result.topics:
                top_debates = []
                for t in result.topics:
                    if isinstance(t, dict):
                        for d in (t.get("debates") or []):
                            if isinstance(d, dict) and d not in top_debates:
                                top_debates.append(d)
                if top_debates:
                    result.debates = top_debates

            # 彻底拔除 topics，避免克隆膨胀
            result.topics = []

        return result
