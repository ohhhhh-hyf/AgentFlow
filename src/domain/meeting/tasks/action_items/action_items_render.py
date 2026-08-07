from __future__ import annotations

import json
from collections.abc import AsyncIterator

from llm_client import LLMClient

from ...models import MeetingState
from .prompts import ITEM_RENDER_TEMPLATE_PROMPT


class ActionItemsRender:
    """把已批准的待办提取结果渲染为最终输出。

    - 无模板（--item_template 未指定）：确定性格式化列表，不调 LLM
    - 有模板：把待办结果 + 模板原样拼进 prompt，由 LLM 按模板渲染文本
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def extract_actions(state: MeetingState) -> list[dict]:
        """从 state 中提取最终待办列表。

        客观视角：全员已分配待办 + 未分配待办；
        个人视角：仅用户本人待办。
        """
        actions = (
            (state.get("lines") or {})
            .get("action_items", {})
            .get("draft")
            or {}
        )
        if state.get("objective_perspective"):
            items = list(actions.get("my_actions") or [])
            items.extend(actions.get("unassigned_actions") or [])
        else:
            items = list(actions.get("my_actions") or [])
        return items

    def format(self, state: MeetingState) -> list[dict]:
        """输出最终待办列表（等价于 extract_actions 的稳定入口）。"""
        return self.extract_actions(state)

    @staticmethod
    def _context(state: MeetingState) -> str:
        mode = "objective" if state.get("objective_perspective") else "personal"
        items = ActionItemsRender.extract_actions(state)
        return (
            f"视角模式：{mode}\n\n"
            f"已批准待办事项列表：\n"
            f"{json.dumps(items, ensure_ascii=False, indent=2)}"
        )

    async def render_with_template(
        self, state: MeetingState, template: str
    ) -> str:
        """LLM 按待办模板渲染待办输出（模板原样拼进用户消息，整段返回）。"""
        template = template or ""
        if not template.strip():
            raise ValueError("item_template 为空")
        user = f"{self._context(state)}\n\n{template}"
        return await self.client.text(ITEM_RENDER_TEMPLATE_PROMPT, user)

    async def stream_with_template(
        self, state: MeetingState, template: str
    ) -> AsyncIterator[str]:
        """流式渲染待办输出：LLM token 逐块产出（SSE），与纪要流对称。"""
        template = template or ""
        if not template.strip():
            raise ValueError("item_template 为空")
        user = f"{self._context(state)}\n\n{template}"
        async for chunk in self.client.stream_text(
            ITEM_RENDER_TEMPLATE_PROMPT, user
        ):
            yield chunk
