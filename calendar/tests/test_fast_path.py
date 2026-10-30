"""Fast-Path 回归测试：覆盖规则引擎容易静默算错的高频表达。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fast_path import try_fast_extract  # noqa: E402
from tool import resolve_deadline  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")


def resolve(text: str, meeting: datetime | None = None):
    meeting = meeting or datetime(2026, 10, 29, 14, 30, 45, tzinfo=TZ)
    ir = try_fast_extract(0, text)
    assert ir is not None, f"fast path missed: {text}"
    return resolve_deadline(meeting, ir)


def test_fused_date_time_tokens_route_to_llm() -> None:
    for text in ("今晚", "明晚", "明早", "今晚10点", "明晚10点", "明早10点"):
        assert try_fast_extract(0, text) is None, text


def test_date_plus_time_combinations_route_to_llm() -> None:
    for text in (
        "明天下午",
        "周五下班前",
        "下周三上午10点",
        "明天下午3点半",
        "今天上午",
        "今天中午",
        "今天下午",
        "下下周一下午",
        "这个月十五号下午3点",
        "大后天晚上12点",
        "明天晚上12点",
    ):
        assert try_fast_extract(0, text) is None, text


def test_event_recurrence_and_range_route_to_llm() -> None:
    for text in (
        "项目启动5天后",
        "上线两周后",
        "评审结束3天后",
        "客户确认后一周",
        "每周五",
        "每月15号",
        "每年年底",
        "每季度末",
        "周五到周日",
        "下周一至周五",
        "一周内",
        "两周内",
        "2周内",
        "3周内",
        "4周内",
        "5天内",
        "3个工作日内",
        "2个月内",
        "本周内",
    ):
        assert try_fast_extract(0, text) is None, text


def test_current_month_day_is_not_rolled_forward() -> None:
    result = resolve("本月15号")
    assert result.deadline == "2026/10/15"
    assert "target_in_past" in result.warnings


def test_next_month_day_is_not_lost() -> None:
    meeting = datetime(2026, 10, 10, 10, 0, tzinfo=TZ)
    result = resolve("下月15号", meeting)
    assert result.deadline == "2026/11/15"


def test_current_month_first_is_not_rolled_forward() -> None:
    meeting = datetime(2026, 10, 10, 10, 0, tzinfo=TZ)
    result = resolve("本月1号", meeting)
    assert result.deadline == "2026/10/01"
    assert "target_in_past" in result.warnings


def test_11_oclock_is_morning_not_2300() -> None:
    result = resolve("11点")
    assert result.deadline == "2026/10/30 11:00"


def test_7_oclock_is_morning() -> None:
    result = resolve("7点")
    assert result.deadline == "2026/10/30 07:00"


def test_3_oclock_defaults_to_afternoon() -> None:
    result = resolve("3点")
    assert result.deadline == "2026/10/29 15:00"


def test_days_within_routes_to_llm() -> None:
    assert try_fast_extract(0, "5天内") is None


def test_eod_slot() -> None:
    result = resolve("EOD")
    assert result.deadline == "2026/10/29"
    assert result.time_slot == "下班前"


def test_yizao_slot() -> None:
    result = resolve("一早")
    assert result.deadline == "2026/10/30"
    assert result.time_slot == "上午"


def test_previous_month_day_is_previous_month() -> None:
    result = resolve("上个月15号")
    assert result.deadline == "2026/09/15"
    assert "target_in_past" in result.warnings


def test_previous_month_end() -> None:
    result = resolve("上个月底")
    assert result.deadline == "2026/09/30"


def test_days_before() -> None:
    result = resolve("5天前")
    assert result.deadline == "2026/10/24"


def test_months_before() -> None:
    result = resolve("3个月前")
    assert result.deadline == "2026/07/29"


def test_none_phrases_and_english_tbd() -> None:
    for text in ("无明确时间", "TBD", "不限期"):
        ir = try_fast_extract(0, text)
        assert ir is not None and ir.status == "none", text


def test_zhao_yidian_is_not_parsed_as_one_oclock() -> None:
    assert try_fast_extract(0, "早一点") is None
    assert try_fast_extract(0, "快一点") is None
    assert try_fast_extract(0, "晚一点") is None


def test_ordinal_dian_and_yidiandian_are_not_clock_times() -> None:
    assert try_fast_extract(0, "第一点") is None
    assert try_fast_extract(0, "第二点") is None
    assert try_fast_extract(0, "第1点") is None
    assert try_fast_extract(0, "一点点") is None


def test_one_oclock_still_parses() -> None:
    result = resolve("一点")
    assert result.deadline == "2026/10/30 13:00"


def test_year_nodes() -> None:
    assert resolve("去年底").deadline == "2025/12/31"
    assert resolve("前年初").deadline == "2024/01/01"
    assert resolve("后年底").deadline == "2028/12/31"
    assert resolve("2027年底").deadline == "2027/12/31"
    assert resolve("2027年初").deadline == "2027/01/01"


def test_previous_quarter_end() -> None:
    result = resolve("上季度末")
    assert result.deadline == "2026/09/30"
    assert "target_in_past" in result.warnings


def test_ambiguous_expressions_route_to_llm() -> None:
    for text in ("这周五或者最迟下周一", "周五或下周一", "周五左右"):
        assert try_fast_extract(0, text) is None, text


def test_bare_twelve_is_noon_and_night_twelve_is_midnight() -> None:
    assert resolve("12点").deadline == "2026/10/30 12:00"
    assert resolve("12点半").deadline == "2026/10/30 12:30"
    assert resolve("晚上12点").deadline == "2026/10/30 00:00"
    assert resolve("晚上12点半").deadline == "2026/10/30 00:30"
    assert resolve("24点").deadline == "2026/10/30 00:00"
    assert resolve("中午12点").deadline == "2026/10/30 12:00"
    assert resolve("上午12点").deadline == "2026/10/30 12:00"
    assert resolve("下午12点").deadline == "2026/10/30 12:00"
    assert resolve("今晚12点").deadline == "2026/10/30 00:00"
    assert resolve("明晚12点").deadline == "2026/10/31 00:00"
    assert resolve("今晚12点半").deadline == "2026/10/30 00:30"
    assert resolve("明晚12点半").deadline == "2026/10/31 00:30"


def test_zero_and_zero_plus_minutes_route_to_llm() -> None:
    for text in ("零点", "零点半", "零点15分"):
        assert try_fast_extract(0, text) is None, text


def test_date_plus_zero_routes_to_llm() -> None:
    for text in ("今天零点", "明天零点", "本周五零点"):
        assert try_fast_extract(0, text) is None, text


def test_minutes_without_fen_suffix() -> None:
    assert resolve("下午4点20").deadline == "2026/10/29 16:20"
    assert resolve("下午4点20分").deadline == "2026/10/29 16:20"
    assert resolve("4点20").deadline == "2026/10/29 16:20"
    assert resolve("晚上8点20").deadline == "2026/10/29 20:20"
    assert resolve("晚上8点20分").deadline == "2026/10/29 20:20"
    assert resolve("12点20").deadline == "2026/10/30 12:20"
    assert resolve("12点20分").deadline == "2026/10/30 12:20"


def test_invalid_long_minute_is_not_truncated() -> None:
    assert try_fast_extract(0, "4点200") is None
