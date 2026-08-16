"""library 任务组 prompt（入库与对照不依赖模型措辞）。"""
from __future__ import annotations

from tools.template_prompt import build_template_render_prompt

LIBRARY_GENERATION_SYSTEM_PROMPT = """把用户指定的多份文件写入知识库，并统计独立增量与跨文件冲突。不要编造出处。"""

LIBRARY_SUPERVISOR_DOMAIN_PROMPT = """入库失败才 revise。冲突必须来自两份真实文件的原文对照。"""

LIBRARY_RENDER_PROMPT = """按知识增量、冲突点两段输出，不要写解析页数。"""

LIBRARY_RENDER_TEMPLATE_PROMPT = build_template_render_prompt(
    renderer="资料入库报告",
    source="已批准的入库对照结果",
    empty_rule="没有增量也没有冲突时如实说明。",
)
