from __future__ import annotations

import json
from collections.abc import AsyncIterator

from client import LLMClient
from tools.hard_execution import extract_labeled_json
from tools.runtime.progress import progress

from ....models import MinutesTrace
from ..align import backfill_alignments, gate_alignments, stamp_minutes
from ..extras import parse_trace_extras
from ..prompts import (
    MINUTES_TRACE_ALIGN_OUTPUT_CONTRACT,
    MINUTES_TRACE_ALIGN_PROMPT,
)


def _draft_from_context(approved_context: str) -> dict:
    marker = "已批准溯源纪要草稿："
    blob = approved_context or ""
    if marker in blob:
        blob = blob.split(marker, 1)[1]
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _transcript_from_context(context: str) -> str:
    """从渲染上下文提取会议原文块（meeting 域的原文标签为「会议原文」）。"""
    for marker in ("会议原文：", "会议原文:"):
        if marker in (context or ""):
            tail = context.split(marker, 1)[1]
            for stop in ("\n用户画像", "\n会议理解", "\n已批准", "\n【用户"):
                if stop in tail:
                    tail = tail.split(stop, 1)[0]
            return tail.strip()
    return ""


def _topic_titles_from_context(context: str) -> list[str]:
    understanding = extract_labeled_json(context, "会议理解") or {}
    if not isinstance(understanding, dict):
        return []
    titles: list[str] = []
    for topic in understanding.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        title = str(topic.get("title") or "").strip()
        if title and title not in titles:
            titles.append(title)
    return titles


async def _align_alignments(client, context: str, minutes_md: str) -> list[dict]:
    """审核通过后生成对齐条目：程序落钉优先，LLM 只在程序挂不上时补漏。"""
    extras = parse_trace_extras(context)
    keypoints = list(extras.get("keypoints") or [])
    notes = list(extras.get("notes") or [])
    if not keypoints and not notes:
        return []
    transcript = _transcript_from_context(context)
    topic_titles = _topic_titles_from_context(context)
    key_raw = str(extras.get("key_raw") or "").strip()
    note_raw = str(extras.get("note_raw") or "").strip()
    # 程序预筛候选（零 LLM）：确定性对齐作基底，LLM 只确认/修正/补漏。
    # 候选充足时不喂全量原文（候选自带 evidence 窗口），输出规模随之缩小；
    # 候选为空时回退带全量原文，LLM 自行判断（与旧行为一致，不丢补漏能力）。
    candidates = backfill_alignments(
        [], minutes_md, transcript, keypoints, notes, topic_titles
    )
    # 程序候选已经过主张级门禁。再让 LLM「确认」会多一轮审核、复跑钉子易抖。
    # 有候选就直接落钉；只有程序挂不上时才用 LLM 补漏。
    if candidates:
        progress("溯源落钉：程序对齐 %d 条，跳过 LLM 确认", len(candidates))
        return candidates
    progress("溯源落钉：程序未命中，改用 LLM 对齐")
    blocks = [f"已批准纪要正文：\n{minutes_md}"]
    if transcript:
        blocks.append(f"会议原文：\n{transcript}")
    if key_raw:
        blocks.append(key_raw)
    if note_raw:
        blocks.append(note_raw)
    user = "\n\n".join(blocks)
    try:
        result = await client.structured(
            MINUTES_TRACE_ALIGN_PROMPT,
            user,
            MinutesTrace,
            MINUTES_TRACE_ALIGN_OUTPUT_CONTRACT,
            temperature=0.0,
            max_tokens=16000,
            label="minutes_trace/align",
        )
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        llm_aligns = list(data.get("alignments") or [])
    except Exception:  # noqa: BLE001 - 确认失败降级为程序候选，正文不受影响
        llm_aligns = []
    if llm_aligns:
        # LLM 确认后的输出再过一次程序门禁，防乱挂
        return gate_alignments(
            llm_aligns, minutes_md, transcript, keypoints, notes, topic_titles
        )
    return candidates


class MinutesTraceRender:
    """程序落钉，不让模型改标注格式。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def materialize(self, approved_context: str, template: str = "") -> str:
        """deterministic_pipeline 入口：审核通过后生成对齐 → 程序落钉，不调 LLM 改正文。"""
        return await self.run(approved_context, template)

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = _draft_from_context(approved_context)
        body = str(draft.get("minutes_md") or "").strip()
        if not body:
            return "请直接参考会议原文。"
        alignments = await _align_alignments(self.client, approved_context, body)
        from domain.meeting.tasks.minutes.steps.minutes_render import (
            compact_untemplated_minutes,
        )

        return compact_untemplated_minutes(stamp_minutes(body, alignments))

    async def stream(
        self, approved_context: str, template: str = ""
    ) -> AsyncIterator[str]:
        text = await self.run(approved_context, template)
        if text:
            yield text

