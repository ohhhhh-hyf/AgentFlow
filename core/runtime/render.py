"""图外渲染运行时：模板 Fast Render / 篇幅修订 / 门禁 / 流式产出。

从 DomainNodes mixin 拆出，避免图节点类同时承担产品渲染管线。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from typing import Any

try:
    from core.graph.engine_text import line, line_cn, line_template
    from core.runner.hooks import hooks_for
except ImportError:
    from core.graph.engine_text import line, line_cn, line_template
    from core.runner.hooks import hooks_for

logger = logging.getLogger(__name__)


def _doc_han(state: dict) -> int:
    """本次原文汉字数（用来算篇幅档位与输出上限）；取不到返回 0。"""
    try:
        try:
            from core.templates.length_budget import han_count
        except ImportError:
            from core.templates.length_budget import han_count

        return han_count(str(state.get("transcript") or ""))
    except Exception:  # noqa: BLE001 - 只影响上限估算，不影响渲染
        return 0


def _render_cap(state: dict, template: str) -> int | None:
    """长生成调用的 max_tokens 上限（按目标字数换算）。"""
    try:
        try:
            from core.templates.length_budget import output_token_cap
        except ImportError:
            from core.templates.length_budget import output_token_cap

        return output_token_cap(_doc_han(state), template)
    except Exception:  # noqa: BLE001
        return None


def _is_brief_style(line_name: str, state: dict, template: str) -> bool:
    """是否为 minutes_styles 的高管速览（brief）模式。

    高管速览定位核心拍板结论与重大阻断，文风高度精炼（800–1200 字即可交付完整信息），
    对长会原文不应按通用档位（如 1680 字）强制扩写返工或打出下限咨询告警。
    """
    if line_name != "minutes_styles":
        return False
    mode = str(
        (state.get("line_modes") or state.get("modes") or {}).get("minutes_styles")
        or ""
    ).strip().lower()
    if mode == "brief":
        return True
    if "高管速览" in (template or ""):
        return True
    return False


def _is_transient_error(exc: BaseException) -> bool:
    """判定是否为可局部重试的瞬时网络或服务故障（超时、连接断开、5xx 等）。"""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True

    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    # 硬性非瞬时错误直接熔断，不浪费时间重试
    non_transient = ("401", "403", "unauthorized", "forbidden", "context_length_exceeded")
    if any(k in msg for k in non_transient):
        return False

    transient_indicators = (
        "timeout",
        "timed out",
        "time out",
        "connection reset",
        "connection refused",
        "remote disconnected",
        "remotedisconnected",
        "disconnected",
        "broken pipe",
        "network",
        "econnreset",
        "econnrefused",
        "etimedout",
        "500",
        "502",
        "503",
        "504",
        "gateway timeout",
        "bad gateway",
        "service unavailable",
        "internal server error",
        "server disconnected",
        "stream disconnected",
    )
    if any(k in name for k in ("timeout", "connect", "reset")):
        return True
    return any(indicator in msg for indicator in transient_indicators)


_MAX_TOKENS_SUPPORT: dict = {}


def _accepts_max_tokens(func) -> bool:
    """``func`` 是否接受 ``max_tokens=`` 关键字（按底层函数缓存，每类只判一次）。

    缓存键用底层函数对象本身（绑定方法的 ``__func__``），避免同名方法串味。
    渲染步就这么十几个类，条数有界。
    """
    key = getattr(func, "__func__", func)
    cached = _MAX_TOKENS_SUPPORT.get(key)
    if cached is None:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            cached = False
        else:
            cached = "max_tokens" in params or any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        _MAX_TOKENS_SUPPORT[key] = cached
    return cached


_TEMPERATURE_SUPPORT: dict = {}


def _accepts_temperature(func) -> bool:
    """``func`` 是否接受 ``temperature=`` 关键字。"""
    key = getattr(func, "__func__", func)
    cached = _TEMPERATURE_SUPPORT.get(key)
    if cached is None:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            cached = False
        else:
            cached = "temperature" in params or any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        _TEMPERATURE_SUPPORT[key] = cached
    return cached


_VIEW_SUPPORT: dict = {}


def _accepts_view(func) -> bool:
    """``func`` 是否接受 ``view=`` 关键字。"""
    key = getattr(func, "__func__", func)
    cached = _VIEW_SUPPORT.get(key)
    if cached is None:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            cached = False
        else:
            cached = "view" in params or any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        _VIEW_SUPPORT[key] = cached
    return cached


_LAYOUT_SUPPORT: dict = {}


def _accepts_layout(func) -> bool:
    """``func`` 是否接受 ``layout=`` 关键字。"""
    key = getattr(func, "__func__", func)
    cached = _LAYOUT_SUPPORT.get(key)
    if cached is None:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            cached = False
        else:
            cached = "layout" in params or any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        _LAYOUT_SUPPORT[key] = cached
    return cached


_LANG_SUPPORT: dict = {}


def _accepts_lang(func) -> bool:
    """``func`` 是否接受 ``lang=`` 关键字。"""
    key = getattr(func, "__func__", func)
    cached = _LANG_SUPPORT.get(key)
    if cached is None:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            cached = False
        else:
            cached = "lang" in params or any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
        _LANG_SUPPORT[key] = cached
    return cached


def _render_view(state: dict, line_name: str) -> str | None:
    """取本线已裁决的 view；无该状态时返回 None。"""
    return (state.get("line_views") or {}).get(line_name)


def _render_layout(state: dict, line_name: str) -> str | None:
    """取本线已裁决的 layout；无该状态时返回 None。"""
    return (state.get("line_layouts") or {}).get(line_name)


async def _render_run(
    render,
    context: str,
    template: str,
    cap: int | None,
    temperature: float | None = None,
    view: str | None = None,
    layout: str | None = None,
):
    """调用渲染步；支持 ``max_tokens`` / ``temperature`` / ``view`` / ``layout`` 就带上。"""
    kwargs: dict[str, Any] = {}
    if cap and _accepts_max_tokens(render.run):
        kwargs["max_tokens"] = cap
    if temperature is not None and _accepts_temperature(render.run):
        kwargs["temperature"] = temperature
    if view and _accepts_view(render.run):
        kwargs["view"] = view
    if layout and _accepts_layout(render.run):
        kwargs["layout"] = layout
    return await render.run(context, template, **kwargs)


def _apply_memory_citations(
    engine,
    state: dict,
    line_name: str,
    full_text: str,
    fallback_context: str = "",
) -> str:
    """给渲染后的纪要加记忆引用标注与历史对照（若存在）。"""
    cite_fn = hooks_for(engine.domain_name).apply_citations
    if not full_text or cite_fn is None or line_name not in {"minutes", "minutes_styles"}:
        return full_text
    try:
        line_st = line(state, line_name)
        citation_context = (
            line_st.get("memory_context") or fallback_context or ""
        )
        # 程序算好的历史对照（gen 节点写进草稿的 history_comparison）：
        # 模型被要求"历史不写进正文"，词面锚点在跨场复述下命中率很低
        # （实测 15 条只挂 2 条且都在泛词上），对照小节是零锚点时的可见溯源。
        comparison = (
            line_st.get("draft") or {}
        ).get("history_comparison") or []
        candidate_items = line_st.get("memory_items")
        try:
            return cite_fn(
                full_text,
                citation_context,
                comparison=comparison,
                candidate_items=candidate_items,
            )
        except TypeError:
            return cite_fn(
                full_text,
                citation_context,
                comparison=comparison,
            )
    except Exception:
        logger.warning("memory citation failed line=%s", line_name, exc_info=True)
        return full_text


async def produce_line(
    engine,
    line_name: str,
    state: dict,
    queue: asyncio.Queue,
) -> None:
    """把指定任务线的文本流式塞进队列（并行事件源）。

    - chunk 事件携带 ``line`` 与 ``title``
    - render 实例按命名约定取 ``engine.{line_name}_render``
    - 上下文走 ``engine._render_context``（运行时一份，不再生成 per-line 方法）
    - 降级线整段交付 fallback 已写的确定性文本
    - 渲染异常只降级本线，不中断其他线
    """
    render = getattr(engine, f"{line_name}_render")
    title = engine._line_title(state, line_name)
    degraded = bool(line(state, line_name).get("degraded"))
    template = line_template(state, line_name)
    view = _render_view(state, line_name)
    layout = _render_layout(state, line_name)
    streamed = False
    context = ""
    try:
        try:
            from core.runner.progress import progress
        except ImportError:
            from core.runtime.progress import progress

        _render_t0 = time.time()
        progress("[render:start] line=%s", line_name)
        if line_name == "minutes" and layout:
            progress("[render:layout] line=minutes layout=%s", layout)
        if degraded:
            try:
                engine._post_render_hook(state, line_name)
            except Exception:
                logger.exception("attach after fallback failed line=%s", line_name)
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": line(state, line_name).get("rendered") or "",
                }
            )
            dur = time.time() - _render_t0
            progress("[render:done] line=%s dur=%.2fs", line_name, dur)
            return
        if hasattr(engine, "_pre_render_async"):
            await engine._pre_render_async(state, line_name)
        if engine._pre_render_hook(state, line_name):
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": line(state, line_name).get("rendered") or "",
                }
            )
            dur = time.time() - _render_t0
            progress("[render:done] line=%s dur=%.2fs", line_name, dur)
            return

        policy = engine._line_policy(line_name)
        if not policy.uses_llm_render(template):
            materialize = getattr(render, "materialize", None)
            render_draft = getattr(render, "render_draft", None)
            context = ""
            fill_mode = "draft"
            if materialize is not None:
                context = engine._render_context(state, line_name)
                full_text = await materialize(context, template)
                fill_mode = "materialize"
            elif callable(render_draft):
                full_text = render_draft(state)
                fill_mode = "draft"
            elif policy.llm_render == "never" and hasattr(render, "run"):
                context = engine._render_context(state, line_name)
                full_text = await _render_run(
                    render, context, template, None, view=view, layout=layout
                )
                fill_mode = "run"
            else:
                draft = line(state, line_name).get("draft") or {}
                full_text = (
                    f"# {draft.get('title') or line_cn(line_name, engine._line_cn_names)}"
                )
                fill_mode = "fallback_title"
            full_text = _apply_memory_citations(
                engine, state, line_name, full_text, fallback_context=context
            )
            compact = hooks_for(engine.domain_name).compact_plain
            if full_text and not template and compact is not None:
                full_text = compact(line_name, full_text)
            line_state = line(state, line_name)
            line_state["rendered"] = full_text
            line_state["fill_mode"] = fill_mode
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": full_text,
                }
            )
            engine._post_render_hook(state, line_name)
            dur = time.time() - _render_t0
            progress("[render:done] line=%s dur=%.2fs", line_name, dur)
            return

        try:
            from core.execution.hard_execution import gate_render_output
            from core.templates.router import (
                detect_template_kind,
                is_router_enabled,
            )
        except ImportError:
            from core.execution.hard_execution import gate_render_output
            from core.templates.router import (
                detect_template_kind,
                is_router_enabled,
            )

        context = engine._render_context(state, line_name)
        # 本栏写作纪律（领域钩子，默认空）：取舍口径（如真人聚焦）随用户消息下发
        directives = str(engine._render_directives(state, line_name) or "")
        full_text = ""
        fill_mode = "none"
        gate_ok: bool | None = None
        gate_issues: list[str] = []
        enforce_notes: list[str] = []
        streamed = False
        kind = detect_template_kind(template) if template else ""
        cap = _render_cap(state, template) if template else None

        if fill_mode == "none":
            use_block = bool(
                template
                and hasattr(render, "run")
                and not hasattr(render, "stream")
                and kind in {"placeholder", "spec"}
            )
            max_render_retries = 1
            retry_delay = 1.0

            for attempt in range(max_render_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(
                            "局部渲染重试触发 line=%s attempt=%d", line_name, attempt
                        )
                        await asyncio.sleep(retry_delay)

                    if use_block:
                        full_text = await _render_run(
                            render, context, template, cap, view=view, layout=layout
                        )
                        fill_mode = "freeform"
                    else:
                        parts: list[str] = []
                        stream_kwargs: dict[str, Any] = {}
                        if view and _accepts_view(render.stream):
                            stream_kwargs["view"] = view
                        if layout and _accepts_layout(render.stream):
                            stream_kwargs["layout"] = layout
                        lang = state.get("lang")
                        if lang and _accepts_lang(render.stream):
                            stream_kwargs["lang"] = lang
                        async for chunk in render.stream(
                            context, template, **stream_kwargs
                        ):
                            parts.append(chunk)
                            await queue.put(
                                {
                                    "type": "chunk",
                                    "line": line_name,
                                    "title": title,
                                    "text": chunk,
                                }
                            )
                            streamed = True
                        full_text = "".join(parts)
                        fill_mode = "freeform" if template else "none"

                    if full_text and full_text.strip():
                        if attempt > 0:
                            fill_mode = "retry_success"
                        break
                except Exception as render_exc:
                    if (
                        attempt < max_render_retries
                        and not streamed
                        and _is_transient_error(render_exc)
                    ):
                        logger.warning(
                            "render attempt %d failed (transient), will retry line=%s err=%s",
                            attempt + 1,
                            line_name,
                            render_exc,
                        )
                        continue
                    raise

        is_brief = _is_brief_style(line_name, state, template)
        if template and full_text and is_router_enabled():
            gate = gate_render_output(template, full_text)
            full_text = gate["text"]
            enforce_notes = list(gate.get("notes") or [])
            gate_issues = list(gate.get("issues") or [])
            gate_ok = bool(gate.get("gate_ok"))
            advisory = list(gate.get("advisory_issues") or [])
            # 篇幅咨询：模板没声明全文预算时用档位（原文规模）比一次，纯旁路监控只记录不返工——
            # 治"太薄/太炸"的第一道是 prompt 里的【篇幅预算】与 max_tokens 上限，不再调用 LLM 二次压缩重写。
            try:
                try:
                    from core.templates.length_budget import effective_doc_budget
                except ImportError:
                    from core.templates.length_budget import effective_doc_budget

                span2 = effective_doc_budget(_doc_han(state), template)
            except Exception:  # noqa: BLE001
                span2 = None
            if span2:
                han_now = sum(1 for c in full_text if "\u4e00" <= c <= "\u9fff")
                lo2, hi2 = int(span2[0]), int(span2[1])
                if hi2 and han_now > int(hi2 * 1.2):
                    advisory.append(
                        f"正文约 {han_now} 字，超过本篇参考上限 {hi2} 字（档位）"
                    )
                elif lo2 and han_now < int(lo2 * 0.75) and not is_brief:
                    advisory.append(
                        f"正文约 {han_now} 字，低于本篇参考下限 {lo2} 字（档位）"
                    )
            if advisory:
                # 咨询级：只记录（不触发返工）——供日志与质量大盘监控
                line(state, line_name)["render_advisory_issues"] = advisory
                logger.info("advisory line=%s：%s", line_name, "；".join(advisory))


        full_text = _apply_memory_citations(
            engine, state, line_name, full_text, fallback_context=context
        )
        # 无模板正文的收尾压缩：哪条线要压由域钩子决定（引擎不再点名线名）
        compact = hooks_for(engine.domain_name).compact_plain
        if full_text and not template and compact is not None:
            full_text = compact(line_name, full_text)

        if not streamed and full_text is not None:
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": full_text,
                }
            )

        line_state = line(state, line_name)
        line_state["rendered"] = full_text
        line_state["fill_mode"] = fill_mode
        line_state["render_gate_ok"] = gate_ok
        line_state["render_gate_issues"] = gate_issues
        if enforce_notes:
            line_state["enforce_notes"] = enforce_notes
        if template and gate_ok is False:
            line_state["quality_warning"] = (
                "模板强执行门禁未通过：" + "；".join(gate_issues[:5])
            )
            state["quality_degraded"] = True
        # 审核调用失败（保守放行）：正文照常交付，但把"未做质量把关"记进本线质量信号
        unavailable = str(line_state.get("review_unavailable") or "").strip()
        if unavailable:
            note = f"审核服务调用失败（未做质量把关）：{unavailable}"
            line_state["quality_warning"] = (
                f"{line_state['quality_warning']}；{note}"
                if line_state.get("quality_warning")
                else note
            )

        gate_s = (
            "n/a"
            if gate_ok is None
            else ("pass" if gate_ok else "fail")
        )
        template_id = str(state.get("template_id") or "")
        template_source = str(state.get("template_source") or "")
        template_mode = str(state.get("template_mode") or "")
        if line_name == "minutes":
            logger.info(
                "render line=%s template_id=%s template_source=%s "
                "template_mode=%s fill_mode=%s gate=%s directives=%d",
                line_name,
                template_id,
                template_source,
                template_mode,
                fill_mode,
                gate_s,
                len(directives),
            )
        else:
            logger.info(
                "render line=%s fill_mode=%s gate=%s directives=%d",
                line_name,
                fill_mode,
                gate_s,
                len(directives),
            )
        if enforce_notes:
            logger.info("enforce line=%s notes=%s", line_name, ";".join(enforce_notes))
        if gate_ok is False:
            logger.warning(
                "gate failed line=%s not writing result.md: %s",
                line_name,
                ";".join(gate_issues[:5]),
            )
        dur = time.time() - _render_t0
        progress("[render:done] line=%s dur=%.2fs", line_name, dur)
        engine._post_render_hook(state, line_name)
    except Exception as exc:  # noqa: BLE001 - 单线渲染失败不拖垮整条流水线
        logger.warning(
            "render failed, fallback to deterministic line=%s: %s",
            line_name,
            exc,
            exc_info=True,
        )
        line_state = line(state, line_name)
        line_state["degraded"] = True
        line_state["quality_warning"] = "（服务瞬时繁忙，已启用高保真结构化呈现）"
        state["quality_degraded"] = True

        draft = line_state.get("draft") or {}
        render_draft_fn = getattr(render, "render_draft", None)
        fb_text = ""
        fb_structure = None

        # 1. 优先调用本任务线专属的高保真纯代码渲染器
        if callable(render_draft_fn) and draft:
            try:
                fb_text = render_draft_fn(state)
                line_state["fill_mode"] = "deterministic_draft"
            except Exception:
                logger.exception("render_draft failed line=%s", line_name)
                fb_text = ""

        # 2. 次级文本草稿直出（思维导图 outline / 溯源正文 minutes_md）
        if not fb_text and draft:
            if "outline" in draft and draft["outline"]:
                fb_text = str(draft["outline"])
                line_state["fill_mode"] = "draft_outline"
            elif "minutes_md" in draft and draft["minutes_md"]:
                fb_text = str(draft["minutes_md"])
                line_state["fill_mode"] = "draft_minutes_md"

        # 3. 历史对照/记忆引用追加（若存在）
        fb_text = _apply_memory_citations(
            engine, state, line_name, fb_text, fallback_context=context
        )

        # 4. 兜底中的兜底：沿用通用 FallbackRules 规则
        if not fb_text:
            fb_text, fb_structure = engine._domain_fallback_text(
                state, line_name, engine._fallback_rules[line_name]
            )
            line_state["fill_mode"] = "legacy_fallback"

        line_state["rendered"] = fb_text
        if fb_structure is not None:
            line_state["structure"] = fb_structure
        else:
            try:
                engine._post_render_hook(state, line_name)
            except Exception:
                logger.exception("post_render_hook after fallback failed line=%s", line_name)

        if not streamed:
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": fb_text,
                }
            )
        dur = time.time() - _render_t0
        progress("[render:done] line=%s dur=%.2fs status=degraded", line_name, dur)
    finally:
        await queue.put(None)


__all__ = ["produce_line"]
