from __future__ import annotations

from llm_client import LLMClient
from tools.rag import build_rag_reference_from_text

from ....models import Risk
from ..contracts import RISK_GENERATION_OUTPUT_CONTRACT
from ..prompts import RISK_GENERATION_SYSTEM_PROMPT

# 风险信号关键词：从会议上下文提取信号句作 RAG query（检索历史风险案例）
RISK_KEYWORDS = [
    "风险", "隐患", "担心", "怕", "波动", "不确定", "卡住", "受阻",
    "不够", "紧张", "延迟", "超时", "过期", "损坏", "倒灌", "开裂",
    "阻塞", "安全", "待定", "未明确", "依赖",
]


class RiskAgent:
    """从会议中提取风险、阻碍和隐患（生成前参考 RAG 历史风险案例库）。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Risk:
        # RAG 检索历史风险案例 → 拼【外部参考】段（失败/未启用自动返回空串，不阻塞）
        rag_reference = await build_rag_reference_from_text(
            "meeting", "risk", shared_context, RISK_KEYWORDS
        )
        user_prompt = (
            f"{shared_context}\n\n{rag_reference}" if rag_reference else shared_context
        )
        return await self.client.structured(
            RISK_GENERATION_SYSTEM_PROMPT,
            user_prompt,
            Risk,
            RISK_GENERATION_OUTPUT_CONTRACT,
        )
