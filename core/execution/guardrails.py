"""确定性事实门禁：毫秒级预检草稿中的历史记忆契约（零 LLM）。

定位（SUPERVISOR_AND_UNDERSTANDING_OPTIMIZATION_PLAN · 步骤五）：

- **人名与数字**：人名归属与数字忠实度交由生成端 Prompt 强约束与长文本 LLM Supervisor 深度把关，
  不再采用粗粒度正则机械比对，彻底避免“主讲人/提问者”等公文角色代称与排版序号造成假阳性误报与阻断；
- **对照契约**：记忆未注入（``memory_on=False``）时 ``history_comparison`` 必须为空，
  凭空产出的"历史对照"按捏造拦截。

规则全过是"免审放行"的依据（激进模式：原文 2000~5000 字区间内直接 Approve，
开关 ``SUPERVISOR_GUARDRAIL``，默认开启）；命中红线的草稿照常送 LLM 复核。

边界（刻意如此）：本模块只覆盖确定性"形"（记忆契约），业务结论与深度数值分析
由生成端 Prompt 约束与 LLM 审核兜底——因此激进模式只在中等篇幅区间启用，长会（>5000
字符）始终走 LLM 审核；短会另有 <2000 字的无条件快速通道（见
``DomainNodes._make_supervisor_node``）。
"""
from __future__ import annotations

import os
from typing import Any

_ENV_KEY = "SUPERVISOR_GUARDRAIL"


def guardrail_fast_path_enabled() -> bool:
    """激进放行开关：``SUPERVISOR_GUARDRAIL=off``（或 0/false/no）关闭，默认开启。"""
    value = os.getenv(_ENV_KEY, "on").strip().lower()
    return value not in ("0", "false", "off", "no")


_MAX_FINDINGS = 12


def quick_facts_guardrail(
    draft: object,
    speakers: list[dict[str, Any]] | None = None,
    transcript: str = "",
    *,
    memory_on: bool = True,
) -> tuple[bool, list[str]]:
    """毫秒级确定性事实核查：历史记忆契约。

    人名在册与关键数字指标已彻底剥离粗暴正则比对，由生成端 Prompt 与 LLM Supervisor 把关。
    返回 ``(是否全过, findings)``；``findings`` 为空表示可免审放行。
    ``history_comparison``（程序注入的跨场对照）在 ``memory_on=False``（本次无记忆注入）时
    按生成契约必须为空——凭空产出的"历史对照"是确定性可判的捏造，直接拦下送审。
    本函数不抛错：任何内部异常都会向上冒泡由调用方按"未通过"处理。
    """
    findings: list[str] = []
    if not memory_on and isinstance(draft, dict):
        comparison = draft.get("history_comparison")
        if isinstance(comparison, list) and any(str(x).strip() for x in comparison):
            findings.append("无历史记忆注入却产出历史对照（生成契约要求为空 []）")
    return (not findings), findings[:_MAX_FINDINGS]


__all__ = ["guardrail_fast_path_enabled", "quick_facts_guardrail"]
