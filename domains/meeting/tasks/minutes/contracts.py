"""minutes 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类 MinutesGenerationContract → to_json_template() 生成生成契约 prompt
- 审阅契约类 MinutesSupervisorContract → to_json_template() 生成审阅契约 prompt
"""
from __future__ import annotations

from core.schema.contracts import (
    Check, Decision, Feedback, GenerationContract, StrField, StrListField,
    SupervisorContract,
)
from core.schema.fallback_rules import FallbackRules, Join, Raw


class MinutesGenerationContract(GenerationContract):
    """纪要草稿输出契约。"""

    fields = [
        StrField("headline", "会议纪要标题"),
        StrListField(
            "executive_summary",
            "正文研讨（数组每项 = 一段正文，以业务事项为主干，写清背景依据、方案举措与结论定调；"
            "同类事项合并在同一段，段数按实际业务模块划分；"
            "关键数据、金额、时限与结论必须准确完备；过滤寒暄客套与非实质性过程细节）",
        ),
        StrListField(
            "key_decisions",
            "决策（来自MeetingUnderstanding.decisions：客观全量搬运；"
            "个人模式下聚焦本视角相关决议，措辞忠实于上游事实，每一项为一条独立完整的决策陈述）",
        ),
        StrListField(
            "personally_relevant_points",
            "执行要点（有明确分工则写，无则[]；每条 2–3 句完整句、交代责任人、具体任务、协同对象与交付时限；"
            "信息闭环，严禁半截句；个人模式下优先收录本人待办及关键协同项）",
        ),
        StrListField(
            "risks_and_blockers",
            "风险与卡点（来自MeetingUnderstanding.risks：客观全量搬运；"
            "个人模式下收录与本人直接相关的技术卡点、前置依赖及重点隐患；措辞忠实于上游事实，每一项为一条独立完整的风险陈述）",
        ),
        StrListField(
            "unresolved_questions",
            "未决问题（来自MeetingUnderstanding.open_questions：客观全量搬运；"
            "个人模式下收录与本人相关的会后待澄清事项及外部阻碍；措辞忠实于上游事实，每一项为一条独立完整的未决陈述）",
        ),
        StrListField(
            "history_comparison",
            "与历史对比（已由底层渲染管道自动装配，默认给空数组 []）",
        ),
    ]


class MinutesSupervisorContract(SupervisorContract):
    """纪要审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("facts_check", "仅记录严重问题，轻微问题不记录"),
        Check("perspective_check", "仅记录严重问题"),
        Check("consistency_check", "仅记录严重问题"),
    ]


MINUTES_GENERATION_OUTPUT_CONTRACT = MinutesGenerationContract.to_output_contract()
MINUTES_SUPERVISOR_OUTPUT_CONTRACT = MinutesSupervisorContract.to_output_contract()

# 议题模式专用输出契约（普通字符串，不新增 *GenerationContract 子类，
# 避免 sync_domain 生成多余模型）。
# 与共享契约的关键差异：
# - 不出现「个人模式下……」的字段说明；
# - 不出现「来自 MeetingUnderstanding……」的上游搬运说明；
# - 字段含义只描述议程模式下的 schema 语义，不夹带示例或写法引导。
MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT = """{
  "headline": "",
  "executive_summary": [],
  "key_decisions": [],
  "personally_relevant_points": [],
  "risks_and_blockers": [],
  "unresolved_questions": [],
  "history_comparison": []
}

字段说明：
- headline：会议纪要标题
- executive_summary：正文研讨（按审定议题或业务模块组织；关键事实、量化指标与结论完整）
- key_decisions：决策（现场明确拍板的最终决议；每条独立完整）
- personally_relevant_points：执行要点（有明确分工则写，无则 []；交代责任人、任务、交付物与时限）
- risks_and_blockers：风险与卡点（现场明确提出的技术瓶颈、外部依赖与交付阻碍）
- unresolved_questions：未决问题（现场悬而未决、待澄清、待确认事项）
- history_comparison：与历史对比（底层自动装配，默认 []）"""

# 降级拼装规则（声明式类）：fallback 节点由 sync_domain.py 检测子类后生成
class MinutesFallbackRules(FallbackRules):
    """纪要降级拼装：headline + 5 段（带标签）+ 免责声明。"""

    sections = [
        Raw("headline"),
        Join("executive_summary", "会议要点"),
        Join("key_decisions", "关键决策"),
        Join(
            "personally_relevant_points",
            label={"objective": "全员执行要点", "personal": "职责相关事项"},
        ),
        Join("risks_and_blockers", "风险与阻塞"),
        Join("unresolved_questions", "未决问题"),
        Join("history_comparison", "与历史对比"),
    ]
    empty_text = "请直接参考会议原文。"
    empty_purpose = True
    disclaimer = False


MINUTES_FALLBACK_RULES = MinutesFallbackRules()

__all__ = [
    "MINUTES_GENERATION_OUTPUT_CONTRACT",
    "MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT",
    "MINUTES_SUPERVISOR_OUTPUT_CONTRACT",
    "MINUTES_FALLBACK_RULES",
]
