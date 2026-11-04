"""会议理解 debates 字段下线回归：模型、契约、空结构、包、prompt 都不再出现。"""
from __future__ import annotations

from dataclasses import fields

from domains.meeting.meeting_core.contracts import (
    ALL_CORE_FIELD_NAMES,
    build_core_contract_for_tasks,
)
from domains.meeting.meeting_core.prompts import (
    MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
    build_understanding_prompt,
)
from domains.meeting.meeting_core.understanding_profiles import TASK_PROFILES
from domains.meeting.models import MeetingUnderstanding
from domains.meeting.orchestrator import _EMPTY_MEETING_UNDERSTANDING, _Nodes
from domains.meeting.tasks.consensus_decision.prompts import (
    CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT,
)
from domains.meeting.tasks.minutes.prompts import MINUTES_GENERATION_SYSTEM_PROMPT


def test_meeting_understanding_has_no_debates_field() -> None:
    names = {f.name for f in fields(MeetingUnderstanding)}

    assert "debates" not in names
    assert "debates" not in ALL_CORE_FIELD_NAMES


def test_minutes_contract_has_no_debates_field() -> None:
    contract, omitted = build_core_contract_for_tasks(["minutes"])

    assert '"debates"' not in contract
    assert "debates" not in omitted


def test_empty_understanding_has_no_debates_key() -> None:
    assert "debates" not in _EMPTY_MEETING_UNDERSTANDING


def test_meeting_pack_has_no_debates_key() -> None:
    state = {
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "open_questions": [],
            "risks": [],
            # 旧数据兼容：多出的 debates 键应被忽略
            "debates": [{"speaker": "张三", "stance": "先压测"}],
        }
    }

    for line in ("minutes", "consensus_decision"):
        pack = _Nodes._meeting_pack(object(), state, line)
        assert "debates" not in pack, line


def test_understanding_prompts_have_no_debates_field() -> None:
    prompts = (
        build_understanding_prompt(TASK_PROFILES["minutes"], task="minutes"),
        MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
    )
    for prompt in prompts:
        assert "debates" not in prompt
        assert "context_and_reasoning" in prompt


def test_consumer_prompts_have_no_debates_field() -> None:
    assert "debates" not in MINUTES_GENERATION_SYSTEM_PROMPT
    assert "context_and_reasoning" in MINUTES_GENERATION_SYSTEM_PROMPT

    assert "debates" not in CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT
    assert "session_segments" in CONSENSUS_DECISION_GENERATION_SYSTEM_PROMPT
