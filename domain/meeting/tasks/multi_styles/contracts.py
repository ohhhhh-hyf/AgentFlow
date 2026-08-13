"""multi_styles contract definitions.

「多样式纪要」任务线：同一场会议，按时间线 / 逻辑总分 / 因果推导 / 主体责权 / 决策时效
五种组织模式分别成稿。契约采用统一的 sections 结构承载不同组织段落，
模式由 mode 字段标明（time / logic / causal / party / urgency）。

Required by tools/scripts/sync_domain.py:
- class MultiStylesGenerationContract(GenerationContract)
- class MultiStylesSupervisorContract(SupervisorContract)
- MULTI_STYLES_GENERATION_OUTPUT_CONTRACT = MultiStylesGenerationContract.to_json_template()
- MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT = MultiStylesSupervisorContract.to_json_template()

Optional fallback:
- class MultiStylesFallbackRules(FallbackRules)
- MULTI_STYLES_FALLBACK_RULES = MultiStylesFallbackRules()
"""
from __future__ import annotations

from tools.contracts import (
    Check, Decision, EnumField, Feedback, GenerationContract, ObjListField,
    StrField, SupervisorContract,
)
from tools.fallback_rules import FallbackRules, Lines, Raw
from tools.validation import OutputValidationError

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


def enforce_multi_styles_sections(data: dict) -> None:
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
    - time    （时间线 / 叙事节奏）：会前准备与召开 / 会议展开 / 问题提出 / 各方回应 / 结论与指示 / 散会与后续
    - logic   （逻辑总分 / 归纳分类）：会议性质 / 总体结论 / 分类议题 / 会议要求 / 后续安排
    - causal  （因果推导 / 风险与动因）：起因 / 现状 / 隐患 / 对策
    - party   （主体责权 / 立场与博弈）：标题直接用主体命名，可带立场标签（如「运营部反馈」），一方一段
    - urgency （决策时效 / 执行倒计时）：立即办理 / 限期完成 / 近期推进 / 下次议定 / 长期监测；content 为清单体
    """

    fields = [
        EnumField("mode", ["time", "logic", "causal", "party", "urgency"]),
        StrField("title", "纪要标题（一句话，优先沿用会议理解的 meeting_purpose）"),
        ObjListField("sections", [
            StrField("title", "本段标题（必须取自当前模式的标题集合，见契约说明）"),
            StrField(
                "content",
                "非空字符串，禁止用数组代替；"
                "time/logic/causal/party 写书面完整句；"
                "urgency 用换行分隔的「动作名：谁+做什么+原文时限」，行首不要重复段标题",
            ),
        ]),
        StrField("summary", "一段话总摘要（30-60 字，用当前模式口吻概括，不复述 title）"),
    ]


class MultiStylesSupervisorContract(SupervisorContract):
    """多样式纪要审核契约：组织逻辑正确 + 事实忠诚。"""

    decision = Decision()
    feedback = Feedback("Only fill when decision=revise; be specific and evidence-based")
    checks = [
        Check(
            "mode_check",
            "仅拦截整篇完全串成另一种模式（如 time 全文按立即办理分桶、party 标题全是起因/现状）。"
            "段内用了「方面」、起因夹带现状、urgency 分桶偏松，一律通过",
        ),
        Check(
            "facts_check",
            "仅拦截明显编造或张冠李戴；小幅整理措辞、遗漏次要细节不拦截",
        ),
        Check(
            "consistency_check",
            "仅拦截 sections 完全空或标题与内容明显对不上；"
            "重复、残句、清单形态不完美不拦截",
        ),
    ]


MULTI_STYLES_GENERATION_OUTPUT_CONTRACT = MultiStylesGenerationContract.to_json_template()
MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT = MultiStylesSupervisorContract.to_json_template()


class MultiStylesFallbackRules(FallbackRules):
    """降级拼装：标题 + 各组织段落 + 总摘要。"""

    sections = [
        Raw("title"),
        Lines("sections"),
        Raw("summary"),
    ]
    empty_text = "暂无多样式纪要"
    disclaimer = True
    structured = {"field": "sections"}


MULTI_STYLES_FALLBACK_RULES = MultiStylesFallbackRules()

__all__ = [
    "MULTI_STYLES_GENERATION_OUTPUT_CONTRACT",
    "MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT",
    "MULTI_STYLES_FALLBACK_RULES",
    "enforce_multi_styles_sections",
]
