from __future__ import annotations

import json
import re

from infra.llm import LLMClient
from core.execution.hard_execution import extract_labeled_json

from ....models import MinutesTrace
from ..contracts import MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT
from ..extras import parse_trace_extras
from ..prompts import MINUTES_TRACE_GENERATION_SYSTEM_PROMPT
from ..structure import bulletize_minutes, collect_people


def _dump(obj: object) -> dict:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        data = obj.model_dump()
        return data if isinstance(data, dict) else {}
    return dict(obj) if isinstance(obj, dict) else {}


def _focus_guide(extras: dict[str, object]) -> str:
    """生成【关键点覆盖要求】+【用户笔记提示】。

    关键点逐条列出并声明为必覆盖验收项(正文必须为每条留承载句,句位即溯源位);
    笔记只提示、不列清单(批注不入文,笔记所指事实按正常纪要写作自然写入即可);
    笔记原文块由 run() 以【用户笔记】标签注入到上下文。
    """
    keypoints = [
        str(x).strip()
        for x in (extras.get("keypoints") or [])
        if str(x).strip()
    ]
    notes = [
        (str(left).strip(), str(right).strip())
        for left, right in (extras.get("notes") or [])
        if str(left).strip() and str(right).strip()
    ]
    parts: list[str] = []
    if keypoints:
        lines = [
            "【关键点覆盖要求】",
            f"本次会议有 {len(keypoints)} 条用户关键点，逐条列出如下。",
            "每条关键点对应的会议内容，必须在纪要正文相应议题中至少有一条完整、通顺的「- 」正文事实句承载：",
            "在对应议题的事实条目中与相关事实自然合并改写，不必逐字复述；",
            "这条承载句将作为该关键点的溯源与定位位置。任一条关键点在正文找不到对应内容，视为本次生成的缺陷。",
            "正文句要保留可辨认的专名、数字、动作与范围，便于与会议原文核对；会议原文没有的内容不要补充。",
            "不要为覆盖而把同一条内容重复堆叠成多句；同义内容自然出现在多处属正常。",
            "若某条关键点与本次会议内容确实无对应(一般不会发生)，宁可省略不写，也不要硬造正文或凭空发挥。",
        ]
        for i, kp in enumerate(keypoints, 1):
            lines.append(f"{i}. {kp}")
        parts.append("\n".join(lines))
    if notes:
        parts.append(
            "【用户笔记提示】\n"
            f"另有 {len(notes)} 条用户笔记(原文划线句 + 批注，原文见上方【用户笔记】块)，不列入覆盖清单：\n"
            "- 批注文字一律不得写入正文；\n"
            "- 笔记指向的会议事实若属实质内容，按正常纪要写作在对应议题中体现即可；不为挂载而注水、不整句照抄口语原文。"
        )
    return "\n\n".join(parts)


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


# trace 实际消费的理解字段：程序（topics/meeting_purpose）+ LLM
# （meeting_brief/topics/decisions/risks/open_questions/action_hints/risk_hints/dependencies）。
_TRACE_UNDERSTANDING_KEYS = (
    "meeting_brief",
    "topics",
    "decisions",
    "risks",
    "open_questions",
    "meeting_purpose",
    "action_hints",
    "risk_hints",
    "dependencies",
)


def _trace_understanding(understanding: dict) -> dict:
    """按 trace 消费字段裁剪理解 JSON（只影响发给 LLM 的内容，不动程序用数据）。"""
    data = {
        key: value
        for key, value in (understanding or {}).items()
        if key in _TRACE_UNDERSTANDING_KEYS
    }
    brief = " ".join(str(data.get("meeting_brief") or "").split()).strip()
    purpose = " ".join(str(data.get("meeting_purpose") or "").split()).strip()
    if brief and purpose == brief:
        data.pop("meeting_purpose", None)
    return data


class MinutesTraceAgent:
    """按议题树写客观平实纪要 + 对齐草稿；门禁在返回前执行。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> MinutesTrace:
        extras = parse_trace_extras(shared_context)
        understanding = extract_labeled_json(shared_context, "会议理解") or {}
        if not isinstance(understanding, dict):
            understanding = {}
        focus = _focus_guide(extras)
        transcript = _extract_transcript(shared_context, understanding)
        people = collect_people(understanding, transcript)
        banned = "、".join(people) if people else "人名、职务称呼、发言者编号"

        parts: list[str] = []
        if transcript:
            parts.append(f"会议原文：\n{transcript}")
        llm_understanding = _trace_understanding(understanding)
        if llm_understanding:
            parts.append(
                f"会议理解：\n{json.dumps(llm_understanding, ensure_ascii=False, indent=2)}"
            )

        topics = understanding.get("topics") or []
        topic_titles = [
            str(t.get("title") or "").strip()
            for t in topics
            if isinstance(t, dict) and str(t.get("title") or "").strip()
        ]
        if topic_titles:
            topic_list = "\n".join(f"{i}. {title}" for i, title in enumerate(topic_titles, 1))
            parts.append(f"【议题清单（纪要正文二级标题必须严格按此展开）】\n{topic_list}")

        fmt_spec = (
            "【纪要结构要求】\n"
            "# 会议纪要：[会议全局主题]\n\n"
            "## 会议概况\n"
            "1 段连贯文字（约 100-150 字），概述全场背景、核心主旨与大盘决议，禁止列表符号与序号。\n\n"
            "## [议题名称]\n"
            "- 各议题标题必须且只能取自上述「议题清单」。\n"
            "- 使用「- 」分点，一行陈述一个完整客观事实，组内严禁任何加粗机械前缀（如禁止写“**讨论**：/ **决议**：”等）。\n"
            "- 事实饱满度要求：每个议题下充分结合 topics[].key_points、discussion，以及对应的 decisions、action_hints（分工动作/排期节点）和 risk_hints，写出包含明确责任人、时限、技术指标与交付标准的完整事实句（3~6 条），为专名、参数及后续溯源落钉提供充足承载句（无相应内容的维度直接不写）。"
        )
        parts.append(fmt_spec)

        note_raw = str(extras.get("note_raw") or "").strip()
        if note_raw:
            parts.append(f"【用户笔记】\n{note_raw}")
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

        data["minutes_md"] = minutes_md
        return MinutesTrace.validate(data)

