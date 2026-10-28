"""Step 5：所有内置议题模板的生成/渲染解耦矩阵测试。"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.config import agenda_template_dir, resolve_agenda_template_format
from domains.meeting.orchestrator import _Nodes
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender

CHECKLIST_TITLE = "【本轮 JSON 输出契约（唯一结构，最高优先级）】"
FOLD_CLAUSE = "模板无此类栏目时，折入结论/决议或最近相关小节"

FIELD_NAMES = (
    "headline",
    "executive_summary",
    "key_decisions",
    "personally_relevant_points",
    "risks_and_blockers",
    "unresolved_questions",
    "history_comparison",
)


def _iter_templates():
    for lang in ("zh", "en"):
        for path in sorted(agenda_template_dir(lang).glob("*.md")):
            fmt = resolve_agenda_template_format(path.stem, lang=lang)
            if fmt:
                yield lang, path.stem, fmt


def _normal_state(template: str) -> dict:
    return {
        "transcript": "张三 10:00: 本周完成联调，下周压测。",
        "objective_perspective": True,
        "templates": {"minutes": template},
        "line_extra": {},
        "meeting_understanding": {
            "meeting_brief": "周会",
            "meeting_purpose": "同步进展",
            "session_segments": [],
            "topics": [],
            "decisions": [],
            "risks": [],
            "open_questions": [],
        },
    }


def _agenda_state(template: str) -> dict:
    return {
        "transcript": "张三 10:00: 芯片良率达标。",
        "tagged_transcript": (
            "【会议开场背景与主线脉络】\n...\n\n"
            "【议题 01：芯片量产】（汇报人：张三）\n"
            "张三 10:00: 芯片良率达标。"
        ),
        "has_valid_agenda": True,
        "valid_agendas": [],
        "objective_perspective": True,
        "templates": {"minutes": template},
        "line_extra": {},
    }


def test_all_templates_are_excluded_from_generation_context() -> None:
    nodes = _Nodes()
    checked = 0
    for _lang, _stem, template in _iter_templates():
        for state in (_normal_state(template), _agenda_state(template)):
            ctx = nodes._line_shared_context(state, "minutes")
            assert "【目标样式模板】" not in ctx
            assert template.strip() not in ctx
            assert CHECKLIST_TITLE in ctx
            for field in FIELD_NAMES:
                assert field in ctx
            checked += 1
    assert checked >= 40


def test_all_templates_render_prompt_has_mapping_without_fold() -> None:
    renderer = MinutesGenerationRender(MagicMock())
    checked = 0
    for lang, _stem, template in _iter_templates():
        for ctx, view in (
            ("视角模式：objective", "objective"),
            ("议题模式：agenda_enhanced\n视角模式：objective", "agenda_objective"),
        ):
            prompt, user = renderer._prompt_and_user(
                ctx, template, view=view, lang=lang
            )
            assert "key_decisions" in prompt
            assert "personally_relevant_points" in prompt
            assert "risks_and_blockers" in prompt
            assert "unresolved_questions" in prompt
            assert FOLD_CLAUSE not in prompt
            assert "无对应栏目时的折叠规则" not in prompt
            assert user.strip()
            checked += 1
    assert checked >= 40
