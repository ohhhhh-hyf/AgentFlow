"""{{DOMAIN}} 编排层：LangGraph 图 + 节点 + 流式输出（{{CN_NAME}} 域）。

手写区 = 领域钩子覆写 + 领域专属节点（可选）；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
节点映射 / 渲染上下文 / 各类 import / Report 组装器 / FallbackRules /
专属节点骨架。

共享编排内核位于 tools/domain_engine.py（DomainNodes mixin + 纯函数），
本文件只保留领域差异。领域可按需覆写引擎钩子：
- _compute_title / _line_title：视角标题与展示标题
- _shared_context / _supervisor_context：agent / supervisor 上下文（可含核心理解）
- _build_core：core 节点（默认仅 perspective 公共组件）
- _pre_render_hook / _post_render_hook：render 前后特判
- _empty_purpose / _LINES_FORMATTERS：降级文本绑定

新增任务线流程：register_task.py --domain {{DOMAIN}} --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain {{DOMAIN}} 全量生成 → --check 校验。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable

from langgraph.graph import START

from llm_client import LLMClient
from perspective import PerspectiveModelingAgent
from .domain_config import LINE_CN_NAMES
from .models import (
    {{STATE_CLASS}},
    UserIdentity,
    is_objective_perspective,
)
from .{{DOMAIN}}_factory import {{PASCAL}}AgentFactory

# 共享编排内核（领域无关）：纯函数 + DomainNodes 图节点 mixin
from tools.domain_engine import (
    DomainNodes,
    json_dumps as _json,
    line as _line,
    line_cn as _engine_line_cn,
    line_draft_title as _engine_line_draft_title,
    line_template as _line_template,
    make_fallback_text,
)

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

# 生成区骨架引用的模块级 _fallback_text（3 参版本，绑定领域 formatters）
_fallback_text = make_fallback_text(
    _LINES_FORMATTERS, _empty_purpose, QUALITY_DISCLAIMER
)

class _Nodes(DomainNodes):
    """{{CN_NAME}} 图节点实现：共享内核（tools/domain_engine.DomainNodes）+ 领域专属。

    同构节点（agent / supervisor / revision / route）与流式生产 / 图构建 /
    运行由引擎提供。领域按需覆写引擎钩子（见模块 docstring），
    领域专属 core 节点在此追加。
    """

    # 领域钩子：降级文本绑定（引擎 _domain_fallback_text 读取）
    _fallback_formatters = _LINES_FORMATTERS
    _quality_disclaimer = QUALITY_DISCLAIMER

    # 领域专属 core 节点在此追加（可选）：
    # async def _xxx_node(self, state) -> dict: ...
    # 并在 _build_core 中挂载（默认仅 perspective 公共组件）

    # ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

    # ── 渲染上下文生成区结束 ──

    # ── 专属节点方法生成区：由 tools/scripts/sync_domain.py 生成骨架，函数体可改 ──

    # ── 专属节点方法生成区结束 ──

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

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        # ── 节点映射生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── 节点映射生成区结束 ──

        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        # ── FallbackRules 注册生成区结束 ──

        # 共享编排内核所需实例属性（引擎通过 self 读取；值来自领域注册表）
        self._task_lines = TASK_LINES
        self._line_cn_names = LINE_CN_NAMES
        self._state_class = {{STATE_CLASS}}
        self._quality_warning = QUALITY_WARNING
