"""引擎/app 层冒烟（零 LLM）：桩系统跑通 ``prepare_run`` → ``run`` → 落盘 → 记忆钩子。

用法::

    python -m tests.test_engine_smoke

为什么单独一套：引擎层（tools/core/runner、tools/runtime/render、tools/exports/outputs）
一直没有自动化测试，而它的改动最容易出现"编译 + 单测全绿、真实请求 500"——2026-09-22 的
``name 'hooks' is not defined`` 就是这类（只被真实 HTTP 冒烟抓到）。本套件用**桩系统**把
引擎的接线钉死：记忆准备/回写走的是域钩子、产物落盘走的是域 HTML 钩子、无模板压缩走的是
压缩钩子；图与各 Agent 归真系统负责，这里不碰，所以零 LLM、秒级。
"""
from __future__ import annotations

import asyncio
import tempfile
from dataclasses import replace
from pathlib import Path

from tools.core import runner
from tools.core.domain_hooks import hooks_for, register
from tools.core.runtime_context import load_domain

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = """# 通用纪要

# [纪要正文]
[一段话写清本场要点]
"""
TRANSCRIPT = "申家坤 10:00:01\n长文本我回去改配置。\n武思华 10:00:20\n引擎报表下周出。\n"
LINE_TEXT = "# 全文摘要\n\n本场先过 Java 侧节奏，长文本回去改配置。（2026-09-22 冒烟桩文本）\n"


class _StubSystem:
    """桩系统：引擎只依赖 ``run_streaming``（图/Agent 由真系统负责，本测试不触）。"""

    def __init__(self, events: list[dict]) -> None:
        self._events = [dict(item) for item in events]
        self.client = None  # 引擎的 usage 快照会捕获 AttributeError 并返回空
        self.seen: dict = {}

    async def run_streaming(
        self, transcript, user, *, templates=None, lines=None, line_modes=None, line_extra=None
    ):
        self.seen = {
            "transcript": transcript,
            "templates": dict(templates or {}),
            "lines": list(lines or []),
            "line_extra": dict(line_extra or {}),
        }
        for event in self._events:
            yield event


def _events() -> list[dict]:
    return [
        {"type": "chunk", "line": "minutes", "title": "会议纪要", "text": LINE_TEXT},
        {
            "type": "done",
            "reports": {"minutes": {"headline": "会议纪要", "personalized_minutes": LINE_TEXT}},
            "understanding": {"meeting_purpose": "冒烟", "speakers": []},
            "quality_warning": None,
            "gate_by_line": {"minutes": None},
        },
    ]


async def _drive(tmp: Path, *, memory: bool, profile: Path, spy: dict) -> tuple[dict, _StubSystem, object]:
    """跑一遍 prepare_run + run，返回 (collected, 桩系统, prep)。"""
    ctx = load_domain("meeting", tmp)
    ctx.output_dir = tmp / "out"
    transcript_file = tmp / "input.txt"
    transcript_file.write_text(TRANSCRIPT, encoding="utf-8")
    template_file = tmp / "template.md"
    template_file.write_text(TEMPLATE, encoding="utf-8")

    system = _StubSystem(_events())
    ctx.system_cls = lambda: system  # 桩系统替掉真系统（真系统会真调 LLM）

    prep = await runner.prepare_run(
        ctx,
        transcript_file,
        profile,
        tmp / ".env",
        {"minutes": template_file},
        ["minutes"],
        None,
        "1",
        "冒烟项目",
        None,
        None, None, None, None, None, None,
        compile_natural=False,      # 占位符模板不需要编译，省掉 client
        monitor=False,
        collect_reports=True,
        memory=memory,
        meeting_time="2026-09-22 10:00",
    )
    collected = await runner.run(
        ctx,
        transcript_file,
        profile,
        tmp / ".env",
        {"minutes": template_file},
        ["minutes"],
        None,
        "1",
        "冒烟项目",
        None,
        None, None, None, None, None, None,
        compile_natural=False,
        monitor=False,
        collect_reports=True,
        memory=memory,
        meeting_time="2026-09-22 10:00",
    )
    return collected or {}, system, prep


def test_engine_smoke() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw).resolve()
        hooks = hooks_for("meeting")
        calls: dict = {}
        orig_prepare = hooks.prepare_memory

        def spy_prepare(**kwargs):
            calls["prepare"] = kwargs
            return orig_prepare(**kwargs)

        def spy_persist(**kwargs):
            # 只记录不转发：原实现会真的写记忆并调 embedding API（本套件要求完全离线、秒级）。
            # "记忆写得对不对"由 tests/test_meeting_memory.py 覆盖，这里只钉"引擎有没有按
            # 约定调用钩子"。
            calls["persist"] = kwargs
            return None

        register("meeting", replace(hooks, prepare_memory=spy_prepare, persist_memory=spy_persist))
        try:
            collected, system, prep = asyncio.run(
                _drive(tmp, memory=True, profile=PROJECT_ROOT / "assets" / "profiles" / "developer.json", spy=calls)
            )
        finally:
            register("meeting", hooks)

        check("prepare_run：l经域钩子准备记忆（memory_lines 判定生效）",
              prep.memory_enabled is True and "prepare" in calls, str(prep.memory_enabled))
        check("prepare_run：line_extra 里带上了会议记忆 meta（引擎不认 META_KEY，由钩子写入）",
              bool(prep.line_extra), str(list(prep.line_extra)))
        check("prepare_run：桩系统收到模板与线名",
              system.seen.get("lines") == ["minutes"] and bool(system.seen.get("templates", {}).get("minutes")), "")
        check("run：done 事件被落盘（正文产物存在且内容为事件里的文本）",
              (path := (collected.get("saved") or {}).get("minutes", {}).get("text")) is not None
              and Path(path).is_file()
              and "冒烟桩文本" in Path(path).read_text(encoding="utf-8"),
              str((collected.get("saved") or {}).get("minutes")))
        check("run：域 HTML 钩子生效（minutes.html 由域渲染器生成）",
              (html := (collected.get("saved") or {}).get("minutes", {}).get("html")) is not None
              and Path(html).is_file()
              and "<html" in Path(html).read_text(encoding="utf-8").lower(),
              str(html))
        check("run：跑完走域钩子回写记忆（persist_memory 被调用并带上 user/project）",
              "persist" in calls
              and calls["persist"].get("user_id") == "1"
              and calls["persist"].get("project_id") == "冒烟项目",
              str(sorted(calls.get("persist", {}).keys())))

        # 对照：memory=False → 准备/回写都不触发，line_extra 为空
        calls.clear()
        register("meeting", replace(hooks, prepare_memory=spy_prepare, persist_memory=spy_persist))
        try:
            collected2, _, prep2 = asyncio.run(
                _drive(tmp, memory=False, profile=PROJECT_ROOT / "assets" / "profiles" / "object.json", spy=calls)
            )
        finally:
            register("meeting", hooks)
        check("memory=False：不准备记忆、line_extra 为空、回写钩子不触发",
              prep2.memory_enabled is False and prep2.line_extra == {} and not calls,
              f"{prep2.memory_enabled} {prep2.line_extra} {sorted(calls)}")
        check("memory=False：产物照常落盘（客观档不受记忆开关影响）",
              bool((collected2.get("saved") or {}).get("minutes", {}).get("text")), "")


class _StubAgent:
    """桩生成 Agent：只回一个能 model_dump 的对象。"""

    def __init__(self, draft: dict) -> None:
        self._draft = draft
        self.last_context = ""

    async def run(self, context):
        self.last_context = context

        class _Out:
            def __init__(self, data: dict) -> None:
                self._data = data

            def model_dump(self) -> dict:
                return dict(self._data)

        return _Out(self._draft)


def _node_state(line_extra: dict | None = None) -> dict:
    return {
        "transcript": TRANSCRIPT,
        "meeting_understanding": {"meeting_purpose": "冒烟", "speakers": []},
        "notes_understanding": {},
        "user": {"name": "申家坤"},
        "perspective_profile": {},
        "objective_perspective": False,
        "line_extra": line_extra or {},
        "line_modes": {},
        "lines": {},
        "templates": {},
    }


def test_engine_agent_node() -> None:
    """引擎的 `_make_agent_node`（每线生成入口）真的能跑：两域都覆盖。

    这段代码在 app 冒烟里被桩系统替掉了，只能在这里覆盖——2026-09-22 的
    `hooks_for` 未导入就是它先暴露的（真实请求报 graph run failed）。
    """
    from dataclasses import replace as _replace

    from domain.meeting.orchestrator import MeetingAgentSystem
    from domain.notes.orchestrator import NotesAgentSystem
    from tools.core.domain_hooks import hooks_for, register

    # meeting：记忆线 → 注入钩子应给出 memory_context（engine 写回 line state）
    hooks = hooks_for("meeting")
    bind, line_extra = hooks.prepare_memory(
        project_root=PROJECT_ROOT,
        domain="meeting",
        user_id="1",
        transcript=TRANSCRIPT,
        line_names=["minutes"],
        project_id="冒烟项目",
        subject=None,
        meeting_time="2026-09-22 10:00",
        request_id="req-smoke",
    )
    check("节点级：prepare_memory 给出会议记忆 meta（注入的前提）", bool(line_extra), str(line_extra))

    # 用 spy 包一层注入钩子：断言引擎**确实调用了它**（真实内容取决于记忆命中，stub 理解里
    # 没有可绑定的项目 ⇒ 允许为空 context，这是合法路径）
    calls: dict = {}
    orig_inject = hooks.inject_line_extra

    def spy_inject(state_arg, line_arg, *, line_extra=None):
        calls["inject"] = line_arg
        return orig_inject(state_arg, line_arg, line_extra=line_extra)

    register("meeting", _replace(hooks, inject_line_extra=spy_inject))
    try:
        system = object.__new__(MeetingAgentSystem)  # 不跑 __init__（会建 LLM client）
        system._task_lines = {"minutes": {"agent_attr": "minutes_agent", "empty_draft": {}}}
        system._line_cn_names = {"minutes": "纪要"}
        system.minutes_agent = _StubAgent({"headline": "冒烟", "executive_summary": ["要点"],
                                           "history_comparison": []})
        out = asyncio.run(system._make_agent_node("minutes")(_node_state(line_extra)))
    finally:
        register("meeting", hooks)
    draft = (out.get("lines") or {}).get("minutes", {})
    check("节点级：meeting 生成节点返回草稿且未降级",
          draft.get("degraded") is False and draft.get("draft", {}).get("headline") == "冒烟",
          str(draft)[:120])
    check("节点级：引擎按钩子接线注入记忆（钩子被调用 + 结果写回 line state）",
          calls.get("inject") == "minutes"
          and {"memory_context", "memory_bind", "memory_warning"} <= set(draft),
          f"{calls} {sorted(draft)}")
    check("节点级：注入为空也不影响生成（无可绑定项目时 context 为空是合法路径）",
          draft.get("memory_context") == "", repr(draft.get("memory_context")))

    # notes：非记忆注入线（inject_line_extra 为空）→ 节点照样跑通、字段为空
    notes = object.__new__(NotesAgentSystem)
    notes._task_lines = {"graph": {"agent_attr": "graph_agent", "empty_draft": {}}}
    notes._line_cn_names = {"graph": "知识图谱"}
    notes.graph_agent = _StubAgent({"headline": "图谱"})
    out2 = asyncio.run(notes._make_agent_node("graph")(_node_state()))
    draft2 = (out2.get("lines") or {}).get("graph", {})
    check("节点级：notes 生成节点跑通且无记忆注入（空 context）",
          draft2.get("degraded") is False and draft2.get("memory_context") == "",
          str(draft2)[:120])


def main() -> int:
    test_engine_smoke()
    test_engine_agent_node()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for item in FAIL:
        print("FAIL", item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
