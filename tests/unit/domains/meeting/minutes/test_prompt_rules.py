"""tests/unit/meeting/test_minutes_qa_quote_prompt_rules.py -- 问答/金句生成规则。"""
from __future__ import annotations

from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
    MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT,
)


def test_objective_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_OBJECTIVE_GENERATION_PROMPT

    assert "关键发言原话与重要问答有机融入对应议题段落" in prompt
    assert "交代清楚决策依据" in prompt


def test_agenda_column_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_AGENDA_GENERATION_PROMPT

    assert "问答与金句" in prompt
    assert "属于正文内容" in prompt
    assert "写入对应议题段落" in prompt
    assert "不得写入 unresolved_questions 或 key_decisions" in prompt


def test_topic_major_prompt_routes_qa_and_quotes_to_topic_summary() -> None:
    prompt = MINUTES_TOPIC_MAJOR_GENERATION_PROMPT

    assert "问答与金句写入 topic_summary" in prompt
    assert "问答保留问答配对" in prompt
    assert "金句保留原话措辞与发言人归属" in prompt
    assert "不得写入 decisions 或 open_questions" in prompt


def test_objective_render_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_RENDER_TEMPLATE_PROMPT

    assert "7. 问答/Q&A/问答记录类栏目" in prompt
    assert "映射 executive_summary[1:] 中对应议题的问答内容" in prompt
    assert "保留问答配对" in prompt
    assert "不得映射到 unresolved_questions" in prompt

    assert "8. 金句/金句总结/关键原话类栏目" in prompt
    assert "保留原话措辞与发言人归属" in prompt
    assert "不得映射到 key_decisions" in prompt

    assert "9. 无法判断栏目语义" in prompt


def test_agenda_column_render_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT

    assert "7. 问答/Q&A/问答记录类栏目" in prompt
    assert "映射 executive_summary[1:] 中对应议题的问答内容" in prompt
    assert "保留问答配对" in prompt
    assert "不得映射到 unresolved_questions" in prompt

    assert "8. 金句/金句总结/关键原话类栏目" in prompt
    assert "保留原话措辞与发言人归属" in prompt
    assert "不得映射到 key_decisions" in prompt

    assert "9. 若模板没有总述/概况栏" in prompt
    assert "10. 不强行塞入不相关内容，不自创模板外栏目。" in prompt


def test_topic_major_render_prompt_routes_qa_and_quotes_to_topic_summary() -> None:
    prompt = MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT

    assert "问答/Q&A/问答记录/核心问答 → topic_summary（保留问答配对）" in prompt
    assert "金句/金句总结/关键原话 → topic_summary（保留原话与发言人归属）" in prompt

    assert "4. 全局问答/金句类栏目：从 topics[].topic_summary 归集" in prompt
    assert "不新增议题" in prompt
    assert "不得映射到 open_questions / decisions" in prompt

    assert "8. 不强行塞入不相关内容，不自创模板外栏目。" in prompt
