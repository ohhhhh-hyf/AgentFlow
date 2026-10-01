"""{{DOMAIN}} —— {{CN_NAME}}领域。

基于 register_domain.py 生成的干净骨架：
- 视角建模（perspective 公共组件）已内置：orchestrator 自动挂载节点、
  {{DOMAIN}}_factory 组装 PerspectiveModelingAgent、state 含
  perspective_profile 字段——新领域无需重复实现
- 核心层在 {{DOMAIN}}_core/ 下编写（可选，如"{{CN_NAME}}理解"）
- 任务线通过 register_task.py --domain {{DOMAIN}} --task xxx --name "中文名" 添加
- 编排/生成区由 sync_domain.py --domain {{DOMAIN}} 管理
"""
from pathlib import Path

from .models import UserIdentity, {{STATE_CLASS}}
from .orchestrator import {{PASCAL}}AgentSystem
from .{{DOMAIN}}_factory import {{PASCAL}}AgentFactory

# 领域自包含的样例资源根目录（输入 / 画像 / 模板）
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

__all__ = [
    "{{PASCAL}}AgentFactory",
    "{{PASCAL}}AgentSystem",
    "SAMPLES_DIR",
    "UserIdentity",
    "{{STATE_CLASS}}",
]
