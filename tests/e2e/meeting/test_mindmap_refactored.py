"""e2e/integration test: 验证思维导图 (mindmap) 重构后的端到端全链路行为。

1. 单任务 mindmap 调用：
   - 彻底跳过 meeting_understanding（不调用 LLM）；
   - 彻底跳过 perspective_modeling（不调用 LLM）；
   - 彻底拔除 llm_render（不调用 LLM 文本/流式接口）；
   - 短会通过确定性 Fast-Path 直接放行，长会正常调用 MindmapSupervisor 审核；
   - 纯 Python 确定性组装与清洗大纲输出；
2. 共享上下文纯净化：仅注入【会议原文】，不注入空 JSON 字典；
3. 多任务共存安全：当同时请求 minutes + mindmap 时，会议理解正常运作，零副作用。
"""
from __future__ import annotations

import asyncio
from typing import Any
import pytest

from domains.meeting.models import (
    MeetingUnderstanding,
    Mindmap,
    MindmapSupervisorReview,
    Minutes,
    MinutesSupervisorReview,
)
from domains.meeting.orchestrator import MeetingAgentSystem
from domains.meeting.domain_config import LINE_KINDS

pytestmark = pytest.mark.e2e


def _sample_mindmap() -> Mindmap:
    return Mindmap(
        title="双周研发效能复盘会",
        outline=(
            "# 双周研发效能复盘会\n"
            "## 核心系统重构\n"
            "### 网关鉴权改造\n"
            "- 完成鉴权模块解耦上线\n"
            "- 压测QPS突破20000\n"
            "## 待办事项\n"
            "- [修复流控配置热更新缺陷] (责任人: 张三 | 时限: 周五18:00前)\n"
            "## 相关风险\n"
            "- 生产环境灰度集群显存不足\n"
        ),
    )


def _sample_mindmap_review() -> MindmapSupervisorReview:
    return MindmapSupervisorReview(
        decision="approve",
        mindmap_check={"status": "pass", "findings": []},
        feedback=[],
    )


class _MockLLMClient:
    def __init__(self) -> None:
        self.structured_calls: list[tuple[Any, str, str]] = []
        self.text_calls: list[tuple[str, str]] = []

    async def structured(self, system: str, user: str, model=None, contract=None, **kwargs):
        self.structured_calls.append((model, system, user))
        if model is Mindmap:
            return _sample_mindmap()
        if model is MindmapSupervisorReview:
            return _sample_mindmap_review()
        if model is MeetingUnderstanding:
            return MeetingUnderstanding(
                meeting_brief="复盘会议",
                meeting_purpose="技术同步",
                speakers=["张三", "李四"],
                session_segments=[],
                decisions=["本周发布"],
                open_questions=[],
                risks=[],
            )
        if model is Minutes:
            return Minutes(headline="复盘会议", executive_summary=["总结"])
        if model is MinutesSupervisorReview:
            return MinutesSupervisorReview(
                decision="approve",
                facts_check={"status": "pass", "findings": []},
                structure_check={"status": "pass", "findings": []},
                consistency_check={"status": "pass", "findings": []},
                feedback=[],
            )
        raise AssertionError(f"未预期的模型调用：{model!r}")

    async def text(self, prompt: str, user: str, **kwargs):
        self.text_calls.append((prompt, user))
        return "rendered text"

    async def stream_text(self, prompt: str, user: str, **kwargs):
        self.text_calls.append((prompt, user))
        yield "rendered chunk"

    def monitor_snapshot(self) -> dict[str, Any]:
        return {"usage_totals": {"total_tokens": 100, "cache_hit_tokens": 0}}


def test_mindmap_render_policy_is_never() -> None:
    """验证领域配置中 mindmap 已锁定 llm_render 为 never。"""
    assert LINE_KINDS["mindmap"]["llm_render"] == "never"


def test_mindmap_single_task_pipeline_fast_path() -> None:
    """验证单任务 mindmap 执行：跳过会议理解、跳过视角建模、跳过 LLM 渲染。"""
    client = _MockLLMClient()
    system = MeetingAgentSystem(client=client)

    async def _run():
        events = []
        async for event in system.run_streaming(
            transcript="张三：我们完成了网关鉴权改造，压测QPS突破20000。周五前要修复流控配置。",
            user={"name": "张三"},
            lines=["mindmap"],
            lang="zh",
        ):
            events.append(event)
        return events

    events = asyncio.run(_run())
    types = [e.get("type") for e in events]
    assert "chunk" in types
    assert "done" in types

    # 1. 验证被调用的模型列表：MeetingUnderstanding 绝不可被调用
    called_models = [m for m, _, _ in client.structured_calls]
    assert MeetingUnderstanding not in called_models, "单任务 mindmap 不应触发 MeetingUnderstanding"
    assert Mindmap in called_models, "必须调用 MindmapAgent 生成大纲"
    # 短会 (<2000字符) 命中确定性快速放行，节约一次审核 LLM 调用
    assert client.text_calls == [], "mindmap 渲染必须为纯 Python 确定性执行，严禁调用 LLM"

    # 2. 验证生成 Agent 接收的上下文：纯净仅包含【会议原文】，不含空 JSON 字典
    mindmap_gen_call = next((sys, usr) for m, sys, usr in client.structured_calls if m is Mindmap)
    sys_prompt, usr_prompt = mindmap_gen_call
    assert "会议思维导图架构师" in sys_prompt
    assert "【会议原文】" in usr_prompt
    assert "会议理解" not in usr_prompt, "跳过理解后，不应给大纲生成注入会议理解空 JSON"

    # 3. 验证最终产出的 Markdown 树状结构
    done_event = next(e for e in events if e.get("type") == "done")
    reports = done_event.get("reports") or {}
    assert "mindmap" in reports
    outline = reports["mindmap"].outline
    assert "# 双周研发效能复盘会" in outline
    assert "## 核心系统重构" in outline
    assert "## 待办事项" in outline
    assert "## 相关风险" in outline


def test_mindmap_supervisor_review_on_long_meeting() -> None:
    """验证长会议场景下，MindmapSupervisorReview 正常触发调用。"""
    client = _MockLLMClient()
    system = MeetingAgentSystem(client=client)
    # 关闭短会快速放行门禁，强制走 LLM Supervisor 审核
    system._supervisor_fast_path_chars = 0

    async def _run():
        events = []
        async for event in system.run_streaming(
            transcript="张三：我们完成了网关鉴权改造，压测QPS突破20000。周五前要修复流控配置。",
            user={"name": "张三"},
            lines=["mindmap"],
            lang="zh",
        ):
            events.append(event)
        return events

    events = asyncio.run(_run())
    called_models = [m for m, _, _ in client.structured_calls]
    assert Mindmap in called_models
    assert MindmapSupervisorReview in called_models, "长会或非短会时必须调用 MindmapSupervisorReview 审核"
    assert client.text_calls == [], "依然零 LLM 渲染"


def test_mindmap_multi_task_coexistence_safety() -> None:
    """验证多任务并发时（如 minutes + mindmap），公共会议理解正常运作，零破坏。"""
    client = _MockLLMClient()
    system = MeetingAgentSystem(client=client)

    async def _run():
        events = []
        async for event in system.run_streaming(
            transcript="张三：本周发布新版本。",
            user={"name": "张三"},
            lines=["minutes", "mindmap"],
            lang="zh",
        ):
            events.append(event)
        return events

    events = asyncio.run(_run())
    called_models = [m for m, _, _ in client.structured_calls]
    # 多任务并发时，minutes 依然需要会议理解，因此 MeetingUnderstanding 正常调用
    assert MeetingUnderstanding in called_models, "多任务包含 minutes 时必须正常保留会议理解底座"
    assert Mindmap in called_models, "mindmap 正常运行"


def test_mindmap_app_run_task_response(monkeypatch) -> None:
    """验证 app/tasks.py run_task 接口层返回: data.text 为层级 Markdown，data.file_name 为 mindmap.html。"""
    from app.schemas import TaskRequest
    from app.tasks import run_task
    import domains.meeting.orchestrator as orch_module

    mock_client = _MockLLMClient()
    orig_cls = orch_module.MeetingAgentSystem

    def _mock_system(*args, **kwargs):
        kwargs["client"] = mock_client
        return orig_cls(*args, **kwargs)

    monkeypatch.setattr(orch_module, "MeetingAgentSystem", _mock_system)

    req = TaskRequest(
        texts={"transcript": "张三：我们完成了网关鉴权改造，压测QPS突破20000。周五前要修复流控配置。"},
    )
    resp = asyncio.run(run_task("meeting", "mindmap", req, user_id="test_user", request_id="req_test_mindmap"))
    assert resp.code == 0
    assert resp.message == "success"
    assert resp.data.file_name == "mindmap.html"
    assert "# 双周研发效能复盘会" in resp.data.text
    assert "## 核心系统重构" in resp.data.text
    assert "## 待办事项" in resp.data.text
    assert "## 相关风险" in resp.data.text


def test_mindmap_app_stream_task_events(monkeypatch) -> None:
    """验证 app/tasks.py stream_task 流式接口: 正确抛出 chunk 事件并在 done 事件中携带 data.text 与 data.file_name。"""
    from app.schemas import TaskRequest
    from app.tasks import stream_task
    import domains.meeting.orchestrator as orch_module

    mock_client = _MockLLMClient()
    orig_cls = orch_module.MeetingAgentSystem

    def _mock_system(*args, **kwargs):
        kwargs["client"] = mock_client
        return orig_cls(*args, **kwargs)

    monkeypatch.setattr(orch_module, "MeetingAgentSystem", _mock_system)

    req = TaskRequest(
        texts={"transcript": "张三：我们完成了网关鉴权改造，压测QPS突破20000。周五前要修复流控配置。"},
    )

    async def _test():
        response = await stream_task("meeting", "mindmap", req, user_id="test_user", request_id="req_test_stream")
        events = []
        async for chunk in response.body_iterator:
            import json
            chunk_str = chunk if isinstance(chunk, str) else chunk.decode("utf-8")
            for line in chunk_str.strip().splitlines():
                if line.strip():
                    events.append(json.loads(line))
        return events

    events = asyncio.run(_test())
    event_types = [e.get("type") for e in events]
    assert "chunk" in event_types
    assert "done" in event_types

    done_event = next(e for e in events if e.get("type") == "done")
    assert done_event["code"] == 0
    assert done_event["data"]["file_name"] == "mindmap.html"
    assert "# 双周研发效能复盘会" in done_event["data"]["text"]


