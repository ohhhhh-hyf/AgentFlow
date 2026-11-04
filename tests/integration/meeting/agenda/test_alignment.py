# 拆分自原大文件，保留：test_identify_hub_speakers_english_roles, test_alignment_unmentioned_agenda_marks_skipped, test_alignment_presenter_name_grounding…

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

pytestmark = pytest.mark.integration

PROJECT_ROOT = Path(__file__).resolve().parent

while PROJECT_ROOT.parent != PROJECT_ROOT and not (PROJECT_ROOT / "domains").exists():
    PROJECT_ROOT = PROJECT_ROOT.parent

AGENDA_DIR = (
    PROJECT_ROOT / "data" / "1" / "agenda"
    if (PROJECT_ROOT / "data" / "1" / "agenda").exists()
    else PROJECT_ROOT / "agenda"
)

def test_identify_hub_speakers_english_roles():
    """英文 Host/Moderator 角色能进入枢纽池，且不误伤真实汇报人。"""
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        DiscussionBlock,
        _identify_hub_speakers,
    )

    plan = AgendaPlan(
        items=[
            AgendaItemParsed(seq="01", title="Architecture Review", presenters=["Alice Chen"])
        ]
    )
    plan.meta.attendees = "Host: Carol Wu；Moderator: Dave Park"
    blocks = [
        DiscussionBlock(speaker="Carol Wu", timestamp="", content="Welcome everyone.", index=0),
        DiscussionBlock(speaker="Alice Chen", timestamp="", content="Architecture details.", index=1),
    ]
    hubs, dual = _identify_hub_speakers(plan, blocks)
    assert "Carol Wu" in hubs
    assert "Dave Park" in hubs
    assert "Alice Chen" not in hubs
    assert dual == set()


def test_alignment_unmentioned_agenda_marks_skipped():
    """核心防幻觉单测：验证 Test 1 中发言块独立路由。
    
    结果：
    - 议题01（小艺慧记，申家坤）：申家坤未参会未发言，如实判为 skipped，块数为 0；
    - 议题02（翻译海外，刘畅）：正常讨论，为 discussed；
    - 议题03（HAG）：未参会，为 skipped；
    - 议题04（SpeechASR，陆敬怡等）：陆敬怡发言准确归入议题04（不再被孤立标题抢占到议题01），为 discussed。
    """
    docx_path = AGENDA_DIR / "test1" / "商评1.docx"
    txt_path = AGENDA_DIR / "test1" / "商评1.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 1 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    res = align_agenda_with_transcript(plan, transcript)
    assert len(res.alignments) == 4
    # 核心判决：02 与 04 有效讨论，01 与 03 确实未讨论
    assert res.discussed_count == 2
    assert res.skipped_count == 2

    a1, a2, a3, a4 = res.alignments
    assert a1.item.seq == "01"
    assert a1.status == "skipped"
    assert a1.matched_blocks == []

    assert a2.item.seq == "02"
    assert a2.status == "discussed"
    assert "刘畅" in a2.matched_speakers
    assert len(a2.matched_blocks) > 30

    assert a3.item.seq == "03"
    assert a3.status == "skipped"
    assert a3.matched_blocks == []

    assert a4.item.seq == "04"
    assert a4.status == "discussed"
    assert "陆敬怡" in a4.matched_speakers
    assert len(a4.matched_blocks) > 100

    # 验证按现场研讨真实流向排序：先讨论的 02，随后 04，最后是 skipped 的 01 和 03
    chrono = res.chronological_alignments
    assert len(chrono) == 4
    assert [c.item.seq for c in chrono] == ["02", "04", "01", "03"]


def test_alignment_presenter_name_grounding():
    """验证 Test 2 中 9 项议题依靠汇报人主权发言彻底解决标题错位问题。"""
    docx_path = AGENDA_DIR / "test2" / "商评2.docx"
    txt_path = AGENDA_DIR / "test2" / "商评2.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 2 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    res = align_agenda_with_transcript(plan, transcript)
    assert len(res.alignments) == 9
    assert res.discussed_count == 9

    align_map = {a.item.seq: a for a in res.alignments}

    # 郑爽准确回到 04 IDS，而不是留在小艺慧记或 HAG
    assert "郑爽" in align_map["04"].matched_speakers
    assert len(align_map["04"].matched_blocks) > 100

    # 陈啟锴在 05 HAG
    assert "陈啟锴" in align_map["05"].matched_speakers
    assert len(align_map["05"].matched_blocks) > 100

    # 陆敬怡在 06 SpeechASR
    assert "陆敬怡" in align_map["06"].matched_speakers

    # 孙鹤鸣在 07 SpeechTTS
    assert "孙鹤鸣" in align_map["07"].matched_speakers

    # 张昊辰在 08 HiTranslationService
    assert "张昊辰" in align_map["08"].matched_speakers

    # 验证现场换序（Permutations）：现场 SpeechTTS (07) 发生于 SpeechASR (06) 之前
    chrono2 = res.chronological_alignments
    assert len(chrono2) == 9
    chrono_seqs = [c.item.seq for c in chrono2]
    assert chrono_seqs.index("07") < chrono_seqs.index("06")


def test_alignment_speaker_name_typo_fuzzy_reconciled():
    """验证 商评2 中 OCR 识别错字（陈啟错）的自动纠错与对齐：
    1. match_presenter_name 识别 错 与 锴 的 OCR 易混变体，打分达 0.95；
    2. parse_agenda_text 传入 transcript 时自动校准为真实发言人 陈啟锴；
    3. align_agenda_with_transcript 将第 5 项（HAG）成功判定为 discussed，不再沦为 [本次未讨论]。
    """
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        match_presenter_name,
        parse_agenda_text,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import align_agenda_with_transcript

    # 1. 变体与形似容错打分
    assert match_presenter_name("陈啟错", "陈啟锴") >= 0.9
    assert match_presenter_name("陈启蒙", "陈啟锴") == 0.0  # 杜绝异人同姓字辈误伤

    docx_path = AGENDA_DIR / "test2" / "商评2.docx"
    txt_path = AGENDA_DIR / "test2" / "商评2.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 2 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    # 模拟 OCR 出现错别字 陈啟错
    agenda_with_typo = txt_path.read_text(encoding="utf-8").replace("陈啟锴", "陈啟错")
    assert "陈啟错" in agenda_with_typo

    plan = parse_agenda_text(agenda_with_typo, transcript=transcript)
    hag_item = next(it for it in plan.items if "HAG" in it.title)
    assert "陈啟锴" in hag_item.presenters

    res = align_agenda_with_transcript(plan, transcript)
    hag_align = next(a for a in res.alignments if "HAG" in a.item.title)
    assert hag_align.status == "discussed"
    assert len(hag_align.matched_blocks) > 0
    assert res.discussed_count == 9
    assert res.skipped_count == 0
