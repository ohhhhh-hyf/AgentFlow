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


_SPEAKER_PREFIX = re.compile(
    r"(^|\n)([-*]\s*)?(?:发言者\s*\d+|相关发言|会上发言|发言人)[：:，,、\s]*(?:计划|提出|表示|建议|指出|强调)?\s*"
)
_SPEAKER_REF = re.compile(r"发言者\s*\d+")


def _remove_speaker_placeholders(text: str) -> str:
    """转写占位符不是真实人名：剥离句首口语转述前缀，行中残留转为中性表述。"""
    if not text:
        return ""
    cleaned = _SPEAKER_PREFIX.sub(r"\1\2", text)
    return _SPEAKER_REF.sub("会上发言", cleaned)


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
            parts.append(
                f"【核心讨论主题参考】\n{topic_list}\n"
                "（二级标题可参考或归纳自上述主题，根据会议实际业务模块展开清晰层级）"
            )

        fmt_spec = (
            "【纪要结构要求】\n"
            "# 会议纪要：[会议全局主题]\n\n"
            "## 会议概况\n"
            "1 段连贯文字（约 100-150 字），概述全场背景、核心主旨与大盘决议，采用纯文本段落（不使用列表符号）。\n\n"
            "## [业务议题]\n"
            "（若议题包含多个独立业务方向，可按业务逻辑拆分子板块 `### 业务子方向`）\n"
            "- 使用「- 」分点，每条为动词起笔的独立事实陈述，自然涵盖方案举措、责任分工、交付节点与核心指标。\n"
            "- 针对特定具体事项，可使用精练主题词引导（如 `- **事项名称**：推进要点与结论...`），保持每条内容信息饱满独立，避免机械套用相同主语或重复发言前缀。\n"
            "- 每个板块或议题下充分结合 topics[].key_points、discussion，以及对应的 decisions、action_hints 与 risk_hints，写出包含明确责任人、时限、技术指标与交付标准的完整事实句（3~6 条），为专名、参数及后续溯源落钉提供充足承载句（无相应内容的维度直接不写）。"
        )
        parts.append(fmt_spec)

        note_raw = str(extras.get("note_raw") or "").strip()
        if note_raw:
            parts.append(f"【用户笔记】\n{note_raw}")
        if focus:
            parts.append(focus)
        parts.append(f"【议题标题规范】请使用业务事项或研讨主题作为标题，避免使用个人姓名或发言人编号（如：{banned}）作为标题。")
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

