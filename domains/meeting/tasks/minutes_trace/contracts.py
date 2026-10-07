"""minutes_trace 的契约定义。"""
from __future__ import annotations

from core.schema.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    StrField,
    SupervisorContract,
)
from core.schema.fallback_rules import FallbackRules, Raw

class MinutesTraceGenerationContract(GenerationContract):
    """溯源纪要草稿：正文。"""

    fields = [
        StrField("minutes_md", "按议题树写出的正文，句末不要带溯源钉"),
    ]


class MinutesTraceSupervisorContract(SupervisorContract):
    """审核纪要正文；对齐只拦明显乱挂。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
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
    disclaimer = False


MINUTES_TRACE_FALLBACK_RULES = MinutesTraceFallbackRules()
