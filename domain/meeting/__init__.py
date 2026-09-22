from pathlib import Path

from .meeting_factory import MeetingAgentFactory
from .models import (
    ActionItemsSupervisorReview,
    MinutesSupervisorReview,
    UserIdentity,
)
from .orchestrator import MeetingAgentSystem
from .reports import (
    ActionItemsReport,
    MinutesReport,
)

# 领域自包含的样例资源根目录（summary / profile / template）
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

__all__ = [
    "ActionItemsSupervisorReview",
    "ActionItemsReport",
    "MeetingAgentFactory",
    "MeetingAgentSystem",
    "MinutesReport",
    "MinutesSupervisorReview",
    "SAMPLES_DIR",
    "UserIdentity",
]


# ── 域钩子自注册（2026-09-22）：引擎层不 import 具体域，只问 hooks_for("<domain>") ──
# 放在包 __init__ 末尾：load_domain 先 import 域包 ⇒ 注册一定早于引擎的任何调用。
from .hooks import HOOKS as MeetingHooks  # noqa: E402
from tools.core.domain_hooks import register as _register_hooks  # noqa: E402

_register_hooks("meeting", MeetingHooks)
