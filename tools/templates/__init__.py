"""模板子系统：渲染 prompt（``template_prompt``）/ 约束评测（``template_eval``）/
篇幅预算（``length_budget``）/ 正文格式规则（``body_rules``）/ 路由层（``router/``）。

模板注册表（``template_v2`` / ``template_v3`` 目录）仍在仓库顶层：
生效目录由 ``AGENTFLOW_TEMPLATE_DIR`` 决定，``app/config.py::template_dir()`` 读取。
"""
