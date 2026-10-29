"""场景识别 Agent 的图内编排：分类 → 后处理 → 模板物化 → 状态回写。

Stage 5 只在此处消费 Stage 4 透传的状态；开关为 ``off`` 或
``template_auto=False`` 时节点不做任何改动。
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace
from typing import Any

from domains.meeting.domain_config import minutes_template_auto_mode

from .scene_catalog import TEMPLATE_CLASSIFIER_PROMPT_VERSION, candidate_ids_for_mode
from .template_classifier import (
    GENERAL_TEMPLATE_ID,
    TemplateClassifierAgent,
    TemplateDecision,
    postprocess,
    should_skip_by_length,
)

logger = logging.getLogger(__name__)

MODE_ON = "on"


def _mode_of(state: dict, agenda_text: str) -> str:
    """场景模式以 API 判定为准；缺失时按 agenda_text 兜底。"""
    mode = str(state.get("template_mode") or "").strip().lower()
    if mode == "agenda":
        return "agenda"
    if agenda_text:
        return "agenda"
    return "normal"


def _final_template_id(state: dict) -> str:
    return str(state.get("template_id") or "").strip() or GENERAL_TEMPLATE_ID


def _skip_reason(state: dict) -> str:
    source = str(state.get("template_source") or "").strip().lower()
    if source == "explicit":
        return "explicit_template"
    if source == "personal_default":
        return "personal_profile"
    return "switch_off"


def _decision_payload(
    decision: TemplateDecision,
    *,
    applied: bool,
    source: str,
    duration: float,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "template": decision.template,
        "confidence": decision.confidence,
        "accepted": decision.accepted,
        "action": decision.action,
        "reason": reason or decision.reason,
        "mode": decision.mode,
        "raw_template": decision.raw_template,
        "raw_confidence": decision.raw_confidence,
        "applied": applied,
        "source": source,
        "duration": round(duration, 2),
        "prompt_version": TEMPLATE_CLASSIFIER_PROMPT_VERSION,
    }


def _log_decision(
    decision: TemplateDecision,
    candidates: int,
    *,
    reason: str | None = None,
) -> None:
    logger.info(
        "[template:auto:decision] template=%s confidence=%s action=%s "
        "reason=%s candidate_count=%d mode=%s",
        decision.template,
        decision.confidence,
        decision.action,
        reason or decision.reason,
        candidates,
        decision.mode,
    )


def resolve_template_text(template_id: str, mode: str, lang: str = "zh") -> str:
    """模板 ID → 模板文本（普通 / 议题目录）。空文本表示物化失败。"""
    from app.config import (
        resolve_agenda_template_format,
        resolve_template_format,
    )

    resolver = (
        resolve_agenda_template_format
        if (mode or "").strip().lower() == "agenda"
        else resolve_template_format
    )
    return str(resolver(template_id, lang=lang) or "").strip()


async def materialize_template(
    template_id: str,
    mode: str,
    *,
    lang: str = "zh",
    client: Any = None,
) -> str:
    """加载模板；natural 模板复用 prepare_run 的二次编译。异常返回空串。"""
    try:
        text = resolve_template_text(template_id, mode, lang)
    except Exception:  # noqa: BLE001 - 物化失败不阻塞，保留兜底模板
        logger.warning(
            "[template:auto:materialize] template_id=%s mode=%s "
            "action=fallback reason=resolve_error source=auto_fallback",
            template_id,
            mode,
            exc_info=True,
        )
        return ""
    if not text:
        return ""

    from core.templates.router import (
        LINE_SCHEMA_HINTS,
        maybe_compile_natural_template,
    )

    text = await maybe_compile_natural_template(
        text,
        domain="meeting",
        line_name="minutes",
        schema_hint=LINE_SCHEMA_HINTS.get("minutes", ""),
        client=client,
    )
    return str(text or "").strip()


def _log_materialized(
    template_id: str,
    mode: str,
    text: str,
    *,
    duration: float,
) -> None:
    fingerprint = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    logger.info(
        "[template:auto:materialize] template_id=%s mode=%s template_chars=%d "
        "template_fingerprint=%s source=auto duration=%.2fs",
        template_id,
        mode,
        len(text),
        fingerprint,
        duration,
    )


def _fallback_result(
    state: dict,
    decision: TemplateDecision,
    candidates: int,
    *,
    mode: str,
    reason: str,
    duration: float,
    apply_source: bool,
) -> dict:
    """回退 general_minutes：保留兜底模板，只补观测字段。"""
    _log_decision(decision, candidates, reason=reason)
    final_id = _final_template_id(state)
    source = "auto_fallback" if apply_source else str(
        state.get("template_source") or ""
    )
    logger.info(
        "[template:auto:done] final_template=%s template_source=%s "
        "template_mode=%s confidence=%s reason=%s total_duration=%.2fs",
        final_id,
        source,
        mode,
        decision.confidence,
        reason,
        duration,
    )
    update: dict = {
        "template_decision": _decision_payload(
            decision,
            applied=False,
            source=source,
            duration=duration,
            reason=reason,
        ),
        "template_mode": mode,
    }
    if apply_source:
        update["template_id"] = final_id
        update["template_source"] = source
    return update


async def select_minutes_template(
    state: dict,
    *,
    client: Any = None,
    agent: Any = None,
) -> dict:
    """图内前置节点：仅在自动模式下分类并（on 时）替换 minutes 模板。"""
    started = time.monotonic()
    if not state.get("template_auto"):
        logger.info(
            "[template:auto:skip] reason=%s final_template=%s",
            _skip_reason(state),
            _final_template_id(state),
        )
        return {}

    transcript = str(state.get("transcript") or "")
    agenda_text = str((state.get("line_extra") or {}).get("agenda_text") or "").strip()
    mode = _mode_of(state, agenda_text)
    final_id = _final_template_id(state)
    switch = minutes_template_auto_mode()
    if switch == "off":
        # 防御：API 层在 off 时不会置 template_auto=True，但图也可能被直接调用。
        logger.info(
            "[template:auto:skip] reason=switch_off final_template=%s", final_id
        )
        return {}
    apply_result = switch == MODE_ON

    # 短会：不调用 Agent，保留兜底模板
    if should_skip_by_length(transcript):
        logger.info(
            "[template:auto:skip] reason=short_text transcript_chars=%d "
            "final_template=%s",
            len(transcript.strip()),
            final_id,
        )
        decision = TemplateDecision(
            template=final_id,
            confidence=None,
            accepted=False,
            action="skip",
            reason="short_text",
            mode=mode,
        )
        return {
            "template_decision": _decision_payload(
                decision,
                applied=False,
                source=str(state.get("template_source") or ""),
                duration=time.monotonic() - started,
            )
        }

    candidates = candidate_ids_for_mode(mode)
    logger.info(
        "[template:auto:start] mode=%s candidates=%d transcript_chars=%d "
        "agenda=%d prompt_version=%s switch=%s",
        mode,
        len(candidates),
        len(transcript.strip()),
        int(bool(agenda_text)),
        TEMPLATE_CLASSIFIER_PROMPT_VERSION,
        switch,
    )

    agent_obj = agent or TemplateClassifierAgent(client)
    try:
        result = await agent_obj.run(
            transcript,
            agenda_text,
            candidates,
            lang=str(state.get("lang") or "zh"),
        )
    except Exception:  # noqa: BLE001 - 分类失败不阻塞主流程
        logger.warning("[template:auto:agent:invalid] reason=call_error", exc_info=True)
        decision = TemplateDecision(
            template=final_id,
            confidence=None,
            accepted=False,
            action="fallback",
            reason="error",
            mode=mode,
        )
        return _fallback_result(
            state,
            decision,
            len(candidates),
            mode=mode,
            reason="error",
            duration=time.monotonic() - started,
            apply_source=apply_result,
        )

    if getattr(result, "skipped", False):
        logger.info(
            "[template:auto:skip] reason=short_text transcript_chars=%d "
            "final_template=%s",
            len(transcript.strip()),
            final_id,
        )
        decision = TemplateDecision(
            template=final_id,
            confidence=None,
            accepted=False,
            action="skip",
            reason="short_text",
            mode=mode,
        )
        return {
            "template_decision": _decision_payload(
                decision,
                applied=False,
                source=str(state.get("template_source") or ""),
                duration=time.monotonic() - started,
            )
        }

    if getattr(result, "ok", False):
        decision = postprocess(
            result.parsed,
            candidates,
            mode=mode,
        )
    else:
        reason = "invalid_output" if result.error == "invalid_output" else "error"
        decision = TemplateDecision(
            template=final_id,
            confidence=None,
            accepted=False,
            action="fallback",
            reason=reason,
            mode=mode,
        )

    if not decision.accepted:
        return _fallback_result(
            state,
            decision,
            len(candidates),
            mode=mode,
            reason=decision.reason,
            duration=time.monotonic() - started,
            apply_source=apply_result,
        )

    # shadow：只记录决策，绝不覆盖模板
    if not apply_result:
        _log_decision(decision, len(candidates))
        logger.info(
            "[template:auto:done] final_template=%s template_source=%s "
            "template_mode=%s confidence=%s shadow=1 total_duration=%.2fs",
            final_id,
            str(state.get("template_source") or ""),
            mode,
            decision.confidence,
            time.monotonic() - started,
        )
        return {
            "template_decision": _decision_payload(
                decision,
                applied=False,
                source=str(state.get("template_source") or ""),
                duration=time.monotonic() - started,
            ),
            "template_mode": mode,
        }

    materialize_t0 = time.monotonic()
    try:
        text = await materialize_template(
            decision.template,
            mode,
            lang=str(state.get("lang") or "zh"),
            client=client,
        )
    except Exception:  # noqa: BLE001 - 物化异常按失败处理
        logger.warning(
            "[template:auto:materialize] template_id=%s mode=%s "
            "action=fallback reason=materialize_error source=auto_fallback",
            decision.template,
            mode,
            exc_info=True,
        )
        text = ""

    if not text:
        _log_decision(decision, len(candidates), reason="empty_template")
        logger.info(
            "[template:auto:materialize] template_id=%s mode=%s "
            "action=fallback reason=empty_template source=auto_fallback",
            decision.template,
            mode,
        )
        fallback_decision = replace(
            decision,
            template=GENERAL_TEMPLATE_ID,
            accepted=False,
            action="fallback",
            reason="empty_template",
        )
        return _fallback_result(
            state,
            fallback_decision,
            len(candidates),
            mode=mode,
            reason="empty_template",
            duration=time.monotonic() - started,
            apply_source=True,
        )

    _log_materialized(
        decision.template,
        mode,
        text,
        duration=time.monotonic() - materialize_t0,
    )
    _log_decision(decision, len(candidates))
    logger.info(
        "[template:auto:done] final_template=%s template_source=auto "
        "template_mode=%s confidence=%s total_duration=%.2fs",
        decision.template,
        mode,
        decision.confidence,
        time.monotonic() - started,
    )
    templates = dict(state.get("templates") or {})
    templates["minutes"] = text
    return {
        "templates": templates,
        "template_id": decision.template,
        "template_source": "auto",
        "template_mode": mode,
        "template_decision": _decision_payload(
            decision,
            applied=True,
            source="auto",
            duration=time.monotonic() - started,
        ),
    }


__all__ = [
    "materialize_template",
    "resolve_template_text",
    "select_minutes_template",
]
