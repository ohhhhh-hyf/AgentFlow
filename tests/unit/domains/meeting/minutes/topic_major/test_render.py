"""tests/unit/meeting/test_minutes_topic_major_render.py -- topic_major 渲染接线。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from core.runtime.render import _render_run
from core.templates.router import split_template_layout
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_render import (
    MinutesGenerationRender,
    cleanup_empty_topic_sections,
    render_fallback_topic_major,
)


def _team_template() -> str:
    path = (
        Path(__file__).resolve().parents[6]
        / "resources"
        / "agenda_templates"
        / "zh"
        / "team_meeting.md"
    )
    clean, _mode, _container = split_template_layout(path.read_text(encoding="utf-8"))
    return clean


def _topic_draft() -> dict:
    return {
        "headline": "团队例会纪要",
        "overview": "本次例会围绕接口联调展开。",
        "topics": [
            {
                "topic_name": "接口联调",
                "topic_summary": ["方案已确认"],
                "decisions": ["按 B 方案执行"],
                "actions": ["张三周五前完成联调报告"],
                "risks": ["依赖外部团队"],
                "open_questions": ["上线时间待确认"],
            }
        ],
        "history_comparison": [],
    }


class _FakeRenderClient:
    def __init__(self) -> None:
        self.prompt = ""
        self.user = ""
        self.kwargs: dict = {}

    async def text(self, prompt, user, **kwargs):
        self.prompt = prompt
        self.user = user
        self.kwargs = kwargs
        return "# 渲染结果"

    async def stream_text(self, prompt, user, **kwargs):
        self.prompt = prompt
        self.user = user
        self.kwargs = kwargs
        yield "# 渲染结果"


def test_render_prompt_selected_by_layout() -> None:
    template = _team_template()
    context = "已批准会议纪要草稿：\n{}"

    topic_prompt, _topic_user = MinutesGenerationRender._prompt_and_user(
        context, template, view="agenda_objective", layout="topic_major"
    )
    column_prompt, _column_user = MinutesGenerationRender._prompt_and_user(
        context, template, view="agenda_objective", layout="column_major"
    )

    assert "议题容器类栏目" in topic_prompt
    assert "topic_summary" in topic_prompt
    assert "executive_summary" not in topic_prompt
    assert "不得将分组拆成平行列表项" in topic_prompt
    assert "例如" not in topic_prompt
    assert "bullet" not in topic_prompt.lower()
    assert "执行准绳" not in topic_prompt  # 渲染 prompt 不混生成红线
    assert column_prompt != topic_prompt


def test_team_template_declares_fourth_level_sections() -> None:
    template = _team_template()

    assert "#### 工作进展" in template
    assert "#### 落实安排" in template
    assert "#### 未决风险" in template
    assert "**子主题**：" in template
    assert "不设固定组数和条数" in template


def test_render_run_passes_layout_to_prompt() -> None:
    client = _FakeRenderClient()
    render = MinutesGenerationRender(client)

    text = asyncio.run(
        render.run(
            "已批准会议纪要草稿：\n{}",
            _team_template(),
            view="agenda_objective",
            layout="topic_major",
        )
    )

    assert text == "# 渲染结果"
    assert "议题容器类栏目" in client.prompt
    assert "topic_summary" in client.prompt
    assert "layout" not in client.kwargs


def test_render_stream_passes_layout_to_prompt() -> None:
    client = _FakeRenderClient()
    render = MinutesGenerationRender(client)

    async def _collect() -> list[str]:
        return [
            chunk
            async for chunk in render.stream(
                "已批准会议纪要草稿：\n{}",
                _team_template(),
                view="agenda_objective",
                layout="topic_major",
            )
        ]

    chunks = asyncio.run(_collect())

    assert chunks == ["# 渲染结果"]
    assert "议题容器类栏目" in client.prompt
    assert "topic_summary" in client.prompt


def test_render_context_injects_container_and_topic_draft() -> None:
    state = {
        "line_layouts": {"minutes": "topic_major"},
        "line_containers": {"minutes": "议题梳理"},
        "has_valid_agenda": True,
        "valid_agendas": [],
        "transcript": "短会",
        "user": {"perspective": "objective"},
        "objective_perspective": True,
        "meeting_understanding": {},
        "perspective_profile": {},
        "line_extra": {},
        "templates": {},
        "lang": "zh",
        "line_views": {"minutes": "agenda_objective"},
        "lines": {
            "minutes": {
                "draft": _topic_draft(),
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }

    context = _Nodes()._render_context(state, "minutes")

    assert "议题容器：\n议题梳理" in context
    assert "topic_summary" in context
    assert "interface" not in context
    assert "executive_summary" not in context


def test_render_draft_topic_major_fallback() -> None:
    state = {
        "lang": "zh",
        "lines": {"minutes": {"draft": _topic_draft()}},
    }

    text = MinutesGenerationRender.render_draft(state)

    assert "# 团队例会纪要" in text
    assert "## 全文摘要" in text
    assert "## 议题梳理" in text
    assert "### 一. 接口联调" in text
    assert "**工作进展**" in text
    assert "**落实安排**" in text
    assert "**未决风险**" in text
    assert "张三周五前完成联调报告" in text
    assert "上线时间待确认" in text


def test_render_fallback_topic_major_empty() -> None:
    assert render_fallback_topic_major({}) == "请直接参考会议原文。"


def test_render_runtime_passes_layout_to_run() -> None:
    captured: dict = {}

    class _Render:
        async def run(self, context, template, *, view=None, layout=None):
            captured["view"] = view
            captured["layout"] = layout
            return "ok"

    result = asyncio.run(
        _render_run(
            _Render(),
            "ctx",
            "tpl",
            None,
            view="agenda_objective",
            layout="topic_major",
        )
    )

    assert result == "ok"
    assert captured == {"view": "agenda_objective", "layout": "topic_major"}


def test_cleanup_empty_topic_sections() -> None:
    text = """### 一. 接口联调
**工作进展**
- 方案已确认
**落实安排**

**未决风险**
- 上线时间待确认
"""

    cleaned = cleanup_empty_topic_sections(text)

    assert "**工作进展**" in cleaned
    assert "**落实安排**" not in cleaned
    assert "**未决风险**" in cleaned
    assert "上线时间待确认" in cleaned


def test_render_run_cleans_empty_topic_sections() -> None:
    class _Client:
        async def text(self, prompt, user, **kwargs):
            return "### 一. 接口联调\n**工作进展**\n- 方案已确认\n**落实安排**\n\n**未决风险**\n- 待确认\n"

    render = MinutesGenerationRender(_Client())
    text = asyncio.run(
        render.run(
            "已批准会议纪要草稿：\n{}",
            _team_template(),
            view="agenda_objective",
            layout="topic_major",
        )
    )

    assert "**落实安排**" not in text
    assert "**工作进展**" in text
    assert "**未决风险**" in text
