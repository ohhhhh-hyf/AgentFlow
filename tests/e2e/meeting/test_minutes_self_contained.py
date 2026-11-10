"""客观普通纪要自包含端到端回归测试 (Phase 5).

覆盖核心场景：
1. 单任务客观普通纪要端到端短路跳过会议理解，直面原文生成 7 字段；
2. 多源辅助材料（keypoints, notes, vision_info）动态拼接与规约挂载；
3. 英文模式（lang='en'）商务人设与 4 大语言红线包裹；
4. 多任务并发（lines=['minutes', 'actions']）时会议理解正常按需唤醒，互不踩踏；
5. 个人视角模式（view='personal'）保持正常调用会议理解与视角建模。
"""
from __future__ import annotations

import asyncio
from typing import Any
import pytest

from domains.meeting.models import (
    ActionItems,
    ActionItemsSupervisorReview,
    MeetingUnderstanding,
    Minutes,
    MinutesSupervisorReview,
)
from domains.meeting.orchestrator import MeetingAgentSystem

pytestmark = pytest.mark.e2e


def _dummy_minutes_draft() -> Minutes:
    return Minutes(
        executive_summary=[
            "会议针对系统架构优化与QPS扩容方案展开研讨，明确了核心推进节奏。",
            "技术团队决定对网关服务实施重构，下周三完成灰度发布，目标支持12000 QPS。",
        ],
        key_decisions=["网关服务重构：下周三完成灰度发布，满足12000 QPS性能指标"],
        personally_relevant_points=["李工：周二前输出压测与降级方案报告"],
        risks_and_blockers=["下游依赖系统高并发时可能出现超时熔断"],
        unresolved_questions=[],
        history_comparison=[],
    )


def _dummy_actions() -> ActionItems:
    return ActionItems(
        actions=[
            {
                "title": "网关重构压测",
                "item": "输出压测与降级方案报告",
                "owner": "李工",
                "deadline": "周二前",
                "collaborators": [],
                "acceptance_criteria": "达标12000 QPS",
                "dependency": None,
                "evidence": "李工负责在周二前输出压测报告。",
            }
        ]
    )


def _dummy_understanding() -> MeetingUnderstanding:
    return MeetingUnderstanding(
        meeting_brief="系统优化例会",
        meeting_purpose="推进网关重构与性能压测",
        speakers=["张工", "李工"],
        session_segments=[],
        decisions=["网关重构定于下周三灰度上线"],
        risks=["下游依赖超时"],
        open_questions=[],
    )


def _dummy_supervisor_review() -> MinutesSupervisorReview:
    return MinutesSupervisorReview(
        decision="approve",
        feedback=[],
        facts_check=True,
        perspective_check=True,
        consistency_check=True,
    )


def _dummy_actions_review() -> ActionItemsSupervisorReview:
    return ActionItemsSupervisorReview(
        decision="approve",
        actions_check={"status": "pass", "findings": []},
        feedback=[],
    )


class _TestFakeLLMClient:
    def __init__(self) -> None:
        self.structured_calls: list[dict[str, Any]] = []
        self.render_calls: list[tuple[str, str]] = []

    async def structured(self, system, user, model=None, contract=None, **kwargs):
        call_info = {
            "model": model,
            "system": system,
            "user": user,
            "contract": contract,
            "kwargs": kwargs,
        }
        self.structured_calls.append(call_info)

        if model is MeetingUnderstanding:
            return _dummy_understanding()
        if model is Minutes:
            return _dummy_minutes_draft()
        if model is MinutesSupervisorReview:
            return _dummy_supervisor_review()
        if model is ActionItems:
            return _dummy_actions()
        if model is ActionItemsSupervisorReview:
            return _dummy_actions_review()
        if model is None or model is dict or "perspective" in str(system) or "本人视角" in str(system):
            return {
                "confidence": "high",
                "personal_summary": "负责网关重构与性能压测",
                "focus_points": ["网关重构", "压测"],
                "possible_actions": [],
                "collaborations": [],
                "concerns": [],
                "data_gaps": [],
                "focus_risks": [],
                "open_questions": [],
            }
        raise AssertionError(f"Unexpected model call: {model!r}")

    async def text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        return "# 系统架构与性能优化会\n\n会议纪要正文。"

    async def stream_text(self, prompt, user, **kwargs):
        self.render_calls.append((prompt, user))
        yield "# 系统架构与性能优化会\n\n会议纪要正文。"


def test_minutes_single_task_objective_self_contained():
    """测试用例 1：单任务客观普通纪要端到端短路跳过会议理解，直面原文生成 7 字段。"""
    client = _TestFakeLLMClient()
    system = MeetingAgentSystem(client=client)
    system._supervisor_fast_path_chars = 0  # 强制走 Supervisor LLM 质检链路进行完整测试

    async def _run():
        events = []
        async for ev in system.run_streaming(
            transcript="张工 10:00: 我们决定下周三上线网关重构，李工周二前给出压测报告，目标12000 QPS。",
            lines=["minutes"],
            lang="zh",
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    # 1. 验证完成事件与无质量降级（主动自包含跳过，非降级）
    done_ev = next(ev for ev in events if ev.get("type") == "done")
    assert done_ev.get("quality_warning") is None, "单任务客观普通纪要自包含运行不得触发质量降级"
    assert "minutes" in done_ev.get("reports", {})

    # 2. 验证绝对没有调用 MeetingUnderstanding 模型
    models = [c["model"] for c in client.structured_calls]
    assert MeetingUnderstanding not in models, "单任务客观普通纪要绝不得调用 MeetingUnderstanding"
    assert Minutes in models
    assert MinutesSupervisorReview in models

    # 3. 验证草稿 Agent 上下文装配纯净
    draft_call = next(c for c in client.structured_calls if c["model"] is Minutes)
    sys_prompt = draft_call["system"]
    user_prompt = draft_call["user"]

    assert "你是专职会议秘书与业务分析专家" in sys_prompt
    assert "根据会议实际研讨的事项数量与讨论深度自然分项" in sys_prompt
    assert "围绕业务主线就事论事展开" in sys_prompt
    assert "以会议理解为事实骨架" not in sys_prompt
    assert "以理解层" not in sys_prompt

    assert "以【会议原文】为最高事实依据" in user_prompt
    assert "会议理解：" not in user_prompt
    assert "session_segments" not in user_prompt

    # 4. 验证渲染产物存在
    full_text = "".join(
        ev.get("text", "") for ev in events if ev.get("type") == "chunk" and ev.get("line") == "minutes"
    )
    assert len(full_text) > 0


def test_minutes_with_multi_source_auxiliary():
    """测试用例 2：多源辅助材料（keypoints, notes, vision_info）动态装配与规约生效。"""
    client = _TestFakeLLMClient()
    system = MeetingAgentSystem(client=client)

    aux_text = (
        "【用户核心关键点】\n目标支持12000 QPS\n\n"
        "【用户划线原话与笔记】\n- 原话：\"下周三上线\" | 备注：确认发布窗口\n\n"
        "【视觉信息参考(OCR)】\nAPI Gateway v2.4"
    )

    async def _run():
        events = []
        async for ev in system.run_streaming(
            transcript="张工：下周三上线网关重构，李工跟进压测报告。",
            lines=["minutes"],
            lang="zh",
            line_extra={"minutes_auxiliary": aux_text},
        ):
            events.append(ev)
        return events

    asyncio.run(_run())

    draft_call = next(c for c in client.structured_calls if c["model"] is Minutes)
    sys_prompt = draft_call["system"]
    user_prompt = draft_call["user"]

    # 验证动态规则块挂载
    assert "## 辅助材料使用规约" in sys_prompt
    assert "【原文事实优先】" in sys_prompt
    assert "## 用户关键点参考" in sys_prompt
    assert "## 用户笔记参考" in sys_prompt
    assert "## 视觉信息参考 (OCR)" in sys_prompt

    # 验证输入上下文包含辅助材料
    assert "【用户核心关键点】\n目标支持12000 QPS" in user_prompt
    assert "【用户划线原话与笔记】" in user_prompt
    assert "【视觉信息参考(OCR)】\nAPI Gateway v2.4" in user_prompt


def test_minutes_english_adaptation():
    """测试用例 3：英文多语种（lang='en'）人设包装与 4 大语言红线约束。"""
    client = _TestFakeLLMClient()
    system = MeetingAgentSystem(client=client)

    async def _run():
        events = []
        async for ev in system.run_streaming(
            transcript="Alice: We deploy the gateway redesign on Wednesday. Bob: I will finish the load testing by Tuesday.",
            lines=["minutes"],
            lang="en",
        ):
            events.append(ev)
        return events

    asyncio.run(_run())

    draft_call = next(c for c in client.structured_calls if c["model"] is Minutes)
    sys_prompt = draft_call["system"]
    user_prompt = draft_call["user"]

    # 验证英文人设与红线
    assert "【核心人设与交付目标】" in sys_prompt
    assert "你是专职的【英文（English）】会议纪要草稿 Agent" in sys_prompt
    assert "## 语言红线" in sys_prompt
    assert "所有字段必须严格使用【英文（English）】输出" in sys_prompt
    assert "[TBD]" in sys_prompt
    assert "[Owner] Action + Deliverable + Deadline" in sys_prompt
    assert "输出语种要求：英文（English）" in user_prompt


def test_minutes_multi_task_compatibility():
    """测试用例 4：多任务并发场景（lines=['minutes', 'actions']）下，理解层正常唤醒，互不踩踏。"""
    client = _TestFakeLLMClient()
    system = MeetingAgentSystem(client=client)

    async def _run():
        events = []
        async for ev in system.run_streaming(
            transcript="张工：下周三上线网关重构，李工周二前给出压测报告。",
            lines=["minutes", "actions"],
            lang="zh",
        ):
            events.append(ev)
        return events

    events = asyncio.run(_run())

    models = [c["model"] for c in client.structured_calls]
    # 多任务并发时，actions 依赖理解层，因此 MeetingUnderstanding 正常调用！
    assert MeetingUnderstanding in models, "多任务并发包含 actions 时，MeetingUnderstanding 必须正常唤醒"
    assert Minutes in models
    assert ActionItems in models

    # 验证 minutes 线依然直面原文生成且无空理解干扰
    draft_call = next(c for c in client.structured_calls if c["model"] is Minutes)
    assert "会议理解：" not in draft_call["user"], "minutes 任务线上行上下文切断理解层注入"
    assert "以【会议原文】为最高事实依据" in draft_call["user"]


def test_minutes_personal_view_retains_understanding():
    """测试用例 5：个人视角模式（view='personal'）严格保留会议理解与画像建模。"""
    client = _TestFakeLLMClient()
    system = MeetingAgentSystem(client=client)

    async def _run():
        events = []
        async for ev in system.run_streaming(
            transcript="张工：下周三上线网关重构，李工周二前给出压测报告。",
            user={"name": "李工", "perspective": "personal"},
            lines=["minutes"],
            lang="zh",
        ):
            events.append(ev)
        return events

    asyncio.run(_run())

    models = [c["model"] for c in client.structured_calls]
    # 个人模式下，必须调用会议理解作为全局事实底座
    assert MeetingUnderstanding in models, "个人视角模式严格保留会议理解依赖"
