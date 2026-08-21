"""领域无关的多 Agent 编排引擎（meeting / notes 共享内核）。

背景
----
meeting 与 notes 两个域的 orchestrator 曾经是同一内核的复制（约 80% 行重复），
并已发生多处行为漂移（supervisor 审核键名、revision 节点、路由判断、图异常兜底、
降级检查、produce 特判）。本模块把共享内核抽到一处，两域 orchestrator 只保留：

- 生成区（模型 / TASK_LINES / 工厂挂载 / Report 组装器；不再生成 render/fallback 方法）
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
  / ``_quality_warning`` / ``_fallback_rules`` / ``_report_assemblers``），
  这些实例属性由领域 __init__ 设置。
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
      ``_report_assemblers`` 由 sync_domain 生成区写入）
    - 可选覆写钩子：``_compute_title`` / ``_line_title`` / ``_shared_context`` /
      ``_supervisor_context`` / ``_build_core`` / ``_pre_render_hook`` /
      ``_post_render_hook`` / ``_empty_purpose`` /
      ``_understanding_key`` / ``_understanding_label`` / ``_transcript_label``
    """

    MAX_REVISIONS = 1

    # 领域钩子：默认值（领域按需覆写为类属性）
    _fallback_formatters: dict[str, object] = {}
    _quality_disclaimer = "（生成可能有误）"
    _understanding_key = ""
    _understanding_label = "已审核理解"
    _transcript_label = "原文"

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _mode_label(state: dict) -> str:
        if state.get("objective_perspective"):
            return "objective"
        user = state.get("user") or {}
        if str(user.get("persona_type") or "").strip().lower() == "role_template":
            return "role_template"
        return "personal"

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
            f"说明：objective=客观全员；role_template=职业模板（name 是职业名，不是会场真人）；"
            f"personal=真人个人（name 是真实姓名）。"
            f"裁剪时同时遵守画像 focus_areas / interests / principles / constraints / output_style。"
            f"职业/真人对决策、风险、未决从上游下采（只删不改），关注域内的数字、时限、承诺、口径、范围边界不得省略。\n\n"
            f"用户画像：\n{json_dumps(state['user'])}\n\n"
            f"用户视角模型：\n{json_dumps(state.get('perspective_profile'))}\n\n"
            f"原文：\n{state['transcript']}"
        )

    def _supervisor_source_pack(self, state: dict, line_name: str) -> str:
        """审核用原文：按草稿事实点摘录，短文仍给全文。"""
        from tools.runtime.supervisor_slice import (
            collect_needles,
            compact_perspective,
            compact_profile,
            slice_transcript,
            summarize_understanding,
        )

        sub = line(state, line_name)
        draft = sub.get("draft") or {}
        understanding = self._understanding(state)
        needles = collect_needles(draft) + collect_needles(understanding)
        raw = state.get("transcript") or ""
        excerpt, hits, used = slice_transcript(raw, needles)
        if not excerpt.strip():
            excerpt = raw.strip()
            used = len(raw)
        is_full = used >= len(raw)
        if is_full:
            source_note = "原文（最高事实来源）："
            excerpt = raw
        else:
            source_note = (
                "以下原文按草稿事实点摘录，仍是最高事实来源。"
                f"已覆盖草稿中 {hits} 处可定位表述。"
                "摘录未覆盖处不得凭空补全；不足以核对某条时 revise 并指出缺哪句。"
            )
        parts = [f"{source_note}\n{excerpt}"]
        summary = summarize_understanding(understanding)
        if summary:
            parts.append(f"{self._understanding_label}（摘要）：\n{summary}")
        profile = compact_profile(state.get("user") or {})
        if profile:
            parts.append(f"用户画像：\n{profile}")
        perspective = compact_perspective(state.get("perspective_profile"))
        if perspective:
            parts.append(f"用户视角模型：\n{perspective}")
        return "\n\n".join(parts)

    def _supervisor_context(self, state: dict, line_name: str) -> str:
        from tools.runtime.supervisor_slice import compact_draft_for_review

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
            f"{self._supervisor_source_pack(state, line_name)}\n\n"
            f"{line_draft_title(line_name, self._line_cn_names)}：\n"
            f"{json_dumps(compact_draft_for_review(sub['draft']))}"
        )

    def _empty_purpose(self, state: dict) -> str:
        """empty_purpose 兜底时的「目的」文案（领域有核心理解时覆写）。"""
        return ""

    def _understanding(self, state: dict) -> dict:
        """读取本领域核心理解；key 由 ``_understanding_key`` 声明。"""
        from tools.runtime.context import understanding_of

        return understanding_of(state, self._understanding_key)

    def _render_context_blocks(
        self, state: dict
    ) -> list[tuple[str, object, str]]:
        """渲染上下文里「已批准草稿」之前的块。领域只改三个钩子即可。"""
        blocks: list[tuple[str, object, str]] = [
            (self._transcript_label, state.get("transcript") or "", "raw"),
            ("用户画像", state.get("user") or {}, "json"),
        ]
        if self._understanding_key:
            blocks.append(
                (
                    self._understanding_label,
                    state.get(self._understanding_key),
                    "json",
                )
            )
        if state.get("perspective_profile"):
            blocks.append(
                ("已审核用户视角", state.get("perspective_profile"), "json")
            )
        return blocks

    def _render_context(self, state: dict, line_name: str) -> str:
        """运行时拼装渲染上下文；不再生成 ``_{line}_render_context``。"""
        from tools.runtime.context import build_render_context

        sub = line(state, line_name)
        extra = (state.get("line_extra") or {}).get(line_name) or ""
        return build_render_context(
            mode=self._mode_label(state),
            objective=bool(state.get("objective_perspective")),
            blocks=self._render_context_blocks(state),
            draft=sub.get("draft"),
            review=sub.get("review") or {},
            line_cn=line_cn(line_name, self._line_cn_names),
            extra=extra,
        )

    def _make_fallback_node(self, line_name: str):
        """生成某任务线的降级节点（与历史生成区函数体同构）。"""

        async def node(state: dict) -> dict:
            text, structure = self._domain_fallback_text(
                state, line_name, self._fallback_rules[line_name]
            )
            line_dict = {"rendered": text, "degraded": True}
            if structure is not None:
                line_dict["structure"] = structure
            return {
                "lines": {line_name: line_dict},
                "quality_degraded": True,
            }

        return node

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

    def _build_core(self, builder, line_names: list[str] | None = None) -> list[str]:
        """构建 core 层节点，返回 core 节点名列表（任务线汇合点）。

        默认只有 perspective 公共组件；领域可追加自己的 core 节点：
        ``builder.add_node("xxx", self._xxx_node)`` / ``builder.add_edge(START, "xxx")``
        """
        del line_names
        builder.add_node("perspective_modeling", self._perspective_modeling_node)
        builder.add_edge(START, "perspective_modeling")
        return ["perspective_modeling"]

    def _line_policy(self, line_name: str):
        """读本线种类策略；未声明时按 llm_document 兜底（测试桩可用）。"""
        from tools.runtime.kinds import LLM_DOCUMENT, policy_for

        policies = getattr(self, "_line_policies", None) or {}
        if line_name in policies:
            return policies[line_name]
        return policy_for(LLM_DOCUMENT)

    def _pre_render_hook(self, state: dict, line_name: str) -> bool:
        """render 前钩子：返回 True 表示已自行产出 rendered（跳过 render 调用）。"""
        return False

    def _post_render_hook(self, state: dict, line_name: str) -> None:
        """按种类抽结构：pipeline 不抽；extract 抽列表；document 仅当 Report 声明 structure。"""
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE

        policy = self._line_policy(line_name)
        if policy.kind == DETERMINISTIC_PIPELINE:
            return
        render = getattr(self, f"{line_name}_render", None)
        extractor = getattr(render, "extract_structure", None) or getattr(
            render, "extract_actions", None
        )
        if extractor:
            line(state, line_name)["structure"] = extractor(state)
            return
        report_cls = (getattr(self, "_report_assemblers", None) or {}).get(line_name)
        if not policy.extracts_structure and not (
            report_cls and line_has_structure(report_cls)
        ):
            return
        draft = line(state, line_name).get("draft") or {}
        structure = draft.get(line_name)
        if structure is None:
            lists = [value for value in draft.values() if isinstance(value, list)]
            structure = lists[0] if len(lists) == 1 else []
        line(state, line_name)["structure"] = structure

    # ── 共享节点：占位入口 + 视角建模（perspective 公共组件）──────

    async def _noop_core_node(self, state: dict) -> dict:
        """core 层空时的占位入口节点。

        当某次运行的全部任务线都被领域按线跳过 core（如 notes 的
        library/catalog/checklist 不跑视角建模与笔记理解）时，
        图仍需一个从 START 出发的入口，直接透传 state。
        """
        return {}

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
            if mode and self._line_policy(line_name).cli_mode:
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
        """委托给 ``tools.runtime.render``：图外渲染不属于节点 mixin。"""
        try:
            from tools.runtime.render import produce_line

            await produce_line(self, line_name, state, queue)
        except Exception as exc:  # 防御：producer 异常必须可见，否则主循环静默等待永不结束
            logger.error(
                "任务线 %s 渲染异常：%s", line_name, exc, exc_info=True
            )
            queue.put_nowait(exc)
            queue.put_nowait(None)  # 该线终止，避免 run_streaming 永久等待

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
        core = self._build_core(builder, line_names)

        # 任务线：由注册表生成同构节点（agent / supervisor / revision / route）
        for line_name in line_names:
            agent_node = self._make_agent_node(line_name)
            supervisor_node = self._make_supervisor_node(line_name)
            revision_node = self._make_revision_node(line_name, agent_node)
            route = self._make_route(line_name)

            builder.add_node(f"{line_name}_agent", agent_node)
            builder.add_node(f"{line_name}_supervisor", supervisor_node)
            builder.add_node(f"{line_name}_revision", revision_node)
            custom = getattr(self, "_fallback_nodes", None) or {}
            fallback = custom.get(line_name) or self._make_fallback_node(
                line_name
            )
            builder.add_node(f"{line_name}_fallback", fallback)

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
                "gate_by_line": {},
                "pipeline": self._pipeline_by_line(state, line_names),
                "understanding": self._understanding(state),
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
            "pipeline": self._pipeline_by_line(state, line_names),
            "understanding": state.get("meeting_understanding")
            or state.get("notes_understanding")
            or {},
        }

    def _pipeline_by_line(self, state: dict, line_names: list[str]) -> dict:
        """各线审核结论 / 返工次数 / 是否降级，供任务监控采集。"""
        out: dict[str, dict] = {}
        for name in line_names:
            sub = line(state, name) or {}
            review = sub.get("review") or {}
            if not isinstance(review, dict):
                review = {}
            decision = str(review.get("decision") or "").strip()
            degraded = bool(sub.get("degraded"))
            try:
                revisions = int(sub.get("revision_count") or 0)
            except (TypeError, ValueError):
                revisions = 0
            out[name] = {
                "decision": decision,
                "revision_count": revisions,
                "degraded": degraded,
                "fallback": degraded or decision == "reject",
            }
        return out

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
