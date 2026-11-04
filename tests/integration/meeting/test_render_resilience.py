"""tests/meeting/test_render_resilience.py
验证会议领域渲染双重保险与零 LLM 确定性保底机制：
1. _is_transient_error 异常分类判定
2. 各任务线 render_draft 纯代码确定性组装
3. 第一道保险：瞬时网络故障触发单步局部重试自愈
4. 第二道保险：大模型彻底不可用时 0 毫秒纯代码保底交付与统一质量提示
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator
import pytest

from core.runtime.render import _is_transient_error, produce_line
from domains.meeting.tasks.mindmap.steps.mindmap_render import MindmapRender
from domains.meeting.tasks.minutes_trace.steps.minutes_trace_render import MinutesTraceRender
from domains.meeting.tasks.minutes_styles.steps.minutes_styles_render import MultiStylesRender
from domains.meeting.tasks.consensus_decision.steps.consensus_decision_render import ConsensusDecisionRender
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender
from domains.meeting.tasks.risks.steps.risks_render import RiskRender
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_render import AgendaMinutesRender


def test_is_transient_error() -> None:
    """验证瞬时可重试异常与不可重试异常判定。"""
    assert _is_transient_error(asyncio.TimeoutError("timeout")) is True
    assert _is_transient_error(TimeoutError("connection timed out")) is True
    assert _is_transient_error(ConnectionResetError("connection reset by peer")) is True
    assert _is_transient_error(Exception("502 Bad Gateway from nginx")) is True
    assert _is_transient_error(Exception("504 Gateway Timeout")) is True
    assert _is_transient_error(Exception("Internal Server Error: 500")) is True
    assert _is_transient_error(Exception("RemoteDisconnected: Server closed connection")) is True

    # 不可重试硬性错误
    assert _is_transient_error(Exception("401 Unauthorized token")) is False
    assert _is_transient_error(Exception("403 Forbidden access")) is False
    assert _is_transient_error(Exception("context_length_exceeded maximum tokens")) is False


def test_mindmap_render_draft() -> None:
    """验证思维导图零 LLM 纯代码直接出稿。"""
    state = {
        "lines": {
            "mindmap": {
                "draft": {
                    "title": "项目复盘会",
                    "outline": "# 根节点\n## 主分支1\n- 叶子节点",
                }
            }
        }
    }
    rendered = MindmapRender.render_draft(state)
    assert "# 根节点" in rendered
    assert "## 主分支1" in rendered
    assert "- 叶子节点" in rendered


def test_minutes_trace_render_draft() -> None:
    """验证溯源纪要零 LLM 纯代码直接出稿。"""
    state = {
        "lines": {
            "minutes_trace": {
                "draft": {
                    "minutes_md": "# 业务对齐会议\n\n## 议题一\n- 方案落地",
                }
            }
        }
    }
    rendered = MinutesTraceRender.render_draft(state)
    assert rendered == "# 业务对齐会议\n\n## 议题一\n- 方案落地"


def test_minutes_styles_render_draft() -> None:
    """验证多样式纪要零 LLM 纯代码直接出稿。"""
    state = {
        "lines": {
            "minutes_styles": {
                "draft": {
                    "title": "敏捷对齐周会",
                    "summary": "本周全员完成需求对齐与联调。",
                    "sections": [
                        {"title": "对齐共识", "content": "- 统一接口规范；\n- 确定上线窗口。"},
                        {"title": "各方责任", "content": "- 后端张三负责接口变更；\n- 前端李四联调。"},
                    ],
                }
            }
        }
    }
    rendered = MultiStylesRender.render_draft(state)
    assert "# 敏捷对齐周会" in rendered
    assert "> **速览摘要**：本周全员完成需求对齐与联调。" in rendered
    assert "## 对齐共识" in rendered
    assert "- 统一接口规范；" in rendered
    assert "## 各方责任" in rendered
    assert "- 后端张三负责接口变更；" in rendered


def test_consensus_decision_render_draft() -> None:
    """验证共识决策零 LLM 纯代码直接出稿。"""
    state = {
        "lines": {
            "consensus_decision": {
                "draft": {
                    "summary": {"health_headline": "决策进展顺利，架构分歧已达成共识"},
                    "issues": [
                        {
                            "topic": "灰度放量比例设定",
                            "consensus_grade": "hard_alignment",
                            "accord": "首批放量5%，观察24小时指标后再扩量至20%",
                            "trigger": "保障生产稳定性",
                            "caveat": "监控报错率超过0.01%即刻回滚",
                            "trade_off": {"gain": "风险完全可控", "sacrifice": "全量发布周期延长1天"},
                        }
                    ],
                }
            }
        }
    }
    rendered = ConsensusDecisionRender.render_draft(state)
    assert "# 会议共识与因果决策分析" in rendered
    assert "决策进展顺利，架构分歧已达成共识" in rendered
    assert "**达成决议**：首批放量5%" in rendered
    assert "**约束预警**：监控报错率超过0.01%即刻回滚" in rendered
    assert "**方案权衡**：收益: 风险完全可控；代价: 全量发布周期延长1天" in rendered


class DummyEngine:
    domain_name = "meeting"
    _line_cn_names = {
        "minutes": "会议纪要",
        "consensus_decision": "共识决策",
        "minutes_styles": "多样式纪要",
        "minutes_trace": "溯源纪要",
    }
    _fallback_rules = {
        "minutes": MinutesGenerationRender,
        "consensus_decision": ConsensusDecisionRender,
        "minutes_styles": MultiStylesRender,
        "minutes_trace": MinutesTraceRender,
    }

    def __init__(self, render_obj, line_name: str = "minutes") -> None:
        setattr(self, f"{line_name}_render", render_obj)

    def _line_title(self, state: dict, line_name: str) -> str:
        return f"{self._line_cn_names.get(line_name, line_name)}输出"

    def _line_policy(self, line_name: str):
        class DummyPolicy:
            kind = "deterministic_pipeline" if line_name == "minutes_trace" else "llm_document"
            llm_render = "never" if line_name == "minutes_trace" else "always"
            extracts_structure = True
            def uses_llm_render(self, template: str) -> bool:
                if line_name == "minutes_trace":
                    return False
                return True
        return DummyPolicy()

    def _render_context(self, state: dict, line_name: str) -> str:
        return "approved render context"

    def _render_directives(self, state: dict, line_name: str) -> str:
        return ""

    def _pre_render_hook(self, state: dict, line_name: str) -> bool:
        return False

    def _post_render_hook(self, state: dict, line_name: str) -> None:
        pass

    def _domain_fallback_text(self, state: dict, line_name: str, rules):
        return "fallback generic text", None


@pytest.mark.anyio
async def test_produce_line_first_insurance_retry_success() -> None:
    """验证第一道保险：瞬时超时故障触发单步重试，且第2次调用成功。"""
    call_count = 0

    class TransientFailThenSucceedRender:
        async def stream(self, context: str, template: str = "", **kwargs) -> AsyncIterator[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("Gateway ReadTimeout")
            yield "# 成功渲染正文"

    engine = DummyEngine(TransientFailThenSucceedRender(), "minutes")
    state = {
        "lines": {
            "minutes": {
                "draft": {"headline": "测试草稿"},
            }
        },
        "templates": {"minutes": ""},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "minutes", state, queue)

    assert call_count == 2
    item = await queue.get()
    assert item["type"] == "chunk"
    assert item["text"] == "# 成功渲染正文"
    assert state["lines"]["minutes"]["rendered"] == "# 成功渲染正文"
    assert state["lines"]["minutes"]["fill_mode"] == "retry_success"
    assert not state.get("quality_degraded")


@pytest.mark.anyio
async def test_produce_line_second_insurance_zero_llm_fallback() -> None:
    """验证第二道保险：大模型集群持续报错时，0 毫秒纯代码保底出稿，交付高保真结构化正文。"""
    class AlwaysFailRender:
        async def run(self, context: str, template: str = "", **kwargs) -> str:
            raise ConnectionResetError("Connection refused by upstream 500")

        @staticmethod
        def render_draft(state: dict) -> str:
            return MinutesGenerationRender.render_draft(state)

    engine = DummyEngine(AlwaysFailRender(), "minutes")
    state = {
        "objective_perspective": True,
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "核心架构评审会",
                    "executive_summary": ["全员确认采用分布式存储方案。"],
                    "key_decisions": ["封板日期定为10月30日"],
                    "personally_relevant_points": ["架构师负责压测"],
                    "risks_and_blockers": ["机房带宽受限"],
                    "unresolved_questions": ["容灾备机待采购"],
                }
            }
        },
        "templates": {"minutes": "[正文占位符]"},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "minutes", state, queue)

    item = await queue.get()
    assert item["type"] == "chunk"
    assert "# 核心架构评审会" in item["text"]
    assert "## 关键决策" in item["text"]
    assert "- 封板日期定为10月30日" in item["text"]
    assert "## 风险与阻塞" in item["text"]
    assert "- 机房带宽受限" in item["text"]

    min_state = state["lines"]["minutes"]
    assert min_state["rendered"] == item["text"]
    assert min_state["degraded"] is True
    assert min_state["quality_warning"] == "（服务瞬时繁忙，已启用高保真结构化呈现）"
    assert state["quality_degraded"] is True
    assert min_state["fill_mode"] == "deterministic_draft"


@pytest.mark.anyio
async def test_produce_line_minutes_styles_zero_llm_fallback() -> None:
    """验证多样式纪要在渲染报错时通过 render_draft 纯代码保底出稿。"""
    class AlwaysFailStylesRender:
        async def stream(self, context: str, template: str = "", **kwargs) -> AsyncIterator[str]:
            raise TimeoutError("LLM timed out")
            yield ""

        @staticmethod
        def render_draft(state: dict) -> str:
            return MultiStylesRender.render_draft(state)

    engine = DummyEngine(AlwaysFailStylesRender(), "minutes_styles")
    state = {
        "lines": {
            "minutes_styles": {
                "draft": {
                    "title": "项目复盘纪要",
                    "summary": "全流程复盘完成，明确改进对策。",
                    "sections": [
                        {"title": "现状说明", "content": "- 线上缺陷数环比下降15%。"},
                        {"title": "改进措施", "content": "- 补充自动化集成测试。"},
                    ],
                }
            }
        },
        "templates": {"minutes_styles": ""},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "minutes_styles", state, queue)

    item = await queue.get()
    assert item["type"] == "chunk"
    assert "# 项目复盘纪要" in item["text"]
    assert "> **速览摘要**：全流程复盘完成，明确改进对策。" in item["text"]
    assert "## 现状说明" in item["text"]
    assert "- 线上缺陷数环比下降15%。" in item["text"]

    line_st = state["lines"]["minutes_styles"]
    assert line_st["rendered"] == item["text"]
    assert line_st["degraded"] is True
    assert line_st["quality_warning"] == "（服务瞬时繁忙，已启用高保真结构化呈现）"
    assert line_st["fill_mode"] == "deterministic_draft"


@pytest.mark.anyio
async def test_produce_line_consensus_decision_zero_llm_fallback() -> None:
    """验证共识决策在渲染报错时通过 render_draft 纯代码保底出稿。"""
    class AlwaysFailConsensusRender:
        async def stream(self, context: str, template: str = "", **kwargs) -> AsyncIterator[str]:
            raise TimeoutError("LLM timed out")
            yield ""

        @staticmethod
        def render_draft(state: dict) -> str:
            return ConsensusDecisionRender.render_draft(state)

    engine = DummyEngine(AlwaysFailConsensusRender(), "consensus_decision")
    state = {
        "lines": {
            "consensus_decision": {
                "draft": {
                    "summary": {"health_headline": "全会共识高度对齐"},
                    "issues": [
                        {
                            "topic": "发布时间窗口",
                            "consensus_grade": "hard_alignment",
                            "accord": "统一于周四凌晨2点发布",
                            "trigger": "避开业务高峰",
                        }
                    ],
                }
            }
        },
        "templates": {"consensus_decision": ""},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "consensus_decision", state, queue)

    item = await queue.get()
    assert item["type"] == "chunk"
    assert "# 会议共识与因果决策分析" in item["text"]
    assert "全会共识高度对齐" in item["text"]
    assert "发布时间窗口【一致赞成】" in item["text"]
    assert "**达成决议**：统一于周四凌晨2点发布" in item["text"]

    line_st = state["lines"]["consensus_decision"]
    assert line_st["rendered"] == item["text"]
    assert line_st["degraded"] is True
    assert line_st["quality_warning"] == "（服务瞬时繁忙，已启用高保真结构化呈现）"
    assert line_st["fill_mode"] == "deterministic_draft"


@pytest.mark.anyio
async def test_produce_line_minutes_trace_prioritizes_materialize() -> None:
    """验证溯源纪要正常执行时优先走 materialize 对齐与落钉，而不是被 render_draft 短路。"""
    class TraceRenderWithBoth:
        async def materialize(self, approved_context: str, template: str = "") -> str:
            return "# 溯源纪要\n- 关键决策已落实###[【keypoint: 重点事项】]"

        @staticmethod
        def render_draft(state: dict) -> str:
            return MinutesTraceRender.render_draft(state)

    render_obj = TraceRenderWithBoth()
    engine = DummyEngine(render_obj, "minutes_trace")
    state = {
        "lines": {
            "minutes_trace": {
                "draft": {
                    "minutes_md": "# 溯源纪要\n- 关键决策已落实",
                }
            }
        },
        "templates": {"minutes_trace": ""},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "minutes_trace", state, queue)

    item = await queue.get()
    assert item["type"] == "chunk"
    assert "###[【keypoint: 重点事项】]" in item["text"]
    assert state["lines"]["minutes_trace"]["fill_mode"] == "materialize"
    assert state["lines"]["minutes_trace"].get("degraded") is not True


@pytest.mark.anyio
async def test_produce_line_minutes_trace_fallback_when_materialize_fails() -> None:
    """验证溯源纪要当 materialize 发生不可恢复异常时，平滑降级为 render_draft 纯代码出稿。"""
    class FailingTraceRender:
        async def materialize(self, approved_context: str, template: str = "") -> str:
            raise RuntimeError("Corrupted alignment metadata")

        @staticmethod
        def render_draft(state: dict) -> str:
            return MinutesTraceRender.render_draft(state)

    render_obj = FailingTraceRender()
    engine = DummyEngine(render_obj, "minutes_trace")
    state = {
        "lines": {
            "minutes_trace": {
                "draft": {
                    "minutes_md": "# 溯源纪要\n- 关键决策已落实",
                }
            }
        },
        "templates": {"minutes_trace": ""},
    }
    queue = asyncio.Queue()

    await produce_line(engine, "minutes_trace", state, queue)

    item = await queue.get()
    assert item["type"] == "chunk"
    assert item["text"] == "# 溯源纪要\n- 关键决策已落实"
    assert state["lines"]["minutes_trace"]["degraded"] is True
    assert state["lines"]["minutes_trace"]["quality_warning"] == "（服务瞬时繁忙，已启用高保真结构化呈现）"
    assert state["lines"]["minutes_trace"]["fill_mode"] == "deterministic_draft"


