from __future__ import annotations

from collections.abc import AsyncIterator

from llm_client import LLMClient
from tools.prompt_utils import build_render_prompt

from ....models import MeetingState
from ..prompts import ITEM_RENDER_PROMPT, ITEM_RENDER_TEMPLATE_PROMPT


class ActionItemsRender:
    """把已批准的待办提取结果渲染为最终输出（与纪要渲染对称）。

    - 无模板：LLM 渲染待办清单文本
    - 有模板：LLM 按模板渲染文本（模板拼进用户消息）
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @staticmethod
    def _prompt_and_user(context: str, template: str) -> tuple[str, str]:
        """按是否提供模板选择渲染 prompt（与纪要渲染共用同一规则）。"""
        return build_render_prompt(
            context,
            template,
            ITEM_RENDER_PROMPT,
            ITEM_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, context: str, template: str = "") -> str:
        """整段渲染待办文本（无模板 / 有模板统一入口）。"""
        prompt, user = self._prompt_and_user(context, template)
        return await self.client.text(prompt, user)

    async def stream(
        self, context: str, template: str = ""
    ) -> AsyncIterator[str]:
        """流式渲染待办文本：LLM token 逐块产出（SSE），与纪要流对称。"""
        prompt, user = self._prompt_and_user(context, template)
        async for chunk in self.client.stream_text(prompt, user):
            yield chunk

    @staticmethod
    def extract_actions(state: MeetingState) -> list[dict]:
        """从 state 中提取最终待办列表（降级兜底用，不调 LLM）。

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

    @staticmethod
    def format_action(index: int, item: dict) -> str:
        """把一条待办格式化为文本行（确定性降级输出用）。"""
        _prio = {"high": "高优先", "medium": "中优先", "low": "低优先"}
        meta = []
        prio = item.get("priority", "")
        if prio and prio in _prio:
            meta.append(_prio[prio])
        if item.get("owner"):
            meta.append(f"负责人：{item['owner']}")
        if item.get("deadline"):
            meta.append(f"截止：{item['deadline']}")
        suffix = f"（{'；'.join(meta)}）" if meta else ""
        return f"{index}. {item['task']}{suffix}"
