"""meeting_core 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类（MeetingUnderstandingGenerationContract 等）→ to_json_template() 生成 prompt 常量
- 审阅契约类（无：core 是公共底座，没有 supervisor）
"""
from __future__ import annotations

from tools.contracts import (
    EnumField, GenerationContract, ObjListField, StrField, StrListField,
)


class MeetingUnderstandingGenerationContract(GenerationContract):
    """会议理解输出契约。"""

    fields = [
        StrField("meeting_purpose", "一句话概括会议目的"),
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


class PerspectiveModelingGenerationContract(GenerationContract):
    """视角建模输出契约。"""

    fields = [
        EnumField("confidence", ["high", "medium", "low"]),
        StrField("name", "用户姓名，客观模式下通常为null"),
        StrField("inferred_role", "基于原文推断的角色，无依据时为null"),
        StrListField("responsibilities", "本次会议中涉及的该用户/全员职责"),
        StrListField("goals", "本次会议中该用户/全员应达成的目标"),
        StrListField("concerns", "该用户/全员应关注的风险、不确定因素"),
        StrListField("relevant_topics", "与该用户/全员直接相关的议题"),
        StrListField("evidence", "原文中支撑以上判断的具体语句"),
    ]


MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    MeetingUnderstandingGenerationContract.to_json_template()
)

PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT = (
    PerspectiveModelingGenerationContract.to_json_template()
)

__all__ = [
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
]
