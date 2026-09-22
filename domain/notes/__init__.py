"""notes —— 笔记领域。

基于 register_domain.py 生成的干净骨架：
- 视角建模（perspective 公共组件）已内置：orchestrator 自动挂载节点、
  notes_factory 组装 PerspectiveModelingAgent、state 含
  perspective_profile 字段——新领域无需重复实现
- 核心层在 notes_core/ 下编写（可选，如"笔记理解"）
- 任务线通过 register_task.py --domain notes --task xxx --name "中文名" 添加
- 编排/生成区由 sync_domain.py --domain notes 管理
"""
from pathlib import Path

from .models import UserIdentity, NotesState
from .orchestrator import NotesAgentSystem
from .notes_factory import NotesAgentFactory

# 领域自包含的样例资源根目录（输入 / 画像 / 模板）
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

__all__ = [
    "NotesAgentFactory",
    "NotesAgentSystem",
    "SAMPLES_DIR",
    "UserIdentity",
    "NotesState",
]


# ── 域钩子自注册（2026-09-22）：引擎层不 import 具体域，只问 hooks_for("<domain>") ──
# 放在包 __init__ 末尾：load_domain 先 import 域包 ⇒ 注册一定早于引擎的任何调用。
from .hooks import HOOKS as NotesHooks  # noqa: E402
from tools.core.domain_hooks import register as _register_hooks  # noqa: E402

_register_hooks("notes", NotesHooks)
