"""Step 2：PersonalPerspective 模型、契约、Prompt 的冻结测试。"""
from __future__ import annotations

import pytest

from core.schema.validation import OutputValidationError
from domains.shared.perspective import (
    EMPTY_PERSONAL_PERSPECTIVE,
    PERSONAL_PERSPECTIVE_FIELDS,
    PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT,
    PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT,
    PERSONAL_PERSPECTIVE_PROMPT_VERSION,
    PersonalPerspective,
    PersonalPerspectiveGenerationContract,
)

_VALID = {
    "confidence": "high",
    "personal_summary": "负责压测与显存优化，需要周五前给出报告。",
    "focus_points": ["demo 落地与压测", "显存 ≤4.5GB"],
    "possible_actions": ["周四 18:00 前输出压测报告"],
    "collaborations": ["张工：周一下午提供测试环境"],
    "concerns": ["显存不足可能影响单卡并发"],
    "data_gaps": ["缺少测试环境 GPU 驱动版本"],
    "focus_risks": ["重点人物关注上线窗口"],
    "open_questions": ["与徐玥确认沙箱测试范围"],
}


def test_personal_perspective_validates_exactly_nine_fields() -> None:
    model = PersonalPerspective.validate(_VALID)
    assert model.confidence == "high"
    assert model.personal_summary == _VALID["personal_summary"]
    assert model.collaborations == _VALID["collaborations"]
    assert model.focus_risks == _VALID["focus_risks"]
    assert tuple(EMPTY_PERSONAL_PERSPECTIVE) == PERSONAL_PERSPECTIVE_FIELDS
    assert len(EMPTY_PERSONAL_PERSPECTIVE) == 9


def test_personal_perspective_rejects_missing_unknown_and_wrong_types() -> None:
    missing = dict(_VALID)
    del missing["focus_risks"]
    with pytest.raises(OutputValidationError):
        PersonalPerspective.validate(missing)

    unknown = dict(_VALID)
    unknown["attention_points"] = ["旧字段"]
    with pytest.raises(OutputValidationError):
        PersonalPerspective.validate(unknown)

    wrong_type = dict(_VALID)
    wrong_type["personal_summary"] = []
    with pytest.raises(OutputValidationError):
        PersonalPerspective.validate(wrong_type)


def test_personal_contract_matches_model_fields() -> None:
    assert tuple(f.name for f in PersonalPerspectiveGenerationContract.fields) == (
        PERSONAL_PERSPECTIVE_FIELDS
    )
    contract = PERSONAL_PERSPECTIVE_GENERATION_OUTPUT_CONTRACT
    for field in PERSONAL_PERSPECTIVE_FIELDS:
        assert field in contract, field
    for old in ("attention_points", "relevant_topics", "evidence", "responsibilities"):
        assert old not in contract, old


def test_personal_prompt_freezes_inputs_outputs_and_boundaries() -> None:
    prompt = PERSONAL_PERSPECTIVE_MODELING_SYSTEM_PROMPT
    assert PERSONAL_PERSPECTIVE_PROMPT_VERSION == "personal-v1"

    for field in ("name", "name_aliases", "role", "focus_person", "focus_thing", "preferences"):
        assert field in prompt, field
    for field in (
        "meeting_brief",
        "meeting_purpose",
        "speakers",
        "session_segments",
        "decisions",
        "open_questions",
        "risks",
    ):
        assert field in prompt, field
    for field in PERSONAL_PERSPECTIVE_FIELDS:
        assert field in prompt, field

    for forbidden in (
        "action_hints",
        "risk_hints",
        "dependencies",
        "attention_points",
        "relevant_topics",
        "evidence",
        "responsibilities",
    ):
        assert forbidden not in prompt, forbidden

    assert "证据包" in prompt
    assert "不得执行" in prompt
