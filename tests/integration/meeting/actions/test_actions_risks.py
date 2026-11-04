# 拆分自原大文件，保留：test_actions_prompts_and_contracts_positive_hygiene, test_risks_prompts_and_contracts_positive_hygiene, test_action_items_report_validation_new_schema…

"""测试待办与风险的公文流文本生成与HTML渲染。"""

import re
import pytest
from core.graph.engine_text import render_risk_items
from domains.meeting.memory.render import (
    _parse_actions_from_text,
    _parse_risks_from_text,
    render_actions_html,
    render_risks_html,
)
from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender

pytestmark = pytest.mark.integration

if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))

def test_actions_prompts_and_contracts_positive_hygiene():
    """验证待办提示词与契约已实现全正向引导，零禁止性恐吓词，零测试人名与工程泄漏。"""
    from domains.meeting.tasks.actions.prompts import (
        ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
        ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT,
        ACTION_ITEMS_RENDER_PROMPT,
    )
    from domains.meeting.tasks.actions.contracts import (
        ActionItemsGenerationContract,
        ActionItemsSupervisorContract,
    )

    combined = (
        ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
        + ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT
        + ACTION_ITEMS_RENDER_PROMPT
        + str(ActionItemsGenerationContract.to_output_contract())
        + str(ActionItemsSupervisorContract.to_output_contract())
    )

    # 1. 验证负向禁止性字眼清零
    for forbidden_word in ["严禁", "禁止", "杜绝", "草草收尾"]:
        assert forbidden_word not in combined, f"待办提示词或契约中仍包含负向禁止词: {forbidden_word}"

    # 2. 验证私有测试人名与领域泄漏项清零
    for leaked_term in ["申家坤", "徐玥", "930", "特种人员", "人员进出场资料闭环"]:
        assert leaked_term not in combined, f"待办提示词或契约中仍包含泄漏词汇: {leaked_term}"

    # 3. 验证评级梯队与分类打架内耗已消除
    assert "全选中优先" not in combined
    assert "未拉开梯度" not in combined


def test_risks_prompts_and_contracts_positive_hygiene():
    """验证风险提示词与契约已实现全正向引导，零禁止性恐吓词，零特定领域泄漏。"""
    from domains.meeting.tasks.risks.prompts import (
        RISK_GENERATION_SYSTEM_PROMPT,
        RISK_SUPERVISOR_DOMAIN_PROMPT,
        RISK_RENDER_PROMPT,
    )
    from domains.meeting.tasks.risks.contracts import (
        RiskGenerationContract,
        RiskSupervisorContract,
    )

    combined = (
        RISK_GENERATION_SYSTEM_PROMPT
        + RISK_SUPERVISOR_DOMAIN_PROMPT
        + RISK_RENDER_PROMPT
        + str(RiskGenerationContract.to_output_contract())
        + str(RiskSupervisorContract.to_output_contract())
    )

    # 1. 验证负向禁止性字眼清零
    for forbidden_word in ["严禁", "禁止", "杜绝", "绝不"]:
        assert forbidden_word not in combined, f"风险提示词或契约中仍包含负向禁止词: {forbidden_word}"

    # 2. 验证特定场景词汇软引导清零
    for leaked_term in ["会翻车", "防汛与排水隐患", "现场实体质量隐患"]:
        assert leaked_term not in combined, f"风险提示词或契约中仍包含泄漏词汇: {leaked_term}"

    # 3. 验证评级梯队内耗已消除
    assert "全选中风险" not in combined
    assert "扎堆中风险" not in combined


def test_action_items_report_validation_new_schema():
    """验证待办报告校验器（ActionItemsReport）使用扁平 8 字段契约。"""
    from core.schema.validation import OutputValidationError
    from domains.meeting.reports import ActionItemsReport

    payload = {
        "actions": [
            {
                "title": "雨水倒灌问题处理",
                "item": "检查并处理卢萨卡点提升桶位置雨水倒灌问题，通过技术措施解决",
                "owner": "施工组",
                "deadline": "会后",
                "collaborators": ["运维团队"],
                "acceptance_criteria": "通过技术措施解决雨水倒灌问题",
                "dependency": "现场脚手架搭建就绪",
                "evidence": "检查并处理卢萨卡点提升桶位置雨水倒灌问题",
            }
        ],
        "quality_warning": None,
        "personalized_text": "1. **雨水倒灌问题处理**\n   - 检查并处理卢萨卡点提升桶位置雨水倒灌问题",
    }
    report = ActionItemsReport.validate(payload)
    assert len(report.actions) == 1
    act = report.actions[0]
    assert act["title"] == "雨水倒灌问题处理"
    assert act["item"].startswith("检查并处理卢萨卡点")
    assert act["owner"] == "施工组"
    assert act["acceptance_criteria"] == "通过技术措施解决雨水倒灌问题"

    # 旧字段不再被接受
    payload_legacy = {
        "actions": [
            {
                "task": "临时修复防汛板",
                "owner": "施工组",
                "deadline": "今天",
                "priority": "high",
                "evidence": "今天先把防汛板立起来",
            }
        ]
    }
    with pytest.raises(OutputValidationError):
        ActionItemsReport.validate(payload_legacy)


def test_action_items_flat_contract_compatibility() -> None:
    """验证扁平 actions 契约的校验器与渲染链路。"""
    from domains.meeting.models import ActionItems
    from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender

    payload = {
        "actions": [
            {
                "title": "契约解耦与单测",
                "item": "完成新旧契约解耦与单测编写",
                "owner": "核心团队",
                "deadline": "周五",
                "collaborators": ["测试组", "运维组"],
                "acceptance_criteria": "全量单测通过",
                "dependency": None,
                "evidence": "周五前完成解耦",
            },
            {
                "title": "线上告警监控",
                "item": "跟进线上告警指标监控",
                "owner": None,
                "deadline": None,
                "collaborators": [],
                "acceptance_criteria": None,
                "dependency": None,
                "evidence": "后续多关注监控",
            },
        ],
    }

    # 1. ActionItems 只保留扁平 actions
    inst = ActionItems.validate(payload)
    assert len(inst.actions) == 2
    assert inst.actions[0]["item"] == "完成新旧契约解耦与单测编写"
    assert not hasattr(inst, "assigned_actions")
    assert not hasattr(inst, "unassigned_actions")

    # 2. 渲染器读取扁平 actions 并正确渲染清单
    state = {
        "objective_perspective": True,
        "lines": {"actions": {"draft": payload}},
    }
    extracted = ActionItemsRender.extract_actions(state)
    assert len(extracted) == 2
    rendered_text = ActionItemsRender.render_draft(state)
    assert "契约解耦与单测" in rendered_text
    assert "完成新旧契约解耦与单测编写" in rendered_text
    assert "核心团队" in rendered_text
    assert "（责任方：核心团队 配合方：测试组、运维组）" in rendered_text
    assert "线上告警监控" in rendered_text
    assert "跟进线上告警指标监控" in rendered_text

    # 3. 验证经过 LLMClient 结构化解析器时不会被剥离 actions
    import json
    from infra.llm.llmclient import LLMClient
    raw_json = json.dumps(payload)
    parsed = LLMClient._parse_and_validate(
        raw_json,
        ActionItems,
        allow_missing=frozenset(),
    )
    assert len(parsed.actions) == 2
    assert parsed.actions[0]["item"] == "完成新旧契约解耦与单测编写"
    assert not hasattr(parsed, "assigned_actions")


def test_actions_has_no_understanding_profile() -> None:
    from domains.meeting.meeting_core.understanding_profiles import TASK_PROFILES
    from domains.meeting.meeting_core.contracts import build_core_contract_for_tasks

    assert "actions" not in TASK_PROFILES

    # risks 单独或与 actions 组合时，仍只按 risks 的轻量 profile 生成契约
    contract_r, _ = build_core_contract_for_tasks(["risks"])
    contract_ar, _ = build_core_contract_for_tasks(["actions", "risks"])
    for contract in (contract_r, contract_ar):
        assert "segment_title" in contract
        assert "context_and_reasoning" not in contract
        assert "key_facts" not in contract

    # 混入 minutes 时仍使用 full segments
    contract_m, _ = build_core_contract_for_tasks(["minutes", "actions"])
    assert "context_and_reasoning" in contract_m
    assert "key_facts" in contract_m


def test_orchestrator_shared_context_supplies_transcript_for_actions_and_risks():
    """验证 actions 只读会议原文；risks 仍保留原有原文 + 顺藤摸瓜指引。"""
    from domains.meeting.orchestrator import MeetingAgentSystem

    orch = object.__new__(MeetingAgentSystem)
    state = {
        "perspective": "objective",
        "transcript": "【讨论实录】张三：我承诺周五前完成接口改造。李四：网关并发突破 10000 时存在熔断风险。王总：大家必须在周日前完成上线验收。",
        "meeting_understanding": {
            "meeting_purpose": "周例会",
            "speakers": [{"name": "张三"}, {"name": "李四"}, {"name": "王总"}],
            "session_segments": [{"segment_title": "架构改造"}],
            "decisions": ["王总明确：必须在周日前完成上线验收", "同意架构改造方案"],
            "action_hints": [{"action": "完成接口改造", "owner": "张三"}],
            "risk_hints": [{"risk": "网关并发突破 10000 时存在熔断风险", "owner": "李四"}],
        },
        "lines": {},
    }

    # 1. actions 只给原文，不再给会议理解 / 视角 / 命中内容
    ctx_actions = orch._line_shared_context(state, "actions")
    assert ctx_actions == "【会议原文】\n" + state["transcript"]
    assert "会议理解" not in ctx_actions
    assert "action_hints" not in ctx_actions
    assert "用户画像" not in ctx_actions

    # 2. 验证 risks 上下文含原文与指引
    ctx_risks = orch._line_shared_context(state, "risks")
    assert "【讨论实录】张三：我承诺周五前完成接口改造" in ctx_risks
    assert "深度结合【会议原文】全面穷尽挖掘" in ctx_risks
