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


def test_orchestrator_line_shared_context_enhanced():
    nodes = _Nodes()
    valid_item = ValidAgendaItem(
        seq="1",
        title="自研车载芯片二期量产",
        presenters=["张三"],
        start_index=0,
        end_index=1,
        matched_blocks=[DiscussionBlock(speaker="张三", timestamp="10:00", content="芯片良率达标", index=0)],
    )
    state_enhanced = {
        "transcript": "张三 10:00: 芯片良率达标",
        "tagged_transcript": "【议题 1：自研车载芯片二期量产】（汇报人：张三）\n张三 10:00: 芯片良率达标",
        "has_valid_agenda": True,
        "valid_agendas": [valid_item],
        "meeting_understanding": {
            "meeting_brief": "测试简报",
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
    }
    context = nodes._line_shared_context(state_enhanced, "minutes")
    assert "【现场审定的有效议题清单（正文必须按此议题结构与顺序展开）】" in context
    assert "1. 议题：自研车载芯片二期量产（汇报人：张三）" in context
    assert "【会议原文】" in context
    assert "【议题 1：自研车载芯片二期量产】" in context


def test_orchestrator_line_shared_context_fallback():
    nodes = _Nodes()
    state_legacy = {
        "transcript": "李四 10:00: 讨论一般事务",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {
            "meeting_brief": "常规简报",
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
    }
    context = nodes._line_shared_context(state_legacy, "minutes")
    assert "【现场审定的有效议题清单" not in context
    assert "会议原文：\n李四 10:00: 讨论一般事务" in context


def test_orchestrator_render_context():
    nodes = _Nodes()
    valid_item = ValidAgendaItem(
        seq="1",
        title="自研车载芯片二期量产",
        presenters=["张三"],
    )
    state_enhanced = {
        "transcript": "张三: 芯片进展",
        "has_valid_agenda": True,
        "valid_agendas": [valid_item],
        "meeting_understanding": {},
        "lines": {"minutes": {"draft": {"executive_summary": ["概括"], "key_decisions": []}}},
    }
    render_ctx = nodes._render_context(state_enhanced, "minutes")
    assert "【现场审定的有效议题清单（正文必须按此议题结构与顺序展开）】" in render_ctx
    assert "自研车载芯片二期量产" in render_ctx
    assert "【排版与小节命名纪律】" in render_ctx
    assert "正文 [要点梳理] 栏目必须严格以且仅以本清单中的议题全称作为 ### 小节标题" in render_ctx

    state_legacy = {
        "transcript": "张三: 芯片进展",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {},
        "lines": {"minutes": {"draft": {"executive_summary": ["概括"], "key_decisions": []}}},
    }
    render_ctx_legacy = nodes._render_context(state_legacy, "minutes")
    assert "【现场审定的有效议题清单" not in render_ctx_legacy


def test_orchestrator_non_minutes_task_unaffected():
    nodes = _Nodes()
    state = {
        "transcript": "张三: 行动项与风险",
        "has_valid_agenda": True,
        "valid_agendas": [ValidAgendaItem(seq="1", title="某议题")],
        "meeting_understanding": {
            "meeting_brief": "简报",
            "action_hints": [],
            "dependencies": [],
            "decisions": [],
            "session_segments": [],
        },
    }
    # actions 任务应完全不受 minutes 议程注入影响
    actions_ctx = nodes._line_shared_context(state, "actions")
    assert "【现场审定的有效议题清单" not in actions_ctx
    assert "会议原文：\n张三: 行动项与风险" in actions_ctx


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

def test_agenda_template_resolution():
    from app.config import resolve_template_format, resolve_agenda_template_format

    # 1. 议题模式下加载通用纪要：命中 resources/agenda_templates/general_minutes.md
    agenda_fmt = resolve_agenda_template_format("general_minutes")
    assert "小节标题必须与清单中的议题全称一字不差对齐" in agenda_fmt
    assert "采用议题聚类" not in agenda_fmt

    # 2. 常规模式下加载通用纪要：原模板 resources/templates/general_minutes.md 保持不变
    legacy_fmt = resolve_template_format("general_minutes")
    assert "采用议题聚类" in legacy_fmt
    assert "小节标题必须与清单中的议题全称一字不差对齐" not in legacy_fmt

    # 3. 议题模式下加载未单独定制的模板（如 project_progress）：平滑回退普通模板
    fallback_fmt = resolve_agenda_template_format("project_progress")
    orig_fmt = resolve_template_format("project_progress")
    assert fallback_fmt == orig_fmt


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
    assert "小节标题必须与清单中的议题全称一字不差对齐" in enhanced_template_text

    # 场景 B: minutes 任务无 docs -> 使用 legacy templates
    req_no_docs = TaskRequest(texts={"transcript": "张三 10:00: 讨论常规事项"})
    prep_legacy = _prepare("meeting", "minutes", req_no_docs, "u_test_template_2")
    legacy_template_text = prep_legacy.templates["minutes"].read_text(encoding="utf-8")
    assert "采用议题聚类" in legacy_template_text
    assert "小节标题必须与清单中的议题全称一字不差对齐" not in legacy_template_text

