"""tests/unit/meeting/test_minutes_topic_major_contract.py -- topic_major 契约与模型。"""
from __future__ import annotations

import json
from dataclasses import fields

import pytest

from core.schema.validation import OutputValidationError
from domains.meeting.models import TopicMajorMinutes
from domains.meeting.tasks.minutes.contracts import (
    MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT,
    MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT,
)

_TOP_KEYS = {"headline", "overview", "topics", "history_comparison"}
_TOPIC_KEYS = {
    "topic_name",
    "topic_summary",
    "decisions",
    "actions",
    "risks",
    "open_questions",
}


def _sample() -> dict:
    return {
        "headline": "团队例会纪要",
        "overview": "本次例会围绕接口联调与上线准备展开。",
        "topics": [
            {
                "topic_name": "接口联调",
                "topic_summary": ["接口方案已确认", "联调排期本周内"],
                "decisions": ["按 B 方案执行"],
                "actions": ["张三周五前完成联调报告"],
                "risks": ["依赖外部团队，可能延迟"],
                "open_questions": ["上线时间是否按原计划"],
            }
        ],
        "history_comparison": [],
    }


def test_contract_json_shape() -> None:
    raw = MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT.split("字段说明：", 1)[0].strip()
    data = json.loads(raw)

    assert set(data) == _TOP_KEYS
    assert set(data["topics"][0]) == _TOPIC_KEYS
    assert isinstance(data["topics"], list)


def test_contract_is_independent_from_agenda_contract() -> None:
    assert MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT != MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    assert "topic_summary" in MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
    assert "executive_summary" in MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT


def test_contract_requires_clean_topic_name() -> None:
    assert "议题全称本体" in MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
    assert "不得带" in MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
    assert "议题：" in MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT


def test_contract_requires_natural_topic_summary_grouping() -> None:
    contract = MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
    assert "按业务逻辑自然分组" in contract
    assert "不设固定组数和条数" in contract
    assert "**子主题**：" in contract


def test_model_fields_exact() -> None:
    assert [f.name for f in fields(TopicMajorMinutes)] == [
        "headline",
        "overview",
        "topics",
        "history_comparison",
    ]


def test_model_accepts_valid_sample() -> None:
    model = TopicMajorMinutes.validate(_sample())

    assert model.headline == "团队例会纪要"
    assert model.topics[0]["topic_name"] == "接口联调"
    assert model.model_dump()["topics"][0]["actions"] == ["张三周五前完成联调报告"]


def test_model_allows_empty_topics_and_lists() -> None:
    data = {
        "headline": "标题",
        "overview": "概况",
        "topics": [],
        "history_comparison": [],
    }

    model = TopicMajorMinutes.validate(data)

    assert model.topics == []
    assert model.history_comparison == []


def test_model_rejects_missing_top_level_key() -> None:
    data = _sample()
    data.pop("overview")

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_extra_top_level_key() -> None:
    data = _sample()
    data["extra"] = "x"

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_missing_topic_key() -> None:
    data = _sample()
    data["topics"][0].pop("risks")

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_extra_topic_key() -> None:
    data = _sample()
    data["topics"][0]["extra"] = "x"

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_non_list_topics() -> None:
    data = _sample()
    data["topics"] = {}

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_non_object_topic_item() -> None:
    data = _sample()
    data["topics"] = ["not-an-object"]

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_non_string_topic_fields() -> None:
    data = _sample()
    data["topics"][0]["decisions"] = "不是数组"

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)


def test_model_rejects_empty_topic_name() -> None:
    data = _sample()
    data["topics"][0]["topic_name"] = "  "

    with pytest.raises(OutputValidationError):
        TopicMajorMinutes.validate(data)
