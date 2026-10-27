from core.execution.hard_execution import is_agenda_enhanced_mode
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_RENDER_PROMPT,
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
        "tagged_transcript": "【现场审定的有效议题清单】：\n1. 议题：自研车载芯片二期量产（汇报人：张三）\n\n【议题 1：自研车载芯片二期量产】（汇报人：张三）\n张三 10:00: 芯片良率达标",
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
    assert "议题模式：agenda_enhanced" in context
    assert "本场会议已审定有效议题清单" in context
    assert is_agenda_enhanced_mode(context) is True
    assert "1. 议题：自研车载芯片二期量产（汇报人：张三）" in context
    assert "【议题 1：自研车载芯片二期量产】" in context


def test_shared_context_agenda_aux():
    """议题纪要上下文同时包含打标转写和三块辅助材料。"""
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
        "tagged_transcript": (
            "【现场审定的有效议题清单】：\n"
            "1. 议题：自研车载芯片二期量产（汇报人：张三）\n\n"
            "【议题 1：自研车载芯片二期量产】（汇报人：张三）\n"
            "张三 10:00: 芯片良率达标"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [valid_item],
        "meeting_understanding": {
            "meeting_brief": "测试简报",
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "line_extra": {
            "minutes_auxiliary": (
                "【用户核心关键点】\n良率 91.5%\n\n"
                "【用户划线原话与笔记】\n- 原话：\"良率达标\" | 备注：复核口径\n\n"
                "【视觉信息参考(OCR)】\n流片报表：样本量 1200 片"
            )
        },
    }
    context = nodes._line_shared_context(state_enhanced, "minutes")
    assert "议题模式：agenda_enhanced" in context
    assert "【议题 1：自研车载芯片二期量产】" in context
    assert "【用户核心关键点】\n良率 91.5%" in context
    assert "【用户划线原话与笔记】" in context
    assert "【视觉信息参考(OCR)】\n流片报表：样本量 1200 片" in context


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
    assert "议题模式" in render_ctx
    assert "现场审定的有效议题清单" in render_ctx
    assert "自研车载芯片二期量产" in render_ctx
    assert is_agenda_enhanced_mode(render_ctx) is True
    assert "【议题结构排版指引】" not in render_ctx
    assert "使用清单中的议题全称作为 ### 小节标题" not in render_ctx

    state_legacy = {
        "transcript": "张三: 芯片进展",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {},
        "lines": {"minutes": {"draft": {"executive_summary": ["概括"], "key_decisions": []}}},
    }
    render_ctx_legacy = nodes._render_context(state_legacy, "minutes")
    assert "现场审定的有效议题清单" not in render_ctx_legacy
    assert is_agenda_enhanced_mode(render_ctx_legacy) is False


def test_orchestrator_supervisor_context():
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
        "meeting_understanding": {"meeting_brief": "测试", "decisions": [], "risks": [], "open_questions": []},
        "lines": {"minutes": {"draft": {"executive_summary": ["概括"], "key_decisions": []}, "revision_count": 0}},
    }
    sup_ctx = nodes._supervisor_context(state_enhanced, "minutes")
    assert "议题模式：agenda_enhanced" in sup_ctx
    assert is_agenda_enhanced_mode(sup_ctx) is True

    state_legacy = {
        "transcript": "张三: 芯片进展",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {"meeting_brief": "测试", "decisions": [], "risks": [], "open_questions": []},
        "lines": {"minutes": {"draft": {"executive_summary": ["概括"], "key_decisions": []}, "revision_count": 0}},
    }
    sup_ctx_legacy = nodes._supervisor_context(state_legacy, "minutes")
    assert "议题模式：agenda_enhanced" not in sup_ctx_legacy
    assert is_agenda_enhanced_mode(sup_ctx_legacy) is False


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

def test_agenda_template_resolution():
    from app.config import resolve_template_format, resolve_agenda_template_format

    # 1. 议题模式下加载通用纪要：命中 resources/agenda_templates/zh/general_minutes.md
    agenda_fmt = resolve_agenda_template_format("general_minutes")
    from core.templates.router._gate import scan_fixed_bracket_literals
    assert scan_fixed_bracket_literals(agenda_fmt) == [], "agenda template must not have unparsed fixed bracket literals"
    assert "以现场审定的有效议题清单为主线展开" in agenda_fmt
    assert "每个议题以「### 一. 议题名称」顶格列出" in agenda_fmt
    assert "**业务子主题**" in agenda_fmt
    assert "#### 1. 子主题名称" not in agenda_fmt
    assert "采用议题聚类" not in agenda_fmt

    # 2. 常规模式下加载通用纪要：原模板 resources/templates/general_minutes.md 保持不变
    legacy_fmt = resolve_template_format("general_minutes")
    assert "采用议题聚类" in legacy_fmt
    assert "以现场审定的有效议题清单为主线展开" not in legacy_fmt

    # 3. 议题模式下加载已定制的 project_progress：命中 resources/agenda_templates/zh/project_progress.md
    agenda_proj_fmt = resolve_agenda_template_format("project_progress")
    assert "以现场审定的有效议题清单为主线展开，每个议题下独立设立一张明细表格" in agenda_proj_fmt

    # 4. 议题模式下加载已定制的 decision_review：命中 resources/agenda_templates/zh/decision_review.md
    agenda_dec_fmt = resolve_agenda_template_format("decision_review")
    assert "以现场审定的有效评审议题为主线展开，每个议题下独立设立一张论证明细表格" in agenda_dec_fmt

    # 5. 议题模式下加载已定制的 workshop_session：命中 resources/agenda_templates/zh/workshop_session.md
    agenda_ws_fmt = resolve_agenda_template_format("workshop_session")
    assert "以现场审定的有效议题清单为主线展开" in agenda_ws_fmt
    assert "多方向探讨或观点交锋以独立加粗行「**业务子主题/探讨方向**」划分段落" in agenda_ws_fmt

    # 6. 议题模式下加载已定制的 retrospective_session：命中 resources/agenda_templates/zh/retrospective_session.md
    agenda_retro_fmt = resolve_agenda_template_format("retrospective_session")
    assert scan_fixed_bracket_literals(agenda_retro_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_retro_fmt
    assert "每条以反映具体交付物或量化指标的实质业务短语起笔" in agenda_retro_fmt

    # 7. 议题模式下加载已定制的 exchange_forum：命中 resources/agenda_templates/zh/exchange_forum.md
    agenda_ef_fmt = resolve_agenda_template_format("exchange_forum")
    assert scan_fixed_bracket_literals(agenda_ef_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ef_fmt
    assert "正文统一以反映具体业务实体或事实要点的实质业务短语起笔" in agenda_ef_fmt

    # 8. 议题模式下加载已定制的 class_transcript：命中 resources/agenda_templates/zh/class_transcript.md
    agenda_ct_fmt = resolve_agenda_template_format("class_transcript")
    assert scan_fixed_bracket_literals(agenda_ct_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ct_fmt
    assert "正文统一以反映具体概念、定理或推演主题的实质业务短语起笔" in agenda_ct_fmt

    # 9. 议题模式下加载已定制的 special_lecture：命中 resources/agenda_templates/zh/special_lecture.md
    agenda_sl_fmt = resolve_agenda_template_format("special_lecture")
    assert scan_fixed_bracket_literals(agenda_sl_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_sl_fmt
    assert "正文统一以反映核心观点或论证要素的实质业务短语起笔" in agenda_sl_fmt

    # 10. 议题模式下加载已定制的 group_seminar：命中 resources/agenda_templates/zh/group_seminar.md
    agenda_gs_fmt = resolve_agenda_template_format("group_seminar")
    assert scan_fixed_bracket_literals(agenda_gs_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_gs_fmt
    assert "正文统一以反映发言人或核心论述的实质业务短语起笔" in agenda_gs_fmt

    # 11. 议题模式下加载已定制的 research_dialogue：命中 resources/agenda_templates/zh/research_dialogue.md
    agenda_rd_fmt = resolve_agenda_template_format("research_dialogue")
    assert scan_fixed_bracket_literals(agenda_rd_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_rd_fmt
    assert "正文统一以反映具体业务模块或痛点诉求的实质短语起笔" in agenda_rd_fmt

    # 12. 议题模式下加载已定制的 interview_transcript：命中 resources/agenda_templates/zh/interview_transcript.md
    agenda_it_fmt = resolve_agenda_template_format("interview_transcript")
    assert scan_fixed_bracket_literals(agenda_it_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_it_fmt
    assert "正文统一以反映具体事件、心路历程或核心观点的实质短语起笔" in agenda_it_fmt

    # 13. 议题模式下加载已定制的 knowledge_memo：命中 resources/agenda_templates/zh/knowledge_memo.md
    agenda_km_fmt = resolve_agenda_template_format("knowledge_memo")
    assert scan_fixed_bracket_literals(agenda_km_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_km_fmt
    assert "正文统一以反映具体概念、理论要素或知识分项的实质短语起笔" in agenda_km_fmt

    # 14. 议题模式下加载已定制的 legal_advisory：命中 resources/agenda_templates/zh/legal_advisory.md
    agenda_la_fmt = resolve_agenda_template_format("legal_advisory")
    assert scan_fixed_bracket_literals(agenda_la_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_la_fmt
    assert "每项统一以反映关键节点、涉案主体或争议行为的实质短语起笔" in agenda_la_fmt
    assert "每项统一以「**分析维度**：法规依据与定调结论」起笔" in agenda_la_fmt
    assert "以列表符「- 」直接列出具体行动事项" in agenda_la_fmt

    # 15. 议题模式下加载已定制的 media_briefing：命中 resources/agenda_templates/zh/media_briefing.md
    agenda_mb_fmt = resolve_agenda_template_format("media_briefing")
    assert scan_fixed_bracket_literals(agenda_mb_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_mb_fmt
    assert "正文统一以反映具体业务动作或成果的实质短语起笔" in agenda_mb_fmt
    assert "具体问答交互下沉至「Q&A环节」" in agenda_mb_fmt
    assert "(现场有互动问答才呈现，若全场无互动问答则本栏整体自适应隐去)" in agenda_mb_fmt

    # 16. 议题模式下加载已定制的 government_bulletin：命中 resources/agenda_templates/zh/government_bulletin.md
    agenda_gb_fmt = resolve_agenda_template_format("government_bulletin")
    assert scan_fixed_bracket_literals(agenda_gb_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_gb_fmt
    assert "正文统一以反映具体政策或规划的实质短语起笔" in agenda_gb_fmt
    assert "重要政策法规与核心量化数据自然加粗" in agenda_gb_fmt

    # 17. 议题模式下加载已定制的 media_qa_session：命中 resources/agenda_templates/zh/media_qa_session.md
    agenda_mq_fmt = resolve_agenda_template_format("media_qa_session")
    assert scan_fixed_bracket_literals(agenda_mq_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_mq_fmt
    assert "提问行「**提问方**：提问核心焦点」紧随回答行「**答复方**：明确结论与政策事实依据」成对展开" in agenda_mq_fmt
    assert "## [信息澄清与表态]" in agenda_mq_fmt

    # 18. 议题模式下加载已定制的 conversation_transcript：命中 resources/agenda_templates/zh/conversation_transcript.md
    agenda_ct_fmt = resolve_agenda_template_format("conversation_transcript")
    assert scan_fixed_bracket_literals(agenda_ct_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_ct_fmt
    assert "正文统一以反映发言人或核心观点的实质短语起笔" in agenda_ct_fmt
    assert "①「### 达成共识」" in agenda_ct_fmt
    assert "②「### 存有分歧」" in agenda_ct_fmt

    # 19. 议题模式下加载已定制的 site_visit_tour：命中 resources/agenda_templates/zh/site_visit_tour.md
    agenda_sv_fmt = resolve_agenda_template_format("site_visit_tour")
    assert scan_fixed_bracket_literals(agenda_sv_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_sv_fmt
    assert "按「- **看点名称**：具体解说要点与专业数据」逐条展开" in agenda_sv_fmt
    assert "清单化提炼参访所获认知增量、实践启示与转化建议" in agenda_sv_fmt

    # 20. 议题模式下加载已定制的 home_school_liaison：命中 resources/agenda_templates/zh/home_school_liaison.md
    agenda_hsl_fmt = resolve_agenda_template_format("home_school_liaison")
    assert scan_fixed_bracket_literals(agenda_hsl_fmt) == []
    assert "以现场审定的有效议题清单为主线展开，每个议题顶格以「### 一. 议题名称」列出" in agenda_hsl_fmt
    assert "每项以「- **观察维度/表现领域**」独立成行起笔" in agenda_hsl_fmt
    assert "每项以「- **探讨主题/关注焦点**」独立成行起笔" in agenda_hsl_fmt

    # 21. 议题模式下加载未设议题驱动的模板（如 contract_vetting）：平滑回退普通模板
    fallback_fmt = resolve_agenda_template_format("contract_vetting")
    orig_fmt = resolve_template_format("contract_vetting")
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
    assert "以现场审定的有效议题清单为主线展开" in enhanced_template_text
    assert "每个议题以「### 一. 议题名称」顶格列出" in enhanced_template_text

    # 场景 B: minutes 任务无 docs -> 使用 legacy templates
    req_no_docs = TaskRequest(texts={"transcript": "张三 10:00: 讨论常规事项"})
    prep_legacy = _prepare("meeting", "minutes", req_no_docs, "u_test_template_2")
    legacy_template_text = prep_legacy.templates["minutes"].read_text(encoding="utf-8")
    assert "采用议题聚类" in legacy_template_text
    assert "以现场审定的有效议题清单为主线展开" not in legacy_template_text

def test_meeting_understanding_node_agenda_guidance():
    import asyncio
    nodes = _Nodes()
    captured_kwargs = {}

    class MockUnderstandingAgent:
        async def run(self, transcript, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            from domains.meeting.models_generated import MeetingUnderstanding
            return MeetingUnderstanding(
                meeting_brief="测试",
                meeting_purpose="目的",
                scene="通用",
            )

    nodes.meeting_understanding_agent = MockUnderstandingAgent()

    valid_item = ValidAgendaItem(
        seq="1",
        title="自研车载芯片二期量产",
        presenters=["张三"],
    )

    state = {
        "transcript": "张三 10:00: 进展汇报自研芯片",
        "has_valid_agenda": True,
        "valid_agendas": [valid_item],
        "line_extra": {"agenda_text": "1. 自研车载芯片二期量产 汇报人：张三"},
    }

    # 1. 单任务 minutes 且有效议程：直接短路跳过理解层（方案 A 提速）
    from domains.meeting.orchestrator import _EMPTY_MEETING_UNDERSTANDING
    node_func_single = nodes._make_meeting_understanding_node(["minutes"])
    res_single = asyncio.run(node_func_single(state))
    assert res_single["meeting_understanding"] == _EMPTY_MEETING_UNDERSTANDING
    assert captured_kwargs == {}, "单任务 minutes 议题增强必须短路跳过 meeting_understanding 节点"

    # 2. 多任务并行（如 minutes + actions）：不短路，正常调用理解层并传递 is_agenda_enhanced
    node_func_multi = nodes._make_meeting_understanding_node(["minutes", "actions"])
    asyncio.run(node_func_multi(state))
    assert captured_kwargs.get("is_agenda_enhanced") is True
    channel = captured_kwargs.get("user_channel", "")
    assert "【审定议题阶段归集指引】" not in channel


@pytest.mark.anyio
async def test_agenda_track_b_prompt_routing():
    # 1. 理解层 Agent 系统提示词路由
    from domains.meeting.meeting_core.meeting_understanding_agent import MeetingUnderstandingAgent
    mock_client = MagicMock()

    async def mock_structured(prompt, *args, **kwargs):
        from domains.meeting.models_generated import MeetingUnderstanding
        return MeetingUnderstanding(meeting_brief="b", meeting_purpose="p", scene="s")
    mock_client.structured.side_effect = mock_structured

    mu_agent = MeetingUnderstandingAgent(mock_client)
    await mu_agent.run("测试原文", is_agenda_enhanced=True)
    called_prompt = mock_client.structured.call_args[0][0]
    assert called_prompt == MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT

    # 2. 纪要草稿 Agent 提示词路由
    from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
    agent = MinutesGenerationAgent(mock_client)
    mock_client.structured.reset_mock()
    async def mock_structured_draft(prompt, *args, **kwargs):
        from domains.meeting.models_generated import Minutes
        return Minutes(headline="测试标题", executive_summary=["段落1"])
    mock_client.structured.side_effect = mock_structured_draft

    await agent.run("议题模式：agenda_enhanced\n视角模式：objective\n\n会议理解：{}")
    called_prompt = mock_client.structured.call_args[0][0]
    assert called_prompt == MINUTES_AGENDA_GENERATION_PROMPT

    # 3. 纪要审核 Supervisor 提示词路由
    from domains.meeting.tasks.minutes.steps.minutes_supervisor import MinutesGenerationSupervisor
    from domains.shared.supervisor import GlobalSupervisor
    supervisor = MinutesGenerationSupervisor(mock_client)
    mock_client.structured.reset_mock()
    async def mock_structured_review(prompt, *args, **kwargs):
        from domains.meeting.models_generated import MinutesSupervisorReview
        return MinutesSupervisorReview(
            decision="approve",
            facts_check={"passed": True, "issues": []},
            perspective_check={"passed": True, "issues": []},
            consistency_check={"passed": True, "issues": []},
            feedback=[],
        )
    mock_client.structured.side_effect = mock_structured_review

    await supervisor.review("视角模式：objective\n纪要返工次数：0/2\n\n议题模式：agenda_enhanced\n草稿：{}")
    called_prompt = mock_client.structured.call_args[0][0]
    expected_prompt = GlobalSupervisor.build_prompt(MINUTES_AGENDA_SUPERVISOR_PROMPT)
    assert called_prompt == expected_prompt

    # 4. 纪要渲染 Render 提示词路由
    from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
    renderer = MinutesGenerationRender(mock_client)
    # 4a. 无模板模式
    rendered_prompt, _ = renderer._prompt_and_user("议题模式：agenda_enhanced\n视角模式：objective", "")
    assert "（审定议题专有模式）" in rendered_prompt
    assert "### 一. [审定议题一全称]" in rendered_prompt
    # 4b. 模板模式
    rendered_prompt_tpl, _ = renderer._prompt_and_user("议题模式：agenda_enhanced\n视角模式：objective", "# 通用纪要模板\n{{scalar:要点梳理}}")
    assert "严格遵循模板栏目规约与公文层级标准完成排版" in rendered_prompt_tpl
    assert "大项标题（### 一. 议题名称）" in rendered_prompt_tpl

def test_meeting_state_declares_agenda_fields():
    from domains.meeting.models import MeetingState
    annotations = MeetingState.__annotations__
    assert "has_valid_agenda" in annotations
    assert "valid_agendas" in annotations
    assert "tagged_transcript" in annotations


@pytest.mark.anyio
async def test_langgraph_agenda_state_propagation():
    from domains.meeting.orchestrator import MeetingAgentSystem
    from unittest.mock import MagicMock
    from domains.meeting.models_generated import MeetingUnderstanding, Minutes, MinutesSupervisorReview

    mock_client = MagicMock()
    called_labels = []

    async def mock_structured(prompt, *args, **kwargs):
        label = kwargs.get("label", "")
        called_labels.append(label)
        if "meeting_understanding" in label:
            return MeetingUnderstanding(meeting_brief="测试", meeting_purpose="目的", scene="通用")
        elif "minutes/agent" in label:
            return Minutes(headline="测试标题", executive_summary=["段落1"])
        elif "minutes/supervisor" in label:
            return MinutesSupervisorReview(
                decision="approve",
                facts_check={"passed": True, "issues": []},
                perspective_check={"passed": True, "issues": []},
                consistency_check={"passed": True, "issues": []},
                feedback=[],
            )
        raise ValueError(f"Unexpected label {label}")

    mock_client.structured.side_effect = mock_structured

    system = MeetingAgentSystem(mock_client)
    compiled_graph = system._build_graph(["minutes"])

    init_state = {
        "transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%",
        "user": {},
        "line_extra": {"agenda_text": "1. 自研芯片二期量产 汇报人：张三"},
        "lines": {"minutes": {"revision_count": 0}},
    }
    final_state = await compiled_graph.ainvoke(init_state)

    # 1. 验证 LangGraph 完整传递了审定议题状态通道
    assert final_state.get("has_valid_agenda") is True
    assert final_state.get("valid_agendas") is not None
    assert len(final_state.get("valid_agendas")) == 1
    assert "【现场审定的有效议题清单】" in final_state.get("tagged_transcript", "")

    # 2. 验证 minutes_agent 真正命中了 agenda 模式，而非 objective 兜底
    assert "minutes/agent/agenda" in called_labels

    # 3. 验证 supervisor 上下文中具备议题模式
    sup_ctx = system._supervisor_context(final_state, "minutes")
    assert is_agenda_enhanced_mode(sup_ctx) is True

    # 4. 验证 render 上下文中具备议题模式与有效议题清单数据块
    render_ctx = system._render_context(final_state, "minutes")
    assert is_agenda_enhanced_mode(render_ctx) is True
    assert "现场审定的有效议题清单" in render_ctx

@pytest.mark.anyio
async def test_prepare_run_preserves_agenda_text_in_line_extra(tmp_path, monkeypatch):
    from app.tasks import _prepare, _runner_args
    from core.runner.runner import prepare_run
    from app.schemas import TaskRequest

    doc_path = tmp_path / "agenda.txt"
    doc_path.write_text("1. 自研芯片二期量产 汇报人：张三", encoding="utf-8")
    monkeypatch.setattr("app.tasks._input_file", lambda uid, kind, name: doc_path)

    req = TaskRequest(
        texts={"transcript": "张三 10:00: 自研芯片二期量产良率达到了91.5%"},
        docs=["agenda.txt"],
    )
    p = _prepare("meeting", "minutes", req, "u_test_runner")
    assert "agenda_text" in p.extra_line_inputs

    args = _runner_args(p)
    prep = await prepare_run(p.ctx, **args)
    # 核心守卫：runner.py 绝不可在 prepare_run 中丢弃 agenda_text
    assert "agenda_text" in prep.line_extra
    assert "自研芯片二期量产" in prep.line_extra["agenda_text"]


def test_minutes_prompt_matter_oriented_governance():
    """验证新老逻辑 Prompt 彻底去机械流水账对白，确立就事论事与正向引导准则。"""
    from domains.meeting.tasks.minutes.prompts import (
        _MINUTES_COMMON_BASE,
        MINUTES_OBJECTIVE_GENERATION_PROMPT,
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
        MINUTES_AGENDA_SUPERVISOR_PROMPT,
    )
    from domains.meeting.meeting_core.prompts import (
        MEETING_UNDERSTANDING_SYSTEM_PROMPT,
        MEETING_UNDERSTANDING_LIGHTWEIGHT_SYSTEM_PROMPT,
        MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
    )

    # 1. 核心诱因根治：验证公共基底彻底废除“主体+动作”句式公式，引入三层主体与就事论事
    assert "主体 + 核心动作/主张 + 量化指标/定调依据 + 最终结论/后续安排" not in _MINUTES_COMMON_BASE
    assert "分章节主体表达规范（就事论事原则）" in _MINUTES_COMMON_BASE
    assert "避免机械堆砌发言动词" in _MINUTES_COMMON_BASE

    # 2. 负向对抗字眼治理：验证核心生成 Prompt 不包含杜绝/拒绝等对抗句式
    for p in [MINUTES_OBJECTIVE_GENERATION_PROMPT, MINUTES_AGENDA_GENERATION_PROMPT]:
        assert "杜绝凭空编造" not in p
        assert "拒绝多从句生硬拼接的长难句" not in p
        assert "剔除铺垫修辞" not in p

    # 3. 理解层决议格式治理：验证老逻辑与新逻辑均要求 decisions 以事项为主干
    assert "条目以被决定的业务事项为主干" in MEETING_UNDERSTANDING_SYSTEM_PROMPT
    assert "以被决定的业务事项为主干" in MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT
    assert "严禁输出长篇背景叙事" not in MEETING_UNDERSTANDING_LIGHTWEIGHT_SYSTEM_PROMPT
    assert "严禁主观脑补" not in MEETING_UNDERSTANDING_LIGHTWEIGHT_SYSTEM_PROMPT

    # 4. 审核放行规则验证：确保 Supervisor 显式放行公文决议体与脱水表述
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in MINUTES_AGENDA_SUPERVISOR_PROMPT


def test_agenda_minutes_quality_and_stability_prompts():
    """验证议题纪要草稿与渲染提示词中：扁平子主题、列表项就事论事、解除字数枷锁、去转述动词。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
        MINUTES_AGENDA_RENDER_PROMPT,
    )

    # 1. 验证生成提示词彻底移除字数枷锁（不再限制 40-60 字及 2-5 条）
    assert "单条约 40–60 字" not in MINUTES_AGENDA_GENERATION_PROMPT
    assert "提炼 2–5 条核心事实" not in MINUTES_AGENDA_GENERATION_PROMPT

    # 2. 验证生成提示词包含扁平子主题与纯净列表项规约
    assert "- [要点名称]: [具体事实陈述]" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "**[业务子主题名称]**" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "不使用四级标题或数字编号" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "以业务方案、技术机理与推进结果为主干直接陈述" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "正文只记录事项本身" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "参数指标、对比基线、排期节点 100% 完整保留" in MINUTES_AGENDA_GENERATION_PROMPT

    # 3. 验证渲染提示词对齐扁平子主题与纯净列表项
    assert "大项标题（### 一. 议题名称）" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "加粗子主题（**业务子主题**）" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "列表项（- 要点名称: 具体陈述）" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "不添加任何前言导语" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT

    # 4. 验证非模板渲染也同步对齐扁平子主题与纯净列表项
    assert "**业务子主题**" in MINUTES_AGENDA_RENDER_PROMPT
    assert "- 要点名称: 具体陈述" in MINUTES_AGENDA_RENDER_PROMPT
    assert "**[业务子主题名称]**" in MINUTES_AGENDA_RENDER_PROMPT
    assert "[要点名称]: [具体事实陈述]" in MINUTES_AGENDA_RENDER_PROMPT
    # 示例骨架不得再出现四级标题，避免与「不使用四级标题与数字编号」规则冲突
    assert "####" not in MINUTES_AGENDA_RENDER_PROMPT


def test_orchestrator_line_shared_context_recency_injection():
    """验证议题模式下长上下文最底端注入最高优先级执行准绳（近因效应）。"""
    nodes = _Nodes()
    state_enhanced = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": True,
        "templates": {"minutes": "# 通用模板\n{{scalar:要点梳理}}"},
    }
    ctx = nodes._line_shared_context(state_enhanced, "minutes")
    assert "【审定议题草稿生成执行准绳】" in ctx
    assert "1. 标题直出" in ctx
    assert "2. 扁平子主题" in ctx
    assert "3. 纯净列表" in ctx
    assert "4. 就事论事" in ctx
    assert "5. 细节充分" in ctx

    # 验证非议题模式下不注入该准绳
    state_legacy = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": False,
        "templates": {"minutes": "# 通用模板\n{{scalar:要点梳理}}"},
    }
    ctx_legacy = nodes._line_shared_context(state_legacy, "minutes")
    assert "【审定议题草稿生成执行准绳】" not in ctx_legacy

    # 验证非 minutes 任务线不注入该准绳
    state_actions = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": True,
    }
    ctx_actions = nodes._line_shared_context(state_actions, "actions")
    assert "【审定议题草稿生成执行准绳】" not in ctx_actions


@pytest.mark.anyio
async def test_orchestrator_process_agenda_passes_lang(monkeypatch):
    """orchestrator 二次处理必须把 state.lang 传给 process_agenda_for_minutes。"""
    from domains.meeting import agenda_engine
    from domains.meeting.orchestrator import MeetingAgentSystem

    captured: dict[str, str] = {}
    item = ValidAgendaItem(
        seq="01",
        title="Architecture Review",
        presenters=["Alice Chen"],
    )

    def fake_process(transcript, agenda_text, *, lang="zh"):
        captured["lang"] = lang
        return AgendaProcessResult(
            has_valid_agenda=True,
            valid_agendas=[item],
            tagged_transcript=(
                "【现场审定的有效议题清单】：\n"
                "1. 议题：Architecture Review"
            ),
        )

    monkeypatch.setattr(agenda_engine, "process_agenda_for_minutes", fake_process)
    system = MeetingAgentSystem(MagicMock())
    node = system._make_meeting_understanding_node(["minutes"])
    state = {
        "transcript": "Alice Chen 00:01\nArchitecture review details",
        "line_extra": {"agenda_text": "1. Architecture Review"},
        "lang": "en",
        "user": {},
    }

    result = await node(state)
    assert captured["lang"] == "en"
    assert result["has_valid_agenda"] is True


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
                scene="通用",
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


@pytest.mark.anyio
async def test_minutes_agenda_en_pipeline():
    """英文议题增强 minutes 线：有效议题、打标转写、agenda prompt 全部就绪。"""
    _, final, called = await _run_minutes_graph(
        transcript=_EN_TRANSCRIPT,
        lang="en",
        agenda_text=_EN_AGENDA,
    )
    assert final.get("has_valid_agenda") is True
    assert [item.title for item in final.get("valid_agendas") or []] == [
        "Architecture Review",
        "Release Plan",
    ]
    assert "Architecture Review" in final.get("tagged_transcript", "")
    assert "minutes/agent/agenda" in called


@pytest.mark.anyio
async def test_minutes_agenda_zh_unchanged():
    """中文议题增强 minutes 线：行为保持原有议题归属。"""
    _, final, called = await _run_minutes_graph(
        transcript=_ZH_TRANSCRIPT,
        lang="zh",
        agenda_text=_ZH_AGENDA,
    )
    assert final.get("has_valid_agenda") is True
    assert [item.title for item in final.get("valid_agendas") or []] == [
        "架构评审",
        "发布计划",
    ]
    assert "架构评审" in final.get("tagged_transcript", "")
    assert "minutes/agent/agenda" in called


@pytest.mark.anyio
async def test_minutes_normal_en_does_not_enter_agenda_mode():
    """英文普通纪要无议程 docs：不得误入议程模式。"""
    _, final, called = await _run_minutes_graph(
        transcript="Alice Chen 00:01\nThe architecture review covers the gateway redesign.",
        lang="en",
    )
    assert not final.get("has_valid_agenda")
    assert not any("minutes/agent/agenda" in label for label in called)
    assert any("minutes/agent/objective" in label for label in called)
    assert any("meeting_understanding" in label for label in called)


@pytest.mark.anyio
async def test_minutes_normal_zh_unchanged():
    """中文普通纪要无议程 docs：保持普通纪要路径。"""
    _, final, called = await _run_minutes_graph(
        transcript="张三 10:00: 今天讨论常规事项。",
        lang="zh",
    )
    assert not final.get("has_valid_agenda")
    assert not any("minutes/agent/agenda" in label for label in called)
    assert any("minutes/agent/objective" in label for label in called)


@pytest.mark.anyio
async def test_normal_minutes_english_unchanged():
    """英文普通纪要草稿/渲染字段不被议程逻辑改写。"""
    _, final, called = await _run_minutes_graph(
        transcript="Alice Chen 00:01\nThe architecture review covers the gateway redesign.",
        lang="en",
        headline="English Minutes Headline",
    )
    assert not final.get("has_valid_agenda")
    minutes_state = ((final.get("lines") or {}).get("minutes") or {})
    draft = minutes_state.get("draft") or {}
    assert draft.get("headline") == "English Minutes Headline"
    assert draft.get("executive_summary") == ["段落1"]
    assert any("minutes/agent/objective" in label for label in called)


@pytest.mark.anyio
async def test_normal_minutes_zh_unchanged():
    """中文普通纪要草稿/渲染字段不被议程逻辑改写。"""
    _, final, called = await _run_minutes_graph(
        transcript="张三 10:00: 今天讨论常规事项。",
        lang="zh",
        headline="中文普通纪要标题",
    )
    assert not final.get("has_valid_agenda")
    minutes_state = ((final.get("lines") or {}).get("minutes") or {})
    draft = minutes_state.get("draft") or {}
    assert draft.get("headline") == "中文普通纪要标题"
    assert draft.get("executive_summary") == ["段落1"]
    assert any("minutes/agent/objective" in label for label in called)


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
