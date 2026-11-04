"""minutes 生成阶段与排版模板解耦：上下文只保留 JSON 契约。"""
from __future__ import annotations

import asyncio
import logging

from domains.meeting.models import Minutes
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent

CHECKLIST_TITLE = "【本轮 JSON 输出契约（唯一结构，最高优先级）】"

FIELD_NAMES = (
    "headline",
    "executive_summary",
    "key_decisions",
    "personally_relevant_points",
    "risks_and_blockers",
    "unresolved_questions",
    "history_comparison",
)


def _normal_state() -> dict:
    return {
        "transcript": "张三 10:00: 本周完成联调，下周压测。",
        "objective_perspective": True,
        "templates": {
            "minutes": "## [全文摘要]\n[单段概括]\n\n## [要点梳理]\n[正文]"
        },
        "line_extra": {},
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "session_segments": [],
            "topics": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
    }


def _agenda_state() -> dict:
    return {
        "transcript": "张三 10:00: 芯片良率达标。",
        "tagged_transcript": (
            "【会议开场背景与主线脉络】\n...\n\n"
            "【议题 01：芯片量产】（汇报人：张三）\n"
            "张三 10:00: 芯片良率达标。"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [],
        "objective_perspective": True,
        "templates": {
            "minutes": "## [评审概况]\n[概况]\n\n## [方案陈述]\n| 立场 | 核心论点 |"
        },
        "line_extra": {},
    }


def test_normal_minutes_generation_context_excludes_layout_template() -> None:
    ctx = _Nodes()._line_shared_context(_normal_state(), "minutes")

    assert "【目标样式模板】" not in ctx
    assert "## [全文摘要]" not in ctx
    assert "## [要点梳理]" not in ctx
    assert CHECKLIST_TITLE in ctx
    for name in FIELD_NAMES:
        assert name in ctx
    assert "会议原文：\n张三 10:00: 本周完成联调，下周压测。" in ctx


def test_agenda_minutes_generation_context_excludes_layout_template() -> None:
    ctx = _Nodes()._line_shared_context(_agenda_state(), "minutes")

    assert "【目标样式模板】" not in ctx
    assert "## [评审概况]" not in ctx
    assert "## [方案陈述]" not in ctx
    assert "议题模式：agenda_enhanced" in ctx
    assert "【审定议题草稿生成执行准绳】" in ctx
    assert CHECKLIST_TITLE in ctx
    for name in FIELD_NAMES:
        assert name in ctx


def test_minutes_styles_generation_context_has_no_field_checklist() -> None:
    state = _normal_state()
    state["templates"] = {"minutes_styles": "## [全文摘要]\n[正文]"}
    ctx = _Nodes()._line_shared_context(state, "minutes_styles")

    assert CHECKLIST_TITLE not in ctx


def _budget_state() -> dict:
    return {
        "transcript": "会" * 1000,
        "templates": {
            "minutes": "## [评审概况]\n[概况]\n\n## [方案陈述]\n[正文]"
        },
        "objective_perspective": True,
        "line_extra": {},
        "meeting_understanding": {
            "meeting_brief": "评审会",
            "meeting_purpose": "评审",
            "session_segments": [],
            "topics": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
    }


def test_length_budget_omits_template_columns_for_generation() -> None:
    nodes = _Nodes()
    state = _budget_state()

    generation = nodes._length_budget_line(
        state, "minutes", include_columns=False
    )
    render = nodes._length_budget_line(state, "minutes", include_columns=True)

    assert "【篇幅预算】" in generation
    assert "本模板" not in generation
    assert "本模板" in render


def test_minutes_generation_context_budget_has_no_template_columns() -> None:
    ctx = _Nodes()._line_shared_context(_budget_state(), "minutes")

    assert "【篇幅预算】" in ctx
    assert "本模板" not in ctx


def test_render_template_prompts_map_extra_fields_without_fold() -> None:
    """渲染 prompt 只说明 actions/risks/unresolved 的栏目语义，不强制折叠。"""
    for prompt in (
        MINUTES_RENDER_TEMPLATE_PROMPT,
        MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    ):
        assert "key_decisions" in prompt
        assert "personally_relevant_points" in prompt
        assert "risks_and_blockers" in prompt
        assert "unresolved_questions" in prompt
        assert "模板无此类栏目时，折入结论/决议或最近相关小节" not in prompt
        assert "无对应栏目时的折叠规则" not in prompt


def test_minutes_agent_label_includes_template_id() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.label = ""

        async def structured(self, *args, **kwargs):
            self.label = str(kwargs.get("label") or "")
            return Minutes(headline="测试纪要", executive_summary=["本周完成联调。"])

    client = FakeClient()
    agent = MinutesGenerationAgent(client)
    asyncio.run(
        agent.run("视角模式：objective", view="objective", template_id="abc123")
    )

    assert client.label == "minutes/agent/objective/abc123"


def test_minutes_generation_logs_template_fingerprint(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="domains.meeting.orchestrator"):
        _Nodes()._line_shared_context(_normal_state(), "minutes")

    assert "[minutes:generation]" in caplog.text
    assert "template_in_context=False" in caplog.text
    assert "template_id=" in caplog.text
    assert "template_id=none" not in caplog.text
    assert "template_chars=" in caplog.text
