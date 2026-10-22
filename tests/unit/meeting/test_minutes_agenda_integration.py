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
    assert "议题大项（### 一. 议题名称）" in rendered_prompt_tpl

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
    assert "避免在每句话开头机械堆砌“某某提出/某某认为/某某指出”等发言动词" in _MINUTES_COMMON_BASE

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
    """验证议题纪要草稿与渲染提示词中：加粗引导、首行直出、解除字数枷锁、去转述动词。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
        MINUTES_AGENDA_RENDER_PROMPT,
    )

    # 1. 验证生成提示词彻底移除字数枷锁（不再限制 40-60 字及 2-5 条）
    assert "单条约 40–60 字" not in MINUTES_AGENDA_GENERATION_PROMPT
    assert "提炼 2–5 条核心事实" not in MINUTES_AGENDA_GENERATION_PROMPT

    # 2. 验证生成提示词包含加粗引导规范与首行直出规约
    assert "- **[事项/方案/方向主题]**：具体事实陈述" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "项首大项标题（首行顶格直出）" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "绝对严禁在标题前编写任何导语、前言、背景铺垫或过渡段落" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "严禁在正文中出现“xxx提出”、“xxx强调”" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "量化数据精准穷尽" in MINUTES_AGENDA_GENERATION_PROMPT

    # 3. 验证渲染提示词注入【零导语首行直出铁规】并完整保留加粗
    assert "【零导语首行直出铁规】" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "绝对严禁在二级栏目标题与首个三级小标题之间插入任何总结句、过渡句或前言导语" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "条目完整保留「- **事项主题**：具体事实陈述」加粗格式" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT

    # 4. 验证非模板渲染也同步对齐加粗格式
    assert "- **事项主题**：具体事实陈述" in MINUTES_AGENDA_RENDER_PROMPT


def test_orchestrator_line_shared_context_recency_injection():
    """验证议题模式下长上下文最底端注入最高优先级执行红线（近因效应）。"""
    nodes = _Nodes()
    state_enhanced = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": True,
        "templates": {"minutes": "# 通用模板\n{{scalar:要点梳理}}"},
    }
    ctx = nodes._line_shared_context(state_enhanced, "minutes")
    assert "【审定议题草稿生成核心红线（执行前最后确认）】" in ctx
    assert "1. 格式统一加粗：正文列表项一律严格采用「- **[事项/方案/方向主题]**：具体事实陈述」格式" in ctx
    assert "2. 彻底剥离转述" in ctx
    assert "3. 充分充实研讨细节" in ctx
    assert "4. 结构纯净零前言" in ctx

    # 验证非议题模式下不注入该红线
    state_legacy = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": False,
        "templates": {"minutes": "# 通用模板\n{{scalar:要点梳理}}"},
    }
    ctx_legacy = nodes._line_shared_context(state_legacy, "minutes")
    assert "【审定议题草稿生成核心红线" not in ctx_legacy

    # 验证非 minutes 任务线不注入该红线
    state_actions = {
        "transcript": "张三 10:00: 讨论芯片量产",
        "has_valid_agenda": True,
    }
    ctx_actions = nodes._line_shared_context(state_actions, "actions")
    assert "【审定议题草稿生成核心红线" not in ctx_actions
