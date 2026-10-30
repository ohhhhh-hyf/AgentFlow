from __future__ import annotations

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
        """从 state 中提取最终扁平待办列表（降级兜底用，不调 LLM）。"""
        actions = (
            (state.get("lines") or {})
            .get("actions", {})
            .get("draft")
            or {}
        )
        items = list(actions.get("actions") or [])
        # actions 不消费会议理解；只清理占位符 owner，不按参会名单推断人名。
        return validate_action_roster(items, set())

    @staticmethod
    def render_items(items: list[dict]) -> str:
        """把扁平待办条目渲染为无序号块式清单。

        格式：
        **{title}**： {item}（责任方：{owner}）
         - 协同配合：{collaborators}
         - 时间节点：{deadline}
         - 前置依赖：{dependency}
         - 交付验收：{acceptance_criteria}
        """
        if not items:
            return "暂无明确待办事项"

        _invalid = {
            "null",
            "none",
            "无",
            "未提及",
            "未明确",
            "待排期",
            "待指定",
            "-",
            "待认领",
            "未分配",
            "待定",
            "待确认",
        }

        valid: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            body = str(item.get("item") or "").strip()
            if not body:
                continue
            valid.append(item)

        if not valid:
            return "暂无明确待办事项"

        blocks: list[str] = []
        for item in valid:
            title = str(item.get("title") or "").strip().strip("*").strip()
            body = str(item.get("item") or "").strip()
            if not title:
                title = body

            owner = str(item.get("owner") or "").strip()
            deadline = str(item.get("deadline") or "").strip()
            collab_raw = item.get("collaborators")
            if isinstance(collab_raw, (list, tuple)):
                collab = "、".join(
                    str(v).strip() for v in collab_raw if str(v).strip()
                )
            else:
                collab = str(collab_raw or "").strip()
            acceptance = str(item.get("acceptance_criteria") or "").strip()
            dependency = str(item.get("dependency") or "").strip()

            lines = [f"**{title}**： {body}"]
            if owner and owner.lower() not in _invalid:
                lines[0] += f"（责任方：{owner}）"
            if collab and collab.lower() not in _invalid:
                lines.append(f" - 协同配合：{collab}")
            if deadline and deadline.lower() not in _invalid:
                lines.append(f" - 时间节点：{deadline}")
            if dependency and dependency.lower() not in _invalid:
                lines.append(f" - 前置依赖：{dependency}")
            if acceptance and acceptance.lower() not in _invalid:
                lines.append(f" - 交付验收：{acceptance}")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    @staticmethod
    def render_draft(state: dict) -> str:
        """无模板时按草稿字段排清单，与渲染 prompt 格式一致，不调 LLM。"""
        actions = (
            (state.get("lines") or {}).get("actions", {}).get("draft") or {}
        )
        return ActionItemsRender.render_items(list(actions.get("actions") or []))

    @staticmethod
    def format_action(index: int, item: dict) -> str:
        """把单条待办格式化为规范文本块。"""
        res = ActionItemsRender.render_items([item])
        if index != 1 and res.startswith("1."):
            res = f"{index}." + res[2:]
        return res


ActionItemsRender.format_action.render_items = ActionItemsRender.render_items

