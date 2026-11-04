"""tests/unit/meeting/test_minutes_topic_major_supervisor.py -- topic_major 审核接线。"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from domains.meeting.models import MinutesSupervisorReview
from domains.meeting.orchestrator import MeetingAgentSystem, _Nodes
from domains.meeting.tasks.minutes.steps.minutes_supervisor import (
    MinutesGenerationSupervisor,
)


def _review_payload() -> dict:
    return {
        "decision": "approve",
        "feedback": [],
        "facts_check": {"status": "pass", "findings": []},
        "perspective_check": {"status": "pass", "findings": []},
        "consistency_check": {"status": "pass", "findings": []},
    }


class _CapturingClient:
    def __init__(self) -> None:
        self.system = ""
        self.user = ""
        self.label = ""

    async def structured(self, system, user, model, contract, **kwargs):
        self.system = system
        self.user = user
        self.label = str(kwargs.get("label") or "")
        return model.validate(_review_payload())


def test_supervisor_selects_topic_major_scope_and_label() -> None:
    client = _CapturingClient()
    supervisor = MinutesGenerationSupervisor(client)

    result = asyncio.run(
        supervisor.review(
            "议题模式：agenda_enhanced\n\n会议纪要草稿：\n{}",
            view="agenda_objective",
            layout="topic_major",
        )
    )

    assert isinstance(result, MinutesSupervisorReview)
    assert "议题主序模式审查范围" in client.system
    assert "审定议题模式审查范围" not in client.system
    assert client.label == "minutes/supervisor/agenda_topic"


def test_supervisor_column_major_scope_unchanged() -> None:
    client = _CapturingClient()
    supervisor = MinutesGenerationSupervisor(client)

    asyncio.run(
        supervisor.review(
            "议题模式：agenda_enhanced\n\n会议纪要草稿：\n{}",
            view="agenda_objective",
        )
    )

    assert "审定议题模式审查范围" in client.system
    assert "议题主序模式审查范围" not in client.system
    assert client.label == "minutes/supervisor/agenda"


class _SupervisorStub:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def review(self, context: str, *, view: str, layout: str) -> dict:
        self.calls.append({"context": context, "view": view, "layout": layout})
        return _review_payload()


def _supervisor_system(supervisor: _SupervisorStub) -> MeetingAgentSystem:
    system = object.__new__(MeetingAgentSystem)
    system._task_lines = {
        "minutes": {
            "supervisor_attr": "minutes_supervisor",
            "reject_review": {
                "facts_check": {"status": "fail", "findings": ["x"]},
                "perspective_check": {"status": "fail", "findings": ["x"]},
                "consistency_check": {"status": "fail", "findings": ["x"]},
            },
        }
    }
    system._line_cn_names = {"minutes": "纪要"}
    system._supervisor_fast_path_chars = 2000
    system._supervisor_guardrail_range = (2000, 5000)
    system.minutes_supervisor = supervisor
    return system


def _topic_state(*, transcript: str = "短会：讨论接口联调。") -> dict:
    return {
        "transcript": transcript,
        "tagged_transcript": (
            "【现场审定的有效议题清单】：\n"
            "1. 议题：接口联调（汇报人：张三）\n\n"
            "════════════════════════════════════════\n"
            "【议题 01：接口联调】\n"
            "张三 10:00: 讨论接口联调"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [
            SimpleNamespace(title="接口联调", presenters=["张三"])
        ],
        "user": {"perspective": "objective"},
        "objective_perspective": True,
        "meeting_understanding": {},
        "perspective_profile": {},
        "line_extra": {},
        "templates": {},
        "lang": "zh",
        "line_views": {"minutes": "agenda_objective"},
        "line_layouts": {"minutes": "topic_major"},
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "团队例会纪要",
                    "overview": "本次例会围绕接口联调展开。",
                    "topics": [
                        {
                            "topic_name": "接口联调",
                            "topic_summary": ["方案已确认"],
                            "decisions": ["按 B 方案执行"],
                            "actions": ["张三周五前完成联调报告"],
                            "risks": ["依赖外部团队"],
                            "open_questions": ["上线时间待确认"],
                        }
                    ],
                    "history_comparison": [],
                },
                "revision_feedback": [],
                "revision_count": 0,
            }
        },
    }


def test_supervisor_node_injects_layout_and_disables_fast_path() -> None:
    supervisor = _SupervisorStub()
    out = asyncio.run(
        _supervisor_system(supervisor)._make_supervisor_node("minutes")(
            _topic_state()
        )
    )

    assert len(supervisor.calls) == 1
    assert supervisor.calls[0]["view"] == "agenda_objective"
    assert supervisor.calls[0]["layout"] == "topic_major"
    assert "review_bypassed" not in out["lines"]["minutes"]


def test_supervisor_context_keeps_topic_draft_fields() -> None:
    context = _Nodes()._supervisor_context(_topic_state(), "minutes")

    assert "topic_summary" in context
    assert "open_questions" in context
    assert "接口联调" in context
    assert "【现场审定的有效议题清单】" in context
    assert "【议题 01：接口联调】" in context
