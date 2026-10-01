"""模板栏位 → 理解层可跳字段（单线裁剪的第二步）。

为什么（2026-09-18 耗时复盘）：minutes 单线跑时，会议理解是整个流水线最贵的中间件——
它的 JSON 要进草稿、审核、装配每一次调用的上下文（实测一篇 6000 字发布会实录抽了
6.2k token / 1.3 万字符），而 ``_meeting_pack`` 给 minutes 的包只取
meeting_brief / meeting_purpose / scene / topics / decisions / risks / open_questions。
其中 risks / open_questions 也只有在模板**真的写了风险/未决栏**时才会进正文：
发布会四栏、课堂四栏、讲座四栏、访谈三栏都用不到。

规则只做"确认用不到才跳"的减法：模板正文（中文名、写作要求、栏名、栏位说明）里出现该
字段的任一关键词就保留，完全不出现才跳过。宁可少跳，不可丢内容；新增模板无需登记，
词表命中即保留，是安全侧的默认。
"""
from __future__ import annotations

# 风险/隐患类：模板里出现任一词 → risks 照常抽取
RISK_KEYWORDS: tuple[str, ...] = (
    "风险",
    "隐患",
    "阻塞",
    "卡点",
    "障碍",
    "威胁",
    "未决",
    "待确认",
    "待定",
    "待澄清",
    "待明确",
    "疑问",
    "悬而未决",
    "待解决",
    "未解决",
    "未达成",
)

# 未决/待确认类：模板里出现任一词 → open_questions 照常抽取
OPEN_QUESTION_KEYWORDS: tuple[str, ...] = (
    "未决",
    "待确认",
    "待定",
    "待澄清",
    "待明确",
    "疑问",
    "悬而未决",
    "待解决",
    "未解决",
    "未达成",
    "待议",
    "后续确认",
)

FIELD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "risks": RISK_KEYWORDS,
    "open_questions": OPEN_QUESTION_KEYWORDS,
}


def skip_fields_for_template(template_text: str) -> frozenset[str]:
    """模板用不到的字段 → 可跳过集合；空模板返回空集（不裁）。"""
    text = template_text or ""
    if not text.strip():
        return frozenset()
    return frozenset(
        field
        for field, words in FIELD_KEYWORDS.items()
        if not any(word in text for word in words)
    )


__all__ = [
    "FIELD_KEYWORDS",
    "OPEN_QUESTION_KEYWORDS",
    "RISK_KEYWORDS",
    "skip_fields_for_template",
]
