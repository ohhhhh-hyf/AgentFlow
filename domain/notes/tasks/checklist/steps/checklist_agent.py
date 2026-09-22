from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from tools.llm import LLMClient

from ....models import Checklist
from ..assemble import assemble_checklist
from ..contracts import CHECKLIST_GENERATION_OUTPUT_CONTRACT
from ..gather import build_checklist_briefing, load_session
from ..prompts import CHECKLIST_GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(str(os.getenv(name) or default).strip())
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def batch_size() -> int:
    """每批卡片数（``CHECKLIST_LLM_BATCH_SIZE``，默认 9）。

    容量按契约字段预算反推：S 档每卡 ≈ 5 条 facts + 4-6 步 + 260 字 explain
    ≈ 600-800 tokens 输出，9 张 ≈ 5-7k tokens，稳在单次输出上限之内。
    """
    return _env_int("CHECKLIST_LLM_BATCH_SIZE", 9, 1, 40)


def batch_parallel() -> int:
    """并行批次数（``CHECKLIST_LLM_PARALLEL``，默认 4，与 OCR/模型并发口径一致）。"""
    return _env_int("CHECKLIST_LLM_PARALLEL", 4, 1, 16)


def _batch_token_budget(rows: list[dict[str, Any]]) -> int:
    """按**批内实际档位与条目数**给动态输出预算（不再固定 10000）。

    每卡预算 = 基础（字段骨架）+ explain 字数预算 + 条目数预算；
    S 档写得长、B/C 写得短，所以预算按档位累加而不是 ×N。
    """
    per_card_s = _env_int("CHECKLIST_TOKENS_PER_CARD_S", 900, 300, 3000)
    per_card_a = _env_int("CHECKLIST_TOKENS_PER_CARD_A", 700, 300, 3000)
    budget = 0
    for row in rows:
        grade = str(row.get("session_priority") or "A")
        budget += per_card_a if grade == "A" else per_card_s
    return max(1200, min(16000, budget + 400))  # 余量 + 上限保护


def _chunk(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


class ChecklistAgent:
    """Catalog 定范围；有老师文本则激活重点，否则按目录+知识库写卡片。

    调用结构（D1/D2）：待写卡（S/A + 老师点名）按固定容量**切批并行**——
    单次模型输出有硬上限、而卡片数随目录规模无上限，所以既不能"一次全量"（必然截断，
    实测 43 张卡要 20k-36k tokens、远超上限，触发截断→减半→再请求，端到端 3 分钟），
    也不该为了省时间**少写卡**（覆盖是产品承诺）。切批后每批用**动态 max_tokens**
    （批内档位预算之和），正常情况一次到位；某批失败只降级该批（程序合成），不追加轮次。
    卡片集合始终等于激活集合（程序逐行出卡），精写与否不影响覆盖。
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Checklist:
        catalog, activated, teacher = load_session(shared_context)
        empty = {
            "course": "",
            "catalog_version": "",
            "cards": [],
            "uncertain_quotes": ["没有可用的知识目录，请先运行 catalog"],
            "strategy": [],
            "phases": [],
        }
        if not catalog:
            return Checklist.validate(empty)

        # 模型撰写范围：高优先卡与老师点名卡进模型；低优先未点名由程序直出
        # （与 build_checklist_briefing 的过滤规则保持一致）
        llm_rows = [
            row
            for row in activated
            if str(row.get("session_priority") or "C") in {"S", "A"} or row.get("_mentioned")
        ]
        llm_cards: dict[str, dict[str, Any]] = {}
        batches = _chunk(list(llm_rows), batch_size()) if llm_rows else []
        if batches:
            parallel = max(1, min(batch_parallel(), len(batches)))
            semaphore = asyncio.Semaphore(parallel)

            async def one_batch(index: int, batch: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]], str]:
                batch_ids = {str(row.get("id") or "").strip() for row in batch}
                budget = _batch_token_budget(batch)
                async with semaphore:
                    logger.info(
                        "checklist batch %d/%d cards=%d max_tokens=%d",
                        index, len(batches), len(batch), budget,
                    )
                    try:
                        draft = await self.client.structured(
                            CHECKLIST_GENERATION_SYSTEM_PROMPT,
                            build_checklist_briefing(catalog, batch, teacher),
                            Checklist,
                            CHECKLIST_GENERATION_OUTPUT_CONTRACT,
                            max_tokens=budget,
                            timeout=300,
                            label="checklist/agent",
                        )
                    except Exception as exc:  # noqa: BLE001 - 单批失败只降级该批（程序合成）
                        logger.warning("checklist batch %d failed, program fills it: %s", index, exc)
                        return index, [], str(exc)
                produced = [
                    card
                    for card in draft.cards or []
                    if str((card or {}).get("kp_id") or "").strip() in batch_ids
                ]
                return index, produced, ""

            results = await asyncio.gather(*(one_batch(i, b) for i, b in enumerate(batches, 1)))
            for _index, produced, _err in sorted(results, key=lambda item: item[0]):
                for card in produced:
                    kid = str(card.get("kp_id") or "").strip()
                    if kid and kid not in llm_cards:
                        llm_cards[kid] = card

        llm_draft = (
            {"course": "", "catalog_version": "", "cards": list(llm_cards.values())}
            if llm_cards
            else None
        )
        merged = assemble_checklist(catalog, activated, llm_draft, teacher)
        logger.info(
            "checklist cards=%d llm_written=%d program_written=%d batches=%d(llm_rows=%d)",
            len(merged.get("cards") or []),
            len(llm_cards),
            len(merged.get("cards") or []) - len(llm_cards),
            len(batches),
            len(llm_rows),
        )
        if llm_rows and len(llm_cards) < len(llm_rows):
            logger.warning(
                "checklist cards llm=%d/%d, rest by program",
                len(llm_cards),
                len(llm_rows),
            )
        return Checklist.validate(merged)
