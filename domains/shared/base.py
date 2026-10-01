"""domains.shared.base —— 业务领域基础协议与生命周期规范。

各领域（meeting, notes）实现本协议定义的钩子，
使得 app/ 网关层无需编写具体任务的特判逻辑（消除上帝代码）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class PreparedTaskInput:
    """领域预处理后的标准化输入。"""

    line: str
    user_id: str
    input_files: list[Path] | Path | None = None
    extra_line_inputs: dict[str, str] = field(default_factory=dict)
    modes: dict[str, str] = field(default_factory=dict)
    templates: dict[str, Path] = field(default_factory=dict)
    profile_file: Path | None = None
    subject: str = ""
    project: str = ""
    memory: bool = False
    time: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class DomainHooksProtocol(Protocol):
    """领域生命周期钩子协议。"""

    memory_lines: frozenset[str]

    async def prepare_task_input(
        self,
        line: str,
        user_id: str,
        req: Any,
        data_resolver: Any,
    ) -> PreparedTaskInput:
        """各领域负责自己专属的材料解析与预处理（如 agenda 专有 OCR、checklist 目录核验）。"""
        ...

    def enrich_response_data(
        self,
        line: str,
        result: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        """各领域负责自己特有摘要与监视指标的计算（如 checklist 摘要卡片、catalog 体检）。"""
        ...


__all__ = ["DomainHooksProtocol", "PreparedTaskInput"]
