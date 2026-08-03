from __future__ import annotations

import asyncio


class SchemaRepairAgent:
    """只修复 JSON 结构，不修改业务事实。"""

    def __init__(self, client) -> None:
        self.client = client

    async def run(self, invalid_output: str, contract: str, error: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 SchemaRepairAgent，只能修复 JSON 结构和字段类型。"
                    "不得增加、删除、推断或改写任何业务事实。"
                    "只输出 JSON，不要输出 Markdown。"
                    f"\n唯一合法的输出模板：\n{contract}"
                ),
            },
            {
                "role": "user",
                "content": f"校验错误：{error}\n待修复输出：\n{invalid_output}",
            },
        ]
        return await asyncio.to_thread(self.client._post, messages)
