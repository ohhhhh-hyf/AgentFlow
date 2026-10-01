"""core.runner.events —— 统一领域事件模型。

设计原则：
1. 核心引擎（Runner/DAG）仅产出纯 Python 结构化领域事件（TaskEvent）；
2. 彻底切断与 Web 传输层（FastAPI StreamingResponse、NDJSON 字节流）的反向依赖；
3. API 端负责将 TaskEvent 包装为 HTTP NDJSON 流；
4. Worker 端直接迭代 TaskEvent 写入 Redis，免去字节解码再解析的二次损耗。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TaskEvent:
    """领域事件对象。"""

    type: Literal["phase", "chunk", "done", "error"]
    node: str = ""
    line: str = ""
    title: str = ""
    text: str = ""
    code: int = 0
    message: str = ""
    quality_warning: str = ""
    monitor: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转为字典序列化形式。"""
        if self.type == "phase":
            return {"type": "phase", "node": self.node}
        if self.type == "chunk":
            return {
                "type": "chunk",
                "line": self.line,
                "title": self.title,
                "text": self.text,
            }
        if self.type == "done":
            payload: dict[str, Any] = {
                "type": "done",
                "code": self.code,
                "message": self.message or "success",
                "monitor": self.monitor,
                "data": self.data,
            }
            if self.quality_warning:
                payload["quality_warning"] = self.quality_warning
            return payload
        if self.type == "error":
            return {
                "type": "error",
                "code": self.code,
                "message": self.message,
            }
        return {"type": self.type, **self.raw}


__all__ = ["TaskEvent"]
