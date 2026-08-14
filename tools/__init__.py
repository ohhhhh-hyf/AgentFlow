"""tools —— 按层拆开的运行时与工具。

分层见同目录 ``README.md``。旧导入路径保持可用：

- 应用：``from tools.runner import run`` 或 ``from tools.app import run``
- 编排：``from tools.domain_engine import DomainNodes``
- 渲染：``from tools.runtime.render import produce_line``
- 模板：``from tools.template_router import route_template``
"""
