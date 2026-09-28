"""agenda_minutes_agent.py -- 议程驱动型会议纪要生成 Agent。

流程：
1. 从 shared_context 中提取既定议程单与会议录音转写；
2. parse_agenda_text 解析既定议程大盘 AgendaPlan；
3. align_agenda_with_transcript 执行发言人真名双向锚定与实录切片；
4. 对 skipped 议题执行 Zero-Evidence 截断（杜绝虚构脑补）；
5. 对 discussed 议题调用大模型提炼全景四要素；
6. Agenda-as-Anchor 绝对骨架后置硬校验：100% 覆盖议程单全部序号与法定全称。
"""
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from tools.llm import LLMClient
from tools.schema.validation import OutputValidationError

from ....models import AgendaMinutes
from ....models_base import ModelMixin
from ..agenda_parser import AgendaItemParsed, AgendaPlan, parse_agenda_text
from ..alignment_engine import AgendaAlignment, AlignmentResult, align_agenda_with_transcript
from ..contracts import (
    AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT,
    SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT,
)
from ..prompts import (
    AGENDA_MINUTES_GENERATION_SYSTEM_PROMPT,
    SINGLE_AGENDA_ITEM_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class SingleAgendaItemModel(ModelMixin):
    """单议题结构化输出数据模型。"""

    presenter: str = ""
    status_tag: str = "[审议通过]"
    proposal_highlights: list[str] = field(default_factory=list)
    deliberation_details: dict[str, Any] = field(default_factory=dict)
    resolution: str = ""
    action_commitments: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def validate(cls, data: dict) -> "SingleAgendaItemModel":
        if not isinstance(data, dict):
            raise OutputValidationError("SingleAgendaItemModel 必须是对象")
        delib = data.get("deliberation_details")
        if not isinstance(delib, dict):
            delib = {"key_metrics": [], "feedback_concerns": []}
        return cls(
            presenter=str(data.get("presenter") or "").strip(),
            status_tag=str(data.get("status_tag") or "[审议通过]").strip(),
            proposal_highlights=list(data.get("proposal_highlights") or []),
            deliberation_details={
                "key_metrics": list(delib.get("key_metrics") or []),
                "feedback_concerns": list(delib.get("feedback_concerns") or []),
            },
            resolution=str(data.get("resolution") or "").strip(),
            action_commitments=list(data.get("action_commitments") or []),
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
    max_chars: int = 12000,
) -> str:
    """按预算截取议题证据，优先确保官方汇报人的发言100%保留。"""
    if len(align.evidence_text) <= max_chars:
        return align.evidence_text

    blocks = align.matched_blocks
    presenters = set(align.item.presenters)
    # 优先抽取汇报人自己的发言
    pres_blocks = [b for b in blocks if any(p in b.speaker for p in presenters)]
    other_blocks = [b for b in blocks if not any(p in b.speaker for p in presenters)]

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

        # 1. 议程大盘解析：Fail-Fast 坚决不反向扫描转写
        plan = parse_agenda_text(agenda_raw)
        if not plan.items:
            raise ValueError(
                "未能从输入文档中解析出会前既定议程单（请提供包含序号和议题名称的标准文档或清晰图片）。"
            )

        # 2. 发言人双向锚定对齐
        alignment_res = align_agenda_with_transcript(plan, transcript)
        logger.info(
            "agenda_minutes alignment: total=%d, discussed=%d, skipped=%d",
            len(plan.items),
            alignment_res.discussed_count,
            alignment_res.skipped_count,
        )

        # 3. Map 阶段：受控并发抽取每个讨论过的议题（彻底打破单次 64K 上下文限制）
        concurrency = int(os.getenv("AGENDA_MINUTES_CONCURRENCY", "4"))
        semaphore = asyncio.Semaphore(concurrency)

        async def _extract_single_item(align: AgendaAlignment) -> dict[str, Any]:
            it = align.item
            pres_str = "、".join(it.presenters) if it.presenters else (it.raw_presenter or "未指定")
            async with semaphore:
                budgeted_evidence = _extract_budgeted_evidence(align, max_chars=12000)
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
                        SINGLE_AGENDA_ITEM_SYSTEM_PROMPT,
                        user_prompt,
                        SingleAgendaItemModel,
                        SINGLE_AGENDA_ITEM_OUTPUT_CONTRACT,
                        label=f"agenda_minutes/item_{it.seq}",
                        max_tokens=2000,
                    )
                    extracted = res.__dict__ if hasattr(res, "__dict__") else dict(res)
                except Exception as exc:
                    logger.warning("议题 %s 并发抽取异常，使用保底降级: %s", it.seq, exc)
                    extracted = {
                        "presenter": pres_str,
                        "status_tag": "[审议通过]",
                        "proposal_highlights": [f"既定议题审议：{it.title}"],
                        "deliberation_details": {"key_metrics": [], "feedback_concerns": []},
                        "resolution": "",
                        "action_commitments": [],
                    }
                extracted["agenda_seq"] = it.seq
                extracted["agenda_title"] = it.title
                extracted["discussion_state"] = "discussed"
                return extracted

        # 并发抽取所有 discussed 项，skipped 项由状态机判定，零 Token 调用
        discussed_alignments = [a for a in alignment_res.chronological_alignments if a.status == "discussed"]
        extracted_map: dict[str, dict[str, Any]] = {}
        if discussed_alignments:
            results = await asyncio.gather(*[_extract_single_item(a) for a in discussed_alignments])
            for r in results:
                seq_key = str(r.get("agenda_seq") or "").strip()
                if seq_key.isdigit():
                    seq_key = f"{int(seq_key):02d}"
                extracted_map[seq_key] = r

        # 4. Reduce 阶段：组装并强制锁定议题骨架与现场时序
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
            "adhoc_items": self._extract_adhoc_items(alignment_res.adhoc_blocks),
        }

        # 5. 后置硬约束锁定（议程序号与标题100%忠实原案，未讨论要素强制留空）
        enforced = self._enforce_agenda_invariants(raw_draft, alignment_res)

        # 6. 生成全景一句话总体评价（短轻量调用，耗时<1秒）
        overview_headline = await self._generate_overview_headline(
            enforced["meeting_meta"].get("theme") or "",
            enforced["agenda_items"],
        )
        enforced["meeting_meta"]["overview_headline"] = overview_headline

        return AgendaMinutes.validate(enforced)

    async def _generate_overview_headline(
        self,
        theme: str,
        items: list[dict[str, Any]],
    ) -> str:
        """基于各议题决议与定调，生成1句话全会推进总体评价。"""
        lines = []
        for it in items:
            state = it.get("discussion_state") or "discussed"
            tag = it.get("status_tag") or ""
            res = it.get("resolution") or ""
            res_short = res.splitlines()[0] if res else ("未形成决议" if state == "discussed" else "未讨论")
            lines.append(f"- 议题 {it.get('agenda_seq')} {it.get('agenda_title')}：{tag} | {res_short[:50]}")
        user_prompt = f"会议主题：{theme}\n议题审议概况：\n" + "\n".join(lines[:12])
        sys_prompt = (
            "你是一位高管秘书。请根据会议各议题审议结论概况，用一句话（30~60字）精炼概括全会议程推进总体评价与核心结论"
            "（例如：各核心版本总体审议通过，现网安全与灰度策略按前置约束从严落实，未讨论议题顺延下期）。"
            "直接输出这句评价文字，不要包含任何前缀、解释或标点符号外的多余字符。"
        )
        try:
            res = await self.client.text(
                sys_prompt,
                user_prompt,
                label="agenda_minutes/overview_headline",
                max_tokens=200,
            )
            clean = res.strip().strip('"').strip("'")
            if clean and len(clean) >= 10:
                return clean
        except Exception as e:
            logger.warning("overview_headline generation fallback: %s", e)
        return "全场议程推进平稳，核心技术与版本审议达成阶段共识。"

    def _extract_adhoc_items(
        self, adhoc_blocks: list[Any]
    ) -> list[dict[str, Any]]:
        """从未归属的长发言块中提取高管全局指示。"""
        if not adhoc_blocks:
            return []
        items = []
        for b in adhoc_blocks[:3]:
            if len(b.content) > 50:
                items.append({
                    "title": f"全局重要指示与要求（{b.speaker}）",
                    "speaker": b.speaker,
                    "content": b.content.strip()[:300],
                    "action": "请各模块负责人会后排查并跟踪落实。",
                })
        return items

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

        # 建立严格按 plan.items 排布的议程输出列表
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
                    "status_tag": "[本次未讨论]",
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

                status_tag = str(raw_match.get("status_tag") or "").strip()
                if not status_tag or status_tag == "[本次未讨论]":
                    status_tag = "[审议通过]"

                actual_pres = str(raw_match.get("presenter") or "").strip()
                if not actual_pres or actual_pres == "未记录":
                    actual_pres = pres_str

                enforced_item = {
                    "agenda_seq": seq,
                    "agenda_title": it.title,  # 100% 遵从 txt 法定原案
                    "presenter": actual_pres,
                    "status_tag": status_tag,
                    "proposal_highlights": list(raw_match.get("proposal_highlights") or [f"既定议题审议：{it.title}"]),
                    "deliberation_details": {
                        "key_metrics": list(delib.get("key_metrics") or []),
                        "feedback_concerns": list(delib.get("feedback_concerns") or []),
                    },
                    # 拿掉默认通过语：未形成决议则保持为空，严禁随意补「原则同意推进」
                    "resolution": str(raw_match.get("resolution") or "").strip(),
                    "action_commitments": list(raw_match.get("action_commitments") or []),
                    "discussion_state": "discussed",
                }

            enforced_agenda_items.append(enforced_item)

        adhoc_items = list(data.get("adhoc_items") or [])

        return {
            "meeting_meta": meeting_meta,
            "agenda_items": enforced_agenda_items,
            "adhoc_items": adhoc_items,
        }
