"""时间语义 IR 与最终结果模型。

设计原则：
- 支持“极致扁平化（Sparse IR）”与“传统嵌套”双模式；
- 大模型仅需输出有效键，严禁输出大批冗余 null；
- 内部自动双向转换与归一化，保证严格类型安全。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DateRule(str, Enum):
    """日期规则枚举。"""

    OFFSET_DAYS = "offset_days"          # 相对自然日（明天=1，后天=2，昨天=-1）
    OFFSET_WORKDAYS = "offset_workdays"  # 相对工作日（跳过周末，3个工作日后=3）
    OFFSET_WEEKS = "offset_weeks"        # 相对整周（两周后=2）
    OFFSET_MONTHS = "offset_months"      # 相对整月（三个月后=3）
    WEEKDAY = "weekday"                  # 星期几（1=周一 ... 7=周日/周末）
    MONTH_END = "month_end"              # 月底（本月=0，下月=1）
    MONTH_START = "month_start"          # 月初（下月初=1）
    QUARTER_END = "quarter_end"          # 季度末（本季=0，下季=1，或指定 target_quarter 1~4）
    QUARTER_START = "quarter_start"      # 季度初（本季=0，下季=1）
    YEAR_END = "year_end"                # 年末/年底（本年=0，明年=1，固定为12/31）
    YEAR_START = "year_start"            # 年初（本年=0，明年=1，固定为01/01）
    MONTH_DAY = "month_day"              # 明确月日（10月1号）
    DAY_OF_MONTH = "day_of_month"        # 只有几号（15号）
    SAME_DAY = "same_day"                # 当天（今天、今晚）
    IMPLICIT_DATE = "implicit_date"      # 仅有具体时间，日期缺省


class TimeRule(str, Enum):
    """时间规则枚举。"""

    ALL_DAY = "all_day"                  # 纯日期，全天
    EXACT = "exact"                      # 明确点钟（HH:MM）
    SLOT = "slot"                        # 业务模糊时段（上午、下午等）
    MIDNIGHT = "midnight"                # 午夜24点（跨到次日00:00）
    RELATIVE_MEETING = "relative_meeting"# 会议相对时间（会前/会后若干分钟）


class TimeSlot(str, Enum):
    """职场标准模糊时段（直接规范为中文）。"""

    MORNING = "上午"
    NOON = "中午"
    AFTERNOON = "下午"
    EVENING = "晚上"
    EOD = "下班前"

    @classmethod
    def from_value(cls, val: Optional[str]) -> Optional["TimeSlot"]:
        if not val:
            return None
        v = str(val).strip().lower()
        mapping = {
            "morning": cls.MORNING, "上午": cls.MORNING, "早上": cls.MORNING, "明早": cls.MORNING,
            "noon": cls.NOON, "中午": cls.NOON,
            "afternoon": cls.AFTERNOON, "下午": cls.AFTERNOON,
            "evening": cls.EVENING, "晚上": cls.EVENING, "今晚": cls.EVENING,
            "eod": cls.EOD, "下班前": cls.EOD, "傍晚": cls.EOD, "下班": cls.EOD,
        }
        return mapping.get(v, None)


class DateSpec(BaseModel):
    """日期语义规格。"""

    model_config = ConfigDict(extra="ignore")

    rule: DateRule
    amount: int = 0
    target_weekday: Optional[int] = Field(None, ge=1, le=7)
    week_offset: Optional[int] = None
    month: Optional[int] = Field(None, ge=1, le=12)
    day: Optional[int] = Field(None, ge=1, le=31)
    year: Optional[int] = Field(None, ge=1970, le=2100)
    month_offset: int = 0
    month_explicit: bool = Field(
        False, description="day_of_month 是否明确指定本月/下月；false 表示下一次出现"
    )
    quarter_offset: int = 0
    target_quarter: Optional[int] = Field(None, ge=1, le=4, description="指定季度1~4 (Q1~Q4)")
    year_offset: int = 0

    @model_validator(mode="after")
    def validate_rule_fields(self) -> "DateSpec":
        if self.rule == DateRule.WEEKDAY and self.target_weekday is None:
            raise ValueError("weekday 规则必须提供 target_weekday")
        if self.rule == DateRule.MONTH_DAY and (self.month is None or self.day is None):
            raise ValueError("month_day 规则必须提供 month 和 day")
        if self.rule == DateRule.DAY_OF_MONTH and self.day is None:
            raise ValueError("day_of_month 规则必须提供 day")
        return self


class DateRangeSpec(BaseModel):
    """日期范围：两个端点都使用 DateSpec，范围本身不含时间。"""

    model_config = ConfigDict(extra="ignore")

    start: DateSpec
    end: DateSpec


class TimeSpec(BaseModel):
    """时间语义规格。"""

    model_config = ConfigDict(extra="ignore")

    rule: TimeRule = TimeRule.ALL_DAY
    exact_time: Optional[str] = Field(None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    slot: Optional[TimeSlot] = None
    offset_minutes: int = 0

    @field_validator("slot", mode="before")
    @classmethod
    def normalize_slot(cls, v: Any) -> Optional[TimeSlot]:
        if isinstance(v, TimeSlot):
            return v
        if isinstance(v, str):
            res = TimeSlot.from_value(v)
            if res:
                return res
        return None

    @model_validator(mode="after")
    def validate_rule_fields(self) -> "TimeSpec":
        if self.rule == TimeRule.EXACT:
            if not self.exact_time:
                raise ValueError("exact 规则必须提供 exact_time (HH:MM)")
        elif self.rule == TimeRule.SLOT:
            if self.slot is None:
                raise ValueError("slot 规则必须提供 slot")
        elif self.rule == TimeRule.RELATIVE_MEETING:
            if self.offset_minutes == 0:
                raise ValueError("relative_meeting 规则必须提供非零 offset_minutes")
        return self


class DeadlineIR(BaseModel):
    """单条截止时间的语义 IR。
    
    支持轻量扁平输入（大模型首选），也向下兼容嵌套输入。
    """

    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0, description="输入项下标")
    raw: str = Field(default="", description="原始文本")
    status: Literal["resolved", "ambiguous", "none"] = "resolved"

    # 扁平化属性（优先读取）
    rule: Optional[DateRule] = None
    amount: int = 0
    target_weekday: Optional[int] = None
    week_offset: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    year: Optional[int] = None
    month_offset: int = 0
    month_explicit: bool = False
    quarter_offset: int = 0
    target_quarter: Optional[int] = None
    year_offset: int = 0

    exact_time: Optional[str] = None
    slot: Optional[TimeSlot] = None
    offset_minutes: int = 0
    is_midnight: bool = False
    time_rule: Optional[TimeRule] = None

    # 结构化容器（保证与下游 Tool 100% 兼容）
    date: Optional[DateSpec] = None
    range: Optional[DateRangeSpec] = None
    # 多个候选范围（如“这周或下周初”）；由 Tool 按相邻/小间隔合并为一个保守范围
    candidate_ranges: List[DateRangeSpec] = Field(default_factory=list)
    time: TimeSpec = Field(default_factory=TimeSpec)

    reason: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unify_flat_input(cls, data: Any) -> Any:
        """核心魔法：当大模型输出扁平稀疏 JSON 时，自动合成标准的 date 与 time 对象。"""
        if not isinstance(data, dict):
            return data

        # 1. 扁平日期字段转换
        if "date" not in data and "rule" in data and data["rule"]:
            data["date"] = {
                "rule": data["rule"],
                "amount": data.get("amount", 0),
                "target_weekday": data.get("target_weekday"),
                "week_offset": data.get("week_offset"),
                "month": data.get("month"),
                "day": data.get("day"),
                "year": data.get("year"),
                "month_offset": data.get("month_offset", 0),
                "month_explicit": data.get("month_explicit", False),
                "quarter_offset": data.get("quarter_offset", 0),
                "target_quarter": data.get("target_quarter"),
                "year_offset": data.get("year_offset", 0),
            }

        # 2. 扁平时间字段转换
        if "time" not in data:
            time_dict: dict = {}
            if data.get("is_midnight"):
                time_dict["rule"] = TimeRule.MIDNIGHT
            elif data.get("exact_time"):
                time_dict["rule"] = TimeRule.EXACT
                time_dict["exact_time"] = data["exact_time"]
            elif data.get("slot"):
                time_dict["rule"] = TimeRule.SLOT
                time_dict["slot"] = data["slot"]
            elif data.get("offset_minutes"):
                time_dict["rule"] = TimeRule.RELATIVE_MEETING
                time_dict["offset_minutes"] = data["offset_minutes"]
            elif data.get("time_rule"):
                time_dict["rule"] = data["time_rule"]
            else:
                time_dict["rule"] = TimeRule.ALL_DAY

            if "offset_minutes" in data and time_dict.get("rule") != TimeRule.RELATIVE_MEETING:
                time_dict["offset_minutes"] = data["offset_minutes"]

            data["time"] = time_dict

        return data

    @model_validator(mode="after")
    def validate_status(self) -> "DeadlineIR":
        if self.status == "resolved":
            has_date = self.date is not None
            has_range = self.range is not None
            has_candidates = bool(self.candidate_ranges)
            if sum((has_date, has_range, has_candidates)) != 1:
                raise ValueError(
                    "resolved 状态必须且只能提供 date、range、candidate_ranges 之一"
                )
            if has_date and self.date is not None:
                if (
                    self.date.rule == DateRule.IMPLICIT_DATE
                    and self.time.rule == TimeRule.ALL_DAY
                ):
                    raise ValueError("implicit_date 不能搭配 all_day；没有时间表达时请用 status=none")
                if self.time.rule == TimeRule.RELATIVE_MEETING and self.date.rule not in {
                    DateRule.SAME_DAY,
                    DateRule.IMPLICIT_DATE,
                }:
                    raise ValueError("relative_meeting 只支持 same_day / implicit_date")
        return self


class ExtractionResponse(BaseModel):
    """大模型批量输出容器。"""

    model_config = ConfigDict(extra="ignore")

    items: List[DeadlineIR]


class ResolvedDeadline(BaseModel):
    """最终标准化输出模型。
    
    业务核心格式：
    {
      "raw": "明天下午交作业",
      "deadline": "2026/10/30",
      "time_slot": "下午",
      "kind": "date"
    }
    """

    model_config = ConfigDict(extra="ignore")

    index: int
    raw: str
    deadline: Optional[str] = None
    deadline_start: Optional[str] = None
    deadline_end: Optional[str] = None
    time_slot: Optional[str] = None   # "上午" | "中午" | "下午" | "晚上" | "下班前" | None
    kind: Literal["date", "datetime", "range", "none"] = "none"
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    def to_clean_dict(self) -> dict:
        """返回标准的业务对象。"""
        return {
            "raw": self.raw,
            "deadline": self.deadline,
            "deadline_start": self.deadline_start,
            "deadline_end": self.deadline_end,
            "time_slot": self.time_slot,
            "kind": self.kind,
        }


__all__ = [
    "DateRule",
    "TimeRule",
    "TimeSlot",
    "DateSpec",
    "DateRangeSpec",
    "TimeSpec",
    "DeadlineIR",
    "ExtractionResponse",
    "ResolvedDeadline",
]
