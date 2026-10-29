"""Stage 3：隔离的分类 Agent（FakeLLM）。"""
from __future__ import annotations

import asyncio
import logging
import re

import pytest

from domains.meeting.tasks.minutes.steps.scene_catalog import (
    AGENDA_CANDIDATE_IDS,
    NORMAL_CANDIDATE_IDS,
)
from domains.meeting.tasks.minutes.steps.template_classifier import (
    TemplateClassifierAgent,
)


class FakeClient:
    def __init__(self, response: str = "", exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, str, dict]] = []

    async def text(self, system: str, user: str, **kwargs) -> str:
        self.calls.append((system, user, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.response


def _long_transcript() -> str:
    return "会议内容" * 600  # 2400 字，不触发短会/采样


def _run(agent: TemplateClassifierAgent, *args, **kwargs):
    return asyncio.run(agent.run(*args, **kwargs))


def test_agent_returns_parsed_result_and_call_params() -> None:
    client = FakeClient('{"template":"project_progress","confidence":0.86}')
    agent = TemplateClassifierAgent(client)

    result = _run(agent, _long_transcript(), "", NORMAL_CANDIDATE_IDS, lang="zh")

    assert result.ok is True
    assert result.skipped is False
    assert result.parsed == {"template": "project_progress", "confidence": 0.86}
    assert result.error is None
    assert result.duration >= 0

    system, user, kwargs = client.calls[0]
    assert len(re.findall(r"^- [a-z_]+（", system, re.M)) == 29
    assert "【待检测文本】" in user
    assert kwargs["temperature"] == 0.0
    assert kwargs["json_mode"] is True
    assert kwargs["max_tokens"] == 128
    assert kwargs["timeout"] == 15.0
    assert kwargs["label"] == "minutes/template_classify"


def test_agent_skips_short_transcript_without_call() -> None:
    client = FakeClient('{"template":"project_progress","confidence":0.9}')
    agent = TemplateClassifierAgent(client)

    result = _run(agent, "短会", "", NORMAL_CANDIDATE_IDS)

    assert result.ok is False
    assert result.skipped is True
    assert result.error == "short_text"
    assert client.calls == []


def test_agent_returns_invalid_output_without_raising() -> None:
    client = FakeClient("not json")
    agent = TemplateClassifierAgent(client)

    result = _run(agent, _long_transcript(), "", NORMAL_CANDIDATE_IDS)

    assert result.ok is False
    assert result.skipped is False
    assert result.parsed is None
    assert result.error == "invalid_output"
    assert result.raw_output == "not json"


def test_agent_returns_call_error_without_raising() -> None:
    client = FakeClient(exc=TimeoutError("timeout"))
    agent = TemplateClassifierAgent(client)

    result = _run(agent, _long_transcript(), "", NORMAL_CANDIDATE_IDS)

    assert result.ok is False
    assert result.error == "call_error:TimeoutError"
    assert result.parsed is None


def test_agent_uses_agenda_candidates_and_agenda_message() -> None:
    client = FakeClient('{"template":"team_meeting","confidence":0.8}')
    agent = TemplateClassifierAgent(client)

    result = _run(
        agent,
        _long_transcript(),
        "1. 议题：定价\n2. 议题：排期",
        AGENDA_CANDIDATE_IDS,
    )

    assert result.ok is True
    system, user, _ = client.calls[0]
    assert len(re.findall(r"^- [a-z_]+（", system, re.M)) == 20
    assert "clinical_advisory" not in system
    assert "【现场审定的有效议题清单】" in user
    assert "1. 议题：定价" in user


def test_agent_samples_long_transcript() -> None:
    client = FakeClient('{"template":"project_progress","confidence":0.8}')
    agent = TemplateClassifierAgent(client)
    text = "H" * 6000 + "\n" + "M" * 4000 + "\n" + "T" * 5000

    _run(agent, text, "", NORMAL_CANDIDATE_IDS)

    _, user, _ = client.calls[0]
    assert "【中段节选】" in user
    assert "【结尾】" in user


def test_agent_rejects_empty_candidates_without_call() -> None:
    client = FakeClient('{"template":"project_progress","confidence":0.8}')
    agent = TemplateClassifierAgent(client)

    result = _run(agent, _long_transcript(), "", [])

    assert result.ok is False
    assert result.error == "no_candidates"
    assert client.calls == []


def test_agent_logs_raw_and_invalid_output(caplog) -> None:
    caplog.set_level(logging.INFO)
    agent = TemplateClassifierAgent(
        FakeClient('{"template":"project_progress","confidence":0.86}')
    )
    _run(agent, _long_transcript(), "", NORMAL_CANDIDATE_IDS)
    assert "[template:auto:agent]" in caplog.text
    assert "raw_template=project_progress" in caplog.text
    assert "raw_confidence=0.86" in caplog.text
    assert "prompt_version=scene-v1" in caplog.text

    caplog.clear()
    agent = TemplateClassifierAgent(FakeClient("not json"))
    _run(agent, _long_transcript(), "", NORMAL_CANDIDATE_IDS)
    assert "[template:auto:agent:invalid]" in caplog.text
