"""Step 3：个人证据包构建测试。"""
from __future__ import annotations

from domains.shared.perspective import (
    PERSONAL_EVIDENCE_FULL_LIMIT,
    build_personal_evidence_pack,
)

_USER = {
    "name": "张三",
    "name_aliases": ["小张"],
    "role": "后端工程师",
    "focus_person": ["李四"],
    "focus_thing": ["压测"],
    "preferences": ["先说结论"],
}

_FILLER = "无关内容。" * 200


def test_short_transcript_returns_full_mode() -> None:
    text = "张三 00:00:01\n负责压测。\n李四 00:00:10\n讨论排期。"
    out, stats = build_personal_evidence_pack(text, _USER)
    assert stats["mode"] == "full"
    assert stats["empty"] is False
    assert stats["chars_in"] == len(text)
    assert stats["chars_out"] == len(out)
    assert text in out
    assert "本场原文较短" in out


def test_empty_transcript_returns_empty() -> None:
    out, stats = build_personal_evidence_pack("", _USER)
    assert out == ""
    assert stats["mode"] == "empty"
    assert stats["empty"] is True
    assert stats["chars_out"] == 0


def test_named_track_keeps_self_and_focus_thing() -> None:
    text = (
        "张三 00:00:01\n"
        + "负责压测和显存优化，周五前提交报告。" * 20
        + "\n赵六 00:00:05\n"
        + _FILLER
        + "\n王五 00:00:20\n讨论压测方案。\n"
    )
    out, stats = build_personal_evidence_pack(text, _USER, max_chars=500)
    assert stats["mode"] == "slice"
    assert stats["track"] == "NAMED"
    assert stats["kept"] >= 2
    assert stats["dropped"] >= 1
    assert "张三" in out
    assert "压测" in out
    assert "赵六" not in out


def test_content_track_keeps_named_handshake() -> None:
    text = (
        "发言人 1 00:00:01\n赵工你汇报一下网关进展。\n"
        "发言人 2 00:00:10\n支付网关已提测。\n"
        "发言人 3 00:00:30\n"
        + _FILLER
    )
    user = {"name": "赵衡", "name_aliases": ["赵工"], "focus_thing": ["支付网关"]}
    out, stats = build_personal_evidence_pack(text, user, max_chars=500)
    assert stats["mode"] == "slice"
    assert stats["track"] == "CONTENT"
    assert "支付网关" in out


def test_bullet_speaker_lines_are_parsed() -> None:
    text = (
        "• 发言者 1 00:00:01\n赵工你汇报一下网关进展。\n"
        "• 发言者 2 00:00:10\n支付网关已提测。\n"
        "• 发言者 3 00:00:30\n"
        + _FILLER
    )
    user = {"name": "赵衡", "name_aliases": ["赵工"], "focus_thing": ["支付网关"]}
    out, stats = build_personal_evidence_pack(text, user, max_chars=500)
    assert stats["mode"] == "slice"
    assert stats["track"] == "CONTENT"
    assert "支付网关" in out


def test_user_absent_still_keeps_focus_thing() -> None:
    text = "王五 00:00:01\n压测方案需要重排。\n" + _FILLER
    out, stats = build_personal_evidence_pack(text, _USER, max_chars=500)
    assert "压测" in out
    assert "张三" not in out
    assert stats["mode"] in {"slice", "keyword"}


def test_keyword_window_when_no_speaker_structure() -> None:
    text = "无关内容。" * 1000 + "张三负责压测。" + "无关内容。" * 1000
    out, stats = build_personal_evidence_pack(text, _USER, max_chars=500)
    assert stats["mode"] == "keyword"
    assert stats["track"] == "KEYWORD"
    assert stats["fallback"] is False
    assert "张三" in out
    assert "压测" in out


def test_global_sample_when_no_keywords_found() -> None:
    text = "无关内容。" * 2000
    out, stats = build_personal_evidence_pack(text, _USER, max_chars=500)
    assert stats["mode"] == "sample"
    assert stats["track"] == "SAMPLE"
    assert stats["fallback"] is True
    assert stats["capped"] is True
    assert "全局采样" in out


def test_full_limit_constant_is_frozen() -> None:
    assert PERSONAL_EVIDENCE_FULL_LIMIT == 12000
