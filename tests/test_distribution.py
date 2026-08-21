# -*- coding: utf-8 -*-
"""distribution 单测：复习重点分布按知识点 Top10 + 其他、总和 100%。"""
from __future__ import annotations

from domain.notes.tasks.checklist.assemble import distribution


def _card(name: str, priority: str, chapter: str = "第一章") -> dict:
    return {"name": name, "chapter": chapter, "session_priority": priority}


class TestDistribution:
    def test_超过10个知识点时归并其他(self):
        cards = [
            _card(f"知识点{i:02d}", "S" if i < 3 else ("A" if i < 6 else ("B" if i < 10 else "C")))
            for i in range(13)
        ]
        rows = distribution(cards)
        assert len(rows) == 11, f"应 Top10 + 其他 = 11 项，实际 {len(rows)}"
        assert rows[-1]["label"] == "其他"

    def test_总和为100(self):
        cards = [_card(f"点{i}", "A") for i in range(5)]
        rows = distribution(cards)
        total = sum(r["value"] for r in rows)
        assert abs(total - 100.0) < 0.01, f"饼图总和应为 100%，实际 {total}"

    def test_不超过10个知识点时无其他(self):
        cards = [_card(f"点{i}", "A") for i in range(5)]
        rows = distribution(cards)
        assert all(r["label"] != "其他" for r in rows)

    def test_权重按优先级排序(self):
        cards = [
            _card("低优先级点", "C"),
            _card("高优先级点", "S"),
        ]
        rows = distribution(cards)
        assert rows[0]["label"] == "高优先级点", "S 级应排前面"
        assert rows[0]["value"] > rows[1]["value"]

    def test_同知识点多张卡权重累加(self):
        cards = [_card("重复点", "A"), _card("重复点", "B")]
        rows = distribution(cards)
        assert len(rows) == 1, "同名知识点应合并"
        assert rows[0]["label"] == "重复点"
