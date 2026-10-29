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
    Field, GenerationContract, ObjListField, StrField, StrListField,
)

from .understanding_profiles import (
    FULL_PROFILE,
    UnderstandingProfile,
    resolve_profile,
)

# ── 基础与可选字段定义 ──────────────────────────────────────────

SESSION_SEGMENTS_FIELD = ObjListField(
    "session_segments",
    [
        StrField("segment_title", "该研讨阶段的议题或业务标的名称（顺应会议推进时序划分3~6个自然阶段）"),
        StrField("context_and_reasoning", "该阶段的讨论脉络、争议焦点与定调依据（连贯陈述，保留论辩与决策动因）"),
        StrListField("key_facts", "该阶段提出的硬核指标（数字/时限/金额/范围）、交付成果与推进动作（逐条真实记录）"),
    ],
    desc="顺应会议推进时序的自然研讨阶段列表（承载议题脉络与量化事实血肉）",
)

SESSION_SEGMENTS_LIGHT_FIELD = ObjListField(
    "session_segments",
    [
        StrField("segment_title", "该研讨阶段的议题或业务标的名称（顺应会议推进时序划分3~6个自然阶段，作为宏观分类标题）"),
    ],
    desc="顺应会议推进时序的议题标的分类列表（仅提取议题标题供下游模块成组分类，不展开大段叙事）",
)

MEETING_BRIEF_FIELD = StrField("meeting_brief", "80~200字概括整场会议主线全貌与核心态势")
MEETING_PURPOSE_FIELD = StrField("meeting_purpose", "一句话概括会议目的")
SPEAKERS_FIELD = ObjListField("speakers", [
    StrField("name", "统一显示称呼：姓名优先，其次原文角色，再次原始编号；不推断、不编造"),
    StrField("role", "角色（发言人/主持人/记者/听众/嘉宾/主讲人…，照原文；判断不出为null）"),
    StrField("org", "机构/单位/媒体名（照原文；没有为null）"),
])

BASE_FIELD_NAMES: tuple[str, ...] = (
    "meeting_brief",
    "meeting_purpose",
    "speakers",
)

CORE_BASE_FIELDS: list[Field] = [
    MEETING_BRIEF_FIELD,
    MEETING_PURPOSE_FIELD,
    SPEAKERS_FIELD,
    SESSION_SEGMENTS_FIELD,
]

DECISIONS_FIELD = StrListField("decisions", "已明确拍板/达成共识的结论（逐条列出、不遗漏；同类多项分别列出）")
OPEN_QUESTIONS_FIELD = StrListField("open_questions", "尚未达成一致或需后续确认的事项（逐条列出、不遗漏）")
RISKS_FIELD = StrListField("risks", "原文明确提到的风险/隐患/阻碍（逐条列出、不遗漏；同一句含多个风险对象时拆成多条）")

ACTION_HINTS_FIELD = ObjListField("action_hints", [
    StrField("action", "原文动作短语（谁+做什么，逐字可截取，可清语气词）"),
    StrField("owner", "原文明示的负责人/承诺人姓名；无明确负责人时为null"),
    StrField("timing", "原文时间约束（如「XX前完成」「会后」「尽快」），保留原文表达；无时为null"),
    StrField("condition", "触发条件（如「若XX未确认」「等XX到位」），保留原文；无时为null"),
    StrField("collaborators", "原文明示的协同对象/配合方；无明确协同方为null"),
    StrField("acceptance", "原文明示的交付标准或验收判定；无明确标准为null"),
    StrField("topic", "所属研讨阶段或议题标题（对应session_segments[].segment_title）；无对应时为null"),
    StrField("evidence", "原文中支撑此行动线索的一句话"),
])

RISK_HINTS_FIELD = ObjListField("risk_hints", [
    StrField("risk", "原文风险表述（可截取含信号片段），与risks列表条目可对应"),
    StrField("topic", "所属研讨阶段或议题标题（对应session_segments[].segment_title）；无对应时为null"),
    StrField("trigger", "原文明确提及的爆发前提/触发诱因；未提及为null"),
    StrField("impact", "原文明确的影响后果；无时为null"),
    StrField("mitigation", "原文已有的应对措施；未提为null"),
    StrField("owner", "原文明示的负责人姓名；无或为占位符时为null"),
    StrField("evidence", "原文中支撑此风险线索的一句话"),
])

DEPENDENCIES_FIELD = StrListField("dependencies", "原文明确的未确认前置/依赖（如「等XX确认」「取决于XX」「XX到位后才能YY」）")

FIELD_DEFS: dict[str, Field] = {
    "meeting_brief": MEETING_BRIEF_FIELD,
    "meeting_purpose": MEETING_PURPOSE_FIELD,
    "speakers": SPEAKERS_FIELD,
    "session_segments_full": SESSION_SEGMENTS_FIELD,
    "session_segments_light": SESSION_SEGMENTS_LIGHT_FIELD,
    "decisions": DECISIONS_FIELD,
    "open_questions": OPEN_QUESTIONS_FIELD,
    "risks": RISKS_FIELD,
    "action_hints": ACTION_HINTS_FIELD,
    "risk_hints": RISK_HINTS_FIELD,
    "dependencies": DEPENDENCIES_FIELD,
}


def fields_for_profile(profile: UnderstandingProfile) -> list[Field]:
    """按任务 profile 生成理解输出字段列表。"""
    fields = [FIELD_DEFS[name] for name in BASE_FIELD_NAMES]
    if profile.segments != "none":
        fields.append(FIELD_DEFS[f"session_segments_{profile.segments}"])
    fields.extend(FIELD_DEFS[name] for name in profile.fields)
    return fields


ALL_CORE_FIELD_NAMES: frozenset[str] = frozenset({
    "meeting_brief",
    "meeting_purpose",
    "speakers",
    "session_segments",
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

    ``template_text`` 保留参数兼容；模板不再参与理解层字段裁剪。
    """
    profile = resolve_profile(active_tasks, memory_on=memory_on) or FULL_PROFILE
    chosen_fields = fields_for_profile(profile)

    class DynamicMeetingUnderstandingGenerationContract(GenerationContract):
        fields: ClassVar[list[Field]] = chosen_fields

    contract_str = DynamicMeetingUnderstandingGenerationContract.to_output_contract()
    active_names = {f.name for f in chosen_fields}
    omitted = ALL_CORE_FIELD_NAMES - active_names
    return contract_str, omitted

__all__ = [
    "ALL_CORE_FIELD_NAMES",
    "BASE_FIELD_NAMES",
    "FIELD_DEFS",
    "MeetingUnderstandingGenerationContract",
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
    "SESSION_SEGMENTS_LIGHT_FIELD",
    "build_core_contract_for_tasks",
    "fields_for_profile",
]
