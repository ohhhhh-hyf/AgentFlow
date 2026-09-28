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

import json
import logging
import re
from typing import Any

from tools.llm import LLMClient

from ....models import AgendaMinutes
from ..agenda_parser import AgendaItemParsed, AgendaPlan, parse_agenda_text
from ..alignment_engine import AlignmentResult, align_agenda_with_transcript
from ..contracts import AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT
from ..prompts import AGENDA_MINUTES_GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


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

        # 3. 构造给 LLM 的上下文包：按议程与实录切片组织
        context_prompt_parts = []
        
        # 会议元信息
        meta_summary = plan.meta.theme or "会议审议与研讨例会"
        context_prompt_parts.append(f"【既定议程总表】（共 {len(plan.items)} 项既定议题）：")
        for it in plan.items:
            pres_str = "、".join(it.presenters) if it.presenters else (it.raw_presenter or "未指定")
            context_prompt_parts.append(f"- 议题 {it.seq}：{it.title}（汇报人：{pres_str}）")

        context_prompt_parts.append("\n【各议题实录讨论切片与证据】")
        for a in alignment_res.alignments:
            if a.status == "skipped":
                context_prompt_parts.append(
                    f"\n### 议题 {a.item.seq} · {a.item.title}\n"
                    f"【状态】：本次未讨论（录音全文未见汇报人发言及相关审议，严格标记为 skipped，禁止臆造，要素保持为空）\n"
                )
            else:
                budgeted_evidence = _extract_budgeted_evidence(a, max_chars=12000)
                context_prompt_parts.append(
                    f"\n### 议题 {a.item.seq} · {a.item.title}\n"
                    f"【出场汇报人与发言人】：{', '.join(a.matched_speakers[:8])}\n"
                    f"【现场实录切片（真实发言原声）】：\n{budgeted_evidence}\n"
                )

        if alignment_res.adhoc_blocks:
            context_prompt_parts.append("\n【议程外/尾声全局重要讨论切片（潜在临时追加指示）】：")
            adhoc_text = "\n".join(
                f"{b.speaker} {b.timestamp}\n{b.content}"
                for b in alignment_res.adhoc_blocks[:15]
            )
            context_prompt_parts.append(adhoc_text[:6000])

        assembled_input = "\n\n".join(context_prompt_parts)

        # 4. LLM 结构化生成
        raw = await self.client.structured(
            AGENDA_MINUTES_GENERATION_SYSTEM_PROMPT,
            assembled_input,
            AgendaMinutes,
            AGENDA_MINUTES_GENERATION_OUTPUT_CONTRACT,
            label="agenda_minutes/agent",
            max_tokens=4000,
        )

        # 5. Agenda-as-Anchor 骨架绝对锁定与零证据强制执行
        enforced = self._enforce_agenda_invariants(raw, alignment_res)
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

        # 建立严格按 plan.items 排布的议程输出列表
        enforced_agenda_items: list[dict[str, Any]] = []

        for align in alignment_res.alignments:
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

                enforced_item = {
                    "agenda_seq": seq,
                    "agenda_title": it.title,  # 100% 遵从 txt 法定原案
                    "presenter": pres_str or str(raw_match.get("presenter") or ""),
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
