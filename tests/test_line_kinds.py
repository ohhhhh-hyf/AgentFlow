"""第二刀：任务线按种类分流，不再用线名特判。"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace


class KindPolicyTest(unittest.TestCase):
    def test_unknown_kind_rejected(self):
        from tools.runtime.kinds import policy_for

        with self.assertRaises(ValueError):
            policy_for("llm_magic")

    def test_extract_defaults(self):
        from tools.runtime.kinds import LLM_EXTRACT, policy_for

        p = policy_for(LLM_EXTRACT)
        self.assertTrue(p.uses_llm_render(False))
        self.assertTrue(p.cli_template)
        self.assertFalse(p.cli_mode)
        self.assertFalse(p.sidecar)
        self.assertTrue(p.extracts_structure)

    def test_document_defaults(self):
        from tools.runtime.kinds import LLM_DOCUMENT, policy_for

        p = policy_for(LLM_DOCUMENT)
        self.assertTrue(p.uses_llm_render(True))
        self.assertTrue(p.cli_template)
        self.assertFalse(p.cli_mode)
        self.assertFalse(p.sidecar)
        self.assertFalse(p.extracts_structure)

    def test_pipeline_defaults(self):
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, policy_for

        p = policy_for(DETERMINISTIC_PIPELINE)
        self.assertFalse(p.uses_llm_render(False))
        self.assertFalse(p.uses_llm_render(True))
        self.assertFalse(p.cli_template)
        self.assertFalse(p.sidecar)
        self.assertFalse(p.extracts_structure)

    def test_trace_is_pipeline_with_sidecar(self):
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, resolve_line_policies

        policies = resolve_line_policies(
            {
                "minutes_trace": {
                    "kind": DETERMINISTIC_PIPELINE,
                    "sidecar": True,
                }
            }
        )
        p = policies["minutes_trace"]
        self.assertEqual(p.kind, DETERMINISTIC_PIPELINE)
        self.assertTrue(p.sidecar)
        self.assertFalse(p.cli_template)
        self.assertFalse(p.uses_llm_render(False))

    def test_knowledge_graph_pipeline_renders_only_with_template(self):
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, resolve_line_policies

        p = resolve_line_policies(
            {
                "knowledge_graph": {
                    "kind": DETERMINISTIC_PIPELINE,
                    "llm_render": "if_template",
                    "cli_template": True,
                }
            }
        )["knowledge_graph"]
        self.assertFalse(p.uses_llm_render(False))
        self.assertTrue(p.uses_llm_render(True))
        self.assertTrue(p.cli_template)

    def test_multi_styles_document_exposes_mode(self):
        from tools.runtime.kinds import LLM_DOCUMENT, resolve_line_policies

        p = resolve_line_policies(
            {"multi_styles": {"kind": LLM_DOCUMENT, "cli_mode": True}}
        )["multi_styles"]
        self.assertTrue(p.cli_mode)
        self.assertTrue(p.uses_llm_render(False))

    def test_resolve_requires_declared_lines(self):
        from tools.runtime.kinds import LLM_EXTRACT, resolve_line_policies

        with self.assertRaises(ValueError) as ctx:
            resolve_line_policies({"risk": LLM_EXTRACT}, required=["risk", "points"])
        self.assertIn("points", str(ctx.exception))


class DomainConfigKindsTest(unittest.TestCase):
    def test_meeting_kinds_match_product_map(self):
        from domain.meeting.domain_config import LINE_KINDS
        from tools.runtime.kinds import (
            DETERMINISTIC_PIPELINE,
            LLM_DOCUMENT,
            LLM_EXTRACT,
            resolve_line_policies,
        )

        policies = resolve_line_policies(LINE_KINDS)
        self.assertEqual(policies["risk"].kind, LLM_EXTRACT)
        self.assertEqual(policies["action_items"].kind, LLM_EXTRACT)
        self.assertEqual(policies["minutes_generation"].kind, LLM_DOCUMENT)
        self.assertEqual(policies["multi_styles"].kind, LLM_DOCUMENT)
        self.assertTrue(policies["multi_styles"].cli_mode)
        self.assertEqual(policies["minutes_trace"].kind, DETERMINISTIC_PIPELINE)
        self.assertTrue(policies["minutes_trace"].sidecar)
        self.assertFalse(policies["minutes_trace"].cli_template)

    def test_notes_kinds_match_product_map(self):
        from domain.notes.domain_config import LINE_KINDS
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, LLM_EXTRACT, resolve_line_policies

        policies = resolve_line_policies(LINE_KINDS)
        self.assertEqual(policies["points"].kind, LLM_EXTRACT)
        self.assertEqual(policies["knowledge_graph"].kind, DETERMINISTIC_PIPELINE)
        self.assertTrue(policies["knowledge_graph"].uses_llm_render(True))
        self.assertFalse(policies["knowledge_graph"].uses_llm_render(False))


class StructureByKindTest(unittest.TestCase):
    def test_extract_kind_pulls_single_list(self):
        from tools.domain_engine import DomainNodes
        from tools.runtime.kinds import LLM_EXTRACT, policy_for

        @dataclass
        class RiskReport:
            risks: list = field(default_factory=list, metadata={"source": "structure"})

        class Stub(DomainNodes):
            _line_policies = {"risk": policy_for(LLM_EXTRACT)}
            _report_assemblers = {"risk": RiskReport}

        state = {"lines": {"risk": {"draft": {"risks": [{"risk": "延期"}]}}}}
        Stub()._post_render_hook(state, "risk")
        self.assertEqual(state["lines"]["risk"]["structure"], [{"risk": "延期"}])

    def test_pipeline_kind_does_not_heuristic_extract(self):
        from tools.domain_engine import DomainNodes
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, policy_for

        @dataclass
        class TraceReport:
            alignments: list = field(
                default_factory=list, metadata={"source": "structure"}
            )

        class Stub(DomainNodes):
            _line_policies = {
                "minutes_trace": policy_for(DETERMINISTIC_PIPELINE, sidecar=True)
            }
            _report_assemblers = {"minutes_trace": TraceReport}

        state = {
            "lines": {
                "minutes_trace": {
                    "draft": {"alignments": [{"kind": "x"}], "minutes_md": "#"}
                }
            }
        }
        Stub()._post_render_hook(state, "minutes_trace")
        self.assertNotIn("structure", state["lines"]["minutes_trace"])

    def test_extract_kind_prefers_render_extractor(self):
        from tools.domain_engine import DomainNodes
        from tools.runtime.kinds import LLM_EXTRACT, policy_for

        @dataclass
        class ActionReport:
            action_items: list = field(
                default_factory=list, metadata={"source": "structure"}
            )

        class Render:
            @staticmethod
            def extract_structure(state):
                return [{"task": "custom"}]

        class Stub(DomainNodes):
            _line_policies = {"action_items": policy_for(LLM_EXTRACT)}
            _report_assemblers = {"action_items": ActionReport}
            action_items_render = Render()

        state = {
            "lines": {
                "action_items": {
                    "draft": {
                        "my_actions": [1],
                        "delegated_actions": [2],
                        "unassigned_actions": [3],
                    }
                }
            }
        }
        Stub()._post_render_hook(state, "action_items")
        self.assertEqual(
            state["lines"]["action_items"]["structure"], [{"task": "custom"}]
        )


class ModeInjectionTest(unittest.TestCase):
    def test_agent_context_only_injects_mode_when_policy_allows(self):
        from tools.domain_engine import DomainNodes
        from tools.runtime.kinds import LLM_DOCUMENT, policy_for

        class Agent:
            def __init__(self):
                self.seen = ""

            async def run(self, context):
                self.seen = context

                class R:
                    def model_dump(self_inner):
                        return {}

                return R()

        class Stub(DomainNodes):
            _line_policies = {
                "multi_styles": policy_for(LLM_DOCUMENT, cli_mode=True),
                "mindmap": policy_for(LLM_DOCUMENT),
            }
            _task_lines = {
                "multi_styles": {"agent_attr": "multi_styles_agent", "empty_draft": {}},
                "mindmap": {"agent_attr": "mindmap_agent", "empty_draft": {}},
            }
            _line_cn_names = {"multi_styles": "多样式纪要", "mindmap": "思维导图"}
            multi_styles_agent = Agent()
            mindmap_agent = Agent()

            def _shared_context(self, state):
                return "BASE"

        import asyncio

        stub = Stub()
        state = {
            "lines": {"multi_styles": {}, "mindmap": {}},
            "line_modes": {"multi_styles": "time", "mindmap": "time"},
        }
        asyncio.run(stub._make_agent_node("multi_styles")(state))
        asyncio.run(stub._make_agent_node("mindmap")(state))
        self.assertIn("组织模式：time", stub.multi_styles_agent.seen)
        self.assertNotIn("组织模式：", stub.mindmap_agent.seen)


class RunnerCliByKindTest(unittest.TestCase):
    def test_parser_follows_policy_not_line_name(self):
        from tools.runner import build_parser
        from tools.runtime.kinds import (
            DETERMINISTIC_PIPELINE,
            LLM_DOCUMENT,
            LLM_EXTRACT,
            policy_for,
        )
        from tools.runtime_context import DomainContext

        ctx = DomainContext(
            name="meeting",
            module=SimpleNamespace(),
            config=SimpleNamespace(),
            models=SimpleNamespace(),
            orchestrator=SimpleNamespace(),
            system_cls=object,
            samples_dir=Path("."),
            line_cn_names={
                "risk": "风险分析",
                "multi_styles": "多样式纪要",
                "minutes_trace": "溯源纪要",
            },
            task_lines={
                "risk": {},
                "multi_styles": {},
                "minutes_trace": {},
            },
            task_aliases={},
            env_prefix="MEETING",
            project_root=Path("."),
            line_policies={
                "risk": policy_for(LLM_EXTRACT),
                "multi_styles": policy_for(LLM_DOCUMENT, cli_mode=True),
                "minutes_trace": policy_for(
                    DETERMINISTIC_PIPELINE, sidecar=True
                ),
            },
        )
        parser = build_parser(ctx)
        dests = {a.dest for a in parser._actions}
        self.assertIn("risk_template", dests)
        self.assertNotIn("risk_mode", dests)
        self.assertIn("multi_styles_template", dests)
        self.assertIn("multi_styles_mode", dests)
        self.assertNotIn("minutes_trace_template", dests)
        self.assertNotIn("minutes_trace_mode", dests)


class SidecarByKindTest(unittest.TestCase):
    def test_sidecar_lines_come_from_policy(self):
        from tools.runtime.kinds import sidecar_lines
        from tools.runtime.kinds import DETERMINISTIC_PIPELINE, LLM_EXTRACT, policy_for

        policies = {
            "risk": policy_for(LLM_EXTRACT),
            "minutes_trace": policy_for(DETERMINISTIC_PIPELINE, sidecar=True),
        }
        self.assertEqual(sidecar_lines(["risk", "minutes_trace"], policies), ["minutes_trace"])
        self.assertEqual(sidecar_lines(["risk"], policies), [])


if __name__ == "__main__":
    unittest.main()
