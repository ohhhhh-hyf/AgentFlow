"""actions 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类 ActionItemsGenerationContract → to_json_template() 生成生成契约 prompt
- 审阅契约类 ActionItemsSupervisorContract → to_json_template() 生成审阅契约 prompt
"""
from __future__ import annotations

from core.schema.contracts import (
    Check, Decision, Feedback, GenerationContract, ObjListField,
    StrField, StrListField, SupervisorContract,
)
from core.schema.fallback_rules import FallbackRules, Lines


# 待办只做客观输出：单一扁平 actions 数组，每条 8 字段。
# assigned/unassigned 由 owner 是否为 null 在展示层派生。
ACTIONS_OBJECTIVE_OUTPUT_FIELDS = ("actions",)
ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES = (
    "title",
    "item",
    "owner",
    "deadline",
    "collaborators",
    "acceptance_criteria",
    "dependency",
    "evidence",
)
ACTIONS_OBJECTIVE_REMOVED_ITEM_FIELDS = (
    "category",
    "task",
    "timing_anchor",
    "deliverable",
    "status",
    "confidence",
)
ACTIONS_OBJECTIVE_REMOVED_OUTPUT_FIELDS = (
    "assigned_actions",
    "unassigned_actions",
    "my_actions",
    "delegated_actions",
)

ACTION_ITEM_FIELDS = [
    StrField("title", "item 的展示小标题；不包含 deadline，不引入新事实"),
    StrField("item", "剥离 deadline 后的可执行待办正文"),
    StrField("owner", "原文明示的负责人姓名/团队；未明示为null"),
    StrField("deadline", "原文明示的截止时间；保留原文表达，未明示为null"),
    StrListField("collaborators", "原文提到的协同对象/配合方；每个元素一个对象；未提及为空数组"),
    StrField("acceptance_criteria", "原文明示的验收标准、完成判定或交付物；未提及为null"),
    StrField("dependency", "原文明示的前置条件或前置动作；无明确前后制约为null"),
    StrField("evidence", "原文或actions_text中支撑此待办的可定位摘录"),
]


class ActionItemsGenerationContract(GenerationContract):
    """客观视角待办输出契约：单一扁平 actions 数组。"""

    fields = [
        ObjListField("actions", ACTION_ITEM_FIELDS),
    ]


class ActionItemsSupervisorContract(SupervisorContract):
    """待办审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("actions_check", "仅记录严重问题"),
    ]


ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT = (
    ActionItemsGenerationContract.to_output_contract()
)
ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT = (
    ActionItemsGenerationContract.to_output_contract()
)
ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT = ActionItemsSupervisorContract.to_output_contract()

# 降级拼装规则（声明式类）：fallback 节点由 sync_domain.py 检测子类后生成
class ActionItemsFallbackRules(FallbackRules):
    """待办降级拼装：扁平 actions 逐行格式化 + 结构化 items。"""

    sections = [Lines("actions")]
    empty_text = "暂无明确待办事项"
    structured = {"merge": ["actions"]}


ACTION_ITEMS_FALLBACK_RULES = ActionItemsFallbackRules()

__all__ = [
    "ACTIONS_OBJECTIVE_OUTPUT_FIELDS",
    "ACTIONS_OBJECTIVE_ITEM_FIELD_NAMES",
    "ACTIONS_OBJECTIVE_REMOVED_ITEM_FIELDS",
    "ACTIONS_OBJECTIVE_REMOVED_OUTPUT_FIELDS",
    "ACTION_ITEM_FIELDS",
    "ActionItemsGenerationContract",
    "ACTION_ITEMS_OBJECTIVE_GENERATION_OUTPUT_CONTRACT",
    "ACTION_ITEMS_GENERATION_OUTPUT_CONTRACT",
    "ACTION_ITEMS_SUPERVISOR_OUTPUT_CONTRACT",
    "ACTION_ITEMS_FALLBACK_RULES",
]
