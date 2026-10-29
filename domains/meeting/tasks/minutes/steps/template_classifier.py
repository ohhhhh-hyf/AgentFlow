"""场景识别 Agent 的纯函数层：短会判断、采样、解析、归一化、后处理。

本模块不调用 LLM、不依赖 graph，便于单独测试。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

from domains.meeting.domain_config import TEMPLATE_AUTO_SHORT_CHARS

from .scene_catalog import (
    TEMPLATE_CLASSIFIER_PROMPT_VERSION,
    build_system_prompt,
    build_user_message,
)

logger = logging.getLogger(__name__)

# 采样参数：与执行清单一致
TEMPLATE_AUTO_FULL_LIMIT = 12_000
TEMPLATE_AUTO_HEAD_CHARS = 6_000
TEMPLATE_AUTO_MIDDLE_CHARS = 2_000
TEMPLATE_AUTO_TAIL_CHARS = 4_000
TEMPLATE_AUTO_CONFIDENCE_THRESHOLD = 0.70
GENERAL_TEMPLATE_ID = "general_minutes"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class TemplateDecision:
    """后处理结果；template 始终是最终可用的模板 ID。"""

    template: str
    confidence: float | None
    accepted: bool
    action: str
    reason: str
    mode: str
    raw_template: str | None = None
    raw_confidence: float | None = None


@dataclass(frozen=True)
class ClassifierRunResult:
    """一次分类调用的原始结果（不做阈值/候选集后处理）。"""

    ok: bool
    skipped: bool
    parsed: dict[str, Any] | None
    raw_output: str
    error: str | None
    duration: float


class TemplateClassifierAgent:
    """隔离的 LLM 分类 Agent：只负责一次调用与解析，不依赖 graph。"""

    def __init__(
        self,
        client: Any,
        *,
        timeout: float = 15.0,
        max_tokens: int = 128,
    ) -> None:
        self.client = client
        self.timeout = timeout
        self.max_tokens = max_tokens

    async def run(
        self,
        transcript: str,
        agenda_text: str,
        candidates: Iterable[str] | None,
        lang: str = "zh",
    ) -> ClassifierRunResult:
        """调用一次 LLM，返回 {template, confidence} 或失败结果。"""
        started = time.monotonic()
        text = transcript or ""
        if should_skip_by_length(text):
            duration = time.monotonic() - started
            logger.info(
                "[template:auto:agent:skip] reason=short_text chars=%d duration=%.2fs",
                len(text.strip()),
                duration,
            )
            return ClassifierRunResult(
                ok=False,
                skipped=True,
                parsed=None,
                raw_output="",
                error="short_text",
                duration=duration,
            )

        candidate_ids = tuple(candidates or ())
        if not candidate_ids:
            duration = time.monotonic() - started
            logger.warning("[template:auto:agent:invalid] reason=no_candidates")
            return ClassifierRunResult(
                ok=False,
                skipped=False,
                parsed=None,
                raw_output="",
                error="no_candidates",
                duration=duration,
            )

        try:
            system_prompt = build_system_prompt(candidate_ids)
            user_prompt = build_user_message(
                sample_transcript(text),
                agenda_text=agenda_text,
            )
        except Exception as exc:  # noqa: BLE001 - 纯数据异常也应回退
            duration = time.monotonic() - started
            logger.warning(
                "[template:auto:agent:invalid] reason=build_prompt error=%s",
                type(exc).__name__,
            )
            return ClassifierRunResult(
                ok=False,
                skipped=False,
                parsed=None,
                raw_output="",
                error=f"build_prompt:{type(exc).__name__}",
                duration=duration,
            )

        try:
            raw = await self.client.text(
                system_prompt,
                user_prompt,
                temperature=0.0,
                json_mode=True,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                label="minutes/template_classify",
            )
        except Exception as exc:  # noqa: BLE001 - 分类失败由调用方回退
            duration = time.monotonic() - started
            logger.warning(
                "[template:auto:agent:invalid] reason=call_error error=%s duration=%.2fs",
                type(exc).__name__,
                duration,
            )
            return ClassifierRunResult(
                ok=False,
                skipped=False,
                parsed=None,
                raw_output="",
                error=f"call_error:{type(exc).__name__}",
                duration=duration,
            )

        duration = time.monotonic() - started
        raw_text = str(raw or "")
        parsed = parse_classifier_output(raw_text)
        if parsed is None:
            logger.warning(
                "[template:auto:agent:invalid] raw=%s duration=%.2fs",
                raw_text.replace("\n", " ")[:200],
                duration,
            )
            return ClassifierRunResult(
                ok=False,
                skipped=False,
                parsed=None,
                raw_output=raw_text,
                error="invalid_output",
                duration=duration,
            )

        logger.info(
            "[template:auto:agent] raw_template=%s raw_confidence=%s "
            "candidates=%d prompt_version=%s duration=%.2fs",
            parsed["template"],
            parsed["confidence"],
            len(candidate_ids),
            TEMPLATE_CLASSIFIER_PROMPT_VERSION,
            duration,
        )
        return ClassifierRunResult(
            ok=True,
            skipped=False,
            parsed=parsed,
            raw_output=raw_text,
            error=None,
            duration=duration,
        )


def should_skip_by_length(
    transcript: str,
    *,
    threshold: int = TEMPLATE_AUTO_SHORT_CHARS,
) -> bool:
    """短会放行：去首尾空白后字符数 < 阈值。"""
    return len((transcript or "").strip()) < threshold


def _snap_head(text: str, pos: int, window: int = 500) -> int:
    """尽量在 pos 前最近的换行处切头；找不到就按 pos。"""
    start = max(0, pos - window)
    nl = text.rfind("\n", start, pos)
    return nl + 1 if nl >= 0 else pos


def _snap_tail(text: str, pos: int, window: int = 500) -> int:
    """尽量在 pos 后最近的换行处切尾；找不到就按 pos。"""
    end = min(len(text), pos + window)
    nl = text.find("\n", pos, end)
    return nl + 1 if nl >= 0 else pos


def sample_transcript(
    transcript: str,
    *,
    full_limit: int = TEMPLATE_AUTO_FULL_LIMIT,
    head_chars: int = TEMPLATE_AUTO_HEAD_CHARS,
    middle_chars: int = TEMPLATE_AUTO_MIDDLE_CHARS,
    tail_chars: int = TEMPLATE_AUTO_TAIL_CHARS,
) -> str:
    """按“头 + 中 + 尾”裁剪长文本；2000–12000 字直接返回全文。

    三段严格来自原文的不重叠切片；中间段居中取样，尽量落在换行处。
    """
    text = transcript or ""
    if len(text) <= full_limit:
        return text

    head_end = _snap_head(text, min(head_chars, len(text)))
    tail_start = _snap_tail(text, max(head_end, len(text) - tail_chars))
    tail_start = max(head_end, min(tail_start, len(text)))

    head = text[:head_end]
    tail = text[tail_start:]
    pool = text[head_end:tail_start]

    if len(pool) <= middle_chars:
        middle = pool
    else:
        start = (len(pool) - middle_chars) // 2
        nl = pool.find("\n", start, start + 200)
        if nl >= 0:
            start = nl + 1
        middle = pool[start : start + middle_chars]

    parts: list[str] = []
    if head.strip():
        parts.append(head.strip())
    if middle.strip():
        parts.append("【中段节选】\n" + middle.strip())
    if tail.strip():
        parts.append("【结尾】\n" + tail.strip())
    return "\n\n".join(parts)


def parse_classifier_output(raw: Any) -> dict[str, Any] | None:
    """解析 Agent 输出；非法结构返回 None。

    接受 dict 或 JSON 字符串（允许外层 ```json 围栏/前后少量说明文字）。
    只接受 template 非空字符串、confidence 为 0~1 的数字（bool 不算数字）。
    """
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        text = _JSON_FENCE_RE.sub("", raw.strip()).strip()
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except (TypeError, ValueError):
                return None
    else:
        return None

    if not isinstance(data, dict):
        return None
    template = data.get("template")
    confidence = data.get("confidence")
    if not isinstance(template, str) or not template.strip():
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        return None
    return {"template": template.strip(), "confidence": confidence}


def normalize_template_id(
    raw: str | None,
    candidate_ids: Iterable[str],
) -> str | None:
    """归一化模板 ID：去空白、转小写、去 .md，并校验候选集。"""
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    if value.endswith(".md"):
        value = value[:-3].strip()
    return value if value in set(candidate_ids) else None


def postprocess(
    result: Any,
    candidate_ids: Iterable[str],
    mode: str = "normal",
    *,
    threshold: float = TEMPLATE_AUTO_CONFIDENCE_THRESHOLD,
    general_id: str = GENERAL_TEMPLATE_ID,
) -> TemplateDecision:
    """把 Agent 输出变成最终决策；任何异常都回退 general_minutes。"""
    mode = (mode or "normal").strip().lower()
    candidates = set(candidate_ids)
    parsed = parse_classifier_output(result)
    if parsed is None:
        return TemplateDecision(
            template=general_id,
            confidence=None,
            accepted=False,
            action="fallback",
            reason="invalid_output",
            mode=mode,
        )

    raw_template = parsed["template"]
    raw_confidence = parsed["confidence"]
    normalized = normalize_template_id(raw_template, candidates)
    if normalized is None:
        return TemplateDecision(
            template=general_id,
            confidence=raw_confidence,
            accepted=False,
            action="fallback",
            reason="not_in_candidates",
            mode=mode,
            raw_template=raw_template,
            raw_confidence=raw_confidence,
        )
    if normalized == general_id:
        return TemplateDecision(
            template=general_id,
            confidence=raw_confidence,
            accepted=False,
            action="fallback",
            reason="general",
            mode=mode,
            raw_template=raw_template,
            raw_confidence=raw_confidence,
        )
    if raw_confidence < threshold:
        return TemplateDecision(
            template=general_id,
            confidence=raw_confidence,
            accepted=False,
            action="fallback",
            reason="low_confidence",
            mode=mode,
            raw_template=raw_template,
            raw_confidence=raw_confidence,
        )
    return TemplateDecision(
        template=normalized,
        confidence=raw_confidence,
        accepted=True,
        action="use",
        reason="none",
        mode=mode,
        raw_template=raw_template,
        raw_confidence=raw_confidence,
    )


__all__ = [
    "ClassifierRunResult",
    "GENERAL_TEMPLATE_ID",
    "TEMPLATE_AUTO_CONFIDENCE_THRESHOLD",
    "TEMPLATE_AUTO_FULL_LIMIT",
    "TEMPLATE_AUTO_HEAD_CHARS",
    "TEMPLATE_AUTO_MIDDLE_CHARS",
    "TEMPLATE_AUTO_SHORT_CHARS",
    "TEMPLATE_AUTO_TAIL_CHARS",
    "TEMPLATE_CLASSIFIER_PROMPT_VERSION",
    "TemplateClassifierAgent",
    "TemplateDecision",
    "normalize_template_id",
    "parse_classifier_output",
    "postprocess",
    "sample_transcript",
    "should_skip_by_length",
]
