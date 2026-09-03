from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from client import LLMClient
from tools.hard_execution import extract_labeled_json
from tools.runtime.progress import progress

from ..align import (
    _evidence_candidates,
    _ngram_df,
    _segment_of,
    _sentence_candidates,
    _minutes_sentences,
    _understanding_pool,
    backfill_alignments,
    classify_priority,
    gate_alignments,
    segment_minutes,
    stamp_minutes,
)
from ..extras import parse_trace_extras
from ..prompts import MINUTES_TRACE_VERDICT_PROMPT


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


def _missing_materials(
    kept: list[dict[str, str]],
    keypoints: list[str],
    notes: list[tuple[str, str]],
) -> tuple[list[str], list[tuple[str, str]]]:
    """程序阶段未命中的材料（关键点 / 笔记 left），供 LLM 补漏。"""
    hit_keys = {str(it.get("source") or "") for it in kept if it.get("kind") == "keypoint"}
    miss_keys = [kp for kp in keypoints if kp not in hit_keys]
    hit_left = {
        str(it.get("source") or "").split(" **用户批注**", 1)[0]
        for it in kept
        if it.get("kind") == "note"
    }
    miss_notes = [(l, r) for l, r in notes if l not in hit_left]
    return miss_keys, miss_notes


async def _align_alignments(client, context: str, minutes_md: str) -> tuple[list[dict], dict]:
    """审核通过后生成对齐条目：程序落钉优先，未命中高价值材料走候选包裁判（LLM 只选 id）。"""
    extras = parse_trace_extras(context)
    keypoints = list(extras.get("keypoints") or [])
    notes = list(extras.get("notes") or [])
    if not keypoints and not notes:
        return [], {}
    transcript = _transcript_from_context(context)
    understanding = extract_labeled_json(context, "会议理解") or {}
    if not isinstance(understanding, dict):
        understanding = {}
    topic_titles = _topic_titles_from_context(context)
    # 程序预筛候选（零 LLM）：确定性对齐作基底；会议理解条目作证据池。
    audit: dict[str, Any] = {}
    candidates = backfill_alignments(
        [], minutes_md, transcript, keypoints, notes, topic_titles, understanding, audit
    )
    miss_keys, miss_notes = _missing_materials(candidates, keypoints, notes)
    audit.setdefault("dropped", [])
    if not miss_keys and not miss_notes:
        summary = audit.setdefault("summary", {})
        progress(
            "溯源落钉：程序对齐 %d 条，材料全覆盖"
            "（keypoint %d/%d 有据挂 %d；note %d/%d 有据挂 %d）",
            len(candidates),
            summary.get("keypoint_total", 0),
            summary.get("keypoint_supported", 0),
            summary.get("keypoint_pinned", 0),
            summary.get("note_total", 0),
            summary.get("note_supported", 0),
            summary.get("note_pinned", 0),
        )
        return candidates, audit
    # ── 候选包：只取高价值未命中且 evidence/sentence 候选都非空的材料 ──
    sents = _minutes_sentences(minutes_md)
    df = _ngram_df(sents)
    n_docs = len(sents)
    pool = _understanding_pool(understanding)
    segments = segment_minutes(minutes_md)
    items: list[dict[str, Any]] = []
    idx = 0
    for kp in miss_keys:
        pri = classify_priority(kp)
        if pri == "low":
            audit["dropped"].append({"source": kp, "reason": "low_priority_skipped_llm", "priority": pri})
            continue
        evs = _evidence_candidates(kp, transcript, pool, limit=3)
        scs = _sentence_candidates(kp, sents, df, n_docs, limit=5)
        if not evs or not scs:
            audit["dropped"].append({"source": kp, "reason": "no_candidates_for_llm", "priority": pri})
            continue
        idx += 1
        items.append({
            "source_id": f"kp_{idx}",
            "kind": "keypoint",
            "priority": pri,
            "source": kp,
            "evidence_candidates": [
                {"id": f"E{i}", **ev} for i, ev in enumerate(evs, 1)
            ],
            "sentence_candidates": [
                {"id": f"S{i}", "text": s, "section": _segment_of(s, segments)}
                for i, s in enumerate(scs, 1)
            ],
        })
    for left, right in miss_notes:
        pri = classify_priority(left, right)
        if pri == "low":
            audit["dropped"].append({"source": f"{left} -> {right}", "reason": "low_priority_skipped_llm", "priority": pri})
            continue
        evs = _evidence_candidates(left, transcript, pool, limit=3)
        scs = _sentence_candidates(left, sents, df, n_docs, limit=5)
        if not evs or not scs:
            audit["dropped"].append({"source": f"{left} -> {right}", "reason": "no_candidates_for_llm", "priority": pri})
            continue
        idx += 1
        items.append({
            "source_id": f"note_{idx}",
            "kind": "note",
            "priority": pri,
            "source": f"{left} **用户批注** {right}",
            "evidence_candidates": [
                {"id": f"E{i}", **ev} for i, ev in enumerate(evs, 1)
            ],
            "sentence_candidates": [
                {"id": f"S{i}", "text": s, "section": _segment_of(s, segments)}
                for i, s in enumerate(scs, 1)
            ],
        })
    progress(
        "溯源落钉：程序对齐 %d 条，%d 条关键点/%d 条笔记未命中，其中 %d 条进入候选包裁判",
        len(candidates), len(miss_keys), len(miss_notes), len(items),
    )
    audit["llm"] = {"triggered": bool(items), "pack_sources": len(items)}
    if not items:
        return candidates, audit
    # ── LLM 裁判：只输出 source_id/sentence_id/evidence_id/decision ──
    user = json.dumps({"items": items}, ensure_ascii=False, indent=1)
    try:
        text = await client.text(
            MINUTES_TRACE_VERDICT_PROMPT,
            user,
            temperature=0.0,
            max_tokens=4000,
            label="minutes_trace/verdict",
        )
        verdicts = _parse_verdict_json(text)
    except Exception:  # noqa: BLE001 - 裁判失败降级为程序候选
        verdicts = []
    restored: list[dict[str, str]] = []
    for v in verdicts:
        if str(v.get("decision") or "").strip().lower() != "keep":
            continue
        item = next((it for it in items if it.get("source_id") == v.get("source_id")), None)
        if item is None:
            continue
        ev = next(
            (e for e in item.get("evidence_candidates") or [] if e.get("id") == v.get("evidence_id")),
            None,
        )
        sent = next(
            (s for s in item.get("sentence_candidates") or [] if s.get("id") == v.get("sentence_id")),
            None,
        )
        if ev is None or sent is None:
            continue
        restored.append({
            "sentence": sent["text"],
            "kind": item["kind"],
            "source": item["source"],
            "evidence": ev["text"],
        })
    progress("溯源裁判：%d 条 keep，进入程序门禁", len(restored))
    audit["llm"]["verdict_keep"] = len(restored)
    if restored:
        gated = gate_alignments(
            restored, minutes_md, transcript, keypoints, notes, topic_titles,
            understanding,
        )
        for it in gated:
            it["confidence"] = "llm_selected"
        seen = {
            (it.get("sentence", ""), it.get("kind", ""), it.get("source", ""))
            for it in candidates
        }
        merged = list(candidates)
        for it in gated:
            marker = (it.get("sentence", ""), it.get("kind", ""), it.get("source", ""))
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(it)
        return merged, audit
    return candidates, audit


def _parse_verdict_json(text: str) -> list[dict[str, Any]]:
    """从 LLM 文本中抠出 {"alignments": [...]}（兼容 markdown 包裹）。"""
    raw = text or ""
    start = raw.find("{")
    if start < 0:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    aligns = data.get("alignments") or []
    return [a for a in aligns if isinstance(a, dict)]

class MinutesTraceRender:
    """程序落钉，不让模型改标注格式。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        # 最近一次渲染的溯源审计（summary/pins/dropped/llm），供调试 sidecar（阶段 C 落盘）
        self.last_audit: dict[str, Any] = {}

    async def materialize(self, approved_context: str, template: str = "") -> str:
        """deterministic_pipeline 入口：审核通过后生成对齐 → 程序落钉，不调 LLM 改正文。"""
        return await self.run(approved_context, template)

    async def run(self, approved_context: str, template: str = "") -> str:
        del template
        draft = _draft_from_context(approved_context)
        body = str(draft.get("minutes_md") or "").strip()
        if not body:
            return "请直接参考会议原文。"
        alignments, audit = await _align_alignments(
            self.client, approved_context, body
        )
        self.last_audit = audit
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

