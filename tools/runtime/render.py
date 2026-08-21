"""图外渲染运行时：模板 assemble / 篇幅修订 / 门禁 / 流式产出。

从 DomainNodes mixin 拆出，避免图节点类同时承担产品渲染管线。
"""
from __future__ import annotations

import asyncio
import logging
import sys

from tools.domain_engine_text import line, line_cn, line_template

logger = logging.getLogger(__name__)

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
        if degraded:
            try:
                engine._post_render_hook(state, line_name)
            except Exception:
                logger.exception("%s 降级后挂载失败", line_name)
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
                    from tools.memory.citations import apply_memory_citations

                    full_text = apply_memory_citations(full_text, context)
                except Exception:  # noqa: BLE001
                    logger.warning("记忆引用标注失败（%s）", line_name, exc_info=True)
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

        from tools.hard_execution import gate_render_output
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

        if template and is_router_enabled() and kind == "placeholder":
            client = getattr(render, "client", None)
            if client is not None:
                try:
                    filled = await fill_placeholder_template(
                        client, context, template
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "assemble 异常（%s）", line_name, exc_info=True
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
                full_text = await render.run(context, template)
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
                from tools.template_eval import parse_document_char_budget
                from tools.template_router import _body_han_count
            except Exception:  # noqa: BLE001
                parse_document_char_budget = None  # type: ignore[assignment]
                _body_han_count = None  # type: ignore[assignment]
            if parse_document_char_budget and _body_han_count:
                bud = parse_document_char_budget(template)
                hi = bud.get("hi")
                lo = bud.get("lo")
                if hi:
                    hi_i = int(hi)
                    lo_i = int(lo or 0)
                    for _rev in range(2):
                        han = _body_han_count(full_text)
                        if han > hi_i:
                            target = (
                                (lo_i + hi_i) // 2
                                if lo_i
                                else max(hi_i - 40, hi_i * 4 // 5)
                            )
                            try:
                                compressed = await render.run(
                                    f"{context}\n\n"
                                    f"{_COMPRESS_REVISION.format(han=han, bound=lo_i or hi_i, hi=hi_i, target=target)}\n\n"
                                    f"【当前正文】\n{full_text}",
                                    template,
                                )
                            except Exception:  # noqa: BLE001
                                compressed = ""
                            if compressed and compressed.strip():
                                full_text = compressed
                                fill_mode = "repair"
                                logger.info(
                                    "freeform 偏长（%s>%s），压缩修订#%s（%s）",
                                    han,
                                    hi_i,
                                    _rev + 1,
                                    line_name,
                                )
                                continue
                        elif lo_i and han < int(lo_i * 0.85):
                            try:
                                expanded = await render.run(
                                    f"{context}\n\n"
                                    f"{_EXPAND_REVISION.format(han=han, lo=lo_i, hi=hi_i)}\n\n"
                                    f"【当前正文】\n{full_text}",
                                    template,
                                )
                            except Exception:  # noqa: BLE001
                                expanded = ""
                            if expanded and expanded.strip():
                                full_text = expanded
                                fill_mode = "repair"
                                logger.info(
                                    "freeform 偏短（%s<%s），扩写修订#%s（%s）",
                                    han,
                                    lo_i,
                                    _rev + 1,
                                    line_name,
                                )
                                continue
                        break

        if template and full_text and is_router_enabled():
            gate = gate_render_output(template, full_text)
            full_text = gate["text"]
            enforce_notes = list(gate.get("notes") or [])
            gate_issues = list(gate.get("issues") or [])
            gate_ok = bool(gate.get("gate_ok"))
            hard0 = list(gate.get("hard_issues") or [])

            if (gate_issues or not gate_ok) and hasattr(render, "run"):
                logger.warning(
                    "模板门禁未通过（%s），尝试 repair：%s",
                    line_name,
                    "；".join(gate_issues),
                )
                issues_text = "\n".join(f"- {x}" for x in gate_issues)
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
                        from tools.template_eval import parse_document_char_budget
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
                        repaired = await render.run(repair_context, template)
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "repair 失败（%s）", line_name, exc_info=True
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
                        from tools.hard_execution import truncate_to_budget
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
                        render.client, context, template
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

        if full_text and not template:
            try:
                from tools.memory.citations import apply_memory_citations

                full_text = apply_memory_citations(full_text, context)
            except Exception:  # noqa: BLE001
                logger.warning("记忆引用标注失败（%s）", line_name, exc_info=True)

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

        cn = line_cn(line_name, engine._line_cn_names)
        gate_s = (
            "n/a"
            if gate_ok is None
            else ("pass" if gate_ok else "fail")
        )
        sys.stdout.write(
            f"[模板渲染] {cn} fill_mode={fill_mode} gate={gate_s}\n"
        )
        if enforce_notes:
            sys.stdout.write(
                f"[强执行] {cn} " + "；".join(enforce_notes) + "\n"
            )
        if gate_ok is False:
            sys.stdout.write(
                f"[门禁失败] {cn} 不写入通过态 result.md："
                + "；".join(gate_issues[:5])
                + "\n"
            )
        sys.stdout.flush()
        logger.info(
            "模板渲染 %s fill_mode=%s gate=%s",
            line_name,
            fill_mode,
            gate_s,
        )
        engine._post_render_hook(state, line_name)
    except Exception:  # noqa: BLE001 - 单线渲染失败不拖垮整条流水线
        logger.warning(
            "%s渲染失败，使用确定性兜底文本",
            line_cn(line_name, engine._line_cn_names),
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
