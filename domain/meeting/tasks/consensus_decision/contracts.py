"""consensus_decision contract definitions.

Required by tools/scripts/sync_domain.py:
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

# ── 共识四级成色光谱枚举 ──────────────────────────────────────────
# hard_alignment: 坚实质朴共识（全员无异议闭环）
# conditional_concession: 带保留条件的妥协（表面同意，但附带严苛前提或免责声明）
# unresolved_concern: 未被采纳的关切（当场提出顾虑，但被多数人忽略或压制）
# active_disagreement: 悬而未决的暗礁（各执一词，会后无定论，留存争议）
CONSENSUS_GRADES = [
    "hard_alignment",
    "conditional_concession",
    "unresolved_concern",
    "active_disagreement",
]

# ── 裁决形态枚举 ──────────────────────────────────────────────────
# data_driven: 数据迫降型（由明确测试数据/量化指标强制拍板）
# authority_fiat: 权威定夺型（技术负责人/业务主管依据经验强推）
# quid_pro_quo: 利益妥协交换型（各退一步，达成对等补偿公约）
# consensus: 自然充分共识型（讨论充分后各方理念自然闭环）
DECISION_ARCHETYPES = [
    "data_driven",
    "authority_fiat",
    "quid_pro_quo",
    "consensus",
]


class ConsensusDecisionGenerationContract(GenerationContract):
    """共识成色与因果决策推演输出契约。"""

    fields = [
        ObjField("summary", [
            StrField("health_headline", "全会议题共识健康度战略评估与执行风险总评"),
        ], desc="全会议题共识健康度概览"),
        ObjListField("issues", [
            StrField("issue_id", "议题编号，如 ISS-01, ISS-02"),
            StrField("topic", "核心讨论议题名称，精炼概括（如「某方案的取舍结论」「某事项的完成口径」）"),
            StrField("trigger", "议题源起背景：为什么今天会讨论这个问题？现状痛点是什么？"),
            ObjField("pro_side", [
                StrListField("speakers", "正向/主张方发言人列表"),
                StrField("stance", "核心立场或主张概要（15字以内）"),
                StrListField("arguments", "支撑该主张的事实论据、顾虑理由或逻辑推导"),
                StrField("quote", "主张方最具代表性的一句发言原句"),
            ], desc="正向/主张方观点与论据"),
            ObjField("con_side", [
                StrListField("speakers", "反向/质询方发言人列表"),
                StrField("stance", "反向立场或质询顾虑概要（15字以内）"),
                StrListField("arguments", "质疑、顾虑理由或反对论据"),
                StrField("quote", "反向方最具代表性的一句发言原句"),
            ], desc="反向/质询方观点与顾虑"),
            EnumField("archetype", DECISION_ARCHETYPES, desc="裁决达成形态"),
            StrField("accord", "破局公约或终局拍板结论：各方最终达成的统一口径或各退一步的共识"),
            EnumField("consensus_grade", CONSENSUS_GRADES, desc="共识四级成色分类"),
            StrField("caveat", "附带的保留条件、妥协前提或被压制的潜藏隐患；若无保留条件则为null或无"),
            ObjField("trade_off", [
                StrField("gain", "换取的核心价值、收益或确定性（▲ 得到什么）"),
                StrField("sacrifice", "主动承担的隐性代价、牺牲的灵活性或技术债（▼ 放弃什么）"),
            ], desc="本项决议的得失权衡"),
            StrField("rollback_trigger", "触发方案重新讨论或推翻回滚的客观红线条件（若无明确条件填「无明确翻盘红线」）"),
            StrField("key_quote", "整场讨论中最具冲突戏剧性或最终拍板定案的原文引句"),
        ], desc="核心议题辩证推演条目列表（通常 2~4 项深水区议题）"),
    ]


class ConsensusDecisionSupervisorContract(SupervisorContract):
    """共识决策任务的领域审核契约。"""

    decision = Decision()
    feedback = Feedback("decision=revise 时必填（具体、可执行、有原文依据）；approve/reject 时给空数组 []——字段必须出现，不可省略")
    checks = [
        Check("concession_check", "审查是否存在被掩盖的保留条件或假共识，成色定级是否准确（如带有免责/保留前提必须定级为 conditional_concession 并提炼 caveat）"),
        Check("tradeoff_check", "审查得失天平（gain 与 sacrifice）是否具备真实对抗张力，严禁空泛套话或同义反复"),
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
