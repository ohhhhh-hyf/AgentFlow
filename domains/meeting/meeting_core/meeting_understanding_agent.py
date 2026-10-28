from __future__ import annotations

from collections.abc import Iterable

from infra.llm import LLMClient
from ..models import MeetingUnderstanding
from .prompts import (
    MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
    build_understanding_prompt,
)
from .contracts import build_core_contract_for_tasks
from .understanding_profiles import resolve_profile


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
        is_agenda_enhanced: bool = False,
        lang: str = "zh",
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

        target_contract = contract_str

        profile = resolve_profile(
            tasks,
            memory_on=memory_on,
            is_agenda=is_agenda_enhanced,
        )
        task = tasks[0] if tasks and len(tasks) == 1 else ""
        if profile is None:
            # 议题兼容分支：继续使用旧议题 prompt。
            raw_system_prompt = MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT
        else:
            raw_system_prompt = build_understanding_prompt(profile, task=task)

        if (lang or "").strip().lower() == "en":
            role_prefix = "英文（English）"
            # 拆出首句，保留主体规则
            body_prompt = raw_system_prompt
            first_period = body_prompt.find("。\n")
            if first_period > 0:
                body_prompt = body_prompt[first_period + 2 :].strip()
            system_prompt = (
                f"【核心人设与交付目标】\n"
                f"你是专职的【{role_prefix}】会议理解助手，本次任务必须全程直接提取并产出客观、高密度的结构化{role_prefix}事实底座，供下游任务复用。\n\n"
                f"{body_prompt}\n\n"
                f"## 语言红线\n"
                f"1. 所有字段必须严格使用【{role_prefix}】输出，严禁夹杂中文字符；\n"
                f"2. 专业术语、项目简称、人名保留英文原文写法，不得翻译或脑补。"
            )
        else:
            system_prompt = raw_system_prompt

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

            # 彻底拔除 topics，避免克隆膨胀
            result.topics = []

        return result
