"""图外渲染运行时：模板 assemble / 篇幅修订 / 门禁 / 流式产出。

从 DomainNodes mixin 拆出，避免图节点类同时承担产品渲染管线。
"""
from __future__ import annotations

import asyncio
import logging

from tools.core.domain_engine_text import line, line_cn, line_template

logger = logging.getLogger(__name__)


def _doc_han(state: dict) -> int:
    """本次原文汉字数（用来算篇幅档位与输出上限）；取不到返回 0。"""
    try:
        from tools.templates.length_budget import han_count

        return han_count(str(state.get("transcript") or ""))
    except Exception:  # noqa: BLE001 - 只影响上限估算，不影响渲染
        return 0


def _render_cap(state: dict, template: str) -> int | None:
    """长生成调用的 max_tokens 上限（按目标字数换算）。"""
    try:
        from tools.templates.length_budget import output_token_cap

        return output_token_cap(_doc_han(state), template)
    except Exception:  # noqa: BLE001
        return None


async def _render_run(render, context: str, template: str, cap: int | None):
    """调用渲染步；支持 max_tokens 就带上，老步进对象不支持则退回旧签名。"""
    if cap:
        try:
            return await render.run(context, template, max_tokens=cap)
        except TypeError:
            pass
    return await render.run(context, template)

# ── 渲染修订指令（从 produce_line 抽出，独立便于调整；函数内 format 插值）──

_COMPRESS_REVISION = (
    "【篇幅修订·压缩】当前正文汉字约 {han}，"
    "超过模板约 {bound}–{hi} 字上界。"
    "请**整体改写压缩**到约 {target}–{hi} 字（汉字合计必须≤{hi}），"
    "不是截断半句或硬砍半段："
    "每节改短句、删套话/长清单/次要枝节，"
    "只留关键结论/数字/归属；结构贴合模板点名栏目；"
    "压缩后语句须完整通顺；勿虚构、勿在正文写字数说明。"
)

_EXPAND_REVISION = (
    "【篇幅修订·扩写】当前正文汉字约 {han}，"
    "少于模板约 {lo}–{hi} 字。"
    "请在忠实原文前提下**整体扩写**："
    "补原文已有的具体事实与推进，使合计接近区间中位；"
    "语句完整通顺；勿空话注水、勿截断、勿写字数说明。"
)

_GATE_REPAIR = (
    "【强执行门禁未通过，必须修正】\n"
    "{issues}\n\n"
    "硬性要求：每条表格数据独占一行；遵守模板约 N 行；"
    "禁止残留 [占位符]；禁止空表。"
)

_OVERLONG_COMPRESS = (
    "【字数必须达标】当前正文超出**全文**约 {hi} 字上限。"
    "请**整体改写压缩**到约 {hi} 字以内："
    "每句改短，删除过程铺陈/套话/展开论证/次要细节，"
    "只留关键结论/数字/责任人/时限；"
    "压缩后语句完整通顺；勿虚构；勿在正文写字数说明。"
)

_OVERLONG_SECTION = (
    "【段落字数必须达标】只压缩超限的那一节，"
    "不要用某一段的上限去压其它节或表格。"
    "压缩后语句完整通顺；勿虚构；勿在正文写字数说明。"
)

_KEEP_COMPRESSING = (
    "【字数仍超限，继续压缩】"
    "上一版约 {han} 字，仍超过约 {hi} 字。"
    "请进一步压缩到约 {hi} 字：合并同类句、"
    "去掉可省修饰，只保留结论/数字/责任人/时限。"
)


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
    try:
        from tools.runtime.progress import progress

        progress("render start line=%s", line_name)
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
            return
        if engine._pre_render_hook(state, line_name):
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": line(state, line_name).get("rendered") or "",
                }
            )
            return

        policy = engine._line_policy(line_name)
        if not policy.uses_llm_render(bool(template)):
            context = engine._render_context(state, line_name)
            render_draft = getattr(render, "render_draft", None)
            materialize = getattr(render, "materialize", None)
            if callable(render_draft):
                full_text = render_draft(state)
            elif materialize is not None:
                full_text = await materialize(context, template)
            elif policy.llm_render == "never" and hasattr(render, "run"):
                full_text = await render.run(context, template)
            else:
                draft = line(state, line_name).get("draft") or {}
                full_text = (
                    f"# {draft.get('title') or line_cn(line_name, engine._line_cn_names)}"
                )
            if full_text:
                try:
                    from tools.meeting_memory.render import apply_memory_citations

                    citation_context = (
                        line(state, line_name).get("memory_context") or context
                    )
                    full_text = apply_memory_citations(full_text, citation_context)
                except Exception:  # noqa: BLE001
                    logger.warning("memory citation failed line=%s", line_name, exc_info=True)
            line_state = line(state, line_name)
            line_state["rendered"] = full_text
            line_state["fill_mode"] = "draft"
            await queue.put(
                {
                    "type": "chunk",
                    "line": line_name,
                    "title": title,
                    "text": full_text,
                }
            )
            engine._post_render_hook(state, line_name)
            return

        from tools.execution.hard_execution import gate_render_output
        from tools.template_router import (
            detect_template_kind,
            fill_placeholder_template,
            is_router_enabled,
        )

        context = engine._render_context(state, line_name)
        full_text = ""
        fill_mode = "none"
        gate_ok: bool | None = None
        gate_issues: list[str] = []
        enforce_notes: list[str] = []
        streamed = False
        kind = detect_template_kind(template) if template else ""
        cap = _render_cap(state, template) if template else None

        if template and is_router_enabled() and kind == "placeholder":
            client = getattr(render, "client", None)
            if client is not None:
                try:
                    filled = await fill_placeholder_template(
                        client, context, template, source_han=_doc_han(state)
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "assemble failed (%s)", line_name, exc_info=True
                    )
                    filled = None
                if filled:
                    full_text = filled
                    fill_mode = "assemble"

        if fill_mode == "none":
            use_block = bool(
                template
                and hasattr(render, "run")
                and kind in {"placeholder", "spec"}
            )
            if use_block:
                full_text = await _render_run(render, context, template, cap)
                fill_mode = "freeform"
            else:
                parts: list[str] = []
                async for chunk in render.stream(context, template):
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

        if (
            template
            and full_text
            and is_router_enabled()
            and fill_mode in {"freeform", "repair"}
            and hasattr(render, "run")
        ):
            try:
                from tools.template_router import _body_han_count
                from tools.templates.length_budget import effective_doc_budget
            except Exception:  # noqa: BLE001
                effective_doc_budget = None  # type: ignore[assignment]
                _body_han_count = None  # type: ignore[assignment]
            span = (
                effective_doc_budget(_doc_han(state), template)
                if effective_doc_budget
                else None
            )
            if span and _body_han_count:
                lo_i, hi_i = int(span[0]), int(span[1])
                if hi_i:
                    for _rev in range(2):
                        han = _body_han_count(full_text)
                        if han > hi_i:
                            target = (
                                (lo_i + hi_i) // 2
                                if lo_i
                                else max(hi_i - 40, hi_i * 4 // 5)
                            )
                            try:
                                compressed = await _render_run(
                                    render,
                                    f"{context}\n\n"
                                    f"{_COMPRESS_REVISION.format(han=han, bound=lo_i or hi_i, hi=hi_i, target=target)}\n\n"
                                    f"【当前正文】\n{full_text}",
                                    template,
                                    cap,
                                )
                            except Exception:  # noqa: BLE001
                                compressed = ""
                            if compressed and compressed.strip():
                                full_text = compressed
                                fill_mode = "repair"
                                logger.info(
                                    "freeform too long (%s>%s), compress rev#%s (%s)",
                                    han,
                                    hi_i,
                                    _rev + 1,
                                    line_name,
                                )
                                continue
                        elif lo_i and han < int(lo_i * 0.85):
                            try:
                                expanded = await _render_run(
                                    render,
                                    f"{context}\n\n"
                                    f"{_EXPAND_REVISION.format(han=han, lo=lo_i, hi=hi_i)}\n\n"
                                    f"【当前正文】\n{full_text}",
                                    template,
                                    cap,
                                )
                            except Exception:  # noqa: BLE001
                                expanded = ""
                            if expanded and expanded.strip():
                                full_text = expanded
                                fill_mode = "repair"
                                logger.info(
                                    "freeform too short (%s<%s), expand rev#%s (%s)",
                                    han,
                                    lo_i,
                                    _rev + 1,
                                    line_name,
                                )
                                continue
                        break

        # 装配路径的下限兑现（2026-09-19 实测：一批 55 次运行全是 fill_mode=assemble，
        # "低于下限" 6 次全部静默通过——上面的篇幅分支只对 freeform/repair 生效，
        # 装配稿薄不薄没人管）。这里补**一轮**扩写：只在明显偏薄（低于下限 15%）时触发，
        # 扩写稿更长且无硬伤才采用，不收敛就保留原稿（一次调用，不追加轮次）。
        if (
            template
            and full_text
            and fill_mode == "assemble"
            and is_router_enabled()
            and hasattr(render, "run")
        ):
            try:
                from tools.template_router import _body_han_count
                from tools.templates.length_budget import effective_doc_budget
            except Exception:  # noqa: BLE001
                effective_doc_budget = None  # type: ignore[assignment]
                _body_han_count = None  # type: ignore[assignment]
            span = (
                effective_doc_budget(_doc_han(state), template)
                if effective_doc_budget
                else None
            )
            if span and _body_han_count:
                lo_i, hi_i = int(span[0]), int(span[1])
                han = _body_han_count(full_text)
                if lo_i and han < int(lo_i * 0.85):
                    try:
                        expanded = await _render_run(
                            render,
                            f"{context}\n\n"
                            f"{_EXPAND_REVISION.format(han=han, lo=lo_i, hi=hi_i)}\n\n"
                            f"【当前正文】\n{full_text}",
                            template,
                            cap,
                        )
                    except Exception:  # noqa: BLE001
                        expanded = ""
                    if expanded and expanded.strip():
                        gate_x = gate_render_output(template, expanded)
                        hard_x = list(gate_x.get("hard_issues") or [])
                        if not hard_x and _body_han_count(gate_x["text"]) > han:
                            full_text = gate_x["text"]
                            enforce_notes = list(gate_x.get("notes") or [])
                            gate_issues = list(gate_x.get("issues") or [])
                            gate_ok = bool(gate_x.get("gate_ok"))
                            fill_mode = "repair"
                            logger.info(
                                "assemble too short (%s<%s), expand once (%s)",
                                han,
                                lo_i,
                                line_name,
                            )

        if template and full_text and is_router_enabled():
            gate = gate_render_output(template, full_text)
            full_text = gate["text"]
            enforce_notes = list(gate.get("notes") or [])
            gate_issues = list(gate.get("issues") or [])
            gate_ok = bool(gate.get("gate_ok"))
            hard0 = list(gate.get("hard_issues") or [])
            advisory = list(gate.get("advisory_issues") or [])
            # 篇幅咨询：模板没声明全文预算时用档位（原文规模）比一次，只记录不返工——
            # 治"太薄/太炸"的第一道是 prompt 里的【篇幅预算】与 max_tokens 上限，不是整篇重渲染。
            try:
                from tools.templates.length_budget import effective_doc_budget

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
                elif lo2 and han_now < int(lo2 * 0.85):
                    advisory.append(
                        f"正文约 {han_now} 字，低于本篇参考下限 {lo2} 字（档位）"
                    )
            if advisory:
                # 咨询级：只记录（不触发返工）——超长条/段、缺失说明句，观察一批再收紧
                line(state, line_name)["render_advisory_issues"] = advisory
                logger.info("advisory line=%s：%s", line_name, "；".join(advisory))

            # 段落级字数超出已由 enforce_render_output 按句界确定性拆分（零额外调用）；
            # 只剩这类问题时不再触发整篇返工——篇幅属形态问题，整篇重渲染代价与收益不成比例
            # （2026-09 实测：为字数返工要多花 30–60s）。
            repair_issues = [x for x in gate_issues if "超出段落字数上限" not in x]
            if (repair_issues or not gate_ok) and hasattr(render, "run"):
                logger.warning(
                    "template gate failed (%s), try repair: %s",
                    line_name,
                    "；".join(repair_issues),
                )
                issues_text = "\n".join(f"- {x}" for x in repair_issues)
                repair_context = (
                    f"{context}\n\n"
                    f"{_GATE_REPAIR.format(issues=issues_text)}"
                )
                # 字数超限（_overlong_issue 触发）时追加强压缩指令，
                # 与「篇幅修订·压缩」同强度，避免 LLM 把 issue 当轻提示
                compress_hi = None
                over_issue = next(
                    (x for x in gate_issues if "超出字数上限" in x), None
                )
                if over_issue:
                    try:
                        from tools.templates.template_eval import parse_document_char_budget
                    except Exception:  # pragma: no cover
                        parse_document_char_budget = None  # type: ignore[assignment]
                    budget = (
                        parse_document_char_budget(template or "")
                        if parse_document_char_budget
                        else {}
                    )
                    compress_hi = budget.get("hi")
                    if compress_hi:
                        repair_context += f"\n\n{_OVERLONG_COMPRESS.format(hi=compress_hi)}"
                    elif "段落字数上限" in over_issue:
                        repair_context += f"\n\n{_OVERLONG_SECTION}"

                # repair：字数超限时最多两轮压缩，仍超限则句子级截断兜底
                def _han_count(s: str) -> int:
                    return sum(1 for c in s if "\u4e00" <= c <= "\u9fff")

                for _round in range(2 if compress_hi else 1):
                    try:
                        repaired = await _render_run(
                            render, repair_context, template, cap
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "repair failed (%s)", line_name, exc_info=True
                        )
                        repaired = ""
                    if not (repaired and repaired.strip()):
                        break
                    gate2 = gate_render_output(template, repaired)
                    hard2 = list(gate2.get("hard_issues") or [])
                    if not (gate2["gate_ok"] or len(hard2) < len(hard0)):
                        break
                    full_text = gate2["text"]
                    enforce_notes = list(gate2.get("notes") or [])
                    gate_issues = list(gate2.get("issues") or [])
                    gate_ok = bool(gate2.get("gate_ok"))
                    fill_mode = "repair"
                    hard0 = hard2
                    still_over = compress_hi and any(
                        "超出字数上限" in x for x in gate_issues
                    )
                    if not still_over or _round + 1 >= 2:
                        break
                    han_now = _han_count(full_text)
                    repair_context = (
                        f"{context}\n\n"
                        f"{_KEEP_COMPRESSING.format(han=han_now, hi=compress_hi)}\n\n"
                        f"【上一版正文】\n{full_text}"
                    )
                # 两轮压缩后仍超限：句子级截断兜底（保完整句，宁少勿多）
                if (
                    compress_hi
                    and full_text
                    and _han_count(full_text) > int(compress_hi) * 1.05
                ):
                    try:
                        from tools.execution.hard_execution import truncate_to_budget
                    except Exception:  # pragma: no cover
                        truncate_to_budget = None  # type: ignore[assignment]
                    if truncate_to_budget:
                        truncated = truncate_to_budget(
                            full_text, int(compress_hi)
                        )
                        if truncated and truncated != full_text:
                            full_text = truncated
                            gate2 = gate_render_output(template, full_text)
                            gate_issues = list(gate2.get("issues") or [])
                            hard0 = list(gate2.get("hard_issues") or [])
                            gate_ok = bool(gate2.get("gate_ok"))
                            fill_mode = "repair"

            if (
                not gate_ok
                and kind == "placeholder"
                and fill_mode != "assemble"
                and getattr(render, "client", None) is not None
            ):
                try:
                    filled2 = await fill_placeholder_template(
                        render.client, context, template, source_han=_doc_han(state)
                    )
                except Exception:  # noqa: BLE001
                    filled2 = None
                if filled2:
                    gate3 = gate_render_output(template, filled2)
                    hard3 = list(gate3.get("hard_issues") or [])
                    if gate3["gate_ok"] or len(hard3) < len(hard0):
                        full_text = gate3["text"]
                        enforce_notes = list(gate3.get("notes") or [])
                        gate_issues = list(gate3.get("issues") or [])
                        gate_ok = bool(gate3.get("gate_ok"))
                        fill_mode = "assemble"

        if full_text and line_name in {"minutes", "minutes_styles"}:
            try:
                from tools.meeting_memory.render import apply_memory_citations

                citation_context = (
                    line(state, line_name).get("memory_context") or context
                )
                # 程序算好的历史对照（gen 节点写进草稿的 history_comparison）：
                # 模型被要求"历史不写进正文"，词面锚点在跨场复述下命中率很低
                # （实测 15 条只挂 2 条且都在泛词上），对照小节是零锚点时的可见溯源。
                comparison = (
                    line(state, line_name).get("draft") or {}
                ).get("history_comparison") or []
                full_text = apply_memory_citations(
                    full_text, citation_context, comparison=comparison
                )
            except Exception:  # noqa: BLE001
                logger.warning("memory citation failed line=%s", line_name, exc_info=True)
        if full_text and not template and line_name in {"minutes", "minutes_trace"}:
            from domain.meeting.tasks.minutes.steps.minutes_render import (
                compact_untemplated_minutes,
            )

            full_text = compact_untemplated_minutes(full_text)

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
        logger.info("render line=%s fill_mode=%s gate=%s", line_name, fill_mode, gate_s)
        if enforce_notes:
            logger.info("enforce line=%s notes=%s", line_name, ";".join(enforce_notes))
        if gate_ok is False:
            logger.warning(
                "gate failed line=%s not writing result.md: %s",
                line_name,
                ";".join(gate_issues[:5]),
            )
        progress("render done line=%s", line_name)
        engine._post_render_hook(state, line_name)
    except Exception:  # noqa: BLE001 - 单线渲染失败不拖垮整条流水线
        logger.warning(
            "render failed, fallback to deterministic line=%s",
            line_name,
            exc_info=True,
        )
        line(state, line_name)["degraded"] = True
        fb_text, fb_structure = engine._domain_fallback_text(
            state, line_name, engine._fallback_rules[line_name]
        )
        line(state, line_name)["rendered"] = fb_text
        if fb_structure is not None:
            line(state, line_name)["structure"] = fb_structure
        await queue.put(
            {
                "type": "chunk",
                "line": line_name,
                "title": title,
                "text": fb_text,
            }
        )
    finally:
        await queue.put(None)


__all__ = ["produce_line"]
