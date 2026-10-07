"""minutes_styles contract definitions.

「多样式纪要」任务线：同一场会议，按时间线 / 逻辑总分 / 因果推导 / 主体责权 / 决策时效
五种组织模式分别成稿。契约采用统一的 sections 结构承载不同组织段落，
模式由 mode 字段标明（time / logic / causal / party / urgency）。

Required by tools/codegen/sync_domain.py:
- class MultiStylesGenerationContract(GenerationContract)
- class MultiStylesSupervisorContract(SupervisorContract)
- MULTI_STYLES_GENERATION_OUTPUT_CONTRACT = MultiStylesGenerationContract.to_json_template()
- MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT = MultiStylesSupervisorContract.to_json_template()

Optional fallback:
- class MultiStylesFallbackRules(FallbackRules)
- MULTI_STYLES_FALLBACK_RULES = MultiStylesFallbackRules()
"""
from __future__ import annotations

from core.schema.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, SupervisorContract,
)
from core.schema.fallback_rules import FallbackRules, Lines, Raw
from core.schema.validation import OutputValidationError

def _as_content_string(content: object) -> str:
    """把 content 收成字符串；数组用换行拼接，其它类型转成文本，不因形态否掉整稿。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        lines: list[str] = []
        for part in content:
            if isinstance(part, str):
                piece = part.strip()
            elif isinstance(part, dict):
                name = str(
                    part.get("title") or part.get("action") or ""
                ).strip()
                body = str(
                    part.get("content") or part.get("text") or ""
                ).strip()
                piece = f"{name}：{body}" if name and body else (name or body)
            else:
                piece = str(part or "").strip()
            if piece:
                lines.append(piece)
        return "\n".join(lines)
    if content is None:
        return ""
    return str(content).strip()


def _strip_repeated_title(title: str, content: str) -> str:
    """去掉 content 开头重复的段标题，避免「桶名：动作名：」双冒号。"""
    text = content
    for prefix in (f"{title}：", f"{title}:"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
    return text


def enforce_minutes_styles_sections(data: dict) -> None:
    """只挡住完全空稿；能收口的段落就留下，不因个别段形态否掉整份输出。"""
    sections = data.get("sections")
    if not isinstance(sections, list):
        raise OutputValidationError("sections 必须是数组")
    cleaned: list[dict] = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = _strip_repeated_title(title, _as_content_string(item.get("content")))
        if not title or not content:
            continue
        cleaned.append({"title": title, "content": content})
    if not cleaned:
        raise OutputValidationError("sections 不能为空")
    data["sections"] = cleaned


class MultiStylesGenerationContract(GenerationContract):
    """多样式纪要生成契约（五模式共用统一结构）。

    sections 为有序组织段落，五种模式的标题集合互斥：
    - brief     （高管速览）：核心结论 / 关键决策 / 重大风险
    - topic     （业务归类）：总体概括 / 分类议题 / 后续安排
    - review    （方案权衡）：评审结论 / 方案对比 / 遗留事项
    - retro     （复盘攻坚）：现状说明 / 原因分析 / 改进措施
    - alignment （多方对齐）：对齐共识 / 各方责任 / 接口约定
    """

    fields = [
        EnumField("mode", ["brief", "topic", "review", "retro", "alignment"]),
        StrField("title", "纪要标题（一句话，优先沿用会议理解的 meeting_purpose）"),
        ObjListField("sections", [
            StrField("title", "本段标题（对应当前模式模板中的栏目名）"),
            StrField(
                "content",
                "非空字符串，按模板指令排版的内容文本，包含 ### 议题小节与 - 列表项，禁止用数组代替",
            ),
        ]),
        StrField("summary", "一段话总摘要（30-60 字，用当前模式口吻概括，不复述 title）"),
    ]


class MultiStylesSupervisorContract(SupervisorContract):
    """多样式纪要审核契约：议题覆盖度 + 模式对齐 + 格式排版规范。"""

    decision = Decision()
    feedback = Feedback("Required when decision=revise; use [] for approve/reject — the field must always appear")
    checks = [
        Check(
            "topic_coverage_check",
            "仅拦截上游议题树的核心业务议题在当前纪要中严重遗漏的情况；次要细节未提及不拦截",
        ),
        Check(
            "mode_alignment_check",
            "仅拦截整篇完全偏离当前模式定位（如 brief 写成长篇争辩/流水账；retro 缺失诱因或对策；review 缺失方案对比与妥协代价；alignment 未按主体聚合）。小幅偏差一律通过",
        ),
        Check(
            "formatting_quality_check",
            "仅拦截 sections 完全为空、标题与内容明显错位、或堆砌成未分节大段文本墙；清单格式微瑕、标点不规范不拦截",
        ),
    ]


MULTI_STYLES_GENERATION_OUTPUT_CONTRACT = MultiStylesGenerationContract.to_output_contract()
MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT = MultiStylesSupervisorContract.to_output_contract()


class MultiStylesFallbackRules(FallbackRules):
    """降级拼装：标题 + 各组织段落 + 总摘要。"""

    sections = [
        Raw("title"),
        Lines("sections"),
        Raw("summary"),
    ]
    empty_text = "暂无多样式纪要"
    disclaimer = False
    structured = {"field": "sections"}


MULTI_STYLES_FALLBACK_RULES = MultiStylesFallbackRules()

__all__ = [
    "MULTI_STYLES_GENERATION_OUTPUT_CONTRACT",
    "MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT",
    "MULTI_STYLES_FALLBACK_RULES",
    "enforce_minutes_styles_sections",
]
