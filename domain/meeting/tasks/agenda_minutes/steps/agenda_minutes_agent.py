"""agenda_minutes_agent.py -- 议程驱动型会议纪要生成 Agent。

流程：
1. 从 shared_context 中提取既定议程单与会议录音转写；
2. parse_agenda_text 解析既定议程大盘 AgendaPlan；
3. align_agenda_with_transcript 执行发言人真名双向锚定与实录切片；
4. 对 skipped 议题执行 Zero-Evidence 截断（杜绝虚构脑补）；
5. 对 discussed 议题调用大模型提炼全景四要素；
6. Agenda-as-Anchor 绝对骨架后置硬校验：100% 覆盖议程单全部序号与法定全称。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from tools.llm import LLMClient
from tools.schema.validation import OutputValidationError

from ....models import AgendaMinutes
from ....models_base import ModelMixin
from ..agenda_parser import (
    match_presenter_name,
    parse_agenda_text,
)
from ..alignment_engine import (
    NAME_MATCH_ACCEPT,
    AgendaAlignment,
    AlignmentResult,
    align_agenda_with_transcript,
)
from ..contracts import (
    SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT,
    normalize_status_tag,
)
from ..prompts import (
    build_single_item_prompt,
)
from ..types import detect_agenda_type

logger = logging.getLogger(__name__)


# ── 预算与并发（2026-09-29 抽出命名；**取值一律未改**）──────────────────
#
# 原先这些数字散在函数体与默认参数里，看不出彼此关系。抽成具名常量只为可读；
# 调整它们等于改变证据覆盖与生成长度，需要拿真实夹具重新评估。

# 单议题送模型的实录字符预算（超预算按「汇报人优先」截取，见 _extract_budgeted_evidence）
_EVIDENCE_CHAR_BUDGET = 12000

# 会议类型判定只看转写开头这一段（够识别类型即可，不必全文）
_TYPE_DETECT_TRANSCRIPT_CHARS = 5000

# 单议题结构化输出的 max_tokens 上限
_ITEM_MAX_TOKENS = 2000

# Map 阶段并发度（同名环境变量可覆盖）
_CONCURRENCY_ENV = "AGENDA_MINUTES_CONCURRENCY"
_DEFAULT_CONCURRENCY = "4"


def _normalize_conclusion_points(val: Any) -> list[str]:
    """统一规范化结论与状态字段为干净的条目列表，彻底支持一点一行拆解。"""
    if val is None or val is False:
        return []
    if isinstance(val, (list, tuple, set)):
        res = []
        for x in val:
            res.extend(_normalize_conclusion_points(x))
        return [r for r in res if r]

    s = str(val).strip()
    if not s:
        return []

    # 1. 修复历史上因 str(list) 产生的 "['item1', 'item2']" 字符串
    if s.startswith("[") and s.endswith("]") and ("'," in s or '",' in s or "','" in s or '","' in s):
        import ast

        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return _normalize_conclusion_points(parsed)
        except Exception:
            pass
        inner = s[1:-1].strip()
        parts = re.split(r"'\s*,\s*'|\"\s*,\s*\"", inner)
        cleaned = [p.strip().strip("'\"").strip() for p in parts if p.strip().strip("'\"").strip()]
        if len(cleaned) > 1:
            return _normalize_conclusion_points(cleaned)

    # 2. 预处理：解耦定调语句与前置约束标题（如 '...通过。生效前置约束：1）...' -> '...通过。\n1）...'）
    s = re.sub(r'^\s*(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|后续要求|主要关注项|注意事项)[：:]\s*', '', s)
    s = re.sub(r'([。；;\n])?\s*(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|后续要求|主要关注项|注意事项)[：:]\s*', lambda m: (m.group(1) or '。') + '\n', s)
    s = re.sub(r'([。；;\n])?\s*(?:现场未决卡点|现场卡点|未决卡点|遗留卡点)[：:]\s*', lambda m: (m.group(1) or '。') + '\n', s)

    # 3. 标号前置断行：在 1） 2） 1. (1) ① 一是 等标记前切开
    num_pattern = re.compile(r'(?<=[^0-9\n])(?=(?:[1-9]\d*[\.、）\)]|[(（][1-9]\d*[)）]|[①-⑩]|(?:一是|二是|三是|四是|五是)|(?:第一[，,、]|第二[，,、]|第三[，,、])))')
    s = num_pattern.sub('\n', s)

    # 4. 按行切分
    lines = [line.strip() for line in s.splitlines() if line.strip()]

    # 5. 若未成功分行，但包含 2 个及以上分号，按分号切分
    if len(lines) == 1 and (lines[0].count('；') >= 2 or lines[0].count(';') >= 2):
        lines = [p.strip() for p in re.split(r'[；;]\s*', lines[0]) if p.strip()]

    # 6. 清洗每条开头的数字标号与冗余前缀（如“生效前置约束 1：”等，实现一点一行干货直出）
    cleaned = []
    for it in lines:
        it = re.sub(r'^(?:[-*•·\s]+|(?:[1-9]\d*[\.、）\)]|[(（][1-9]\d*[)）]|[①-⑩]|(?:一是|二是|三是|四是|五是)|(?:第一[，,、]|第二[，,、]|第三[，,、])))\s*', '', it).strip()
        it = re.sub(r'^(?:发布前置条件|生效前置约束|前置条件|前置约束|附带条件|现场未决卡点|现场卡点|未决卡点|遗留卡点)\s*\d*\s*[：:]\s*', '', it).strip()
        if re.search(r'^(?:现场)?无(?:其他)?(?:阻塞|卡点|遗留|风险|问题)', it):
            continue
        if it:
            cleaned.append(it)

    return cleaned or [s]


def _clean_timestamp(ts: str) -> str:
    """清洗时间戳为 HH:MM 或 MM:SS（去掉末尾秒数，若格式为 HH:MM:SS 则保留前两位 HH:MM）。"""
    ts = (ts or "").strip()
    if not ts:
        return ""
    parts = ts.split(":")
    if len(parts) == 3:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    elif len(parts) == 2:
        return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}"
    return ts


def _format_time_range(blocks: list[Any] | None) -> str:
    """根据发言块提取起止时间戳区间，如 '00:10 ~ 00:24'；无有效时间戳或未讨论则返回 '—'。"""
    if not blocks:
        return "—"
    valid_ts = [_clean_timestamp(getattr(b, "timestamp", "")) for b in blocks if getattr(b, "timestamp", None)]
    valid_ts = [t for t in valid_ts if t]
    if not valid_ts:
        return "—"
    start_ts = valid_ts[0]
    end_ts = valid_ts[-1]
    if start_ts == end_ts:
        return start_ts
    return f"{start_ts} ~ {end_ts}"



@dataclass
class SingleAgendaItemModel(ModelMixin):
    """单议题结构化输出数据模型（1~5 栏纯干货直出，向上兼容旧字段）。"""

    presenter: str = ""
    status_tag: str = "审议通过"
    time_range: str = "—"
    # 1~5 纯干货字段
    target_and_audience: list[str] = field(default_factory=list)
    content_and_evidence: list[str] = field(default_factory=list)
    process_and_interaction: list[str] = field(default_factory=list)
    conclusion_and_status: str | list[str] = ""
    action_items: list[dict[str, Any]] = field(default_factory=list)
    # 兼容旧字段
    proposal_highlights: list[str] = field(default_factory=list)
    deliberation_details: dict[str, Any] = field(default_factory=dict)
    resolution: str | list[str] = ""
    action_commitments: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.target_and_audience and self.proposal_highlights:
            self.target_and_audience = list(self.proposal_highlights)
        elif not self.proposal_highlights and self.target_and_audience:
            self.proposal_highlights = list(self.target_and_audience)

        delib = self.deliberation_details if isinstance(self.deliberation_details, dict) else {}
        delib_metrics = list(delib.get("key_metrics") or [])
        delib_concerns = list(delib.get("feedback_concerns") or [])

        if not self.content_and_evidence and delib_metrics:
            self.content_and_evidence = list(delib_metrics)
        elif not delib_metrics and self.content_and_evidence:
            if not isinstance(self.deliberation_details, dict):
                self.deliberation_details = {}
            self.deliberation_details["key_metrics"] = list(self.content_and_evidence)

        if not self.process_and_interaction and delib_concerns:
            self.process_and_interaction = list(delib_concerns)
        elif not delib_concerns and self.process_and_interaction:
            if not isinstance(self.deliberation_details, dict):
                self.deliberation_details = {}
            self.deliberation_details["feedback_concerns"] = list(self.process_and_interaction)

        if not self.conclusion_and_status and self.resolution:
            self.conclusion_and_status = self.resolution
        elif not self.resolution and self.conclusion_and_status:
            self.resolution = self.conclusion_and_status

        if not self.action_items and self.action_commitments:
            self.action_items = list(self.action_commitments)
        elif not self.action_commitments and self.action_items:
            self.action_commitments = list(self.action_items)

    @classmethod
    def validate(cls, data: dict) -> "SingleAgendaItemModel":
        if not isinstance(data, dict):
            raise OutputValidationError("SingleAgendaItemModel 必须是对象")

        # 1. 目标与对象
        target = list(data.get("target_and_audience") or data.get("proposal_highlights") or [])

        # 2. 内容与依据
        content_raw = data.get("content_and_evidence")
        if isinstance(content_raw, list):
            content = list(content_raw)
        elif isinstance(content_raw, dict):
            content = list(content_raw.get("key_metrics") or []) + list(content_raw.get("facts_and_options") or [])
        else:
            delib_raw = data.get("deliberation_details") or {}
            content = list(delib_raw.get("key_metrics") or []) if isinstance(delib_raw, dict) else []

        # 3. 过程与互动
        process_raw = data.get("process_and_interaction")
        if isinstance(process_raw, list):
            process = list(process_raw)
        elif isinstance(process_raw, dict):
            process = list(process_raw.get("feedback_concerns") or []) + list(process_raw.get("focus_debates") or [])
        else:
            delib_raw = data.get("deliberation_details") or {}
            process = list(delib_raw.get("feedback_concerns") or []) if isinstance(delib_raw, dict) else []

        # 4. 结论与状态（支持多点结构化与单条自然语言）
        conclusion_raw = data.get("conclusion_and_status") or data.get("resolution") or ""
        conclusion_pts = _normalize_conclusion_points(conclusion_raw)
        if len(conclusion_pts) > 1:
            conclusion: str | list[str] = conclusion_pts
        elif len(conclusion_pts) == 1:
            conclusion = conclusion_pts[0]
        else:
            conclusion = ""

        # 5. 行动与效果
        actions = list(data.get("action_items") or data.get("action_commitments") or [])

        # 双向映射兼容
        return cls(
            presenter=str(data.get("presenter") or "").strip(),
            status_tag=normalize_status_tag(data.get("status_tag"), is_skipped=False),
            time_range=str(data.get("time_range") or "—").strip(),
            target_and_audience=target,
            content_and_evidence=content,
            process_and_interaction=process,
            conclusion_and_status=conclusion,
            action_items=actions,
            # 兼容旧字段
            proposal_highlights=target,
            deliberation_details={
                "key_metrics": content,
                "feedback_concerns": process,
            },
            resolution=conclusion,
            action_commitments=actions,
        )


def _extract_agenda_and_transcript(shared_context: str) -> tuple[str, str]:
    """从上下文抽屉中解析出既定议程单文本与会议实录正文。"""
    agenda_text = ""
    transcript_text = ""

    # 1. 优先从特定标记提取
    if "【既定议程单】" in shared_context or "【既定议程】" in shared_context or "【议程】" in shared_context:
        marker = "【既定议程单】" if "【既定议程单】" in shared_context else ("【既定议程】" if "【既定议程】" in shared_context else "【议程】")
        parts = shared_context.split(marker, 1)
        rest = parts[1]
        if "【会议原文】" in rest:
            agenda_part, transcript_part = rest.split("【会议原文】", 1)
            agenda_text = agenda_part.strip()
            transcript_text = transcript_part.strip()
        elif "【会议转写】" in rest:
            agenda_part, transcript_part = rest.split("【会议转写】", 1)
            agenda_text = agenda_part.strip()
            transcript_text = transcript_part.strip()
        else:
            agenda_text = rest.strip()

    if not transcript_text and "【会议原文】" in shared_context:
        transcript_text = shared_context.split("【会议原文】", 1)[1].strip()

    # 2. 兜底提取
    if not agenda_text and ("编号" in shared_context or "序号" in shared_context) and "|" in shared_context:
        # 尝试查找包含表格的一段
        lines = shared_context.splitlines()
        tbl = []
        for line in lines:
            if "|" in line or line.startswith(("+", "-")) or any(h in line for h in ("会议主题", "Subject", "与会人")):
                tbl.append(line)
        if tbl:
            agenda_text = "\n".join(tbl)

    if not transcript_text:
        transcript_text = shared_context.strip()

    return agenda_text, transcript_text


def _extract_budgeted_evidence(
    align: AgendaAlignment,
    max_chars: int = _EVIDENCE_CHAR_BUDGET,
) -> str:
    """按预算截取议题证据，优先确保官方汇报人的发言100%保留。"""
    if len(align.evidence_text) <= max_chars:
        return align.evidence_text

    blocks = align.matched_blocks
    presenters = set(align.item.presenters)
    # 优先抽取汇报人自己的发言
    pres_blocks = [
        b for b in blocks
        if any(match_presenter_name(p, b.speaker) >= NAME_MATCH_ACCEPT for p in presenters)
    ]
    other_blocks = [
        b for b in blocks
        if not any(match_presenter_name(p, b.speaker) >= NAME_MATCH_ACCEPT for p in presenters)
    ]

    selected: list[Any] = list(pres_blocks)
    current_len = sum(len(b.content) for b in selected)

    # 填充其他重要讨论块（问答、决议）
    for b in other_blocks:
        if current_len + len(b.content) > max_chars:
            break
        selected.append(b)
        current_len += len(b.content)

    selected.sort(key=lambda b: b.index)
    lines_buf = [f"{b.speaker} {b.timestamp}\n{b.content.strip()}" for b in selected]
    return "\n\n".join(lines_buf)


class AgendaMinutesAgent:
    """议程驱动型会议纪要 Agent（免分类通用四要素与绝对骨架锁定）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> AgendaMinutes:
        agenda_raw, transcript = _extract_agenda_and_transcript(shared_context)

        # 1. 议程大盘解析：Fail-Fast 坚决不反向扫描转写（支持 transcript 人名校对）
        plan = parse_agenda_text(agenda_raw, transcript=transcript)
        if not plan.items:
            raise ValueError(
                "未能从输入文档中解析出会前既定议程单（请提供包含序号和议题名称的标准文档或清晰图片）。"
            )

        # 2. 发言人双向锚定对齐
        alignment_res = align_agenda_with_transcript(plan, transcript)
        align_log = [
            f"[AGENDA_ALIGNMENT] 现场研讨对齐结果汇总 (有效讨论: {alignment_res.discussed_count}, 未讨论/跳过: {alignment_res.skipped_count}):"
        ]
        for align in alignment_res.alignments:
            status_tag = "【有效讨论】" if align.status == "discussed" else "【未讨论/跳过】"
            speakers = ", ".join(align.matched_speakers) if align.matched_speakers else "无匹配发言"
            pres_str = ", ".join(align.item.presenters) if align.item.presenters else "无"
            align_log.append(
                f"  {status_tag} 议题 {align.item.seq} 《{align.item.title}》 | 既定汇报人: [{pres_str}] | 现场发言人: [{speakers}] (命中讨论块: {len(align.matched_blocks)})"
            )
        logger.info("\n".join(align_log))


        # 3. 动态检测会议类型（退居幕后的 9 大类型导师）并装配单议题 Prompt
        type_spec = detect_agenda_type(
            theme=plan.meta.theme or "",
            context=transcript[:_TYPE_DETECT_TRANSCRIPT_CHARS],
        )
        logger.info(
            "agenda_minutes detected meeting type: %s (%s)",
            type_spec.type_name,
            type_spec.type_id,
        )
        item_system_prompt = build_single_item_prompt(type_spec)

        # 4. Map 阶段：受控并发抽取每个讨论过的议题（彻底打破单次 64K 上下文限制）
        concurrency = int(os.getenv(_CONCURRENCY_ENV, _DEFAULT_CONCURRENCY))
        semaphore = asyncio.Semaphore(concurrency)

        async def _extract_single_item(align: AgendaAlignment) -> dict[str, Any]:
            it = align.item
            pres_str = "、".join(it.presenters) if it.presenters else (it.raw_presenter or "未指定")
            async with semaphore:
                budgeted_evidence = _extract_budgeted_evidence(align, max_chars=_EVIDENCE_CHAR_BUDGET)
                user_prompt = (
                    f"【既定议题基本信息】：\n"
                    f"- 议程序号：{it.seq}\n"
                    f"- 法定议题全称：{it.title}\n"
                    f"- 议程指定汇报人：{pres_str}\n"
                    f"- 现场出场发言人：{', '.join(align.matched_speakers[:8])}\n\n"
                    f"【现场实录切片（真实发言原声）】：\n"
                    f"{budgeted_evidence}"
                )
                try:
                    res = await self.client.structured(
                        item_system_prompt,
                        user_prompt,
                        SingleAgendaItemModel,
                        SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT,
                        label=f"agenda_minutes/item_{it.seq}",
                        max_tokens=_ITEM_MAX_TOKENS,
                    )
                    extracted = res.__dict__ if hasattr(res, "__dict__") else dict(res)
                except Exception as exc:
                    logger.warning("议题 %s 并发抽取异常，使用保底降级: %s", it.seq, exc)
                    extracted = {
                        "presenter": pres_str,
                        "status_tag": "审议通过",
                        "target_and_audience": [f"既定议题审议：{it.title}"],
                        "content_and_evidence": [],
                        "process_and_interaction": [],
                        "conclusion_and_status": "",
                        "action_items": [],
                        "proposal_highlights": [f"既定议题审议：{it.title}"],
                        "deliberation_details": {"key_metrics": [], "feedback_concerns": []},
                        "resolution": "",
                        "action_commitments": [],
                    }
                extracted["agenda_seq"] = it.seq
                extracted["agenda_title"] = it.title
                extracted["time_range"] = _format_time_range(align.matched_blocks)
                extracted["discussion_state"] = "discussed"
                return extracted

        # 并发抽取所有 discussed 项，严格遵从现场讨论时序（skipped 项由状态机判定，零 Token 调用）
        discussed_alignments = [a for a in alignment_res.chronological_alignments if a.status == "discussed"]
        extracted_map: dict[str, dict[str, Any]] = {}
        if discussed_alignments:
            results = await asyncio.gather(*[_extract_single_item(a) for a in discussed_alignments])
            for r in results:
                seq_key = str(r.get("agenda_seq") or "").strip()
                if seq_key.isdigit():
                    seq_key = f"{int(seq_key):02d}"
                extracted_map[seq_key] = r

        # 5. Reduce 阶段：组装并强制锁定议题骨架与现场时序
        raw_draft = {
            "meeting_meta": {
                "theme": plan.meta.theme or "商用发布与关键技术议题审议会",
                "date_time": plan.meta.date_time or "2026年度会议",
                "attendees_summary": plan.meta.attendees or "全体与会人",
                "agenda_stats": (
                    f"既定议题共 {len(plan.items)} 项（有效审议 {alignment_res.discussed_count} 项 · "
                    f"本次未讨论 {alignment_res.skipped_count} 项）"
                ),
            },
            "agenda_items": list(extracted_map.values()),
            "adhoc_items": [],
        }

        # 6. 后置硬约束锁定（议程序号与标题100%忠实原案，未讨论要素强制留空）
        enforced = self._enforce_agenda_invariants(raw_draft, alignment_res)

        return AgendaMinutes.validate(enforced)

    def _enforce_agenda_invariants(
        self,
        raw: AgendaMinutes | dict,
        alignment_res: AlignmentResult,
    ) -> dict[str, Any]:
        """后置强约束：议题序号、标题与跳过状态 100% 遵从会前议程单与对齐引擎判定。"""
        data = raw if isinstance(raw, dict) else (raw.__dict__ if hasattr(raw, "__dict__") else {})
        plan = alignment_res.plan

        meeting_meta = dict(data.get("meeting_meta") or {})
        if not meeting_meta.get("theme"):
            meeting_meta["theme"] = plan.meta.theme or "商用发布与关键技术议题审议会"
        if not meeting_meta.get("date_time"):
            meeting_meta["date_time"] = plan.meta.date_time or "2026年度会议"
        if not meeting_meta.get("attendees_summary") and plan.meta.attendees:
            meeting_meta["attendees_summary"] = plan.meta.attendees
        if not meeting_meta.get("agenda_stats"):
            meeting_meta["agenda_stats"] = (
                f"既定议题共 {len(plan.items)} 项（有效审议 {alignment_res.discussed_count} 项 · "
                f"本次未讨论 {alignment_res.skipped_count} 项）"
            )

        raw_items_map = {}
        for item in (data.get("agenda_items") or []):
            if isinstance(item, dict):
                seq_key = str(item.get("agenda_seq") or "").strip()
                if seq_key.isdigit():
                    seq_key = f"{int(seq_key):02d}"
                raw_items_map[seq_key] = item

        # 建立严格按现场讨论时序（先讨论在前，未讨论置底）的议程输出列表
        enforced_agenda_items: list[dict[str, Any]] = []

        for align in alignment_res.chronological_alignments:
            it = align.item
            seq = it.seq
            raw_match = raw_items_map.get(seq) or {}
            pres_str = "、".join(it.presenters) if it.presenters else (it.raw_presenter or "")

            if align.status == "skipped":
                # 零证据确定性置空：不写要点、不写决议、不写「建议顺延」，要素彻底留空
                enforced_item = {
                    "agenda_seq": seq,
                    "agenda_title": it.title,  # 100% 遵从 txt 法定原案
                    "presenter": pres_str,
                    "status_tag": "本次未讨论",
                    "time_range": "—",
                    # 1~5 栏纯干货直出
                    "target_and_audience": [],
                    "content_and_evidence": [],
                    "process_and_interaction": [],
                    "conclusion_and_status": "",
                    "action_items": [],
                    # 向上兼容旧字段
                    "proposal_highlights": [],
                    "deliberation_details": {
                        "key_metrics": [],
                        "feedback_concerns": [],
                    },
                    "resolution": "",
                    "action_commitments": [],
                    "discussion_state": "skipped",
                }
            else:
                # 讨论过：血肉遵从实录提炼，骨架锁定 txt 标题
                delib = raw_match.get("deliberation_details") or {}
                if not isinstance(delib, dict):
                    delib = {"key_metrics": [], "feedback_concerns": []}

                status_tag = normalize_status_tag(raw_match.get("status_tag"), is_skipped=False)
                if not status_tag or status_tag == "本次未讨论":
                    status_tag = "审议通过"

                actual_pres = str(raw_match.get("presenter") or "").strip()
                if not actual_pres or actual_pres == "未记录":
                    actual_pres = pres_str

                time_range = _format_time_range(align.matched_blocks)
                if time_range == "—" and raw_match.get("time_range"):
                    time_range = str(raw_match["time_range"]).strip() or "—"

                # 1. 目标与对象
                target = list(
                    raw_match.get("target_and_audience")
                    or raw_match.get("proposal_highlights")
                    or [f"既定议题审议：{it.title}"]
                )

                # 2. 内容与依据
                content_raw = raw_match.get("content_and_evidence")
                if isinstance(content_raw, list) and content_raw:
                    content = list(content_raw)
                elif isinstance(content_raw, dict):
                    content = list(content_raw.get("key_metrics") or []) + list(content_raw.get("facts_and_options") or [])
                else:
                    content = list(delib.get("key_metrics") or [])

                # 3. 过程与互动
                process_raw = raw_match.get("process_and_interaction")
                if isinstance(process_raw, list) and process_raw:
                    process = list(process_raw)
                elif isinstance(process_raw, dict):
                    process = list(process_raw.get("feedback_concerns") or []) + list(process_raw.get("focus_debates") or [])
                else:
                    process = list(delib.get("feedback_concerns") or [])

                # 4. 结论与状态
                conclusion = str(
                    raw_match.get("conclusion_and_status")
                    or raw_match.get("resolution")
                    or ""
                ).strip()

                # 5. 行动与效果
                actions = list(
                    raw_match.get("action_items")
                    or raw_match.get("action_commitments")
                    or []
                )

                enforced_item = {
                    "agenda_seq": seq,
                    "agenda_title": it.title,  # 100% 遵从 txt 法定原案
                    "presenter": actual_pres,
                    "status_tag": status_tag,
                    "time_range": time_range,
                    # 1~5 栏纯干货直出
                    "target_and_audience": target,
                    "content_and_evidence": content,
                    "process_and_interaction": process,
                    "conclusion_and_status": conclusion,
                    "action_items": actions,
                    # 向上兼容旧字段
                    "proposal_highlights": target,
                    "deliberation_details": {
                        "key_metrics": content,
                        "feedback_concerns": process,
                    },
                    "resolution": conclusion,
                    "action_commitments": actions,
                    "discussion_state": "discussed",
                }

            enforced_agenda_items.append(enforced_item)

        return {
            "meeting_meta": meeting_meta,
            "agenda_items": enforced_agenda_items,
            "adhoc_items": [],
        }
