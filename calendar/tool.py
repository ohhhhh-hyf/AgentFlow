"""确定性待办 DDL 解析 Tool。

输入：meeting_start_time + DeadlineIR
输出：严格标准化绝对时间 (%Y/%m/%d 或 %Y/%m/%d %H:%M) 与时段标记 (time_slot)

核心规范：
1. 扩展支持全周期节点（周末、月底、季度底 Q1~Q4、年底/年初 12/31 & 01/01）；
2. 时段任务（如“明天下午”、“周五下班前”）输出纯公历日期 + 中文 time_slot，不虚构 15:00；
3. 钟点任务（如“下午3点半”）输出具体时间点，kind 为 datetime；
4. 不读取当前系统时间（严格以 meeting_start_time 为原点）；
5. 纯确定性算法，单条异常结构化隔离，不中断批处理。
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import List, Tuple, Union, Optional
from zoneinfo import ZoneInfo

from models import (
    DateRule,
    DateSpec,
    DeadlineIR,
    ResolvedDeadline,
    TimeRule,
    TimeSlot,
    TimeSpec,
)

_TIMEZONE = ZoneInfo("Asia/Shanghai")
_DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$")

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)

# 模糊时段阈值判断（用于判断会议时刻是否已经晚于该时段，以此判断是否自动顺延至下一次）
_SLOT_THRESHOLDS = {
    TimeSlot.MORNING: time(12, 0),      # 上午在 12:00 后即视为过去
    TimeSlot.NOON: time(13, 0),         # 中午在 13:00 后即视为过去
    TimeSlot.AFTERNOON: time(18, 0),    # 下午在 18:00 后即视为过去
    TimeSlot.EOD: time(18, 0),          # 下班前在 18:00 后即视为过去
    TimeSlot.EVENING: time(23, 59),     # 晚上直到深夜
}

# 明确的时间点指示词
_TIME_CUES = (
    "上午", "中午", "下午", "晚上", "傍晚", "下班前", "早上", "凌晨", "午夜", "今晚", "明早",
    "明晚", "一早", "午休前", "下半天",
)
_TIME_POINT_RE = re.compile(
    r"(?:(?<!早)(?<!快)(?<!稍)(?<!多)(?<!少)(?<!好)(?<!慢)(?<!晚)(?<!差)(?<!有)(?<!微)(?<!第)"
    r"[零一二三四五六七八九十两]+|(?<!第)\d{1,2})\s*点(?!点)"
)
_MEETING_TIME_RE = re.compile(r"会[前后]\s*\d+.*(?:小时|分钟|刻|钟头)")
_MEETING_RELATIVE_DATE_RULES = {
    DateRule.SAME_DAY,
    DateRule.IMPLICIT_DATE,
}


def _has_time_cue(text: str) -> bool:
    """精准检查文本中是否包含具体时间或时段指示。"""
    return (
        any(cue in text for cue in _TIME_CUES)
        or bool(_TIME_POINT_RE.search(text))
        or bool(_MEETING_TIME_RE.search(text))
    )


def parse_meeting_start(
    value: Union[str, datetime],
    timezone: str = "Asia/Shanghai",
) -> datetime:
    """解析会议开始时间，并统一绑定指定时区。"""
    try:
        tz = ZoneInfo(timezone or "Asia/Shanghai")
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"非法 timezone：{timezone!r}") from exc

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("meeting_start_time 不能为空")
        parsed = None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
        if parsed is None:
            for fmt in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise ValueError(f"无法解析会议开始时间：{value!r}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _days_in_month(year: int, month: int) -> int:
    """获取指定年月的天数（天然支持闰年平年判定）。"""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    """月份数学加减运算。"""
    total = year * 12 + (month - 1) + delta
    new_year, new_month = divmod(total, 12)
    return new_year, new_month + 1


def _add_business_days(start: date, days: int) -> date:
    """工作日加减运算（跳过周六周日）。"""
    current = start
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining:
        current += timedelta(days=step)
        if current.isoweekday() <= 5:
            remaining -= 1
    return current


def _resolve_date(
    meeting_start: datetime,
    spec: DateSpec,
    warnings: List[str],
) -> date:
    meeting_date = meeting_start.date()

    if spec.rule == DateRule.OFFSET_DAYS:
        return meeting_date + timedelta(days=spec.amount)

    if spec.rule == DateRule.OFFSET_WORKDAYS:
        return _add_business_days(meeting_date, spec.amount)

    if spec.rule == DateRule.OFFSET_WEEKS:
        return meeting_date + timedelta(weeks=spec.amount)

    if spec.rule == DateRule.OFFSET_MONTHS:
        year, month = _add_months(
            meeting_date.year, meeting_date.month, spec.amount
        )
        day = min(meeting_date.day, _days_in_month(year, month))
        if day != meeting_date.day:
            warnings.append("day_clamped_to_month_end")
        return date(year, month, day)

    if spec.rule == DateRule.WEEKDAY:
        if spec.target_weekday is None:
            raise ValueError("weekday 规则缺少 target_weekday")
        monday = meeting_date - timedelta(days=meeting_date.isoweekday() - 1)
        if spec.week_offset is None:
            target = monday + timedelta(days=spec.target_weekday - 1)
            if target < meeting_date:
                target += timedelta(days=7)
                warnings.append("weekday_resolved_to_next_occurrence")
            return target
        target = monday + timedelta(
            weeks=spec.week_offset,
            days=spec.target_weekday - 1,
        )
        if target < meeting_date:
            warnings.append("target_in_past")
        return target

    if spec.rule == DateRule.MONTH_END:
        year, month = _add_months(
            meeting_date.year, meeting_date.month, spec.month_offset
        )
        return date(year, month, _days_in_month(year, month))

    if spec.rule == DateRule.MONTH_START:
        year, month = _add_months(
            meeting_date.year, meeting_date.month, spec.month_offset
        )
        return date(year, month, 1)

    # 季度初 (quarter_start)
    if spec.rule == DateRule.QUARTER_START:
        if spec.target_quarter is not None:
            q_month = (spec.target_quarter - 1) * 3 + 1
            target_year = spec.year if spec.year is not None else (meeting_date.year + spec.year_offset)
            if spec.year is None and spec.year_offset == 0 and date(target_year, q_month, 1) < meeting_date:
                target_year += 1
                warnings.append("year_inferred_next_year")
            return date(target_year, q_month, 1)
        quarter_start_month = ((meeting_date.month - 1) // 3) * 3 + 1
        month_delta = quarter_start_month - meeting_date.month + spec.quarter_offset * 3
        year, month = _add_months(meeting_date.year, meeting_date.month, month_delta)
        return date(year, month, 1)

    # 季度末 (quarter_end)
    if spec.rule == DateRule.QUARTER_END:
        if spec.target_quarter is not None:
            q_month = spec.target_quarter * 3
            target_year = spec.year if spec.year is not None else (meeting_date.year + spec.year_offset)
            if spec.year is None and spec.year_offset == 0 and date(target_year, q_month, _days_in_month(target_year, q_month)) < meeting_date:
                target_year += 1
                warnings.append("year_inferred_next_year")
            return date(target_year, q_month, _days_in_month(target_year, q_month))
        quarter_end_month = ((meeting_date.month - 1) // 3 + 1) * 3
        month_delta = (
            quarter_end_month - meeting_date.month + spec.quarter_offset * 3
        )
        year, month = _add_months(
            meeting_date.year, meeting_date.month, month_delta
        )
        return date(year, month, _days_in_month(year, month))

    # 年末/年底 (year_end -> 12/31)
    if spec.rule == DateRule.YEAR_END:
        target_year = spec.year if spec.year is not None else (meeting_date.year + spec.year_offset)
        return date(target_year, 12, 31)

    # 年初 (year_start -> 01/01)
    if spec.rule == DateRule.YEAR_START:
        target_year = spec.year if spec.year is not None else (meeting_date.year + spec.year_offset)
        return date(target_year, 1, 1)

    if spec.rule == DateRule.MONTH_DAY:
        if spec.month is None or spec.day is None:
            raise ValueError("month_day 规则缺少 month 或 day")
        if spec.year is not None:
            target = date(spec.year, spec.month, spec.day)
            if target < meeting_date:
                warnings.append("target_in_past")
            return target
        # 没有年份：寻找下一次合法出现（2月29日自动寻找下一个闰年）
        for year_delta in range(0, 9):
            year = meeting_date.year + year_delta
            try:
                target = date(year, spec.month, spec.day)
            except ValueError:
                continue
            if target >= meeting_date:
                if year_delta:
                    warnings.append("year_inferred_next_year")
                return target
        raise ValueError(
            f"month_day 日期不存在：{spec.month} 月 {spec.day} 日"
        )

    if spec.rule == DateRule.DAY_OF_MONTH:
        if spec.day is None:
            raise ValueError("day_of_month 规则缺少 day")
        if spec.month_explicit:
            year, month = _add_months(
                meeting_date.year, meeting_date.month, spec.month_offset
            )
            target = date(year, month, spec.day)
            if target < meeting_date:
                warnings.append("target_in_past")
            return target
        year = meeting_date.year
        month = meeting_date.month
        for month_delta in range(0, 13):
            if spec.day <= _days_in_month(year, month):
                target = date(year, month, spec.day)
                if target >= meeting_date:
                    if month_delta:
                        warnings.append("month_inferred_next_month")
                    return target
            year, month = _add_months(year, month, 1)
        raise ValueError(f"day_of_month 日期不存在：{spec.day} 号")

    if spec.rule in (DateRule.SAME_DAY, DateRule.IMPLICIT_DATE):
        return meeting_date

    raise ValueError(f"未知日期规则：{spec.rule}")


def _resolve_time(
    meeting_start: datetime,
    target_date: date,
    date_spec: DateSpec,
    time_spec: TimeSpec,
    warnings: List[str],
) -> Tuple[datetime, date, bool, Optional[str]]:
    """返回 (start_datetime, final_target_date, is_all_day, time_slot)。
    
    核心原则：
    - slot 模式（如“明天下午”）属于全天任务并标注中文 time_slot，不强加具体时分；
    - exact、midnight、relative 模式属于具体时间任务，kind 为 datetime。
    """
    tz = meeting_start.tzinfo or _TIMEZONE

    # 1. 纯全天日期
    if time_spec.rule == TimeRule.ALL_DAY:
        return datetime.combine(target_date, time.min, tzinfo=tz), target_date, True, None

    # 2. 模糊时段：全天日期 + 中文时段标签 (下午, 下班前等)
    if time_spec.rule == TimeRule.SLOT:
        slot_str = time_spec.slot.value if time_spec.slot else None
        final_date = target_date

        # 若目标日期正好是当天，且会议时刻已晚于该时段，判断是否顺延至下一次
        if final_date == meeting_start.date() and time_spec.slot:
            threshold = _SLOT_THRESHOLDS.get(time_spec.slot, time(18, 0))
            if meeting_start.time() > threshold:
                if date_spec.rule == DateRule.WEEKDAY and date_spec.week_offset is None:
                    final_date += timedelta(days=7)
                    warnings.append("weekday_resolved_to_next_occurrence")
                elif date_spec.rule == DateRule.IMPLICIT_DATE:
                    final_date += timedelta(days=1)
                    warnings.append("implicit_date_rolled_next_day")
                elif date_spec.rule != DateRule.IMPLICIT_DATE:
                    warnings.append("target_in_past")

        return datetime.combine(final_date, time.min, tzinfo=tz), final_date, True, slot_str

    # 3. 会前/会后 (微调具体分钟)
    if time_spec.rule == TimeRule.RELATIVE_MEETING:
        if date_spec.rule not in _MEETING_RELATIVE_DATE_RULES:
            raise ValueError(
                "relative_meeting 只支持 same_day / implicit_date 日期规则"
            )
        start = meeting_start + timedelta(minutes=time_spec.offset_minutes)
        return start, start.date(), False, None

    # 4. 明确点钟 (HH:MM)
    if time_spec.rule == TimeRule.EXACT:
        if not time_spec.exact_time:
            raise ValueError("exact 规则缺少 exact_time")
        hour, minute = map(int, time_spec.exact_time.split(":"))
        start = datetime.combine(target_date, time(hour, minute), tzinfo=tz)
    # 5. 午夜跨天 (次日 00:00)
    elif time_spec.rule == TimeRule.MIDNIGHT:
        start = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=tz)
    else:
        raise ValueError(f"未知时间规则：{time_spec.rule}")

    start += timedelta(minutes=time_spec.offset_minutes)

    if date_spec.rule == DateRule.IMPLICIT_DATE and start < meeting_start:
        start += timedelta(days=1)
        warnings.append("implicit_date_rolled_next_day")
    elif (
        date_spec.rule == DateRule.WEEKDAY
        and date_spec.week_offset is None
        and start < meeting_start
    ):
        start += timedelta(days=7)
        warnings.append("weekday_resolved_to_next_occurrence")
    elif date_spec.rule != DateRule.IMPLICIT_DATE and start < meeting_start:
        warnings.append("target_in_past")

    return start, start.date(), False, None


def _resolve_range(
    meeting_start: datetime,
    range_spec,
    warnings: List[str],
) -> Tuple[str, str]:
    start_date = _resolve_date(meeting_start, range_spec.start, warnings)
    end_date = _resolve_date(meeting_start, range_spec.end, warnings)
    if end_date < start_date:
        raise ValueError(f"范围结束日期早于开始日期：{start_date} > {end_date}")
    if end_date < meeting_start.date():
        if "target_in_past" not in warnings:
            warnings.append("target_in_past")
    elif start_date < meeting_start.date():
        if "range_start_in_past" not in warnings:
            warnings.append("range_start_in_past")
    start_text = start_date.strftime("%Y/%m/%d")
    end_text = end_date.strftime("%Y/%m/%d")
    if not _DATE_RE.fullmatch(start_text) or not _DATE_RE.fullmatch(end_text):
        raise ValueError("范围日期格式异常")
    warnings[:] = list(dict.fromkeys(warnings))
    return start_text, end_text


def resolve_deadline(
    meeting_start: Union[str, datetime],
    ir: DeadlineIR,
    timezone: str = "Asia/Shanghai",
) -> ResolvedDeadline:
    """解析单条 deadline。任何异常都转成结构化 error。"""
    if ir.status == "none":
        if _has_time_cue(ir.raw):
            return ResolvedDeadline(
                index=ir.index,
                raw=ir.raw,
                deadline=None,
                time_slot=None,
                kind="none",
                warnings=list(ir.assumptions),
                error="原文包含时间表达，但 Agent 返回 status=none",
            )
        return ResolvedDeadline(
            index=ir.index,
            raw=ir.raw,
            deadline=None,
            time_slot=None,
            kind="none",
            warnings=[],
            error=None,
        )
    if ir.status == "ambiguous":
        return ResolvedDeadline(
            index=ir.index,
            raw=ir.raw,
            deadline=None,
            time_slot=None,
            kind="none",
            warnings=list(ir.assumptions),
            error=ir.reason or "deadline expression is ambiguous",
        )
    if ir.time.rule == TimeRule.ALL_DAY and _has_time_cue(ir.raw):
        return ResolvedDeadline(
            index=ir.index,
            raw=ir.raw,
            deadline=None,
            time_slot=None,
            kind="none",
            warnings=list(ir.assumptions),
            error="原文包含时间表达，但 Agent 返回 time_rule=all_day",
        )

    warnings = list(ir.assumptions)
    try:
        meeting = parse_meeting_start(meeting_start, timezone)
        if ir.range is not None:
            start_text, end_text = _resolve_range(meeting, ir.range, warnings)
            return ResolvedDeadline(
                index=ir.index,
                raw=ir.raw,
                deadline=end_text,
                deadline_start=start_text,
                deadline_end=end_text,
                time_slot=None,
                kind="range",
                warnings=warnings,
                error=None,
            )
        if ir.date is None:
            raise ValueError("resolved 状态缺少 date")

        target_date = _resolve_date(meeting, ir.date, warnings)
        start, final_date, is_all_day, time_slot = _resolve_time(
            meeting, target_date, ir.date, ir.time, warnings
        )

        if is_all_day:
            deadline = final_date.strftime("%Y/%m/%d")
            kind = "date"
            if final_date < meeting.date() and "target_in_past" not in warnings:
                warnings.append("target_in_past")
            if not _DATE_RE.fullmatch(deadline):
                raise ValueError(f"日期格式异常：{deadline!r}")
        else:
            deadline = start.strftime("%Y/%m/%d %H:%M")
            kind = "datetime"
            if not _DATETIME_RE.fullmatch(deadline):
                raise ValueError(f"日期时间格式异常：{deadline!r}")

        return ResolvedDeadline(
            index=ir.index,
            raw=ir.raw,
            deadline=deadline,
            time_slot=time_slot,
            kind=kind,
            warnings=warnings,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        return ResolvedDeadline(
            index=ir.index,
            raw=ir.raw,
            deadline=None,
            time_slot=None,
            kind="none",
            warnings=warnings,
            error=str(exc),
        )


def resolve_deadlines(
    meeting_start: Union[str, datetime],
    irs: List[DeadlineIR],
    timezone: str = "Asia/Shanghai",
) -> List[ResolvedDeadline]:
    """批量解析，保持输入顺序。"""
    return [resolve_deadline(meeting_start, ir, timezone) for ir in irs]


__all__ = [
    "parse_meeting_start",
    "resolve_deadline",
    "resolve_deadlines",
]
