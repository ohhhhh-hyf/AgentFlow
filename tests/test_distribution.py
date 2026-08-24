# -*- coding: utf-8 -*-
"""distribution：核心/重点按占比切扇区，小块按章归入「·其余」。"""
from __future__ import annotations

from domain.notes.tasks.checklist.assemble import distribution


def _card(name: str, priority: str, chapter: str = "第一章") -> dict:
    return {"name": name, "chapter": chapter, "session_priority": priority}


def _labels(rows: list[dict]) -> list[str]:
    return [str(row["label"]) for row in rows]


class TestDistribution:
    def test_总和为100(self):
        cards = [_card(f"点{i}", "A") for i in range(5)]
        rows = distribution(cards)
        total = sum(r["value"] for r in rows)
        assert abs(total - 100.0) < 0.01, f"饼图总和应为 100%，实际 {total}"

    def test_只画核心和重点不画简要补充(self):
        cards = [
            _card("本征方程", "S", "算符"),
            _card("狄拉克符号", "A", "表象"),
            _card("投影算符", "B", "表象"),
            _card("印刷噪声", "C", "附录"),
        ]
        rows = distribution(cards)
        labels = _labels(rows)
        assert "本征方程" in labels
        assert "狄拉克符号" in labels
        assert "投影算符" not in labels
        assert "印刷噪声" not in labels
        assert "其他" not in labels

    def test_少量重点全部单独成块(self):
        cards = [_card(f"点{i}", "A", "算符") for i in range(5)]
        rows = distribution(cards)
        assert len(rows) == 5
        assert all("其余" not in str(row["label"]) for row in rows)
        assert "其他" not in _labels(rows)

    def test_小扇区按章归并其余(self):
        cards = [_card("本征方程", "S", "算符")]
        cards.extend(_card(f"细节{i}", "A", "算符") for i in range(20))
        rows = distribution(cards)
        labels = _labels(rows)
        assert "本征方程" in labels
        assert "算符·其余" in labels
        assert "其他" not in labels

    def test_其余按章拆开而不是一块其他(self):
        cards = [_card("核心甲", "S", "算符"), _card("核心乙", "S", "表象")]
        cards.extend(_card(f"算符小{i}", "A", "算符") for i in range(12))
        cards.extend(_card(f"表象小{i}", "A", "表象") for i in range(12))
        labels = _labels(distribution(cards))
        assert "算符·其余" in labels
        assert "表象·其余" in labels
        assert "其他" not in labels

    def test_没有核心重点时按章分布(self):
        cards = [
            _card("了解甲", "B", "算符"),
            _card("了解乙", "C", "表象"),
        ]
        rows = distribution(cards)
        labels = _labels(rows)
        assert labels == ["算符", "表象"] or set(labels) == {"算符", "表象"}

    def test_同名核心重点权重累加(self):
        cards = [_card("重复点", "S"), _card("重复点", "A")]
        rows = distribution(cards)
        assert len(rows) == 1
        assert rows[0]["label"] == "重复点"
        assert abs(rows[0]["value"] - 100.0) < 0.01
