"""SchemaRepairAgent —— 通用 JSON 结构修复器实现。"""
from __future__ import annotations

import asyncio

from .schema_repair_prompt import SYSTEM_PROMPT


class SchemaRepairAgent:
    """只修复 JSON 结构，不修改业务事实。

    通用组件：不绑定任何业务领域。调用方提供不合规输出、
    输出契约（模板）与校验错误，本组件返回修复后的 JSON 字符串。
    """

    def __init__(self, client) -> None:
        self.client = client

    async def run(self, invalid_output: str, contract: str, error: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    f"{SYSTEM_PROMPT}"
                    f"\n唯一合法的输出模板：\n{contract}"
                ),
            },
            {
                "role": "user",
                "content": f"校验错误：{error}\n待修复输出：\n{invalid_output}",
            },
        ]
        return await asyncio.to_thread(
            self.client._post, messages, label="schema_repair"
        )
