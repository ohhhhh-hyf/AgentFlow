"""tests/meeting/test_minutes_fast_render.py
验证 minutes 零 LLM 快速渲染：
1. render_draft 纯 Python 格式化（客观模式、个人模式、独占组名行、标题动态化）
2. LinePolicy.uses_llm_render 对默认模板与自定义模板的分流识别
3. produce_line 零 LLM 调用及内存/历史对照透传
"""
from __future__ import annotations

import asyncio
import pytest

from core.runtime.kinds import LinePolicy
from core.runtime.render import produce_line
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender


def test_render_draft_objective() -> None:
    """验证客观视角下 render_draft 正常组装标题与各栏目。"""
    state = {
        "objective_perspective": True,
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "Q3规划会",
                    "executive_summary": ["本周完成系统上线与联调。", "下周推进全链路压测。"],
                    "key_decisions": ["全员统一采用方案A", "上线死线定为周五"],
                    "personally_relevant_points": ["张三负责后端接口", "李四负责前端接入"],
                    "risks_and_blockers": ["第三方接口响应偏慢"],
                    "unresolved_questions": ["容灾机房预算待批复"],
                }
            }
        },
    }
    rendered = MinutesGenerationRender.render_draft(state)
    assert rendered.startswith("# Q3规划会")
    assert "## 全文摘要" in rendered
    assert "本周完成系统上线与联调。" in rendered
    assert "## 关键决策" in rendered
    assert "- 全员统一采用方案A" in rendered
    assert "## 全员执行要点" in rendered
    assert "- 张三负责后端接口" in rendered
    assert "## 风险与阻塞" in rendered
    assert "- 第三方接口响应偏慢" in rendered
    assert "## 未决问题" in rendered
    assert "- 容灾机房预算待批复" in rendered


def test_render_draft_personal() -> None:
    """验证个人视角下标题动态绑定与组名行独占排版。"""
    state = {
        "objective_perspective": False,
        "user": {"name": "张三", "perspective": "personal"},
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "",
                    "executive_summary": ["围绕张三主导的网关模块展开，明确本周交付。"],
                    "key_decisions": [
                        "**与我相关**：",
                        "完成鉴权插件升级",
                        "**姓名**：",
                        "李四负责配合压测",
                    ],
                    "personally_relevant_points": [
                        "**与我相关**：",
                        "今天先把配置改完，明天给结论",
                        "**重点协同**：",
                        "王五周五前提供测试用例",
                    ],
                    "risks_and_blockers": [
                        "**与我相关**：",
                        "配置权限尚未下发，可能延期半天",
                    ],
                }
            }
        },
    }
    rendered = MinutesGenerationRender.render_draft(state)
    # 动态推导为张三视角标题
    assert rendered.startswith("# 张三视角会议纪要")
    assert "## 职责相关事项" in rendered
    # 组名行独占且不带 "- " 前缀
    assert "\n**与我相关**：\n- 今天先把配置改完，明天给结论" in rendered
    assert "\n**重点协同**：\n- 王五周五前提供测试用例" in rendered
    assert "\n**与我相关**：\n- 完成鉴权插件升级" in rendered


def test_line_policy_uses_llm_render_routing() -> None:
    """验证 LinePolicy 对通用/个人默认模板及自定义模板的判定。"""
    policy = LinePolicy(kind="llm_document", llm_render="if_template")

    # 1. 无模板或布尔值
    assert policy.uses_llm_render("") is False
    assert policy.uses_llm_render(False) is False
    assert policy.uses_llm_render(True) is True

    # 2. 默认模板名或内容（纯 Python 装配，零 LLM）
    assert policy.uses_llm_render("general_minutes") is False
    assert policy.uses_llm_render("personal_minutes") is False
    assert policy.uses_llm_render("通用纪要") is False
    assert policy.uses_llm_render("个人视角纪要") is False
    assert policy.uses_llm_render("# 通用纪要\n\n## [全文摘要]...") is False
    assert policy.uses_llm_render("# 个人视角纪要\n\n## [会议概况]...") is False

    # 3. 自定义模板（需调 LLM）
    assert policy.uses_llm_render("project_progress") is True
    assert policy.uses_llm_render("# 项目进度会\n\n## [项目概况]...") is True


def test_produce_line_minutes_fast_path_zero_llm() -> None:
    """验证 produce_line 在 minutes 线走快速短路分支，零 LLM 调用且保留历史记忆对照。"""
    class MockMinutesRender:
        def __init__(self) -> None:
            self.stream_called = 0
            self.run_called = 0

        async def run(self, *args, **kwargs) -> str:
            self.run_called += 1
            return "llm_rendered"

        async def stream(self, *args, **kwargs):
            self.stream_called += 1
            yield "llm_chunk"

        @staticmethod
        def render_draft(state: dict) -> str:
            return MinutesGenerationRender.render_draft(state)

    mock_render = MockMinutesRender()

    received_comparison = []

    def mock_apply_citations(text: str, context: str, *, comparison=None) -> str:
        nonlocal received_comparison
        received_comparison = list(comparison or [])
        return text + "\n\n## 历史记忆引用\n- 记忆1"

    class MockHooks:
        apply_citations = staticmethod(mock_apply_citations)
        compact_plain = None

    class MockEngine:
        domain_name = "meeting"

        def __init__(self) -> None:
            self.minutes_render = mock_render
            self._line_cn_names = {"minutes": "纪要"}

        def _line_policy(self, line_name: str) -> LinePolicy:
            return LinePolicy(kind="llm_document", llm_render="if_template")

        def _pre_render_hook(self, state: dict, line_name: str) -> bool:
            return False

        def _post_render_hook(self, state: dict, line_name: str) -> None:
            pass

        def _line_title(self, state: dict, line_name: str) -> str:
            return "纪要"

        def _render_context(self, state: dict, line_name: str) -> str:
            raise AssertionError("快速分支不应调用重度 _render_context 拼装原文")

    async def _run() -> None:
        # 猴子补丁 hooks_for
        import core.runner.hooks as dh
        orig_hooks_for = dh.hooks_for
        dh.hooks_for = lambda domain: MockHooks()

        try:
            engine = MockEngine()
            state = {
                "objective_perspective": True,
                "templates": {"minutes": "# 通用纪要\n\n## [全文摘要]"},
                "lines": {
                    "minutes": {
                        "draft": {
                            "headline": "测试周会",
                            "executive_summary": ["周会平稳推进。"],
                            "history_comparison": ["延续事项（自第1场）：保持原有排期"],
                        },
                        "memory_context": "【会议记忆】\n- 记忆1：上一场决议 (meeting_id=1)",
                    }
                },
            }
            queue = asyncio.Queue()
            await produce_line(engine, "minutes", state, queue)

            # 验证 LLM 未被调用（零 LLM 调用）
            assert mock_render.stream_called == 0
            assert mock_render.run_called == 0

            # 验证 state 中的 rendered 产物
            line_res = state["lines"]["minutes"]
            assert line_res["fill_mode"] == "draft"
            rendered_text = line_res["rendered"]
            assert "# 测试周会" in rendered_text
            # 真实 apply_citations 成功挂载历史对照
            assert "## 历史对照" in rendered_text
            assert "- 延续事项（自第1场）：保持原有排期" in rendered_text

        finally:
            dh.hooks_for = orig_hooks_for

    asyncio.run(_run())


def test_produce_line_template_with_memory_citations(caplog) -> None:
    """验证 produce_line 在自定义模板模式下，LLM 渲染后能正确追加历史对照与记忆引用且无任何异常 warning。"""
    class MockMinutesRender:
        def __init__(self) -> None:
            self.stream_called = 0

        async def stream(self, context: str, template: str = "", **kwargs):
            self.stream_called += 1
            # 模拟 LLM 流式输出自定义模板正文
            yield "### 自定义专项纪要\n\n- 重点议题已达成共识并落实排期。"

    mock_render = MockMinutesRender()
    received_args = {}

    def mock_apply_citations(text: str, context: str, *, comparison=None, candidate_items=None) -> str:
        received_args["text"] = text
        received_args["context"] = context
        received_args["comparison"] = list(comparison or [])
        received_args["candidate_items"] = candidate_items
        out = text
        if comparison:
            out += "\n\n## 往期沿革\n" + "\n".join(f"- {c}" for c in comparison)
        return out

    class MockHooks:
        apply_citations = staticmethod(mock_apply_citations)
        compact_plain = None

    class MockEngine:
        domain_name = "meeting"

        def __init__(self) -> None:
            self.minutes_render = mock_render
            self._line_cn_names = {"minutes": "纪要"}

        def _line_policy(self, line_name: str) -> LinePolicy:
            return LinePolicy(kind="llm_document", llm_render="if_template")

        def _pre_render_hook(self, state: dict, line_name: str) -> bool:
            return False

        def _post_render_hook(self, state: dict, line_name: str) -> None:
            pass

        def _line_title(self, state: dict, line_name: str) -> str:
            return "纪要"

        def _render_context(self, state: dict, line_name: str) -> str:
            return "这是会议上下文正文。"

        def _render_directives(self, state: dict, line_name: str) -> str:
            return ""

    async def _run() -> None:
        import core.runtime.render as render_mod
        orig_hooks_for = render_mod.hooks_for
        render_mod.hooks_for = lambda domain: MockHooks()

        try:
            engine = MockEngine()
            # 自定义模板触发 uses_llm_render=True
            custom_template = "### 自定义专项纪要\n\n{{body}}"
            state = {
                "objective_perspective": True,
                "templates": {"minutes": custom_template},
                "lines": {
                    "minutes": {
                        "draft": {
                            "headline": "专项评审会",
                            "history_comparison": ["往期议题：鉴权改造方案已在第1场确认"],
                        },
                        "memory_context": "【会议记忆】\n- 记忆条目 (id=1)",
                        "memory_items": [{"id": 1, "text": "鉴权改造"}],
                    }
                },
            }
            queue = asyncio.Queue()
            import logging
            with caplog.at_level(logging.WARNING):
                await produce_line(engine, "minutes", state, queue)

            # 1. 验证 LLM 流式被正常调用
            assert mock_render.stream_called == 1

            # 2. 验证 apply_citations 接收到了正确的 comparison 与 candidate_items
            assert received_args.get("comparison") == ["往期议题：鉴权改造方案已在第1场确认"]
            assert received_args.get("candidate_items") == [{"id": 1, "text": "鉴权改造"}]
            assert "【会议记忆】" in received_args.get("context", "")

            # 3. 验证渲染产物及队列事件成功包含历史对照
            line_st = state["lines"]["minutes"]
            rendered_text = line_st["rendered"]
            assert "### 自定义专项纪要" in rendered_text
            assert "## 往期沿革" in rendered_text
            assert "往期议题：鉴权改造方案已在第1场确认" in rendered_text

            # 4. 验证没有任何 memory citation failed 警告
            citation_warnings = [
                rec.message for rec in caplog.records
                if "memory citation failed" in rec.message
            ]
            assert len(citation_warnings) == 0, f"发现意外告警: {citation_warnings}"

        finally:
            render_mod.hooks_for = orig_hooks_for

    asyncio.run(_run())


def test_produce_line_template_with_real_meeting_hooks(caplog) -> None:
    """验证真实 apply_citations 钩子在自定义模板模式下无缝挂载历史对照且零 warning。"""
    class MockMinutesRender:
        def __init__(self) -> None:
            self.stream_called = 0

        async def stream(self, context: str, template: str = "", **kwargs):
            self.stream_called += 1
            yield "### 模板纪要正文\n\n- 鉴权改造模块已完成评审并合入主干。"

    mock_render = MockMinutesRender()

    class MockEngine:
        domain_name = "meeting"

        def __init__(self) -> None:
            self.minutes_render = mock_render
            self._line_cn_names = {"minutes": "纪要"}

        def _line_policy(self, line_name: str) -> LinePolicy:
            return LinePolicy(kind="llm_document", llm_render="if_template")

        def _pre_render_hook(self, state: dict, line_name: str) -> bool:
            return False

        def _post_render_hook(self, state: dict, line_name: str) -> None:
            pass

        def _line_title(self, state: dict, line_name: str) -> str:
            return "纪要"

        def _render_context(self, state: dict, line_name: str) -> str:
            return "这是会议上下文正文。"

        def _render_directives(self, state: dict, line_name: str) -> str:
            return ""

    async def _run() -> None:
        engine = MockEngine()
        custom_template = "### 模板纪要正文\n\n{{body}}"
        state = {
            "objective_perspective": True,
            "templates": {"minutes": custom_template},
            "lines": {
                "minutes": {
                    "draft": {
                        "headline": "架构升级会",
                        "history_comparison": ["架构决策（自第1场）：统一采用Token网关鉴权"],
                    },
                    "memory_context": "【会议记忆】\n【历史决策】\n- 架构决策 (meeting_id=1)",
                }
            },
        }
        queue = asyncio.Queue()
        import logging
        with caplog.at_level(logging.WARNING):
            await produce_line(engine, "minutes", state, queue)

        assert mock_render.stream_called == 1
        line_st = state["lines"]["minutes"]
        rendered_text = line_st["rendered"]
        assert "### 模板纪要正文" in rendered_text
        # 真实 meeting hooks 会生成 ## 历史对照
        assert "## 历史对照" in rendered_text
        assert "- 架构决策（自第1场）：统一采用Token网关鉴权" in rendered_text

        citation_warnings = [
            rec.message for rec in caplog.records
            if "memory citation failed" in rec.message
        ]
        assert len(citation_warnings) == 0, f"发现意外告警: {citation_warnings}"

    asyncio.run(_run())

