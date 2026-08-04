from __future__ import annotations

from ..client import LLMClient
from ..models import FinalReport
from ..prompts.final_renderer import (
    OUTPUT_CONTRACT,
    OUTPUT_CONTRACT_TEMPLATE,
    SYSTEM_PROMPT,
)


class FinalRenderer:
    """把 Supervisor 已放行的内容渲染为最终展示结果（支持个人/客观视角和模板输出）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, approved_context: str, template: str = "") -> FinalReport:
        """渲染最终结果。template 不为空时按模板格式输出，否则自由段落。"""
        if template.strip():
            context = (
                f"{approved_context}\n\n"
                f"══════════════ 【输出模板】 ══════════════\n"
                f"{template}\n"
                f"══════════════════════════════════════════"
            )
            contract = OUTPUT_CONTRACT_TEMPLATE
        else:
            context = approved_context
            contract = OUTPUT_CONTRACT
        return await self.client.structured(
            SYSTEM_PROMPT,
            context,
            FinalReport,
            contract,
        )
