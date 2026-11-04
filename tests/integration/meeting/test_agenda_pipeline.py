# 拆分自原大文件，保留：test_agenda_minutes_fallback_in_orchestrator, test_fail_fast_when_agenda_empty…

"""tests/integration/meeting/test_agenda_pipeline.py -- 议程驱动型会议纪要端到端生成工作流集成测试。"""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import docx
import pytest
from domains.meeting.agenda_engine import (
    clear_agenda_engine_cache,
    probe_valid_agendas,
    process_agenda_for_minutes,
)
from domains.meeting.agenda_vision import (
    agenda_plan_to_markdown,
    vision_json_to_agenda_plan,
)
from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    clear_agenda_parser_cache,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    clear_alignment_cache,
    group_transcript_blocks,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
    SingleAgendaItemModel,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_render import (
    AgendaMinutesRender,
)
from infra.exporters.html.agenda_minutes import (
    format_agenda_minutes_markdown,
    render_agenda_minutes_html,
)

PROJECT_ROOT = Path(__file__).resolve().parent

while PROJECT_ROOT.parent != PROJECT_ROOT and not (PROJECT_ROOT / "domains").exists():
    PROJECT_ROOT = PROJECT_ROOT.parent

AGENDA_DIR = (
    PROJECT_ROOT / "data" / "1" / "agenda"
    if (PROJECT_ROOT / "data" / "1" / "agenda").exists()
    else PROJECT_ROOT / "agenda"
)

_EN_AGENDA_JSON = {
    "theme": "Architecture Workshop",
    "date_time": "2026-10-27",
    "attendees": ["Facilitator"],
    "agenda_items": [
        {"seq": "01", "title": "Opening Remarks"},
        {"seq": "02", "title": "Architecture Review"},
        {"seq": "03", "title": "Release Plan"},
    ],
}

_EN_TRACK_B_TRANSCRIPT = (
    "[00:00:05] Speaker 1: Good morning everyone. Welcome.\n\n"
    "[00:00:15] Speaker 1: Let's start with the opening remarks.\n\n"
    "[00:05:00] Speaker 2: Now let's move on to the architecture review. "
    "The gateway redesign reduces latency to 120 ms.\n\n"
    "[00:15:00] Speaker 3: Next, the release plan. "
    "We have three milestones and will launch in December.\n"
)

def _clear_all_agenda_caches() -> None:
    clear_agenda_parser_cache()
    clear_alignment_cache()
    clear_agenda_engine_cache()

def test_agenda_minutes_fallback_in_orchestrator():
    """测试当 Supervisor 驳回降级时，Orchestrator 产出完整的 Markdown 纪要而非裸字典。"""
    import asyncio

    async def _run():
        from domains.meeting.orchestrator import MeetingAgentSystem
        class DummyClient:
            pass
        orch = MeetingAgentSystem(client=DummyClient())

        draft = {
            "meeting_meta": {"theme": "降级测试例会", "date_time": "2026/09/28"},
            "agenda_items": [
                {
                    "agenda_seq": "01",
                    "agenda_title": "测试议题一",
                    "presenter": "张工",
                    "status_tag": "[审议通过]",
                    "proposal_highlights": ["方案陈述"],
                    "resolution": "同意",
                    "discussion_state": "discussed",
                }
            ],
        }
        state = {
            "lines": {"agenda_minutes": {"draft": draft}},
            "title": "降级测试例会",
        }

        fallback_node = orch._make_fallback_node("agenda_minutes")
        out = await fallback_node(state)

        line_out = out["lines"]["agenda_minutes"]
        assert line_out["degraded"] is True
        rendered_text = line_out["rendered"]
        # 验证降级产物是完整的 Markdown 而非 str(dict)
        assert "# 议程纪要" in rendered_text
        assert "### 测试议题一" in rendered_text
        assert len(line_out["structure"]) == 1

    asyncio.run(_run())


def test_fail_fast_when_agenda_empty():
    """测试若未能从输入提取出会前议程单，Agent 立即 Fail-Fast，绝不反向解析转写污染骨架。"""
    import asyncio

    async def _run():
        class DummyClient:
            pass

        agent = AgendaMinutesAgent(DummyClient())
        with pytest.raises(ValueError, match="未能从输入文档中解析出会前既定议程单"):
            await agent.run("这里只有会议转写，没有议程表格也没有任何议程序号...")

    asyncio.run(_run())
