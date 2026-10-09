"""meeting_core 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类（MeetingUnderstandingGenerationContract 等）→ to_json_template() 生成 prompt 常量
- 审阅契约类（无：core 是公共底座，没有 supervisor）
- build_core_contract_for_tasks：根据激活的任务线动态组装输出 Schema，消除空列表裁剪 hack
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from core.schema.contracts import (
    EnumField, Field, GenerationContract, ObjListField, StrField, StrListField,
)


# ── 会议场景枚举（公共底座，下游共享）───────────────────────────
SCENE_CHOICES = [
    "通用",
    "团队例会",
    "脑暴/讨论",
    "项目决策与评审",
    "专项讨论会",
    "研讨会",
    "采访/对话",
]

# ── 行动线索类型枚举（公共底座，待办线消费）─────────────────────
ACTION_HINT_KINDS = [
    "commitment",
    "assignment",
    "directive",
    "rectification",
    "followup",
]

# ── 风险信号类型枚举（公共底座，风险线消费）─────────────────────
RISK_SIGNAL_TYPES = [
    "time",
    "resource",
    "staffing",
    "quality",
    "dependency",
    "external",
    "scope",
    "other",
]


# ── 基础与可选字段定义 ──────────────────────────────────────────

CORE_BASE_FIELDS: list[Field] = [
    StrField("meeting_brief", "80~200字概括整场会议主线全貌与核心态势"),
    StrField("meeting_purpose", "一句话概括会议目的"),
    EnumField("scene", SCENE_CHOICES, normalize="通用"),
    ObjListField("speakers", [
        StrField("name", "统一显示称呼：姓名优先，其次原文角色，再次原始编号；不推断、不编造"),
        StrField("role", "角色（发言人/主持人/记者/听众/嘉宾/主讲人…，照原文；判断不出为null）"),
        StrField("org", "机构/单位/媒体名（照原文；没有为null）"),
    ]),
    ObjListField("topics", [
        StrField("module", "所属宏观业务领域/模块（如'核心架构优化'、'现场实体整改'、'交付与验收'，全场收敛为3~5个）"),
        StrField("title", "议题名称/核心命题"),
        StrField("discussion", "该议题的讨论经过、分歧脉络与定调依据（context_and_debate）：谁提出、怎么讨论、分歧在哪、定调依据为何，连贯饱满陈述（不复述 key_points 的事实）"),
        StrListField("key_points", "该议题的核心要点（逐条列出，覆盖两类）：1. 硬核指标（数字/时限/金额/范围）；2. 核心论据与案例（立论依据/论证事实/反驳证据/典型案例）；不遗漏关键支撑事实"),
        ObjListField("debates", [
            StrField("speaker", "发言人/阵营"),
            StrField("stance", "核心主张与观点立场"),
            StrField("argument", "支撑论据或反驳理由"),
        ], desc="该议题的观点交锋与论辩列表（学术研讨/辩论/思想争鸣时重点记录；企业例会无分歧可为[]）"),
        StrField("conclusion", "该议题的结论或共识，无明确结论时为null"),
        StrListField("participants", "原文中明确出现的发言人姓名列表"),
    ]),
]

DECISIONS_FIELD = StrListField("decisions", "已明确拍板/达成共识的结论（逐条列出、不遗漏；同类多项分别列出）")
OPEN_QUESTIONS_FIELD = StrListField("open_questions", "尚未达成一致或需后续确认的事项（逐条列出、不遗漏）")
RISKS_FIELD = StrListField("risks", "原文明确提到的风险/隐患/阻碍（逐条列出、不遗漏；同一句含多个风险对象时拆成多条）")

ACTION_HINTS_FIELD = ObjListField("action_hints", [
    StrField("action", "原文动作短语（谁+做什么，逐字可截取，可清语气词）"),
    StrField("owner", "原文明示的负责人/承诺人姓名；无明确负责人时为null"),
    StrField("timing", "原文时间约束（如「XX前完成」「会后」「尽快」），保留原文表达；无时为null"),
    StrField("condition", "触发条件（如「若XX未确认」「等XX到位」），保留原文；无时为null"),
    StrField("topic", "所属议题标题（对应topics[].title）；无对应时为null"),
    EnumField("kind", ACTION_HINT_KINDS),
    StrField("evidence", "原文中支撑此行动线索的一句话"),
])

RISK_HINTS_FIELD = ObjListField("risk_hints", [
    StrField("risk", "原文风险表述（可截取含信号片段），与risks列表条目可对应"),
    StrField("topic", "所属议题标题；无对应时为null"),
    EnumField("signal_type", RISK_SIGNAL_TYPES),
    StrField("severity_evidence", "原文强度措辞原句（如「必须尽快」「影响较大」「小问题」）；无时为null"),
    StrField("impact", "原文明确的影响后果；无时为null"),
    StrField("mitigation", "原文已有的应对措施；未提为null"),
    StrField("owner", "原文明示的负责人姓名；无或为占位符时为null"),
    StrField("evidence", "原文中支撑此风险线索的一句话"),
])

DEPENDENCIES_FIELD = StrListField("dependencies", "原文明确的未确认前置/依赖（如「等XX确认」「取决于XX」「XX到位后才能YY」）")

ALL_CORE_FIELD_NAMES: frozenset[str] = frozenset({
    "meeting_brief",
    "meeting_purpose",
    "scene",
    "speakers",
    "topics",
    "decisions",
    "open_questions",
    "risks",
    "action_hints",
    "risk_hints",
    "dependencies",
})


class MeetingUnderstandingGenerationContract(GenerationContract):
    """会议理解输出契约（全量平铺事实底座）。"""

    fields: ClassVar[list[Field]] = [
        *CORE_BASE_FIELDS,
        DECISIONS_FIELD,
        OPEN_QUESTIONS_FIELD,
        RISKS_FIELD,
        ACTION_HINTS_FIELD,
        RISK_HINTS_FIELD,
        DEPENDENCIES_FIELD,
    ]


MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    MeetingUnderstandingGenerationContract.to_output_contract()
)


def build_core_contract_for_tasks(
    active_tasks: Iterable[str] | None = None,
    *,
    template_text: str = "",
    memory_on: bool = False,
) -> tuple[str, frozenset[str]]:
    """根据本次激活的任务线动态组装 meeting_core 输出契约及被省略的字段集合。

    返回：(output_contract_str, omitted_fields)
    omitted_fields 为当前未被抽取的字段集，将作为 allow_missing 传给 structured 调用。
    """
    selected = [str(t).strip() for t in (active_tasks or []) if str(t).strip()]
    if not selected:
        return (
            MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT,
            frozenset(),
        )

    selected_set = set(selected)

    need_decisions = bool(
        memory_on
        or any(
            t in selected_set
            for t in (
                "minutes",
                "minutes_styles",
                "minutes_trace",
                "consensus_decision",
                "mindmap",
            )
        )
    )
    need_risks = bool(
        memory_on
        or any(
            t in selected_set
            for t in (
                "minutes",
                "minutes_styles",
                "risks",
                "consensus_decision",
                "minutes_trace",
            )
        )
    )
    need_open_questions = bool(
        memory_on
        or any(
            t in selected_set
            for t in (
                "minutes",
                "minutes_styles",
                "risks",
                "consensus_decision",
            )
        )
    )
    need_action_hints = bool(memory_on or ("actions" in selected_set))
    need_risk_hints = bool(memory_on or ("risks" in selected_set))
    need_dependencies = bool(memory_on)

    # 针对 minutes 单线且给定模板时的按需裁剪：若模板完全不包含风险/未决词汇，则跳过
    if selected == ["minutes"] and template_text.strip() and not memory_on:
        from ..understanding_skip import skip_fields_for_template

        tpl_skips = skip_fields_for_template(template_text)
        if "risks" in tpl_skips:
            need_risks = False
        if "open_questions" in tpl_skips:
            need_open_questions = False

    # 动态裁剪 topics 子字段：决策类/全量纪要类需要 debates，轻量执行类（待办/导图/溯源/纯风险）可跳过 debates
    need_debates = bool(
        memory_on
        or any(
            t in selected_set
            for t in (
                "consensus_decision",
                "minutes",
                "minutes_styles",
            )
        )
    )

    is_minimal_topics = (selected_set <= {"actions", "mindmap"}) and not memory_on
    topic_discussion_desc = (
        "该议题的讨论经过、分歧脉络与定调依据（context_and_debate，50字以内简述）"
        if is_minimal_topics
        else "该议题的讨论经过、分歧脉络与定调依据（context_and_debate）：交代因果背景、主张理由与定调考量，连贯陈述；具体数据指标、金额、时限统一收纳于 key_points，避免冗余重复"
    )

    topic_fields: list[Field] = [
        StrField("module", "所属宏观业务领域/模块（如'核心架构优化'、'现场实体整改'、'交付与验收'，全场收敛为3~5个）"),
        StrField("title", "议题名称/核心命题"),
        StrField("discussion", topic_discussion_desc),
        StrListField("key_points", "该议题的核心要点（逐条列出，覆盖两类）：1. 硬核指标（数字/时限/金额/范围）；2. 核心论据与案例（立论依据/论证事实/反驳证据/典型案例）；不遗漏关键支撑事实"),
    ]
    if need_debates:
        topic_fields.append(
            ObjListField("debates", [
                StrField("speaker", "发言人/阵营"),
                StrField("stance", "核心主张与观点立场"),
                StrField("argument", "支撑论据或反驳理由"),
            ], desc="该议题的观点交锋与论辩列表（学术研讨/辩论/思想争鸣时重点记录；企业例会无分歧可为[]）")
        )
    topic_fields.extend([
        StrField("conclusion", "该议题的结论或共识，无明确结论时为null"),
        StrListField("participants", "原文中明确出现的发言人姓名列表"),
    ])

    chosen_fields: list[Field] = [
        StrField("meeting_brief", "80~200字概括整场会议主线全貌与核心态势"),
        StrField("meeting_purpose", "一句话概括会议目的"),
        EnumField("scene", SCENE_CHOICES, normalize="通用"),
        ObjListField("speakers", [
            StrField("name", "统一显示称呼：姓名优先，其次原文角色，再次原始编号；不推断、不编造"),
            StrField("role", "角色（发言人/主持人/记者/听众/嘉宾/主讲人…，照原文；判断不出为null）"),
            StrField("org", "机构/单位/媒体名（照原文；没有为null）"),
        ]),
        ObjListField("topics", topic_fields),
    ]

    if need_decisions:
        chosen_fields.append(DECISIONS_FIELD)
    if need_open_questions:
        chosen_fields.append(OPEN_QUESTIONS_FIELD)
    if need_risks:
        chosen_fields.append(RISKS_FIELD)
    if need_action_hints:
        chosen_fields.append(ACTION_HINTS_FIELD)
    if need_risk_hints:
        chosen_fields.append(RISK_HINTS_FIELD)
    if need_dependencies:
        chosen_fields.append(DEPENDENCIES_FIELD)

    class DynamicMeetingUnderstandingGenerationContract(GenerationContract):
        fields: ClassVar[list[Field]] = chosen_fields

    contract_str = DynamicMeetingUnderstandingGenerationContract.to_output_contract()
    active_names = {f.name for f in chosen_fields}
    omitted = ALL_CORE_FIELD_NAMES - active_names
    return contract_str, omitted


__all__ = [
    "SCENE_CHOICES",
    "ACTION_HINT_KINDS",
    "RISK_SIGNAL_TYPES",
    "ALL_CORE_FIELD_NAMES",
    "MeetingUnderstandingGenerationContract",
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
    "build_core_contract_for_tasks",
]
