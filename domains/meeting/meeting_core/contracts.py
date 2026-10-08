"""meeting_core 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类（MeetingUnderstandingGenerationContract 等）→ to_json_template() 生成 prompt 常量
- 审阅契约类（无：core 是公共底座，没有 supervisor）
"""
from __future__ import annotations

from core.schema.contracts import (
    EnumField, GenerationContract, ObjListField, StrField, StrListField,
)


class MeetingUnderstandingGenerationContract(GenerationContract):
    """统一议题树会议理解输出契约。"""

    fields = [
        StrField("meeting_brief", "80字以内概括整场会议主线"),
        StrField("meeting_purpose", "一句话概括会议目的"),
        ObjListField("speakers", [
            StrField("name", "统一显示称呼：姓名优先，其次角色/编号；不推断、不编造"),
            StrField("role", "角色/职务（照原文；无为null）"),
            StrField("org", "机构/单位/部门名（照原文；无为null）"),
        ]),
        ObjListField("topics", [
            StrField("topic_id", "议题编号（如 T1, T2）"),
            StrField("module", "所属业务模块/业务领域（精炼概括归属领域）"),
            StrField("title", "核心议题标题（4~12字）"),
            # 恢复为 80~150 字精炼脉络（MINUTES_TEMPLATE_OPTIMIZATION_STRATEGY 方案）：
            StrField("context_and_debate", "该议题讨论脉络与核心分歧焦点（充分展开交代：背景痛点、各方主张与论据、分歧争论焦点、妥协前提与拍板定调依据，严禁空泛套话）"),
            ObjListField("discussion_points", [
                StrField("point", "核心研讨要点/分歧争议主题（8~20字）"),
                StrField("detail", "该要点的具体研讨细节、各方立场与依据（50~100字饱满复合句）"),
                StrListField("evidence_quotes", "原文关键发言人表态或数据支撑（无则[]）"),
            ]),
            StrListField("key_metrics", "量化指标与参数（如并发数、时延、预算、排期等；无则[]）"),
            StrListField("decisions", "本议题拍板决议（含生效前提与约束；无则[]）"),
            ObjListField("actions", [
                StrField("task", "具体行动描述（以动词开头的具体任务描述）"),
                StrField("owner", "原文明示的负责人真实姓名；未明示为null"),
                StrField("deadline", "原文明示的截止时间；未明示为null"),
                StrField("deliverable", "明确交付成果物（如报告、方案、代码PR；无为null）"),
                StrField("dependency", "原文明示的前置依赖动作或输入；无为null"),
                EnumField("priority", ["high", "medium", "low"]),
                StrField("evidence", "原文中支撑此行动的一句话证据"),
            ]),
            ObjListField("risks", [
                StrField("risk", "风险/隐患客观描述"),
                EnumField("severity", ["high", "medium", "low"]),
                StrField("impact", "潜在影响后果；无明确为null"),
                StrField("mitigation", "现场已有的应对措施；未提为null"),
                StrField("owner", "跟进责任人；未明示为null"),
                StrField("evidence", "原文中支撑此风险的一句话证据"),
            ]),
            StrListField("open_issues", "尚未达成一致或需后续确认的事项；无则[]"),
        ]),
    ]


MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    MeetingUnderstandingGenerationContract.to_output_contract()
)

__all__ = [
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
]
