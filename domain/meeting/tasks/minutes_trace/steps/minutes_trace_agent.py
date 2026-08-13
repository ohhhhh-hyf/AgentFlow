from __future__ import annotations

from llm_client import LLMClient
from tools.hard_execution import extract_labeled_json

from ....models import MinutesTrace
from ..align import backfill_alignments
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
        "按用户关键点/笔记里反复出现的问题主题归并正文，不要按人列章节。",
        "能被会议原文支持的主题尽量覆盖。用户批注只用于挂钩来源，禁止写进纪要正文。",
        "关键点/笔记原文见上方【用户关键点】【用户笔记】块，此处不重复。",
    ]
    # 主题提示：从会议理解议题标题 + 用户关键点里提炼高频主题（2A 主题桥的 LLM 侧呼应）
    hints: list[str] = []
    if isinstance(understanding, dict):
        for topic in understanding.get("topics") or []:
            if isinstance(topic, dict) and str(topic.get("title") or "").strip():
                hints.append(str(topic["title"]).strip())
    if keypoints:
        for kp in keypoints[:3]:
            for sep in ("：", ":", "——", "，", "。"):
                if sep in kp:
                    head = kp.split(sep, 1)[0].strip()
                    if head and len(head) <= 12:
                        hints.append(head)
                        break
    seen_hints: list[str] = []
    for h in hints:
        if h and h not in seen_hints:
            seen_hints.append(h)
    if seen_hints:
        lines.append("主题提示：" + "、".join(seen_hints[:6]))
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


class MinutesTraceAgent:
    """按通用模板写纪要 + 对齐草稿；门禁在返回前执行。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> MinutesTrace:
        extras = parse_trace_extras(shared_context)
        pack = extras["pack"] if isinstance(extras["pack"], dict) else {}
        pack_raw = str(extras.get("pack_raw") or "")
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

        user = (
            f"{shared_context}\n\n"
            f"【写作要求】\n{requirement}\n\n"
            f"【输出格式】\n{fmt}\n\n"
            f"{focus}\n\n"
            f"【不得作为议题标题的称呼】{banned}\n\n"
            "【稳定输出要求】\n"
            "- 严格按【输出格式】的大标题组织，标题不要保留方括号。\n"
            "- 主要议题只保留 3–6 个问题/事项，按问题归类；议题标题禁止出现【不得作为议题标题的称呼】。\n"
            "- 禁止「XX汇报」「对XX的建议/点评」「XX工作目标与举措」这类按人成章的标题。\n"
            "- 同一问题下合并所有人的事实与意见；对人的点评放回对应问题。\n"
            "- 每个议题写：问题与事实、讨论观点、建议与方案、议题小结；原文没有则写「未提及」。\n"
            "- 议题小结写成「状态：…。依据：…。」各议题单独判断，禁止全部写成同一个状态。\n"
            "- 「关键决策与明确要求」「行动项与后续安排」以及结论里的子节，原文没有就整节不写。\n"
            "- 除标题和表格外一律用 `- ` 分点，一条只写一件事；不要把多条事实用分号粘成一段。\n"
            "- 建议不要写成决定；保留「可能/暂定/待确认」等不确定语气。\n"
            "- 对齐草稿只挂同一件事；只共享空泛时间/范畴词的不要列。\n"
        )
        raw = await self.client.structured(
            MINUTES_TRACE_GENERATION_SYSTEM_PROMPT,
            user,
            MinutesTrace,
            MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT,
        )
        data = _dump(raw)
        minutes_md = bulletize_minutes(
            _normalize_markdown(str(data.get("minutes_md") or ""))
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
            )
            repaired_data = _dump(repaired)
            new_md = _normalize_markdown(str(repaired_data.get("minutes_md") or ""))
            if new_md:
                minutes_md = bulletize_minutes(new_md)
                if repaired_data.get("alignments"):
                    data["alignments"] = repaired_data.get("alignments")

        alignments = backfill_alignments(
            list(data.get("alignments") or []),
            minutes_md,
            transcript,
            list(extras.get("keypoints") or []),
            list(extras.get("notes") or []),
            topic_titles=[
                str(t.get("title") or "").strip()
                for t in (understanding.get("topics") or [])
                if isinstance(t, dict) and str(t.get("title") or "").strip()
            ] or None,
        )
        data["scene"] = scene
        data["minutes_md"] = minutes_md
        data["alignments"] = alignments
        return MinutesTrace.validate(data)
