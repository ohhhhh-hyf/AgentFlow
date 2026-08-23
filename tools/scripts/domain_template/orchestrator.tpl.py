"""{{DOMAIN}} 编排层：LangGraph 图 + 节点 + 流式输出（{{CN_NAME}} 域）。

手写区 = 领域钩子覆写 + 领域专属节点（可选）；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
各类 import / Report 组装器 / FallbackRules。
render / fallback 由 DomainNodes 运行时一份函数生成，不再按线出样板。

共享编排内核位于 tools/domain_engine.py，渲染在 tools.runtime.render。
本文件只保留领域差异。领域可按需覆写引擎钩子：
- _compute_title / _line_title：视角标题与展示标题
- _shared_context / _supervisor_context：agent / supervisor 上下文（可含核心理解）
- _build_core：core 节点（默认仅 perspective 公共组件）
- _pre_render_hook / _post_render_hook：render 前后特判
- _empty_purpose / _LINES_FORMATTERS：降级文本绑定
- _understanding_key / _understanding_label / _transcript_label：渲染上下文

新增任务线流程：register_task.py --domain {{DOMAIN}} --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain {{DOMAIN}} 全量生成 → --check 校验。
"""
from __future__ import annotations

import logging

from langgraph.graph import START

from client import LLMClient
from perspective import PerspectiveModelingAgent
from .domain_config import LINE_CN_NAMES, LINE_KINDS
from .models import {{STATE_CLASS}}
from .{{DOMAIN}}_factory import {{PASCAL}}AgentFactory

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.domain_engine import (
    DomainNodes,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
)
from tools.runtime.kinds import resolve_line_policies

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── Report import 生成区结束 ──

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── FallbackRules import 生成区结束 ──

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {}

# ── 任务线注册生成区结束 ──

def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return _engine_line_cn(line_name, LINE_CN_NAMES)

def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return _engine_line_draft_title(line_name, LINE_CN_NAMES)

# Lines 段逐条格式化器注册表（domain 按需填写）
# 例：lines 段需要逐条格式化时注册 {线名: 格式化函数(index, item) -> str}
_LINES_FORMATTERS: dict[str, object] = {}

def _empty_purpose(state) -> str:
    """empty_purpose 兜底时的「目的」文案（领域有核心理解时覆写）。"""
    return ""

class _Nodes(DomainNodes):
    """{{CN_NAME}} 图节点实现：共享内核 + 领域专属钩子。"""

    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER
    _understanding_key = ""
    _understanding_label = "已审核理解"
    _transcript_label = "原文"
    _line_cn_names = LINE_CN_NAMES
    _line_policies = resolve_line_policies(LINE_KINDS)

    # 领域专属 core 节点在此追加（可选）：
    # async def _xxx_node(self, state) -> dict: ...
    # 并在 _build_core 中挂载（默认仅 perspective 公共组件）

class {{PASCAL}}AgentSystem(_Nodes):
    """使用 LangGraph 编排核心层、任务线审核返工与最终输出。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

        # 通过工厂组装全部 Agent 依赖（键名 = 属性名，与 TASK_LINES 的 *_attr 对齐）
        agents = {{PASCAL}}AgentFactory.create(self.client)

        # core 层挂载（perspective 公共组件；领域核心 Agent 在此追加）
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling_agent"
        ]

        # ── Agent 挂载生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── Agent 挂载生成区结束 ──

        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = {{STATE_CLASS}}
        self._quality_warning = QUALITY_WARNING

