"""多语种模板目录隔离、请求体 lang 校验与动态模板解析单元测试。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import (
    resolve_template_format,
    template_dir,
    template_key,
    template_registry,
)
from app.schemas import Extra, TaskRequest
from app.tasks import ApiError, _prepare, _runner_args, _template_file


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

    # 英文注册表首期试点仅包含已英化的 general_minutes
    reg_en = template_registry("en")
    assert len(reg_en) >= 1
    assert any("general_minutes" in k for k in reg_en)
    # 严格隔离：未英化的模板绝对不出现在英文注册表中
    assert not any("project_progress" in k for k in reg_en)


def test_template_format_resolution_by_language():
    """测试按语种准确解析模板 format。"""
    # 1. 英文通用纪要解析
    en_fmt = resolve_template_format("general_minutes", lang="en")
    assert "# General Minutes" in en_fmt
    assert "[Executive Summary]" in en_fmt
    assert "[Key Discussion Points]" in en_fmt
    assert "[Decisions & Rulings]" in en_fmt
    assert "通用纪要" not in en_fmt

    # 支持英文标题匹配
    en_title_fmt = resolve_template_format("General Minutes", lang="en")
    assert "# General Minutes" in en_title_fmt

    # 2. 中文通用纪要解析
    zh_fmt = resolve_template_format("general_minutes", lang="zh")
    assert "# 通用纪要" in zh_fmt
    assert "[全文摘要]" in zh_fmt
    assert "[要点梳理]" in zh_fmt
    assert "[结论定调]" in zh_fmt

    zh_title_fmt = resolve_template_format("通用纪要", lang="zh")
    assert "# 通用纪要" in zh_title_fmt


def test_strict_isolation_untranslated_template():
    """测试严格语种隔离：英文模式请求未英化的模板，绝不回退至中文，返回空。"""
    # project_progress 尚未英化
    en_untranslated = resolve_template_format("project_progress", lang="en")
    assert en_untranslated == ""

    # 中文模式正常加载
    zh_translated = resolve_template_format("project_progress", lang="zh")
    assert len(zh_translated) > 0
    assert "项目概况" in zh_translated or "进度追踪" in zh_translated


def test_template_file_task_preparation():
    """测试 app.tasks._template_file 的多语种解析与非法拦截。"""
    # 英文模式加载 general_minutes 成功
    tpl_en = _template_file("meeting", "minutes", "general_minutes", lang="en")
    assert tpl_en is not None
    assert "General Minutes" in tpl_en.read_text(encoding="utf-8")

    # 中文模式加载 general_minutes 成功
    tpl_zh = _template_file("meeting", "minutes", "general_minutes", lang="zh")
    assert tpl_zh is not None
    assert "通用纪要" in tpl_zh.read_text(encoding="utf-8")

    # 英文模式请求尚未英化的模板，必须抛出 400 ApiError
    with pytest.raises(ApiError) as exc_info:
        _template_file("meeting", "minutes", "contract_vetting", lang="en")
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
    assert "General Minutes" in tpl_path_en.read_text(encoding="utf-8")

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
    assert "通用纪要" in tpl_path_zh.read_text(encoding="utf-8")
