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


def validate_action_roster(items: list[dict], roster: set[str]) -> list[dict]:
    """比对 owner 与在册参会人员名单，清洗幻觉人名与占位符。"""
    if not items:
        return []
    _invalid = {"null", "none", "待认领", "未分配", "待定", "待确认", "未提及", "未明确", "无", "-"}
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        it = dict(item)
        owner = str(it.get("owner") or "").strip()
        if not owner or owner.lower() in _invalid:
            it["owner"] = ""
        elif roster:
            # 允许在册人名、包含在册人名、或者带有“组/团队/部门/项目组/中台/专家组/架构/PMO/QA/DBA”等组织角色词
            is_valid = (
                owner in roster
                or any(p in owner for p in roster)
                or any(kw in owner for kw in ("组", "团队", "部门", "中台", "委员会", "室", "中心", "PMO", "QA", "DBA", "架构", "专班"))
            )
            if not is_valid:
                it["owner"] = ""
        out.append(it)
    return out


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
        """从 state 中提取最终待办列表（降级兜底用，不调 LLM，比对在册名单校验责任人）。

        客观视角：全员已分配待办 + 未分配待办；
        个人视角：仅用户本人待办。
        """
        actions = (
            (state.get("lines") or {})
            .get("actions", {})
            .get("draft")
            or {}
        )
        assigned = list(actions.get("assigned_actions") or actions.get("my_actions") or [])
        if state.get("objective_perspective"):
            items = assigned + list(actions.get("unassigned_actions") or [])
        else:
            items = assigned

        roster: set[str] = set()
        mu = state.get("meeting_understanding") or {}
        if isinstance(mu, dict):
            for p in mu.get("participants") or []:
                if isinstance(p, str) and p.strip():
                    roster.add(p.strip())
                elif isinstance(p, dict) and p.get("name"):
                    roster.add(str(p["name"]).strip())
        user_name = (state.get("user") or {}).get("name")
        if user_name and str(user_name).strip():
            roster.add(str(user_name).strip())

        return validate_action_roster(items, roster)

    @staticmethod
    def render_items(items: list[dict]) -> str:
        """把待办条目列表按业务板块（话题）归类聚合，渲染为结构化卡片清单。

        格式规范：
        1. 板块主行：{板块序号}. **[{业务板块}]**
        2. 待办列表项：   - {动词开头的具体事项} (责任人：{责任主体})
        3. 卡片属性块（条件输出）：
           - 时间节点：{时间锚点/截止节点}
           - 协同配合：{协同对象/配合方}
           - 交付验收：{验收标准/交付产物}
           - 前置依赖：{前置条件}
        """
        if not items:
            return "暂无明确待办事项"

        _invalid = {"null", "none", "无", "未提及", "未明确", "待排期", "待指定", "-", "待认领", "未分配", "待定", "待确认"}

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
                timing = str(item.get("timing_anchor") or item.get("deadline") or "").strip()
                collab = str(item.get("collaborators") or "").strip()
                acceptance = str(item.get("acceptance_criteria") or item.get("deliverable") or "").strip()
                dependency = str(item.get("dependency") or "").strip()

                if owner and owner.lower() not in _invalid:
                    topic_lines.append(f"   - {task} (责任人：{owner})")
                else:
                    topic_lines.append(f"   - {task}")

                # 条件输出属性块（有内容才输出，无内容整行隐去）
                if timing and timing.lower() not in _invalid:
                    topic_lines.append(f"     > 时间节点：{timing}")
                if collab and collab.lower() not in _invalid:
                    topic_lines.append(f"     > 协同配合：{collab}")
                if acceptance and acceptance.lower() not in _invalid:
                    topic_lines.append(f"     > 交付验收：{acceptance}")
                if dependency and dependency.lower() not in _invalid:
                    topic_lines.append(f"     > 前置依赖：{dependency}")

            topic_blocks.append("\n".join(topic_lines))

        return "\n\n".join(topic_blocks)

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段排清单，与渲染 prompt 格式一致，不调 LLM。"""
        actions = (
            (state.get("lines") or {}).get("actions", {}).get("draft") or {}
        )
        assigned_items = list(actions.get("assigned_actions") or actions.get("my_actions") or [])
        delegated_items = list(actions.get("delegated_actions") or [])
        unassigned_items = list(actions.get("unassigned_actions") or [])

        all_items = assigned_items + delegated_items + unassigned_items
        return ActionItemsRender.render_items(all_items)

    @staticmethod
    def format_action(index: int, item: dict) -> str:
        """把单条待办格式化为规范文本块。"""
        res = ActionItemsRender.render_items([item])
        if index != 1 and res.startswith("1."):
            res = f"{index}." + res[2:]
        return res


ActionItemsRender.format_action.render_items = ActionItemsRender.render_items

