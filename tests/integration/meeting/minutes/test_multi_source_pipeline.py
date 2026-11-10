# 拆分自 test_multi_source.py，覆盖：test_tc08_supervisor_prompt_and_rules, test_tc06_prepare_line_extra_minutes_auxiliary, test_prepare_actions_auxiliary_does_not_enter_minutes…

"""多源文本融合会议纪要单元测试 (Multi-Source Texts Minutes).

覆盖 TC-01 至 TC-10:
- TC-01: 向下兼容纯语音 (仅 transcript)
- TC-02: 单项包含关键点 (transcript + keypoints)
- TC-03: 单项包含笔记含箭头与无箭头 (transcript + notes)
- TC-04: 单项包含视觉信息 (transcript + vision_info)
- TC-05: 多源全开 (四者俱全)
- TC-06: 与议题纪要 docs 共存
- TC-07: 英文多语种适配 (lang='en')
- TC-08: Supervisor 审查准则验证与上下文注入
- TC-09: Schema 协议层检验 (vision_info 校验与非法 key 拦截)
- TC-10: 议题纪要 + 多源辅助的 system prompt 组装
"""

from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock
import pytest
from pydantic import ValidationError
from app.schemas import TEXT_KEYS, TaskRequest
from app.tasks import (
    _collect_texts,
    _pack_actions_auxiliary,
    _pack_minutes_auxiliary,
    _parse_notes_items,
    _prepare,
)
from domains.meeting.models import Minutes
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    build_minutes_supervisor_prompt,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from tests.support.builders import (
    AGENDA_BASE as _AGENDA_BASE,
    KEYPOINTS_TAG as _KEYPOINTS_TAG,
    NOTES_TAG as _NOTES_TAG,
    VISION_TAG as _VISION_TAG,
    agenda_context as _agenda_context,
    normal_context as _normal_context,
)

pytestmark = pytest.mark.integration

async def _capture_system_prompt(
    shared_context: str, *, lang: str = "zh", view: str = "objective"
) -> str:
    captured: dict[str, str] = {}

    class FakeClient:
        async def structured(self, system, *args, **kwargs):
            captured["system"] = system
            return Minutes()

    agent = MinutesGenerationAgent(FakeClient())
    await agent.run(shared_context, view=view, lang=lang)
    return captured["system"]

def test_tc08_supervisor_prompt_and_rules():
    """TC-08: Supervisor 审查准则验证 (批注拦截、数据专名一致)。"""
    prompt = build_minutes_supervisor_prompt(
        "objective", aux_labels=["notes", "keypoints", "vision"]
    )
    assert "多源辅助参考审查（输入含对应标签时生效）" in prompt
    assert "拦截主观批注：【用户划线原话与笔记】中的个人批注与主观吐槽严禁进入正文" in prompt
    assert "正文引用的【用户核心关键点】中的数字指标、专有名词" in prompt
    assert "正文引用的【视觉信息参考(OCR)】中的数字指标、专有名词" in prompt
    assert "泄露按严重缺陷处理" in prompt


def test_tc06_prepare_line_extra_minutes_auxiliary():
    """TC-06: 验证 _prepare 函数能正确为 minutes 任务组装 minutes_auxiliary。"""
    req = TaskRequest(
        texts={
            "transcript": "今天开会讨论下周发布计划。",
            "keypoints": "流程审批量同比增长46%",
            "notes": "广州珠海增加7个 -> 真的假的？",
            "vision_info": "吞吐量 15000 QPS",
        }
    )
    prep = _prepare("meeting", "minutes", req, user_id="test_user")
    assert prep.line == "minutes"
    assert "minutes_auxiliary" in prep.extra_line_inputs
    aux = prep.extra_line_inputs["minutes_auxiliary"]
    assert "【用户核心关键点】\n流程审批量同比增长46%" in aux
    assert "【用户划线原话与笔记】\n- 原话：\"广州珠海增加7个\" | 备注：真的假的？" in aux
    assert "【视觉信息参考(OCR)】\n吞吐量 15000 QPS" in aux


def test_prepare_actions_auxiliary_does_not_enter_minutes():
    """actions_text 只在 actions 线进入 line_extra，不污染 minutes_auxiliary。"""
    req = TaskRequest(
        texts={
            "transcript": "EPC需在周五前提供合同确认函。",
            "keypoints": "涡轮机运行确认",
            "notes": "李四配合",
            "vision_info": "涡轮机参数表",
            "actions_text": "EPC需提供合同确认函",
        }
    )
    prep = _prepare("meeting", "actions", req, user_id="test_user")
    assert prep.line == "actions"
    assert "actions_auxiliary" in prep.extra_line_inputs
    aux = prep.extra_line_inputs["actions_auxiliary"]
    assert "【用户标记待办原文】\nEPC需提供合同确认函" in aux
    assert "【用户核心关键点】\n涡轮机运行确认" in aux
    assert "【用户划线原话与笔记】\n- 笔记：李四配合" in aux
    assert "【视觉信息参考(OCR)】\n涡轮机参数表" in aux
    assert "minutes_auxiliary" not in prep.extra_line_inputs


def test_tc06_orchestrator_context_injection():
    """TC-06: 验证 orchestrator 编排层将 minutes_auxiliary 分别注入 shared_context 与 supervisor_context。"""
    from domains.meeting.orchestrator import _Nodes

    nodes = _Nodes.__new__(_Nodes)
    nodes._supervisor_source_pack = lambda state, ln: "【原文依据切片】"
    nodes._length_budget_line = lambda state, ln, **kwargs: ""
    nodes._revision_instruction = lambda state, ln: ""
    nodes._meeting_pack = lambda state, ln: {}
    nodes._mode_label = lambda state: "objective"

    state = {
        "transcript": "会议原文内容...",
        "lines": {"minutes": {"draft": {"headline": "测试纪要", "executive_summary": []}}},
        "line_extra": {
            "minutes_auxiliary": "【用户核心关键点】\n指标A提升30%\n\n【视觉信息参考(OCR)】\nQPS: 12000"
        },
        "objective_perspective": True,
        "templates": {},
    }

    # 1. 验证草稿 Agent 上下文挂载
    shared_ctx = nodes._line_shared_context(state, "minutes")
    assert "【用户核心关键点】\n指标A提升30%" in shared_ctx
    assert "【视觉信息参考(OCR)】\nQPS: 12000" in shared_ctx

    # 2. 验证 Supervisor 审核上下文挂载
    sup_ctx = nodes._supervisor_context(state, "minutes")
    assert "【用户核心关键点】\n指标A提升30%" in sup_ctx
    assert "【视觉信息参考(OCR)】\nQPS: 12000" in sup_ctx


def test_normal_minutes_aux_unchanged():
    """普通 minutes：aux 照常注入，但不出现议程标记或议程清单。"""
    # 1. _prepare：无 docs -> 只有 minutes_auxiliary，没有 agenda_text
    req = TaskRequest(
        texts={
            "transcript": "今天开会讨论下周发布计划。",
            "keypoints": "流程审批量同比增长46%",
            "notes": "广州珠海增加7个 -> 真的假的？",
            "vision_info": "吞吐量 15000 QPS",
        }
    )
    prep = _prepare("meeting", "minutes", req, user_id="test_user")
    assert "minutes_auxiliary" in prep.extra_line_inputs
    assert "agenda_text" not in prep.extra_line_inputs

    # 2. _line_shared_context：aux 照常出现，但不出现议程标记/清单
    from domains.meeting.orchestrator import _Nodes

    nodes = _Nodes()
    state = {
        "transcript": "今天开会讨论下周发布计划。",
        "has_valid_agenda": False,
        "valid_agendas": [],
        "meeting_understanding": {
            "meeting_brief": "常规简报",
            "session_segments": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
        "line_extra": {
            "minutes_auxiliary": (
                "【用户核心关键点】\n流程审批量同比增长46%\n\n"
                "【用户划线原话与笔记】\n- 原话：\"广州珠海增加7个\" | 备注：真的假的？\n\n"
                "【视觉信息参考(OCR)】\n吞吐量 15000 QPS"
            )
        },
    }
    context = nodes._line_shared_context(state, "minutes")
    assert "【用户核心关键点】\n流程审批量同比增长46%" in context
    assert "【用户划线原话与笔记】" in context
    assert "【视觉信息参考(OCR)】\n吞吐量 15000 QPS" in context
    assert "议题模式：agenda_enhanced" not in context
    assert "【现场审定的有效议题清单】" not in context


@pytest.mark.anyio
async def test_phase4_supervisor_and_hard_execution_self_contained():
    """Phase 4 验证：无会议理解时，enforce 保持草稿 7 字段闭环，Supervisor 针孔质检平稳运行。"""
    from unittest.mock import MagicMock, AsyncMock
    from core.execution.hard_execution import enforce_minutes_draft
    from domains.meeting.models import MinutesSupervisorReview
    from domains.meeting.orchestrator import _Nodes, _EMPTY_MEETING_UNDERSTANDING
    from domains.meeting.tasks.minutes.steps.minutes_supervisor import MinutesGenerationSupervisor

    raw_transcript = (
        "张三 10:00: 我们决定在下周三上线系统v2.0，李四负责压测，目标QPS达到12000。"
        "李四 10:05: 收到，我周二前给出测试报告。"
        "王五 10:10: 外部依赖服务可能存在偶发超时，需要准备降级方案。"
    )
    draft_dict = {
        "headline": "系统v2.0发布与压测计划会",
        "executive_summary": [
            "会议针对系统v2.0上线安排进行了研讨，明确了上线排期与压测标准。",
            "系统v2.0定于下周三正式上线，压测指标定为12000 QPS。",
        ],
        "key_decisions": ["系统v2.0上线：下周三正式上线，压测达标QPS 12000生效"],
        "personally_relevant_points": ["李四：周二前完成压测并输出测试报告"],
        "risks_and_blockers": ["外部服务偶发超时，需准备降级方案"],
        "unresolved_questions": [],
        "history_comparison": [],
    }

    # 1. 验证 enforce_minutes_draft 在跳过会议理解时，完整保留草稿提炼的 7 字段
    enforced = enforce_minutes_draft(draft_dict, _EMPTY_MEETING_UNDERSTANDING, mode="objective")
    assert enforced["headline"] == "系统v2.0发布与压测计划会"
    assert len(enforced["key_decisions"]) == 1
    assert "下周三正式上线" in enforced["key_decisions"][0]
    assert len(enforced["risks_and_blockers"]) == 1
    assert "外部服务偶发超时" in enforced["risks_and_blockers"][0]
    assert "personally_relevant_points" in enforced
    assert "history_comparison" in enforced

    # 2. 验证 Supervisor source pack 在无理解层时仅依据草稿针孔与原文
    nodes = _Nodes.__new__(_Nodes)
    nodes._understanding = lambda s: s.get("meeting_understanding") or {}
    nodes._understanding_needle_fields = lambda ln: None
    nodes._mode_label = lambda s: "objective"
    nodes._minutes_view = lambda s, ln: "objective"
    nodes._length_budget_line = lambda s, ln, **kw: ""
    nodes._revision_instruction = lambda s, ln: "视角模式：objective\n本轮可以选择 approve、revise 或 reject。"

    state = {
        "transcript": raw_transcript,
        "meeting_understanding": _EMPTY_MEETING_UNDERSTANDING,
        "lines": {"minutes": {"draft": draft_dict}},
        "line_extra": {
            "minutes_auxiliary": "【用户核心关键点】\n目标QPS达到12000"
        },
        "lang": "zh",
    }
    source_pack = nodes._supervisor_source_pack(state, "minutes")
    assert "会议理解（摘要）：" not in source_pack
    assert "原文（最高事实来源）：" in source_pack or "已覆盖草稿中" in source_pack

    # 3. 验证 Supervisor context 正确拼接辅助材料且平稳运行
    sup_ctx = nodes._supervisor_context(state, "minutes")
    assert "【用户核心关键点】\n目标QPS达到12000" in sup_ctx
    assert "系统v2.0发布与压测计划会" in sup_ctx

    # 4. 验证 Supervisor 模型质检调用与判定闭环
    mock_client = MagicMock()
    mock_client.structured = AsyncMock(
        return_value=MinutesSupervisorReview(
            decision="approve",
            feedback=[],
            facts_check=True,
            perspective_check=True,
            consistency_check=True,
        )
    )
    supervisor = MinutesGenerationSupervisor(mock_client)
    review_res = await supervisor.review(sup_ctx, view="objective", lang="zh")
    assert review_res.decision == "approve"
    assert len(review_res.feedback) == 0
    call_args = mock_client.structured.call_args[0]
    assert "你是会议纪要质量审核专家" in call_args[0]
    assert "客观模式审查范围" in call_args[0]

