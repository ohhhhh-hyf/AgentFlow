# 拆分自 test_agenda.py，覆盖：test_agenda_track_b_prompt_routing, test_langgraph_agenda_state_propagation, test_prepare_run_preserves_agenda_text_in_line_extra…

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
from tests.support.fakes import make_minutes_mock_client as _make_minutes_mock_client, run_minutes_graph as _run_minutes_graph

pytestmark = pytest.mark.integration

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



@pytest.mark.anyio
async def test_agenda_track_b_prompt_routing():
    # 1. 理解层 Agent 系统提示词路由
    from domains.meeting.meeting_core.meeting_understanding_agent import MeetingUnderstandingAgent
    mock_client = MagicMock()

    async def mock_structured(prompt, *args, **kwargs):
        from domains.meeting.models_generated import MeetingUnderstanding
        return MeetingUnderstanding(meeting_brief="b", meeting_purpose="p")
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

    await agent.run(
        "议题模式：agenda_enhanced\n视角模式：objective\n\n会议理解：{}",
        view="agenda_objective",
    )
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

    await supervisor.review(
        "视角模式：objective\n纪要返工次数：0/2\n\n议题模式：agenda_enhanced\n草稿：{}",
        view="agenda_objective",
    )
    called_prompt = mock_client.structured.call_args[0][0]
    expected_prompt = GlobalSupervisor.build_prompt(MINUTES_AGENDA_SUPERVISOR_PROMPT)
    assert called_prompt == expected_prompt

    # 4. 纪要渲染 Render 提示词路由
    from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
    renderer = MinutesGenerationRender(mock_client)
    # 4a. 无模板模式：不再有 LLM prompt，生产走 render_draft
    rendered_prompt, _ = renderer._prompt_and_user(
        "议题模式：agenda_enhanced\n视角模式：objective",
        "",
        view="agenda_objective",
    )
    assert rendered_prompt == ""
    # 4b. 模板模式
    rendered_prompt_tpl, _ = renderer._prompt_and_user(
        "议题模式：agenda_enhanced\n视角模式：objective",
        "# 通用纪要模板\n{{scalar:要点梳理}}",
        view="agenda_objective",
    )
    assert "严格遵循模板栏目规约与公文层级标准完成排版" in rendered_prompt_tpl
    assert "大项标题（### 一. 议题名称）" in rendered_prompt_tpl


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
            return MeetingUnderstanding(meeting_brief="测试", meeting_purpose="目的")
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
    assert any("minutes/agent/agenda" in label for label in called_labels)

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
    assert "agenda_plan" in p.extra_line_inputs

    args = _runner_args(p)
    prep = await prepare_run(p.ctx, **args)
    # 核心守卫：runner.py 绝不可在 prepare_run 中丢弃 agenda_plan
    assert "agenda_plan" in prep.line_extra
    plan = prep.line_extra["agenda_plan"]
    assert any("自研芯片二期量产" in it.title for it in plan.items)


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
    assert any("minutes/agent/agenda" in label for label in called)


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
    assert any("minutes/agent/agenda" in label for label in called)


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
    assert not any("meeting_understanding" in label for label in called)


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
