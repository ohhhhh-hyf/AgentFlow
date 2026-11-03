"""tests/unit/meeting/test_minutes_topic_major_agent.py -- topic_major 草稿 agent 接线。"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from domains.meeting.models import TopicMajorMinutes
from domains.meeting.orchestrator import MeetingAgentSystem
from domains.meeting.tasks.minutes.contracts import (
    MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT,
)
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    KEYPOINTS_PROMPT_BLOCK,
    MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import (
    MinutesGenerationAgent,
    check_topic_coverage,
)


def _topic_result() -> TopicMajorMinutes:
    return TopicMajorMinutes.validate(
        {
            "headline": "团队例会纪要",
            "overview": "本次例会围绕接口联调展开。",
            "topics": [
                {
                    "topic_name": "接口联调",
                    "topic_summary": ["方案已确认"],
                    "decisions": ["按 B 方案执行"],
                    "actions": ["张三周五前完成联调报告"],
                    "risks": ["依赖外部团队"],
                    "open_questions": ["上线时间待确认"],
                }
            ],
            "history_comparison": [],
        }
    )


class _CapturingClient:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def structured(self, system, user, model, contract, **kwargs):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "contract": contract,
                "kwargs": kwargs,
            }
        )
        return self.result


def test_check_topic_coverage_matching_normalized_titles() -> None:
    topics = [{"topic_name": "接口联调"}]

    assert check_topic_coverage(topics, ["接口 联调"]) == []
    assert check_topic_coverage(topics, ["接口联调", "上线准备"]) != []


def test_check_topic_coverage_detects_title_mismatch() -> None:
    findings = check_topic_coverage(
        [{"topic_name": "接口联调"}],
        ["上线准备"],
    )

    assert findings
    assert "标题不一致" in findings[0]


def test_check_topic_coverage_without_expected_titles() -> None:
    assert check_topic_coverage([{"topic_name": "任意"}], []) == []


def test_agent_selects_topic_major_prompt_contract_and_model() -> None:
    client = _CapturingClient(_topic_result())
    agent = MinutesGenerationAgent(client)

    result = asyncio.run(
        agent.run(
            "【用户核心关键点】\n关注接口联调\n",
            view="agenda_objective",
            layout="topic_major",
            topic_titles=["接口联调"],
        )
    )

    assert isinstance(result, TopicMajorMinutes)
    call = client.calls[0]
    assert call["model"] is TopicMajorMinutes
    assert call["contract"] is MINUTES_TOPIC_MAJOR_GENERATION_OUTPUT_CONTRACT
    assert call["system"].startswith(MINUTES_TOPIC_MAJOR_GENERATION_PROMPT)
    assert AGENDA_AUX_PROMPT_BLOCK in call["system"]
    assert KEYPOINTS_PROMPT_BLOCK in call["system"]
    assert call["kwargs"]["label"].startswith("minutes/agent/agenda_topic/")


class _AgentStub:
    def __init__(self) -> None:
        self.layout = ""
        self.topic_titles: list[str] = []
        self.view = ""
        self.context = ""

    async def run(self, context: str, *, view: str, layout: str, topic_titles: list[str]):
        self.view = view
        self.layout = layout
        self.topic_titles = topic_titles
        self.context = context

        class _Out:
            def model_dump(self) -> dict:
                return {"headline": "测试纪要"}

        return _Out()


def _agent_system(agent: _AgentStub) -> MeetingAgentSystem:
    system = object.__new__(MeetingAgentSystem)
    system._task_lines = {
        "minutes": {
            "agent_attr": "minutes_agent",
            "empty_draft": {},
        }
    }
    system._line_cn_names = {"minutes": "纪要"}
    system.minutes_agent = agent
    return system


def test_agent_node_injects_layout_and_topic_titles() -> None:
    agent = _AgentStub()
    state = {
        "transcript": "张三：讨论接口联调。",
        "meeting_understanding": {
            "meeting_brief": "",
            "meeting_purpose": "",
            "speakers": [],
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "user": {"name": "张三"},
        "perspective_profile": {},
        "objective_perspective": False,
        "line_extra": {},
        "line_modes": {},
        "templates": {},
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {"headline": "测试纪要"},
                "revision_feedback": [],
            }
        },
        "line_views": {"minutes": "agenda_objective"},
        "line_layouts": {"minutes": "topic_major"},
        "has_valid_agenda": True,
        "valid_agendas": [SimpleNamespace(title="接口联调")],
    }

    asyncio.run(_agent_system(agent)._make_agent_node("minutes")(state))

    assert agent.view == "agenda_objective"
    assert agent.layout == "topic_major"
    assert agent.topic_titles == ["接口联调"]
    assert "【议题主序草稿生成执行准绳】" in agent.context
    assert "topic_summary" in agent.context
    assert "【审定议题草稿生成执行准绳】" not in agent.context
    assert "executive_summary" not in agent.context
