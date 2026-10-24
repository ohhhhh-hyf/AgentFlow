from __future__ import annotations

from infra.llm import LLMClient
from core.execution.hard_execution import (
    enforce_minutes_draft,
    extract_labeled_json,
    is_agenda_enhanced_mode,
    parse_perspective_mode,
    parse_lang_mode,
)
from ....models import Minutes
from ..prompts import (
    KEYPOINTS_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    NOTES_PROMPT_BLOCK,
    VISION_PROMPT_BLOCK,
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

    async def run(self, shared_context: str, *, lang: str | None = None) -> Minutes:
        mode = parse_perspective_mode(shared_context)
        is_agenda = is_agenda_enhanced_mode(shared_context)
        if is_agenda:
            raw_system_prompt = MINUTES_AGENDA_GENERATION_PROMPT
            label_mode = "agenda"
        elif mode == "personal":
            raw_system_prompt = MINUTES_PERSONAL_GENERATION_PROMPT
            label_mode = "personal"
        else:
            raw_system_prompt = MINUTES_OBJECTIVE_GENERATION_PROMPT
            label_mode = "objective"

        aux_blocks = []
        if "【用户核心关键点】" in shared_context:
            aux_blocks.append(KEYPOINTS_PROMPT_BLOCK)
        if "【用户划线原话与笔记】" in shared_context:
            aux_blocks.append(NOTES_PROMPT_BLOCK)
        if "【视觉信息参考(OCR)】" in shared_context:
            aux_blocks.append(VISION_PROMPT_BLOCK)

        if aux_blocks:
            raw_system_prompt = raw_system_prompt + "\n\n" + "\n\n".join(aux_blocks)

        lang_val = lang or parse_lang_mode(shared_context)
        if (lang_val or "").strip().lower() == "en":
            role_prefix = "英文（English）"
            body_prompt = raw_system_prompt
            first_period = body_prompt.find("。\n")
            if first_period > 0:
                body_prompt = body_prompt[first_period + 2 :].strip()
            system_prompt = (
                f"【核心人设与交付目标】\n"
                f"你是专职的【{role_prefix}】会议纪要草稿 Agent，本次任务必须全程直接提炼并输出标准、专业、精炼的商务{role_prefix}结构化草稿。\n\n"
                f"{body_prompt}\n\n"
                f"## 语言红线\n"
                f"1. 所有字段必须严格使用【{role_prefix}】输出，严禁夹杂中文字符与全角标点；\n"
                f"2. 待定/未决统一使用 [TBD] 或 [Pending Confirmation]，严禁输出 [待确认]；\n"
                f"3. 专业术语、专有名词与人名保留英文原文写法；\n"
                f"4. 执行要点统一采用 `[Owner] Action + Deliverable + Deadline` 结构清晰陈述。"
            )
        else:
            system_prompt = raw_system_prompt

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
            lang=lang_val,
        )
        return Minutes.validate(enforced)

