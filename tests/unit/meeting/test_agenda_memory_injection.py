"""Step 4：议题纪要注入事实。agenda-only，普通 minutes / minutes_styles 零影响。"""
from __future__ import annotations

from pathlib import Path

import pytest

from domains.meeting.agenda_engine import ValidAgendaItem
from domains.meeting.memory import runtime as memory_runtime
from domains.meeting.memory.bind import BindResult
from domains.meeting.memory.extract import (
    extract_agenda_meeting_fact,
    extract_meeting_fact,
)
from domains.meeting.memory.inject import _relevance
from domains.meeting.memory.runtime import META_KEY, encode_meta


def _item(seq: str, title: str, presenters: list[str]) -> ValidAgendaItem:
    return ValidAgendaItem(seq=seq, title=title, presenters=list(presenters))


def test_extract_agenda_meeting_fact_topics_and_anchors() -> None:
    fact = extract_agenda_meeting_fact(
        [
            _item("01", "网关鉴权方案评审", ["张三"]),
            _item("02", "前端渲染性能优化", ["李四"]),
        ],
        "张三 10:00: 今天评审两个议题",
        request_id="req_agenda_fact",
    )
    assert [t["title"] for t in fact.topics] == [
        "网关鉴权方案评审",
        "前端渲染性能优化",
    ]
    assert "网关鉴权方案评审" in fact.anchors
    assert "前端渲染性能优化" in fact.anchors
    assert "张三" in fact.anchors
    assert "李四" in fact.anchors
    assert fact.summary.startswith("议题：")
    assert fact.decisions == []
    assert fact.open_items == []
    assert fact.risks == []
    assert fact.action_items == []


def test_agenda_fact_improves_relevance() -> None:
    transcript = "张三 10:00: 今天评审网关鉴权与前端渲染"
    empty_fact = extract_meeting_fact({}, transcript)
    agenda_fact = extract_agenda_meeting_fact(
        [_item("01", "网关鉴权方案评审", ["张三"])],
        transcript,
    )
    related = {"text": "网关鉴权方案A落地情况"}
    unrelated = {"text": "办公室搬迁安排"}
    assert _relevance(related, agenda_fact) > 0
    assert _relevance(related, agenda_fact) > _relevance(related, empty_fact)
    assert _relevance(unrelated, agenda_fact) == 0


def _install_memory_stubs(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: list[str] = []
    old_fact = extract_meeting_fact(
        {"meeting_purpose": "旧事实"},
        "张三 10:00: 讨论常规事项",
    )
    agenda_fact = extract_agenda_meeting_fact(
        [_item("01", "网关鉴权方案评审", ["张三"])],
        "张三 10:00: 讨论常规事项",
    )
    captured: dict = {
        "calls": calls,
        "old_fact": old_fact,
        "agenda_fact": agenda_fact,
    }

    def fake_old(*args, **kwargs):
        calls.append("old")
        return old_fact

    def fake_agenda(*args, **kwargs):
        calls.append("agenda")
        return agenda_fact

    monkeypatch.setattr(memory_runtime, "extract_meeting_fact", fake_old)
    monkeypatch.setattr(memory_runtime, "extract_agenda_meeting_fact", fake_agenda)
    monkeypatch.setattr(
        memory_runtime, "load_registry", lambda *a, **k: {"projects": {}}
    )
    monkeypatch.setattr(memory_runtime, "list_meetings", lambda *a, **k: [])
    monkeypatch.setattr(
        memory_runtime,
        "resolve_bind",
        lambda *a, **k: BindResult(
            project_id="p_test",
            mode="explicit",
            confidence="high",
            core_name="P",
        ),
    )
    monkeypatch.setattr(
        memory_runtime, "_project_entry", lambda *a, **k: {"name": "P"}
    )
    monkeypatch.setattr(
        memory_runtime,
        "load_state",
        lambda *a, **k: {
            "actions": [],
            "open_items": [],
            "risks": [],
            "decisions": [],
        },
    )
    monkeypatch.setattr(
        memory_runtime,
        "backfill_meeting_titles",
        lambda state, meetings: state,
    )

    def fake_context(**kwargs):
        captured["fact"] = kwargs.get("current_fact")
        return "ctx", []

    monkeypatch.setattr(memory_runtime, "build_memory_context", fake_context)
    return captured


def _meta() -> dict[str, str]:
    return {
        META_KEY: encode_meta(
            Path("."),
            "u_test_agenda_memory",
            request_id="req_agenda_memory",
        )
    }


def test_build_line_extra_uses_agenda_fact_only_for_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_memory_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "has_valid_agenda": True,
        "valid_agendas": [_item("01", "网关鉴权方案评审", ["张三"])],
        "user": {},
    }

    result = memory_runtime.build_line_extra(
        state, "minutes", line_extra=_meta()
    )
    assert captured["calls"] == ["agenda"]
    assert captured["fact"] is captured["agenda_fact"]
    assert captured["fact"].topics[0]["title"] == "网关鉴权方案评审"
    assert result.context == "ctx"


def test_build_line_extra_keeps_old_fact_for_minutes_styles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_memory_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {},
        "has_valid_agenda": True,
        "valid_agendas": [_item("01", "网关鉴权方案评审", ["张三"])],
        "user": {},
    }

    memory_runtime.build_line_extra(state, "minutes_styles", line_extra=_meta())
    assert captured["calls"] == ["old"]
    assert captured["fact"] is captured["old_fact"]


def test_build_line_extra_keeps_old_fact_for_normal_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_memory_stubs(monkeypatch)
    state = {
        "transcript": "张三 10:00: 讨论常规事项",
        "meeting_understanding": {"meeting_purpose": "旧事实"},
        "has_valid_agenda": False,
        "valid_agendas": [],
        "user": {},
    }

    memory_runtime.build_line_extra(state, "minutes", line_extra=_meta())
    assert captured["calls"] == ["old"]
    assert captured["fact"] is captured["old_fact"]
