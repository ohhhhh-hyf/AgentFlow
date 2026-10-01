"""结构化生成步的共享基类：agent / supervisor 两条样板链的**唯一实现**。

为什么放这里：``tasks/<线>/steps/{线}_agent.py`` 与 ``{线}_supervisor.py`` 原本
是每个任务线各抄一份的同一段函数体——14 个 agent 里 4 个、13 个 LLM supervisor 里
12 个只在「prompt 常量 / 输出模型 / 契约常量 / label / 可选额外 kwarg」上有差别，
真正的逻辑一行都没有（2026-09 逐文件 diff 确认）。基类把这 5 个差异提成类属性，
于是每个文件只剩「声明自己是谁」。

**刻意不动的**：catalog / library / agenda_minutes / minutes_trace / minutes /
minutes_styles 的 agent 与 supervisor 各有真实差异（本地确定性预审、后处理强约束、
确定性管线、不调 LLM 等），它们继续各自实现 run/review，不继承本基类。

`extra_kwargs` 用来逐字保留历史上的调用差异（label 拼写、max_tokens、显式
temperature 等）——**不要"顺手统一"**：``risks`` 线的 label 是 ``risk/supervisor``
而不是 ``risks/supervisor``，``agenda_minutes``/``minutes`` 传 ``max_tokens=3000``、
``checklist`` 传 ``1024``，这些值进的是监控口径与请求参数，改了就变了行为。
"""
from __future__ import annotations

from typing import Any, ClassVar, TypeVar

from infra.llm import LLMClient

from .supervisor import GlobalSupervisor

T = TypeVar("T")


def _missing(owner: object, *names: str) -> list[str]:
    """列出子类没声明的必填类属性（空串也算没声明）。"""
    out: list[str] = []
    for name in names:
        value = getattr(type(owner), name, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            out.append(name)
    return out


class StructuredGenerationAgent:
    """结构化生成 Agent：一次 ``structured()`` 调用，输出契约模型。

    子类声明：``system_prompt`` / ``output_model`` / ``output_contract`` / ``label``
    （可选 ``extra_kwargs``）。
    """

    system_prompt: ClassVar[str] = ""
    output_model: ClassVar[type] = None  # type: ignore[assignment]
    output_contract: ClassVar[str] = ""
    label: ClassVar[str] = ""
    extra_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, client: LLMClient) -> None:
        missing = _missing(self, "system_prompt", "output_model", "output_contract", "label")
        if missing:
            raise TypeError(
                f"{type(self).__name__} 未声明类属性：{', '.join(missing)}"
                "（StructuredGenerationAgent 的子类必须显式声明，避免退回空 prompt）"
            )
        self.client = client

    async def run(self, shared_context: str) -> T:
        return await self.client.structured(
            self.system_prompt,
            shared_context,
            self.output_model,
            self.output_contract,
            label=self.label,
            **self.extra_kwargs,
        )


class StructuredDomainSupervisor:
    """领域监督者：全局整体标准（注入）+ 领域规则，一次调用完成双重评判。

    子类声明：``domain_prompt`` / ``review_model`` / ``output_contract`` / ``label``
    （可选 ``extra_kwargs``）。

    与旧实现一致：``_system_prompt`` 在 ``__init__`` 里算好并缓存，``review`` 复用，
    因此每次审核只发一次 LLM 调用。
    """

    domain_prompt: ClassVar[str] = ""
    review_model: ClassVar[type] = None  # type: ignore[assignment]
    output_contract: ClassVar[str] = ""
    label: ClassVar[str] = ""
    extra_kwargs: ClassVar[dict[str, Any]] = {}

    def __init__(self, client: LLMClient) -> None:
        missing = _missing(
            self, "domain_prompt", "review_model", "output_contract", "label"
        )
        if missing:
            raise TypeError(
                f"{type(self).__name__} 未声明类属性：{', '.join(missing)}"
                "（StructuredDomainSupervisor 的子类必须显式声明，"
                "否则 GlobalSupervisor.build_prompt 会静默只留全局标准）"
            )
        self.client = client
        self._system_prompt = GlobalSupervisor.build_prompt(self.domain_prompt)

    async def review(self, context: str) -> T:
        return await self.client.structured(
            self._system_prompt,
            context,
            self.review_model,
            self.output_contract,
            label=self.label,
            **self.extra_kwargs,
        )


__all__ = ["StructuredDomainSupervisor", "StructuredGenerationAgent"]
