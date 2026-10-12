"""tests/meeting/test_minutes_decoupling.py
全面验证纪要任务（Minutes）客观视角与个人视角深度解耦：
1. 11 核心字段 Schema 契约校验与防炸护栏（无僵尸字段）
2. 视角建模提示词（Prefill Cache 先验 + 权责本体论 + 无客观死代码）
3. 生成端（MinutesGenerationAgent）双轨提示词路由与纯净分流
4. 编排层（orchestrator）上下文模式纯净隔离
5. 审核端（MinutesGenerationSupervisor）双轨独立审查与放行规则
6. 强执行层（enforce_minutes_draft）数据闭环与 data_gaps 合流
7. 终局 MinutesReport 物理校验（validate_payload 零容忍防崩断言）
"""
from __future__ import annotations

import json
import pytest

from core.schema.validation import OutputValidationError, validate_payload
from core.execution.hard_execution import (
    enforce_minutes_draft,
    parse_perspective_mode,
)
from domains.meeting.models import Minutes
from domains.meeting.reports import MinutesReport
from domains.shared.perspective.models import (
    EMPTY_PERSPECTIVE_MODELING,
    PerspectiveModeling,
)
from domains.shared.perspective.prompts import PERSPECTIVE_MODELING_SYSTEM_PROMPT
from domains.meeting.tasks.minutes.prompts import (
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_RENDER_PROMPT,
    MINUTES_PERSONAL_RENDER_PROMPT,
)


# ── 1. 11 核心字段 Schema 契约校验测试 ──────────────────────────────────────────

def test_perspective_modeling_11_fields_contract():
    """验证 PerspectiveModeling 数据模型与契约严格收敛为 11 核心字段。"""
    valid_data = {
        "confidence": "high",
        "name": "申家坤",
        "personal_summary": "负责模型压测与显存优化，推进demo按期交付。",
        "attention_points": ["demo落地推进与性能压测", "显存≤4.5GB指标要求"],
        "possible_actions": ["原文承诺：周四18:00前输出压测报告"],
        "concerns": ["显存不足可能影响单卡50并发"],
        "evidence": ["topics[0].actions[0]：申家坤输出压测报告"],
        "responsibilities": ["模型压测与显存调优"],
        "relevant_topics": ["demo落地推进与性能压测"],
        "open_questions": ["与徐玥确认沙箱测试用例范围"],
        "data_gaps": ["关键输入断供：测试环境GPU驱动版本尚未提供"],
    }

    # 1.1 正常 11 字段验证必须完全通过
    model = PerspectiveModeling.validate(valid_data)
    assert model.name == "申家坤"
    assert len(model.open_questions) == 1
    assert len(model.data_gaps) == 1

    # 1.2 EMPTY_PERSPECTIVE_MODELING 键集合恒等验证
    assert set(EMPTY_PERSPECTIVE_MODELING.keys()) == set(valid_data.keys())
    assert len(EMPTY_PERSPECTIVE_MODELING) == 11

    # 1.3 缺失任何一个必填字段必须抛出 OutputValidationError
    incomplete_data = dict(valid_data)
    del incomplete_data["open_questions"]
    with pytest.raises(OutputValidationError) as exc_info:
        PerspectiveModeling.validate(incomplete_data)
    assert "缺失" in str(exc_info.value)

    # 1.4 残留僵尸字段（如 goals / conclusions / stakeholders / inferred_role）必须严格抛出异常
    for zombie in ("goals", "conclusions", "stakeholders", "inferred_role"):
        zombie_data = dict(valid_data)
        zombie_data[zombie] = ["空话"] if zombie != "inferred_role" else "工程师"
        with pytest.raises(OutputValidationError) as exc_info:
            PerspectiveModeling.validate(zombie_data)
        assert "多余" in str(exc_info.value)


# ── 2. 视角建模提示词重构（Prefill + 权责本体论）─────────────────────────────────

def test_perspective_modeling_prompt_quality():
    """验证 PERSPECTIVE_MODELING_SYSTEM_PROMPT 已彻底洗髓，无死代码且具有正向权责本体论。"""
    prompt = PERSPECTIVE_MODELING_SYSTEM_PROMPT

    # 2.1 彻底剔除客观死代码
    assert 'perspective = "objective"' not in prompt
    assert "客观全员" not in prompt

    # 2.2 头部 Attention Sink 权责本体论断言
    assert "直接责任（My Action）" in prompt
    assert "协同关注（Focus）" in prompt
    assert "背景环境（Context）" in prompt
    assert "open_questions" in prompt
    assert "data_gaps" in prompt

    # 2.3 尾部单句执行交付令替代假自检八股文
    assert "【执行交付令】" in prompt
    assert "自检" not in prompt


# ── 3. 纪要双轨生成提示词与分流测试 ─────────────────────────────────────────────

def test_minutes_generation_prompts_decoupling():
    """验证客观与个人生成提示词完全解耦，客观无个人噪声，个人有看板合流。"""
    # 3.1 共享公共基底保真度测试
    for p in (MINUTES_OBJECTIVE_GENERATION_PROMPT, MINUTES_PERSONAL_GENERATION_PROMPT):
        assert "回到会议原文" in p
        assert "理解层是骨架" in p
        assert "时效优先法典" in p
        assert "尾部记忆核验令" in p

    # 3.2 客观提示词纯净化断言
    assert "通篇统一使用第三人称" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "全员落地执行要点" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "不设立任何个人视角分组标签" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "**本人相关**：" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "本人动作规范" not in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 3.3 个人提示词作战看板体与合流断言
    assert "**本人相关**：" in MINUTES_PERSONAL_GENERATION_PROMPT
    assert "动宾短语" in MINUTES_PERSONAL_GENERATION_PROMPT
    assert "open_questions" in MINUTES_PERSONAL_GENERATION_PROMPT
    assert "data_gaps" in MINUTES_PERSONAL_GENERATION_PROMPT
    assert "**重点协同**：" in MINUTES_PERSONAL_GENERATION_PROMPT
    assert "**重点关注**：" in MINUTES_PERSONAL_GENERATION_PROMPT


def test_parse_perspective_mode_routing():
    """验证 parse_perspective_mode 对客观与个人上下文的前缀精准识别。"""
    obj_ctx = "视角模式：objective\n\n会议理解：{}"
    pers_ctx = "视角模式：personal\n\n会议理解：{}"
    empty_ctx = "会议理解：{}"

    assert parse_perspective_mode(obj_ctx) == "objective"
    assert parse_perspective_mode(pers_ctx) == "personal"
    assert parse_perspective_mode(empty_ctx) == "objective"


# ── 4. 审核端双轨提示词独立性测试 ───────────────────────────────────────────────

def test_minutes_supervisor_prompts_decoupling():
    """验证 Supervisor 提示词保留历史免审与判定条件，客观与个人专项规则互不干扰。"""
    for sup in (MINUTES_OBJECTIVE_SUPERVISOR_PROMPT, MINUTES_PERSONAL_SUPERVISOR_PROMPT):
        assert "搬运项免审" in sup
        assert "enforce_minutes_draft" in sup
        assert "reject 的三个可判定条件" in sup
        assert "拿不准就选它" in sup
        assert "与上游不一致" not in sup

    # 客观专属审查
    assert "全员平铺结构" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "客观模式审查专项" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT

    # 个人专属审查
    assert "动宾短语开头、省略主语" in MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert "自适应裁剪放行保障" in MINUTES_PERSONAL_SUPERVISOR_PROMPT


# ── 5. 强执行层字典闭环与 data_gaps 合流测试 ────────────────────────────────────

def test_hard_execution_enforce_minutes_draft_completeness_and_gaps():
    """验证 enforce_minutes_draft 保证 7 契约键完整，并在个人模式合流 data_gaps。"""
    upstream = {
        "decisions": ["全员方案A拍板"],
        "risks": ["内部服务超时风险"],
        "open_questions": ["外部联调时间待定"],
    }
    raw_draft = {
        "headline": "对齐会",
        "executive_summary": ["会议总结"],
        "key_decisions": ["全员方案A拍板"],
        "personally_relevant_points": ["**本人相关**：", "完成代码提交"],
        "risks_and_blockers": ["**本人相关**：", "外部数据断供卡点：测试物料未到位"],
        "unresolved_questions": [],
    }
    perspective = {
        "data_gaps": ["外部数据断供卡点：测试物料未到位"],
    }

    # 5.1 个人模式下 data_gaps 成功保留，不被粗暴清洗
    enforced_pers = enforce_minutes_draft(
        raw_draft,
        upstream,
        mode="personal",
        perspective=perspective,
    )
    assert "外部数据断供卡点：测试物料未到位" in enforced_pers["risks_and_blockers"]
    assert "history_comparison" in enforced_pers  # 契约键自动补齐

    # 5.2 客观模式下 risks 严格与 upstream 保持一致
    raw_obj_draft = {
        "headline": "对齐会",
        "executive_summary": ["会议总结"],
        "key_decisions": ["全员方案A拍板"],
        "personally_relevant_points": ["张工负责联调"],
        "risks_and_blockers": ["内部服务超时风险"],
        "unresolved_questions": [],
    }
    enforced_obj = enforce_minutes_draft(
        raw_obj_draft,
        upstream,
        mode="objective",
    )
    assert enforced_obj["risks_and_blockers"] == ["内部服务超时风险"]
    assert set(enforced_obj.keys()) == {
        "headline",
        "executive_summary",
        "key_decisions",
        "personally_relevant_points",
        "risks_and_blockers",
        "unresolved_questions",
        "history_comparison",
    }


# ── 6. 终局 MinutesReport 校验（validate_payload 零容忍防崩测试）────────────────

def test_final_report_validate_payload_zero_tolerance():
    """测试终局 MinutesReport 的刚性校验，杜绝 OutputValidationError 异常与降级。"""
    valid_report = {
        "title": "系统架构评审纪要",
        "personalized_minutes": "# 系统架构评审纪要\n\n## 全文摘要\n\n架构设计经全员研讨一致通过。",
        "quality_warning": "",
    }

    # 6.1 合法 Report 结构 100% 校验成功
    validated = validate_payload(MinutesReport, valid_report)
    assert validated.title == "系统架构评审纪要"
    assert isinstance(validated.personalized_minutes, str)

    # 6.2 personalized_minutes 若为非字符串（如误传 dict 或 list），必拦截
    invalid_report = dict(valid_report)
    invalid_report["personalized_minutes"] = {"content": "错成了字典"}
    with pytest.raises(OutputValidationError):
        validate_payload(MinutesReport, invalid_report)

    # 6.3 多余键必拦截
    invalid_report_extra = dict(valid_report)
    invalid_report_extra["extra_key"] = "多余数据"
    with pytest.raises(OutputValidationError):
        validate_payload(MinutesReport, invalid_report_extra)
