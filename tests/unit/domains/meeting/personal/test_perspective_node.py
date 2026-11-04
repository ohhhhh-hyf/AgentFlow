"""Step 5：个人单线视角编排节点测试。"""
from __future__ import annotations

import asyncio

from domains.meeting.orchestrator import _Nodes
from domains.shared.perspective import (
    EMPTY_PERSONAL_PERSPECTIVE,
    PersonalPerspective,
)


class _Host(_Nodes):
    """只借 _Nodes 的方法；不跑父类 __init__。"""

    def __init__(self, agent) -> None:
        self.perspective_modeling_agent = agent

    def _understanding(self, state):
        return state.get("meeting_understanding") or {}


def _personal_result() -> PersonalPerspective:
    return PersonalPerspective(
        confidence="high",
        personal_summary="负责压测。",
        focus_points=["压测"],
        possible_actions=["周五前提交报告"],
        collaborations=["张工：提供环境"],
        concerns=["显存不足"],
        data_gaps=["缺少驱动"],
        focus_risks=["上线窗口"],
        open_questions=["确认范围"],
    )


def test_personal_single_line_uses_run_personal_only() -> None:
    captured: dict = {}

    class FakeAgent:
        async def run_personal(self, understanding, evidence, profile):
            captured.update(
                understanding=understanding,
                evidence=evidence,
                profile=profile,
            )
            return _personal_result()

        async def run(self, *args, **kwargs):
            raise AssertionError("personal 单线不应调用旧 run")

    state = {
        "user": {
            "name": "申家坤",
            "name_aliases": ["家坤"],
            "role": "后端工程师",
            "focus_person": ["张工"],
            "focus_thing": ["压测"],
            "preferences": ["先说结论"],
            "department": "平台部",
        },
        "meeting_understanding": {
            "meeting_brief": "demo 评审",
            "meeting_purpose": "确认上线",
            "speakers": [{"name": "申家坤"}],
            "session_segments": [{"segment_title": "压测"}],
            "decisions": ["周五上线"],
            "open_questions": ["测试范围"],
            "risks": ["显存不足"],
            "action_hints": [{"owner": "申家坤"}],
            "dependencies": ["测试环境"],
        },
        "transcript": "申家坤 00:01\n负责压测。",
        "objective_perspective": False,
        "has_valid_agenda": False,
    }

    result = asyncio.run(_Host(FakeAgent())._make_perspective_node(["minutes"])(state))

    assert set(result) == {"personal_perspective"}
    assert result["personal_perspective"]["confidence"] == "high"
    assert set(captured["understanding"]) == {
        "meeting_brief",
        "meeting_purpose",
        "speakers",
        "session_segments",
        "decisions",
        "open_questions",
        "risks",
    }
    assert set(captured["profile"]) == {
        "name",
        "name_aliases",
        "role",
        "focus_person",
        "focus_thing",
        "preferences",
    }
    assert "【个人证据包】" in captured["evidence"]
    assert "负责压测" in captured["evidence"]


def test_personal_failure_degrades_to_empty_model() -> None:
    class FakeAgent:
        async def run_personal(self, *args, **kwargs):
            raise RuntimeError("boom")

        async def run(self, *args, **kwargs):
            raise AssertionError("不应调用旧 run")

    state = {
        "user": {"name": "申家坤", "name_aliases": []},
        "meeting_understanding": {"meeting_brief": "demo"},
        "transcript": "申家坤 00:01\n负责压测。",
        "objective_perspective": False,
        "has_valid_agenda": False,
    }
    result = asyncio.run(_Host(FakeAgent())._make_perspective_node(["minutes"])(state))

    assert result["personal_perspective"] == EMPTY_PERSONAL_PERSPECTIVE
    assert result["quality_degraded"] is True


def test_multi_line_does_not_use_personal_branch() -> None:
    class FakeAgent:
        async def run_personal(self, *args, **kwargs):
            raise AssertionError("多线不应进入个人单线分支")

        async def run(self, *args, **kwargs):
            class _Out:
                def model_dump(self):
                    return {"confidence": "high", "name": "申家坤"}

            return _Out()

    state = {
        "user": {"name": "申家坤", "name_aliases": []},
        "meeting_understanding": {"meeting_brief": "demo"},
        "transcript": "申家坤 00:01\n负责压测。",
        "objective_perspective": False,
        "has_valid_agenda": False,
    }
    result = asyncio.run(
        _Host(FakeAgent())._make_perspective_node(["minutes", "actions"])(state)
    )
    assert "personal_perspective" not in result
    assert "perspective_profile" in result
