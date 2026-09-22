"""域钩子注册表：引擎层不 import 具体域，只按域名取钩子。

背景（2026-09-22，用户拍板做"彻底反转"）：记忆注入/回写、产物 HTML 渲染、无模板正文收尾
压缩，原本由引擎直接 ``from domain.meeting... import``（11 行跨层导入散在 4 个文件：
``core/runner`` / ``runtime/render`` / ``exports/outputs`` / ``exports/html/consensus_decision``）。
这里把"引擎需要的域能力"定义成协议，域在 ``domain/<name>/hooks.py`` 声明、由
``domain/<name>/__init__.py`` 注册；引擎只问 ``hooks_for(name)``——未注册的域拿到空钩子
（等于"该域没有这项能力"），加新域不需要碰 tools/。

分工：**引擎负责"什么时候调"**（输入组装、渲染前、跑完落盘、产物收尾），
**域负责"具体怎么做"**（会议记忆的 meta 协议、notes 的归属解析、各线 HTML 样式）。
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainHooks:
    """引擎需要的域能力；每一项都可缺省（缺省＝不提供）。

    调用约定（域侧适配器必须按此签名实现，多余的域内差异由适配器吸收）：

    - ``memory_lines``：需要记忆注入/回写的线名；引擎据此判断"本次要不要准备记忆"。
    - ``prepare_memory(*, project_root, domain, user_id, transcript, line_names, project_id,
      subject, meeting_time, request_id) -> (bind, line_extra)``
      ——失败应自行吞掉并返回 ``(None, {})``。
    - ``persist_memory(*, project_root, domain, user_id, project_id, request_id, subject,
      transcript, reports, understanding, meeting_time, bind) -> Any``
      ——返回值由域自定义，引擎不解释。
    - ``inject_line_extra(state, line_name, *, line_extra=None) -> Any``
      ——引擎按属性读 ``context`` / ``bind`` / ``warning`` / ``comparison``。
    - ``apply_citations(text, context, *, comparison=None) -> str``
    - ``html_for(line_name, title, text, data) -> str | None``
      ——返回 None 表示"该线没有专属渲染器"，引擎回退通用 HTML。
    - ``compact_plain(line_name, text) -> str``
      ——无模板正文的收尾压缩；哪条线要压由域自己判断。
    """

    memory_lines: frozenset[str] = frozenset()
    prepare_memory: Callable[..., Any] | None = None
    persist_memory: Callable[..., Any] | None = None
    inject_line_extra: Callable[..., Any] | None = None
    apply_citations: Callable[..., Any] | None = None
    html_for: Callable[..., Any] | None = None
    compact_plain: Callable[..., Any] | None = None


_EMPTY = DomainHooks()
_REGISTRY: dict[str, DomainHooks] = {}


def register(domain: str, hooks: DomainHooks) -> None:
    """域包在 import 时自注册（见各 ``domain/<name>/__init__.py`` 末尾）。重复注册覆盖。"""
    name = str(domain or "").strip()
    if not name or hooks is None:
        return
    _REGISTRY[name] = hooks


def hooks_for(domain: str, *, ensure: bool = True) -> DomainHooks:
    """取域钩子。未注册且 ``ensure`` 时按需 import ``domain.<name>``（触发其自注册）。

    注意语义：``ensure`` 只在域包**尚未被 import** 时能触发自注册——Python 不会重跑已 import
    模块的 ``__init__``。生产路径由 ``load_domain()`` 先 import 域包，注册必然早于引擎调用；
    本函数的兜底只服务于"引擎先被调用"的边角场景。

    取不到一律返回**空钩子**（调用方据此跳过该能力），不抛异常——引擎不能因为
    某个域没实现钩子而挂掉；测试桩/未注册域因此天然可用。
    """
    name = str(domain or "").strip()
    if not name:
        return _EMPTY
    hooks = _REGISTRY.get(name)
    if hooks is not None:
        return hooks
    if not ensure:
        return _EMPTY
    try:
        importlib.import_module(f"domain.{name}")
    except ModuleNotFoundError:
        logger.debug("domain hooks: 未注册的域 %s（按无钩子处理）", name)
        return _EMPTY
    except Exception:  # noqa: BLE001 - 钩子缺失按"无能力"处理，不影响主流程
        logger.warning("domain hooks unavailable domain=%s", name, exc_info=True)
        return _EMPTY
    return _REGISTRY.get(name, _EMPTY)


def registered() -> dict[str, DomainHooks]:
    """已注册的域（诊断/测试用）。"""
    return dict(_REGISTRY)


def clear() -> None:
    """清空注册表（测试用）。"""
    _REGISTRY.clear()


__all__ = ["DomainHooks", "clear", "hooks_for", "register", "registered"]
