"""Stage 0：场景识别开关的默认值与取值。"""
from __future__ import annotations

from domains.meeting.domain_config import (
    TEMPLATE_AUTO_MODES,
    TEMPLATE_AUTO_SHORT_CHARS,
    minutes_template_auto_mode,
)


def test_default_mode_is_off(monkeypatch) -> None:
    monkeypatch.delenv("MINUTES_TEMPLATE_AUTO", raising=False)
    assert minutes_template_auto_mode() == "off"


def test_valid_modes_are_case_insensitive(monkeypatch) -> None:
    for raw, expected in (("SHADOW", "shadow"), ("on", "on"), ("OFF", "off")):
        monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", raw)
        assert minutes_template_auto_mode() == expected


def test_invalid_mode_falls_back_to_off(monkeypatch) -> None:
    for raw in ("", "  ", "enabled", "true", "1"):
        monkeypatch.setenv("MINUTES_TEMPLATE_AUTO", raw)
        assert minutes_template_auto_mode() == "off"


def test_switch_values_and_short_threshold() -> None:
    assert TEMPLATE_AUTO_MODES == ("off", "shadow", "on")
    assert TEMPLATE_AUTO_SHORT_CHARS == 2000
