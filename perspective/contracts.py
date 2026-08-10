"""perspective 公共包的契约定义（prompt 文本见 prompts.py）。

本模块只放"结构化规范"：生成契约类 PerspectiveModelingGenerationContract
→ to_json_template() 生成生成契约 prompt。

注意：本包不参与任何 domain 的 codegen 扫描（codegen 只扫 domain 目录），
模型由本包自带迷你生成器 gen_models.py 维护（复用 codegen 生成逻辑）。
"""
from __future__ import annotations

from tools.contracts import (
    EnumField, GenerationContract, StrField, StrListField,
)


class PerspectiveModelingGenerationContract(GenerationContract):
    """视角建模输出契约。"""

    fields = [
        EnumField("confidence", ["high", "medium", "low"]),
        StrField("name", "用户姓名，客观模式下通常为null"),
        StrField("inferred_role", "基于原文推断的角色，无依据时为null"),
        StrListField("responsibilities", "本次会议中涉及的该用户/全员职责"),
        StrListField("goals", "本次会议中该用户/全员应达成的目标"),
        StrListField("concerns", "该用户/全员应关注的风险、不确定因素"),
        StrListField("relevant_topics", "与该用户/全员直接相关的议题"),
        StrListField("evidence", "原文中支撑以上判断的具体语句"),
    ]


PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT = (
    PerspectiveModelingGenerationContract.to_json_template()
)

__all__ = [
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
]
