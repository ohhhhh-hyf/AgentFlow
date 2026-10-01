from __future__ import annotations

from collections.abc import Iterable
from dataclasses import fields as dc_fields
from typing import Any

from infra.llm import LLMClient
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


def _ensure_derived_fields(result: MeetingUnderstanding) -> None:
    """若大模型仅在 topics 议题树中内聚输出了事实，自动由树派生出平铺视图，确保下游 100% 兼容。"""
    if not isinstance(result, MeetingUnderstanding):
        return
    topics = result.topics or []
    if not isinstance(topics, list):
        return

    derived_actions: list[dict[str, Any]] = []
    derived_risks: list[dict[str, Any]] = []
    derived_decisions: list[str] = []
    derived_open: list[str] = []

    for t in topics:
        if not isinstance(t, dict):
            continue
        topic_title = str(t.get("title") or "").strip()
        for a in (t.get("actions") or []):
            if isinstance(a, dict):
                derived_actions.append({
                    "action": a.get("task") or "",
                    "owner": a.get("owner"),
                    "timing": a.get("deadline"),
                    "condition": a.get("dependency"),
                    "topic": topic_title,
                    "kind": "directive" if a.get("priority") == "high" else "assignment",
                    "evidence": a.get("evidence") or "",
                })
        for r in (t.get("risks") or []):
            if isinstance(r, dict):
                derived_risks.append({
                    "risk": r.get("risk") or "",
                    "topic": topic_title,
                    "signal_type": "quality",
                    "severity_evidence": r.get("evidence") or "",
                    "impact": r.get("impact"),
                    "mitigation": r.get("mitigation"),
                    "owner": r.get("owner"),
                    "evidence": r.get("evidence") or "",
                })
        for d in (t.get("decisions") or []):
            if d and str(d).strip():
                derived_decisions.append(str(d).strip())
        for o in (t.get("open_issues") or []):
            if o and str(o).strip():
                derived_open.append(str(o).strip())

    derived_dependencies: list[str] = []
    for a in derived_actions:
        cond = a.get("condition")
        if cond and str(cond).strip() and str(cond).strip() not in derived_dependencies:
            derived_dependencies.append(str(cond).strip())

    if getattr(result, "action_hints", None) is None:
        result.action_hints = derived_actions
    if getattr(result, "risk_hints", None) is None:
        result.risk_hints = derived_risks
    if getattr(result, "decisions", None) is None:
        result.decisions = derived_decisions
    if getattr(result, "risks", None) is None:
        result.risks = [r["risk"] for r in derived_risks if r.get("risk")]
    if getattr(result, "open_questions", None) is None:
        result.open_questions = derived_open
    if getattr(result, "dependencies", None) is None:
        result.dependencies = derived_dependencies


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
        user_channel: str = "",
    ) -> MeetingUnderstanding:
        """``user_channel``：本用户称呼表（全称 + 会上别称），由画像生成、注入在原文之前。"""
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
        missable = skipped | {"speakers", "action_hints", "risk_hints", "dependencies", "decisions", "risks", "open_questions"}
        result = await self.client.structured(
            MEETING_UNDERSTANDING_SYSTEM_PROMPT,
            user,
            MeetingUnderstanding,
            MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
            label="core/meeting_understanding",
            allow_missing=missable,
        )
        _ensure_derived_fields(result)
        return result

