# -*- coding: utf-8 -*-
"""compact_draft_for_review 单测：审核草稿压缩保结构、截长文、计大列表。"""
from __future__ import annotations

from tools.runtime.supervisor_slice import compact_draft_for_review


LONG = "长" * 200


class TestCompactDraft:
    def test_结构列表保留全部元素(self):
        draft = {
            "chapters": [
                {"id": "ch_001", "name": "章", "topics": [
                    {"id": "tp_001", "name": "主题", "knowledge_points": [
                        {"id": "kp_001", "name": "点", "knowledge_type": "concept"},
                    ]},
                ]},
                {"id": "ch_002", "name": "章二"},
            ]
        }
        comp = compact_draft_for_review(draft)
        assert len(comp["chapters"]) == 2, "结构列表不应被计数"
        assert comp["chapters"][0]["topics"][0]["knowledge_points"][0]["id"] == "kp_001"
        assert comp["chapters"][0]["topics"][0]["knowledge_points"][0]["knowledge_type"] == "concept"

    def test_长字符串截断并标注总长(self):
        draft = {"explain": LONG, "name": "短名"}
        comp = compact_draft_for_review(draft)
        assert comp["name"] == "短名", "短字段原样保留"
        assert "（共 200 字）" in comp["explain"], "长文本应截断并标注总长"
        assert len(comp["explain"]) < 100

    def test_大内容列表转计数(self):
        draft = {"key_facts": [f"事实{i}" for i in range(20)]}
        comp = compact_draft_for_review(draft)
        assert "（20 条，已省略）" in comp["key_facts"][0], "超 8 条的内容列表应转为计数"

    def test_小内容列表保留(self):
        draft = {"pitfalls": ["错误一", "错误二"]}
        comp = compact_draft_for_review(draft)
        assert comp["pitfalls"] == ["错误一", "错误二"]

    def test_短列表内的短字符串保留(self):
        draft = {"method_steps": ["辨认", "计算", "检查"]}
        comp = compact_draft_for_review(draft)
        assert comp["method_steps"] == ["辨认", "计算", "检查"]
