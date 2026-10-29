"""PersonalPerspective 生成契约。

与 personal_models.PersonalPerspective 的 9 字段严格一致。
不要在这里引入旧 PerspectiveModeling 的 name / responsibilities /
attention_points / relevant_topics / evidence。
"""
from __future__ import annotations

from core.schema.contracts import (
    EnumField,
    GenerationContract,
    StrField,
    StrListField,
)

PERSONAL_PROFILE_FIELDS = (
    "name",
    "name_aliases",
    "role",
    "focus_person",
    "focus_thing",
    "preferences",
)

PERSONAL_UNDERSTANDING_FIELDS = (
    "meeting_brief",
    "meeting_purpose",
    "speakers",
    "session_segments",
    "decisions",
    "open_questions",
    "risks",
)

PERSONAL_DRAFT_UNDERSTANDING_FIELDS = (
    "meeting_brief",
    "speakers",
    "session_segments",
    "decisions",
)


class PersonalPerspectiveGenerationContract(GenerationContract):
    """个人视角建模输出契约。"""

    fields = [
        EnumField(
            "confidence",
            ["high", "medium", "low"],
            "整体置信度：证据充分且关键字段有据为 high；部分推断为 medium；"
            "证据包过少/fallback/仅全局背景为 low",
        ),
        StrField(
            "personal_summary",
            "100–150 字本人视角概览：本人核心战线、关键结论与上下游协同卡点；"
            "可被下游直接引用；无依据写空串",
        ),
        StrListField(
            "focus_points",
            "与本人直接相关的议题、事实、指标、重点人物/标的要点；"
            "不得把全场议题平铺进来",
        ),
        StrListField(
            "possible_actions",
            "本人承诺、被指派、主动认领的动作；写清事项、交付物与时限；"
            "不得把建议、讨论或他人任务写成本人行动",
        ),
        StrListField(
            "collaborations",
            "他人对本人工作的承诺、输入与协同依赖；写清姓名与节点；"
            "不得写成本人行动",
        ),
        StrListField(
            "concerns",
            "影响本人交付的内部技术隐患、交付风险与不确定性；不写全局风险",
        ),
        StrListField(
            "data_gaps",
            "外部依赖断供、缺物料/接口/配置导致本人交付受阻的卡点",
        ),
        StrListField(
            "focus_risks",
            "重点关注人物/标的的风险、定调隐患与波及面",
        ),
        StrListField(
            "open_questions",
            "本人会后需拉通、待确认、悬而未决的事项；写清协同对象与预期结果",
        ),
    ]


PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT = (
    PersonalPerspectiveGenerationContract.to_output_contract()
)


__all__ = [
    "PERSONAL_PROFILE_FIELDS",
    "PERSONAL_UNDERSTANDING_FIELDS",
    "PERSONAL_DRAFT_UNDERSTANDING_FIELDS",
    "PersonalPerspectiveGenerationContract",
    "PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT",
]
