"""CLI 基础与输入归一化测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli import _one_to_one, _to_clean_items, normalize_input  # noqa: E402


def test_one_to_one_keeps_order_and_pads_missing() -> None:
    results = [
        {"index": 0, "deadline": "2026/10/30"},
        {"index": 1, "deadline": None},
    ]
    assert _one_to_one(results, 3) == ["2026/10/30", None, None]


def test_one_to_one_exact_count() -> None:
    results = [{"index": 0, "deadline": "2026/10/30 15:00"}]
    assert _one_to_one(results, 1) == ["2026/10/30 15:00"]


def test_normalize_input_formats() -> None:
    # 纯字符串
    assert normalize_input("明天") == ["明天"]

    # 列表字符串
    assert normalize_input(["明天", "后天"]) == ["明天", "后天"]

    # 字典列表
    assert normalize_input([{"deadline": "周五"}, {"text": "下周三"}]) == ["周五", "下周三"]

    # action_groups 复杂嵌套
    ag_data = {
        "action_groups": [
            {
                "assigned": [{"deadline": "周五下班前"}],
                "unassigned": [{"deadline": "下周三"}],
            }
        ]
    }
    assert normalize_input(ag_data) == ["周五下班前", "下周三"]


def test_clean_output_keeps_range_fields() -> None:
    results = [{
        "index": 0,
        "raw": "一周内",
        "deadline": "2026/11/05",
        "deadline_start": "2026/10/29",
        "deadline_end": "2026/11/05",
        "time_slot": None,
        "kind": "range",
    }]
    out = _to_clean_items(results, 1, ["一周内"])
    assert out[0]["deadline"] == "2026/11/05"
    assert out[0]["deadline_start"] == "2026/10/29"
    assert out[0]["deadline_end"] == "2026/11/05"
    assert out[0]["kind"] == "range"
