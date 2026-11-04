# 拆分自 test_actions_risks.py，覆盖：test_risk_items_text_render, test_risk_html_flow_render…

"""测试待办与风险的公文流文本生成与HTML渲染。"""

import re
import pytest
from core.graph.engine_text import render_risk_items
from domains.meeting.memory.render import (
    _parse_actions_from_text,
    _parse_risks_from_text,
    render_actions_html,
    render_risks_html,
)
from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender

pytestmark = pytest.mark.integration

if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))

def test_risk_items_text_render():
    """测试风险分析文本渲染与动态弹性伸缩。"""
    items = [
        {
            "category": "核心系统稳定性",
            "risk": "压测 QPS 超过 2000 时网关频繁断流",
            "owner": "架构组",
            "trigger_condition": "单机房并发流量突增 > 2000 QPS",
            "impact": "交易链路雪崩并造成资损",
            "mitigation": "临时扩容 4 台网关，本周内完成异步化改造",
        },
        {
            "category": "核心系统稳定性",
            "risk": "鉴权网关跨机房调用单点超时抖动",
            "owner": "待认领",
            "impact": "高峰期引发重试风暴",
            "mitigation": None,
        },
    ]

    text = render_risk_items(items)
    assert "1. **[核心系统稳定性]**" in text
    assert "- 压测 QPS 超过 2000 时网关频繁断流 (架构组)" in text
    assert "> 触发诱因：单机房并发流量突增 > 2000 QPS" in text
    assert "> 潜在危害：交易链路雪崩并造成资损" in text
    assert "> 现场对策：临时扩容 4 台网关，本周内完成异步化改造" in text
    assert "- 鉴权网关跨机房调用单点超时抖动" in text
    assert "待认领" not in text
    assert "现场对策：无" not in text
    assert "高风险" not in text
    assert "中风险" not in text


def test_risk_html_flow_render():
    """测试风险 HTML 现代轻量工单卡片排版（形态 A）。"""
    items = [
        {
            "category": "核心网关高并发",
            "risk": "核心路由压测超过 2000 QPS 频繁断流",
            "severity": "high",
            "owner": "架构组",
            "impact": "大促交易中断资损",
            "mitigation": "临时扩容 4 台网关前置限流",
        },
        {
            "category": "提升泵防汛隐患",
            "risk": "提升泵位置存在雨季雨水倒灌隐患",
            "severity": "medium",
            "owner": "待认领",
            "impact": "局部严重积水浸泡设备",
            "mitigation": "现场未定（待现场勘测后补充预案）",
        },
    ]

    html = render_risks_html("风险分析测试", "", data={"risks": items})
    assert "ck-card" in html
    assert "核心网关高并发" in html
    assert "核心路由压测超过 2000 QPS 频繁断流" in html
    assert "ck-pill-high" in html
    assert "高风险" in html
    assert "跟进人: 架构组" in html
    assert "潜在危害：" in html
    assert "大促交易中断资损" in html
    assert "应对措施：" in html
    assert "临时扩容 4 台网关前置限流" in html

    assert "提升泵防汛隐患" in html
    assert "ck-pill-medium" in html
    assert "中风险" in html
    # 未指定跟进人彻底隐去，绝不显示待认领，无 1. 2. 序号与条数统计
    assert not re.search(r'class="ck-card-title">\s*\d+[\.、]', html)
    assert "项风险" not in html
    assert "跟进人: 待认领" not in html
    assert "待认领" not in html
    assert "现场未定（待现场勘测后补充预案）" in html

    # 验证无 emoji
    assert "💥" not in html
    assert "🛡️" not in html
    assert "🔴" not in html
