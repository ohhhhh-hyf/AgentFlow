from __future__ import annotations

import re
from collections.abc import AsyncIterator

from infra.llm import LLMClient
from core.runner.prompt_utils import build_render_prompt

from ....models import MeetingState
from ..prompts import (
    ACTION_ITEMS_RENDER_PROMPT,
    ACTION_ITEMS_RENDER_TEMPLATE_PROMPT,
)


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
            ACTION_ITEMS_RENDER_PROMPT,
            ACTION_ITEMS_RENDER_TEMPLATE_PROMPT,
        )

    async def run(self, context: str, template: str = "") -> str:
        """整段渲染待办文本（无模板 / 有模板统一入口）。"""
        prompt, user = self._prompt_and_user(context, template)
        temp = 0.0 if (template or "").strip() else None
        try:
            return await self.client.text(
                prompt, user, temperature=temp, label="actions/render"
            )
        except TypeError:
            return await self.client.text(prompt, user, label="actions/render")

    async def stream(
        self, context: str, template: str = ""
    ) -> AsyncIterator[str]:
        """流式渲染待办文本：LLM token 逐块产出（SSE），与纪要流对称。"""
        prompt, user = self._prompt_and_user(context, template)
        async for chunk in self.client.stream_text(
            prompt, user, label="actions/render"
        ):
            yield chunk

    @staticmethod
    def extract_structure(state: MeetingState) -> list[dict]:
        """extract 种类的结构抽取入口（引擎按这个名字调用）。"""
        return ActionItemsRender.extract_actions(state)

    @staticmethod
    def extract_actions(state: MeetingState) -> list[dict]:
        """从 state 中提取最终待办列表（降级兜底用，不调 LLM）。

        客观视角：全员已分配待办 + 未分配待办；
        个人视角：仅用户本人待办。
        """
        actions = (
            (state.get("lines") or {})
            .get("actions", {})
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
    def render_items(items: list[dict]) -> str:
        """把待办条目列表按业务板块（话题）归类聚合，渲染为结构化卡片清单。

        格式规范：
        1. 板块主行：{板块序号}. **[{业务板块}]**
        2. 待办列表项：   - {动词开头的具体事项}({责任主体})
        3. 卡片属性块（条件输出）：
           - 交付时限：{截止节点}
           - 交付成果：{交付产物}
           - 前置依赖：{前置条件}
        """
        if not items:
            return "暂无明确待办事项"

        _invalid = {"null", "none", "无", "未提及", "未明确", "待排期", "待指定", "-"}

        # 1. 话题归类聚合（保持初次出现的先后顺序）
        groups: dict[str, list[dict]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            task_raw = str(item.get("task") or "").strip()
            if not task_raw:
                continue
            cat = str(item.get("category") or "").strip()
            if not cat and (task_raw.startswith("【") or task_raw.startswith("[")):
                m = re.match(r"^[【\[](.*?)[】\]](.*)$", task_raw)
                if m:
                    cat = m.group(1).strip()
            if not cat:
                cat = "综合事项"
            groups.setdefault(cat, []).append(item)

        if not groups:
            return "暂无明确待办事项"

        topic_blocks: list[str] = []
        for cat_idx, (cat, cat_items) in enumerate(groups.items(), start=1):
            topic_lines = [f"{cat_idx}. **[{cat}]**"]
            for item in cat_items:
                task_raw = str(item.get("task") or "").strip()
                # 剔除可能重复包含在 task_raw 开头的 [cat] 或【cat】
                if task_raw.startswith(f"[{cat}]"):
                    task = task_raw[len(f"[{cat}]"):].strip()
                elif task_raw.startswith(f"【{cat}】"):
                    task = task_raw[len(f"【{cat}】"):].strip()
                elif (task_raw.startswith("【") and "】" in task_raw) or (task_raw.startswith("[") and "]" in task_raw):
                    m = re.match(r"^[【\[](.*?)[】\]](.*)$", task_raw)
                    task = m.group(2).strip() if m else task_raw
                else:
                    task = task_raw

                owner = str(item.get("owner") or "").strip()
                deadline = str(item.get("deadline") or "").strip()
                deliverable = str(item.get("deliverable") or "").strip()
                dependency = str(item.get("dependency") or "").strip()

                prio_key = str(item.get("priority") or "medium").lower().strip()
                prio_map = {
                    "high": "高优先", "medium": "中优先", "low": "低优先",
                    "高": "高优先", "中": "中优先", "低": "低优先",
                    "高优先": "高优先", "中优先": "中优先", "低优先": "低优先",
                }
                prio_display = prio_map.get(prio_key, "中优先")
                owner_display = owner if (owner and owner.lower() not in _invalid) else "待认领"
                meta_display = f"{prio_display} · {owner_display}"

                topic_lines.append(f"   - {task}({meta_display})")

                # 条件输出属性块
                if deadline and deadline.lower() not in _invalid:
                    topic_lines.append(f"     > 完成时限：{deadline}")
                if deliverable and deliverable.lower() not in _invalid:
                    topic_lines.append(f"     > 交付标准：{deliverable}")
                if dependency and dependency.lower() not in _invalid:
                    topic_lines.append(f"     > 前置条件：{dependency}")

            topic_blocks.append("\n".join(topic_lines))

        return "\n\n".join(topic_blocks)

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段排清单，与渲染 prompt 格式一致，不调 LLM。"""
        actions = (
            (state.get("lines") or {}).get("actions", {}).get("draft") or {}
        )
        my_items = list(actions.get("my_actions") or [])
        delegated_items = list(actions.get("delegated_actions") or [])
        unassigned_items = list(actions.get("unassigned_actions") or [])

        all_items = my_items + delegated_items + unassigned_items
        return ActionItemsRender.render_items(all_items)

    @staticmethod
    def format_action(index: int, item: dict) -> str:
        """把单条待办格式化为规范文本块。"""
        res = ActionItemsRender.render_items([item])
        if index != 1 and res.startswith("1."):
            res = f"{index}." + res[2:]
        return res


ActionItemsRender.format_action.render_items = ActionItemsRender.render_items

