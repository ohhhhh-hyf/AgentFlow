"""Step 4：PerspectiveModelingAgent.run_personal() 测试。"""
from __future__ import annotations

import asyncio

from domains.shared.perspective import (
    PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT,
    PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
    PersonalPerspective,
    PerspectiveModelingAgent,
)


def _valid_perspective() -> PersonalPerspective:
    return PersonalPerspective(
        confidence="high",
        personal_summary="负责压测与显存优化。",
        focus_points=["压测"],
        possible_actions=["周五前提交报告"],
        collaborations=["张工：周一下午提供环境"],
        concerns=["显存不足"],
        data_gaps=["缺少 GPU 驱动"],
        focus_risks=["上线窗口风险"],
        open_questions=["确认测试范围"],
    )


def test_run_personal_filters_inputs_and_uses_personal_contract() -> None:
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured.update(
                system=system,
                user=user,
                model=model,
                contract=contract,
                kwargs=kwargs,
            )
            return _valid_perspective()

    understanding = {
        "meeting_brief": "demo 评审会",
        "meeting_purpose": "确认上线窗口",
        "speakers": [{"name": "申家坤"}],
        "session_segments": [{"segment_title": "压测"}],
        "decisions": ["周五上线"],
        "open_questions": ["测试范围"],
        "risks": ["显存不足"],
        "action_hints": [{"owner": "申家坤"}],
        "risk_hints": ["显存"],
        "dependencies": ["测试环境"],
        "topics": ["旧字段"],
    }
    profile = {
        "name": "申家坤",
        "name_aliases": ["家坤"],
        "role": "后端工程师",
        "focus_person": ["张工"],
        "focus_thing": ["压测"],
        "preferences": ["先说结论"],
        "department": "平台部",
        "responsibilities": ["压测"],
        "persona_type": "user",
    }
    evidence = "【个人证据包】\n申家坤 00:01\n负责压测。"

    agent = PerspectiveModelingAgent(FakeClient())
    result = asyncio.run(agent.run_personal(understanding, evidence, profile))

    assert result is not None
    assert captured["system"] == PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT
    assert captured["model"] is PersonalPerspective
    assert captured["contract"] == PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT
    assert captured["kwargs"]["label"] == "core/personal_perspective"

    user = captured["user"]
    for field in (
        "meeting_brief",
        "meeting_purpose",
        "speakers",
        "session_segments",
        "decisions",
        "open_questions",
        "risks",
    ):
        assert field in user, field
    for field in ("name", "name_aliases", "role", "focus_person", "focus_thing", "preferences"):
        assert field in user, field
    for forbidden in ("action_hints", "risk_hints", "dependencies", "department", "persona_type", "responsibilities"):
        assert forbidden not in user, forbidden
    assert evidence in user
    assert "【用户画像】" in user
    assert "【会议理解】" in user
    assert "【个人证据包】" in user


def test_old_run_is_unchanged() -> None:
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured.update(system=system, user=user, label=kwargs.get("label"))
            return object()

    agent = PerspectiveModelingAgent(FakeClient())
    asyncio.run(agent.run("输入材料", '{"name": "申家坤"}'))

    assert captured["label"] == "core/perspective_modeling"
    assert "当前输入材料" in captured["user"]
