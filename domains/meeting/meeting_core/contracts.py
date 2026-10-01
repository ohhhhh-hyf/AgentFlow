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
    """统一议题树会议理解输出契约。"""

    fields = [
        StrField("meeting_brief", "80字以内概括整场会议主线"),
        StrField("meeting_purpose", "一句话概括会议目的"),
        EnumField("scene", SCENE_CHOICES, normalize="通用"),
        ObjListField("speakers", [
            StrField("name", "统一显示称呼：姓名优先，其次角色/编号；不推断、不编造"),
            StrField("role", "角色/职务（照原文；无为null）"),
            StrField("org", "机构/单位/部门名（照原文；无为null）"),
        ]),
        ObjListField("topics", [
            StrField("topic_id", "议题编号（如 T1, T2）"),
            StrField("module", "所属业务模块/领域（如'基础架构与中间件'、'海外数据合规'）"),
            StrField("title", "核心议题标题（4~12字）"),
            StrField("context_and_debate", "该议题讨论经过与争论脉络（谁提出、论据交锋、为什么分歧，100~200字自然叙事）"),
            StrListField("key_metrics", "量化指标与参数（如并发数、时延、预算、排期等；无则[]）"),
            StrListField("decisions", "本议题拍板决议（含生效前提与约束；无则[]）"),
            StrListField("rejected_proposals", "现场讨论并明确否决的方案及原因；无则[]"),
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
        StrListField("decisions", "已明确拍板/达成共识的结论（逐条列出；同类多项分别列出；无则[]）"),
        StrListField("open_questions", "尚未达成一致或需后续确认的事项（逐条列出；无则[]）"),
        StrListField("risks", "原文明确提到的风险/隐患/阻碍（逐条列出；无则[]）"),
        ObjListField("action_hints", [
            StrField("action", "原文动作短语（谁+做什么）"),
            StrField("owner", "负责人姓名；无为null"),
            StrField("timing", "时间约束；无为null"),
            StrField("condition", "触发条件；无为null"),
            StrField("topic", "所属议题标题；无为null"),
            EnumField("kind", ACTION_HINT_KINDS),
            StrField("evidence", "支撑一句话"),
        ]),
        ObjListField("risk_hints", [
            StrField("risk", "原文风险表述"),
            StrField("topic", "所属议题标题；无为null"),
            EnumField("signal_type", RISK_SIGNAL_TYPES),
            StrField("severity_evidence", "强度原句；无为null"),
            StrField("impact", "影响后果；无为null"),
            StrField("mitigation", "应对措施；无为null"),
            StrField("owner", "负责人姓名；无为null"),
            StrField("evidence", "支撑一句话"),
        ]),
        StrListField("dependencies", "原文明确的未确认前置/依赖；无则[]"),
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
