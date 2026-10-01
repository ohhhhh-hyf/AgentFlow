from __future__ import annotations

from domains.shared.supervisor import StructuredGenerationAgent

from ....models import Risk
from ..contracts import RISK_GENERATION_OUTPUT_CONTRACT
from ..prompts import RISK_GENERATION_SYSTEM_PROMPT


class RiskAgent(StructuredGenerationAgent):
    """从会议中提取风险、阻碍和隐患。"""

    system_prompt = RISK_GENERATION_SYSTEM_PROMPT
    output_model = Risk
    output_contract = RISK_GENERATION_OUTPUT_CONTRACT
    # 注意：label 是 risk/ 而不是 risks/（历史拼写，改名会变监控口径）
    label = "risk/agent"
