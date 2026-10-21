from __future__ import annotations

from infra.llm import LLMClient
from core.execution.hard_execution import (
    enforce_minutes_draft,
    extract_labeled_json,
    is_agenda_enhanced_mode,
    parse_perspective_mode,
)
from ....models import Minutes
from ..prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
)
from ..contracts import MINUTES_GENERATION_OUTPUT_CONTRACT


def _extract_transcript(shared_context: str) -> str:
    if not shared_context:
        return ""
    for marker in ("【会议原文】\n", "会议原文：\n", "会议原文:\n", "原文（最高事实来源）：\n", "原文（最高事实来源）:\n"):
        idx = shared_context.find(marker)
        if idx >= 0:
            rest = shared_context[idx + len(marker):]
            for end_marker in (
                "\n\n════════",
                "\n\n【目标样式模板】",
                "\n\n【会议记忆】",
                "\n\n【项目推进背景】",
                "\n\n【既定议程单】",
                "\n\n字数预算",
            ):
                end_idx = rest.find(end_marker)
                if end_idx >= 0:
                    rest = rest[:end_idx]
            return rest.strip()
    return ""


def _extract_memory_texts(shared_context: str) -> list[str]:
    if not shared_context:
        return []
    texts: list[str] = []
    in_mem_section = False
    for line in shared_context.splitlines():
        s = line.strip()
        if any(sec in s for sec in ("【项目推进背景】", "【延续事项】", "【历史决策】", "【风险演变】", "【已闭环】")):
            in_mem_section = True
            continue
        if in_mem_section and (s.startswith("════════") or (s.startswith("【") and "】" in s)):
            if not any(sec in s for sec in ("【项目推进背景】", "【延续事项】", "【历史决策】", "【风险演变】", "【已闭环】")):
                in_mem_section = False
                continue
        if in_mem_section and s.startswith("- "):
            item_text = s[2:].strip()
            p_idx = item_text.rfind("（")
            if p_idx > 0 and item_text.endswith("）"):
                item_text = item_text[:p_idx].strip()
            elif "(" in item_text and item_text.endswith(")"):
                p_idx = item_text.rfind("(")
                if p_idx > 0:
                    item_text = item_text[:p_idx].strip()
            if item_text:
                texts.append(item_text)
    return texts


class MinutesGenerationAgent:
    """基于会议理解和视角模型生成纪要草稿（个人视角或客观全员视角）。

    双轨分流架构：
    - 客观模式：挂载 MINUTES_OBJECTIVE_GENERATION_PROMPT，纯粹第三人称公文体；
    - 个人模式：挂载 MINUTES_PERSONAL_GENERATION_PROMPT，作战秘书看板体。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Minutes:
        mode = parse_perspective_mode(shared_context)
        is_agenda = is_agenda_enhanced_mode(shared_context)
        if is_agenda:
            system_prompt = MINUTES_AGENDA_GENERATION_PROMPT
            label_mode = "agenda"
        elif mode == "personal":
            system_prompt = MINUTES_PERSONAL_GENERATION_PROMPT
            label_mode = "personal"
        else:
            system_prompt = MINUTES_OBJECTIVE_GENERATION_PROMPT
            label_mode = "objective"

        raw = await self.client.structured(
            system_prompt,
            shared_context,
            Minutes,
            MINUTES_GENERATION_OUTPUT_CONTRACT,
            label=f"minutes/agent/{label_mode}",
        )
        understanding = extract_labeled_json(shared_context, "会议理解")
        perspective = extract_labeled_json(shared_context, "用户视角模型")
        transcript = _extract_transcript(shared_context)
        memory_texts = _extract_memory_texts(shared_context)
        enforced = enforce_minutes_draft(
            raw,
            understanding,
            mode=mode,
            perspective=perspective,
            memory_texts=memory_texts,
            transcript=transcript,
            is_agenda=is_agenda,
        )
        return Minutes.validate(enforced)

