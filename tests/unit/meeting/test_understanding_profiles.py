"""会议理解四任务 profile：prompt / contract / pack 对齐回归。"""
from __future__ import annotations

import asyncio

from domains.meeting.meeting_core.contracts import build_core_contract_for_tasks
from domains.meeting.meeting_core.meeting_understanding_agent import (
    MeetingUnderstandingAgent,
)
from domains.meeting.meeting_core.prompts import build_understanding_prompt
from domains.meeting.meeting_core.understanding_profiles import (
    FULL_PROFILE,
    TASK_PROFILES,
    resolve_profile,
)
from domains.meeting.models import MeetingUnderstanding
from domains.meeting.orchestrator import _Nodes


def _contract_fields(task: str) -> str:
    contract, _ = build_core_contract_for_tasks([task])
    return contract


def _prompt(task: str) -> str:
    profile = resolve_profile([task])
    assert profile is not None
    return build_understanding_prompt(profile, task=task)


def test_task_profiles_match_four_task_matrix() -> None:
    assert TASK_PROFILES["minutes"].segments == "full"
    assert TASK_PROFILES["minutes"].fields == ("decisions", "open_questions", "risks")

    assert TASK_PROFILES["actions"].segments == "light"
    assert TASK_PROFILES["actions"].fields == ("decisions", "action_hints")

    assert TASK_PROFILES["risks"].segments == "light"
    assert TASK_PROFILES["risks"].fields == ("open_questions", "risks", "risk_hints")

    assert TASK_PROFILES["mindmap"].segments == "full"
    assert TASK_PROFILES["mindmap"].fields == ("decisions", "risks", "open_questions")


def test_memory_profile_is_full() -> None:
    profile = resolve_profile(["minutes"], memory_on=True)

    assert profile == FULL_PROFILE
    assert "dependencies" in profile.fields
    assert "action_hints" in profile.fields
    assert "risk_hints" in profile.fields


def test_agenda_profile_uses_legacy_prompt_branch() -> None:
    assert resolve_profile(["minutes"], is_agenda=True) is None


def test_memory_prompt_contains_all_fields() -> None:
    prompt = build_understanding_prompt(FULL_PROFILE, task="minutes")

    for name in (
        "decisions",
        "open_questions",
        "risks",
        "action_hints",
        "risk_hints",
        "dependencies",
    ):
        assert name in prompt


def test_multi_task_is_union_fallback() -> None:
    profile = resolve_profile(["actions", "risks"])

    assert profile is not None
    assert profile.segments == "light"
    assert set(profile.fields) == {
        "decisions",
        "action_hints",
        "open_questions",
        "risks",
        "risk_hints",
    }


def test_minutes_contract_and_prompt_exclude_hints_and_dependencies() -> None:
    contract = _contract_fields("minutes")
    prompt = _prompt("minutes")

    for name in ("action_hints", "risk_hints", "dependencies"):
        assert f'"{name}"' not in contract
        assert name not in prompt

    for name in ("decisions", "open_questions", "risks"):
        assert f'"{name}"' in contract
        assert name in prompt

    assert "context_and_reasoning" in contract
    assert "context_and_reasoning" in prompt


def test_actions_contract_and_prompt_only_use_action_hints() -> None:
    contract = _contract_fields("actions")
    prompt = _prompt("actions")

    assert '"action_hints"' in contract
    assert "action_hints" in prompt
    for name in ("risk_hints", "open_questions", "risks", "dependencies"):
        assert f'"{name}"' not in contract
        assert name not in prompt

    assert "context_and_reasoning" not in contract
    assert "context_and_reasoning" not in prompt


def test_risks_contract_and_prompt_only_use_risk_hints() -> None:
    contract = _contract_fields("risks")
    prompt = _prompt("risks")

    assert '"risk_hints"' in contract
    assert "risk_hints" in prompt
    for name in ("action_hints", "decisions", "dependencies"):
        assert f'"{name}"' not in contract
        assert name not in prompt

    assert "context_and_reasoning" not in contract
    assert "context_and_reasoning" not in prompt


def test_mindmap_contract_and_prompt_include_risks_and_open_questions() -> None:
    contract = _contract_fields("mindmap")
    prompt = _prompt("mindmap")

    for name in ("decisions", "risks", "open_questions"):
        assert f'"{name}"' in contract
        assert name in prompt

    for name in ("action_hints", "risk_hints", "dependencies"):
        assert f'"{name}"' not in contract
        assert name not in prompt

    assert "context_and_reasoning" in contract
    assert "context_and_reasoning" in prompt


def test_meeting_pack_matches_four_task_profiles() -> None:
    state = {
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "open_questions": [],
            "risks": [],
            "action_hints": [],
            "risk_hints": [],
            "dependencies": [],
        }
    }

    minutes = _Nodes._meeting_pack(object(), state, "minutes")
    assert "action_hints" not in minutes
    assert "risk_hints" not in minutes
    assert "dependencies" not in minutes

    actions = _Nodes._meeting_pack(object(), state, "actions")
    assert "action_hints" in actions
    assert "dependencies" not in actions
    assert "risk_hints" not in actions

    risks = _Nodes._meeting_pack(object(), state, "risks")
    assert "risk_hints" in risks
    assert "dependencies" not in risks
    assert "action_hints" not in risks

    mindmap = _Nodes._meeting_pack(object(), state, "mindmap")
    assert "decisions" in mindmap
    assert "risks" in mindmap
    assert "open_questions" in mindmap
    assert "action_hints" not in mindmap
    assert "risk_hints" not in mindmap
    assert "dependencies" not in mindmap


def test_risks_pack_keeps_dependencies_only_when_present() -> None:
    state = {
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "open_questions": [],
            "risks": [],
            "action_hints": [],
            "risk_hints": [],
            "dependencies": ["等安全团队确认后才能上线"],
        }
    }

    risks = _Nodes._meeting_pack(object(), state, "risks")
    assert risks["dependencies"] == ["等安全团队确认后才能上线"]
    assert "dependencies" not in _Nodes._meeting_pack(object(), state, "actions")


def test_agent_uses_dynamic_prompt_and_contract() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.prompt = ""
            self.contract = ""

        async def structured(self, prompt, user, model, contract, **kwargs):
            self.prompt = prompt
            self.contract = contract
            return MeetingUnderstanding(meeting_brief="b", meeting_purpose="p")

    for task in ("minutes", "actions", "risks", "mindmap"):
        client = FakeClient()
        agent = MeetingUnderstandingAgent(client)  # type: ignore[arg-type]
        asyncio.run(agent.run("会议原文", active_tasks=[task]))

        assert client.contract == _contract_fields(task)
        assert client.prompt == _prompt(task)
