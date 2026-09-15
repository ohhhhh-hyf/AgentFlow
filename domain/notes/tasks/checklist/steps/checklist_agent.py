from __future__ import annotations

import logging
from typing import Any

from client import LLMClient

from ....models import Checklist
from ..assemble import assemble_checklist
from ..contracts import CHECKLIST_GENERATION_OUTPUT_CONTRACT
from ..gather import build_checklist_briefing, load_session
from ..prompts import CHECKLIST_GENERATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# 分批轮次上限：单轮产出会随规模自然收敛，此值只防异常死循环
_MAX_BATCH_ROUNDS = 64


class ChecklistAgent:
    """Catalog 定范围；有老师文本则激活重点，否则按目录+知识库写卡片。

    生成采用容量自适应分批：单次模型输出有硬上限，而待写卡片数随目录规模
    增长无上限——把待写卡分成多轮，每轮只请求仍未覆盖的卡，批次大小按上一轮
    实际产出自行校准（产出少于请求 = 超出容量，下一轮收窄），直到全部覆盖或
    收敛到单张仍失败（此时整卡列表交给程序兜底）。任何规模的目录都能完整出卡，
    每张卡都优先由模型撰写。
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
        todo = list(llm_rows)
        cap: int | None = None  # 本轮批次上限；None = 首轮尝试全部剩余
        for _ in range(_MAX_BATCH_ROUNDS):
            if not todo:
                break
            batch = todo if cap is None else todo[: max(1, cap)]
            batch_ids = {str(row.get("id") or "").strip() for row in batch}
            try:
                draft = await self.client.structured(
                    CHECKLIST_GENERATION_SYSTEM_PROMPT,
                    build_checklist_briefing(catalog, batch, teacher),
                    Checklist,
                    CHECKLIST_GENERATION_OUTPUT_CONTRACT,
                    max_tokens=10000,
                    timeout=300,
                    label="checklist/agent",
                )
            except Exception as exc:  # noqa: BLE001 - 单轮失败降级：余卡交程序兜底
                logger.warning(
                    "checklist llm output failed (cards %d/%d), rest by program: %s",
                    len(llm_cards),
                    len(llm_rows),
                    exc,
                )
                break
            produced = 0
            for card in draft.cards or []:
                kid = str((card or {}).get("kp_id") or "").strip()
                if kid and kid in batch_ids and kid not in llm_cards:
                    llm_cards[kid] = card
                    produced += 1
            todo = [row for row in todo if str(row.get("id") or "").strip() not in llm_cards]
            if not todo:
                break
            if produced > 0:
                cap = produced  # 自校准：实测容量内能完整产出的数量
            else:
                # 本轮零产出（截断过早或输出不合规）：批次减半重试，避免原地空转
                cap = max(1, len(batch) // 2) if cap is None else max(1, cap // 2)
                if cap == 1 and produced == 0:
                    break

        llm_draft = (
            {"course": "", "catalog_version": "", "cards": list(llm_cards.values())}
            if llm_cards
            else None
        )
        merged = assemble_checklist(catalog, activated, llm_draft, teacher)
        if llm_draft is not None and len(llm_cards) < len(llm_rows):
            logger.warning(
                "checklist cards llm=%d/%d, rest by program",
                len(llm_cards),
                len(llm_rows),
            )
        return Checklist.validate(merged)
