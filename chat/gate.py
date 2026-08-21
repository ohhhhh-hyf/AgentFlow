"""检索门控：决定当前问题是否需要检索记忆 / 知识库。

原则（一句话）：不是"检索到了就展示"，而是"当前问题确实需要，才检索、才使用"。

三层机制：
1. 规则短路（零成本）：寒暄/纯语气短句 → 直接不检索
2. LLM 门控（1 次调用）：模糊问题 → 判断 need_memory / need_knowledge（分开判断，省一半检索）
3. 保守兜底：门控失败或低置信 → 默认"都需要检索"（宁可多检索，不漏检）
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from tools.validation import (
    OutputValidationError,
    _choice,
    _exact_fields,
    _string,
)

logger = logging.getLogger(__name__)

GATE_HISTORY_LAST = 4

# ── 规则短路：寒暄/纯语气短句 ───────────────────────────────

_GREETING_WORDS = (
    "你好", "您好", "嗨", "哈喽", "hello", "hi", "hey",
    "在吗", "在不在", "谢谢", "感谢", "辛苦了",
    "再见", "拜拜", "晚安", "早上好", "中午好", "下午好", "晚上好",
    "嗯", "哦", "好的", "好", "可以", "没问题", "ok", "okay", "yes", "no",
    "哈哈", "嗯嗯", "对", "是的", "是吧", "就是", "懂了", "明白了",
    "?", "？",
)
_GREETING_RE = re.compile(
    r"^[" + "".join(_GREETING_WORDS) + r"\s！!。.?？~～，,、…·]*$"
)
_RULE_MAX_LEN = 12

# ── 规则短路：自我表露（偏好/习惯/自我介绍）→ 走画像，不检索 ──

_SELF_DISCLOSURE_RE = re.compile(
    r"我(?:喜欢|习惯|偏好|偏爱|倾向于|更倾向|比较喜欢|平时喜欢|做事喜欢|一般喜欢)"
)
# 疑问句标记：问号或疑问词 → 不短路（"我喜欢这个方案吗？"是提问）
_QUESTION_RE = re.compile(
    r"[?？]|什么|怎么|为什么|如何|哪|谁|几|多少|吗|呢|是不是|能不能|行不行|可不可以|要不要|可否"
)


def rule_self_disclosure(question: str):
    """自我表露句（"我喜欢先给结论""我习惯先看结果"）→ 不检索，走用户画像。

    排除疑问句（"我喜欢这个方案吗？"仍需正常处理）。
    """
    q = (question or "").strip()
    if not q or _QUESTION_RE.search(q):
        return None
    if _SELF_DISCLOSURE_RE.search(q):
        return GateDecision(
            False, False, "自我表露（偏好/习惯），走用户画像，无需检索", "high"
        )
    return None


def rule_short_circuit(question: str):
    """纯寒暄/语气短句 → 返回"不检索"门控；其它返回 None（交给 LLM 门控）。

    只对整句都是寒暄词的短句短路，避免误伤"你好，上次会议说了什么"这类
    带真实问题的混合句。
    """
    q = (question or "").strip()
    if not q:
        return GateDecision(False, False, "空输入，无需检索", "high")
    if len(q) <= _RULE_MAX_LEN and _GREETING_RE.match(q):
        return GateDecision(False, False, "寒暄/闲聊，无需依赖历史或资料", "high")
    return None


# ── LLM 门控 ────────────────────────────────────────────────

GATE_SYSTEM_PROMPT = """你是「检索门控」。判断当前用户问题是否需要依赖"历史信息 / 用户记忆 / 内部知识库"才能准确回答。

规则：
- **默认不需要检索**；只有当前问题必须依赖历史/记忆/内部知识才能准确回答时，才需要
- 仅仅"人物相同、项目相同、语义相似"不能作为检索理由
- 如果不使用记忆/知识库也能自然完整回答，则直接普通对话，不需要检索
- 用户表达个人偏好、习惯、自我介绍（"我喜欢…""我习惯…""我是开发人员"）属于**自我表露**，
  是用户画像的素材，**不需要检索**记忆或知识库
- 询问"上次/之前/我记得/我们聊过/会议/项目进展/他/她"等涉及过往信息 → 需要记忆（need_memory）
- 询问"资料/文档/课件/笔记/知识点/公式/定义"等内部知识 → 需要知识库（need_knowledge）
- 寒暄、闲聊、通用常识、只需推理的问题 → 都不需要

输出字段：
- need_memory：是否需要检索该用户的历史记忆（会议记录/对话事实）
- need_knowledge：是否需要检索该用户的知识库（资料/课件/笔记）
- reason：判断理由（一句话）
- confidence：判断置信度（high / medium / low；不确定时给 low）"""

GATE_OUTPUT_CONTRACT = """{
  "need_memory": false,
  "need_knowledge": false,
  "reason": "",
  "confidence": "high"
}
字段说明：
- need_memory：是否需要检索该用户的历史记忆（会议记录/对话事实）
- need_knowledge：是否需要检索该用户的知识库（资料/课件/笔记）
- reason：判断理由（一句话）
- confidence：判断置信度（high / medium / low；不确定时给 low）"""


@dataclass
class GateDecision:
    need_memory: bool = False
    need_knowledge: bool = False
    reason: str = ""
    confidence: str = "high"

    @classmethod
    def validate(cls, data: dict) -> "GateDecision":
        _exact_fields(data, {"need_memory", "need_knowledge", "reason", "confidence"}, cls.__name__)
        if not isinstance(data["need_memory"], bool):
            raise OutputValidationError("need_memory 必须是布尔值")
        if not isinstance(data["need_knowledge"], bool):
            raise OutputValidationError("need_knowledge 必须是布尔值")
        _string(data["reason"], "reason")
        _choice(data["confidence"], {"high", "medium", "low"}, "confidence")
        return cls(
            need_memory=bool(data["need_memory"]),
            need_knowledge=bool(data["need_knowledge"]),
            reason=str(data["reason"]),
            confidence=str(data["confidence"]),
        )


async def llm_gate(client, question: str, history: list[dict[str, str]] | None = None) -> GateDecision:
    """LLM 门控：判断是否检索。失败/低置信 → 保守"都需要检索"。"""
    turns = [
        f"{'用户' if m.get('role') == 'user' else '助手'}：{m.get('content')}"
        for m in (history or [])[-GATE_HISTORY_LAST:]
        if m.get("content")
    ]
    history_text = "\n".join(turns) if turns else "（无）"
    try:
        decision = await client.structured(
            GATE_SYSTEM_PROMPT,
            f"当前问题：{question}\n\n最近对话：\n{history_text}",
            GateDecision,
            GATE_OUTPUT_CONTRACT,
            temperature=0.0,
            label="chat/gate",
        )
        if decision.confidence == "low":
            logger.info("门控低置信（%s），保守检索", decision.reason)
            return GateDecision(True, True, f"门控低置信，保守检索（{decision.reason}）", "low")
        return decision
    except Exception as exc:  # noqa: BLE001 - 门控失败不阻断提问
        logger.warning("检索门控失败，保守检索", exc_info=True)
        return GateDecision(True, True, "门控失败，保守检索", "low")


async def decide(
    question: str,
    client,
    history: list[dict[str, str]] | None = None,
) -> GateDecision:
    """检索门控主入口：规则短路（寒暄→自我表露）优先，其次 LLM 门控。"""
    q = (question or "").strip()
    if not q:
        return GateDecision(False, False, "空输入，无需检索", "high")
    rule = rule_short_circuit(q)
    if rule is not None:
        return rule
    disclosure = rule_self_disclosure(q)
    if disclosure is not None:
        return disclosure
    return await llm_gate(client, q, history)


__all__ = [
    "GATE_OUTPUT_CONTRACT",
    "GATE_SYSTEM_PROMPT",
    "GateDecision",
    "decide",
    "llm_gate",
    "rule_self_disclosure",
    "rule_short_circuit",
]
