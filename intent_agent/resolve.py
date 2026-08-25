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
        """无相互依赖的任务可并行；有 needs 的按依赖串行。返回执行分组。"""
        ready: list[TaskPlan] = []
        index = {t.task: t for t in self.tasks}
        names = [t.task for t in self.tasks]
        for t in self.tasks:
            deps = set(t.needs) | DEPENDS.get(t.task, set())
            deps = {d for d in deps if d in names and index.get(d) is not t}
            if not deps:
                ready.append(t)
        groups: list[list[TaskPlan]] = [ready] if ready else []
        done = {t.task for t in ready}
        for t in self.tasks:
            if t in ready:
                continue
            if set(t.needs) <= done:
                groups.append([t])
                done.add(t.task)
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

    context：{user_id, subject, user, ...} 作为缺失参数的默认值
    （用户句子已给的值优先，LLM 已填的 params 优先于 context）。
    """
    entries = normalize_llm_output(llm_raw)
    if not entries:
        return Plan([], "未能识别出可执行的任务")
    ctx = {k: v for k, v in (context or {}).items() if v}
    tasks: list[TaskPlan] = []
    names = [e["task"] for e in entries]
    for e in entries:
        params = dict(e["params"])
        # 上下文默认参数：只填该任务 schema 允许的字段（OCR 不需要 user_id 就不塞）
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


def parse(text: str, context: str = "", ctx_params: dict[str, Any] | None = None) -> Plan:
    """同步入口：一句话 → Plan。context 是给 LLM 的已知上下文文本；ctx_params 是默认参数。"""
    raw = asyncio.run(_call_llm(text, context))
    return build_plan(text, raw, ctx_params)
