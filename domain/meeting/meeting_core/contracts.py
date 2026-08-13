"""meeting_core 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类（MeetingUnderstandingGenerationContract 等）→ to_json_template() 生成 prompt 常量
- 审阅契约类（无：core 是公共底座，没有 supervisor）
"""
from __future__ import annotations

from tools.contracts import (
    EnumField, GenerationContract, ObjListField, StrField, StrListField,
)


# ── 会议场景枚举（公共底座，下游共享）───────────────────────────
# minutes_trace 等下游按场景取不同组织侧重；理解 agent 结构化输出，
# 下游 detect_scene 优先消费该字段，启发式只作兜底。
SCENE_CHOICES = [
    "通用",
    "团队例会",
    "脑暴/讨论",
    "项目决策与评审",
    "专项讨论会",
    "研讨会",
    "采访/对话",
]


class MeetingUnderstandingGenerationContract(GenerationContract):
    """会议理解输出契约。"""

    fields = [
        StrField("meeting_purpose", "一句话概括会议目的"),
        EnumField("scene", SCENE_CHOICES),
        ObjListField("topics", [
            StrField("title", "议题名称"),
            StrField("discussion", "讨论内容概述"),
            StrField("conclusion", "该议题的结论，无结论时为null"),
            StrListField("participants", "原文中明确出现的发言人姓名"),
        ]),
        StrListField("decisions", "已明确拍板/达成共识的结论"),
        StrListField("open_questions", "尚未达成一致或需后续确认的事项"),
        StrListField("risks", "原文明确提到的风险/隐患/阻碍"),
    ]


MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    MeetingUnderstandingGenerationContract.to_output_contract()
)

__all__ = [
    "SCENE_CHOICES",
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
]
