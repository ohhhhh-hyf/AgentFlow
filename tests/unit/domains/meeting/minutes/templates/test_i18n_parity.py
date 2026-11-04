# 拆分自 test_i18n.py，覆盖：test_batch1_english_templates_resolution, test_batch2_english_templates_resolution, test_batch3_english_templates_resolution…

"""多语种模板目录隔离、请求体 lang 校验与动态模板解析单元测试。"""

from __future__ import annotations
import pytest
from pydantic import ValidationError
from app.config import (
    resolve_agenda_template_format,
    resolve_template_format,
    template_dir,
    template_key,
    template_registry,
)
from app.schemas import Extra, TaskRequest
from app.tasks import ApiError, _prepare, _runner_args, _template_file
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock
import pytest
from core.execution.hard_execution import enforce_minutes_draft, parse_lang_mode
from core.templates.length_budget import english_budget_line, word_count
from core.templates.router import validate_rendered_output
from domains.meeting.meeting_core.meeting_understanding_agent import MeetingUnderstandingAgent
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.tasks.minutes.steps.minutes_render import MinutesGenerationRender
from domains.meeting.tasks.minutes.steps.minutes_supervisor import MinutesGenerationSupervisor

def test_batch1_english_templates_resolution():
    """测试第一批落地的 6 套英文会议模板解析与格式正确性。"""
    batch1_templates = [
        ("project_progress", "Project Progress Meeting", "[Project Overview]", "[Progress Tracking]"),
        ("team_meeting", "Team Routine Meeting", "[Meeting Overview]", "[Work Progress]"),
        ("decision_review", "Decision & Review Meeting", "[Review Overview]", "[Final Resolutions]"),
        ("workshop_session", "Workshop Session", "[Workshop Overview]", "[Core Viewpoints]"),
        ("retrospective_session", "Retrospective Session", "[Retrospective Overview]", "[Actionable Improvements]"),
        ("exchange_forum", "Exchange Forum", "[Context & Background]", "[Core Information]"),
    ]
    for tid, title, sec1, sec2 in batch1_templates:
        fmt = resolve_template_format(tid, lang="en")
        assert fmt, f"模板 {tid} 解析失败"
        assert sec1 in fmt, f"模板 {tid} 缺失栏目 {sec1}"
        assert sec2 in fmt, f"模板 {tid} 缺失栏目 {sec2}"

        # 支持按英文 Title 查找
        title_fmt = resolve_template_format(title, lang="en")
        assert title_fmt, f"按英文标题 {title} 查找失败"
        assert sec1 in title_fmt


def test_batch2_english_templates_resolution():
    """测试第二批落地的 5 套英文学习/学术场景模板解析与格式正确性。"""
    batch2_templates = [
        ("class_transcript", "Class Transcript", "[Course Overview]", "[Core Knowledge Points]"),
        ("special_lecture", "Special Lecture", "[Lecture Overview]", "[Core Viewpoints]"),
        ("group_seminar", "Group Seminar", "[Discussion Topic]", "[Discussion Highlights]"),
        ("knowledge_memo", "Knowledge Memo", "[Knowledge Overview]", "[Core Concepts]"),
        ("debate_forum", "Debate Forum", "[Debate Overview]", "[Parties' Stances]"),
    ]
    for tid, title, sec1, sec2 in batch2_templates:
        fmt = resolve_template_format(tid, lang="en")
        assert fmt, f"模板 {tid} 解析失败"
        assert sec1 in fmt, f"模板 {tid} 缺失栏目 {sec1}"
        assert sec2 in fmt, f"模板 {tid} 缺失栏目 {sec2}"

        # 支持按英文 Title 查找
        title_fmt = resolve_template_format(title, lang="en")
        assert title_fmt, f"按英文标题 {title} 查找失败"
        assert sec1 in title_fmt


def test_batch3_english_templates_resolution():
    """测试第三批落地的 4 套英文访谈/面试场景模板解析与格式正确性。"""
    batch3_templates = [
        ("research_dialogue", "Research Dialogue", "[Interview Overview]", "[Core Feedback]"),
        ("interview_transcript", "Interview Transcript", "[Interview Overview]", "[Interview Details]"),
        ("hiring_report", "Hiring Report", "[Candidate Profile]", "[Interview Q&A]"),
        ("interview_debrief", "Interview Debrief", "[Interview Overview]", "[Personal Performance]"),
    ]
    for tid, title, sec1, sec2 in batch3_templates:
        fmt = resolve_template_format(tid, lang="en")
        assert fmt, f"模板 {tid} 解析失败"
        assert sec1 in fmt, f"模板 {tid} 缺失栏目 {sec1}"
        assert sec2 in fmt, f"模板 {tid} 缺失栏目 {sec2}"

        # 支持按英文 Title 查找
        title_fmt = resolve_template_format(title, lang="en")
        assert title_fmt, f"按英文标题 {title} 查找失败"
        assert sec1 in title_fmt


def test_batch4_english_templates_resolution():
    """测试第四批落地的 5 套英文医疗/法律咨询场景模板解析与格式正确性。"""
    batch4_templates = [
        ("clinical_advisory", "Clinical Advisory", "[Consultation Overview]", "[Treatment Plan]"),
        ("psychological_session", "Psychological Session", "[Session Overview]", "[Session Details]"),
        ("legal_advisory", "Legal Advisory", "[Advisory Overview]", "[Legal Analysis]"),
        ("court_transcript", "Court Transcript", "[Trial Overview]", "[Claims & Defenses]"),
        ("contract_vetting", "Contract Vetting", "[Contract Overview]", "[Risk Identification]"),
    ]
    for tid, title, sec1, sec2 in batch4_templates:
        fmt = resolve_template_format(tid, lang="en")
        assert fmt, f"模板 {tid} 解析失败"
        assert sec1 in fmt, f"模板 {tid} 缺失栏目 {sec1}"
        assert sec2 in fmt, f"模板 {tid} 缺失栏目 {sec2}"

        # 支持按英文 Title 查找
        title_fmt = resolve_template_format(title, lang="en")
        assert title_fmt, f"按英文标题 {title} 查找失败"
        assert sec1 in title_fmt


def test_batch5_english_templates_resolution():
    """测试第五批落地的 8 套英文媒体发布/日常记录场景模板解析与格式正确性。"""
    batch5_templates = [
        ("media_briefing", "Media Briefing", "[Briefing Overview]", "[Core Information]"),
        ("product_launch", "Product Launch", "[Product Overview]", "[Market Positioning]"),
        ("government_bulletin", "Government Bulletin", "[Bulletin Overview]", "[Core Policies]"),
        ("media_qa_session", "Media Q&A Session", "[Session Overview]", "[Core Q&A]"),
        ("personal_memo", "Personal Memo", "[Memo Overview]", "[Action Reminders]"),
        ("conversation_transcript", "Conversation Transcript", "[Conversation Overview]", "[Discussion Contents]"),
        ("site_visit_tour", "Site Visit Tour", "[Visit Overview]", "[Core Highlights]"),
        ("home_school_liaison", "Home-School Liaison", "[Liaison Overview]", "[School Performance]"),
    ]
    for tid, title, sec1, sec2 in batch5_templates:
        fmt = resolve_template_format(tid, lang="en")
        assert fmt, f"模板 {tid} 解析失败"
        assert sec1 in fmt, f"模板 {tid} 缺失栏目 {sec1}"
        assert sec2 in fmt, f"模板 {tid} 缺失栏目 {sec2}"

        # 支持按英文 Title 查找
        title_fmt = resolve_template_format(title, lang="en")
        assert title_fmt, f"按英文标题 {title} 查找失败"
        assert sec1 in title_fmt


def test_all_29_templates_bilingual_parity():
    """验证全部 29 套模板在中文与英文下均具备 1:1 双语对齐与完整解析能力。"""
    import re
    from app.config import TEMPLATE_SCENARIO

    assert len(TEMPLATE_SCENARIO) == 29
    reg_zh = template_registry("zh")
    reg_en = template_registry("en")
    assert len(reg_zh) == 29
    assert len(reg_en) == 29

    for tid in TEMPLATE_SCENARIO:
        zh_fmt = resolve_template_format(tid, lang="zh")
        assert zh_fmt, f"中文模板 {tid} 未能解析"

        en_fmt = resolve_template_format(tid, lang="en")
        assert en_fmt, f"英文模板 {tid} 未能解析"

        # 验证英文模板顶层标题为英文，不含中文字符
        en_item = next(item for k, item in reg_en.items() if k.endswith(f"_{tid}"))
        assert en_item["name"], f"英文模板 {tid} 缺失名称"
        assert not re.search(r"[\u4e00-\u9fa5]", str(en_item["name"])), (
            f"英文模板 {tid} 标题含中文：{en_item['name']}"
        )


def test_strict_isolation_untranslated_template():
    """测试严格语种隔离：未知或非法模板名无论中英文均返回空。"""
    assert resolve_template_format("unknown_custom_template", lang="en") == ""
    assert resolve_template_format("unknown_custom_template", lang="zh") == ""
