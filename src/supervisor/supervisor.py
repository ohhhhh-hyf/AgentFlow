"""全局监督器实现 —— 把整体标准注入到各任务组的 supervisor prompt。

执行方式（Prompt 注入）：任务 supervisor 的领域规则与全局整体标准
拼接为一份完整 prompt，由任务 supervisor 一次 LLM 调用完成
「整体标准 + 领域标准」的双重评判；全局监督器本身不单独发起调用。
"""
from __future__ import annotations

from .supervisor_prompt import GLOBAL_SUPERVISOR_PROMPT


def inject_global_standard(domain_prompt: str) -> str:
    """把全局整体标准注入到任务 supervisor 的领域 prompt 中。

    Args:
        domain_prompt: 任务组的领域审核规则（含领域输出契约等）。

    Returns:
        拼接后的完整 supervisor prompt：全局标准在前，领域规则在后。
    """
    domain_prompt = domain_prompt.strip()
    if not domain_prompt:
        return GLOBAL_SUPERVISOR_PROMPT
    return f"{GLOBAL_SUPERVISOR_PROMPT}\n\n{domain_prompt}"


class GlobalSupervisor:
    """全局监督器：向各任务 supervisor 注入整体标准。

    设计上不持有 LLM 客户端、不发起调用；仅负责 prompt 组装。
    各任务 supervisor 实例化时调用 :meth:`build_prompt` 获取完整 prompt。
    """

    @staticmethod
    def build_prompt(domain_prompt: str) -> str:
        return inject_global_standard(domain_prompt)


__all__ = [
    "GLOBAL_SUPERVISOR_PROMPT",
    "GlobalSupervisor",
    "inject_global_standard",
]
