"""quiz 的契约定义（prompt 文本见 prompts.py）。"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    EnumField,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines


class QuizGenerationContract(GenerationContract):
    """自测题输出契约。前三组是内部拆解，questions 才给用户看。"""

    fields = [
        ObjListField(
            "concepts",
            [
                StrField("name", "概念/定理/公式名，用原文术语"),
                EnumField(
                    "kind",
                    ["definition", "theorem", "formula", "other"],
                    "definition=定义；theorem=定理；formula=公式；other=其它核心概念",
                ),
                StrField("evidence", "原文依据，可定位片段"),
            ],
        ),
        ObjListField(
            "relations",
            [
                EnumField(
                    "kind",
                    ["cause", "contrast", "derivation"],
                    "cause=因果；contrast=对比；derivation=推导链",
                ),
                StrField("left", "关系左端（原因/甲方/前提）"),
                StrField("right", "关系右端（结果/乙方/结论）"),
                StrField("evidence", "原文依据"),
            ],
        ),
        ObjListField(
            "details",
            [
                EnumField(
                    "kind",
                    ["condition", "symbol", "special"],
                    "condition=适用条件；symbol=符号含义；special=特例/反例",
                ),
                StrField("text", "细节本身"),
                StrField("evidence", "原文依据"),
            ],
        ),
        ObjListField(
            "questions",
            [
                StrField(
                    "prompt",
                    "题干。必须让用户推理，禁止把原文结论改成填空就能抄",
                ),
                EnumField(
                    "dimension",
                    ["cause", "contrast", "condition", "detail", "application"],
                    "cause=因果（优先 A→B 问为什么）；contrast=对比；"
                    "condition=适用条件；detail=关键细节；application=迁移应用",
                ),
                StrField(
                    "note_hook",
                    "对应笔记里的哪条关系或细节，供审核对照，不展示给用户",
                ),
                StrListField(
                    "answer_points",
                    "参考得分点 2–3 条；写推理要点，不要整句抄原文",
                ),
            ],
        ),
    ]


class QuizSupervisorContract(SupervisorContract):
    """自测题审核契约。"""

    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行、有原文依据")
    checks = [
        Check(
            "quiz_check",
            "仅记录严重问题：题干能靠原文整句抄出答案、编造笔记没有的关系、"
            "得分点少于 2 条、全是同一维度、把定义背诵题当成推理题",
        ),
    ]


QUIZ_GENERATION_OUTPUT_CONTRACT = QuizGenerationContract.to_output_contract()
QUIZ_SUPERVISOR_OUTPUT_CONTRACT = QuizSupervisorContract.to_output_contract()


class QuizFallbackRules(FallbackRules):
    """自测题降级：只保留题干列表。"""

    sections = [
        Lines("questions"),
    ]
    empty_text = "笔记过短或缺少可推理关系，暂不出题"
    structured = {"field": "questions"}


QUIZ_FALLBACK_RULES = QuizFallbackRules()

__all__ = [
    "QUIZ_FALLBACK_RULES",
    "QUIZ_GENERATION_OUTPUT_CONTRACT",
    "QUIZ_SUPERVISOR_OUTPUT_CONTRACT",
]
