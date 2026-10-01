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

from core.schema.contracts import (
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
from core.schema.fallback_rules import FallbackRules, Lines

# ── 共识四级分级枚举 ──────────────────────────────────────────
# hard_alignment: 一致赞成（全员无保留条件闭环）
# conditional_concession: 附带前提同意（表面同意，但附带明确前提或限制要求）
# unresolved_concern: 保留意见（当场提出顾虑，但被多数人忽略或搁置）
# active_disagreement: 悬而未决分歧（各执一词，会后无定论，留存争议）
CONSENSUS_GRADES = [
    "hard_alignment",
    "conditional_concession",
    "unresolved_concern",
    "active_disagreement",
]

# ── 裁决形态枚举 ──────────────────────────────────────────────────
# data_driven: 数据驱动（由明确测试数据/量化指标/标准规范拍板）
# authority_fiat: 最终拍板（技术负责人/业务主管依据职责经验拍板定夺）
# quid_pro_quo: 协同交换（各退一步，达成对等配合方案）
# consensus: 讨论一致（讨论充分后各方理念充分交融达成一致）
DECISION_ARCHETYPES = [
    "data_driven",
    "authority_fiat",
    "quid_pro_quo",
    "consensus",
]


class ConsensusDecisionGenerationContract(GenerationContract):
    """共识与决策分析输出契约。"""

    fields = [
        ObjField("summary", [
            StrField("health_headline", "全会议题决策概览与执行风险总评（客观提炼全局共识与关键执行关注项）"),
        ], desc="全会议题决策概览"),
        ObjListField("issues", [
            StrField("issue_id", "议题编号，如 ISS-01, ISS-02"),
            StrField("topic", "核心讨论议题名称，精炼概括（如「某方案的取舍结论」「某事项的标准确认」）"),
            StrField("trigger", "议题起因：讨论该议题的业务/技术背景、目标要求或现状痛点"),
            ObjField("pro_side", [
                StrListField("speakers", "主张/提案/汇报方发言人列表"),
                StrField("stance", "核心立场或主张概要（15字以内）"),
                StrListField("arguments", "支撑该主张的事实论据、专业逻辑、标准规范或验证结果（1~3条）"),
                StrField("quote", "主张方最具代表性的一句发言原句"),
            ], desc="主张/提案/汇报方观点与论据"),
            ObjField("con_side", [
                StrListField("speakers", "提出顾虑/质询/协作审议方发言人列表（若全员赞同，填写协同确认方或审议代表）"),
                StrField("stance", "顾虑考量、质询意见或协同确认概要（15字以内）"),
                StrListField("arguments", "提出的顾虑、约束考量、协同要求或确认要点（1~3条）"),
                StrField("quote", "提出顾虑方最具代表性的一句发言原句"),
            ], desc="提出顾虑方观点与考量"),
            EnumField("archetype", DECISION_ARCHETYPES, desc="决定方式"),
            StrField("accord", "达成决议：各方最终达成的共识结论、执行口径或协同方案"),
            EnumField("consensus_grade", CONSENSUS_GRADES, desc="共识分级"),
            StrField("caveat", "附带前提与预警（若全员一致赞成无附加前提，填 null 或无）"),
            ObjField("trade_off", [
                StrField("gain", "获取的好处：核心价值、业务收益或确定性（得到什么好处）"),
                StrField("sacrifice", "付出的代价：资源成本、承担的妥协/操作代价或放弃的备选方案（付出或放弃什么代价）"),
            ], desc="本项决议的权衡取舍与成本代价"),
            StrField("rollback_trigger", "底线：触发方案重新讨论或调整的底线条件与复核机制（若会上未提及填「无明确底线，按里程碑复核」或「无明确底线」）"),
            StrField("key_quote", "整场研讨中最具代表性或定调决策的现场原话"),
        ], desc="议题决定过程条目列表（通常 1~4 项关键议题）"),
    ]


class ConsensusDecisionSupervisorContract(SupervisorContract):
    """共识决策任务的领域审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("concession_check", "审查共识分级定级是否准确（若发言人明确表达保留意见、免责前提或待补齐事项，定级为 conditional_concession 并提炼 caveat；若全员一致赞成无附带条件，允许定级为 hard_alignment）"),
        Check("tradeoff_check", "审查权衡取舍（获取的好处 gain 与 付出的代价 sacrifice）是否具备实质内容，反映真实的收益与成本/资源投入/妥协代价，严禁空泛套话"),
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
