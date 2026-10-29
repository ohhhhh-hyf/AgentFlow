"""Stage 6：场景识别边界（候选集、二次校验、物化失败、超时、采样）。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.config import resolve_agenda_template_format
from app.schemas import TaskRequest
from app.tasks import _prepare
from core.graph.engine_text import line_template
from domains.meeting.models_generated import MeetingUnderstanding
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.minutes.steps.scene_catalog import (
    AGENDA_CANDIDATE_IDS,
    NORMAL_CANDIDATE_IDS,
    SCENE_CATALOG,
)
from domains.meeting.tasks.minutes.steps.template_classifier import sample_transcript
from domains.meeting.tasks.minutes.steps.template_select import select_minutes_template

LONG_TRANSCRIPT = "会议内容" * 600
NO_AGENDA_IDS = tuple(entry.id for entry in SCENE_CATALOG if not entry.has_agenda)


class FakeClient:
    def __init__(self, response: str = "", exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, str]] = []

    async def text(self, system: str, user: str, **kwargs) -> str:
        self.calls.append((system, user))
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeUnderstandingAgent:
    async def run(self, transcript, **kwargs):
        return MeetingUnderstanding(meeting_brief="测试简报", meeting_purpose="常规讨论")


def _state(**overrides) -> dict:
    state = {
        "transcript": LONG_TRANSCRIPT,
        "templates": {"minutes": "【兜底模板】"},
        "template_auto": True,
        "template_source": "default",
        "template_id": "general_minutes",
        "template_mode": "normal",
        "line_extra": {},
        "lang": "zh",
    }
    state.update(overrides)
    return state


def _select(state: dict, client: FakeClient) -> dict:
    return asyncio.run(select_minutes_template(state, client=client))


# ── 9 个无议程版场景 ────────────────────────────────────────


def test_candidate_sets_partition_no_agenda_scenarios() -> None:
    assert len(NORMAL_CANDIDATE_IDS) == 29
    assert len(AGENDA_CANDIDATE_IDS) == 20
    assert len(NO_AGENDA_IDS) == 9
    assert set(AGENDA_CANDIDATE_IDS).isdisjoint(NO_AGENDA_IDS)
    assert set(NORMAL_CANDIDATE_IDS) == set(AGENDA_CANDIDATE_IDS) | set(NO_AGENDA_IDS)


def test_agenda_mode_rejects_no_agenda_scenarios(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    expected = resolve_agenda_template_format("general_minutes", "zh").strip()
    for template_id in NO_AGENDA_IDS:
        client = FakeClient(json.dumps({"template": template_id, "confidence": 0.95}))
        state = _state(
            template_mode="agenda",
            templates={"minutes": expected},
            line_extra={"agenda_text": "1. 议题：量产 汇报人：张三"},
        )
        out = _select(state, client)
        state.update(out)
        assert "templates" not in out, template_id
        assert state["template_id"] == "general_minutes", template_id
        assert state["template_source"] == "auto_fallback", template_id
        assert out["template_decision"]["reason"] == "not_in_candidates", template_id
        assert out["template_decision"]["template"] == "general_minutes", template_id
        # 回退保留 _prepare 已加载的议程版 general_minutes
        assert line_template(state, "minutes") == expected, template_id


# ── 议程探测与二次校验不一致 ─────────────────────────────────


def test_agenda_secondary_validation_failure_keeps_selected_template(monkeypatch) -> None:
    """_prepare 判有效、pipeline 二次校验无效：沿用已选的议程模板（现有边界）。"""
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    state = _state(
        template_mode="agenda",
        line_extra={"agenda_text": "1. 自研车载芯片二期量产 汇报人：张三"},
    )
    client = FakeClient('{"template":"project_progress","confidence":0.86}')
    state.update(_select(state, client))
    expected = resolve_agenda_template_format("project_progress", "zh").strip()
    assert line_template(state, "minutes") == expected

    # transcript 与议程完全无关 → pipeline 二次校验失败
    state["transcript"] = "李四 10:00: 随便聊聊午饭吃什么。\n" * 200
    nodes = _Nodes()
    nodes.meeting_understanding_agent = FakeUnderstandingAgent()
    result = asyncio.run(nodes._make_meeting_understanding_node(["minutes"])(state))

    assert result["has_valid_agenda"] is False
    assert "templates" not in result
    assert line_template(state, "minutes") == expected
    assert state["template_id"] == "project_progress"
    assert state["template_mode"] == "agenda"


# ── 物化失败 / 文件缺失 ──────────────────────────────────────


def test_missing_template_file_falls_back(monkeypatch, tmp_path) -> None:
    import app.config as app_config

    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    monkeypatch.setattr(app_config, "template_dir", lambda lang="zh": tmp_path)
    client = FakeClient('{"template":"project_progress","confidence":0.86}')
    out = _select(_state(), client)

    assert "templates" not in out
    assert out["template_id"] == "general_minutes"
    assert out["template_source"] == "auto_fallback"
    assert out["template_decision"]["reason"] == "empty_template"
    assert out["template_decision"]["applied"] is False


# ── Agent 超时 ───────────────────────────────────────────────


def test_agent_timeout_falls_back_without_raising(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    client = FakeClient(exc=TimeoutError("timeout"))
    out = _select(_state(), client)

    assert "templates" not in out
    assert out["template_id"] == "general_minutes"
    assert out["template_source"] == "auto_fallback"
    assert out["template_decision"]["reason"] == "error"
    assert out["template_decision"]["applied"] is False


# ── 画像类型 ─────────────────────────────────────────────────


def test_role_template_enters_auto_matching(monkeypatch) -> None:
    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 项目进度讨论"},
        extra={"profile": "developer"},
    )
    prep = _prepare("meeting", "minutes", req, "u_test_role_template")
    assert prep.template_auto is True
    assert prep.template_source == "default"
    assert prep.template_id == "general_minutes"
    assert prep.template_mode == "normal"


def test_personal_profile_never_enters_auto(monkeypatch, tmp_path) -> None:
    import json as _json
    from pathlib import Path

    monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", "on")
    user_path = tmp_path / "user.json"
    user_path.write_text(_json.dumps({"name": "张三"}), encoding="utf-8")
    object_path = Path(__file__).resolve().parents[3] / "resources" / "profiles" / "object.json"
    monkeypatch.setattr(
        "app.tasks._profile_file",
        lambda domain, value, user_id="": user_path
        if (value or "").strip().lower() == "user"
        else object_path,
    )
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 项目进度讨论"},
        extra={"profile": "user"},
    )
    prep = _prepare("meeting", "minutes", req, "u_test_personal_auto")
    assert prep.template_auto is False
    assert prep.template_source == "personal_default"
    assert prep.template_id == "personal_minutes"


# ── 文本切分 ─────────────────────────────────────────────────


def test_sample_head_snaps_to_previous_newline() -> None:
    text = "A" * 25 + "\n" + "B" * 10 + "\n" + "C" * 100
    sampled = sample_transcript(
        text,
        full_limit=50,
        head_chars=30,
        middle_chars=0,
        tail_chars=0,
    )
    assert sampled == "A" * 25
    assert "BBBB" not in sampled
