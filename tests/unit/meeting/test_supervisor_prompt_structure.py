"""Step 3：审核 prompt 的结构与防回归守卫。"""
from __future__ import annotations

from domains.meeting.tasks.minutes import prompts as minutes_prompts
from domains.meeting.tasks.minutes.prompts import (
    _SUPERVISOR_COMMON_BASE,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_SUPERVISOR_DOMAIN_PROMPT,
    build_minutes_supervisor_prompt,
)

_ALL_PROMPTS = (
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
)

_DROPPED_FIELDS = (
    "key_decisions",
    "risks_and_blockers",
    "unresolved_questions",
)


def test_all_supervisor_prompts_share_common_base() -> None:
    prefix = _SUPERVISOR_COMMON_BASE + "\n\n"
    for prompt in _ALL_PROMPTS:
        assert prompt.startswith(prefix)
        assert prompt.count(_SUPERVISOR_COMMON_BASE) == 1


def test_agenda_common_base_is_removed() -> None:
    assert not hasattr(minutes_prompts, "_AGENDA_SUPERVISOR_COMMON_BASE")


def test_supervisor_scope_only_reviews_present_content() -> None:
    assert "本轮送审范围" in _SUPERVISOR_COMMON_BASE
    assert "只审送审稿中实际出现的内容" in _SUPERVISOR_COMMON_BASE
    assert "未出现的内容不判缺失，也不发表意见" in _SUPERVISOR_COMMON_BASE


def test_common_base_does_not_name_dropped_fields() -> None:
    for field in _DROPPED_FIELDS:
        assert field not in _SUPERVISOR_COMMON_BASE


def test_common_base_drops_old_carry_wording() -> None:
    for old in (
        "搬运项免审",
        "上游事实搬运项",
        "enforce_minutes_draft",
        "历史记忆隔离审查",
    ):
        assert old not in _SUPERVISOR_COMMON_BASE


def test_common_base_has_no_duplicate_rule_blocks() -> None:
    assert _SUPERVISOR_COMMON_BASE.count("### 严重缺陷") == 1
    assert _SUPERVISOR_COMMON_BASE.count("只有以下情况才判 reject") == 1
    # 决策 / 历史 / 辅助材料已移出静态基底，改为运行时动态拼接
    assert _SUPERVISOR_COMMON_BASE.count("### 决策") == 0
    assert _SUPERVISOR_COMMON_BASE.count("### 历史记忆审查") == 0
    assert _SUPERVISOR_COMMON_BASE.count("### 多源辅助参考审查") == 0
    assert _SUPERVISOR_COMMON_BASE.count("### Findings") == 1


def test_agenda_rules_are_not_duplicated() -> None:
    assert MINUTES_AGENDA_SUPERVISOR_PROMPT.count("议程骨架违规判定") == 1
    assert MINUTES_AGENDA_SUPERVISOR_PROMPT.count("### 辅助材料与议程骨架") == 1
    assert MINUTES_AGENDA_SUPERVISOR_PROMPT.count("### 标题一致性口径") == 1


def test_agenda_rules_are_absent_from_normal_prompts() -> None:
    for prompt in (
        MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
        MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    ):
        assert "议程骨架违规判定" not in prompt
        assert "### 辅助材料与议程骨架" not in prompt
        assert "### 标题一致性口径" not in prompt


def test_view_specific_rules_do_not_leak() -> None:
    assert "个人视角审查专项" not in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "客观模式审查专项" not in MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert "客观模式审查专项" not in MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "个人视角审查专项" not in MINUTES_AGENDA_SUPERVISOR_PROMPT


def test_agenda_prompt_keeps_heading_localization_anchors() -> None:
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "### 一." in prompt
    assert "### 二." in prompt
    assert "三级标题序号" in prompt
    assert "### I." not in prompt
    assert "中文数字序号" not in prompt


def test_agenda_prompt_keeps_title_normalization_rules() -> None:
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "### 标题一致性口径" in prompt
    assert "标题比对口径" in prompt
    assert "忽略大小写" in prompt
    assert "连续空白" in prompt
    assert "连字符差异" in prompt
    assert "语义被改写" in prompt
    assert "英文标题保留原文" in prompt


def test_english_wrapper_anchor_is_preserved() -> None:
    assert _SUPERVISOR_COMMON_BASE.startswith("你是会议纪要质量审核专家。")
    assert "。\n\n## 领域审核规则：纪要生成" in _SUPERVISOR_COMMON_BASE


def test_objective_compat_alias_is_still_objective() -> None:
    assert MINUTES_SUPERVISOR_DOMAIN_PROMPT is MINUTES_OBJECTIVE_SUPERVISOR_PROMPT


def test_supervisor_prompt_length_budget() -> None:
    # 软预算：防止 prompt 再次膨胀；数值留有余量，不锁死文案。
    assert len(_SUPERVISOR_COMMON_BASE) <= 1000
    assert len(MINUTES_AGENDA_SUPERVISOR_PROMPT) <= 1600

def test_builder_omits_aux_history_when_absent() -> None:
    prompt = build_minutes_supervisor_prompt("personal")
    assert "### 多源辅助参考审查" not in prompt
    assert "### 历史记忆审查" not in prompt
    assert prompt.rstrip().endswith("- 以用户消息表头给出的可选动作为准。")


def test_builder_includes_only_present_aux_rules() -> None:
    notes = build_minutes_supervisor_prompt("objective", aux_labels=["notes"])
    assert "【用户划线原话与笔记】" in notes
    assert "【用户核心关键点】" not in notes
    assert "【视觉信息参考(OCR)】" not in notes

    both = build_minutes_supervisor_prompt(
        "objective", aux_labels=["keypoints", "vision"]
    )
    assert "【用户核心关键点】" in both
    assert "【视觉信息参考(OCR)】" in both
    assert "【用户划线原话与笔记】" not in both


def test_builder_appends_history_and_decision_last() -> None:
    prompt = build_minutes_supervisor_prompt(
        "personal",
        has_history=True,
        allowed_actions="返工次数已用完，本轮只能选择 approve 或 reject。",
    )
    assert "### 历史记忆审查" in prompt
    assert "本轮只能选择 approve 或 reject" in prompt
    assert prompt.rindex("### 决策") > prompt.rindex("### 历史记忆审查")


def test_builder_detects_aux_history_and_allowed_actions_from_context() -> None:
    context = (
        "视角模式：personal\n"
        "纪要返工次数：1/1\n"
        "返工次数已用完，本轮只能选择 approve 或 reject。\n\n"
        "【用户划线原话与笔记】\n- 备注：先别上线\n"
        "【项目推进背景】\n- 上期已确认排期\n"
        '纪要草稿：\n{"history_comparison": ["上期：v1"]}'
    )
    prompt = build_minutes_supervisor_prompt("personal", context=context)
    assert "### 多源辅助参考审查" in prompt
    assert "【用户划线原话与笔记】" in prompt
    assert "### 历史记忆审查" in prompt
    assert "本轮只能选择 approve 或 reject" in prompt

