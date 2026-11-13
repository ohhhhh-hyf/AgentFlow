"""前置智能模板分类器 (零旧代码依赖).

核心能力:
1. 12k 字符采样截断 (前 6k + 中 2k + 尾 4k), 保证快速响应 (耗时 ~1s);
2. 必选前置步骤, 区分议题模式 (20 个候选) 与普通模式 (29 个候选);
3. 纯原生调用 LLMClient.chat_json, 异常与低置信度 (< 0.70) 统一安全兜底 general_minutes.
"""
from __future__ import annotations

import logging
from typing import Any

from infra.llm.client import LLMClient
from .catalog import (
    build_classifier_system_prompt,
    build_classifier_user_message,
    candidate_ids_for_mode,
)

logger = logging.getLogger("tasks.minutes.classifier")

TEMPLATE_AUTO_FULL_LIMIT = 12_000
TEMPLATE_AUTO_HEAD_CHARS = 6_000
TEMPLATE_AUTO_MIDDLE_CHARS = 2_000
TEMPLATE_AUTO_TAIL_CHARS = 4_000
MIN_VALID_LENGTH = 80


def sample_transcript(text: str) -> str:
    """对超长文本进行 12k 采样截断, 兼顾开篇背景、中期研讨与末期定调."""
    s = (text or "").strip()
    if len(s) <= TEMPLATE_AUTO_FULL_LIMIT:
        return s

    head = s[:TEMPLATE_AUTO_HEAD_CHARS]
    mid_start = max(TEMPLATE_AUTO_HEAD_CHARS, len(s) // 2 - TEMPLATE_AUTO_MIDDLE_CHARS // 2)
    middle = s[mid_start : mid_start + TEMPLATE_AUTO_MIDDLE_CHARS]
    tail = s[-TEMPLATE_AUTO_TAIL_CHARS:]
    return f"{head}\n\n...[中间内容截断]...\n\n{middle}\n\n...[中间内容截断]...\n\n{tail}"


class TemplateClassifier:
    """前置智能模板分类器."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.client = llm_client or LLMClient()

    async def classify(
        self,
        transcript: str,
        agenda_text: str = "",
        has_agenda: bool = False,
    ) -> str:
        """执行智能分类, 返回匹配的模板 ID (如 'general_minutes').

        Args:
            transcript: 会议现场实录
            agenda_text: 议程文本 (若有)
            has_agenda: 是否为议程模式 (决定选用 20 个还是 29 个候选集)
        """
        text = (transcript or "").strip()
        if len(text) < MIN_VALID_LENGTH:
            logger.info("[Classifier] 文本长度不足 (%d < %d), 直接兜底 general_minutes", len(text), MIN_VALID_LENGTH)
            return "general_minutes"

        sampled = sample_transcript(text)
        sys_prompt = build_classifier_system_prompt(has_agenda=has_agenda)
        user_msg = build_classifier_user_message(sampled, agenda_text=agenda_text)
        allowed = set(candidate_ids_for_mode(has_agenda=has_agenda))

        try:
            res: dict[str, Any] = await self.client.chat_json(
                system_prompt=sys_prompt,
                user_prompt=user_msg,
                temperature=0.0,
                max_tokens=64,
                timeout=15.0,
            )
            tpl = str(res.get("template") or "").strip().lower()
            conf = float(res.get("confidence") or 0.0)

            logger.info("[Classifier] 识别结果: template=%s, confidence=%.2f, has_agenda=%s", tpl, conf, has_agenda)

            if tpl in allowed and conf >= 0.70:
                return tpl

            logger.info("[Classifier] 未满足置信度或模板无效 (tpl=%r, conf=%.2f), 兜底 general_minutes", tpl, conf)
            return "general_minutes"

        except Exception as exc:
            logger.warning("[Classifier] 智能分类调用异常 (%s), 安全兜底 general_minutes", exc)
            return "general_minutes"


async def classify_template(
    transcript: str,
    agenda_text: str = "",
    is_agenda: bool = False,
    llm_client: LLMClient | None = None,
) -> tuple[str, float]:
    """便捷分类函数，返回 (template_id, confidence)。"""
    classifier = TemplateClassifier(llm_client=llm_client)
    res = await classifier.classify(transcript, agenda_text=agenda_text, has_agenda=is_agenda)
    return res, 1.0

