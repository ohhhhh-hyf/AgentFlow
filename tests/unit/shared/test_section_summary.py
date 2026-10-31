"""Section Summary Agent 单测（不访问网络）。"""
from __future__ import annotations

import json

import pytest

from domains.shared.section_summary import (
    SECTION_SUMMARY_PROMPT,
    SectionSummary,
    SectionSummaryAgent,
    SectionSummaryInputError,
    format_transcript_for_prompt,
    parse_transcript,
    render_markdown,
)
from domains.shared.section_summary.prompts import build_prompt
from domains.shared.section_summary.validation import normalize_sections

TRANSCRIPT = """申家坤 00:00:00
今天主要三件事：版本发布、线上问题、下周排期。
李娜 00:00:30
1.4.5 已经提测，主流程跑完了。
申家坤 00:03:10
好，版本没问题。第二个，线上那个报错谁跟一下？
王强 00:03:25
是空指针，日志里能复现。
"""


class FakeClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = []

    async def text(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt, kwargs))
        return self.response


def _valid_response() -> str:
    return json.dumps(
        [
            {
                "time_start": "00:00:00",
                "title": "1.4.5 版本发布进展",
                "key_words": ["版本发布", "提测"],
                "section_summary": "确认 1.4.5 已提测，主流程验证通过。",
            },
            {
                "time_start": "00:03:10",
                "title": "线上报错定位",
                "key_words": ["空指针", "日志复现"],
                "section_summary": "王强定位为空指针问题，安排优先修复。",
            },
        ],
        ensure_ascii=False,
    )


def test_parse_speaker_timestamp_format() -> None:
    lines = parse_transcript(TRANSCRIPT)
    assert [line.timestamp for line in lines] == [
        "00:00:00",
        "00:00:30",
        "00:03:10",
        "00:03:25",
    ]
    assert lines[0].speaker == "申家坤"
    assert "版本发布" in lines[0].text
    assert lines[2].text.startswith("好，版本没问题")


def test_parse_one_line_bracket_format() -> None:
    lines = parse_transcript(
        "00:00:01 [张三] 大家好，今天讨论预算。\n"
        "00:02:03 [李四] 预算还需要再确认。\n"
    )
    assert len(lines) == 2
    assert lines[0].speaker == "张三"
    assert lines[0].text == "大家好，今天讨论预算。"
    assert lines[1].timestamp == "00:02:03"


def test_parse_timestamp_then_speaker_header_format() -> None:
    lines = parse_transcript("[00:00:01] 张三\n你好\n[00:02:03] 李四\n收到\n")
    assert [(line.timestamp, line.speaker) for line in lines] == [
        ("00:00:01", "张三"),
        ("00:02:03", "李四"),
    ]


def test_parse_leading_bullet_headers() -> None:
    lines = parse_transcript(
        "• 发言者 1 52:00\n内容一\n"
        "• 发言者 2 53:10\n内容二\n"
    )
    assert [(line.timestamp, line.speaker) for line in lines] == [
        ("52:00", "发言者 1"),
        ("53:10", "发言者 2"),
    ]
    assert format_transcript_for_prompt(lines).splitlines()[0] == (
        "52:00 [发言者 1] 内容一"
    )


def test_parse_leading_dash_bullet() -> None:
    lines = parse_transcript("- 发言者 1 52:00\n内容一\n- 发言者 2 53:10\n内容二\n")
    assert [line.speaker for line in lines] == ["发言者 1", "发言者 2"]


def test_parse_without_timestamp_raises() -> None:
    with pytest.raises(SectionSummaryInputError):
        parse_transcript("张三：你好\n李四：收到\n")


def test_format_transcript_for_prompt() -> None:
    lines = parse_transcript(TRANSCRIPT)
    text = format_transcript_for_prompt(lines)
    assert text.splitlines()[0] == "00:00:00 [申家坤] 今天主要三件事：版本发布、线上问题、下周排期。"
    assert text.splitlines()[1].startswith("00:00:30 [李娜]")


def test_normalize_canonicalizes_time_and_limits_fields() -> None:
    lines = parse_transcript(TRANSCRIPT)
    long_title = "这是一个非常非常长的标题超过二十个字符需要被截断"
    long_summary = "这是一段很长的纪要。" * 40
    raw = json.dumps(
        [
            {
                "time_start": "0:00:00",
                "title": long_title,
                "key_words": [
                    "这是一个超过十个字的关键词",
                    "预算",
                    "预算",
                    "成本",
                    "排期",
                    "风险",
                ],
                "section_summary": long_summary,
            }
        ],
        ensure_ascii=False,
    )
    sections, warnings = normalize_sections(raw, lines)
    assert warnings == []
    section = sections[0]
    assert section.time_start == "00:00:00"
    assert len(section.title) <= 20
    assert len(section.section_summary) <= 200
    assert len(section.key_words) <= 4
    assert all(len(word) <= 10 for word in section.key_words)
    assert len(section.key_words) == len(set(section.key_words))


def test_normalize_coerces_key_words_string() -> None:
    lines = parse_transcript(TRANSCRIPT)
    raw = json.dumps(
        [
            {
                "time_start": "00:00:00",
                "title": "版本发布",
                "key_words": "版本、提测，兼容性",
                "section_summary": "确认版本进展。",
            }
        ],
        ensure_ascii=False,
    )
    sections, warnings = normalize_sections(raw, lines)
    assert warnings == []
    assert sections[0].key_words == ["版本", "提测", "兼容性"]


def test_normalize_aligns_first_section_to_first_line() -> None:
    lines = parse_transcript(TRANSCRIPT)
    raw = json.dumps(
        [
            {
                "time_start": "00:00:30",
                "title": "版本发布",
                "key_words": [],
                "section_summary": "确认版本进展。",
            }
        ],
        ensure_ascii=False,
    )
    sections, warnings = normalize_sections(raw, lines)
    assert sections[0].time_start == "00:00:00"
    assert any("首行" in warning for warning in warnings)


def test_normalize_drops_unknown_time() -> None:
    lines = parse_transcript(TRANSCRIPT)
    raw = json.dumps(
        [
            {
                "time_start": "00:59:59",
                "title": "不存在的时间",
                "key_words": [],
                "section_summary": "内容。",
            }
        ],
        ensure_ascii=False,
    )
    sections, warnings = normalize_sections(raw, lines)
    assert sections == []
    assert any("不存在" in warning for warning in warnings)


def test_render_markdown_with_and_without_keywords() -> None:
    sections = [
        SectionSummary(
            time_start="00:00:00",
            title="预算讨论",
            key_words=["预算", "确认"],
            section_summary="张三介绍预算。",
        ),
        SectionSummary(
            time_start="00:03:10",
            title="排期讨论",
            key_words=[],
            section_summary="确认下周三交付。",
        ),
    ]
    assert render_markdown(sections) == (
        "00:00:00  预算讨论  \n"
        "关键词：预算、确认  \n"
        "张三介绍预算。\n"
        "\n"
        "00:03:10  排期讨论  \n"
        "确认下周三交付。\n"
    )


def test_agent_uses_prompt_and_fake_client() -> None:
    client = FakeClient(_valid_response())
    result = SectionSummaryAgent(client=client).run(TRANSCRIPT)

    assert result.warnings == []
    assert result.raw_response == _valid_response()
    assert len(result.sections) == 2
    assert result.sections[0].time_start == "00:00:00"
    assert result.sections[1].time_start == "00:03:10"
    assert result.markdown.startswith("00:00:00  1.4.5 版本发布进展  \n")
    assert "关键词：版本发布、提测  \n" in result.markdown

    system_prompt, user_prompt, kwargs = client.calls[0]
    assert "00:00:00 [申家坤]" in system_prompt
    assert "{{transcript}}" not in system_prompt
    assert user_prompt
    assert kwargs["temperature"] == 0.0
    assert kwargs["json_mode"] is False


def test_agent_falls_back_on_bad_json() -> None:
    client = FakeClient("这不是 JSON")
    result = SectionSummaryAgent(client=client).run(TRANSCRIPT)

    assert result.sections
    assert result.markdown
    assert result.raw_response == "这不是 JSON"
    assert any("规则兜底" in warning for warning in result.warnings)
    assert result.markdown.startswith("00:00:00  ")


def test_prompt_contains_placeholder_and_key_rules() -> None:
    assert SECTION_SUMMARY_PROMPT.startswith("你是会议段落速览助手。")
    assert "{{transcript}}" in SECTION_SUMMARY_PROMPT
    assert "R5 边界不明确时" in SECTION_SUMMARY_PROMPT
    assert "time_start" in SECTION_SUMMARY_PROMPT
    assert "key_words" in SECTION_SUMMARY_PROMPT

    filled = build_prompt("TRANSCRIPT_TOKEN")
    assert filled.count("TRANSCRIPT_TOKEN") == 1
    assert "{{transcript}}" not in filled
