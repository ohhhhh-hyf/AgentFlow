# 拆分自原大文件，保留：test_resolve_profile_mode, test_resolve_minutes_view_matrix, test_personal_agenda_400…

"""议题纪要 v1 边界：personal×agenda 拒绝、agenda 去个人化、记忆迁移止血。"""

from __future__ import annotations
import asyncio
import json
from pathlib import Path
import pytest
from app.schemas import TaskRequest
from app.tasks import ApiError, _prepare
from core.execution.hard_execution import (
    enforce_minutes_draft,
    is_agenda_enhanced_mode,
)
from core.runner.profiles import resolve_profile_mode
from domains.meeting.agenda_engine import ValidAgendaItem
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.agenda_minutes.alignment_engine import DiscussionBlock
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
)
from domains.meeting.views import (
    AgendaPersonalUnsupported,
    VIEW_AGENDA_OBJECTIVE,
    resolve_minutes_view,
)

pytestmark = pytest.mark.integration

def _agenda_item() -> ValidAgendaItem:
    return ValidAgendaItem(
        seq="1",
        title="自研芯片二期量产",
        presenters=["张三"],
        start_index=0,
        end_index=1,
        matched_blocks=[
            DiscussionBlock(
                speaker="张三", timestamp="10:00", content="芯片良率达标", index=0
            )
        ],
    )

def _agenda_state(*, user: dict, objective_perspective: bool = False) -> dict:
    item = _agenda_item()
    return {
        "transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%",
        "tagged_transcript": (
            "【现场审定的有效议题清单】：\n"
            "1. 议题：自研芯片二期量产（汇报人：张三）\n\n"
            "════════════════════════════════════════\n"
            "【议题 01：自研芯片二期量产】\n"
            "张三 10:00: 芯片良率达标"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [item],
        "user": user,
        "objective_perspective": objective_perspective,
        "meeting_understanding": {},
        "perspective_profile": {"personal_summary": "本人负责芯片量产"},
        "user_hits_block": "【本用户命中】\n- 张三：芯片良率",
        "user_radar_block": "【重点关注雷达】\n- 张三",
        "line_extra": {
            "agenda_text": "1. 自研芯片二期量产 汇报人：张三",
            "minutes_auxiliary": "【用户核心关键点】\n良率91.5%",
        },
        "templates": {"minutes": "# 通用纪要\n## [全文摘要]\n[占位]"},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "",
                    "executive_summary": [],
                    "key_decisions": [],
                    "personally_relevant_points": [],
                    "risks_and_blockers": [],
                    "unresolved_questions": [],
                    "history_comparison": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }

def _normal_personal_state() -> dict:
    return {
        "transcript": "张三 10:00: 讨论常规事项",
        "user": {"name": "张三"},
        "objective_perspective": False,
        "has_valid_agenda": False,
        "meeting_understanding": {
            "meeting_brief": "常规简报",
            "meeting_purpose": "同步进展",
            "session_segments": [
                {
                    "segment_title": "进展同步",
                    "context_and_reasoning": "张三同步进展",
                    "key_facts": ["完成联调"],
                }
            ],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "perspective_profile": {"personal_summary": "本人负责联调"},
        "user_hits_block": "【本用户命中】\n- 张三：联调",
        "user_radar_block": "【重点关注雷达】\n- 张三",
        "line_extra": {},
        "templates": {"minutes": "# 个人视角纪要\n## [会议概况]\n[占位]"},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "",
                    "executive_summary": [],
                    "key_decisions": [],
                    "personally_relevant_points": [],
                    "risks_and_blockers": [],
                    "unresolved_questions": [],
                    "history_comparison": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }

def _prepare_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三", encoding="utf-8")
    user_path = tmp_path / "user.json"
    user_path.write_text(json.dumps({"name": "张三"}), encoding="utf-8")

    root = Path(__file__).resolve().parents[4]
    developer_path = root / "resources" / "profiles" / "developer.json"
    object_path = root / "resources" / "profiles" / "object.json"

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)

    def fake_profile_file(domain: str, profile_value: str, user_id: str = "") -> Path:
        value = (profile_value or "").strip().lower()
        if value == "user":
            return user_path
        if value == "developer":
            return developer_path
        return object_path

    monkeypatch.setattr("app.tasks._profile_file", fake_profile_file)

def _minutes_req(profile: str) -> TaskRequest:
    return TaskRequest(
        texts={"transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%"},
        docs=["agenda.txt"],
        extra={"profile": profile},
    )

def test_resolve_profile_mode() -> None:
    assert resolve_profile_mode({}) == "objective"
    assert resolve_profile_mode({"perspective": "objective"}) == "objective"
    assert resolve_profile_mode({"name": "张三"}) == "personal"
    assert (
        resolve_profile_mode(
            {"name": "开发人员", "persona_type": "role_template"}
        )
        == "role_template"
    )


def test_resolve_minutes_view_matrix() -> None:
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="personal")
        == "personal"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="objective")
        == "objective"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=False, profile_mode="role_template")
        == "role_template"
    )
    assert (
        resolve_minutes_view(has_valid_agenda=True, profile_mode="objective")
        == VIEW_AGENDA_OBJECTIVE
    )
    assert (
        resolve_minutes_view(has_valid_agenda=True, profile_mode="role_template")
        == VIEW_AGENDA_OBJECTIVE
    )
    with pytest.raises(AgendaPersonalUnsupported):
        resolve_minutes_view(has_valid_agenda=True, profile_mode="personal")


def test_personal_agenda_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    with pytest.raises(ApiError) as exc:
        _prepare("meeting", "minutes", _minutes_req("user"), "u_test_personal")
    assert exc.value.status == 400
    assert "个人视角暂不支持议题增强模式" in exc.value.message


def test_role_template_agenda_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    prep = _prepare("meeting", "minutes", _minutes_req("developer"), "u_test_role")
    assert prep.minutes_view == VIEW_AGENDA_OBJECTIVE
    assert prep.prepare_warning
    assert prep.profile_file.name == "object.json"
    text = prep.templates["minutes"].read_text(encoding="utf-8")
    assert "以现场审定的有效议题清单为主线展开" in text


def test_prepare_objective_agenda_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_fixture(tmp_path, monkeypatch)
    prep = _prepare("meeting", "minutes", _minutes_req(""), "u_test_objective")
    assert prep.minutes_view == VIEW_AGENDA_OBJECTIVE
    assert prep.prepare_warning == ""
    text = prep.templates["minutes"].read_text(encoding="utf-8")
    assert "以现场审定的有效议题清单为主线展开" in text


def test_prepare_run_rejects_personal_agenda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import _runner_args
    from core.runner.runner import prepare_run

    _prepare_fixture(tmp_path, monkeypatch)
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 讨论常规事项"},
        extra={"profile": "user"},
    )
    p = _prepare("meeting", "minutes", req, "u_test_run_personal")
    p.extra_line_inputs["agenda_text"] = "1. 自研芯片二期量产 汇报人：张三"
    with pytest.raises(ValueError, match="个人视角暂不支持议题增强模式"):
        asyncio.run(prepare_run(p.ctx, **_runner_args(p)))


def test_prepare_run_forces_role_template_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import _runner_args
    from core.runner.runner import prepare_run

    _prepare_fixture(tmp_path, monkeypatch)
    req = TaskRequest(
        texts={"transcript": "张三 10:00: 讨论常规事项"},
        extra={"profile": "developer"},
    )
    p = _prepare("meeting", "minutes", req, "u_test_run_role")
    p.extra_line_inputs["agenda_text"] = "1. 自研芯片二期量产 汇报人：张三"
    prep = asyncio.run(prepare_run(p.ctx, **_runner_args(p)))
    user_data = (
        prep.user.model_dump()
        if hasattr(prep.user, "model_dump")
        else dict(prep.user)
    )
    assert user_data["perspective"] == "objective"


def test_stream_personal_agenda_returns_error_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.tasks import iter_task_events

    _prepare_fixture(tmp_path, monkeypatch)

    async def _collect():
        return [
            event
            async for event in iter_task_events(
                "meeting",
                "minutes",
                _minutes_req("user"),
                user_id="u_test_stream_personal",
                request_id="req_test_stream_personal",
            )
        ]

    events = asyncio.run(_collect())
    assert events
    assert events[0]["type"] == "error"
    assert events[0]["code"] == 400
    assert "个人视角暂不支持议题增强模式" in events[0]["message"]
