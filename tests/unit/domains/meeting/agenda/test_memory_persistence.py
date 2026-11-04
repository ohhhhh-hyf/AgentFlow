"""Step 5：议题纪要持久化事实。只对单线 agenda 生效，普通纪要零影响。"""
from __future__ import annotations

from pathlib import Path

import pytest

from domains.meeting.agenda_engine import ValidAgendaItem
from domains.meeting.memory import runtime as memory_runtime
from domains.meeting.memory.bind import BindResult
from domains.meeting.memory.extract import (
    MeetingFact,
    extract_meeting_fact_from_minutes_draft,
)
from domains.meeting.orchestrator import _Nodes

_EMPTY_UNDERSTANDING = {
    "meeting_brief": "",
    "meeting_purpose": "",
    "speakers": [],
    "session_segments": [],
    "topics": [],
    "decisions": [],
    "open_questions": [],
    "risks": [],
    "action_hints": [],
    "risk_hints": [],
    "dependencies": [],
}


def _fact(title: str, **fields) -> MeetingFact:
    fact = MeetingFact(meeting_id="m_test", time="")
    fact.title = title
    for key, value in fields.items():
        setattr(fact, key, value)
    return fact


def test_extract_fact_from_minutes_draft_mapping() -> None:
    draft = {
        "headline": "芯片评审纪要",
        "executive_summary": [
            "全场概览：本次评审两个议题。",
            "### 一. 网关鉴权方案评审\n- 方案A通过",
            "### 二. 前端渲染性能优化\n- 首屏 0.8s",
        ],
        "key_decisions": ["网关鉴权采用方案A"],
        "personally_relevant_points": ["张三下周三前完成回滚演练"],
        "risks_and_blockers": ["虚拟列表低端机兼容风险"],
        "unresolved_questions": ["灰度脚本未在预发验证"],
        "history_comparison": [],
    }
    fact = extract_meeting_fact_from_minutes_draft(
        draft,
        transcript="张三：网关鉴权采用方案A，前端首屏 0.8s",
        request_id="req_draft_fact",
    )
    assert fact.title == "芯片评审纪要"
    assert fact.summary == "全场概览：本次评审两个议题。"
    assert fact.decisions == ["网关鉴权采用方案A"]
    assert fact.open_items == ["灰度脚本未在预发验证"]
    assert fact.risks == ["虚拟列表低端机兼容风险"]
    assert [a["text"] for a in fact.action_items] == [
        "张三下周三前完成回滚演练"
    ]
    assert [t["title"] for t in fact.topics] == [
        "网关鉴权方案评审",
        "前端渲染性能优化",
    ]
    assert "芯片评审纪要" in fact.anchors
    assert fact.time_source == "unknown"


def test_extract_fact_from_minutes_draft_prefers_agenda_titles() -> None:
    draft = {
        "headline": "",
        "executive_summary": ["概览"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    fact = extract_meeting_fact_from_minutes_draft(
        draft,
        agenda_titles=["法定议题一", "法定议题二"],
        transcript="会议原文",
    )
    assert fact.title == "法定议题一"
    assert [t["title"] for t in fact.topics] == ["法定议题一", "法定议题二"]


def test_understanding_has_fact_ignores_empty_structure() -> None:
    assert memory_runtime._understanding_has_fact(_EMPTY_UNDERSTANDING) is False
    assert memory_runtime._understanding_has_fact({"meeting_brief": "有事实"}) is True
    assert memory_runtime._understanding_has_fact({"decisions": ["d"]}) is True
    assert memory_runtime._understanding_has_fact({}) is False


def _install_persist_stubs(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: list[str] = []
    old_fact = _fact("old", decisions=["old_d"])
    draft_fact = _fact(
        "draft",
        decisions=["draft_d"],
        topics=[{"title": "议题一"}],
    )
    captured: dict = {"calls": calls, "old_fact": old_fact, "draft_fact": draft_fact}

    def fake_old(*args, **kwargs):
        calls.append("old")
        return old_fact

    def fake_draft(*args, **kwargs):
        calls.append("draft")
        return draft_fact

    monkeypatch.setattr(memory_runtime, "extract_meeting_fact", fake_old)
    monkeypatch.setattr(
        memory_runtime, "extract_meeting_fact_from_minutes_draft", fake_draft
    )
    monkeypatch.setattr(memory_runtime, "load_registry", lambda *a, **k: {})
    monkeypatch.setattr(memory_runtime, "list_meetings", lambda *a, **k: [])
    monkeypatch.setattr(
        memory_runtime,
        "resolve_bind",
        lambda *a, **k: BindResult(
            project_id="", mode="auto", confidence="low"
        ),
    )

    def fake_append(root, uid, meeting):
        captured["meeting"] = meeting

    monkeypatch.setattr(
        memory_runtime, "append_or_replace_meeting", fake_append
    )
    return captured


def _persist(
    monkeypatch: pytest.MonkeyPatch,
    *,
    understanding: dict,
    drafts: dict | None,
    has_valid_agenda: bool,
    degraded_by_line: dict | None = None,
    agenda_titles: list[str] | None = None,
) -> dict:
    captured = _install_persist_stubs(monkeypatch)
    memory_runtime.persist_after_run(
        Path("."),
        "u_test_agenda_persist",
        "",
        "req_agenda_persist",
        "会议转写原文",
        {"minutes": {"personalized_minutes": "渲染正文"}},
        understanding,
        drafts=drafts,
        degraded_by_line=degraded_by_line or {},
        has_valid_agenda=has_valid_agenda,
        agenda_titles=agenda_titles or [],
    )
    return captured


def test_persist_agenda_uses_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _persist(
        monkeypatch,
        understanding=_EMPTY_UNDERSTANDING,
        drafts={"minutes": {"headline": "草稿标题", "key_decisions": ["d"]}},
        has_valid_agenda=True,
        degraded_by_line={"minutes": False},
    )
    assert captured["calls"] == ["draft"]
    assert captured["meeting"]["decisions"] == ["draft_d"]
    assert captured["meeting"]["rendered_preview"] == "渲染正文"


def test_persist_agenda_with_real_understanding_uses_old_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _persist(
        monkeypatch,
        understanding={"meeting_brief": "有事实"},
        drafts={"minutes": {"headline": "草稿标题", "key_decisions": ["d"]}},
        has_valid_agenda=True,
    )
    assert captured["calls"] == ["old"]
    assert captured["meeting"]["decisions"] == ["old_d"]


def test_persist_normal_minutes_uses_old_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _persist(
        monkeypatch,
        understanding={"meeting_purpose": "普通会议"},
        drafts={"minutes": {"headline": "草稿标题", "key_decisions": ["d"]}},
        has_valid_agenda=False,
    )
    assert captured["calls"] == ["old"]


def test_persist_degraded_agenda_uses_old_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _persist(
        monkeypatch,
        understanding=_EMPTY_UNDERSTANDING,
        drafts={"minutes": {"headline": "草稿标题", "key_decisions": ["d"]}},
        has_valid_agenda=True,
        degraded_by_line={"minutes": True},
    )
    assert captured["calls"] == ["old"]


def test_persist_empty_draft_uses_old_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _persist(
        monkeypatch,
        understanding=_EMPTY_UNDERSTANDING,
        drafts={"minutes": {}},
        has_valid_agenda=True,
    )
    assert captured["calls"] == ["old"]


def test_agenda_draft_persisted_and_visible_next_session(tmp_path: Path) -> None:
    from domains.meeting.memory.runtime import (
        META_KEY,
        build_line_extra,
        encode_meta,
    )
    from domains.meeting.memory.store import load_state

    project_root = tmp_path
    user_id = "u_agenda_persist_e2e"
    project_id = "proj_agenda_persist_e2e"
    draft = {
        "headline": "网关与前端评审会",
        "executive_summary": [
            "本次评审两个议题。",
            "### 一. 网关鉴权方案评审\n- 方案A通过",
            "### 二. 前端渲染性能优化\n- 首屏 0.8s",
        ],
        "key_decisions": ["网关鉴权采用方案A"],
        "personally_relevant_points": ["张三下周三前完成回滚演练"],
        "risks_and_blockers": ["虚拟列表低端机兼容风险"],
        "unresolved_questions": ["灰度脚本未在预发验证"],
        "history_comparison": [],
    }
    memory_runtime.persist_after_run(
        project_root,
        user_id,
        project_id,
        "req_s1",
        "张三：网关鉴权采用方案A，前端首屏 0.8s",
        {"minutes": {"headline": "网关与前端评审会"}},
        _EMPTY_UNDERSTANDING,
        meeting_time="2026-10-26",
        drafts={"minutes": draft},
        degraded_by_line={"minutes": False},
        has_valid_agenda=True,
        agenda_titles=["网关鉴权方案评审", "前端渲染性能优化"],
    )

    state = load_state(project_root, user_id, project_id)
    assert "网关鉴权采用方案A" in [
        d.get("text") for d in state.get("decisions") or []
    ]
    assert "张三下周三前完成回滚演练" in [
        a.get("text") for a in state.get("actions") or []
    ]
    assert "虚拟列表低端机兼容风险" in [
        r.get("text") for r in state.get("risks") or []
    ]

    # 第二场：议程注入应能看到上一场写回的待办
    meta = encode_meta(
        project_root,
        user_id,
        project=project_id,
        request_id="req_s2",
        meeting_time="2026-11-02",
    )
    next_state = {
        "transcript": "下一场会议原文",
        "meeting_understanding": _EMPTY_UNDERSTANDING,
        "has_valid_agenda": True,
        "valid_agendas": [
            ValidAgendaItem(
                seq="01", title="网关鉴权方案评审", presenters=["张三"]
            )
        ],
        "user": {},
    }
    injected = build_line_extra(
        next_state, "minutes", line_extra={META_KEY: meta}
    )
    assert "张三下周三前完成回滚演练" in injected.context


def test_memory_done_context_only_for_minutes() -> None:
    nodes = _Nodes()
    state = {
        "lines": {
            "minutes": {
                "draft": {"headline": "草稿标题"},
                "degraded": False,
            }
        },
        "has_valid_agenda": True,
        "valid_agendas": [
            ValidAgendaItem(
                seq="01", title="网关鉴权方案评审", presenters=["张三"]
            )
        ],
    }
    context = nodes._memory_done_context(state, ["minutes"])
    assert context["drafts"]["minutes"]["headline"] == "草稿标题"
    assert context["degraded_by_line"]["minutes"] is False
    assert context["has_valid_agenda"] is True
    assert context["agenda_titles"] == ["网关鉴权方案评审"]

    assert nodes._memory_done_context(state, ["actions"]) == {}
