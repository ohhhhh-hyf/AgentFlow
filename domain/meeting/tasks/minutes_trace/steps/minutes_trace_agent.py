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
            "每条关键点对应的会议内容，必须在纪要正文的相应议题中至少有一条完整、通顺的正文句承载：",
            "可在该议题的「问题与事实 / 讨论观点 / 建议与方案 / 议题小结」下与其它内容合并改写，不必逐字复述；",
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
    # 不重复输出议题标题提示：topics 标题已随「会议理解」JSON 完整发给 LLM。
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
    data = {
        key: value
        for key, value in (understanding or {}).items()
        if key in _TRACE_UNDERSTANDING_KEYS
    }
    # meeting 域打包时 meeting_brief 会以 meeting_purpose 兜底，两字段同文时
    # 只发一份（brief 保留），避免同一段目的文字发给 LLM 两次。
    brief = " ".join(str(data.get("meeting_brief") or "").split()).strip()
    purpose = " ".join(str(data.get("meeting_purpose") or "").split()).strip()
    if brief and purpose == brief:
        data.pop("meeting_purpose", None)
    return data


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
        focus = _focus_guide(extras)
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
        # 用户笔记原文（左句 -> 批注）在此保留原文块；用户关键点不再重复裸注入——
        # 其全量清单已带编号逐条列在 focus 的【关键点覆盖要求】中（内容等价）。
        note_raw = str(extras.get("note_raw") or "").strip()
        if note_raw:
            parts.append(f"【用户笔记】\n{note_raw}")
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

