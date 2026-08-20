"""minutes_trace 的契约定义。"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    EnumField,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Raw

# 会议场景枚举：与 meeting_core/contracts.py 的 SCENE_CHOICES 保持同值
# （sync_domain 按文件路径加载 contracts.py，不能用包间相对导入）
SCENE_CHOICES = [
    "通用",
    "团队例会",
    "脑暴/讨论",
    "项目决策与评审",
    "专项讨论会",
    "研讨会",
    "采访/对话",
]


class MinutesTraceGenerationContract(GenerationContract):
    """溯源纪要草稿：场景 + 正文 + 对齐草稿。"""

    fields = [
        EnumField("scene", SCENE_CHOICES),
        StrField("minutes_md", "按所选场景骨架写出的正文，句末不要带溯源钉"),
        ObjListField(
            "alignments",
            [
                StrField("sentence", "纪要正文中的原句（须能在 minutes_md 中找到）"),
                StrField("kind", "keypoint 或 note"),
                StrField("source", "关键点整行，或笔记的原文片段"),
                StrField("evidence", "能对上会议原文的一句依据"),
            ],
            desc="本阶段返回空数组 []；对齐在审核通过后由单独步骤生成",
        ),
    ]


class MinutesTraceSupervisorContract(SupervisorContract):
    """审核纪要正文；对齐只拦明显乱挂。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check("facts_check", "仅记录严重问题：正文编造会议没有的事实"),
        Check("template_check", "仅记录严重问题：缺内容总结或主要议题，或按发言人流水账"),
        Check("trace_check", "仅记录严重问题：把用户批注写成会上事实或明显乱挂来源"),
    ]


MINUTES_TRACE_GENERATION_OUTPUT_CONTRACT = (
    MinutesTraceGenerationContract.to_output_contract()
)
MINUTES_TRACE_SUPERVISOR_OUTPUT_CONTRACT = (
    MinutesTraceSupervisorContract.to_output_contract()
)


class MinutesTraceFallbackRules(FallbackRules):
    """降级只出纪要正文，不补假钉。"""

    sections = [
        Raw("minutes_md"),
    ]
    empty_text = "请直接参考会议原文。"
    empty_prefix = "系统未能通过质量审核，以下为基于现有材料的粗略整理。"
    empty_purpose = True
    disclaimer = True


MINUTES_TRACE_FALLBACK_RULES = MinutesTraceFallbackRules()
