"""meeting_core 的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：
- 生成契约类（MeetingUnderstandingGenerationContract 等）→ to_json_template() 生成 prompt 常量
- 审阅契约类（无：core 是公共底座，没有 supervisor）
"""
from __future__ import annotations

from core.schema.contracts import (
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

# ── 行动线索类型枚举（公共底座，待办线消费）─────────────────────
# commitment=承诺表态（我来做/我们负责）；assignment=明确分配（由 YY 负责）；
# directive=指令要求（要求/必须/务必…落实）；rectification=整改项（验收/检查提出的整改）；
# followup=后续跟进（会后要跟踪/确认/再议）。对应待办线的信号清单。
ACTION_HINT_KINDS = [
    "commitment",
    "assignment",
    "directive",
    "rectification",
    "followup",
]

# ── 风险信号类型枚举（公共底座，风险线消费）─────────────────────
# time=时间/期限；resource=资源/预算；staffing=人员/人力；quality=质量/标准；
# dependency=依赖未确认；external=外部条件（政策/疫情/供货方等）；scope=范围边界；
# other=其它明确风险信号。用于风险线的 severity/source 定位与归类。
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


class MeetingUnderstandingGenerationContract(GenerationContract):
    """会议理解输出契约（平铺事实底座）。"""

    fields = [
        StrField("meeting_brief", "80字以内概括整场会议主线"),
        StrField("meeting_purpose", "一句话概括会议目的"),
        # 形态标签类枚举：真实场景有二十多种，7 类覆盖不到 → 非法值归一「通用」，不抛错重试
        EnumField("scene", SCENE_CHOICES, normalize="通用"),
        # 发言人与角色对照（统一显示称呼↔角色的单点落点）：下游 Q&A/表态/概况栏直接消费，不必每栏
        # 从长原文里重新推"这段是谁在说"（实测会退化成「答」「主持人（机构名）」）。
        ObjListField("speakers", [
            StrField("name", "统一显示称呼：姓名优先，其次原文角色，再次原始编号；不推断、不编造"),
            StrField("role", "角色（发言人/主持人/记者/听众/嘉宾/主讲人…，照原文；判断不出为null）"),
            StrField("org", "机构/单位/媒体名（照原文；没有为null）"),
        ]),
        ObjListField("topics", [
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
        StrListField("decisions", "已明确拍板/达成共识的结论（逐条列出、不遗漏；同类多项分别列出）"),
        StrListField("open_questions", "尚未达成一致或需后续确认的事项（逐条列出、不遗漏）"),
        StrListField("risks", "原文明确提到的风险/隐患/阻碍（逐条列出、不遗漏；同一句含多个风险对象时拆成多条）"),
        # ── 下游线索字段（供待办/风险线直接消费，只做定位与锚定，不做业务判断）──
        ObjListField("action_hints", [
            StrField("action", "原文动作短语（谁+做什么，逐字可截取，可清语气词）"),
            StrField("owner", "原文明示的负责人/承诺人姓名；无明确负责人时为null"),
            StrField("timing", "原文时间约束（如「XX前完成」「会后」「尽快」），保留原文表达；无时为null"),
            StrField("condition", "触发条件（如「若XX未确认」「等XX到位」），保留原文；无时为null"),
            StrField("topic", "所属议题标题（对应topics[].title）；无对应时为null"),
            EnumField("kind", ACTION_HINT_KINDS),
            StrField("evidence", "原文中支撑此行动线索的一句话"),
        ]),
        ObjListField("risk_hints", [
            StrField("risk", "原文风险表述（可截取含信号片段），与risks列表条目可对应"),
            StrField("topic", "所属议题标题；无对应时为null"),
            EnumField("signal_type", RISK_SIGNAL_TYPES),
            StrField("severity_evidence", "原文强度措辞原句（如「必须尽快」「影响较大」「小问题」）；无时为null"),
            StrField("impact", "原文明确的影响后果；无时为null"),
            StrField("mitigation", "原文已有的应对措施；未提为null"),
            StrField("owner", "原文明示的负责人姓名；无或为占位符时为null"),
            StrField("evidence", "原文中支撑此风险线索的一句话"),
        ]),
        StrListField("dependencies", "原文明确的未确认前置/依赖（如「等XX确认」「取决于XX」「XX到位后才能YY」）"),
    ]


MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT = (
    MeetingUnderstandingGenerationContract.to_output_contract()
)

__all__ = [
    "SCENE_CHOICES",
    "ACTION_HINT_KINDS",
    "RISK_SIGNAL_TYPES",
    "MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT",
]
