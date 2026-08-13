"""action_items 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类 ActionItemsGenerationContract → to_json_template() 生成生成契约 prompt
- 审阅契约类 ActionItemsSupervisorContract → to_json_template() 生成审阅契约 prompt
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class ActionItemsGenerationContract(GenerationContract):
    """待办提取输出契约。"""

    fields = [
        ObjListField("my_actions", [
            StrField("task", "以动词开头的任务描述，条件型任务写清触发条件"),
            StrField("owner", "原文明示的负责人姓名，无明确负责人时为null"),
            StrField("deadline", "原文明示的截止时间，无明确时间时为null"),
            EnumField("priority", ["high", "medium", "low"]),
            EnumField("status", ["explicit", "inferred"]),
            StrField("evidence", "原文中支撑此待办的具体语句（可直接定位）"),
            EnumField("confidence", ["high", "medium", "low"]),
        ]),
        ObjListField("delegated_actions"),
        ObjListField("unassigned_actions"),
    ]


class ActionItemsSupervisorContract(SupervisorContract):
    """待办审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check("action_items_check", "仅记录严重问题"),
    ]


ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT = ActionItemsGenerationContract.to_output_contract()
ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT = ActionItemsSupervisorContract.to_output_contract()

# 降级拼装规则（声明式类）：fallback 节点由 sync_domain.py 检测子类后生成
class ActionItemsFallbackRules(FallbackRules):
    """待办降级拼装：客观合并后逐行格式化 + 结构化 items。"""

    sections = [
        Lines(
            "my_actions",
            merge=["my_actions", "unassigned_actions"],
        ),
    ]
    empty_text = "暂无明确待办"
    structured = {"merge": ["my_actions", "unassigned_actions"]}


ACTION_ITEMS_FALLBACK_RULES = ActionItemsFallbackRules()

__all__ = [
    "ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT",
    "ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT",
    "ACTION_ITEMS_FALLBACK_RULES",
]
