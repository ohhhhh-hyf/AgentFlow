"""每个业务 Agent 的 System Prompt 和输出契约。

每个文件只包含两个常量：SYSTEM_PROMPT 和 OUTPUT_CONTRACT。
Agent 类从这里导入，做到 prompt 与逻辑分离，方便：
- 版本对比（git diff 只看 prompt 变更）
- 非开发人员审核 prompt
- 后续替换为远程配置或文件加载
"""

from . import (  # noqa: F401 — 保持干净的导入入口
    action_items,
    final_renderer,
    meeting_understanding,
    minutes_generation,
    perspective_modeling,
    schema_repair,
    supervisor,
)
