"""tools —— 通用工具（与领域无关，供任意业务复用）。

模块地图见同目录 ``README.md``。

常用导入示例（请直接从子模块导入，本包不做顶层转发）：

- 运行：``from tools.runner import run``
- 领域加载：``from tools.runtime_context import load_domain``
- 编排：``from tools.domain_engine import DomainNodes``
- 模板：``from tools.template_router import route_template``
- 强执行：``from tools.hard_execution import gate_render_output``
"""
