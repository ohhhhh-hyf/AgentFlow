"""领域无关的多 Agent 编排引擎（meeting / notes 共享内核）。

背景
----
meeting 与 notes 两个域的 orchestrator 曾经是同一内核的复制（约 80% 行重复），
并已发生多处行为漂移（supervisor 审核键名、revision 节点、路由判断、图异常兜底、
降级检查、produce 特判）。本模块把共享内核抽到一处，两域 orchestrator 只保留：

- 生成区（由 tools/scripts/sync_domain.py 管理，勿手改）
- 领域专属 core 节点（会议理解 / 笔记理解）
- 少量钩子覆写（见 ``DomainNodes`` 的"领域钩子"注释）

模块提供：

- 纯函数在 ``domain_engine_text``（本模块再导出，领域别名 import 不变）
- ``DomainNodes`` mixin：同构图节点、流式生产者、图构建与 ``run_streaming``

设计约定
--------
- sync_domain.py 生成的代码引用模块级名字（``_line`` / ``_json`` / ``_fallback_text``
  等）。领域 orchestrator 通过别名 import 保持这些名字可用，
  生成区内容不变，``sync_domain.py --check`` 依然通过。
- 领域类继承 ``DomainNodes`` 后通过覆写钩子定制领域行为；引擎方法一律经
  ``self.xxx`` 读取领域数据（``_task_lines`` / ``_line_cn_names`` / ``_state_class``
  / ``_quality_warning`` / ``_fallback_rules`` / ``_report_assemblers`` /
  ``_fallback_nodes``），这些实例属性由领域 __init__ 设置。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable

from langgraph.graph import END, START, StateGraph

from perspective import EMPTY_PERSPECTIVE_MODELING
from tools.domain_engine_text import (
    assemble_report,
    fallback_text,
    field_values,
    format_graph_node,
    format_risk_item,
    json_dumps,
    line,
    line_cn,
    line_draft_title,
    line_has_structure,
    line_template,
    make_fallback_text,
    normalize_templates,
    normalize_transcript,
    pick_label,
    sec_attr,
)
from tools.validation import validate_payload

logger = logging.getLogger(__name__)

# 纯函数见 domain_engine_text；此处再导出以保持 from tools.domain_engine import ...

# ── DomainNodes：图节点 mixin（领域无关内核）──────────────────

class DomainNodes:
    """LangGraph 图节点 mixin（领域无关内核）。

    领域类继承本类，并确保：
    - 实例属性（领域 __init__ 设置）：``_task_lines`` / ``_line_cn_names`` /
      ``_state_class`` / ``_quality_warning``（后三者之外的 ``_fallback_rules`` /
      ``_report_assemblers`` / ``_fallback_nodes`` 由 sync_domain 生成区写入）
    - 可选覆写钩子：``_compute_title`` / ``_line_title`` / ``_shared_context`` /
      ``_supervisor_context`` / ``_build_core`` / ``_pre_render_hook`` /
      ``_post_render_hook`` / ``_empty_purpose``
    """

    MAX_REVISIONS = 1

    # 领域钩子：默认值（领域按需覆写为类属性）
    _fallback_formatters: dict[str, object] = {}
    _quality_disclaimer = "（生成可能有误）"

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _mode_label(state: dict) -> str:
        return "objective" if state.get("objective_perspective") else "personal"

    @staticmethod
    def _revision_context(context: str, feedback: list[str], label: str) -> str:
        if not feedback:
            return context
        return f"{context}\n\nSupervisor {label}：\n{json_dumps(feedback)}"

    # ── 领域钩子：默认实现（领域按需覆写）──────────────────────

    def _compute_title(self, state: dict) -> str:
        """视角标题（通用规则：客观 → 客观输出；个人 → 姓名视角输出）。"""
        if bool(state.get("objective_perspective")):
            return "客观输出"
        user = state.get("user") or {}
        return f"{user.get('name', '用户')}视角输出"

    def _line_title(self, state: dict, line_name: str) -> str:
        """线 → 展示标题（通用默认；领域可覆写加线名特判）。"""
        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = user.get("name") or "用户"
        return f"{line_cn(line_name, self._line_cn_names)}输出"

    def _shared_context(self, state: dict) -> str:
        """agent 共享上下文（视角模式 + 画像 + 视角模型 + 原文）。

        领域专属上下文（如核心理解结果）在此追加。
        """
        mode = self._mode_label(state)
        return (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
            f"用户画像：\n{json_dumps(state['user'])}\n\n"
            f"用户视角模型：\n{json_dumps(state.get('perspective_profile'))}\n\n"
            f"原文：\n{state['transcript']}"
        )

    def _supervisor_context(self, state: dict, line_name: str) -> str:
        cfg = self._task_lines[line_name]
        sub = line(state, line_name)
        revision_count = sub.get("revision_count", 0)
        mode = self._mode_label(state)
        cn = line_cn(line_name, self._line_cn_names)
        allowed = (
            "本轮可以选择 approve、revise 或 reject。"
            if revision_count < self.MAX_REVISIONS
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"视角模式：{mode}\n"
            f"{cn}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{json_dumps(state['user'])}\n\n"
            f"用户视角模型：\n{json_dumps(state.get('perspective_profile'))}\n\n"
            f"{line_draft_title(line_name, self._line_cn_names)}：\n"
            f"{json_dumps(sub['draft'])}"
        )

    def _empty_purpose(self, state: dict) -> str:
        """empty_purpose 兜底时的「目的」文案（领域有核心理解时覆写）。"""
        return ""

    def _domain_fallback_text(self, state: dict, line_name: str, rules):
        """领域降级文本拼装：绑定领域 formatters / empty_purpose / disclaimer。"""
        return fallback_text(
            state,
            line_name,
            rules,
            self._fallback_formatters,
            self._empty_purpose,
            self._quality_disclaimer,
        )

    def _build_core(self, builder) -> list[str]:
        """构建 core 层节点，返回 core 节点名列表（任务线汇合点）。

        默认只有 perspective 公共组件；领域可追加自己的 core 节点：
        ``builder.add_node("xxx", self._xxx_node)`` / ``builder.add_edge(START, "xxx")``
        """
        builder.add_node("perspective_modeling", self._perspective_modeling_node)
        builder.add_edge(START, "perspective_modeling")
        return ["perspective_modeling"]

    def _pre_render_hook(self, state: dict, line_name: str) -> bool:
        """render 前钩子：返回 True 表示已自行产出 rendered（跳过 render 调用）。"""
        return False

    def _post_render_hook(self, state: dict, line_name: str) -> None:
        """render 后钩子：默认从草稿提取结构化列表（Report 有 structure 字段时）。

        提取规则（与各线 draft 形态约定一致）：
        - ``draft[线名]`` 存在且为 list → 直接用
        - 否则草稿中恰好只有一个 list → 用它；多个/零个 → 空列表
        """
        if not line_has_structure(self._report_assemblers[line_name]):
            return
        draft = line(state, line_name).get("draft") or {}
        structure = draft.get(line_name)
        if structure is None:
            lists = [value for value in draft.values() if isinstance(value, list)]
            structure = lists[0] if len(lists) == 1 else []
        line(state, line_name)["structure"] = structure

    # ── 共享节点：视角建模（perspective 公共组件）──────────────

    async def _perspective_modeling_node(self, state: dict) -> dict:
        """把用户画像映射到本次输入（所有领域共用）。"""
        try:
            result = await self.perspective_modeling_agent.run(
                state["transcript"],
                json_dumps(state["user"]),
            )
        except Exception as exc:  # noqa: BLE001 - 有意的降级设计
            logger.warning("视角建模失败，使用空视角继续", exc_info=True)
            return {
                "perspective_profile": EMPTY_PERSPECTIVE_MODELING,
                "quality_degraded": True,
            }
        return {"perspective_profile": result.model_dump()}

    # ── 同构节点工厂（由 TASK_LINES 注册表生成）───────────────

    def _make_agent_node(self, line_name: str):
        """生成某任务线的「生成/提取」节点（agent → 草稿）。"""
        cfg = self._task_lines[line_name]
        cn = line_cn(line_name, self._line_cn_names)

        async def node(state: dict) -> dict:
            agent = getattr(self, cfg["agent_attr"])
            # 每线可选参数：组织模式 / 附加上下文（state["line_modes"] / ["line_extra"]）
            context = self._shared_context(state)
            mode = (state.get("line_modes") or {}).get(line_name)
            if mode:
                context = f"组织模式：{mode}\n\n{context}"
            extra = (state.get("line_extra") or {}).get(line_name)
            if extra:
                context = f"{context}\n\n{extra}"
            try:
                result = await agent.run(
                    self._revision_context(
                        context,
                        line(state, line_name).get("revision_feedback", []),
                        f"{cn}返工意见",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 有意的降级设计
                logger.warning(f"{cn}生成失败，使用空草稿继续", exc_info=True)
                return {
                    "lines": {
                        line_name: {
                            "draft": cfg["empty_draft"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            # 显式写 degraded=False：返工成功后清除此前失败标记
            return {
                "lines": {
                    line_name: {
                        "draft": result.model_dump(),
                        "degraded": False,
                    }
                }
            }

        return node

    def _make_supervisor_node(self, line_name: str):
        """生成某任务线的「审核」节点（supervisor → review，键统一为 ``review``）。

        ``revision_feedback`` 不再由 supervisor 写入：返工节点会从 review
        取 feedback 显式传给 agent，避免两域键名/写入时机漂移。
        """
        cfg = self._task_lines[line_name]
        cn = line_cn(line_name, self._line_cn_names)

        async def node(state: dict) -> dict:
            supervisor = getattr(self, cfg["supervisor_attr"])
            try:
                review = await supervisor.review(
                    self._supervisor_context(state, line_name)
                )
            except Exception as exc:  # noqa: BLE001 - 有意的降级设计
                logger.warning(
                    f"{cn}审核失败，按 reject 转降级", exc_info=True
                )
                return {
                    "lines": {
                        line_name: {
                            "review": cfg["reject_review"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
            return {
                "lines": {
                    line_name: {
                        "review": review.model_dump(),
                        "degraded": False,
                    }
                }
            }

        return node

    def _make_revision_node(self, line_name: str, agent_node):
        """生成某任务线的「返工」节点（revise → 带反馈重跑 agent）。

        显式从 review 取 feedback 构造 patched_state 传给 agent，
        并把 feedback / revision_count 持久化回 state。
        """
        async def node(state: dict) -> dict:
            review = line(state, line_name).get("review") or {}
            feedback = review.get("feedback", []) or []
            sub = line(state, line_name)
            revision_count = sub.get("revision_count", 0) + 1
            patched_state = dict(state)
            patched_lines = dict(state.get("lines") or {})
            patched_line = dict(patched_lines.get(line_name) or {})
            patched_line["revision_feedback"] = feedback
            patched_lines[line_name] = patched_line
            patched_state["lines"] = patched_lines
            updates = await agent_node(patched_state)
            line_patch = updates.setdefault("lines", {}).setdefault(line_name, {})
            line_patch["revision_feedback"] = feedback
            line_patch["revision_count"] = revision_count
            return updates

        return node

    def _make_route(self, line_name: str):
        """生成某任务线的条件路由（approve→结束 / reject或超限→fallback / 否则返工）。

        渲染节点已移除：approve 后文本渲染由 run_streaming 的 ``_produce``
        接管，路由返回哨兵 ``"__end__"`` 映射到 END。
        """

        def route(state: dict) -> str:
            decision = line(state, line_name)["review"]["decision"]
            if decision == "approve":
                return "__end__"
            if decision == "reject" or line(state, line_name).get(
                "revision_count", 0
            ) >= self.MAX_REVISIONS:
                return f"{line_name}_fallback"
            return f"{line_name}_revision"

        return route

    # ── 流式生产者 ────────────────────────────────────────────

    async def _produce(
        self,
        line_name: str,
        state: dict,
        queue: asyncio.Queue,
    ) -> None:
        """通用流式生产者：把指定任务线的文本流式塞进队列（并行事件源）。

        线 → 事件映射（注册表驱动）：
        - chunk 事件统一携带 ``line``（线名）与 ``title``（展示标题）
        - render 实例按命名约定取 ``self.{line_name}_render``
        - 上下文方法按命名约定取 ``self._{line_name}_render_context``
        - render.stream 签名统一 ``(context, template="")``
        - 降级线：直接整段交付 fallback 节点写的确定性文本
        - 渲染异常：降级为该线的确定性兜底文本，不中断其他线（问题 #4）
        """
        render = getattr(self, f"{line_name}_render")
        title = self._line_title(state, line_name)
        degraded = bool(line(state, line_name).get("degraded"))
        template = line_template(state, line_name)
        try:
            if degraded:
                # 降级：确定性兜底文本一次性整段交付
                await queue.put(
                    {
                        "type": "chunk",
                        "line": line_name,
                        "title": title,
                        "text": line(state, line_name).get("rendered") or "",
                    }
                )
                return
            if self._pre_render_hook(state, line_name):
                # 领域已自行产出 rendered（跳过 render 调用）
                await queue.put(
                    {
                        "type": "chunk",
                        "line": line_name,
                        "title": title,
                        "text": line(state, line_name).get("rendered") or "",
                    }
                )
                return
            # 强执行渲染管线：
            # 1) placeholder 只走 assemble（失败才 freeform 兜底）
            # 2) 程序硬约束（粘连修复/行数截断/空表）
            # 3) 验收门禁：硬伤则 repair；仍失败则 gate_ok=False（不落通过 md）
            import sys

            from tools.hard_execution import gate_render_output
            from tools.template_router import (
                detect_template_kind,
                fill_placeholder_template,
                is_router_enabled,
            )

            context_fn = getattr(self, f"_{line_name}_render_context")
            context = context_fn(state)
            full_text = ""
            fill_mode = "none"
            gate_ok: bool | None = None
            gate_issues: list[str] = []
            enforce_notes: list[str] = []
            streamed = False
            kind = detect_template_kind(template) if template else ""

            # ── 1) 有占位符模板：强制优先 assemble ──
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

            # ── 2) assemble 失败：有模板用整段 freeform；无模板才 stream ──
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

            # ── 3) 篇幅软修订（freeform/repair 路径；assemble 内部已自检）──
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
                                        f"{context}\n\n【篇幅修订·压缩】当前正文汉字约 {han}，"
                                        f"超过模板约 {lo_i or hi_i}–{hi_i} 字上界。"
                                        f"请**整体改写压缩**到约 {target}–{hi_i} 字（汉字合计必须≤{hi_i}），"
                                        "不是截断半句或硬砍半段："
                                        "每节改短句、删套话/长清单/次要枝节，"
                                        "只留关键结论/数字/归属；结构贴合模板点名栏目；"
                                        "压缩后语句须完整通顺；勿虚构、勿在正文写字数说明。\n\n"
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
                                        f"{context}\n\n【篇幅修订·扩写】当前正文汉字约 {han}，"
                                        f"少于模板约 {lo_i}–{hi_i} 字。"
                                        "请在忠实原文前提下**整体扩写**："
                                        "补原文已有的具体事实与推进，使合计接近区间中位；"
                                        "语句完整通顺；勿空话注水、勿截断、勿写字数说明。\n\n"
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

            # ── 4) 强执行 + 门禁（仅有模板时）──
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
                    repair_context = (
                        f"{context}\n\n【强执行门禁未通过，必须修正】\n"
                        + "\n".join(f"- {x}" for x in gate_issues)
                        + "\n\n硬性要求：每条表格数据独占一行；遵守模板约 N 行；"
                        "禁止残留 [占位符]；禁止空表。"
                    )
                    try:
                        repaired = await render.run(repair_context, template)
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "repair 失败（%s）", line_name, exc_info=True
                        )
                        repaired = ""
                    if repaired and repaired.strip():
                        gate2 = gate_render_output(template, repaired)
                        hard2 = list(gate2.get("hard_issues") or [])
                        if gate2["gate_ok"] or len(hard2) < len(hard0):
                            full_text = gate2["text"]
                            enforce_notes = list(gate2.get("notes") or [])
                            gate_issues = list(gate2.get("issues") or [])
                            gate_ok = bool(gate2.get("gate_ok"))
                            fill_mode = "repair"
                            hard0 = hard2

                # freeform 仍硬伤：再强攻 assemble
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

            # 未 stream 过的路径：整段推送最终正文
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

            cn = line_cn(line_name, self._line_cn_names)
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
            self._post_render_hook(state, line_name)
        except Exception as exc:  # noqa: BLE001 - 单线渲染失败不拖垮整条流水线
            logger.warning(
                "%s渲染失败，使用确定性兜底文本",
                line_cn(line_name, self._line_cn_names),
                exc_info=True,
            )
            line(state, line_name)["degraded"] = True
            fb_text, fb_structure = self._domain_fallback_text(
                state, line_name, self._fallback_rules[line_name]
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

    # ── 图异常 / 校验失败兜底 ─────────────────────────────────

    def _fallback_reports(
        self, state: dict, line_names: list[str]
    ) -> dict:
        """图异常/校验失败时的确定性 Report（按线声明式拼装，零线级特判）。"""
        lines = state.setdefault("lines", {})
        for line_name in line_names:
            rules = self._fallback_rules[line_name]
            text, structure = self._domain_fallback_text(state, line_name, rules)
            line_dict = lines.setdefault(line_name, {})
            line_dict["rendered"] = text
            if structure is not None:
                line_dict["structure"] = structure
        return {
            line_name: assemble_report(
                state,
                self._quality_warning,
                self._report_assemblers[line_name],
                line_name,
                self._compute_title,
            )
            for line_name in line_names
        }

    # ── 图构建与流式运行 ──────────────────────────────────────

    def _normalize_lines(
        self, lines: Iterable[str] | None
    ) -> list[str]:
        """规范化 lines 参数：None → 全部任务线；校验未知/空值。"""
        if lines is None:
            return list(self._task_lines)
        result = list(lines)
        unknown = [name for name in result if name not in self._task_lines]
        if unknown:
            raise ValueError(
                f"未知任务线 {unknown}，可用：{list(self._task_lines)}"
            )
        if not result:
            raise ValueError("lines 不能为空，至少指定一条任务线")
        return result

    def _build_graph(
        self, line_names: Iterable[str] | None = None
    ) -> object:
        """构建 LangGraph：core（领域核心理解 + 视角建模）+ 指定任务线。

        ``line_names`` 为 None 时构建全部任务线；否则只构建选中的线
        （core 始终构建——任何任务线都需要 core）。
        """
        line_names = self._normalize_lines(line_names)
        builder = StateGraph(self._state_class)

        # 核心层：领域钩子（默认 perspective 公共组件；领域可追加）
        core = self._build_core(builder)

        # 任务线：由注册表生成同构节点（agent / supervisor / revision / route）
        for line_name in line_names:
            agent_node = self._make_agent_node(line_name)
            supervisor_node = self._make_supervisor_node(line_name)
            revision_node = self._make_revision_node(line_name, agent_node)
            route = self._make_route(line_name)

            builder.add_node(f"{line_name}_agent", agent_node)
            builder.add_node(f"{line_name}_supervisor", supervisor_node)
            builder.add_node(f"{line_name}_revision", revision_node)
            builder.add_node(
                f"{line_name}_fallback", self._fallback_nodes[line_name]
            )

            # 核心层汇合 → 本线 agent → supervisor → 条件路由
            builder.add_edge(core, f"{line_name}_agent")
            builder.add_edge(f"{line_name}_agent", f"{line_name}_supervisor")
            builder.add_conditional_edges(
                f"{line_name}_supervisor",
                route,
                {
                    "__end__": END,
                    f"{line_name}_revision": f"{line_name}_revision",
                    f"{line_name}_fallback": f"{line_name}_fallback",
                },
            )
            builder.add_edge(f"{line_name}_revision", f"{line_name}_supervisor")
            builder.add_edge(f"{line_name}_fallback", END)

        return builder.compile()

    async def run_streaming(
        self,
        transcript: str,
        user=None,
        template: str = "",
        item_template: str = "",
        templates: dict[str, str] | None = None,
        lines: Iterable[str] | None = None,
        line_modes: dict[str, str] | None = None,
        line_extra: dict[str, str] | None = None,
    ) -> AsyncIterator[dict]:
        """流式输出：各任务线文本并行逐块推送，按线携带展示标题。

        ``lines`` 指定要执行的任务线（默认全部）：只传部分线名时，
        未选中的线不构建节点、不调用 LLM，也不会产出对应事件。

        事件协议（async generator，按产出顺序 yield dict）：

        - ``{"type": "chunk", "line": str, "title": str, "text": str}``
          某条线的文本流式块（line = 线名；title = 展示标题）；逐块追加即为完整输出
        - ``{"type": "done", "quality_warning": str | None, "reports": dict}``
          结束标记；quality_warning 非空表示输出降级，需提示核对；
          reports = {线名: Report}，流式消费后可从此取最终结构化结果
        """
        if not transcript.strip():
            raise ValueError("输入文本不能为空")

        # 前置阶段：归一化 → 图执行（分析 + 各线审核 + 返工）
        transcript = normalize_transcript(transcript)
        template = template or ""
        item_template = item_template or ""
        if user is None:
            user_data: dict = {}
            objective_mode = False
        else:
            user_data = (
                user.model_dump() if hasattr(user, "model_dump") else dict(user)
            )
            objective_mode = (
                str(user_data.get("perspective") or "").strip().lower()
                == "objective"
            )
        if objective_mode and not user_data.get("perspective"):
            user_data["perspective"] = "objective"
        # lines 校验（提前到模板分发前，供按线分派使用；非法线名直接抛给调用方）
        line_names = self._normalize_lines(lines)
        # 模板按线统一收纳（须在 initial_state 前）：templates 优先，便捷参数兜底
        templates = normalize_templates(
            template,
            item_template,
            templates,
            line_names,
            self._report_assemblers,
        )

        initial_state: dict = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "templates": templates,
            "line_modes": dict(line_modes or {}),
            "line_extra": dict(line_extra or {}),
        }
        # 图执行失败时 state 不会被赋值；先绑定 initial_state，
        # 保证兜底分支引用 state 不抛 NameError（最后防线自身不崩溃）
        state = initial_state
        try:
            graph = self._build_graph(line_names)
            state = await graph.ainvoke(initial_state)
        except Exception as exc:  # noqa: BLE001 - 最后防线：图内异常不崩溃，走确定性兜底
            logger.warning("图执行失败，使用确定性兜底输出", exc_info=True)
            fb = self._fallback_reports(initial_state, line_names)
            for line_name in line_names:
                if line_name in fb:
                    yield {
                        "type": "chunk",
                        "line": line_name,
                        "title": self._line_title(initial_state, line_name),
                        "text": line(initial_state, line_name).get("rendered")
                        or "",
                    }
            yield {
                "type": "done",
                "quality_warning": self._quality_warning,
                "reports": fb,
                "understanding": state.get("meeting_understanding")
                or state.get("notes_understanding")
                or {},
            }
            return

        # 并行启动各线事件源，通过队列合并：一条线流式生成期间其他线已可交付
        queue: asyncio.Queue = asyncio.Queue()
        producers = [
            asyncio.create_task(self._produce(line_name, state, queue))
            for line_name in line_names
        ]
        remaining = len(producers)
        try:
            while remaining:
                event = await queue.get()
                if event is None:
                    remaining -= 1
                    continue
                if isinstance(event, Exception):  # 防御：producer 异常不应冒泡中断
                    logger.warning("流式事件异常：%s", event)
                    continue
                yield event
        finally:
            # 取消未完成的 producer task，避免事件循环关闭时悬挂任务与线程（问题 #4）
            for task in producers:
                task.cancel()
            await asyncio.gather(*producers, return_exceptions=True)

        # 任意线降级（含渲染失败降级）→ 全局质量警告
        any_line_degraded = any(
            bool(line(state, name).get("degraded")) for name in self._task_lines
        )
        quality_warning = (
            self._quality_warning
            if (any_line_degraded or bool(state.get("quality_degraded")))
            else None
        )
        gate_by_line = {
            name: line(state, name).get("render_gate_ok")
            for name in line_names
        }
        yield {
            "type": "done",
            "quality_warning": quality_warning,
            "reports": self._final_reports(state, line_names, quality_warning),
            "gate_by_line": gate_by_line,
            "understanding": state.get("meeting_understanding")
            or state.get("notes_understanding")
            or {},
        }

    def _final_reports(
        self,
        state: dict,
        line_names: list[str],
        warning: str | None,
    ) -> dict:
        """图执行成功后按线组装最终 Report（单线校验失败只降级该线）。

        reports 键 = 线名（与 chunk 事件的 ``line`` 一致），消费端按线名取。
        逐线校验：某条线 Report 校验失败时仅该线退回确定性兜底，
        不再连累其它正常线的结果（旧实现一条线失败全部线一起降级）。
        """
        reports: dict = {}
        for line_name in line_names:
            report_cls = self._report_assemblers[line_name]
            reports[line_name] = assemble_report(
                state, warning, report_cls, line_name, self._compute_title
            )
        final: dict = {}
        for key, report in reports.items():
            try:
                final[key] = validate_payload(
                    type(report), report.model_dump()
                )
            except Exception:  # noqa: BLE001 - 单线校验失败，仅该线退回确定性兜底
                logger.warning(
                    "输出校验失败（%s），该线退回确定性兜底",
                    key,
                    exc_info=True,
                )
                final[key] = self._fallback_reports(state, [key])[key]
        return final


__all__ = [
    "DomainNodes",
    "assemble_report",
    "fallback_text",
    "field_values",
    "format_graph_node",
    "format_risk_item",
    "json_dumps",
    "line",
    "line_cn",
    "line_draft_title",
    "line_has_structure",
    "line_template",
    "make_fallback_text",
    "normalize_templates",
    "normalize_transcript",
    "pick_label",
    "sec_attr",
]
