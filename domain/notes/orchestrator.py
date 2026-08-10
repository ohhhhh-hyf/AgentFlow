"""notes 编排层：LangGraph 图 + 节点 + 流式输出（笔记 域）。

手写区 = 通用编排内核（任何 domain 同构，可按需调整）+ 领域专属节点；
生成区（由 tools/scripts/sync_domain.py 生成）：任务线注册 / Agent 挂载 /
节点映射 / 渲染上下文 / 各类 import / Report 组装器 / FallbackRules /
专属节点骨架。

新增任务线流程：register_task.py --domain notes --task xxx --name "中文名"
→ 手写 tasks/xxx/prompts.py + reports.py 追加 Report 类
→ sync_domain.py --domain notes 全量生成 → --check 校验。
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import fields

from langgraph.graph import END, START, StateGraph

from llm_client import LLMClient
from perspective import EMPTY_PERSPECTIVE_MODELING, PerspectiveModelingAgent
from .domain_config import LINE_CN_NAMES
from .models import (
    NotesState,
    UserIdentity,
    is_objective_perspective,
)
from .notes_factory import NotesAgentFactory
from .notes_core import NotesUnderstandingAgent

# ── Report import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .reports import (
    PointsReport,
)
# ── Report import 生成区结束 ──

# ── 任务线 import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.points import (
    PointsAgent,
    PointsRender,
    PointsSupervisor,
)

# ── 任务线 import 生成区结束 ──

# ── FallbackRules import 生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

from .tasks.points.contracts import POINTS_FALLBACK_RULES

# ── FallbackRules import 生成区结束 ──

from tools.validation import validate_payload

logger = logging.getLogger(__name__)

QUALITY_WARNING = "生成可能有误，请结合原文核对。"
QUALITY_DISCLAIMER = "（生成可能有误）"

# ── 空结构常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_EMPTY_NOTES_UNDERSTANDING = {
    "note_purpose": "",
    "sections": [],
    "key_terms": [],
    "open_questions": [],
}

_EMPTY_POINTS = {
    "points": [],
}

# ── 空结构常量生成区结束 ──

# ── 拒绝审核常量生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

_REJECT_POINTS_REVIEW = {
    "decision": "reject",
    "points_check": {"status": "fail", "findings": ["LLM 调用失败，未完成审核"]},
    "feedback": ["LLM 调用失败，未完成审核，转降级输出"],
}

# ── 拒绝审核常量生成区结束 ──

# ── 任务线注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

TASK_LINES: dict[str, dict] = {
    "points": {
        "agent_attr": "points_agent",
        "supervisor_attr": "points_supervisor",
        "empty_draft": _EMPTY_POINTS,
        "reject_review": _REJECT_POINTS_REVIEW,
    },
}

# ── 任务线注册生成区结束 ──

def _line(state: NotesState, line_name: str) -> dict:
    """取某任务线在 state 中的子空间（lines[线名]）。"""
    return (state.get("lines") or {}).get(line_name) or {}

def _line_cn(line_name: str) -> str:
    """线名 → 中文名（查共享注册表，未注册则回退英文线名）。"""
    return LINE_CN_NAMES.get(line_name, line_name)

def _line_draft_title(line_name: str) -> str:
    """线名 → 草稿标题（自动推导为「中文名草稿」）。"""
    return f"{_line_cn(line_name)}草稿"

def _line_template(state: NotesState, line_name: str) -> str:
    """取某任务线的输出模板（未传模板时返回空串）。"""
    return (state.get("templates") or {}).get(line_name, "")

def _line_has_structure(report_cls: type) -> bool:
    """该线 Report 是否输出结构化列表（存在 source="structure" 字段）。"""
    return any(
        f.metadata.get("source") == "structure"
        for f in fields(report_cls)
    )

def _normalize_templates(
    template: str,
    item_template: str,
    templates: dict[str, str] | None,
    line_names: list[str],
    report_assemblers: dict,
) -> dict[str, str]:
    """按线统一收纳输出模板：``templates`` 优先，便捷参数兜底。"""
    result = dict(templates or {})
    for line in line_names:
        if line in result:
            continue
        report_cls = report_assemblers[line]
        if _line_has_structure(report_cls):
            if item_template:
                result[line] = item_template
        elif template:
            result[line] = template
    return result

def _compute_title(state: NotesState) -> str:
    """视角标题（通用规则：客观 → 客观输出；个人 → 姓名视角输出）。"""
    if bool(state.get("objective_perspective")):
        return "客观输出"
    user = state.get("user") or {}
    return f"{user.get('name', '用户')}视角输出"

def _assemble_report(
    state: NotesState,
    warning: str | None,
    report_cls: type,
    line_name: str,
) -> object:
    """通用 Report 组装器：按字段 metadata["source"] 从 state 抽屉取值。

    source 约定：
    - ``title`` → 视角标题（_compute_title 通用计算）
    - ``rendered`` → lines[线名]["rendered"]（LLM 渲染文本）
    - ``structure`` → lines[线名]["structure"]（结构化列表）
    - ``draft.xxx`` → lines[线名]["draft"]["xxx"]（草稿字段）
    - 无 source → 不赋值（留给 dataclass default）
    - quality_warning 固定填 warning（降级状态）
    """
    data: dict = {}
    for f in fields(report_cls):
        src = f.metadata.get("source")
        if src is None:
            continue
        if src == "title":
            data[f.name] = _compute_title(state)
        elif src == "rendered":
            data[f.name] = _line(state, line_name).get("rendered")
        elif src == "structure":
            data[f.name] = _line(state, line_name).get("structure")
        elif src.startswith("draft."):
            draft = _line(state, line_name).get("draft") or {}
            data[f.name] = draft.get(src[len("draft."):])
    names = {f.name for f in fields(report_cls)}
    if "quality_warning" in names:
        data["quality_warning"] = warning
    return report_cls(**data)

def _normalize_transcript(text: str) -> str:
    """规范化输入文本：合并段落内硬换行，保留段落间空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\x00", text)
    text = text.replace("\n", "")
    text = text.replace("\x00", "\n\n")
    return text.strip()

def _json(value: object) -> str:
    """dict/list → 可读 JSON 文本（喂给 LLM 用）。"""
    import json
    return json.dumps(value, ensure_ascii=False, indent=2)

def _sec_attr(sec, name, default=None):
    """取段/规则属性：兼容 FallbackRules 对象与裸 dict。"""
    if isinstance(sec, dict):
        return sec.get(name, default)
    return getattr(sec, name, default)

def _pick_label(sec, objective: bool) -> str:
    """段标签：支持视角联动（{objective: ..., personal: ...}）。"""
    label = _sec_attr(sec, "label")
    if isinstance(label, dict):
        return label.get("objective" if objective else "personal", "未命名")
    return label or "未命名"

def _field_values(draft: dict, sec, objective: bool) -> list:
    """取段字段值：支持 merge（客观视角合并多个字段）。"""
    merge = _sec_attr(sec, "merge")
    field = _sec_attr(sec, "field")
    if merge:
        values = list(draft.get(merge[0]) or [])
        if objective:
            for extra in merge[1:]:
                values.extend(draft.get(extra) or [])
        return values
    return draft.get(field) or []

# ── Lines 段逐条格式化器注册表（domain 按需填写）───────────────
# 例：lines 段需要逐条格式化时注册 {线名: 格式化函数(index, item) -> str}
_LINES_FORMATTERS: dict[str, object] = {}

def _empty_purpose(state: NotesState) -> str:
    """empty_purpose 兜底时的「目的」文案（领域有核心理解时覆写）。"""
    return ""

def _fallback_text(
    state: NotesState, line_name: str, rules
) -> tuple[str, list | None]:
    """按声明式规则把草稿拼成确定性文本（+ 可选结构化列表）。

    rules 为 FallbackRules 子类实例（见 tools/fallback_rules.py）：
    - sections: 有序段列表（Raw/Join/Lines）
    - empty_prefix / empty_text / empty_purpose：全空时兜底文案
    - disclaimer: 是否追加 QUALITY_DISCLAIMER
    - structured: {merge: [...]} 客观合并的结构化列表（structure，Report 用）
    """
    draft = _line(state, line_name).get("draft") or {}
    objective = bool(state.get("objective_perspective"))
    sections: list[str] = []
    for sec in _sec_attr(rules, "sections", []) or []:
        values = _field_values(draft, sec, objective)
        kind = _sec_attr(sec, "kind", "raw")
        if kind == "raw":
            if values:
                sections.append(str(values))
        elif kind == "join":
            body = "；".join(str(v) for v in values if v)
            if body:
                sections.append(f"{_pick_label(sec, objective)}：{body}")
        elif kind == "lines":
            formatter = _LINES_FORMATTERS.get(line_name)
            if formatter is None:
                continue  # 未注册该线逐条格式化器：跳过（结构由 structured 提供）
            for index, item in enumerate(values, start=1):
                sections.append(formatter(index, item))
    if not sections:
        text = _sec_attr(rules, "empty_text", "") or ""
        prefix = _sec_attr(rules, "empty_prefix", "") or ""
        if prefix:
            purpose = _empty_purpose(state)
            if purpose and _sec_attr(rules, "empty_purpose", False):
                text = f"{prefix}{purpose}"
            else:
                text = f"{prefix}{text}"
        text = text or "（暂无内容）"
    else:
        text = "\n".join(sections)
    if (
        _sec_attr(rules, "disclaimer", False)
        and text
        and QUALITY_DISCLAIMER not in text
    ):
        text = f"{text}\n\n{QUALITY_DISCLAIMER}"
    structure = None
    structured = _sec_attr(rules, "structured")
    if structured:
        merge = structured.get("merge") or []
        if merge:
            structure = list(draft.get(merge[0]) or [])
            if objective:
                for extra in merge[1:]:
                    structure.extend(draft.get(extra) or [])
    return text, structure

class _Nodes:
    """图节点实现（mixin，供 NotesAgentSystem 继承）。

    同构节点（agent / supervisor / revision / route）由 TASK_LINES 注册表
    通过工厂方法生成；render / fallback 为各线专属方法。

    每个节点方法签名与 LangGraph 节点要求一致：
    接收 state，返回部分更新的 dict。
    """

    MAX_REVISIONS = 1

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _mode_label(state: NotesState) -> str:
        return "objective" if state.get("objective_perspective") else "personal"

    @staticmethod
    def _shared_context(state: NotesState) -> str:
        """agent 共享上下文（视角模式 + 画像 + 视角模型 + 原文）。

        领域专属上下文（如核心理解结果）在此追加。
        """
        mode = _Nodes._mode_label(state)
        return (
            f"视角模式：{mode}\n"
            f"说明：perspective=objective 时为客观全员口径；"
            f"缺省或其它值为个人用户口径。\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文：\n{state['transcript']}"
        )

    @staticmethod
    def _revision_context(
        context: str, feedback: list[str], label: str
    ) -> str:
        if not feedback:
            return context
        return f"{context}\n\nSupervisor {label}：\n{_json(feedback)}"

    def _supervisor_context(self, state: NotesState, line_name: str) -> str:
        cfg = TASK_LINES[line_name]
        sub = _line(state, line_name)
        revision_count = sub.get("revision_count", 0)
        mode = self._mode_label(state)
        allowed = (
            "本轮可以选择 approve、revise 或 reject。"
            if revision_count < self.MAX_REVISIONS
            else "返工次数已用完，本轮只能选择 approve 或 reject。"
        )
        return (
            f"视角模式：{mode}\n"
            f"{_line_cn(line_name)}返工次数：{revision_count}/{self.MAX_REVISIONS}\n"
            f"{allowed}\n\n"
            f"notes理解：\n{_json(state.get('notes_understanding'))}\n\n"
            f"原文（最高事实来源）：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"用户视角模型：\n{_json(state.get('perspective_profile'))}\n\n"
            f"{_line_draft_title(line_name)}：\n{_json(sub['draft'])}"
        )

    async def _perspective_modeling_node(
        self, state: NotesState
    ) -> dict:
        """视角建模（perspective 公共组件）：把用户画像映射到本次输入。"""
        try:
            result = await self.perspective_modeling_agent.run(
                state["transcript"],
                _json(state["user"]),
            )
        except Exception as exc:
            logger.warning("视角建模失败，使用空视角继续", exc_info=True)
            return {
                "perspective_profile": EMPTY_PERSPECTIVE_MODELING,
                "quality_degraded": True,
            }
        return {"perspective_profile": result.model_dump()}

    async def _notes_understanding_node(self, state: NotesState) -> dict:
        """notes理解：提取主题、结构、术语和待澄清问题。"""
        try:
            result = await self.notes_understanding_agent.run(state["transcript"])
        except Exception:
            logger.warning("notes理解失败，使用空理解继续", exc_info=True)
            return {
                "notes_understanding": _EMPTY_NOTES_UNDERSTANDING,
                "quality_degraded": True,
            }
        return {"notes_understanding": result.model_dump()}

    # ── 渲染上下文生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

    def _points_render_context(self, state: NotesState) -> str:
        mode = self._mode_label(state)
        line = _line(state, "points")
        review = line.get("review") or {}
        return (
            f"视角模式：{mode}\n"
            f"objective_perspective：{bool(state.get('objective_perspective'))}\n\n"
            f"原文：\n{state['transcript']}\n\n"
            f"用户画像：\n{_json(state['user'])}\n\n"
            f"已审核用户视角：\n{_json(state.get('perspective_profile'))}\n\n"
            f"已批准知识点总结草稿：\n{_json(line.get('draft'))}\n\n"
            f"知识点总结审核结论：\n{_json(review)}"
        )

    # ── 渲染上下文生成区结束 ──

    # ── 同构节点工厂（由 TASK_LINES 注册表生成）───────────────

    def _make_agent_node(self, line_name: str):
        """生成「生成/提取」节点（agent → 草稿）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: NotesState) -> dict:
            agent = getattr(self, cfg["agent_attr"])
            try:
                result = await agent.run(
                    self._revision_context(
                        self._shared_context(state),
                        _line(state, line_name).get("revision_feedback", []),
                        f"{_line_cn(line_name)}返工意见",
                    )
                )
            except Exception as exc:
                logger.warning(
                    f"{_line_cn(line_name)}生成失败，使用空草稿继续", exc_info=True
                )
                return {
                    "lines": {
                        line_name: {
                            "draft": cfg["empty_draft"],
                            "degraded": True,
                        }
                    },
                    "quality_degraded": True,
                }
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
        """生成「领域审核 + 全局标准」节点（supervisor → review）。"""
        cfg = TASK_LINES[line_name]

        async def node(state: NotesState) -> dict:
            review_agent = getattr(self, cfg["supervisor_attr"])
            try:
                review = await review_agent.review(
                    self._supervisor_context(state, line_name)
                )
            except Exception as exc:
                logger.warning(
                    f"{_line_cn(line_name)}审核失败，使用拒绝审核继续",
                    exc_info=True,
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
        """生成「返工」节点（revise → 带反馈重跑 agent）。"""
        revision_count_key = line_name

        async def node(state: NotesState) -> dict:
            review = _line(state, line_name).get("review") or {}
            feedback = review.get("feedback", []) or []
            sub = _line(state, line_name)
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
        """生成「路由」节点（supervisor → approve/reject/revise 分支）。"""
        revision_count_key = line_name

        def route(state: NotesState) -> str:
            review = _line(state, line_name).get("review") or {}
            decision = review.get("decision")
            if decision == "approve":
                return "__end__"
            revision_count = _line(state, line_name).get("revision_count", 0)
            if decision == "revise" and revision_count < self.MAX_REVISIONS:
                return f"{line_name}_revision"
            return f"{line_name}_fallback"

        return route

    def _line_title(self, state: NotesState, line_name: str) -> str:
        """线 → 展示标题（领域可在前面加自己的线名分支）。

        例：if line_name == "xxx": return "客观xxx" if objective else "xxx"
        """
        objective = bool(state.get("objective_perspective"))
        user = state.get("user") or {}
        name = user.get("name") or "用户"
        return f"{_line_cn(line_name)}输出"

    async def _produce(
        self,
        line_name: str,
        state: NotesState,
        queue: asyncio.Queue,
    ) -> None:
        """通用流式生产者：把指定任务线的文本流式塞进队列（并行事件源）。

        线 → 事件映射（注册表驱动）：
        - chunk 事件统一携带 ``line``（线名）与 ``title``（展示标题）
        - render 实例按命名约定取 ``self.{line_name}_render``
        - 上下文方法按命名约定取 ``self._{line_name}_render_context``
        - render.stream 签名统一 ``(context, template="")``
        - 降级线：直接整段交付 fallback 节点写的确定性文本
        """
        render = getattr(self, f"{line_name}_render")
        title = self._line_title(state, line_name)
        degraded = bool(_line(state, line_name).get("degraded"))
        template = _line_template(state, line_name)
        try:
            if degraded:
                await queue.put(
                    {
                        "type": "chunk",
                        "line": line_name,
                        "title": title,
                        "text": _line(state, line_name).get("rendered") or "",
                    }
                )
                return
            context_fn = getattr(self, f"_{line_name}_render_context")
            context = context_fn(state)
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
            _line(state, line_name)["rendered"] = "".join(parts)
            if _line_has_structure(self._report_assemblers[line_name]):
                draft = _line(state, line_name).get("draft") or {}
                structure = draft.get(line_name)
                if structure is None:
                    lists = [value for value in draft.values() if isinstance(value, list)]
                    structure = lists[0] if len(lists) == 1 else []
                _line(state, line_name)["structure"] = structure
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)

    # ── 专属节点方法生成区：由 tools/scripts/sync_domain.py 生成骨架，函数体可改 ──

    async def _points_fallback_node(self, state: NotesState) -> dict:
        text, structure = _fallback_text(
            state, "points", POINTS_FALLBACK_RULES)
        line_dict = {"rendered": text, "degraded": True}
        if structure is not None:
            line_dict["structure"] = structure
        return {"lines": {"points": line_dict}, "quality_degraded": True}

    # ── 专属节点方法生成区结束 ──

    def _fallback_reports(
        self, state: NotesState, line_names: list[str]
    ) -> dict:
        """图异常/校验失败时的确定性 Report（按线声明式拼装，零线级特判）。"""
        lines = state.setdefault("lines", {})
        for line_name in line_names:
            rules = self._fallback_rules[line_name]
            text, structure = _fallback_text(state, line_name, rules)
            line_dict = lines.setdefault(line_name, {})
            line_dict["rendered"] = text
            if structure is not None:
                line_dict["structure"] = structure
        return {
            line_name: _assemble_report(
                state,
                QUALITY_WARNING,
                self._report_assemblers[line_name],
                line_name,
            )
            for line_name in line_names
        }

class NotesAgentSystem(_Nodes):
    """使用 LangGraph 编排核心层、任务线审核返工与最终输出。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

        # 通过工厂组装全部 Agent 依赖（键名 = 属性名，与 TASK_LINES 的 *_attr 对齐）
        agents = NotesAgentFactory.create(self.client)

        # core 层挂载（perspective 公共组件；领域核心 Agent 在此追加）
        self.perspective_modeling_agent: PerspectiveModelingAgent = agents[
            "perspective_modeling_agent"
        ]
        self.notes_understanding_agent: NotesUnderstandingAgent = agents[
            "notes_understanding_agent"
        ]

        # ── Agent 挂载生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self.points_agent: PointsAgent = agents["points_agent"]
        self.points_supervisor: PointsSupervisor = agents["points_supervisor"]
        self.points_render: PointsRender = agents["points_render"]

        # ── Agent 挂载生成区结束 ──

        # 各线专属的渲染 / 降级节点（同构节点由注册表在 _build_graph 中生成）
        # ── 节点映射生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_nodes: dict[str, object] = {}
        self._fallback_nodes["points"] = self._points_fallback_node

        # ── 节点映射生成区结束 ──

        # ── Report 组装器生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._report_assemblers = {
            "points": PointsReport,
        }

        # ── Report 组装器生成区结束 ──

        # ── FallbackRules 注册生成区：由 tools/scripts/sync_domain.py 生成，勿手改 ──

        self._fallback_rules = {
            "points": POINTS_FALLBACK_RULES,
        }

        # ── FallbackRules 注册生成区结束 ──

    def _normalize_lines(self, lines) -> list[str]:
        """线名校验：未知线直接报错；缺省返回全部注册线。"""
        result = list(lines) if lines else list(TASK_LINES)
        unknown = [name for name in result if name not in TASK_LINES]
        if unknown:
            raise ValueError(
                f"未知任务线 {unknown}，可用：{list(TASK_LINES)}"
            )
        return result

    def _build_graph(
        self, line_names: Iterable[str] | None = None
    ) -> object:
        """构建 LangGraph：core（视角建模）+ 指定任务线。

        ``line_names`` 为 None 时构建全部任务线；否则只构建选中的线
        （core 始终构建——任何任务线都需要视角建模）。
        """
        line_names = self._normalize_lines(line_names)
        builder = StateGraph(NotesState)

        # 核心层：perspective 公共组件。领域可在此追加自己的 core 节点：
        #   builder.add_node("xxx", self._xxx_node)
        #   builder.add_edge(START, "xxx")
        #   core.append("xxx")
        builder.add_node("notes_understanding", self._notes_understanding_node)
        builder.add_node(
            "perspective_modeling", self._perspective_modeling_node
        )
        builder.add_edge(START, "notes_understanding")
        builder.add_edge(START, "perspective_modeling")
        core = ["notes_understanding", "perspective_modeling"]

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
            builder.add_edge(
                f"{line_name}_revision", f"{line_name}_supervisor"
            )
            builder.add_edge(f"{line_name}_fallback", END)

        return builder.compile()

    async def run_streaming(
        self,
        transcript: str,
        user: UserIdentity | None = None,
        template: str = "",
        item_template: str = "",
        templates: dict[str, str] | None = None,
        lines: Iterable[str] | None = None,
    ) -> AsyncIterator[dict]:
        """运行全部指定任务线并流式产出事件（chunk / done）。

        :param transcript: 原文
        :param user: 用户画像（缺省用空画像，走客观口径需设置 perspective）
        :param template: 纯文本线统一输出模板（便捷参数）
        :param item_template: 结构化线统一条目模板（便捷参数）
        :param templates: 按线输出模板（优先级高于便捷参数）
        :param lines: 选跑的任务线，None 表示全部
        """
        if not transcript.strip():
            raise ValueError("原文为空——请先提供会议文本")

        transcript = _normalize_transcript(transcript)
        template = template or ""
        item_template = item_template or ""
        user = user or UserIdentity()
        objective_mode = is_objective_perspective(user)
        user_data = user.model_dump()
        if objective_mode and not user_data.get("perspective"):
            user_data["perspective"] = "objective"
        line_names = self._normalize_lines(lines)
        templates = _normalize_templates(
            template,
            item_template,
            templates,
            line_names,
            self._report_assemblers,
        )
        initial_state = {
            "transcript": transcript,
            "user": user_data,
            "objective_perspective": objective_mode,
            "templates": templates,
        }
        try:
            graph = self._build_graph(line_names)
            state = await graph.ainvoke(initial_state)
        except Exception as exc:
            logger.warning("图执行失败，退回确定性兜底", exc_info=True)
            state = initial_state
            state["lines"] = {}
            state["quality_degraded"] = True
            yield {
                "type": "done",
                "quality_warning": QUALITY_WARNING,
                "reports": self._fallback_reports(state, line_names),
            }
            return

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
                elif isinstance(event, Exception):
                    logger.warning("流式渲染失败：%s", event)
                else:
                    yield event
        finally:
            for task in producers:
                task.cancel()
            await asyncio.gather(*producers, return_exceptions=True)

        any_line_degraded = any(
            bool(_line(state, name).get("degraded")) for name in TASK_LINES
        )
        quality_warning = (
            QUALITY_WARNING
            if (any_line_degraded or bool(state.get("quality_degraded")))
            else None
        )
        yield {
            "type": "done",
            "quality_warning": quality_warning,
            "reports": self._final_reports(state, line_names, quality_warning),
        }

    def _final_reports(
        self,
        state: NotesState,
        line_names: list[str],
        warning: str | None,
    ) -> dict:
        """组装最终 Report（逐个经 validate_payload 严格校验）。"""
        reports = {}
        for line_name in line_names:
            report_cls = self._report_assemblers[line_name]
            reports[line_name] = _assemble_report(
                state, warning, report_cls, line_name
            )
        try:
            return {
                key: validate_payload(type(report), report.model_dump())
                for key, report in reports.items()
            }
        except Exception:
            logger.warning("输出校验失败，退回确定性兜底", exc_info=True)
            return self._fallback_reports(state, line_names)
