# -*- coding: utf-8 -*-
"""测试短会议篇幅预算豁免逻辑与直接放行机制。"""
import pytest
from core.templates.length_budget import (
    SHORT_MEETING_HAN_THRESHOLD,
    SHORT_MEETING_WORDS_THRESHOLD,
    budget_line,
    capped_budget,
    english_budget_line,
    english_length_budget,
)


def test_short_meeting_budget_exemption():
    """验证短会议（<3000 汉字）全面豁免 80% 硬天花板，防止上下限倒挂与过度压缩。"""
    # 1. 极短文本（800 汉字）：旧逻辑会算出 (720, 640) 产生倒挂；新逻辑返回档位天然区间 (720, 1800)
    assert capped_budget(800) == (720, 1800)

    # 2. 短会议典型场景（1015 汉字）：旧逻辑卡在 (720, 812)；新逻辑返回 (720, 1800)
    assert capped_budget(1015) == (720, 1800)

    # 3. 临界短会（2500 汉字）：仍属于短会，返回 (720, 1800)
    assert capped_budget(2500) == (720, 1800)

    # 4. 中长会（3500 汉字）：正常遵守 80% 约束 (1080, 2800)
    assert capped_budget(3500) == (1080, 2800)

    # 5. 超长会（30000 汉字）：正常遵守 80% 约束与档位上限 (2400, 8000)
    assert capped_budget(30000) == (2400, 8000)


def test_short_meeting_budget_prompt_line():
    """验证注入 Prompt 的篇幅预算说明对短会不再输出 80% 限制字句。"""
    bl_short = budget_line(1015)
    assert "不超过原文的 80%" not in bl_short
    assert "720–1800 汉字" in bl_short

    bl_long = budget_line(3500)
    assert "不超过原文的 80%" in bl_long
    assert "1080–2800 汉字" in bl_long


def test_english_short_meeting_exemption():
    """验证英文短会议篇幅预算豁免逻辑。"""
    # 英文短会（800 words < 1500）：返回档位天然区间 (400, 1000)
    assert english_length_budget(800) == (400, 1000)

    # 英文中长会（2000 words）：遵守 80% 约束
    assert english_length_budget(2000) == (600, 1600)

    # Prompt 说明短会不含 80% 提示
    el_short = english_budget_line(800)
    assert "never exceeding 80%" not in el_short

    el_long = english_budget_line(2000)
    assert "never exceeding 80%" in el_long
