# 拆分自 test_agenda.py，覆盖：test_meeting_understanding_node_agenda_guidance, test_meeting_state_declares_agenda_fields, test_minutes_prompt_matter_oriented_governance…

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


def test_meeting_state_declares_agenda_fields():
    from domains.meeting.models import MeetingState
    annotations = MeetingState.__annotations__
    assert "has_valid_agenda" in annotations
    assert "valid_agendas" in annotations
    assert "tagged_transcript" in annotations


def test_minutes_prompt_matter_oriented_governance():
    """验证新老逻辑 Prompt 彻底去机械流水账对白，确立就事论事与正向引导准则。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_OBJECTIVE_GENERATION_PROMPT,
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
        MINUTES_AGENDA_SUPERVISOR_PROMPT,
    )
    from domains.meeting.meeting_core.prompts import (
        MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT,
        build_understanding_prompt,
    )
    from domains.meeting.meeting_core.understanding_profiles import TASK_PROFILES

    # 1. 核心诱因根治：验证公共基底彻底废除“主体+动作”句式公式，引入三层主体与就事论事
    assert "主体 + 核心动作/主张 + 量化指标/定调依据 + 最终结论/后续安排" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "分章节主体表达规范（就事论事原则）" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "避免机械堆砌发言动词" in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 2. 负向对抗字眼治理：验证核心生成 Prompt 不包含杜绝/拒绝等对抗句式
    for p in [MINUTES_OBJECTIVE_GENERATION_PROMPT, MINUTES_AGENDA_GENERATION_PROMPT]:
        assert "杜绝凭空编造" not in p
        assert "拒绝多从句生硬拼接的长难句" not in p
        assert "剔除铺垫修辞" not in p

    # 3. 理解层决议格式治理：验证动态 minutes 与议题 prompt 均要求 decisions 以事项为主干
    minutes_understanding_prompt = build_understanding_prompt(
        TASK_PROFILES["minutes"], task="minutes"
    )
    risks_understanding_prompt = build_understanding_prompt(
        TASK_PROFILES["risks"], task="risks"
    )
    assert "条目以被决定的业务事项为主干" in minutes_understanding_prompt
    assert "以被决定的业务事项为主干" in MEETING_UNDERSTANDING_AGENDA_SYSTEM_PROMPT
    assert "严禁主观脑补" not in risks_understanding_prompt

    # 4. 审核放行规则验证：确保 Supervisor 显式放行公文决议体与脱水表述
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in MINUTES_AGENDA_SUPERVISOR_PROMPT


def test_agenda_minutes_quality_and_stability_prompts():
    """验证议题纪要草稿与渲染提示词中：扁平子主题、列表项就事论事、解除字数枷锁、去转述动词。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_AGENDA_GENERATION_PROMPT,
        MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
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
