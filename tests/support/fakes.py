"""轻量测试替身与流程驱动。"""
from __future__ import annotations


def make_minutes_mock_client(called_labels: list[str], *, headline: str):
    """构造纪要链路的 MagicMock 客户端，记录 structured 调用 label。"""
    from unittest.mock import MagicMock

    from domains.meeting.models_generated import (
        MeetingUnderstanding,
        Minutes,
        MinutesSupervisorReview,
    )

    client = MagicMock()

    async def mock_structured(prompt, *args, **kwargs):
        label = kwargs.get("label", "")
        called_labels.append(label)
        if "meeting_understanding" in label:
            return MeetingUnderstanding(meeting_brief="测试", meeting_purpose="目的")
        if "minutes/agent" in label:
            return Minutes(executive_summary=["段落1"])
        if "minutes/supervisor" in label:
            return MinutesSupervisorReview(
                decision="approve",
                facts_check={"passed": True, "issues": []},
                perspective_check={"passed": True, "issues": []},
                consistency_check={"passed": True, "issues": []},
                feedback=[],
            )
        raise ValueError(f"Unexpected label {label}")

    client.structured.side_effect = mock_structured
    return client


async def run_minutes_graph(
    *,
    transcript: str,
    lang: str,
    agenda_text: str = "",
    headline: str = "测试标题",
):
    """用假客户端跑一遍 minutes 图，返回 (system, final_state, called_labels)。"""
    from domains.meeting.agenda_engine import clear_agenda_engine_cache
    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.meeting.tasks.agenda_minutes.agenda_parser import clear_agenda_parser_cache
    from domains.meeting.tasks.agenda_minutes.alignment_engine import clear_alignment_cache

    clear_agenda_parser_cache()
    clear_alignment_cache()
    clear_agenda_engine_cache()

    called: list[str] = []
    client = make_minutes_mock_client(called, headline=headline)
    system = MeetingAgentSystem(client)
    graph = system._build_graph(["minutes"])
    state = {
        "transcript": transcript,
        "user": {},
        "lang": lang,
        "line_extra": {"agenda_text": agenda_text} if agenda_text else {},
        "lines": {"minutes": {"revision_count": 0}},
    }
    final = await graph.ainvoke(state)
    return system, final, called
