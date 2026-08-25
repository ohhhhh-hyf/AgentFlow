# -*- coding: utf-8 -*-
"""意图识别 Agent —— 解析与校验：LLM 输出 → 规范化 Plan。

- params 按任务 schema 归一（字段名与 runner/CLI 打通）
- missing 计算（缺的必需参数，供提示上传/补全）
- 依赖 = LLM needs ∪ 规则 DEPENDS（保守串行）；推导并行/串行说明
"""
from __future__ import annotations

import asyncio
from typing import Any

from .prompts import INTENT_OUTPUT_CONTRACT, INTENT_SYSTEM_PROMPT, build_intent_user_prompt
from .schema import (
    DEPENDS,
    SCALAR_PARAMS,
    TASK_SPECS,
    missing_params,
    normalize_params,
    normalize_task_name,
    task_domain,
)


class IntentResponse:
    """意图识别输出（供 client.structured 校验；浅校验 plan 为数组）。"""

    def __init__(self, plan: list[Any], explanation: str = "") -> None:
        self.plan = plan
        self.explanation = explanation

    @classmethod
    def validate(cls, data: dict[str, Any]) -> "IntentResponse":
        from tools.schema.validation import OutputValidationError

        plan = data.get("plan")
        if not isinstance(plan, list):
            raise OutputValidationError("plan 必须是数组")
        return cls(plan, str(data.get("explanation") or ""))


class TaskPlan:
    __slots__ = ("task", "domain", "params", "missing", "optional", "needs", "note")

    def __init__(
        self,
        task: str,
        params: dict[str, Any],
        needs: list[str],
        note: str,
    ) -> None:
        self.task = task
        self.domain = task_domain(task)
        self.params = params
        self.needs = [n for n in needs if n in TASK_SPECS]
        self.missing = missing_params(task, params)
        self.note = note
        # 可选但未填的标量参数（如 minutes_generation 的 user_id/project）
        spec = TASK_SPECS.get(task) or {}
        scalar_opt = [k for k in (spec.get("optional") or []) if k in SCALAR_PARAMS]
        self.optional = [k for k in scalar_opt if not params.get(k)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "domain": self.domain,
            "params": self.params,
            "missing": self.missing,
            "optional": self.optional,
            "needs": self.needs,
            "note": self.note,
        }


class Plan:
    def __init__(self, tasks: list[TaskPlan], explanation: str = "") -> None:
        self.tasks = tasks
        self.explanation = explanation

    @property
    def parallel_groups(self) -> list[list[TaskPlan]]:
        """标准分层拓扑排序：计算真正的并行执行阶段 (DAG Stages)。
        每一层包含所有依赖已在前面层全部满足的任务（可在同一阶段并发执行）。
        """
        if not self.tasks:
            return []

        index = {t.task: t for t in self.tasks}
        all_task_names = set(index.keys())

        # 计算每个任务在当前 plan 范围内的有效依赖集合
        in_deps: dict[str, set[str]] = {}
        for t in self.tasks:
            declared_needs = set(t.needs)
            rule_needs = DEPENDS.get(t.task, set())
            effective_deps = (declared_needs | rule_needs) & all_task_names
            effective_deps.discard(t.task)
            in_deps[t.task] = effective_deps

        done = set()
        groups: list[list[TaskPlan]] = []
        remaining = list(self.tasks)

        while remaining:
            # 找到所有前置依赖已经全部满足的任务
            current_stage = [
                t for t in remaining
                if in_deps[t.task].issubset(done)
            ]
            if not current_stage:
                # 环形依赖或异常兜底：每次取第一个解环
                current_stage = [remaining[0]]

            groups.append(current_stage)
            for t in current_stage:
                done.add(t.task)
                remaining.remove(t)

        return groups

    def to_dict(self) -> dict[str, Any]:
        return {
            "explanation": self.explanation,
            "plan": [t.to_dict() for t in self.tasks],
            "execution": [
                [t.task for t in group] for group in self.parallel_groups
            ],
        }


def normalize_llm_output(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    """把 LLM 原始输出按 schema 归一到 plan 条目列表。"""
    if not raw:
        return []
    entries = raw.get("plan")
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        task = normalize_task_name(entry.get("task"))
        if not task:
            continue  # 未知任务丢弃
        params = normalize_params(task, entry.get("params"))
        needs = entry.get("needs")
        needs = [str(n).strip() for n in needs if str(n or "").strip()] if isinstance(needs, list) else []
        note = str(entry.get("note") or "").strip()
        out.append({"task": task, "params": params, "needs": needs, "note": note})
    return out


def build_plan(
    text: str,
    llm_raw: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
) -> Plan:
    """LLM 输出 + 上下文默认参数 → 最终 Plan。

    保持任务串行/阶段显式可见（如 ocr -> library、catalog -> checklist）。
    """
    entries = normalize_llm_output(llm_raw)
    if not entries:
        return Plan([], "未能识别出可执行的任务")

    # 若仅包含 checklist，补充前置 catalog 形成显式两阶段流水线
    task_names = [e["task"] for e in entries]
    if "checklist" in task_names and "catalog" not in task_names:
        catalog_entry = {"task": "catalog", "params": {}, "needs": [], "note": "提取核心知识大纲（复习清单前置）"}
        idx = task_names.index("checklist")
        entries.insert(idx, catalog_entry)

    ctx = {k: v for k, v in (context or {}).items() if v}
    tasks: list[TaskPlan] = []
    names = [e["task"] for e in entries]
    for e in entries:
        params = dict(e["params"])
        # 上下文默认参数：只填该任务 schema 允许的字段
        spec = TASK_SPECS.get(e["task"]) or {}
        allowed_ctx = set(spec.get("required") or []) | set(spec.get("optional") or [])
        for key in ("user_id", "user", "subject", "project", "chapter"):
            if key in allowed_ctx and not params.get(key) and ctx.get(key):
                params[key] = str(ctx[key])
        # 规则依赖兜底：needs ∪ DEPENDS（只保留 plan 内存在的任务，去自引用）
        needs = list(e["needs"])
        for dep in DEPENDS.get(e["task"], set()):
            if dep in names and dep not in needs and dep != e["task"]:
                needs.append(dep)
        tasks.append(TaskPlan(e["task"], params, needs, e["note"]))
    explanation = str((llm_raw or {}).get("explanation") or "").strip()
    if not explanation:
        explanation = "、".join(t.task for t in tasks) + " 共 " + str(len(tasks)) + " 个任务"
    return Plan(tasks, explanation)


async def _call_llm(text: str, context: str = "") -> dict[str, Any]:
    from client import LLMClient
    from client.config import load_env

    try:
        from pathlib import Path

        load_env(Path(__file__).resolve().parent.parent / ".env")
        client = LLMClient()
        model = await client.structured(
            INTENT_SYSTEM_PROMPT,
            build_intent_user_prompt(text, context),
            IntentResponse,
            INTENT_OUTPUT_CONTRACT,
            label="intent/agent",
        )
        if isinstance(model, IntentResponse):
            return {"plan": model.plan, "explanation": model.explanation}
        return {}
    except Exception:
        return {}


def _rule_recognize(text: str) -> list[str]:
    """关键词规则识别：匹配用户语句中的任务词，并严格按照在句子中出现的先后顺序排序。"""
    from .schema import TASK_KEYWORDS

    text_clean = text or ""
    matches: list[tuple[int, str]] = []

    for task, keywords in TASK_KEYWORDS.items():
        min_pos = -1
        for kw in sorted(keywords, key=len, reverse=True):
            if kw.startswith("~"):
                import re

                m = re.search(kw[1:], text_clean)
                if m:
                    min_pos = m.start() if min_pos == -1 else min(min_pos, m.start())
                    break
            else:
                pos = text_clean.find(kw)
                if pos != -1:
                    min_pos = pos if min_pos == -1 else min(min_pos, pos)
                    break
        if min_pos != -1:
            matches.append((min_pos, task))

    matches.sort(key=lambda x: x[0])
    hit = [task for _, task in matches]

    # 确保依赖拓扑顺序：library -> catalog -> checklist
    if "checklist" in hit:
        if "catalog" in hit:
            hit.remove("catalog")
        c_idx = hit.index("checklist")
        hit.insert(c_idx, "catalog")
    if "library" in hit:
        hit.remove("library")
        hit.insert(0, "library")

    return hit


def build_plan_from_rules(
    text: str, tasks: list[str], ctx_params: dict[str, Any] | None = None
) -> Plan:
    """规则兜底：用关键词规则的任务生成 Plan。"""
    ctx = {k: v for k, v in (ctx_params or {}).items() if v}
    plan_tasks: list[TaskPlan] = []
    names = list(tasks)
    for task in tasks:
        params: dict[str, Any] = {}
        spec = TASK_SPECS.get(task) or {}
        allowed = set(spec.get("required") or []) | set(spec.get("optional") or [])
        for key in ("user_id", "user", "subject", "project"):
            if key in allowed and ctx.get(key):
                params[key] = str(ctx[key])
        needs = [d for d in DEPENDS.get(task, set()) if d in names]
        note_map = {
            "ocr": "识别图片文字与公式",
            "library": "结构化解析并入库",
            "catalog": "提取核心知识大纲",
            "checklist": "生成考点与复习清单",
            "quiz": "生成智能自测题",
            "knowledge_graph": "构建知识图谱拓扑",
            "minutes_generation": "生成多视角会议纪要",
            "action_items": "提取行动项与待办 (TODO)",
            "risk": "分析会议潜在风险点",
            "mindmap": "导出交互式思维导图",
            "minutes_trace": "事实核查与发言溯源",
            "multi_styles": "生成多风格版本纪要",
            "review": "笔记审校与逻辑核查",
        }
        note = note_map.get(task, f"执行{task}")
        plan_tasks.append(TaskPlan(task, params, needs, note))
    return Plan(plan_tasks, "、".join(tasks) + f" 共 {len(tasks)} 个任务")


def parse(text: str, context: str = "", ctx_params: dict[str, Any] | None = None) -> Plan:
    """同步入口：一句话 → Plan。

    识别策略（极速+高准度）：
    1. 关键词规则先行（毫秒级、确定性）——命中且完整时直接采用
    2. 否则 LLM 深度语义识别
    3. LLM 失败/为空 → 关键词规则兜底
    """
    text = (text or "").strip()
    rules = _rule_recognize(text)
    if rules and len(rules) >= 1:
        # 命中明确规则任务（如包含复习清单、会议纪要等），直接组装精准 Plan
        return build_plan_from_rules(text, rules, ctx_params)
    raw = asyncio.run(_call_llm(text, context))
    plan = build_plan(text, raw, ctx_params)
    if not plan.tasks and rules:
        return build_plan_from_rules(text, rules, ctx_params)
    return plan
