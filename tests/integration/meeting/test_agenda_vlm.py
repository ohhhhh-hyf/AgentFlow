# 拆分自 test_agenda_pipeline.py，覆盖：test_english_vlm_json_to_tagged_transcript_pipeline, test_english_agenda_lang_zh_does_not_activate…

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

pytestmark = pytest.mark.integration

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

def test_english_vlm_json_to_tagged_transcript_pipeline():
    """英文 VLM JSON -> plan -> probe -> process -> align 的纯 Python 链路。"""
    _clear_all_agenda_caches()
    plan = vision_json_to_agenda_plan(_EN_AGENDA_JSON)
    agenda_text = agenda_plan_to_markdown(plan)

    valid = probe_valid_agendas(_EN_TRACK_B_TRANSCRIPT, agenda_text, lang="en")
    assert [item.title for item in valid] == [
        "Opening Remarks",
        "Architecture Review",
        "Release Plan",
    ]

    res = process_agenda_for_minutes(
        _EN_TRACK_B_TRANSCRIPT,
        agenda_text,
        lang="en",
    )
    assert res.has_valid_agenda is True
    assert [item.title for item in res.valid_agendas] == [
        "Opening Remarks",
        "Architecture Review",
        "Release Plan",
    ]
    assert "Architecture Review" in res.tagged_transcript
    assert "Release Plan" in res.tagged_transcript

    alignment = align_agenda_with_transcript(
        plan,
        _EN_TRACK_B_TRANSCRIPT,
        lang="en",
    )
    assert alignment.discussed_count == 3
    assert {
        item.item.title
        for item in alignment.alignments
        if item.status == "discussed"
    } == {"Opening Remarks", "Architecture Review", "Release Plan"}


def test_english_agenda_lang_zh_does_not_activate():
    """同一英文内容议程在 lang=zh 下不应走英文内容轨。"""
    _clear_all_agenda_caches()
    plan = vision_json_to_agenda_plan(_EN_AGENDA_JSON)
    agenda_text = agenda_plan_to_markdown(plan)

    assert probe_valid_agendas(
        _EN_TRACK_B_TRANSCRIPT, agenda_text, lang="zh"
    ) == []

    res = process_agenda_for_minutes(
        _EN_TRACK_B_TRANSCRIPT,
        agenda_text,
        lang="zh",
    )
    assert res.has_valid_agenda is False
