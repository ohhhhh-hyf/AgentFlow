# 拆分自 test_agenda.py，覆盖：test_orchestrator_line_shared_context_enhanced, test_shared_context_agenda_aux, test_orchestrator_line_shared_context_fallback…

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
    assert "【会议原文】\n张三: 行动项与风险" in actions_ctx


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
