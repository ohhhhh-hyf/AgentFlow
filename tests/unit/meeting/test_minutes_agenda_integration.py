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
    from core.templates.router._gate import scan_fixed_bracket_literals
    assert scan_fixed_bracket_literals(agenda_fmt) == [], "agenda template must not have unparsed fixed bracket literals"
    assert "以现场审定的有效议题清单为主线展开呈现" in agenda_fmt
    assert "每个审定议题设立三级小节标题" in agenda_fmt
    assert "#### 1. 子主题名称" in agenda_fmt
    assert "采用议题聚类" not in agenda_fmt

    # 2. 常规模式下加载通用纪要：原模板 resources/templates/general_minutes.md 保持不变
    legacy_fmt = resolve_template_format("general_minutes")
    assert "采用议题聚类" in legacy_fmt
    assert "以现场审定的有效议题清单为主线展开呈现" not in legacy_fmt

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
    assert "以现场审定的有效议题清单为主线展开呈现" in enhanced_template_text
    assert "每个审定议题设立三级小节标题" in enhanced_template_text

    # 场景 B: minutes 任务无 docs -> 使用 legacy templates
    req_no_docs = TaskRequest(texts={"transcript": "张三 10:00: 讨论常规事项"})
    prep_legacy = _prepare("meeting", "minutes", req_no_docs, "u_test_template_2")
    legacy_template_text = prep_legacy.templates["minutes"].read_text(encoding="utf-8")
    assert "采用议题聚类" in legacy_template_text
    assert "以现场审定的有效议题清单为主线展开呈现" not in legacy_template_text

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

    node_func = nodes._make_meeting_understanding_node(["minutes"])

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

    asyncio.run(node_func(state))

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
    assert "### [审定议题一全称]" in rendered_prompt
    # 4b. 模板模式
    rendered_prompt_tpl, _ = renderer._prompt_and_user("议题模式：agenda_enhanced\n视角模式：objective", "# 通用纪要模板\n{{scalar:要点梳理}}")
    assert "以审定议题为主线结构规范" in rendered_prompt_tpl
    assert "一级小节标题（### 议题名称）" in rendered_prompt_tpl

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
