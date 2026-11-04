"""Step 8：个人审核 / 渲染上下文清理测试。"""
from __future__ import annotations

from domains.meeting.orchestrator import _Nodes


def _state(*, lang: str = "zh") -> dict:
    return {
        "user": {"name": "申家坤", "name_aliases": ["家坤"]},
        "objective_perspective": False,
        "has_valid_agenda": False,
        "lang": lang,
        "transcript": "申家坤 10:00: 负责压测。",
        "meeting_understanding": {
            "meeting_brief": "demo 评审",
            "meeting_purpose": "确认上线",
            "speakers": [{"name": "申家坤"}],
            "session_segments": [{"segment_title": "压测"}],
            "decisions": ["周五上线"],
            "risk": ["显存不足"],
            "open_questions": ["测试范围"],
        },
        "personal_perspective": {
            "confidence": "high",
            "personal_summary": "负责压测。",
            "focus_points": ["压测"],
            "possible_actions": ["周五前提交报告"],
            "collaborations": ["张工：提供环境"],
            "concerns": ["显存不足"],
            "data_gaps": ["缺少驱动"],
            "focus_risks": ["上线窗口"],
            "open_questions": ["确认范围"],
        },
        "perspective_profile": {"personal_summary": "旧视角模型"},
        "user_hits_block": "【本用户命中】\n- 申家坤：压测",
        "user_radar_block": "【重点关注雷达】\n- 申家坤",
        "line_extra": {"minutes": "旧记忆块"},
        "templates": {"minutes": "# 个人视角纪要\n## [会议概况]\n[占位]"},
        "lines": {
            "minutes": {
                "draft": {
                    "headline": "demo 评审",
                    "executive_summary": ["负责压测。"],
                    "key_decisions": ["周五上线"],
                    "personally_relevant_points": ["**本人相关**：", "周五前提交报告"],
                    "risks_and_blockers": ["**本人相关**：", "显存不足"],
                    "unresolved_questions": ["确认范围"],
                    "history_comparison": [],
                },
                "review": {"decision": "approve"},
                "revision_count": 0,
            }
        },
    }


def test_personal_render_context_only_has_draft_and_review() -> None:
    context = _Nodes()._render_context(_state(), "minutes")
    assert context.startswith("视角模式：personal")
    assert "已批准" in context
    assert "demo 评审" in context
    assert "纪要审核结论" in context
    for forbidden in (
        "用户画像",
        "会议理解",
        "【本用户命中】",
        "【重点关注雷达】",
        "会议原文",
        "篇幅预算",
        "旧记忆块",
        "旧视角模型",
    ):
        assert forbidden not in context, forbidden


def test_personal_render_context_keeps_english_language_block() -> None:
    context = _Nodes()._render_context(_state(lang="en"), "minutes")
    assert "输出语种要求：\n英文（English）" in context
    assert "用户画像" not in context


def test_personal_supervisor_context_drops_hit_radar_and_old_perspective() -> None:
    context = _Nodes()._supervisor_context(_state(), "minutes")
    assert "纪要草稿：" in context
    assert "原文（最高事实来源）：" in context
    for forbidden in (
        "用户画像",
        "用户视角模型",
        "【本用户命中】",
        "【重点关注雷达】",
        "旧视角模型",
    ):
        assert forbidden not in context, forbidden


def test_objective_render_context_keeps_legacy_blocks() -> None:
    state = _state()
    state["user"] = {}
    context = _Nodes()._render_context(state, "minutes")
    assert "视角模式：objective" in context
    assert "用户画像" in context
    assert "会议理解" in context
