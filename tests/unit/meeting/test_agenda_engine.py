import pytest

from domains.meeting.agenda_engine import (
    ValidAgendaItem,
    AgendaProcessResult,
    probe_valid_agendas,
    process_agenda_for_minutes,
    build_tagged_transcript_with_head_tail,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import DiscussionBlock


def test_agenda_engine_empty_inputs():
    assert probe_valid_agendas("", "") == []
    assert probe_valid_agendas("some transcript", "") == []
    assert probe_valid_agendas("", "1. 议题一") == []

    res = process_agenda_for_minutes("", "")
    assert not res.has_valid_agenda
    assert res.valid_agendas == []
    assert res.tagged_transcript == ""


def test_agenda_engine_non_agenda_document():
    transcript = """
    张三: 今天我们讨论一下系统的部署架构。
    李四: 好的，我建议采用Kubernetes集群方案。
    """
    non_agenda_doc = """
    def calculate_tax(income):
        return income * 0.2
    """
    valid = probe_valid_agendas(transcript, non_agenda_doc)
    assert valid == []

    res = process_agenda_for_minutes(transcript, non_agenda_doc)
    assert not res.has_valid_agenda
    assert res.valid_agendas == []
    assert res.tagged_transcript == transcript


def test_agenda_engine_ceremonial_and_skipped_filtering():
    agenda_text = """
    1. 观看公司宣传片（会务组）
    2. 自研车载芯片二期量产（主讲人：张三）
    3. 全体合影留念（会务组）
    4. 智能客服降本方案（主讲人：王五）
    5. 下半年团建方案（主讲人：赵六）
    """
    transcript = """
    主持人: 各位上午好，请大家先看大屏幕上的宣传片，稍后开始。
    张三 10:00:
    各位好，关于自研车载芯片二期量产，目前A样芯片良率已经达到了91.5%，综合功耗超出预期。
    我们需要追加1200万元流片预算。
    李四: 我赞同追加预算。
    主持人: 大家在背景板前合个影，一二三茄子。
    王五 10:30:
    接下来由我汇报智能客服降本方案。目前客服月均成本达到80万元，我们计划用AI替代70%常规咨询。
    下周在华东大区上线试点。
    主持人: 时间到了，今天的团建方案今天来不及讨论了，改天再对齐。散会！
    """
    valid = probe_valid_agendas(transcript, agenda_text)
    titles = [item.title for item in valid]

    # 验证仪式项（宣传片、合影）被剔除
    assert not any("宣传片" in t for t in titles)
    assert not any("合影" in t for t in titles)
    # 验证未讨论项（团建）被剔除
    assert not any("团建" in t for t in titles)
    # 验证实质讨论项被保留
    assert any("自研车载芯片" in t for t in titles)
    assert any("智能客服" in t for t in titles)


def test_agenda_engine_chronological_reordering():
    # 议程单原顺序：1. 客服方案 2. 芯片二期
    agenda_text = """
    1. 智能客服降本方案（汇报人：王五）
    2. 自研车载芯片二期量产（汇报人：张三）
    """
    # 现场实际先聊了芯片，再聊客服
    transcript = """
    张三 09:00:
    王五临时有事，我先汇报自研车载芯片二期量产。目前良率91.5%，建议追加流片资金。
    王五 09:30:
    我赶到了，现在由我汇报智能客服降本方案，计划分流70%咨询。
    """
    valid = probe_valid_agendas(transcript, agenda_text)
    assert len(valid) == 2
    # 验证重排为现场实际时序
    assert "芯片" in valid[0].title
    assert "客服" in valid[1].title


def test_agenda_engine_head_and_tail_protection():
    all_blocks = [
        DiscussionBlock(speaker="主持人", timestamp="09:00", content="各位领导上午好，今天召开战略决策会，感谢大家准时参会。", index=0),
        DiscussionBlock(speaker="张三", timestamp="09:10", content="关于芯片二期，我们的核心数据如下，良率91.5%...", index=1),
        DiscussionBlock(speaker="李总", timestamp="09:50", content="大家讲得很好，最后定下来追加1200万预算，海外合规抓紧办，散会。", index=2),
    ]
    valid_item = ValidAgendaItem(
        seq="1",
        title="芯片二期进展",
        presenters=["张三"],
        start_index=1,
        end_index=2,
        matched_blocks=[all_blocks[1]],
    )
    tagged = build_tagged_transcript_with_head_tail(all_blocks, [valid_item])

    assert "【会议开场背景与主线脉络】" in tagged
    assert "今天召开战略决策会" in tagged
    assert "【议题 1：芯片二期进展】（汇报人：张三）" in tagged
    assert "良率91.5%" in tagged
    assert "【会末收尾与全场定调】" in tagged
    assert "最后定下来追加1200万预算" in tagged


def test_agenda_parser_cache_and_no_duplicate_logging(caplog):
    """验证多次探测与处理同一议程单时，启用解析缓存且日志绝不重复打印既定议程识别。"""
    from domains.meeting.tasks.agenda_minutes.agenda_parser import clear_agenda_parser_cache
    import logging

    clear_agenda_parser_cache()
    caplog.set_level(logging.INFO)

    agenda_text = """
    | 序号 | 议题名称 | 汇报人 |
    | 1 | 议题甲 | 张三 |
    | 2 | 议题乙 | 李四 |
    """
    transcript = """
    张三: 各位好，我们现在开始汇报议题甲。目前进展顺利。
    李四: 好的，接下来开始汇报议题乙。各项指标合格。
    """

    # 模拟实际流程：1次 probe_valid_agendas + 2次 process_agenda_for_minutes
    valid1 = probe_valid_agendas(transcript, agenda_text)
    assert len(valid1) == 2

    res2 = process_agenda_for_minutes(transcript, agenda_text)
    assert res2.has_valid_agenda
    assert len(res2.valid_agendas) == 2

    res3 = process_agenda_for_minutes(transcript, agenda_text)
    assert res3.has_valid_agenda

    # 关键断言：无论调用多少次，既定议程识别成功信息与对齐引擎启动信息在 INFO 级别只输出 1 次！
    agenda_log_count = caplog.text.count("[AGENDA_PARSER] 既定议程单识别成功")
    assert agenda_log_count == 1, f"Expected 1 agenda log, got {agenda_log_count}"

    alignment_log_count = caplog.text.count("[AGENDA_ALIGNMENT] 启动对齐引擎")
    assert alignment_log_count == 1, f"Expected 1 alignment log, got {alignment_log_count}"


def test_parser_log_dedup_across_different_transcript_speakers(caplog):
    """验证即使探针阶段与流水线执行阶段转写格式有细微差别导致发言人集合不完全一致，解析日志依然全局只输出 1 次。"""
    from domains.meeting.tasks.agenda_minutes.agenda_parser import clear_agenda_parser_cache
    import logging

    clear_agenda_parser_cache()
    caplog.set_level(logging.INFO)

    agenda_text = """
    | 序号 | 议题名称 | 汇报人 |
    | 1 | 核心算法演进 | 王五 |
    """
    transcript1 = "王五 10:00: 各位好，我们现在开始汇报核心算法演进方案，整体指标均已达到预期。\n赵六: 旁听发言。"
    transcript2 = "王五 10:00: 各位好，我们现在开始汇报核心算法演进方案，整体指标均已达到预期。"  # 少了赵六，发言人列表不同

    valid = probe_valid_agendas(transcript1, agenda_text)
    assert len(valid) == 1

    res = process_agenda_for_minutes(transcript2, agenda_text)
    assert res.has_valid_agenda

    agenda_log_count = caplog.text.count("[AGENDA_PARSER] 既定议程单识别成功")
    assert agenda_log_count == 1, f"Expected 1 agenda log, got {agenda_log_count}"


def test_probe_valid_agendas_passes_lang(monkeypatch):
    """入口探测必须把 lang 透传给 process_agenda_for_minutes。"""
    from domains.meeting import agenda_engine

    captured: dict[str, str] = {}

    def fake_process(transcript, agenda_text, *, lang="zh"):
        captured["lang"] = lang
        return AgendaProcessResult(
            has_valid_agenda=True,
            valid_agendas=[],
            tagged_transcript="",
        )

    monkeypatch.setattr(agenda_engine, "process_agenda_for_minutes", fake_process)
    agenda_engine.probe_valid_agendas("t", "a", lang="en")
    assert captured["lang"] == "en"


def test_process_agenda_passes_lang(monkeypatch):
    """二次处理必须把 lang 透传给 alignment。"""
    from domains.meeting import agenda_engine
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        AgendaItemParsed,
        AgendaPlan,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        AlignmentResult,
        DiscussionBlock,
    )

    item = AgendaItemParsed(
        seq="01", title="Architecture Review", presenters=["Alice Chen"]
    )
    captured: dict[str, str] = {}

    def fake_parse(text, transcript="", candidate_speakers=None):
        return AgendaPlan(items=[item])

    def fake_align(plan, transcript, *, lang="zh"):
        captured["lang"] = lang
        block = DiscussionBlock(
            speaker="Alice Chen",
            timestamp="00:01",
            content="Architecture review details and release plan.",
            index=0,
        )
        align = AgendaAlignment(
            item=plan.items[0],
            status="discussed",
            matched_speakers=["Alice Chen"],
            matched_blocks=[block],
            start_index=0,
            end_index=1,
        )
        return AlignmentResult(
            plan=plan,
            alignments=[align],
            all_speakers={"Alice Chen"},
            adhoc_blocks=[],
        )

    monkeypatch.setattr(agenda_engine, "parse_agenda_text", fake_parse)
    monkeypatch.setattr(agenda_engine, "align_agenda_with_transcript", fake_align)
    agenda_engine.clear_agenda_engine_cache()

    res = agenda_engine.process_agenda_for_minutes(
        "Alice Chen 00:01\nArchitecture review details and release plan.",
        "1. Architecture Review",
        lang="en",
    )
    assert captured["lang"] == "en"
    assert res.has_valid_agenda is True
    assert res.valid_agendas[0].title == "Architecture Review"


def test_process_agenda_for_minutes_english_cache_key(monkeypatch):
    """同一输入在 zh/en 下不得共用 process 缓存。"""
    from domains.meeting import agenda_engine
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        AgendaItemParsed,
        AgendaPlan,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import AlignmentResult

    item = AgendaItemParsed(
        seq="01", title="Architecture Review", presenters=["Alice Chen"]
    )
    calls: list[str] = []

    def fake_parse(text, transcript="", candidate_speakers=None):
        return AgendaPlan(items=[item])

    def fake_align(plan, transcript, *, lang="zh"):
        calls.append(lang)
        return AlignmentResult(
            plan=plan,
            alignments=[],
            all_speakers=set(),
            adhoc_blocks=[],
        )

    monkeypatch.setattr(agenda_engine, "parse_agenda_text", fake_parse)
    monkeypatch.setattr(agenda_engine, "align_agenda_with_transcript", fake_align)
    agenda_engine.clear_agenda_engine_cache()

    agenda_engine.process_agenda_for_minutes("t", "a", lang="zh")
    agenda_engine.process_agenda_for_minutes("t", "a", lang="en")
    assert calls == ["zh", "en"]


def test_extract_valid_agendas_passes_lang(monkeypatch):
    """仪式过滤必须收到正确的 lang。"""
    from types import SimpleNamespace

    from domains.meeting import agenda_engine
    from domains.meeting.tasks.agenda_minutes.agenda_parser import AgendaItemParsed

    captured: dict[str, str] = {}

    def fake_trivial(align, *, lang="zh"):
        captured["lang"] = lang
        return False

    monkeypatch.setattr(agenda_engine, "is_trivial_ceremonial_item", fake_trivial)
    align = SimpleNamespace(
        status="discussed",
        item=AgendaItemParsed(
            seq="01", title="Architecture Review", presenters=[]
        ),
        matched_blocks=[object()],
        start_index=0,
        end_index=1,
    )
    res = SimpleNamespace(chronological_alignments=[align])

    valid = agenda_engine._extract_valid_agendas_from_alignment(res, lang="en")
    assert captured["lang"] == "en"
    assert len(valid) == 1


def test_process_agenda_for_minutes_english_filters_ceremonial():
    """英文议题增强链路：Group Photo / Lunch Break / Video Playback 不进入有效议题。"""
    from domains.meeting import agenda_engine
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        clear_agenda_parser_cache,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        clear_alignment_cache,
    )

    agenda = """
| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| --- | --- | --- | --- |
| 01 | Group Photo |  | 5 min |
| 02 | Architecture Review | Alice Chen | 20 min |
| 03 | Lunch Break |  | 60 min |
| 04 | Release Plan | Bob Lee | 15 min |
| 05 | Video Playback |  | 10 min |
"""
    transcript = (
        "[00:00:05] Carol Wu: Good morning everyone. Let's get started.\n\n"
        "[00:00:15] Carol Wu: Next up, Alice Chen.\n\n"
        "[00:00:25] Alice Chen: The architecture review covers the gateway "
        "redesign. We measured 120 ms latency and will release the new version "
        "next month.\n\n"
        "[00:10:00] Carol Wu: Moving on to the next item, Bob.\n\n"
        "[00:10:10] Bob Lee: The release plan has three milestones. We will "
        "complete testing by November and launch in December.\n\n"
        "[00:15:00] Carol Wu: Let's take a group photo.\n\n"
        "[00:16:00] Carol Wu: We'll have lunch after this.\n\n"
        "[00:20:00] Carol Wu: That's all for today. Thanks everyone.\n"
    )

    clear_agenda_parser_cache()
    clear_alignment_cache()
    agenda_engine.clear_agenda_engine_cache()

    res = agenda_engine.process_agenda_for_minutes(
        transcript,
        agenda,
        lang="en",
    )
    assert res.has_valid_agenda is True
    assert [item.title for item in res.valid_agendas] == [
        "Architecture Review",
        "Release Plan",
    ]


_EN_AGENDA = """
| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| --- | --- | --- | --- |
| 01 | Architecture Review | Alice Chen | 20 min |
| 02 | Release Plan | Bob Lee | 15 min |
"""

_EN_TRANSCRIPT = (
    "[00:00:05] Carol Wu: Good morning everyone. Let's get started.\n\n"
    "[00:00:15] Carol Wu: Next up, Alice Chen.\n\n"
    "[00:00:25] Alice Chen: The architecture review covers the gateway redesign. "
    "We measured 120 ms latency and will release the new version next month.\n\n"
    "[00:10:00] Carol Wu: Moving on to the next item, Bob.\n\n"
    "[00:10:10] Bob Lee: The release plan has three milestones. "
    "We will complete testing by November and launch in December.\n\n"
    "[00:20:00] Carol Wu: That's all for today. Thanks everyone.\n"
)


def _clear_agenda_caches() -> None:
    from domains.meeting import agenda_engine
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        clear_agenda_parser_cache,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        clear_alignment_cache,
    )

    clear_agenda_parser_cache()
    clear_alignment_cache()
    agenda_engine.clear_agenda_engine_cache()


def test_probe_valid_agendas_english():
    """真实英文议程 + 英文转写：probe 应返回两个有效议题。"""
    from domains.meeting.agenda_engine import probe_valid_agendas

    _clear_agenda_caches()
    valid = probe_valid_agendas(_EN_TRANSCRIPT, _EN_AGENDA, lang="en")
    assert [item.title for item in valid] == [
        "Architecture Review",
        "Release Plan",
    ]


def test_process_agenda_for_minutes_english():
    """真实英文议程 + 英文转写：process 应产出有效议题与英文打标转写。"""
    from domains.meeting.agenda_engine import process_agenda_for_minutes

    _clear_agenda_caches()
    res = process_agenda_for_minutes(_EN_TRANSCRIPT, _EN_AGENDA, lang="en")
    assert res.has_valid_agenda is True
    assert [item.title for item in res.valid_agendas] == [
        "Architecture Review",
        "Release Plan",
    ]
    assert "Architecture Review" in res.tagged_transcript
    assert "Release Plan" in res.tagged_transcript


def test_english_ceremonial_and_skipped_filtering():
    """英文仪式项与未讨论项都不进入有效议题。"""
    from domains.meeting.agenda_engine import process_agenda_for_minutes

    agenda = """
| 序号 | 议题名称 | 汇报人/主讲人 |
| --- | --- | --- |
| 01 | Group Photo |  |
| 02 | Architecture Review | Alice Chen |
| 03 | Security Update | Dave Park |
"""
    transcript = (
        "[00:00:05] Carol Wu: Good morning everyone.\n\n"
        "[00:00:15] Carol Wu: Next up, Alice Chen.\n\n"
        "[00:00:25] Alice Chen: The architecture review covers the gateway "
        "redesign. We measured 120 ms latency and will release the new version "
        "next month.\n\n"
        "[00:20:00] Carol Wu: That's all for today. Thanks everyone.\n"
    )

    _clear_agenda_caches()
    res = process_agenda_for_minutes(transcript, agenda, lang="en")
    assert res.has_valid_agenda is True
    assert [item.title for item in res.valid_agendas] == ["Architecture Review"]
