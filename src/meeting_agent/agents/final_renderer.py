from __future__ import annotations

from ..client import LLMClient
from ..models import FinalReport
from ..prompts.final_renderer import (
    OUTPUT_CONTRACT,
    OUTPUT_CONTRACT_TEMPLATE,
    SYSTEM_PROMPT,
)


# 仅渲染纪要正文的 prompt（不要求 JSON，直接输出文本）
_MINUTES_ONLY_PROMPT = """你是会议纪要渲染器。根据已审核通过的会议分析结果，渲染一段连贯精简的纪要正文。

写作原则：
- 保留关键背景、数字、日期、姓名、决策和承诺，去掉流水账和套话
- 段落之间自然过渡，同一事实只出现一次，不要换个说法复述
- 目标篇幅 3-4 段，每段 3-5 句。内容偏少时 2 段即可，严禁为凑篇幅而重复或注水
- 段落之间用一个换行符分隔，严禁空行（严禁连续两个换行，严禁段落之间有空行）
- 不要写"会议讨论了""与会者认为""大家一致同意"等套话，直接陈述事实
- 不使用 Markdown 标题、编号列表、加粗或斜体
- 客观视角用第三人称，个人视角避免"你""您"
- 只输出纪要正文，不要输出 JSON、不要输出标题、不要输出任何其他内容

视角模式、会议原文、用户画像、已审核的分析结果都在下方用户消息中。"""

# 仅渲染纪要正文 + 模板格式
_MINUTES_TEMPLATE_PROMPT = """你是会议纪要渲染器。根据已审核通过的会议分析结果和下方输出模板，渲染会议纪要。

操作步骤：
1. 识别模板中的固定文字（保留）和 [描述] 占位符（需替换）
2. 替换占位符为已批准草稿中的内容，信息不足填「未提及」
3. [xxx / yyy / zzz] = 多选一，含 emoji
4. 含 [xxx] 的表格行 = 行模板，根据内容生成对应行数（表头原样保留）
5. 输出与模板逐字符对齐，仅 [xxx] 被替换
6. 严禁编造事实
7. 只输出填充后的完整内容，不要输出 JSON 包装"""


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

    async def run_minutes_only(self, approved_context: str, template: str = "") -> str:
        """仅渲染纪要正文（纯文本），不产出 JSON —— 用于并行渲染节点。"""
        template = template or ""
        if template.strip():
            prompt = _MINUTES_TEMPLATE_PROMPT
            user = (
                f"{approved_context}\n\n"
                f"══════════════ 【输出模板】 ══════════════\n"
                f"{template}\n"
                f"══════════════════════════════════════════"
            )
        else:
            prompt = _MINUTES_ONLY_PROMPT
            user = approved_context
        return await self.client.text(
            prompt,
            user,
        )
