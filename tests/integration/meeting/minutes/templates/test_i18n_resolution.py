# 拆分自 test_i18n.py，覆盖：test_task_request_lang_validation, test_template_dir_and_registry_isolation, test_template_format_resolution_by_language…

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

pytestmark = pytest.mark.integration

def test_task_request_lang_validation():
    """测试 TaskRequest 第一层顶层字段 lang 校验与归一化。"""
    # 缺省为中文
    req_default = TaskRequest()
    assert req_default.lang == "zh"

    # 显式英文与别名大小写清洗
    req_en = TaskRequest(lang="en")
    assert req_en.lang == "en"

    req_en_upper = TaskRequest(lang="EN")
    assert req_en_upper.lang == "en"

    req_english = TaskRequest(lang="english")
    assert req_english.lang == "en"

    # 显式中文与别名清洗
    req_zh = TaskRequest(lang="zh")
    assert req_zh.lang == "zh"

    req_chinese = TaskRequest(lang="chinese")
    assert req_chinese.lang == "zh"

    # 非法语种取值拦截 (抛出 422 验证异常)
    with pytest.raises(ValidationError) as exc_info:
        TaskRequest(lang="fr")
    assert "lang 仅支持 'zh' 或 'en'" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info_jp:
        TaskRequest(lang="jp")
    assert "lang 仅支持 'zh' 或 'en'" in str(exc_info_jp.value)


def test_template_dir_and_registry_isolation():
    """测试模板目录与注册表严格按语种物理隔离。"""
    zh_dir = template_dir("zh")
    assert zh_dir.name == "zh"
    assert zh_dir.is_dir()

    en_dir = template_dir("en")
    assert en_dir.name == "en"
    assert en_dir.is_dir()

    # 默认调用指向中文
    default_dir = template_dir()
    assert default_dir.name == "zh"

    # 中文注册表包含 29 个模板
    reg_zh = template_registry("zh")
    assert len(reg_zh) == 29
    assert any("general_minutes" in k for k in reg_zh)
    assert any("project_progress" in k for k in reg_zh)

    # 英文注册表全量对齐 29 套场景模板（29:29 严格对齐）
    reg_en = template_registry("en")
    assert len(reg_en) == 29
    assert any("general_minutes" in k for k in reg_en)
    assert any("project_progress" in k for k in reg_en)
    assert any("class_transcript" in k for k in reg_en)
    assert any("research_dialogue" in k for k in reg_en)
    assert any("clinical_advisory" in k for k in reg_en)
    assert any("contract_vetting" in k for k in reg_en)
    assert any("media_briefing" in k for k in reg_en)
    assert any("home_school_liaison" in k for k in reg_en)
    # 非法或不存在的模板不出现在注册表中
    assert not any("non_existent_template" in k for k in reg_en)


def test_template_format_resolution_by_language():
    """测试按语种准确解析模板 format。"""
    # 1. 英文通用纪要解析
    en_fmt = resolve_template_format("general_minutes", lang="en")
    assert "# General Minutes" not in en_fmt
    assert "[Executive Summary]" in en_fmt
    assert "[Key Discussion Points]" in en_fmt
    assert "[Decisions & Rulings]" in en_fmt
    assert "通用纪要" not in en_fmt

    # 支持英文标题匹配
    en_title_fmt = resolve_template_format("General Minutes", lang="en")
    assert "[Executive Summary]" in en_title_fmt

    # 2. 中文通用纪要解析
    zh_fmt = resolve_template_format("general_minutes", lang="zh")
    assert "# 通用纪要" not in zh_fmt
    assert "[全文摘要]" in zh_fmt
    assert "[要点梳理]" in zh_fmt
    assert "[结论定调]" in zh_fmt

    zh_title_fmt = resolve_template_format("通用纪要", lang="zh")
    assert "[全文摘要]" in zh_title_fmt


def test_agenda_template_resolution_by_language():
    """议题模板目录按语种隔离：zh/ 与 en/ 各自命中对应议题模板。"""
    zh_fmt = resolve_agenda_template_format("general_minutes", lang="zh")
    assert resolve_agenda_template_format("general_minutes") == zh_fmt
    assert "以现场审定的有效议题清单为主线展开" in zh_fmt
    assert "### 一. 议题名称" in zh_fmt

    en_fmt = resolve_agenda_template_format("general_minutes", lang="en")
    assert "[Executive Summary]" in en_fmt
    assert "[Topic Review]" in en_fmt
    assert "#### Key Discussion Points" in en_fmt
    assert "#### Decisions & Rulings" in en_fmt
    assert "### I. Topic Title" in en_fmt
    assert "### 1. Topic Title" not in en_fmt
    assert "以现场审定的有效议题" not in en_fmt


def test_template_file_task_preparation():
    """测试 app.tasks._template_file 的多语种解析与非法拦截。"""
    # 英文模式加载 general_minutes 成功
    tpl_en = _template_file("meeting", "minutes", "general_minutes", lang="en")
    assert tpl_en is not None
    assert "[Executive Summary]" in tpl_en.read_text(encoding="utf-8")

    # 中文模式加载 general_minutes 成功
    tpl_zh = _template_file("meeting", "minutes", "general_minutes", lang="zh")
    assert tpl_zh is not None
    assert "[全文摘要]" in tpl_zh.read_text(encoding="utf-8")

    # 英文模式加载第五批模板成功
    tpl_media = _template_file("meeting", "minutes", "media_briefing", lang="en")
    assert tpl_media is not None
    assert "[Briefing Overview]" in tpl_media.read_text(encoding="utf-8")

    # 非法模板名必须抛出 400 ApiError
    with pytest.raises(ApiError) as exc_info:
        _template_file("meeting", "minutes", "unknown_custom_template", lang="en")
    assert exc_info.value.status == 400
    assert "extra.template 非法" in exc_info.value.message


def test_prepare_and_runner_args_pipeline_pass_through():
    """测试 _prepare 与 _runner_args 全流程透传 lang 参数。"""
    # 1. 英文请求
    req_en = TaskRequest(
        lang="en",
        texts={"transcript": "Good morning team, let us review the sprint."},
        extra=Extra(template="general_minutes"),
    )
    p_en = _prepare("meeting", "minutes", req_en, user_id="test_user")
    assert p_en.lang == "en"
    args_en = _runner_args(p_en)
    assert args_en["lang"] == "en"
    tpl_path_en = p_en.templates.get("minutes")
    assert tpl_path_en is not None
    assert "[Executive Summary]" in tpl_path_en.read_text(encoding="utf-8")

    # 2. 中文请求
    req_zh = TaskRequest(
        lang="zh",
        texts={"transcript": "各位早，今天我们做一下冲刺评审。"},
        extra=Extra(template="general_minutes"),
    )
    p_zh = _prepare("meeting", "minutes", req_zh, user_id="test_user")
    assert p_zh.lang == "zh"
    args_zh = _runner_args(p_zh)
    assert args_zh["lang"] == "zh"
    tpl_path_zh = p_zh.templates.get("minutes")
    assert tpl_path_zh is not None
    assert "[全文摘要]" in tpl_path_zh.read_text(encoding="utf-8")
