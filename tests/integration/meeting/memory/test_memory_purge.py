# 拆分自 test_meeting_memory.py，覆盖：test_purge_stale_memory_from_decisions, test_minutes_agent_stale_purge_integration, test_extract_topics_roundtrip…

"""会议记忆零 LLM 衡约：身份、不传 project 接续、状态机、时间/场次。

用法::

    python -m tests.test_meeting_memory
"""

from __future__ import annotations
import json
from pathlib import Path
from domains.meeting.memory.bind import (
    bind_meeting,
    is_strong_anchor,
    is_weak_project_name,
    pick_project_name,
    project_core,
)
from domains.meeting.memory.extract import MeetingFact, extract_meeting_fact
from domains.meeting.memory.inject import build_memory_context, preview_comparison
from domains.meeting.memory.render import parse_memory_items
from domains.meeting.memory.runtime import persist_after_run, resolve_bind
from domains.meeting.memory.state import rebuild_state, session_index, session_label, update_state
from domains.meeting.memory.store import list_meetings, load_registry, load_state
from tests.support.expectations import expect
import pytest
from tests.support.builders import meeting_fact as _fact

pytestmark = pytest.mark.integration


def test_purge_stale_memory_from_decisions():
    from core.execution.hard_execution import purge_stale_memory_from_decisions, enforce_minutes_draft

    draft_decisions = [
        "本次新增决议：上线GPU集群",
        "8月18日前优化 minutes_trace",  # Stale memory from past meeting, not in transcript
    ]
    memory_texts = ["8月18日前优化 minutes_trace", "历史已决策事项B"]
    transcript = "今天我们核心讨论了本次新增决议：上线GPU集群，全员一致同意。"

    valids, migrated = purge_stale_memory_from_decisions(draft_decisions, memory_texts, transcript)
    expect(valids == ["本次新增决议：上线GPU集群"], "有效决议仅保留本次实录讨论项", str(valids))
    expect(any("8月18日前优化 minutes_trace" in m for m in migrated), "未重申历史记忆被自动迁移至往期沿革", str(migrated))

    raw_draft = {
        "headline": "测试例会",
        "executive_summary": ["总结"],
        "key_decisions": ["本次新增决议：上线GPU集群", "8月18日前优化 minutes_trace"],
        "personally_relevant_points": ["推进GPU集群上线"],
        "risks_and_blockers": [],
        "unresolved_questions": [],
    }
    enforced = enforce_minutes_draft(
        raw_draft,
        {"decisions": ["本次新增决议：上线GPU集群", "8月18日前优化 minutes_trace"]},
        mode="objective",
        memory_texts=memory_texts,
        transcript=transcript,
    )
    expect(enforced["key_decisions"] == ["本次新增决议：上线GPU集群"], "enforce_minutes_draft key_decisions 纯净无历史污染", str(enforced["key_decisions"]))
    expect(any("8月18日前优化 minutes_trace" in h for h in enforced["history_comparison"]), "enforce_minutes_draft history_comparison 承接往期沿革", str(enforced["history_comparison"]))


def test_minutes_agent_stale_purge_integration():
    import asyncio
    from domains.meeting.tasks.minutes.steps.minutes_agent import (
        MinutesGenerationAgent,
        _extract_transcript,
        _extract_memory_texts,
    )
    from domains.meeting.models import Minutes

    shared_ctx = (
        "会议理解：\n{\"key_decisions\": [\"上线GPU集群\", \"8月18日前优化 minutes_trace\"]}\n\n"
        "会议原文：\n今天我们核心讨论了本次新增决议：上线GPU集群，全员一致同意。\n\n"
        "══════════════════════════════════════════════════════════════\n"
        "【项目推进背景】\n"
        "- 8月18日前优化 minutes_trace（第1场已决策）\n"
        "══════════════════════════════════════════════════════════════"
    )
    tr = _extract_transcript(shared_ctx)
    expect("上线GPU集群" in tr, "agent helper: transcript 正确提取", tr)
    mem_texts = _extract_memory_texts(shared_ctx)
    expect("8月18日前优化 minutes_trace" in mem_texts, "agent helper: memory_texts 正确提取", str(mem_texts))

    class MockClient:
        async def structured(self, *args, **kwargs):
            return Minutes(
                headline="测试例会",
                executive_summary=["总结"],
                key_decisions=["上线GPU集群", "8月18日前优化 minutes_trace"],
                personally_relevant_points=["推进GPU集群上线"],
                risks_and_blockers=[],
                unresolved_questions=[],
                history_comparison=[],
            )

    agent = MinutesGenerationAgent(MockClient())
    res = asyncio.run(agent.run(shared_ctx, view="objective"))
    expect(res.key_decisions == ["上线GPU集群"], "agent.run 自动剥离未重申旧决议", str(res.key_decisions))
    expect(any("8月18日前优化 minutes_trace" in h for h in res.history_comparison), "agent.run 自动将旧决议归入往期沿革", str(res.history_comparison))


def test_extract_topics_roundtrip() -> None:
    """阶段一：extract 保留议题结构；flat 字段照旧；存储往返无损。"""
    understanding = {
        "meeting_purpose": "网关鉴权改造评审",
        "meeting_brief": "评审鉴权方案",
        "topics": [{
            "topic_id": "T1",
            "module": "网关核心架构",
            "title": "鉴权方案选型与延迟优化",
            "context_and_debate": "李工主张二级缓存，张工顾虑一致性。",
            "key_metrics": ["P99 200ms"],
            "decisions": ["采用二级缓存方案"],
            "rejected_proposals": ["全量迁移"],
            "actions": [{
                "task": "完成缓存保护设计", "owner": "李工",
                "deadline": "10-10", "deliverable": "设计文档",
            }],
            "risks": [{"risk": "多实例缓存不一致", "severity": "high"}],
            "open_issues": ["主从切换降级策略未定"],
        }],
    }
    fact = extract_meeting_fact(
        understanding, "李工：采用二级缓存方案。", request_id="r1", time="2026-09-01"
    )
    expect(bool(fact.topics) and fact.topics[0]["topic_id"] == "T1"
          and fact.topics[0]["module"] == "网关核心架构"
          and fact.topics[0]["title"] == "鉴权方案选型与延迟优化", "fact.topics 保留议题结构", str(fact.topics))
    expect(fact.topics[0]["actions"][0] == {
              "text": "完成缓存保护设计", "owner": "李工",
              "timing": "10-10", "deliverable": "设计文档",
          }, "topics 动作条目归一（text/owner/timing/deliverable）", str(fact.topics[0]["actions"]))
    expect(fact.topics[0]["risks"] == ["多实例缓存不一致"], "topics 风险归一为文本", str(fact.topics[0]["risks"]))
    expect(fact.decisions == ["采用二级缓存方案"]
          and "多实例缓存不一致" in fact.risks
          and any(a["text"] == "完成缓存保护设计" for a in fact.action_items)
          and fact.open_items == ["主从切换降级策略未定"], "flat 字段照旧产出（零回归）", "")
    again = MeetingFact.from_dict(fact.as_dict())
    expect(again.topics == fact.topics, "as_dict/from_dict 往返保持 topics", str(again.topics))
    empty = MeetingFact.from_dict({"meeting_id": "m_old"})
    expect(empty.topics == [], "旧数据无 topics → 默认空列表", str(empty.topics))
