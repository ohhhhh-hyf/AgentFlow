"""tests/unit/meeting/test_minutes_topic_major_prompts.py -- topic_major prompt 与路由。"""
from __future__ import annotations

from domains.meeting.tasks.minutes.prompt_map import (
    is_topic_major,
    minutes_prompt_set,
    prompt_label,
    render_template_prompt,
)
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
    MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT,
    build_minutes_supervisor_prompt,
)


def test_minutes_prompt_set_topic_major() -> None:
    prompt_set = minutes_prompt_set("agenda_objective", "topic_major")

    assert prompt_set.generation is MINUTES_TOPIC_MAJOR_GENERATION_PROMPT
    assert prompt_set.supervisor is MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT


def test_minutes_prompt_set_column_major_unchanged() -> None:
    default_set = minutes_prompt_set("agenda_objective")
    explicit_set = minutes_prompt_set("agenda_objective", "column_major")

    assert default_set.generation is MINUTES_AGENDA_GENERATION_PROMPT
    assert default_set.supervisor is MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert explicit_set.generation is MINUTES_AGENDA_GENERATION_PROMPT
    assert explicit_set.supervisor is MINUTES_AGENDA_SUPERVISOR_PROMPT


def test_non_agenda_view_ignores_topic_major_layout() -> None:
    prompt_set = minutes_prompt_set("personal", "topic_major")

    assert prompt_set.generation is not MINUTES_TOPIC_MAJOR_GENERATION_PROMPT
    assert prompt_set.supervisor is not MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT


def test_render_template_prompt_topic_major() -> None:
    assert (
        render_template_prompt("agenda_objective", "topic_major")
        is MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT
    )


def test_render_template_prompt_column_major_unchanged() -> None:
    assert (
        render_template_prompt("agenda_objective")
        is MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    )
    assert (
        render_template_prompt("personal")
        is MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT
    )


def test_prompt_label_and_is_topic_major() -> None:
    assert is_topic_major("agenda_objective", "topic_major")
    assert not is_topic_major("agenda_objective", "column_major")
    assert not is_topic_major("personal", "topic_major")

    assert prompt_label("agenda_objective", "topic_major") == "agenda_topic"
    assert prompt_label("agenda_objective") == "agenda"
    assert prompt_label("personal") == "personal"


def test_topic_major_generation_prompt_fields() -> None:
    prompt = MINUTES_TOPIC_MAJOR_GENERATION_PROMPT

    for key in (
        "topic_name",
        "topic_summary",
        "decisions",
        "actions",
        "risks",
        "open_questions",
    ):
        assert key in prompt
    assert "executive_summary" not in prompt
    assert "N 个有效议题必须输出 N 条" in prompt


def test_topic_major_supervisor_scope() -> None:
    assert "议题主序模式审查范围" in MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT
    assert "topic_summary" in MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT
    assert "审定议题模式审查范围" not in MINUTES_TOPIC_MAJOR_SUPERVISOR_PROMPT

    built = build_minutes_supervisor_prompt(
        "agenda_objective", layout="topic_major", context=""
    )
    assert "议题主序模式审查范围" in built


def test_topic_major_render_prompt_mapping() -> None:
    prompt = MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT

    for text in ("overview", "topics", "topic_summary", "open_questions", "container"):
        assert text in prompt
    assert "executive_summary" not in prompt
    assert "议题容器类栏目" in prompt
