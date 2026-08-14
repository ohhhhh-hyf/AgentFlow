"""第一刀：运行时分层与注册表，不再为每条线生成 render/fallback 样板。

覆盖三个不变量：
1. 理解结果只走领域钩子 key，不再 or-chain meeting/notes 字段名
2. 渲染上下文由一份运行时函数拼装，含 line_extra，标签跟中文名走
3. 降级节点由工厂生成，orchestrator 不再需要 _{line}_fallback_node
"""
from __future__ import annotations

import asyncio
import unittest


class UnderstandingHookTest(unittest.TestCase):
    def test_uses_only_the_named_key(self):
        from tools.runtime.context import understanding_of

        state = {
            "meeting_understanding": {"meeting_purpose": "上线评审"},
            "notes_understanding": {"note_purpose": "导数"},
        }
        self.assertEqual(
            understanding_of(state, "meeting_understanding"),
            {"meeting_purpose": "上线评审"},
        )
        self.assertEqual(
            understanding_of(state, "notes_understanding"),
            {"note_purpose": "导数"},
        )
        self.assertEqual(understanding_of(state, ""), {})
        self.assertEqual(understanding_of(state, "missing"), {})

    def test_ignores_non_dict_values(self):
        from tools.runtime.context import understanding_of

        self.assertEqual(understanding_of({"k": "x"}, "k"), {})


class RenderContextTest(unittest.TestCase):
    def test_generic_context_matches_legacy_shape(self):
        from tools.runtime.context import build_render_context

        text = build_render_context(
            mode="objective",
            objective=True,
            blocks=[
                ("会议原文", "大家好", "raw"),
                ("用户画像", {"name": "Ada"}, "json"),
                ("已审核会议理解", {"meeting_purpose": "评审"}, "json"),
                ("已审核用户视角", {"role": "pm"}, "json"),
            ],
            draft={"headline": "纪要"},
            review={"decision": "approve"},
            line_cn="纪要",
            extra="记忆摘录：上次未闭环",
        )
        self.assertIn("视角模式：objective", text)
        self.assertIn("objective_perspective：True", text)
        self.assertIn("会议原文：\n大家好", text)
        self.assertIn("已审核会议理解：", text)
        self.assertIn("已批准纪要草稿：", text)
        self.assertIn("纪要审核结论：", text)
        self.assertIn("记忆摘录：上次未闭环", text)
        self.assertIn('"headline": "纪要"', text)

    def test_trace_label_stays_stable_for_stamp_render(self):
        from tools.runtime.context import build_render_context

        text = build_render_context(
            mode="objective",
            objective=True,
            blocks=[("会议原文", "原文", "raw")],
            draft={"minutes_md": "# 纪要", "alignments": []},
            review={},
            line_cn="溯源纪要",
        )
        self.assertIn("已批准溯源纪要草稿：", text)


class DomainNodesRuntimeTest(unittest.TestCase):
    def test_render_context_uses_hooks_and_line_extra(self):
        from tools.domain_engine import DomainNodes

        class Stub(DomainNodes):
            _understanding_key = "meeting_understanding"
            _understanding_label = "已审核会议理解"
            _transcript_label = "会议原文"
            _line_cn_names = {"minutes_generation": "纪要"}

        state = {
            "transcript": "开会了",
            "user": {"name": "Ada"},
            "objective_perspective": True,
            "meeting_understanding": {"meeting_purpose": "评审"},
            "notes_understanding": {"note_purpose": "不该出现"},
            "perspective_profile": {"role": "pm"},
            "lines": {
                "minutes_generation": {
                    "draft": {"headline": "标题"},
                    "review": {"decision": "approve"},
                }
            },
            "line_extra": {"minutes_generation": "【记忆命中】p1"},
        }
        text = Stub()._render_context(state, "minutes_generation")
        self.assertIn("开会了", text)
        self.assertIn("已审核会议理解", text)
        self.assertIn("评审", text)
        self.assertNotIn("不该出现", text)
        self.assertIn("【记忆命中】p1", text)
        self.assertIn("已批准纪要草稿：", text)

    def test_understanding_payload_follows_hook(self):
        from tools.domain_engine import DomainNodes

        class Meeting(DomainNodes):
            _understanding_key = "meeting_understanding"

        class Notes(DomainNodes):
            _understanding_key = "notes_understanding"

        state = {
            "meeting_understanding": {"meeting_purpose": "m"},
            "notes_understanding": {"note_purpose": "n"},
        }
        self.assertEqual(Meeting()._understanding(state)["meeting_purpose"], "m")
        self.assertEqual(Notes()._understanding(state)["note_purpose"], "n")
        self.assertEqual(DomainNodes()._understanding(state), {})

    def test_fallback_factory_does_not_need_generated_method(self):
        from tools.domain_engine import DomainNodes
        from tools.fallback_rules import FallbackRules, Raw

        class Rules(FallbackRules):
            sections = [Raw("headline")]
            empty_text = "请直接参考原文。"
            disclaimer = False

        class Stub(DomainNodes):
            _fallback_rules = {"minutes_generation": Rules()}
            _fallback_formatters = {}
            _quality_disclaimer = ""
            _line_cn_names = {"minutes_generation": "纪要"}

            def _empty_purpose(self, state):
                return ""

        state = {
            "lines": {
                "minutes_generation": {
                    "draft": {"headline": "标题"},
                    "review": {"decision": "reject"},
                }
            }
        }
        node = Stub()._make_fallback_node("minutes_generation")
        result = asyncio.run(node(state))
        self.assertTrue(result["quality_degraded"])
        line = result["lines"]["minutes_generation"]
        self.assertTrue(line["degraded"])
        self.assertIn("标题", line["rendered"])


if __name__ == "__main__":
    unittest.main()
