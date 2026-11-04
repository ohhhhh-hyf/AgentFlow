"""tests/unit/core/templates/test_template_layout.py -- layout 元数据解析与剥离单元测试。"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core.templates.router._base import split_template_layout, split_template_meta
from core.templates.router._detect import detect_template_kind, parse_placeholder_template


def test_block_layout_parsed_and_stripped() -> None:
    text = """# 团队例会

<!-- layout
mode: topic_major
container: 议题梳理
-->

## [议题梳理]
[说明]
"""
    clean, mode, container = split_template_layout(text)

    assert mode == "topic_major"
    assert container == "议题梳理"
    assert "<!-- layout" not in clean
    assert clean.startswith("# 团队例会")
    assert "## [议题梳理]" in clean


def test_inline_layout_parsed() -> None:
    text = "# T\n\n<!-- layout: topic_major -->\n\n## [X]\n[Y]\n"

    clean, mode, container = split_template_layout(text)

    assert mode == "topic_major"
    assert container == ""
    assert "<!-- layout" not in clean
    assert "## [X]" in clean


def test_inline_key_value_layout_parsed() -> None:
    text = "# T\n\n<!-- layout: mode=topic_major; container=议题梳理 -->\n\n## [X]\n[Y]\n"

    clean, mode, container = split_template_layout(text)

    assert mode == "topic_major"
    assert container == "议题梳理"
    assert "<!-- layout" not in clean


@pytest.mark.parametrize(
    ("raw_mode", "expected"),
    [
        ("topic", "topic_major"),
        ("topic-major", "topic_major"),
        ("TOPIC_MAJOR", "topic_major"),
        ("column", "column_major"),
        ("column-major", "column_major"),
        ("COLUMN_MAJOR", "column_major"),
    ],
)
def test_layout_mode_aliases(raw_mode: str, expected: str) -> None:
    text = f"# T\n\n<!-- layout: {raw_mode} -->\n"

    _clean, mode, _container = split_template_layout(text)

    assert mode == expected


def test_no_layout_returns_text_unchanged() -> None:
    text = """# T

<!-- requirement
写作要求
-->

## [X]
[Y]
"""

    clean, mode, container = split_template_layout(text)

    assert clean == text
    assert mode == "column_major"
    assert container == ""


def test_invalid_mode_falls_back_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    text = "# T\n\n<!-- layout\nmode: weird_mode\n-->\n"

    with caplog.at_level(logging.WARNING):
        clean, mode, container = split_template_layout(text)

    assert mode == "column_major"
    assert container == ""
    assert "<!-- layout" not in clean
    assert any("invalid mode" in rec.message for rec in caplog.records)


def test_missing_mode_falls_back_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    text = "# T\n\n<!-- layout\ncontainer: 议题梳理\n-->\n"

    with caplog.at_level(logging.WARNING):
        clean, mode, container = split_template_layout(text)

    assert mode == "column_major"
    assert container == "议题梳理"
    assert "<!-- layout" not in clean
    assert any("missing mode" in rec.message for rec in caplog.records)


def test_duplicate_layout_first_wins_and_all_stripped(caplog: pytest.LogCaptureFixture) -> None:
    text = """# T

<!-- layout
mode: topic_major
container: 议题梳理
-->

<!-- layout
mode: column_major
container: 其他
-->

## [X]
[Y]
"""

    with caplog.at_level(logging.WARNING):
        clean, mode, container = split_template_layout(text)

    assert mode == "topic_major"
    assert container == "议题梳理"
    assert "<!-- layout" not in clean
    assert clean.count("## [X]") == 1
    assert any("duplicate layout" in rec.message for rec in caplog.records)


def test_layout_and_requirement_compose() -> None:
    text = """# T

<!-- layout
mode: topic_major
container: 议题梳理
-->

<!-- requirement
写作要求
-->

## [X]
[Y]
"""

    clean, mode, container = split_template_layout(text)
    body, requirement = split_template_meta(clean)

    assert mode == "topic_major"
    assert container == "议题梳理"
    assert requirement == "写作要求"
    assert "<!-- layout" not in body
    assert "<!-- requirement" not in body
    assert body.startswith("# T")


def test_team_meeting_template_parses_as_placeholder() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "resources"
        / "agenda_templates"
        / "zh"
        / "team_meeting.md"
    )
    text = path.read_text(encoding="utf-8")

    clean, mode, container = split_template_layout(text)

    assert mode == "topic_major"
    assert container == "议题梳理"
    assert "<!-- layout" not in clean
    assert detect_template_kind(clean) == "placeholder"
    titles = [
        seg.get("raw")
        for seg in parse_placeholder_template(clean)
        if seg.get("kind") == "title"
    ]
    assert titles == ["例会概况", "议题梳理"]


def test_column_template_without_layout_is_unchanged() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "resources"
        / "agenda_templates"
        / "zh"
        / "class_transcript.md"
    )
    text = path.read_text(encoding="utf-8")

    clean, mode, container = split_template_layout(text)

    assert clean == text
    assert mode == "column_major"
    assert container == ""
