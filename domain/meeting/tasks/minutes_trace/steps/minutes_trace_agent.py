from __future__ import annotations

import json
import re

from client import LLMClient
from tools.hard_execution import extract_labeled_json

from ....models import MinutesTrace
from ..contracts import MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT
from ..extras import parse_trace_extras
from ..prompts import (
    MINUTES_TRACE_GENERATION_SYSTEM_PROMPT,
    MINUTES_TRACE_REORG_PROMPT,
)
from ..scene import detect_scene, scene_spec
from ..structure import (
    bulletize_minutes,
    collect_people,
    mechanical_closings,
    person_chapter_headings,
)


def _dump(obj: object) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        data = obj.model_dump()
        return data if isinstance(data, dict) else {}
    return dict(obj) if isinstance(obj, dict) else {}


def _focus_guide(extras: dict[str, object], understanding: dict | None = None) -> str:
    """生成【重点覆盖清单】：只给归并指令 + 主题提示，不再重复注入原文。

    3C：原文已在共享上下文的【用户关键点】【用户笔记】块中（runner 注入），
    这里只提炼主题提示（结合会议理解议题标题），省 token 且口径一致。
    """
    keypoints = [str(x).strip() for x in (extras.get("keypoints") or []) if str(x).strip()]
    notes = [
        (str(left).strip(), str(right).strip())
        for left, right in (extras.get("notes") or [])
        if str(left).strip() and str(right).strip()
    ]
    if not keypoints and not notes:
        return ""
    lines = [
        "【重点覆盖清单】",
        "按用户关键点/笔记指向的具体事项归并正文，不要按人列章节。",
        "能被会议原文支持的关键点/笔记尽量写进对应议题，句子通顺完整，不要写成标签堆。",
        "同一事项若在事实、讨论、小结里都会写到，每处都写成完整句，方便后面对齐；不要为挂钩注水。",
        "正文尽量留下可辨认的专名、数字或动作。原文没有的不要补。批注禁止写进正文。",
        "关键点/笔记原文见上方对应块，此处不重复。",
    ]
    hints: list[str] = []
    if isinstance(understanding, dict):
        for topic in understanding.get("topics") or []:
            if isinstance(topic, dict) and str(topic.get("title") or "").strip():
                hints.append(str(topic["title"]).strip())
    seen_hints: list[str] = []
    for h in hints:
        if h and h not in seen_hints:
            seen_hints.append(h)
    if seen_hints:
        lines.append("议题标题提示：" + "、".join(seen_hints[:6]))
    return "\n".join(lines)


def _normalize_markdown(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            prefix = stripped[: len(stripped) - len(stripped.lstrip("#"))]
            title = stripped[len(prefix) :].strip()
            if title.startswith("[") and title.endswith("]"):
                title = title[1:-1].strip()
            line = f"{prefix} {title}".rstrip()
        lines.append(line)
    return "\n".join(lines).strip()


_SPEAKER_REF = re.compile(r"发言者\s*\d+")


def _remove_speaker_placeholders(text: str) -> str:
    """转写占位符不是真实人名，正文侧统一改成中性来源。"""
    return _SPEAKER_REF.sub("相关发言", text or "")


def _extract_transcript(shared_context: str, understanding: dict) -> str:
    transcript = ""
    if "原文：" in (shared_context or ""):
        transcript = shared_context.split("原文：", 1)[1]
        for stop in ("\n【溯源材料", "\n【场景模板包", "\n【用户"):
            if stop in transcript:
                transcript = transcript.split(stop, 1)[0]
    if not transcript and isinstance(understanding, dict):
        transcript = str(understanding.get("meeting_purpose") or "")
    return transcript


def _needs_reorg(minutes_md: str, people: list[str]) -> list[str]:
    reasons: list[str] = []
    headed = person_chapter_headings(minutes_md, people)
    if headed:
        reasons.append("按人成章的议题标题：" + "；".join(headed))
    if mechanical_closings(minutes_md):
        reasons.append("议题小结变成同一句状态套话，缺少分题依据")
    return reasons


# trace 实际消费的理解字段：程序（topics/meeting_purpose）+ LLM
# （scene/meeting_brief/topics/decisions/risks/open_questions）。
# action_hints / risk_hints / dependencies / perspective_profile 等
# 是 actions/risks 线的候选池，trace 用不到——user 侧只发消费字段，省输入 token。
_TRACE_UNDERSTANDING_KEYS = (
    "scene",
    "meeting_brief",
    "topics",
    "decisions",
    "risks",
    "open_questions",
    "meeting_purpose",
)


def _trace_understanding(understanding: dict) -> dict:
    """按 trace 消费字段裁剪理解 JSON（只影响发给 LLM 的内容，不动程序用数据）。"""
    return {
        key: value
        for key, value in (understanding or {}).items()
        if key in _TRACE_UNDERSTANDING_KEYS
    }


class MinutesTraceAgent:
    """按通用模板写纪要 + 对齐草稿；门禁在返回前执行。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> MinutesTrace:
        extras = parse_trace_extras(shared_context)
        pack = extras["pack"] if isinstance(extras["pack"], dict) else {}
        understanding = extract_labeled_json(shared_context, "会议理解") or {}
        if not isinstance(understanding, dict):
            understanding = {}
        focus = _focus_guide(extras, understanding)
        transcript = _extract_transcript(shared_context, understanding)
        # 场景判定：理解/原文启发式，判不出回「通用」；按场景取骨架
        scene = detect_scene(understanding, transcript)
        requirement, fmt = scene_spec(pack, scene)
        people = collect_people(understanding, transcript)
        banned = "、".join(people) if people else "人名、职务称呼、发言者编号"

        # 裁剪输入：只拼 trace 需要的块（原文/会议理解/溯源材料/写作要求/格式），
        # 去掉对 trace 线无用的 视角模式/用户画像/视角模型（省输入 token、减首 token 延迟）
        parts: list[str] = []
        if transcript:
            parts.append(f"会议原文：\n{transcript}")
        llm_understanding = _trace_understanding(understanding)
        if llm_understanding:
            parts.append(
                f"会议理解：\n{json.dumps(llm_understanding, ensure_ascii=False, indent=2)}"
            )
        trace_blocks = "\n\n".join(
            str(block).strip()
            for block in (extras.get("key_raw") or "", extras.get("note_raw") or "")
            if str(block).strip()
        )
        if trace_blocks:
            parts.append(trace_blocks)
        parts.append(f"【写作要求】\n{requirement}")
        parts.append(f"【输出格式】\n{fmt}")
        if focus:
            parts.append(focus)
        parts.append(f"【不得作为议题标题的称呼】{banned}")
        user = "\n\n".join(parts)
        raw = await self.client.structured(
            MINUTES_TRACE_GENERATION_SYSTEM_PROMPT,
            user,
            MinutesTrace,
            MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT,
            max_tokens=16000,
            label="minutes_trace/agent",
        )
        data = _dump(raw)
        minutes_md = bulletize_minutes(
            _remove_speaker_placeholders(
                _normalize_markdown(str(data.get("minutes_md") or ""))
            )
        )
        reasons = _needs_reorg(minutes_md, people)
        if reasons:
            reorg_user = (
                f"{MINUTES_TRACE_REORG_PROMPT}\n\n"
                f"【返工原因】\n"
                + "\n".join(f"- {item}" for item in reasons)
                + f"\n\n【不得作为议题标题的称呼】{banned}\n\n"
                f"【当前草稿】\n{minutes_md}\n"
            )
            repaired = await self.client.structured(
                MINUTES_TRACE_GENERATION_SYSTEM_PROMPT,
                reorg_user,
                MinutesTrace,
                MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT,
                label="minutes_trace/agent",
            )
            repaired_data = _dump(repaired)
            new_md = _normalize_markdown(str(repaired_data.get("minutes_md") or ""))
            if new_md:
                minutes_md = bulletize_minutes(_remove_speaker_placeholders(new_md))

        # alignments 由审核通过后的单独步骤生成（render 阶段），此处草稿不携带
        data["scene"] = scene
        data["minutes_md"] = minutes_md
        data["alignments"] = []
        return MinutesTrace.validate(data)

