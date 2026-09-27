"""consensus_decision contract definitions.

Required by tools/codegen/sync_domain.py:
- class ConsensusDecisionGenerationContract(GenerationContract)
- class ConsensusDecisionSupervisorContract(SupervisorContract)
- CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT = ConsensusDecisionGenerationContract.to_output_contract()
- CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT = ConsensusDecisionSupervisorContract.to_output_contract()

Optional fallback:
- class ConsensusDecisionFallbackRules(FallbackRules)
- CONSENSUS_DECISION_FALLBACK_RULES = ConsensusDecisionFallbackRules()
"""
from __future__ import annotations

from tools.schema.contracts import (
    Check,
    Decision,
    EnumField,
    Feedback,
    GenerationContract,
    ObjField,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.schema.fallback_rules import FallbackRules, Lines

# ── 共识四级分级枚举 ──────────────────────────────────────────
# hard_alignment: 充分坚实共识（全员无保留条件闭环）
# conditional_concession: 带保留条件的妥协（表面同意，但附带明确前提或免责声明）
# unresolved_concern: 未被采纳的关切（当场提出顾虑，但被多数人忽略或搁置）
# active_disagreement: 悬而未决的待决分歧（各执一词，会后无定论，留存争议）
CONSENSUS_GRADES = [
    "hard_alignment",
    "conditional_concession",
    "unresolved_concern",
    "active_disagreement",
]

# ── 裁决形态枚举 ──────────────────────────────────────────────────
# data_driven: 数据/标准驱动型（由明确测试数据/量化指标/标准规范拍板）
# authority_fiat: 权威定夺型（技术负责人/业务主管依据职责经验强推）
# quid_pro_quo: 协同对等交换型（各退一步，达成对等配合方案）
# consensus: 充分研讨共识型（讨论充分后各方理念充分交融达成一致）
DECISION_ARCHETYPES = [
    "data_driven",
    "authority_fiat",
    "quid_pro_quo",
    "consensus",
]


class ConsensusDecisionGenerationContract(GenerationContract):
    """共识与决策推演输出契约。"""

    fields = [
        ObjField("summary", [
            StrField("health_headline", "全会议题共识度评估与执行风险总评（客观提炼全局共识收敛度与关键执行保留项）"),
        ], desc="全会议题共识概览"),
        ObjListField("issues", [
            StrField("issue_id", "议题编号，如 ISS-01, ISS-02"),
            StrField("topic", "核心讨论议题名称，精炼概括（如「某方案的取舍结论」「某事项的标准确认」）"),
            StrField("trigger", "议题源起背景与动因：讨论该议题的业务/技术背景、目标要求或现状痛点"),
            ObjField("pro_side", [
                StrListField("speakers", "主张/提案/汇报方发言人列表"),
                StrField("stance", "核心立场或主张概要（15字以内）"),
                StrListField("arguments", "支撑该主张的事实论据、专业逻辑、标准规范或验证结果（1~3条）"),
                StrField("quote", "主张方最具代表性的一句发言原句"),
            ], desc="主张/提案/汇报方观点与论据"),
            ObjField("con_side", [
                StrListField("speakers", "关切/质询/协作审议方发言人列表（若全员赞同，填写协同确认方或审议代表）"),
                StrField("stance", "关切考量、质询顾虑或协同确认意见概要（15字以内）"),
                StrListField("arguments", "关切隐患、约束考量、协同要求或确认要点（1~3条）"),
                StrField("quote", "关切/质询/协同方最具代表性的一句发言原句"),
            ], desc="关切/质询/协作审议方观点与考量"),
            EnumField("archetype", DECISION_ARCHETYPES, desc="裁决达成形态"),
            StrField("accord", "达成决议或统一口径：各方最终达成的共识结论、执行口径或协同方案"),
            EnumField("consensus_grade", CONSENSUS_GRADES, desc="共识四级分级分类"),
            StrField("caveat", "附带的保留条件、妥协前提或执行预警（若全员充分闭环无保留条件，填 null 或无）"),
            ObjField("trade_off", [
                StrField("gain", "换取的核心价值、业务收益或确定性（得到什么）"),
                StrField("sacrifice", "付出的资源成本、承担的妥协/操作代价或放弃的备选方案（付出或放弃什么）"),
            ], desc="本项决议的权衡取舍与承诺代价"),
            StrField("rollback_trigger", "触发方案重新审议或调整的客观红线条件与复核机制（若会上未提及填「无明确重议红线，按里程碑复核」或「无明确重议红线」）"),
            StrField("key_quote", "整场研讨中最具代表性或定调决策的原文引句"),
        ], desc="核心议题研讨与决策推演条目列表（通常 1~4 项关键议题）"),
    ]


class ConsensusDecisionSupervisorContract(SupervisorContract):
    """共识决策任务的领域审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("concession_check", "审查共识分级定级是否准确（若发言人明确表达保留意见、免责前提或待补齐事项，定级为 conditional_concession 并提炼 caveat；若全员闭环确认无附带条件，允许定级为 hard_alignment）"),
        Check("tradeoff_check", "审查得失权衡（gain 与 sacrifice）是否具备实质内容，反映真实的收益与成本/资源投入/妥协代价，严禁空泛套话"),
        Check("evidence_check", "核验所有发言人及引用原句（quote / key_quote）在会议原文中是否真实存在，严禁捏造虚构"),
    ]


CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT = ConsensusDecisionGenerationContract.to_output_contract()
CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT = ConsensusDecisionSupervisorContract.to_output_contract()


class ConsensusDecisionFallbackRules(FallbackRules):
    """共识决策降级拼装：保留结构化 issues。"""

    sections = [
        Lines("issues"),
    ]
    empty_text = "暂无明确共识与因果决策议题"
    structured = {"field": "issues"}


CONSENSUS_DECISION_FALLBACK_RULES = ConsensusDecisionFallbackRules()

__all__ = [
    "CONSENSUS_DECISION_GENERATION_OUTPUT_CONTRACT",
    "CONSENSUS_DECISION_SUPERVISOR_OUTPUT_CONTRACT",
    "CONSENSUS_DECISION_FALLBACK_RULES",
    "CONSENSUS_GRADES",
    "DECISION_ARCHETYPES",
]
