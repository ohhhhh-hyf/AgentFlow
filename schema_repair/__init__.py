"""SchemaRepair —— 通用 JSON 输出结构修复器（与领域无关）。

在任何 Agent 的结构化输出校验失败、且重试仍不过关时，
由调用方（如 client.llmclient）调用本组件修复 JSON 结构，
只改格式、绝不改业务事实。
"""

from .schema_repair import SchemaRepairAgent

__all__ = ["SchemaRepairAgent"]
