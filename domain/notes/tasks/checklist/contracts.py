"""checklist 契约：只给已激活的 Catalog KP 写复习卡片，禁止新建知识点。"""
from __future__ import annotations

from tools.contracts import (
    Check,
    Decision,
    Feedback,
    GenerationContract,
    ObjListField,
    StrField,
    StrListField,
    SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines, Raw


class ChecklistGenerationContract(GenerationContract):
    """卡片正文；KP 范围由程序从 Catalog 匹配，模型不得扩点。"""

    fields = [
        StrField("course", "沿用 Catalog 课程名"),
        StrField("catalog_version", "抄输入里的目录版本，不要改"),
        ObjListField(
            "cards",
            [
                StrField("kp_id", "必须是 Catalog 里已有的 id，如 kp_006"),
                StrField(
                    "exam_preview",
                    "考法预判：S/A 2-4 句；B/C 1-2 句（说明这次只需了解/当前置）。写清题型、老师点到的变形/流程；无依据不要写必考或具体概率",
                ),
                StrListField(
                    "key_facts",
                    "必须会的硬知识：S/A 3-6 条；B/C 2-3 条。公式或判断标准写完整；不要写成「老师说了」",
                ),
                StrField(
                    "explain",
                    "讲解：S/A 180-320 字；B/C 60-120 字（定义 + 一条限制），档位见输入中每张卡。定义或公式 + 适用边界 + 老师点到的变形 + 笔记缺项补什么；禁止空话",
                ),
                StrListField(
                    "method_steps",
                    "可执行步骤：S/A 4-6 步；B/C 2-3 步。method/application=解题；theorem/concept=判断流程；formula=使用与条件检查。每步写具体操作，不要「按方法做」",
                ),
                StrListField(
                    "pitfalls",
                    "易错：S/A 2-4 条；B/C 0-2 条。优先老师原话限制，并给具体反例或使用边界；无依据不要编",
                ),
            ],
        ),
        StrListField(
            "uncertain_quotes",
            "老师原话里对不上任何 Catalog KP 的片段，不要为此新建知识点",
        ),
        StrListField("strategy", "程序生成，输出 []"),
        ObjListField(
            "phases",
            [
                StrField("title", "阶段名"),
                StrField("goal", "阶段目标"),
                StrListField("kp_ids", "本阶段 KP id"),
                StrListField("names", "本阶段 KP 名"),
                StrField("check", "完成标准"),
            ],
            desc="程序生成，输出 []",
        ),
    ]


class ChecklistSupervisorContract(SupervisorContract):
    decision = Decision()
    feedback = Feedback("仅当 decision=revise 时填写，必须具体可执行")
    checks = [
        Check(
            "checklist_check",
            "仅拦截：cards 里出现 Catalog 没有的 kp_id、编造新知识点、"
            "无老师依据却写必考/具体概率、输出与目录无关的复习鸡汤",
        ),
    ]


CHECKLIST_GENERATION_OUTPUT_CONTRACT = ChecklistGenerationContract.to_output_contract()
CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT = ChecklistSupervisorContract.to_output_contract()


class ChecklistFallbackRules(FallbackRules):
    sections = [Raw("course"), Lines("cards")]
    empty_text = "没有可用的知识目录，请先运行 catalog"
    structured = {"field": "cards"}


CHECKLIST_FALLBACK_RULES = ChecklistFallbackRules()

__all__ = [
    "CHECKLIST_FALLBACK_RULES",
    "CHECKLIST_GENERATION_OUTPUT_CONTRACT",
    "CHECKLIST_SUPERVISOR_OUTPUT_CONTRACT",
]
