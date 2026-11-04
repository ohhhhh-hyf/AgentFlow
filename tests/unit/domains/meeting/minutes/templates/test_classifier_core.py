"""Stage 2：场景识别 Agent 的纯函数层。"""
from __future__ import annotations

from domains.meeting.tasks.minutes.steps.template_classifier import (
    normalize_template_id,
    parse_classifier_output,
    postprocess,
    sample_transcript,
    should_skip_by_length,
)

_CANDIDATES = {"team_meeting", "project_progress", "general_minutes"}


# ── 短会判断 ────────────────────────────────────────────────────

def test_short_threshold_boundary() -> None:
    assert should_skip_by_length("a" * 1999) is True
    assert should_skip_by_length("a" * 2000) is False


def test_short_threshold_strips_whitespace() -> None:
    assert should_skip_by_length("  " + "a" * 1997 + "  ") is True
    assert should_skip_by_length("") is True


# ── 采样 ────────────────────────────────────────────────────────

def test_sample_returns_short_text_unchanged() -> None:
    text = "短会内容" * 100
    assert sample_transcript(text) == text


def test_sample_long_text_has_head_middle_tail_without_overlap() -> None:
    head = "H" * 6000
    middle = "M" * 4000
    tail = "T" * 5000
    text = head + "\n" + middle + "\n" + tail

    sampled = sample_transcript(text)

    assert "【中段节选】" in sampled
    assert "【结尾】" in sampled
    assert sampled.startswith("H")
    assert sampled.endswith("T")
    # 头段完整保留；尾段是原文最后 4000 字
    assert head in sampled
    assert tail[-4000:] in sampled
    # 三段不重叠：中段不会包含完整头段/尾段
    assert sampled.count("H" * 6000) == 1


def test_sample_long_text_without_newlines() -> None:
    text = "x" * 13000
    sampled = sample_transcript(text)
    assert len(sampled) <= 12000 + 40  # 允许两个分隔符
    assert sampled.startswith("x")
    assert sampled.endswith("x")


# ── 解析 ────────────────────────────────────────────────────────

def test_parse_valid_json_string() -> None:
    assert parse_classifier_output(
        '{"template":"project_progress","confidence":0.86}'
    ) == {"template": "project_progress", "confidence": 0.86}


def test_parse_fenced_or_noisy_json() -> None:
    raw = '```json\n{"template":"team_meeting","confidence":0.8}\n```'
    assert parse_classifier_output(raw) == {
        "template": "team_meeting",
        "confidence": 0.8,
    }
    noisy = '结果如下：{"template":"team_meeting","confidence":0.8} 请查收'
    assert parse_classifier_output(noisy) == {
        "template": "team_meeting",
        "confidence": 0.8,
    }


def test_parse_rejects_invalid_payloads() -> None:
    assert parse_classifier_output("not json") is None
    assert parse_classifier_output('{"template":"x"}') is None
    assert parse_classifier_output('{"template":"","confidence":0.8}') is None
    assert parse_classifier_output('{"template":1,"confidence":0.8}') is None
    assert parse_classifier_output('{"template":"x","confidence":"0.8"}') is None
    assert parse_classifier_output('{"template":"x","confidence":true}') is None
    assert parse_classifier_output('{"template":"x","confidence":1.2}') is None
    assert parse_classifier_output(None) is None


# ── 归一化 ──────────────────────────────────────────────────────

def test_normalize_template_id() -> None:
    assert normalize_template_id(" Project_Progress.MD ", _CANDIDATES) == "project_progress"
    assert normalize_template_id("项目进度会", _CANDIDATES) is None
    assert normalize_template_id("unknown", _CANDIDATES) is None
    assert normalize_template_id(None, _CANDIDATES) is None


# ── 后处理 ──────────────────────────────────────────────────────

def test_postprocess_accepts_at_threshold() -> None:
    decision = postprocess(
        {"template": "project_progress", "confidence": 0.70},
        _CANDIDATES,
        "normal",
    )
    assert decision.accepted is True
    assert decision.template == "project_progress"
    assert decision.action == "use"
    assert decision.reason == "none"


def test_postprocess_falls_back_below_threshold() -> None:
    decision = postprocess(
        {"template": "project_progress", "confidence": 0.69},
        _CANDIDATES,
        "normal",
    )
    assert decision.accepted is False
    assert decision.template == "general_minutes"
    assert decision.reason == "low_confidence"


def test_postprocess_falls_back_for_invalid_output() -> None:
    for raw in ("not json", {"template": "x"}, {"confidence": 0.8}):
        decision = postprocess(raw, _CANDIDATES, "normal")
        assert decision.accepted is False
        assert decision.template == "general_minutes"
        assert decision.reason == "invalid_output"


def test_postprocess_falls_back_for_unknown_or_general() -> None:
    unknown = postprocess(
        {"template": "unknown", "confidence": 0.9}, _CANDIDATES, "normal"
    )
    assert unknown.reason == "not_in_candidates"

    general = postprocess(
        {"template": "general_minutes", "confidence": 0.9}, _CANDIDATES, "normal"
    )
    assert general.reason == "general"
    assert general.template == "general_minutes"


def test_postprocess_agenda_fallback_keeps_mode() -> None:
    decision = postprocess(
        {"template": "project_progress", "confidence": 0.4},
        _CANDIDATES,
        "agenda",
    )
    assert decision.accepted is False
    assert decision.template == "general_minutes"
    assert decision.mode == "agenda"
    assert decision.reason == "low_confidence"
