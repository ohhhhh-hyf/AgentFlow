"""tests/unit/meeting/test_minutes_topic_major_memory.py -- topic_major 记忆与兜底。"""
from __future__ import annotations

import asyncio

from domains.meeting.memory.extract import extract_meeting_fact_from_minutes_draft
from domains.meeting.memory.runtime import _draft_has_fact
from domains.meeting.orchestrator import MeetingAgentSystem
from domains.meeting.tasks.minutes.contracts import MINUTES_FALLBACK_RULES


def _topic_draft() -> dict:
    return {
        "overview": "本次例会围绕接口联调与上线准备展开。",
        "topics": [
            {
                "topic_name": "接口联调",
                "topic_summary": ["接口方案已确认", "联调排期本周内"],
                "decisions": ["按 B 方案执行"],
                "actions": ["张三周五前完成联调报告"],
                "risks": ["依赖外部团队，可能延迟"],
                "open_questions": ["上线时间是否按原计划"],
            },
            {
                "topic_name": "上线准备",
                "topic_summary": ["灰度名单已确认"],
                "decisions": ["周三晚开始灰度"],
                "actions": ["李四周二前提交回滚方案"],
                "risks": ["监控覆盖不足"],
                "open_questions": ["是否增加值守人员"],
            },
        ],
        "history_comparison": [],
    }


def test_draft_has_fact_recognizes_topic_major() -> None:
    assert _draft_has_fact(_topic_draft())
    assert _draft_has_fact(
        {
            "overview": "概况",
            "topics": [],
            "history_comparison": [],
        }
    )


def test_extract_topic_major_meeting_fact() -> None:
    fact = extract_meeting_fact_from_minutes_draft(
        _topic_draft(),
        agenda_titles=["接口联调", "上线准备"],
        transcript="张三：讨论接口联调。李四：讨论上线准备。",
        request_id="req_topic_major",
        time="2026-11-03 10:00",
    )

    assert fact.title == ""
    assert fact.summary.startswith("本次例会围绕接口联调")
    assert fact.decisions == ["按 B 方案执行", "周三晚开始灰度"]
    assert fact.risks == ["依赖外部团队，可能延迟", "监控覆盖不足"]
    assert fact.open_items == ["上线时间是否按原计划", "是否增加值守人员"]
    assert [item["text"] for item in fact.action_items] == [
        "张三周五前完成联调报告",
        "李四周二前提交回滚方案",
    ]
    assert [topic["title"] for topic in fact.topics] == ["接口联调", "上线准备"]
    assert fact.topics[0]["decisions"] == ["按 B 方案执行"]
    assert fact.topics[0]["actions"][0]["text"] == "张三周五前完成联调报告"
    assert fact.topics[1]["risks"] == ["监控覆盖不足"]
    assert fact.topics[1]["open_issues"] == ["是否增加值守人员"]


def test_topic_major_fallback_node_renders_overview_and_topics() -> None:
    system = object.__new__(MeetingAgentSystem)
    system._fallback_rules = {"minutes": MINUTES_FALLBACK_RULES}
    state = {
        "lang": "zh",
        "line_layouts": {"minutes": "topic_major"},
        "line_views": {"minutes": "agenda_objective"},
        "lines": {"minutes": {"draft": _topic_draft()}},
    }

    out = asyncio.run(system._make_minutes_fallback_node()(state))

    assert out["quality_degraded"] is True
    line = out["lines"]["minutes"]
    assert line["degraded"] is True
    text = line["rendered"]
    assert "## 全文摘要" in text
    assert "## 议题梳理" in text
    assert "### 一. 接口联调" in text
    assert "### 二. 上线准备" in text
    assert "**工作进展**" in text
    assert "**落实安排**" in text
    assert "**未决风险**" in text
    assert "张三周五前完成联调报告" in text
    assert "监控覆盖不足" in text
