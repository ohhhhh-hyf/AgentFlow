# 拆分自 test_alignment.py，覆盖：test_english_session_closing_signals, test_english_closing_exclusion, test_english_opening_signals…

"""tests/unit/meeting/test_agenda_alignment.py -- 议程与转写实录时间线对齐引擎单元测试。"""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import docx
import pytest
from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    group_transcript_blocks,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
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

def test_english_session_closing_signals():
    """英文收尾信号只在 lang=en 下生效，且中文信号不串用。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        _is_session_closing,
    )

    closing = [
        "That's all for today.",
        "That concludes the meeting.",
        "Let's call it a day.",
        "We're done.",
        "I'll stop here.",
        "To wrap up, let's summarize.",
        "Thanks everyone.",
        "Thank you all.",
        "See you next time.",
        "Bye.",
    ]
    for text in closing:
        assert _is_session_closing(text, lang="en") is True, text
    assert _is_session_closing("谢谢各位，散会", lang="en") is False


def test_english_closing_exclusion():
    """感谢提问/反馈不能被误判为会议收尾。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        _is_session_closing,
    )

    for text in [
        "Thank you for the question.",
        "Thanks for the feedback.",
        "Thanks for pointing that out.",
        "Good question.",
        "Let me clarify.",
        "I'll explain.",
        "Thank you all for the question.",
    ]:
        assert _is_session_closing(text, lang="en") is False, text


def test_english_opening_signals():
    """英文开场/共享屏幕信号只在 lang=en 下生效。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        _is_opening_signal,
    )

    for text in [
        "Can you see my screen?",
        "I'm sharing my screen.",
        "Let me share.",
        "Let's get started.",
        "Let's begin.",
        "Good morning everyone.",
        "Good afternoon, everyone.",
        "I'll start with the architecture.",
        "Today I'll walk you through the release plan.",
        "Here's the agenda.",
    ]:
        assert _is_opening_signal(text, lang="en") is True, text
    assert _is_opening_signal("各位评委好，我来共享屏幕", lang="en") is False


def test_english_equipment_chitchat():
    """英文设备试音/闲聊识别，且不误伤技术讨论。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        _is_equipment_or_chitchat,
    )

    for text in [
        "Can you hear me?",
        "Can everyone hear me?",
        "You're on mute.",
        "Microphone is not working.",
        "Microphone.",
        "I lost connection.",
        "I'm reconnecting.",
        "The screen is lagging.",
        "One moment.",
        "Give me a second.",
        "I need coffee.",
        "Going to the bathroom.",
        "Let's take a break.",
    ]:
        assert _is_equipment_or_chitchat(text, lang="en") is True, text

    for text in [
        "The microphone array calibration is complete.",
        "The connection pool handles 50k concurrent requests.",
        "This architecture review covers the release plan.",
        "喂喂，能听到吗",
    ]:
        assert _is_equipment_or_chitchat(text, lang="en") is False, text


def test_english_host_roadsign():
    """英文主持人换场：指名、议题名、泛指串场与角色标签。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        _detect_host_roadsign,
    )

    plan = AgendaPlan(
        items=[
            AgendaItemParsed(
                seq="01", title="Architecture Review", presenters=["Alice Chen"]
            ),
            AgendaItemParsed(
                seq="02", title="Release Plan", presenters=["Bob Lee"]
            ),
            AgendaItemParsed(
                seq="03", title="Security Update", presenters=["Carol Wu"]
            ),
        ]
    )
    hubs = {"Carol Wu"}

    cases = [
        ("Next up, Alice Chen.", "01", False),
        ("Moving on to the next item, Bob.", "02", False),
        ("Please welcome Carol Wu.", "03", False),
        ("I'd like to invite Alice Chen.", "01", False),
        ("Let's move on to the release plan.", "02", False),
        ("Now we'll hear from Bob Lee.", "02", False),
        ("Over to Alice.", "01", False),
        ("Hand it over to Carol.", "03", False),
        ("Switching to Security Update.", "03", False),
    ]
    for content, expected_seq, expected_generic in cases:
        got_seq, got_generic = _detect_host_roadsign(
            "Carol Wu", content, plan, hubs, lang="en"
        )
        assert got_seq == expected_seq, (content, got_seq)
        assert got_generic is expected_generic, (content, got_generic)

    for text in [
        "Next item.",
        "Next one.",
        "Next topic.",
        "Moving on.",
        "Let's move on.",
        "Up next.",
    ]:
        got_seq, got_generic = _detect_host_roadsign(
            "Carol Wu", text, plan, hubs, lang="en"
        )
        assert got_seq is None
        assert got_generic is True

    # 非枢纽人物不触发
    assert _detect_host_roadsign(
        "Alice Chen", "Next up, Bob Lee.", plan, hubs, lang="en"
    ) == (None, False)

    # 角色标签 Host 自身可作为主持人
    assert _detect_host_roadsign(
        "Host", "Next up, Alice Chen.", plan, set(), lang="en"
    ) == ("01", False)

    # 中文串场词在 en 下不生效
    assert _detect_host_roadsign(
        "Carol Wu", "下面有请 Alice Chen", plan, hubs, lang="en"
    ) == (None, False)


def test_english_has_team_case_insensitive():
    """英文发言人大小写不同，也必须能通过 has_team 核验进入 discussed。"""
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(
                seq="01", title="Architecture Review", presenters=["Alice Chen"]
            )
        ]
    )
    transcript = (
        "alice chen 00:01\n"
        "The architecture review covers the gateway redesign. "
        "We measured 120 ms latency and will release the new version next month."
    )
    res = align_agenda_with_transcript(plan, transcript, lang="en")
    assert res.alignments[0].status == "discussed"


def test_english_doctor_name_boost():
    """正文出现 Dr. Chen 时，应对 Dr. Alice Chen 所属议题加分。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        DiscussionBlock,
        _score_block_for_item,
    )

    item = AgendaItemParsed(
        seq="01", title="Architecture Review", presenters=["Dr. Alice Chen"]
    )
    block = DiscussionBlock(
        speaker="Carol Wu",
        timestamp="",
        content="Dr. Chen will lead the architecture review.",
        index=0,
    )
    score = _score_block_for_item(
        block,
        item,
        ["architecture"],
        set(),
        False,
        lang="en",
    )
    assert score >= 2.0


def test_align_english_transcript_named_track():
    """英文 NAMED 轨：汇报人姓名能驱动议题归属。"""
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(
                seq="01", title="Architecture Review", presenters=["Alice Chen"]
            ),
            AgendaItemParsed(
                seq="02", title="Release Plan", presenters=["Bob Lee"]
            ),
        ]
    )
    transcript = (
        "[00:00:05] Carol Wu: Good morning everyone. Let's get started.\n\n"
        "[00:00:15] Carol Wu: Next up, Alice Chen.\n\n"
        "[00:00:25] Alice Chen: The architecture review covers the gateway redesign. "
        "We measured 120 ms latency and will release the new version next month.\n\n"
        "[00:10:00] Carol Wu: Moving on to the next item, Bob.\n\n"
        "[00:10:10] Bob Lee: The release plan has three milestones. "
        "We will complete testing by November and launch in December.\n\n"
        "[00:20:00] Carol Wu: That's all for today. Thanks everyone.\n"
    )
    res = align_agenda_with_transcript(plan, transcript, lang="en")
    discussed = [a.item.seq for a in res.alignments if a.status == "discussed"]
    assert discussed == ["01", "02"]


def test_align_english_transcript_content_track():
    """英文 CONTENT 轨：无汇报人时靠英文转场词与议题信号切换。"""
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(seq="01", title="Opening Remarks", presenters=[]),
            AgendaItemParsed(seq="02", title="Architecture Review", presenters=[]),
            AgendaItemParsed(seq="03", title="Release Plan", presenters=[]),
            AgendaItemParsed(seq="04", title="Group Photo", presenters=[]),
        ]
    )
    transcript = (
        "[00:00:05] Speaker 1: Good morning everyone. "
        "Welcome to the architecture review workshop.\n\n"
        "[00:00:15] Speaker 1: Let's start with the opening remarks.\n\n"
        "[00:05:00] Speaker 2: Now let's move on to the architecture review. "
        "The gateway redesign reduces latency to 120 ms.\n\n"
        "[00:15:00] Speaker 3: Next, the release plan. "
        "We have three milestones and will launch in December.\n\n"
        "[00:25:00] Speaker 1: Finally, let's take a group photo.\n"
    )
    res = align_agenda_with_transcript(plan, transcript, lang="en")
    statuses = {a.item.seq: a.status for a in res.alignments}
    assert statuses["01"] == "discussed"
    assert statuses["02"] == "discussed"
    assert statuses["03"] == "discussed"
    assert statuses["04"] == "discussed"


def test_english_ceremonial_filtering():
    """英文仪式/后勤项剔除，实质议题保留。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        is_trivial_ceremonial_item,
    )

    for title in [
        "Group Photo",
        "Lunch Break",
        "Video Playback",
        "Campus Tour",
        "Registration",
        "Coffee Break",
    ]:
        item = AgendaItemParsed(seq="01", title=title, presenters=[])
        align = AgendaAlignment(item=item, status="skipped", matched_blocks=[])
        assert is_trivial_ceremonial_item(align, lang="en") is True, title

    for title in [
        "Architecture Review",
        "Release Plan",
        "Technical Deep Dive",
        "Q&A Session",
    ]:
        item = AgendaItemParsed(seq="01", title=title, presenters=[])
        align = AgendaAlignment(item=item, status="skipped", matched_blocks=[])
        assert is_trivial_ceremonial_item(align, lang="en") is False, title


def test_english_ceremonial_discussed_short():
    """英文仪式项即使有极短讨论，也应判为过场。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        DiscussionBlock,
        is_trivial_ceremonial_item,
    )

    item = AgendaItemParsed(seq="01", title="Group Photo", presenters=[])
    block = DiscussionBlock(
        speaker="Carol Wu",
        timestamp="",
        content="Everyone, please come to the front for a group photo.",
        index=0,
    )
    align = AgendaAlignment(
        item=item,
        status="discussed",
        matched_blocks=[block],
    )
    assert is_trivial_ceremonial_item(align, lang="en") is True


def test_english_substantive_ceremonial_item_kept():
    """标题含 video 但内容有实质技术讨论时，不应误删。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        DiscussionBlock,
        is_trivial_ceremonial_item,
    )

    item = AgendaItemParsed(
        seq="01",
        title="Video Playback Performance Review",
        presenters=["Alice Chen"],
    )
    text = (
        "The video playback performance review covers latency, frame dropping, "
        "and codec optimization across the release build. "
    ) * 3
    blocks = [
        DiscussionBlock(
            speaker="Alice Chen",
            timestamp="",
            content=text,
            index=i,
        )
        for i in range(3)
    ]
    align = AgendaAlignment(
        item=item,
        status="discussed",
        matched_blocks=blocks,
    )
    assert is_trivial_ceremonial_item(align, lang="en") is False


def test_english_ceremonial_lang_isolation():
    """中英文仪式过滤互不串用。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        is_trivial_ceremonial_item,
    )

    cn_item = AgendaItemParsed(seq="01", title="全体合影", presenters=[])
    cn_align = AgendaAlignment(item=cn_item, status="skipped", matched_blocks=[])
    assert is_trivial_ceremonial_item(cn_align, lang="en") is False

    en_item = AgendaItemParsed(seq="02", title="Group Photo", presenters=[])
    en_align = AgendaAlignment(item=en_item, status="skipped", matched_blocks=[])
    assert is_trivial_ceremonial_item(en_align, lang="zh") is False
