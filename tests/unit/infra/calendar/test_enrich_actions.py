"""测试 infra.calendar.enrich_actions_deadlines 闭环回填能力。"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from infra.calendar import enrich_actions_deadlines


class MockCalendarLLM:
    """用于测试复杂句 fallback 的 LLM 协议桩。"""

    def __init__(self, response_payload: Dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.response_payload = response_payload or {
            "items": [
                {
                    "index": 0,
                    "raw": "明天下午",
                    "status": "resolved",
                    "date": {"rule": "offset_days", "amount": 1},
                    "time": {"rule": "slot", "slot": "下午"},
                    "reason": None,
                    "assumptions": [],
                }
            ]
        }

    async def chat_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        self.calls.append((system_prompt, user_prompt))
        return self.response_payload


def test_enrich_empty_actions() -> None:
    res = asyncio.run(enrich_actions_deadlines([], "2026-10-30 10:00:00"))
    assert res == []


def test_enrich_all_null_actions() -> None:
    actions = [
        {"title": "任务1", "item": "测试1", "deadline": None},
        {"title": "任务2", "item": "测试2", "deadline": ""},
    ]
    res = asyncio.run(enrich_actions_deadlines(actions, "2026-10-30 10:00:00"))
    assert len(res) == 2
    for item in res:
        assert item["deadline_raw"] is None
        assert item["deadline_display"] is None
        assert item["deadline"] is None


def test_enrich_empty_meeting_time() -> None:
    actions = [
        {"title": "任务1", "item": "测试1", "deadline": "明天15:00"},
    ]
    res = asyncio.run(enrich_actions_deadlines(actions, ""))
    assert len(res) == 1
    assert res[0]["deadline_raw"] == "明天15:00"
    assert res[0]["deadline_display"] == "明天15:00"
    assert res[0]["deadline"] is None


def test_enrich_interleaved_nulls_zero_offset() -> None:
    """核心防错位测试：穿插 null 与有效时间，验证 1:1 绝对对齐。"""
    actions = [
        {"title": "任务0", "item": "做完A", "deadline": "明天15:00"},
        {"title": "任务1", "item": "做完B", "deadline": None},
        {"title": "任务2", "item": "做完C", "deadline": "周五前"},
        {"title": "任务3", "item": "做完D", "deadline": ""},
    ]
    meeting_time = "2026-10-29 10:00:00"  # 周四

    res = asyncio.run(enrich_actions_deadlines(actions, meeting_time, inplace=False))
    assert len(res) == 4

    # 任务0：明天15:00 -> 周五 2026/10/30 15:00
    assert res[0]["deadline_raw"] == "明天15:00"
    assert res[0]["deadline_display"] == "2026/10/30 15:00"
    assert res[0]["deadline"] == "2026-10-30T15:00:00"

    # 任务1：null -> 绝对不被任务2覆盖！
    assert res[1]["deadline_raw"] is None
    assert res[1]["deadline_display"] is None
    assert res[1]["deadline"] is None

    # 任务2：周五前 -> 2026/10/30
    assert res[2]["deadline_raw"] == "周五前"
    assert res[2]["deadline_display"] == "2026/10/30"
    assert res[2]["deadline"] == "2026-10-30T18:00:00"

    # 任务3：空串 -> 绝对安全置空
    assert res[3]["deadline_raw"] is None
    assert res[3]["deadline_display"] is None
    assert res[3]["deadline"] is None


def test_enrich_inplace_flag() -> None:
    actions = [{"title": "任务A", "deadline": "明天15:00"}]
    meeting_time = "2026-10-29 10:00:00"

    # inplace=False: 原列表字典不被修改
    res1 = asyncio.run(enrich_actions_deadlines(actions, meeting_time, inplace=False))
    assert "deadline_display" not in actions[0]
    assert "deadline_display" in res1[0]

    # inplace=True: 原列表字典被修改
    res2 = asyncio.run(enrich_actions_deadlines(actions, meeting_time, inplace=True))
    assert "deadline_display" in actions[0]
    assert actions[0] is res2[0]


def test_enrich_with_mock_llm_time_slot() -> None:
    """测试通过 LLM 协议解析带模糊时段（下午）的待办。"""
    mock_client = MockCalendarLLM(
        response_payload={
            "items": [
                {
                    "index": 0,
                    "raw": "明天下午",
                    "status": "resolved",
                    "date": {"rule": "offset_days", "amount": 1},
                    "time": {"rule": "slot", "slot": "下午"},
                    "reason": None,
                    "assumptions": [],
                }
            ]
        }
    )
    actions = [{"title": "报告", "deadline": "明天下午"}]
    meeting_time = "2026-10-29 10:00:00"

    res = asyncio.run(
        enrich_actions_deadlines(
            actions, meeting_time, client=mock_client, use_fast_path=True
        )
    )
    assert len(res) == 1
    assert res[0]["deadline_raw"] == "明天下午"
    assert res[0]["deadline_display"] == "2026/10/30 下午"
    assert res[0]["deadline"] == "2026-10-30T18:00:00"


def test_enrich_with_mock_llm_range() -> None:
    """测试时间范围（下周）推导。"""
    mock_client = MockCalendarLLM(
        response_payload={
            "items": [
                {
                    "index": 0,
                    "raw": "下周",
                    "status": "resolved",
                    "range": {
                        "start": {"rule": "weekday", "week_offset": 1, "target_weekday": 1},
                        "end": {"rule": "weekday", "week_offset": 1, "target_weekday": 7},
                    },
                    "time": {"rule": "all_day"},
                    "reason": None,
                    "assumptions": [],
                }
            ]
        }
    )
    actions = [{"title": "联调", "deadline": "下周"}]
    meeting_time = "2026-10-29 10:00:00"  # 周四

    res = asyncio.run(
        enrich_actions_deadlines(
            actions, meeting_time, client=mock_client, use_fast_path=False
        )
    )
    assert len(res) == 1
    assert res[0]["deadline_raw"] == "下周"
    assert res[0]["deadline_display"] == "2026/11/02 ~ 2026/11/08"
    assert res[0]["deadline"] == "2026-11-08T18:00:00"


def test_enrich_unresolvable_expression_fallback() -> None:
    """测试无法解析的时间表达（如尽快、后续评估）安全降级。"""
    mock_client = MockCalendarLLM(
        response_payload={
            "items": [
                {
                    "index": 0,
                    "raw": "尽快完成",
                    "status": "none",
                    "reason": "模糊表达，无具体时间锚点",
                    "assumptions": [],
                }
            ]
        }
    )
    actions = [{"title": "优化", "deadline": "尽快完成"}]
    meeting_time = "2026-10-29 10:00:00"

    res = asyncio.run(
        enrich_actions_deadlines(
            actions, meeting_time, client=mock_client, use_fast_path=False
        )
    )
    assert len(res) == 1
    assert res[0]["deadline_raw"] == "尽快完成"
    assert res[0]["deadline_display"] == "尽快完成"
    assert res[0]["deadline"] is None
