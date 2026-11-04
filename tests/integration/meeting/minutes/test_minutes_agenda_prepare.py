# 拆分自 test_agenda.py，覆盖：test_tasks_prepare_minutes_with_valid_agenda, test_prepare_agenda_with_aux, test_prepare_minutes_passes_lang_to_agenda_vlm…

from core.execution.hard_execution import is_agenda_enhanced_mode
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.meeting_core.prompts import (
    MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
)
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from domains.meeting.agenda_engine import (
    ValidAgendaItem,
    AgendaProcessResult,
    process_agenda_for_minutes,
    probe_valid_agendas,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import DiscussionBlock
from domains.meeting.orchestrator import _Nodes
from app.tasks import _prepare
from app.schemas import TaskRequest

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

_ZH_AGENDA = """
| 序号 | 议题名称 | 汇报人/主讲人 |
| --- | --- | --- |
| 01 | 架构评审 | 张三 |
| 02 | 发布计划 | 李四 |
"""

_ZH_TRANSCRIPT = (
    "张三 00:01\n关于架构评审，网关重构把时延降低到120ms，下月发布新版本。\n\n"
    "李四 00:10\n关于发布计划，我们有三个里程碑，十一月完成测试，十二月上线。\n"
)

def _make_minutes_mock_client(called_labels: list[str], *, headline: str):
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
            return MeetingUnderstanding(
                meeting_brief="测试",
                meeting_purpose="目的",
            )
        if "minutes/agent" in label:
            return Minutes(headline=headline, executive_summary=["段落1"])
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

async def _run_minutes_graph(
    *,
    transcript: str,
    lang: str,
    agenda_text: str = "",
    headline: str = "测试标题",
):
    from domains.meeting.agenda_engine import clear_agenda_engine_cache
    from domains.meeting.orchestrator import MeetingAgentSystem
    from domains.meeting.tasks.agenda_minutes.agenda_parser import (
        clear_agenda_parser_cache,
    )
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        clear_alignment_cache,
    )

    clear_agenda_parser_cache()
    clear_alignment_cache()
    clear_agenda_engine_cache()

    called: list[str] = []
    client = _make_minutes_mock_client(called, headline=headline)
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

def test_tasks_prepare_minutes_with_valid_agenda(tmp_path, monkeypatch):
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三\n2. 智能客服降本方案 汇报人：王五", encoding="utf-8")

    def mock_input_file(user_id, kind, name):
        return doc_path

    monkeypatch.setattr("app.tasks._input_file", mock_input_file)

    req = TaskRequest(
        texts={
            "transcript": (
                "张三 10:00\n"
                "自研芯片二期量产良率达到了91.5%，我们的二期流片测试很顺利。\n\n"
                "王五 10:30\n"
                "智能客服降本方案目前测试可以替代70%的常规咨询。\n"
            )
        },
        docs=["agenda.txt"],
    )
    prep = _prepare("meeting", "minutes", req, "u_test_agenda")
    # 验证有效议程提取到了 extra_line_inputs
    assert "agenda_text" in prep.extra_line_inputs
    assert "自研芯片二期量产" in prep.extra_line_inputs["agenda_text"]
    # 验证转写文件未被重复拼接 doc 内容
    assert prep.input_files is not None
    transcript_content = prep.input_files.read_text(encoding="utf-8")
    assert "文档：agenda.txt" not in transcript_content


def test_prepare_agenda_with_aux(tmp_path, monkeypatch):
    """议题 + 三字段：agenda_text 与 minutes_auxiliary 必须同时存在。"""
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text(
        "1. 自研芯片二期量产 汇报人：张三\n2. 智能客服降本方案 汇报人：王五",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.tasks._input_file", lambda user_id, kind, name: doc_path
    )

    req = TaskRequest(
        texts={
            "transcript": (
                "张三 10:00\n"
                "自研芯片二期量产良率达到了91.5%，我们的二期流片测试很顺利。\n\n"
                "王五 10:30\n"
                "智能客服降本方案目前测试可以替代70%的常规咨询。\n"
            ),
            "keypoints": "二期量产良率目标 92%",
            "notes": "良率达标 -> 需要复核测试口径",
            "vision_info": "流片测试报表：良率 91.5%，样本量 1200 片",
        },
        docs=["agenda.txt"],
    )
    prep = _prepare("meeting", "minutes", req, "u_test_agenda_aux")

    # 议程骨架
    assert "agenda_text" in prep.extra_line_inputs
    assert "自研芯片二期量产" in prep.extra_line_inputs["agenda_text"]

    # 三字段辅助材料
    aux = prep.extra_line_inputs.get("minutes_auxiliary", "")
    assert "【用户核心关键点】\n二期量产良率目标 92%" in aux
    assert "【用户划线原话与笔记】" in aux
    assert '原话："良率达标"' in aux
    assert "备注：需要复核测试口径" in aux
    assert "【视觉信息参考(OCR)】\n流片测试报表：良率 91.5%，样本量 1200 片" in aux


def test_prepare_minutes_passes_lang_to_agenda_vlm(tmp_path, monkeypatch):
    """minutes 的 docs 议程图片 VLM 调用必须透传 req.lang。"""
    img_path = tmp_path / "agenda.png"
    img_path.write_bytes(b"dummy")

    monkeypatch.setattr(
        "app.tasks._input_file", lambda user_id, kind, name: img_path
    )

    captured: dict = {}

    def fake_extract_agenda_from_image_docs(**kwargs):
        captured.update(kwargs)
        return None, "1. Topic A 汇报人：Alice"

    monkeypatch.setattr(
        "domains.meeting.agenda_vision.extract_agenda_from_image_docs",
        fake_extract_agenda_from_image_docs,
    )
    probe_captured: dict = {}

    def fake_probe_valid_agendas(transcript, agenda_text, *, lang="zh"):
        probe_captured["lang"] = lang
        return [object()]

    monkeypatch.setattr(
        "domains.meeting.agenda_engine.probe_valid_agendas",
        fake_probe_valid_agendas,
    )

    req = TaskRequest(
        lang="en",
        texts={"transcript": "Alice: We discussed Topic A."},
        docs=["agenda.png"],
    )
    prep = _prepare("meeting", "minutes", req, "u_test_vlm_lang")

    assert captured["lang"] == "en"
    assert probe_captured["lang"] == "en"
    assert "agenda_text" in prep.extra_line_inputs


def test_tasks_prepare_minutes_with_fallback_docs(tmp_path, monkeypatch):
    doc_path = tmp_path / "financial_report.txt"
    doc_path.write_text("Q3 净利润增加 1500 万元，现金流充足。", encoding="utf-8")

    def mock_input_file(user_id, kind, name):
        return doc_path

    monkeypatch.setattr("app.tasks._input_file", mock_input_file)

    req = TaskRequest(
        texts={"transcript": "张三 10:00: 今天讨论常规事项。"},
        docs=["financial_report.txt"],
    )
    prep = _prepare("meeting", "minutes", req, "u_test_agenda")
    # 验证非议程文档未被当作 agenda_text
    assert "agenda_text" not in prep.extra_line_inputs
    # 验证默认回退到 material_docs：文档内容作为资料被拼入了输入转写
    assert prep.input_files is not None
    transcript_content = prep.input_files.read_text(encoding="utf-8")
    assert "financial_report.txt" in transcript_content or "净利润" in transcript_content


def test_tasks_prepare_template_selection(tmp_path, monkeypatch):
    # 场景 A: minutes 任务且 docs 含有有效议题 -> 自动选用 agenda_templates 下的模板
    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三", encoding="utf-8")

    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)

    req_with_agenda = TaskRequest(
        texts={"transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%"},
        docs=["agenda.txt"],
    )
    prep_enhanced = _prepare("meeting", "minutes", req_with_agenda, "u_test_template_1")
    enhanced_template_text = prep_enhanced.templates["minutes"].read_text(encoding="utf-8")
    assert "以现场审定的有效议题清单为主线展开" in enhanced_template_text
    assert "每个议题以「### 一. 议题名称」顶格列出" in enhanced_template_text

    # 场景 B: minutes 任务无 docs -> 使用 legacy templates
    req_no_docs = TaskRequest(texts={"transcript": "张三 10:00: 讨论常规事项"})
    prep_legacy = _prepare("meeting", "minutes", req_no_docs, "u_test_template_2")
    legacy_template_text = prep_legacy.templates["minutes"].read_text(encoding="utf-8")
    assert "采用议题聚类" in legacy_template_text
    assert "以现场审定的有效议题清单为主线展开" not in legacy_template_text


def test_normal_minutes_with_non_agenda_docs_falls_back(tmp_path, monkeypatch):
    """英文非议程 docs 必须静默回退普通纪要资料流程。"""
    doc_path = tmp_path / "finance.txt"
    doc_path.write_text(
        "Q3 net profit increased by 15% and cash flow remains healthy.",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.tasks._input_file",
        lambda user_id, kind, name: doc_path,
    )

    req = TaskRequest(
        lang="en",
        texts={"transcript": "Alice Chen: We discussed the quarterly report."},
        docs=["finance.txt"],
    )
    prep = _prepare("meeting", "minutes", req, "u_test_en_non_agenda")

    assert "agenda_text" not in prep.extra_line_inputs
    assert prep.input_files is not None
    transcript_content = prep.input_files.read_text(encoding="utf-8")
    assert "finance.txt" in transcript_content or "net profit" in transcript_content
