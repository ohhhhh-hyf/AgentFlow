"""tests/unit/meeting/test_minutes_qa_quote_prompt_rules.py -- 问答/金句生成规则。"""
from __future__ import annotations

from domains.meeting.tasks.minutes.prompts import (
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
    MINUTES_TOPIC_MAJOR_GENERATION_PROMPT,
    MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT,
)


def test_objective_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_OBJECTIVE_GENERATION_PROMPT

    assert "金句与问答归属" in prompt
    assert "金句原话：随所在议题就地收录（保留发言人与原话），不作为决策写入 key_decisions" in prompt
    assert "互动问答：议题内问答直接写入对应段落，会末集中问答作为末尾独立项成对展开（注明双方）；已闭环问答不写入 unresolved_questions" in prompt
    assert "交代清楚决策依据" in prompt


def test_agenda_column_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_AGENDA_GENERATION_PROMPT

    assert "金句与问答归属" in prompt
    assert "随所在审定议题就地收录（保留发言人与原话），不作为决策写入 key_decisions" in prompt
    assert "议题内即时问答写入对应议题；会末集中问答若未单独列入审定议程，作为 executive_summary 数组末尾独立项成对展开（注明双方）" in prompt
    assert "已闭环问答不写入 unresolved_questions" in prompt


def test_personal_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_PERSONAL_GENERATION_PROMPT

    assert "金句与问答收录" in prompt
    assert "具有指导意义的发言人金句原话若与本人职责直接相关，随业务段落就地收录" in prompt
    assert "涉及本人的提问或答复成对收录于对应段落" in prompt
    assert "已闭环问答不得写入 unresolved_questions" in prompt


def test_topic_major_prompt_routes_qa_and_quotes_to_topic_summary() -> None:
    prompt = MINUTES_TOPIC_MAJOR_GENERATION_PROMPT

    assert "问答与金句写入 topic_summary" in prompt
    assert "问答保留问答配对" in prompt
    assert "金句保留原话措辞与发言人归属" in prompt
    assert "不得写入 decisions 或 open_questions" in prompt


def test_objective_render_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_RENDER_TEMPLATE_PROMPT

    assert "6. 通用业务类栏目（业务研讨/要点/核心信息类）" in prompt
    assert "避免内容重复渲染" in prompt
    assert "末尾问答项作为本栏最后一个小节正常输出" in prompt

    assert "7. 问答/Q&A/问答记录类栏目" in prompt
    assert "从 executive_summary[1:] 中提取问答内容" in prompt
    assert "优先映射末尾独立项中的集中问答" in prompt
    assert "严格保持一问一答成对展开" in prompt
    assert "不得映射到 unresolved_questions" in prompt

    assert "8. 金句/金句总结/关键原话与表态类栏目" in prompt
    assert "从 executive_summary[1:] 各议题段落中归集发言人原话与关键表态" in prompt
    assert "保留发言人姓名、身份与原话引用" in prompt
    assert "不得映射到 key_decisions" in prompt

    assert "9. 无法判断栏目语义" in prompt


def test_agenda_column_render_prompt_routes_qa_and_quotes_to_executive_summary() -> None:
    prompt = MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT

    assert "避免内容重复渲染" in prompt
    assert "末尾集中问答项作为本栏最后一个小节正常输出" in prompt

    assert "7. 问答/Q&A/问答记录类栏目" in prompt
    assert "从 executive_summary[1:] 中提取问答内容" in prompt
    assert "优先映射末尾独立项中的集中问答" in prompt
    assert "严格保持一问一答成对展开" in prompt
    assert "不得映射到 unresolved_questions" in prompt

    assert "8. 金句/金句总结/关键原话与表态类栏目" in prompt
    assert "从 executive_summary[1:] 各议题段落中归集发言人原话与关键表态" in prompt
    assert "保留发言人姓名、身份与原话引用" in prompt
    assert "不得映射到 key_decisions" in prompt

    assert "9. 若模板没有总述/概况栏" in prompt
    assert "10. 不强行塞入不相关内容，不自创模板外栏目。" in prompt


def test_personal_render_prompt_routes_qa_and_quotes() -> None:
    prompt = MINUTES_PERSONAL_RENDER_TEMPLATE_PROMPT

    assert "段落中收录的本人相关金句原话与问答直接随文完整呈现" in prompt


def test_topic_major_render_prompt_routes_qa_and_quotes_to_topic_summary() -> None:
    prompt = MINUTES_TOPIC_MAJOR_RENDER_TEMPLATE_PROMPT

    assert "问答/Q&A/问答记录/核心问答 → topic_summary（保留问答配对）" in prompt
    assert "金句/金句总结/关键原话 → topic_summary（保留原话与发言人归属）" in prompt

    assert "4. 全局问答/金句类栏目：从 topics[].topic_summary 归集" in prompt
    assert "不新增议题" in prompt
    assert "不得映射到 open_questions / decisions" in prompt

    assert "8. 不强行塞入不相关内容，不自创模板外栏目。" in prompt
