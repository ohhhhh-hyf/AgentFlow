"""Stage 6：FakeLLM 集成（普通/议题/回退）+ render 使用选中模板 + 日志串联。"""
from __future__ import annotations

import asyncio
import logging

from app.config import resolve_agenda_template_format, resolve_template_format
from core.runtime.render import produce_line
from domains.meeting.models_generated import (
    MeetingUnderstanding,
    Minutes,
    MinutesSupervisorReview,
)
from domains.meeting.orchestrator import MeetingAgentSystem

NORMAL_TRANSCRIPT = (
    "张三 10:00: 项目二期量产良率 91.5%，下周进入小批量。\n"
    + ("李四 10:05: 继续讨论量产排期、风险和资源。\n" * 120)
)
AGENDA_TEXT = "1. 自研车载芯片二期量产 汇报人：张三"
AGENDA_TRANSCRIPT = (
    "张三 10:00: 进展汇报自研芯片二期量产良率 91.5%\n"
    + ("李四 10:05: 继续讨论量产排期与风险。\n" * 120)
)


class FakeLLM:
    """同时支持分类用的 text() 与各 Agent 用的 structured()。"""

    def __init__(self, classification: str) -> None:
        self.classification = classification
        self.text_calls: list[str] = []
        self.structured_labels: list[str] = []

    async def text(self, system: str, user: str, **kwargs) -> str:
        self.text_calls.append(kwargs.get("label", ""))
        return self.classification

    async def structured(self, prompt, *args, **kwargs):
        label = kwargs.get("label", "")
        self.structured_labels.append(label)
        if "meeting_understanding" in label:
            return MeetingUnderstanding(meeting_brief="测试简报", meeting_purpose="项目讨论")
        if "minutes/agent" in label:
            return Minutes(headline="测试标题", executive_summary=["段落1"])
        if "minutes/supervisor" in label:
            return MinutesSupervisorReview(
                decision="approve",
                facts_check={"passed": True, "issues": []},
                perspective_check={"passed": True, "issues": []},
                consistency_check={"passed": True, "issues": []},
                feedback=[],
            )
        raise ValueError(f"Unexpected label {label}")


class _CaptureRender:
    def __init__(self) -> None:
        self.templates: list[str] = []

    async def run(self, context, template, **kwargs):
        self.templates.append(template)
        return "# 摘要\n测试正文"


class _Policy:
    def uses_llm_render(self, template: str) -> bool:
        return True


class _RenderEngine:
    domain_name = "meeting"
    _line_cn_names = {"minutes": "纪要"}

    def __init__(self) -> None:
        self.minutes_render = _CaptureRender()

    def _line_title(self, state, line_name):  # noqa: ANN001
        return "纪要"

    def _render_context(self, state, line_name):  # noqa: ANN001
        return "渲染上下文"

    def _render_directives(self, state, line_name):  # noqa: ANN001
        return ""

    def _pre_render_hook(self, state, line_name):  # noqa: ANN001
        return False

    def _post_render_hook(self, state, line_name):  # noqa: ANN001
        return None

    def _line_policy(self, line_name):  # noqa: ANN001
        return _Policy()


def _state(transcript: str, *, mode: str, template: str, line_extra: dict | None = None) -> dict:
    return {
        "transcript": transcript,
        "user": {},
        "lines": {"minutes": {"revision_count": 0}},
        "templates": {"minutes": template},
        "template_auto": True,
        "template_source": "default",
        "template_id": "general_minutes",
        "template_mode": mode,
        "line_extra": line_extra or {},
        "lang": "zh",
    }


def _run_graph(fake: FakeLLM, state: dict) -> dict:
    system = MeetingAgentSystem(fake)
    graph = system._build_graph(["minutes"])
    return asyncio.run(graph.ainvoke(state))


def _render(state: dict) -> list[str]:
    async def _drive() -> list[str]:
        engine = _RenderEngine()
        queue: asyncio.Queue = asyncio.Queue()
        await produce_line(engine, "minutes", state, queue)
        return engine.minutes_render.templates

    return asyncio.run(_drive())


def test_normal_graph_selects_template_and_render_uses_it(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    monkeypatch.setenv("TEMPLATE_ROUTER", "off")
    caplog.set_level(logging.INFO)
    fake = FakeLLM('{"template":"project_progress","confidence":0.86}')
    state = _state(
        NORMAL_TRANSCRIPT,
        mode="normal",
        template=resolve_template_format("general_minutes", "zh").strip(),
    )

    final_state = _run_graph(fake, state)

    assert final_state["template_id"] == "project_progress"
    assert final_state["template_source"] == "auto"
    assert final_state["template_decision"]["applied"] is True
    expected = resolve_template_format("project_progress", "zh").strip()
    assert final_state["templates"]["minutes"] == expected

    captured = _render(final_state)
    assert captured == [expected]
    text = caplog.text
    for marker in (
        "[template:auto:start]",
        "[template:auto:agent]",
        "[template:auto:decision]",
        "[template:auto:done]",
        "render line=minutes template_id=project_progress template_source=auto template_mode=normal",
    ):
        assert marker in text, marker
    # 日志不落完整原文 / 完整 Prompt
    assert NORMAL_TRANSCRIPT[:80] not in text
    assert "【待检测文本】" not in text


def test_agenda_graph_selects_agenda_template_and_render_uses_it(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    monkeypatch.setenv("TEMPLATE_ROUTER", "off")
    caplog.set_level(logging.INFO)
    fake = FakeLLM('{"template":"team_meeting","confidence":0.84}')
    state = _state(
        AGENDA_TRANSCRIPT,
        mode="agenda",
        template=resolve_agenda_template_format("general_minutes", "zh").strip(),
        line_extra={"agenda_text": AGENDA_TEXT},
    )

    final_state = _run_graph(fake, state)

    assert final_state["has_valid_agenda"] is True
    assert final_state["template_id"] == "team_meeting"
    assert final_state["template_source"] == "auto"
    expected = resolve_agenda_template_format("team_meeting", "zh").strip()
    assert final_state["templates"]["minutes"] == expected

    captured = _render(final_state)
    assert captured == [expected]
    assert (
        "render line=minutes template_id=team_meeting template_source=auto template_mode=agenda"
        in caplog.text
    )


def test_fallback_graph_renders_general_minutes(monkeypatch, caplog) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    monkeypatch.setenv("TEMPLATE_ROUTER", "off")
    caplog.set_level(logging.INFO)
    fake = FakeLLM('{"template":"project_progress","confidence":0.62}')
    general = resolve_template_format("general_minutes", "zh").strip()
    state = _state(NORMAL_TRANSCRIPT, mode="normal", template=general)

    final_state = _run_graph(fake, state)

    assert final_state["template_id"] == "general_minutes"
    assert final_state["template_source"] == "auto_fallback"
    assert final_state["template_decision"]["reason"] == "low_confidence"
    assert final_state["templates"]["minutes"] == general

    captured = _render(final_state)
    assert captured == [general]
    assert (
        "render line=minutes template_id=general_minutes template_source=auto_fallback"
        in caplog.text
    )
    assert "reason=low_confidence" in caplog.text
