"""Tool 单测：不依赖 DeepSeek。"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import (  # noqa: E402
    DateRangeSpec,
    DateRule,
    DateSpec,
    DeadlineIR,
    TimeRule,
    TimeSlot,
    TimeSpec,
)
from tool import resolve_deadline  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
MEETING = datetime(2026, 10, 29, 14, 30, 45, tzinfo=TZ)


def ir(date: DateSpec, time: TimeSpec | None = None) -> DeadlineIR:
    return DeadlineIR(
        index=0,
        raw="test",
        status="resolved",
        date=date,
        time=time or TimeSpec(),
    )


def test_tomorrow_date_only() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.OFFSET_DAYS, amount=1)),
    )
    assert result.deadline == "2026/10/30"
    assert result.kind == "date"
    assert re.fullmatch(r"\d{4}/\d{2}/\d{2}", result.deadline or "")


def test_next_wednesday_date_only() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(
                rule=DateRule.WEEKDAY,
                target_weekday=3,
                week_offset=1,
            )
        ),
    )
    assert result.deadline == "2026/11/04"
    assert result.kind == "date"


def test_plain_friday_after_friday_rolls_to_next_week() -> None:
    saturday = datetime(2026, 10, 31, 10, 0, tzinfo=TZ)
    result = resolve_deadline(
        saturday,
        ir(DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=None)),
    )
    assert result.deadline == "2026/11/06"


def test_plain_friday_time_after_meeting_rolls_to_next_week() -> None:
    friday_evening = datetime(2026, 10, 30, 19, 0, tzinfo=TZ)
    result = resolve_deadline(
        friday_evening,
        ir(
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=None),
            TimeSpec(rule=TimeRule.SLOT, slot=TimeSlot.AFTERNOON),
        ),
    )
    assert result.deadline == "2026/11/06"
    assert result.time_slot == "下午"
    assert result.kind == "date"
    assert "weekday_resolved_to_next_occurrence" in result.warnings


def test_month_day_infers_next_year() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.MONTH_DAY, month=10, day=1)),
    )
    assert result.deadline == "2027/10/01"
    assert "year_inferred_next_year" in result.warnings


def test_month_day_explicit_year_keeps_past_date() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.MONTH_DAY, year=2026, month=10, day=1)),
    )
    assert result.deadline == "2026/10/01"
    assert "target_in_past" in result.warnings


def test_month_day_feb_29_finds_next_leap_year() -> None:
    meeting = datetime(2026, 3, 1, 10, 0, tzinfo=TZ)
    result = resolve_deadline(
        meeting,
        ir(DateSpec(rule=DateRule.MONTH_DAY, month=2, day=29)),
    )
    assert result.deadline == "2028/02/29"
    assert "year_inferred_next_year" in result.warnings


def test_tomorrow_afternoon_slot() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.OFFSET_DAYS, amount=1),
            TimeSpec(rule=TimeRule.SLOT, slot=TimeSlot.AFTERNOON),
        ),
    )
    assert result.deadline == "2026/10/30"
    assert result.time_slot == "下午"
    assert result.kind == "date"


def test_time_only_uses_meeting_date() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.IMPLICIT_DATE),
            TimeSpec(rule=TimeRule.EXACT, exact_time="15:00"),
        ),
    )
    assert result.deadline == "2026/10/29 15:00"


def test_time_only_rolls_to_next_day_if_passed() -> None:
    late_meeting = datetime(2026, 10, 29, 16, 0, tzinfo=TZ)
    result = resolve_deadline(
        late_meeting,
        ir(
            DateSpec(rule=DateRule.IMPLICIT_DATE),
            TimeSpec(rule=TimeRule.EXACT, exact_time="15:00"),
        ),
    )
    assert result.deadline == "2026/10/30 15:00"
    assert "implicit_date_rolled_next_day" in result.warnings


def test_evening_slot() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.IMPLICIT_DATE),
            TimeSpec(rule=TimeRule.SLOT, slot=TimeSlot.EVENING),
        ),
    )
    assert result.deadline == "2026/10/29"
    assert result.time_slot == "晚上"
    assert result.kind == "date"


def test_friday_eod() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=None),
            TimeSpec(rule=TimeRule.SLOT, slot=TimeSlot.EOD),
        ),
    )
    assert result.deadline == "2026/10/30"
    assert result.time_slot == "下班前"
    assert result.kind == "date"


def test_midnight_rolls_to_next_day() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.OFFSET_DAYS, amount=3),
            TimeSpec(rule=TimeRule.MIDNIGHT),
        ),
    )
    assert result.deadline == "2026/11/02 00:00"


def test_relative_after_meeting_truncates_seconds() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.SAME_DAY),
            TimeSpec(rule=TimeRule.RELATIVE_MEETING, offset_minutes=60),
        ),
    )
    assert result.deadline == "2026/10/29 15:30"


def test_relative_before_meeting() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(rule=DateRule.SAME_DAY),
            TimeSpec(rule=TimeRule.RELATIVE_MEETING, offset_minutes=-15),
        ),
    )
    assert result.deadline == "2026/10/29 14:15"


def test_offset_weeks() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.OFFSET_WEEKS, amount=2)),
    )
    assert result.deadline == "2026/11/12"


def test_offset_months() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.OFFSET_MONTHS, amount=3)),
    )
    assert result.deadline == "2027/01/29"


def test_quarter_end() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.QUARTER_END, quarter_offset=0)),
    )
    assert result.deadline == "2026/12/31"


def test_offset_months_clamps_day() -> None:
    meeting = datetime(2026, 1, 31, 10, 0, tzinfo=TZ)
    result = resolve_deadline(
        meeting,
        ir(DateSpec(rule=DateRule.OFFSET_MONTHS, amount=1)),
    )
    assert result.deadline == "2026/02/28"
    assert "day_clamped_to_month_end" in result.warnings


def test_month_end() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.MONTH_END, month_offset=0)),
    )
    assert result.deadline == "2026/10/31"


def test_day_of_month_rolls_to_next_month() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.DAY_OF_MONTH, day=15)),
    )
    assert result.deadline == "2026/11/15"
    assert "month_inferred_next_month" in result.warnings


def test_explicit_current_month_day_can_be_past() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(
                rule=DateRule.DAY_OF_MONTH,
                day=15,
                month_offset=0,
                month_explicit=True,
            )
        ),
    )
    assert result.deadline == "2026/10/15"
    assert "target_in_past" in result.warnings


def test_explicit_next_month_day() -> None:
    result = resolve_deadline(
        MEETING,
        ir(
            DateSpec(
                rule=DateRule.DAY_OF_MONTH,
                day=15,
                month_offset=1,
                month_explicit=True,
            )
        ),
    )
    assert result.deadline == "2026/11/15"


def test_all_day_ir_with_time_cue_is_rejected() -> None:
    result = resolve_deadline(
        MEETING,
        DeadlineIR(
            index=0,
            raw="明天下午",
            status="resolved",
            date=DateSpec(rule=DateRule.OFFSET_DAYS, amount=1),
            time=TimeSpec(rule=TimeRule.ALL_DAY),
        ),
    )
    assert result.deadline is None
    assert "time_rule=all_day" in (result.error or "")


def test_none_status_for_zhao_yidian_has_no_time_cue_error() -> None:
    result = resolve_deadline(
        MEETING,
        DeadlineIR(index=0, raw="早一点", status="none"),
    )
    assert result.deadline is None
    assert result.error is None


def test_none_status() -> None:
    result = resolve_deadline(
        MEETING,
        DeadlineIR(index=0, raw="待定", status="none"),
    )
    assert result.deadline is None
    assert result.kind == "none"
    assert result.error is None


def test_ambiguous_status_returns_error() -> None:
    result = resolve_deadline(
        MEETING,
        DeadlineIR(
            index=0,
            raw="下周某天",
            status="ambiguous",
            reason="无法确定具体日期",
        ),
    )
    assert result.deadline is None
    assert result.error == "无法确定具体日期"


def test_invalid_calendar_date_returns_error() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.MONTH_DAY, month=2, day=30)),
    )
    assert result.deadline is None
    assert result.error is not None


def test_bad_timezone_returns_error() -> None:
    result = resolve_deadline(
        MEETING,
        ir(DateSpec(rule=DateRule.OFFSET_DAYS, amount=1)),
        timezone="Not/AZone",
    )
    assert result.deadline is None
    assert "timezone" in (result.error or "")


def test_explicit_today_in_past_keeps_date_with_warning() -> None:
    late_meeting = datetime(2026, 10, 29, 16, 0, tzinfo=TZ)
    result = resolve_deadline(
        late_meeting,
        ir(
            DateSpec(rule=DateRule.SAME_DAY),
            TimeSpec(rule=TimeRule.EXACT, exact_time="15:00"),
        ),
    )
    assert result.deadline == "2026/10/29 15:00"
    assert "target_in_past" in result.warnings


def test_year_end_and_start() -> None:
    # 2026年底 -> 2026/12/31
    res1 = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.YEAR_END, year_offset=0)))
    assert res1.deadline == "2026/12/31"
    assert res1.kind == "date"

    # 2027年底 -> 2027/12/31
    res2 = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.YEAR_END, year_offset=1)))
    assert res2.deadline == "2027/12/31"

    # 2027年初 -> 2027/01/01
    res3 = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.YEAR_START, year_offset=1)))
    assert res3.deadline == "2027/01/01"


def test_quarter_start_and_target_quarter() -> None:
    # 2026/10/29 是 Q4，下季度初是明年 Q1 初 -> 2027/01/01
    res1 = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.QUARTER_START, quarter_offset=1)))
    assert res1.deadline == "2027/01/01"

    # 指定 Q4 末 -> 2026/12/31
    res2 = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.QUARTER_END, target_quarter=4)))
    assert res2.deadline == "2026/12/31"


def test_weekend_resolves_to_sunday() -> None:
    # 2026/10/29 是周四，本周末（周日）是 2026/11/01
    res = resolve_deadline(MEETING, ir(DateSpec(rule=DateRule.WEEKDAY, target_weekday=7, week_offset=0)))
    assert res.deadline == "2026/11/01"
    assert res.kind == "date"

def range_ir(start: DateSpec, end: DateSpec) -> DeadlineIR:
    return DeadlineIR(
        index=0,
        raw="range",
        status="resolved",
        range=DateRangeSpec(start=start, end=end),
    )


def test_week_window_range() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.SAME_DAY),
            DateSpec(rule=DateRule.OFFSET_WEEKS, amount=1),
        ),
    )
    assert result.kind == "range"
    assert result.deadline_start == "2026/10/29"
    assert result.deadline_end == "2026/11/05"
    assert result.deadline == "2026/11/05"


def test_current_week_window_ends_sunday() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.SAME_DAY),
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=7, week_offset=0),
        ),
    )
    assert result.deadline_start == "2026/10/29"
    assert result.deadline_end == "2026/11/01"
    assert result.kind == "range"


def test_explicit_weekday_range() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=0),
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=7, week_offset=0),
        ),
    )
    assert result.deadline_start == "2026/10/30"
    assert result.deadline_end == "2026/11/01"


def test_next_week_range() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=1, week_offset=1),
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=1),
        ),
    )
    assert result.deadline_start == "2026/11/02"
    assert result.deadline_end == "2026/11/06"


def test_next_month_day_range() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.DAY_OF_MONTH, day=15, month_offset=1, month_explicit=True),
            DateSpec(rule=DateRule.DAY_OF_MONTH, day=20, month_offset=1, month_explicit=True),
        ),
    )
    assert result.deadline_start == "2026/11/15"
    assert result.deadline_end == "2026/11/20"


def test_days_within_range() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.SAME_DAY),
            DateSpec(rule=DateRule.OFFSET_DAYS, amount=5),
        ),
    )
    assert result.deadline_start == "2026/10/29"
    assert result.deadline_end == "2026/11/03"
    assert result.kind == "range"


def test_inverted_range_returns_error() -> None:
    result = resolve_deadline(
        MEETING,
        range_ir(
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=5, week_offset=1),
            DateSpec(rule=DateRule.WEEKDAY, target_weekday=1, week_offset=1),
        ),
    )
    assert result.deadline is None
    assert result.kind == "none"
    assert result.error is not None

