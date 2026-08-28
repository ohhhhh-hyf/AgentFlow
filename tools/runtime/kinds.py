"""任务线种类：决定渲染路径、CLI、sidecar 和结构抽取。

三种衣服：

- ``llm_extract``：列表抽取（risk / actions / review / quiz）
- ``llm_document``：成篇文本（纪要 / 多样式 / 思维导图）
- ``deterministic_pipeline``：程序落钉（minutes_trace；无模板的 graph）

种类写在 ``domain_config.LINE_KINDS``，不进 sync_domain 生成区。
minutes_trace 是文档化的 pipeline + sidecar，不是和 risk 对等的「又一条 3-step 线」。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


LLM_EXTRACT = "llm_extract"
LLM_DOCUMENT = "llm_document"
DETERMINISTIC_PIPELINE = "deterministic_pipeline"

KNOWN_KINDS = (LLM_EXTRACT, LLM_DOCUMENT, DETERMINISTIC_PIPELINE)

_KIND_DEFAULTS: dict[str, dict] = {
    LLM_EXTRACT: {
        "sidecar": False,
        "cli_template": True,
        "cli_mode": False,
        "llm_render": "always",
        "extracts_structure": True,
    },
    LLM_DOCUMENT: {
        "sidecar": False,
        "cli_template": True,
        "cli_mode": False,
        "llm_render": "always",
        "extracts_structure": False,
    },
    DETERMINISTIC_PIPELINE: {
        "sidecar": False,
        "cli_template": False,
        "cli_mode": False,
        "llm_render": "never",
        "extracts_structure": False,
    },
}


@dataclass(frozen=True)
class LinePolicy:
    kind: str
    sidecar: bool = False
    cli_template: bool = True
    cli_mode: bool = False
    llm_render: str = "always"
    extracts_structure: bool = False

    def uses_llm_render(self, has_template: bool) -> bool:
        if self.llm_render == "always":
            return True
        if self.llm_render == "never":
            return False
        if self.llm_render == "if_template":
            return bool(has_template)
        raise ValueError(f"未知 llm_render：{self.llm_render}")


def policy_for(kind: str, **overrides: object) -> LinePolicy:
    if kind not in _KIND_DEFAULTS:
        raise ValueError(f"未知任务线种类：{kind}（可用：{', '.join(KNOWN_KINDS)}）")
    data = dict(_KIND_DEFAULTS[kind])
    data.update(overrides)
    return LinePolicy(kind=kind, **data)


def _parse_spec(spec: object) -> LinePolicy:
    if isinstance(spec, LinePolicy):
        return spec
    if isinstance(spec, str):
        return policy_for(spec)
    if isinstance(spec, Mapping):
        payload = dict(spec)
        kind = payload.pop("kind", None)
        if not kind:
            raise ValueError(f"LINE_KINDS 条目缺少 kind：{spec!r}")
        return policy_for(str(kind), **payload)
    raise TypeError(f"LINE_KINDS 条目无法解析：{spec!r}")


def resolve_line_policies(
    specs: Mapping[str, object],
    required: Iterable[str] | None = None,
) -> dict[str, LinePolicy]:
    policies = {name: _parse_spec(spec) for name, spec in specs.items()}
    if required is not None:
        missing = [name for name in required if name not in policies]
        if missing:
            raise ValueError(f"LINE_KINDS 未声明：{missing}")
    return policies


def sidecar_lines(
    line_names: Iterable[str],
    policies: Mapping[str, LinePolicy],
) -> list[str]:
    return [name for name in line_names if policies.get(name) and policies[name].sidecar]


__all__ = [
    "DETERMINISTIC_PIPELINE",
    "KNOWN_KINDS",
    "LLM_DOCUMENT",
    "LLM_EXTRACT",
    "LinePolicy",
    "policy_for",
    "resolve_line_policies",
    "sidecar_lines",
]
