"""library —— 资料入库任务线的协议 prompt 常量。

library 是**程序化任务线**：多文件入库、OCR 合并、知识增量统计全部为
确定性程序流程，不经过任何 LLM 生成调用。本文件的四个常量是任务线
完备性协议（tools/scripts/sync_domain.py readiness 检查按名称存在性
判定）的一部分，运行时不进入 LLM 调用。
"""

LIBRARY_GENERATION_SYSTEM_PROMPT = """「资料入库 Agent」为程序化流程：多文件写入指定知识库并统计知识增量。
入库、OCR 合并、增量计数均为确定性程序逻辑，不使用 LLM 生成。"""

LIBRARY_SUPERVISOR_DOMAIN_PROMPT = """## 领域审核规则：资料入库

library 为程序化任务线，draft 即入库统计结果，审核仅做完整性核对：
- files/items 数值一致；
- 失败时有失败原因。
默认 approve。"""

LIBRARY_RENDER_PROMPT = """把入库统计结果渲染为 Markdown 报告：导入图片/文档数、知识单元增量与来源文件。"""

LIBRARY_RENDER_TEMPLATE_PROMPT = """按模板输出入库报告，只替换占位。"""


__all__ = [
    "LIBRARY_GENERATION_SYSTEM_PROMPT",
    "LIBRARY_SUPERVISOR_DOMAIN_PROMPT",
    "LIBRARY_RENDER_PROMPT",
    "LIBRARY_RENDER_TEMPLATE_PROMPT",
]
