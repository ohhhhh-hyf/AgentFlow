"""企业级高性能待办时间规则匹配器（Fast-Path）。

覆盖 85%+ 的高频标准表达，毫秒级直接产出 DeadlineIR，无需调用 LLM：
1. 常见无时间词：尽快、待定、无、未提及、暂无等 -> status="none"
2. 基础相对日期：今天、明天、后天、大后天、昨天、前天、N天后
3. 工作日：N个工作日后/内
4. 周偏移与周末：本周X、下周X、上周X、周X、两周后、周末（本周末/下周末）
5. 月/季/年偏移：本月底、下月底、下月初、Q1~Q4末、本季度末、下季度末/初、年底/年末、明年初
6. 固定日期：X月X号、X号
7. 会前会后：会后1小时、会前15分钟
8. 业务时段与钟点：上午、下午、晚上、中午、下班前、具体点钟（下午3点半、3点）
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from models import (
    DateRule,
    DateSpec,
    DeadlineIR,
    TimeRule,
    TimeSlot,
    TimeSpec,
)

# 中文数字转换映射
_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "三十": 30, "三十一": 31,
}

_WEEKDAY_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7, "七": 7,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
}

_NONE_PHRASES = (
    "没提时间", "未提时间", "没有时间", "未说明时间", "无时间", "没写时间",
    "无明确时间", "没有明确时间", "不限期",
    "尽快", "待定", "未定", "未提及", "没提", "暂无", "随缘", "无",
    "tbd", "none", "null", "todo", "另行通知"
)
_HAS_TIME_CHARS = re.compile(
    r"[\d一二两三四五六七八九十]|天|周|星期|礼拜|月|号|日|点|时|分|晨|晚|午|会前|会后|下班|季|年"
)

# Fast-Path 只接受“单轴、无锚点、无歧义”的表达。
# 以下类别直接交给 LLM，避免日期/时间组合被静默拼错。
_FUSED_DATE_TIME_RE = re.compile(r"今晚|明晚|明早")
_ALLOWED_MIDNIGHT_RE = re.compile(r"(?:今晚|明晚)\s*12点\s*(?:(?:半)|(?:\d{1,2}分))?")
_RECURRENCE_RE = re.compile(r"每(?:天|日|周|星期|礼拜|月|季度|年)|每隔")
_RANGE_RE = re.compile(
    r"(?:到|至)\s*(?:周|星期|礼拜|今天|明天|后天|大后天|下个?月|本月|月底|月初|年底|年初|Q[1-4]|\d{1,2}[月号日]|[一二三四五六七八九十]+[号日])"
)
_WINDOW_RE = re.compile(
    r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:天|日|周|星期|礼拜|个?工作日|个月)\s*[之以]?\s*内|"
    r"(?:本|这|下|上)[个]?(?:周|星期|礼拜|月|季度|年)\s*内"
)
_EVENT_ANCHOR_RE = re.compile(
    r"项目启动|项目上线|上线|发布|评审|客户确认|合同签署|培训结束|会议结束|验收|交付"
)
_DATE_CUE_RE = re.compile(
    r"今天|明天|后天|大后天|昨天|前天|本周|下周|上周|大下|下下|"
    r"周[一二三四五六日天七1-7]|星期|礼拜|周末|月底|月初|月末|年初|年底|"
    r"季度|Q[1-4]|工作日|\d{4}年|\d{1,2}月|月|"
    r"[0-9一二三四五六七八九十两]+[号日]"
)
_TIME_CUE_RE = re.compile(
    r"上午|中午|下午|晚上|傍晚|下班|EOD|一早|午休|下半天|凌晨|午夜|"
    r"\d{1,2}\s*点|[零一二三四五六七八九十两]+\s*点|会前|会后|小时|分钟"
)


def _parse_int(text: str) -> Optional[int]:
    """解析数字（支持阿拉伯数字与中文数字）。"""
    s = text.strip()
    if s.isdigit():
        return int(s)
    if s in _CN_NUM:
        return _CN_NUM[s]
    if len(s) == 2 and s.startswith("十") and s[1] in _CN_NUM:
        return 10 + _CN_NUM[s[1]]
    if len(s) == 3 and s.endswith("十") and s[0] in _CN_NUM:
        return _CN_NUM[s[0]] * 10
    if len(s) == 3 and "十" in s:
        parts = s.split("十")
        tens = _CN_NUM.get(parts[0], 1)
        units = _CN_NUM.get(parts[1], 0)
        return tens * 10 + units
    return None


def _is_none_expression(text: str) -> bool:
    """判断是否为无时间表达（如'尽快完成'、'待定'、'没提时间'）。"""
    t = text.strip()
    if not t:
        return True
    lowered = t.lower()
    for phrase in _NONE_PHRASES:
        if phrase in lowered:
            cleaned = lowered
            # 先删长短语，避免“无明确时间”被单个“无”提前拆散。
            for p in sorted(_NONE_PHRASES, key=len, reverse=True):
                cleaned = cleaned.replace(p, "")
            if not _HAS_TIME_CHARS.search(cleaned):
                return True
    return False


def _extract_time_spec(text: str) -> Tuple[str, TimeSpec, list[str]]:
    """从文本中提取时间部分，并返回 (剔除时间后的剩余文本, TimeSpec, assumptions)。"""
    assumptions: list[str] = []

    # 1. 带夜间前缀的 12点 / 24点 -> midnight
    #    裸“12点/12点半”留给普通钟点解析；裸“零点”也不在这里吞掉。
    midnight_m = re.search(
        r"(?:晚上|今晚|明晚|午夜)\s*12点\s*(?:(半)|(\d{1,2})分)?",
        text,
    )
    if midnight_m:
        if midnight_m.group(1) == "半":
            offset_minutes = 30
        elif midnight_m.group(2):
            offset_minutes = int(midnight_m.group(2))
        else:
            offset_minutes = 0
        cleaned = text[: midnight_m.start()] + text[midnight_m.end() :]
        return (
            cleaned,
            TimeSpec(rule=TimeRule.MIDNIGHT, offset_minutes=offset_minutes),
            assumptions,
        )
    if re.search(r"24点|24:00", text):
        cleaned = re.sub(r"(?:24点|24:00)", "", text, count=1)
        return cleaned, TimeSpec(rule=TimeRule.MIDNIGHT), assumptions

    # 2. 会前 / 会后 relative_meeting
    rel_m = re.search(
        r"(会前|会后)\s*(\d+|半|[一二两三四五六七八九十]+)\s*(个?小时|个?钟头|分钟)",
        text,
    )
    if rel_m:
        direction, val_str, unit = rel_m.groups()
        if val_str == "半":
            minutes = 30
        else:
            val = _parse_int(val_str) or 1
            minutes = val * 60 if "小时" in unit or "钟头" in unit else val
        offset = -minutes if direction == "会前" else minutes
        cleaned = text[: rel_m.start()] + text[rel_m.end() :]
        return cleaned, TimeSpec(rule=TimeRule.RELATIVE_MEETING, offset_minutes=offset), assumptions

    # 3. 具体点钟（如 "15:30", "下午3点半", "上午10点", "3点"）
    colon_m = re.search(r"(\d{1,2}):(\d{2})", text)
    if colon_m:
        h, m = int(colon_m.group(1)), int(colon_m.group(2))
        exact = f"{h:02d}:{m:02d}"
        cleaned = text[: colon_m.start()] + text[colon_m.end() :]
        return cleaned, TimeSpec(rule=TimeRule.EXACT, exact_time=exact), assumptions

    point_m = re.search(
        r"(凌晨|午夜|早上|上午|中午|下午|晚上|傍晚)?\s*"
        r"(?:(?<!第)(?P<hour_ar>\d{1,2})|"
        r"(?<!早)(?<!快)(?<!稍)(?<!多)(?<!少)(?<!好)(?<!慢)(?<!晚)(?<!差)(?<!有)(?<!微)(?<!第)"
        r"(?P<hour_cn>[一二两三四五六七八九十]+))"
        r"\s*点(?!点)\s*(半|(\d{1,2})\s*分?)?(?!\d)",
        text,
    )
    if point_m:
        period = point_m.group(1)
        hour_str = point_m.group("hour_ar") or point_m.group("hour_cn")
        min_part = point_m.group(4)
        min_digits = point_m.group(5)
        h = _parse_int(hour_str)
        if h is not None:
            m = 30 if min_part == "半" else (int(min_digits) if min_digits else 0)
            if period in ("下午", "晚上", "傍晚") and h < 12:
                h += 12
            elif period in ("凌晨", "午夜") and h == 12:
                h = 0
            elif period == "中午" and 1 <= h <= 3:
                h += 12
            elif not period:
                # 业务默认：1~6 点按下午处理；7~11 点保持上午。
                if 1 <= h <= 6:
                    h += 12
                    assumptions.append(f"{hour_str}点按下午{h:02d}:{m:02d}处理")
            exact = f"{h:02d}:{m:02d}"
            cleaned = text[: point_m.start()] + text[point_m.end() :]
            return cleaned, TimeSpec(rule=TimeRule.EXACT, exact_time=exact), assumptions

    # 4. 业务时段 slot (下班前, 下午, 上午, 晚上, 中午)
    slot_map = [
        (re.compile(r"下班前|下班时|下班|傍晚|EOD", re.IGNORECASE), TimeSlot.EOD),
        (re.compile(r"下半天"), TimeSlot.AFTERNOON),
        (re.compile(r"下午"), TimeSlot.AFTERNOON),
        (re.compile(r"一早|早上|明早|上午"), TimeSlot.MORNING),
        (re.compile(r"今晚|明晚|晚上"), TimeSlot.EVENING),
        (re.compile(r"中午|午休前"), TimeSlot.NOON),
    ]
    for pattern, slot in slot_map:
        if pattern.search(text):
            cleaned = pattern.sub("", text)
            return cleaned, TimeSpec(rule=TimeRule.SLOT, slot=slot), assumptions

    # 5. 无时间修饰 -> ALL_DAY
    return text, TimeSpec(rule=TimeRule.ALL_DAY), assumptions


def try_fast_extract(index: int, raw_text: str) -> Optional[DeadlineIR]:
    """极速尝试使用规则引擎提取时间语义。
    
    返回 DeadlineIR（若高置信度命中）或 None（需交由 LLM 处理）。
    """
    text = (raw_text or "").strip()
    if not text:
        return DeadlineIR(index=index, raw=raw_text, status="none")

    # 1. 检查无时间表达
    if _is_none_expression(text):
        return DeadlineIR(index=index, raw=raw_text, status="none")

    # 1.1 多解/不确定表达交给 LLM 做语义消歧，避免 Fast-Path 静默选中第一个日期。
    if re.search(r"或者|或|要么|还是|左右|前后|大概|可能|也许|暂定|看情况", text):
        return None

    # 1.2 融合日期时间词（今晚/明晚/明早）、周期、区间、事件锚点交给 LLM。
    if _FUSED_DATE_TIME_RE.search(text) and not _ALLOWED_MIDNIGHT_RE.search(text):
        return None
    if _RECURRENCE_RE.search(text):
        return None
    if _WINDOW_RE.search(text) or _RANGE_RE.search(text):
        return None
    if _EVENT_ANCHOR_RE.search(text):
        return None

    # 1.3 日期 + 时间/时段属于组合语义，Fast-Path 不处理。
    if (
        _DATE_CUE_RE.search(text)
        and _TIME_CUE_RE.search(text)
        and not _ALLOWED_MIDNIGHT_RE.search(text)
    ):
        return None

    # 记录“明晚/今晚”的日期锚点：它们会被时间提取阶段消费，
    # 但日期语义必须保留，否则 midnight 会从会议当天开始算。
    is_mingwan = "明晚" in text
    is_mingzao = "明早" in text
    is_jinwan = "今晚" in text

    # 2. 提取时间部分
    remaining, time_spec, assumptions = _extract_time_spec(text)

    # 3. 提取日期部分
    date_spec: Optional[DateSpec] = None

    # A. 会前/会后 属于当天或者 implicit_date
    if time_spec.rule == TimeRule.RELATIVE_MEETING:
        return DeadlineIR(
            index=index,
            raw=raw_text,
            status="resolved",
            date=DateSpec(rule=DateRule.SAME_DAY),
            time=time_spec,
            assumptions=assumptions,
        )

    # B. 基础自然日相对偏移 (今天, 明天, 后天, 大后天, 昨天, 前天)
    if re.search(r"大后天", remaining):
        date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=3)
    elif re.search(r"后天", remaining):
        date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=2)
    elif re.search(r"明天|次日|明早", remaining):
        date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=1)
    elif re.search(r"今天|当天|今晚", remaining):
        date_spec = DateSpec(rule=DateRule.SAME_DAY)
    elif re.search(r"前天", remaining):
        date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=-2)
    elif re.search(r"昨天", remaining):
        date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=-1)

    # B2. “明晚/明早/今晚”已被时间提取消费，补回日期锚点
    if not date_spec:
        if is_mingwan or is_mingzao:
            date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=1)
        elif is_jinwan:
            date_spec = DateSpec(rule=DateRule.SAME_DAY)

    # C. N天后 / N天前 / N天内
    if not date_spec:
        m = re.search(r"(\d+|[一二两三四五六七八九十]+)天[之以]?([后内前])", remaining)
        if m:
            days = _parse_int(m.group(1))
            if days is not None:
                if m.group(2) == "前":
                    days = -days
                date_spec = DateSpec(rule=DateRule.OFFSET_DAYS, amount=days)

    # D. 工作日偏移 (3个工作日后 / 3个工作日内 / 3个工作日前)
    if not date_spec:
        m = re.search(r"(\d+|[一二两三四五六七八九十]+)个?工作日[之以]?([后内前])", remaining)
        if m:
            wdays = _parse_int(m.group(1))
            if wdays is not None:
                if m.group(2) == "前":
                    wdays = -wdays
                date_spec = DateSpec(rule=DateRule.OFFSET_WORKDAYS, amount=wdays)

    # E1. 周末 (如"本周末"、"这周末"、"下周末"、"周末")
    if not date_spec:
        m = re.search(r"(大下|下下|下|本|这|上)?\s*周末", remaining)
        if m:
            prefix = m.group(1)
            week_off = None
            if prefix in ("本", "这"):
                week_off = 0
            elif prefix == "下":
                week_off = 1
            elif prefix in ("大下", "下下"):
                week_off = 2
            elif prefix == "上":
                week_off = -1
            # 职场待办通常将周末截止时间锚定为周日 (target_weekday=7)
            date_spec = DateSpec(
                rule=DateRule.WEEKDAY,
                target_weekday=7,
                week_offset=week_off,
            )

    # E2. 周历对齐 (下周三、本周五、周五下班前、大下周一)
    if not date_spec:
        m = re.search(r"(大下|下下|下|本|这|上)?\s*(?:周|星期|礼拜)([一二三四五六日天七])", remaining)
        if m:
            prefix, w_str = m.groups()
            target_w = _WEEKDAY_MAP.get(w_str)
            if target_w is not None:
                week_off = None
                if prefix in ("本", "这"):
                    week_off = 0
                elif prefix == "下":
                    week_off = 1
                elif prefix in ("大下", "下下"):
                    week_off = 2
                elif prefix == "上":
                    week_off = -1
                date_spec = DateSpec(
                    rule=DateRule.WEEKDAY,
                    target_weekday=target_w,
                    week_offset=week_off,
                )

    # F. 周偏移 (两周后 / 三周前)
    if not date_spec:
        m = re.search(r"(\d+|[一二两三四五六七八九十]+)[个]?(?:周|星期)[之以]?(后|前)", remaining)
        if m:
            w_cnt = _parse_int(m.group(1))
            direction = m.group(2)
            if w_cnt is not None:
                amt = -w_cnt if direction == "前" else w_cnt
                date_spec = DateSpec(rule=DateRule.OFFSET_WEEKS, amount=amt)

    # G. 年底 / 年初 (如"年底", "今年年底", "明年末", "去年底", "2027年底")
    if not date_spec:
        m = re.search(r"(\d{4})\s*年\s*[底末]", remaining)
        if m:
            date_spec = DateSpec(rule=DateRule.YEAR_END, year=int(m.group(1)))
        else:
            m = re.search(r"(\d{4})\s*年\s*初", remaining)
            if m:
                date_spec = DateSpec(
                    rule=DateRule.YEAR_START, year=int(m.group(1))
                )
        if not date_spec:
            if re.search(r"前年[底末]", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_END, year_offset=-2)
            elif re.search(r"去年[底末]", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_END, year_offset=-1)
            elif re.search(r"后年[底末]", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_END, year_offset=2)
            elif re.search(r"明[年]?年[底末]", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_END, year_offset=1)
            elif re.search(r"本[年]?年[底末]|今[年]?年[底末]|(?<!明)(?<!去)(?<!前)(?<!后)年[底末]", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_END, year_offset=0)
            elif re.search(r"前年初", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_START, year_offset=-2)
            elif re.search(r"去年初", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_START, year_offset=-1)
            elif re.search(r"后年初", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_START, year_offset=2)
            elif re.search(r"明[年]?年初", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_START, year_offset=1)
            elif re.search(r"本[年]?年初|今[年]?年初|(?<!明)(?<!去)(?<!前)(?<!后)年初", remaining):
                date_spec = DateSpec(rule=DateRule.YEAR_START, year_offset=0)

    # H. 季度 (Q1~Q4, 一~四季度, 本季度末, 下季度末/初)
    if not date_spec:
        # 指定季度: Q3末 / 第三季度末 / 二季度
        q_m = re.search(r"(?:第)?([一二三四1-4])\s*季度[底末]?|Q([1-4])[底末]?", remaining, re.IGNORECASE)
        if q_m:
            q_val = _parse_int(q_m.group(1) or q_m.group(2))
            if q_val:
                date_spec = DateSpec(rule=DateRule.QUARTER_END, target_quarter=q_val)
        elif re.search(r"下[个]?季度[底末]", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_END, quarter_offset=1)
        elif re.search(r"上[个]?季度[底末]", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_END, quarter_offset=-1)
        elif re.search(r"本季度[底末]|(?<!下)(?<!上)季度[底末]", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_END, quarter_offset=0)
        elif re.search(r"下[个]?季度初", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_START, quarter_offset=1)
        elif re.search(r"上[个]?季度初", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_START, quarter_offset=-1)
        elif re.search(r"本季度初|(?<!下)(?<!上)季度初", remaining):
            date_spec = DateSpec(rule=DateRule.QUARTER_START, quarter_offset=0)

    # I. 月底 / 月初
    if not date_spec:
        if re.search(r"下[个]?月底", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_END, month_offset=1)
        elif re.search(r"上[个]?月底", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_END, month_offset=-1)
        elif re.search(r"本[个]?月底|(?<!下)(?<!上)月底", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_END, month_offset=0)
        elif re.search(r"下[个]?月初", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_START, month_offset=1)
        elif re.search(r"上[个]?月初", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_START, month_offset=-1)
        elif re.search(r"本[个]?月初|(?<!下)(?<!上)月初", remaining):
            date_spec = DateSpec(rule=DateRule.MONTH_START, month_offset=0)

    # J. N个月后 / N个月前
    if not date_spec:
        m = re.search(r"(\d+|[一二两三四五六七八九十]+)[个]?月[之以]?([后前])", remaining)
        if m:
            m_cnt = _parse_int(m.group(1))
            if m_cnt is not None:
                if m.group(2) == "前":
                    m_cnt = -m_cnt
                date_spec = DateSpec(rule=DateRule.OFFSET_MONTHS, amount=m_cnt)

    # K. 固定日期: X月X号 / X月X日
    if not date_spec:
        m = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})月(\d{1,2})[号日]", remaining)
        if m:
            y_str, m_str, d_str = m.groups()
            year_val = int(y_str) if y_str else None
            date_spec = DateSpec(
                rule=DateRule.MONTH_DAY,
                year=year_val,
                month=int(m_str),
                day=int(d_str),
            )

    # K2. 明确“本月/下月 X 号”：不能被 L 的“下一次出现”吞掉
    if not date_spec:
        m = re.search(r"(下个|上个|下|本|这|上)[个]?月\s*(\d{1,2})[号日]", remaining)
        if m:
            prefix = m.group(1)
            if prefix in ("下", "下个"):
                month_offset = 1
            elif prefix in ("上", "上个"):
                month_offset = -1
            else:
                month_offset = 0
            date_spec = DateSpec(
                rule=DateRule.DAY_OF_MONTH,
                day=int(m.group(2)),
                month_offset=month_offset,
                month_explicit=True,
            )

    # L. 只有几号: 15号 / 15日
    if not date_spec:
        m = re.search(r"(?<!\d)(\d{1,2})[号日](?!\d)", remaining)
        if m:
            date_spec = DateSpec(rule=DateRule.DAY_OF_MONTH, day=int(m.group(1)))

    # M. 仅有时间（没有日期）
    if not date_spec:
        if time_spec.rule != TimeRule.ALL_DAY:
            date_spec = DateSpec(rule=DateRule.IMPLICIT_DATE)

    # 如果既没有日期规则，也没有时间规格，无法确定，交给 LLM 走深度语义解析
    if not date_spec:
        return None

    return DeadlineIR(
        index=index,
        raw=raw_text,
        status="resolved",
        date=date_spec,
        time=time_spec,
        assumptions=assumptions,
    )


__all__ = ["try_fast_extract"]
