"""Stage 4：场景识别状态从 API 一路透传到 graph（开关关闭时行为不变）。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas import TaskRequest
from app.tasks import _prepare, _runner_args
from core.runner import runner as runner_mod
from core.runner.runner import prepare_run
from domains.meeting.models import MeetingState
from domains.meeting.orchestrator import MeetingAgentSystem

TRANSCRIPT = (
    "张三 10:00\n"
    "项目二期量产良率达到了91.5%，流片测试很顺利，下周继续优化。\n"
    "王五 10:05\n"
    "智能客服降本方案测试可以替代70%的常规咨询。\n"
)

AGENDA_TRANSCRIPT = (
    "张三 10:00\n"
    "自研芯片二期量产良率达到了91.5%，我们的二期流片测试很顺利。\n\n"
    "王五 10:30\n"
    "智能客服降本方案目前测试可以替代70%的常规咨询。\n"
)


def _prep(transcript: str = TRANSCRIPT, *, template: str = "", profile: str = "", docs=None):
    extra: dict = {}
    if template:
        extra["template"] = template
    if profile:
        extra["profile"] = profile
    req = TaskRequest(texts={"transcript": transcript}, docs=docs or [], extra=extra)
    return _prepare("meeting", "minutes", req, "u_test_template_state")


def _fake_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """个人档画像：避免依赖 data/{user_id}/user.json。"""
    object_path = Path(__file__).resolve().parents[3] / "resources" / "profiles" / "object.json"
    user_path = tmp_path / "user.json"
    user_path.write_text(json.dumps({"name": "张三"}), encoding="utf-8")

    def fake_profile_file(domain: str, profile_value: str, user_id: str = "") -> Path:
        if (profile_value or "").strip().lower() == "user":
            return user_path
        return object_path

    monkeypatch.setattr("app.tasks._profile_file", fake_profile_file)


def _agenda_docs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三\n2. 智能客服降本方案 汇报人：王五", encoding="utf-8")
    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)
    return ["agenda.txt"]


def test_switch_off_default_is_general_minutes(monkeypatch) -> None:
    monkeypatch.delenv("MINUTES_TEMPLATE_AUTO", raising=False)
    p = _prep()
    assert p.template_auto is False
    assert p.template_source == "default"
    assert p.template_id == "general_minutes"
    assert p.template_mode == "normal"


def test_switch_on_marks_empty_template_auto(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    p = _prep()
    assert p.template_auto is True
    assert p.template_source == "default"
    assert p.template_id == "general_minutes"


def test_explicit_template_disables_auto(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    p = _prep(template="project_progress.md")
    assert p.template_auto is False
    assert p.template_source == "explicit"
    assert p.template_id == "project_progress"


def test_explicit_chinese_template_maps_to_english_id(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    p = _prep(template="项目进度会")
    assert p.template_auto is False
    assert p.template_source == "explicit"
    assert p.template_id == "project_progress"


def test_personal_profile_keeps_personal_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    _fake_profile(monkeypatch, tmp_path)
    p = _prep(profile="user")
    assert p.template_auto is False
    assert p.template_source == "personal_default"
    assert p.template_id == "personal_minutes"


def test_agenda_mode_is_passed_through(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    docs = _agenda_docs(monkeypatch, tmp_path)
    p = _prep(AGENDA_TRANSCRIPT, docs=docs)
    assert p.template_mode == "agenda"
    assert p.template_auto is True
    assert p.template_id == "general_minutes"


def test_runner_args_carry_all_fields(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    p = _prep()
    args = _runner_args(p)
    assert args["template_auto"] is True
    assert args["template_source"] == "default"
    assert args["template_id"] == "general_minutes"
    assert args["template_mode"] == "normal"


def test_prepare_run_returns_fields(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    p = _prep(template="project_progress")
    args = _runner_args(p)
    args["compile_natural"] = False
    prep = asyncio.run(prepare_run(p.ctx, **args))
    assert prep.template_auto is False
    assert prep.template_source == "explicit"
    assert prep.template_id == "project_progress"
    assert prep.template_mode == "normal"


def test_run_passes_fields_to_run_streaming(monkeypatch) -> None:
    seen: dict = {}
    prepare_kwargs: dict = {}

    class _StubSystem:
        client = None

        async def run_streaming(self, transcript, user=None, **kwargs):
            seen.update(kwargs)
            yield {"type": "chunk", "line": "minutes", "title": "纪要", "text": "x"}

    system = _StubSystem()
    prep = SimpleNamespace(
        system=system,
        ctx=SimpleNamespace(name="meeting", output_dir=""),
        line_names=["minutes"],
        transcript=TRANSCRIPT,
        user=None,
        template_texts={},
        line_extra={},
        memory_enabled=False,
        memory_bind=None,
        graph_silent=True,
        usage_before={},
        task_monitor=None,
        subject=None,
        lang="zh",
        template_auto=True,
        template_source="auto",
        template_id="project_progress",
        template_mode="normal",
    )

    async def fake_prepare_run(ctx, file, profile, env_file, *args, **kwargs):
        prepare_kwargs.update(kwargs)
        return prep

    monkeypatch.setattr(runner_mod, "prepare_run", fake_prepare_run)

    asyncio.run(
        runner_mod.run(
            SimpleNamespace(name="meeting", output_dir=""),
            Path("input.txt"),
            Path("profile.json"),
            Path(".env"),
            None,
            ["minutes"],
            template_auto=True,
            template_source="auto",
            template_id="project_progress",
            template_mode="normal",
            collect_reports=False,
        )
    )

    assert prepare_kwargs["template_auto"] is True
    assert prepare_kwargs["template_source"] == "auto"
    assert seen["template_auto"] is True
    assert seen["template_source"] == "auto"
    assert seen["template_id"] == "project_progress"
    assert seen["template_mode"] == "normal"


def test_run_streaming_puts_fields_into_initial_state() -> None:
    captured: list[dict] = []

    class _FakeGraph:
        async def astream(self, initial_state, stream_mode=None):
            captured.append(initial_state)
            raise RuntimeError("stop after capture")
            yield  # pragma: no cover - 保持 async generator 语义

    system = object.__new__(MeetingAgentSystem)
    system._task_lines = {"minutes": {}}
    system._report_assemblers = {}
    system._build_graph = lambda line_names: _FakeGraph()
    system._fallback_reports = lambda state, lines: {}
    system._quality_warning = None
    system._pipeline_by_line = lambda state, lines: {}
    system._understanding = lambda state: {}
    system._memory_done_context = lambda state, lines: {}

    async def _drain():
        return [
            event
            async for event in system.run_streaming(
                TRANSCRIPT,
                None,
                templates={"minutes": "# 模板\n## [摘要]\n[内容]"},
                lines=["minutes"],
                template_auto=True,
                template_source="auto",
                template_id="project_progress",
                template_mode="agenda",
            )
        ]

    events = asyncio.run(_drain())
    assert events and events[-1]["type"] == "done"
    state = captured[0]
    assert state["template_auto"] is True
    assert state["template_source"] == "auto"
    assert state["template_id"] == "project_progress"
    assert state["template_mode"] == "agenda"


def test_meeting_state_declares_template_fields() -> None:
    assert {
        "template_auto",
        "template_source",
        "template_id",
        "template_mode",
    } <= set(MeetingState.__annotations__)
