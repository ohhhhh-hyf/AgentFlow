"""minutes 兜底渲染：7 字段 → 通用纪要栏目的确定性映射。"""
from __future__ import annotations

from domains.meeting.tasks.minutes.steps.minutes_render import (
    MinutesGenerationRender,
    render_fallback_minutes,
)


def test_render_fallback_minutes_maps_seven_fields() -> None:
    draft = {
        "headline": "架构同步会",
        "executive_summary": [
            "本次会议聚焦网关重构与发布计划。",
            "### 一. 网关注册\n- 注册链路时延降到 120ms。",
            "### 二. 发布计划\n- 十一月完成测试，十二月上线。",
        ],
        "key_decisions": ["采用方案A", "上线死线定为周五"],
        "personally_relevant_points": ["张三负责网关接口", "李四负责前端接入"],
        "risks_and_blockers": ["第三方接口响应偏慢"],
        "unresolved_questions": ["容灾机房预算待批复"],
        "history_comparison": ["延续事项：保持原有排期"],
    }

    rendered = render_fallback_minutes(draft, objective=True)

    # 标题与栏目齐全
    assert rendered.startswith("# 架构同步会")
    for heading in (
        "## 全文摘要",
        "## 要点梳理",
        "## 关键决策",
        "## 全员执行要点",
        "## 风险与阻塞",
        "## 未决问题",
        "## 与历史对比",
    ):
        assert heading in rendered

    # 第一项摘要进「全文摘要」，后续议题进「要点梳理」
    assert "本次会议聚焦网关重构与发布计划。" in rendered
    assert rendered.index("## 全文摘要") < rendered.index("## 要点梳理")
    assert "### 一. 网关注册" in rendered
    assert "### 二. 发布计划" in rendered
    assert "注册链路时延降到 120ms。" in rendered
    assert "十一月完成测试，十二月上线。" in rendered

    # 其余字段各归各栏
    assert "- 采用方案A" in rendered
    assert "- 张三负责网关接口" in rendered
    assert "- 第三方接口响应偏慢" in rendered
    assert "- 容灾机房预算待批复" in rendered
    assert "- 延续事项：保持原有排期" in rendered

    # 全文字段顺序稳定
    order = [
        "## 全文摘要",
        "## 要点梳理",
        "## 关键决策",
        "## 全员执行要点",
        "## 风险与阻塞",
        "## 未决问题",
        "## 与历史对比",
    ]
    positions = [rendered.index(h) for h in order]
    assert positions == sorted(positions)


def test_render_fallback_minutes_single_summary_has_no_points_section() -> None:
    draft = {
        "headline": "周会",
        "executive_summary": ["本周进度正常。"],
        "key_decisions": ["继续按计划推进"],
    }

    rendered = render_fallback_minutes(draft, objective=True)

    assert "## 全文摘要" in rendered
    assert "## 要点梳理" not in rendered
    assert "## 关键决策" in rendered


def test_render_fallback_minutes_omits_empty_sections() -> None:
    draft = {
        "headline": "周会",
        "executive_summary": ["本周进度正常。"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }

    rendered = render_fallback_minutes(draft, objective=True)

    assert "## 关键决策" not in rendered
    assert "## 全员执行要点" not in rendered
    assert "## 风险与阻塞" not in rendered
    assert "## 未决问题" not in rendered
    assert "## 与历史对比" not in rendered


def test_render_fallback_minutes_empty_draft_message() -> None:
    assert render_fallback_minutes({}) == "请直接参考会议原文。"
    assert render_fallback_minutes({}, is_en=True) == (
        "Please refer directly to the meeting transcript."
    )

    # 有标题但七个字段全空：保留标题，正文给兜底提示
    rendered = render_fallback_minutes({"headline": "空会"}, objective=True)
    assert rendered.startswith("# 空会")
    assert "请直接参考会议原文。" in rendered


def test_render_fallback_minutes_personal_headings() -> None:
    draft = {
        "headline": "",
        "executive_summary": ["围绕张三负责的网关模块展开。"],
        "personally_relevant_points": ["今天先把配置改完"],
        "risks_and_blockers": ["配置权限尚未下发"],
    }

    rendered = render_fallback_minutes(
        draft,
        objective=False,
        is_personal=True,
        user_name="张三",
    )

    assert rendered.startswith("# 张三视角会议纪要")
    assert "## 职责相关事项" in rendered
    assert "## 全员执行要点" not in rendered
    assert "- 今天先把配置改完" in rendered
    assert "- 配置权限尚未下发" in rendered


def test_render_fallback_minutes_english_headings() -> None:
    draft = {
        "headline": "AI Architecture Sync",
        "executive_summary": [
            "Aligned on the multi-agent protocol.",
            "### I. Gateway\n- Latency reduced to 120ms.",
        ],
        "key_decisions": ["Adopt slot assembly."],
        "personally_relevant_points": ["Alice delivers tests by EOD."],
        "risks_and_blockers": ["High token consumption."],
        "unresolved_questions": ["English draft evaluation metrics."],
        "history_comparison": ["Continue the previous schedule."],
    }

    rendered = render_fallback_minutes(draft, objective=True, is_en=True)

    for heading in (
        "## Executive Summary",
        "## Key Discussion Points",
        "## Key Decisions",
        "## Action Items",
        "## Risks & Blockers",
        "## Open Questions",
        "## Historical Comparison",
    ):
        assert heading in rendered
    assert not any("一" <= c <= "鿿" for c in rendered)


def test_render_draft_uses_fallback_layout_for_agenda_blocks() -> None:
    state = {
        "objective_perspective": True,
        "lang": "zh",
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "议题纪要",
                    "executive_summary": [
                        "全场概览。",
                        "### 一. Agent长期记忆\n- 需要解决长期记忆问题。",
                        "### 二. 智能体RSI\n- 讨论递归自演进。",
                    ],
                    "key_decisions": ["优先推进长期记忆。"],
                    "personally_relevant_points": ["王海涛两周内给选型。"],
                    "risks_and_blockers": ["训练卡不足。"],
                    "unresolved_questions": ["RSI评测口径未统一。"],
                    "history_comparison": [],
                }
            }
        },
    }

    rendered = MinutesGenerationRender.render_draft(state)

    assert "## 全文摘要\n\n全场概览。" in rendered
    assert "## 要点梳理" in rendered
    assert "### 一. Agent长期记忆" in rendered
    assert "### 二. 智能体RSI" in rendered
    assert rendered.index("## 要点梳理") < rendered.index("### 一. Agent长期记忆")
    assert "## 关键决策" in rendered
    assert "## 全员执行要点" in rendered
    assert "## 风险与阻塞" in rendered
    assert "## 未决问题" in rendered
