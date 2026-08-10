"""perspective —— 跨 domain 公共的视角建模组件。

任何 domain 的 domain_core 可直接引用：

    from perspective import PerspectiveModelingAgent, PerspectiveModeling
    from perspective import EMPTY_PERSPECTIVE_MODELING

模型由 perspective/gen_models.py 从 contracts.py 生成（复用 codegen
生成逻辑），不参与任何 domain 的 codegen 扫描——单一事实来源，
各 domain 直接 import 本包即可，无需复制。
"""
from .agent import PerspectiveModelingAgent
from .contracts import PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT
from .models import EMPTY_PERSPECTIVE_MODELING, PerspectiveModeling
from .prompts import PERSPECTIVE_MODELING_SYSTEM_PROMPT

__all__ = [
    "PerspectiveModelingAgent",
    "PerspectiveModeling",
    "EMPTY_PERSPECTIVE_MODELING",
    "PERSPECTIVE_MODELING_GENERATION_OUTPUT_CONTRACT",
    "PERSPECTIVE_MODELING_SYSTEM_PROMPT",
]
