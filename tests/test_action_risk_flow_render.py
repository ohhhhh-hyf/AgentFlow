"""测试待办与风险的公文流文本生成与HTML渲染。"""
import pytest
from core.graph.engine_text import render_risk_items
from domains.meeting.memory.render import (
    _parse_actions_from_text,
    _parse_risks_from_text,
    render_actions_html,
    render_risks_html,
)
from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender


def test_action_items_text_render():
    """测试待办事项文本渲染与动态弹性伸缩。"""
    items = [
        {
            "category": "网关压测流控",
            "task": "完成 SDK 适配补丁并进行 2000 QPS 压测",
            "owner": "张伟",
            "priority": "high",
            "deadline": "周五 18:00 前",
            "deliverable": "压测报告与 API 文档",
            "dependency": "基础架构组签发临时 Token",
        },
        {
            "category": "网关压测流控",
            "task": "申请预发布集群机器配额",
            "owner": "待认领",
            "priority": "medium",
            "deadline": None,
            "deliverable": None,
            "dependency": None,
        },
    ]

    text = ActionItemsRender.render_items(items)
    assert "1. **[网关压测流控]**" in text
    assert "- 完成 SDK 适配补丁并进行 2000 QPS 压测(高优先 · 张伟)" in text
    assert "> 完成时限：周五 18:00 前" in text
    assert "> 交付标准：压测报告与 API 文档" in text
    assert "> 前置条件：基础架构组签发临时 Token" in text
    assert "- 申请预发布集群机器配额(中优先)" in text
    assert "待认领" not in text
    # 极简项不应出现未明确占位符
    assert "完成时限：无" not in text
    assert "交付标准：无" not in text
    assert "前置条件：无" not in text


def test_risk_items_text_render():
    """测试风险分析文本渲染与动态弹性伸缩。"""
    items = [
        {
            "category": "核心系统稳定性",
            "risk": "压测 QPS 超过 2000 时网关频繁断流",
            "severity": "high",
            "owner": "架构组",
            "impact": "交易链路雪崩并造成资损",
            "mitigation": "临时扩容 4 台网关，本周内完成异步化改造",
        },
        {
            "category": "核心系统稳定性",
            "risk": "鉴权网关跨机房调用单点超时抖动",
            "severity": "medium",
            "owner": "待认领",
            "impact": "高峰期引发重试风暴",
            "mitigation": None,
        },
    ]

    text = render_risk_items(items)
    assert "1. **[核心系统稳定性]**" in text
    assert "- 压测 QPS 超过 2000 时网关频繁断流(高风险 · 架构组)" in text
    assert "> 潜在危害：交易链路雪崩并造成资损" in text
    assert "> 应对措施：临时扩容 4 台网关，本周内完成异步化改造" in text
    assert "- 鉴权网关跨机房调用单点超时抖动(中风险)" in text
    assert "待认领" not in text
    assert "应对措施：无" not in text


def test_action_html_flow_render():
    """测试待办 HTML 呼吸感公文流排版。"""
    items = [
        {
            "category": "核心网关压测流控",
            "task": "交付音视频推流 SDK 适配补丁",
            "owner": "张伟",
            "priority": "high",
            "deadline": "周五 18:00 前",
            "deliverable": "压测报告与 API 文档",
            "dependency": "基础架构组签发临时 Token",
        },
        {
            "category": "核心网关压测流控",
            "task": "申请预发布独立集群机器配额",
            "owner": "待认领",
            "priority": "medium",
        },
    ]

    html = render_actions_html("待办清单测试", "", data={"actions": items})
    # 验证公文流基础结构
    assert "ck-flow-section" in html
    assert "核心网关压测流控" in html
    assert "2 项待办" in html
    assert "1. 交付音视频推流 SDK 适配补丁" in html
    assert "ck-flow-high" in html
    assert "高优先" in html
    assert "责任人: 张伟" in html
    assert "完成时限: 周五 18:00 前" in html
    assert "ck-flow-drawer" in html
    assert "交付标准：" in html
    assert "压测报告与 API 文档" in html
    assert "前置条件：" in html
    assert "基础架构组签发临时 Token" in html

    # 验证极简项（无抽屉，未分配责任人彻底隐去，绝不显示待认领）
    assert "2. 申请预发布独立集群机器配额" in html
    assert "责任人: 待认领" not in html
    assert "待认领" not in html

    # 验证无 emoji 和无伪复选框
    assert "[ ]" not in html
    assert "📌" not in html
    assert "🎯" not in html


def test_risk_html_flow_render():
    """测试风险 HTML 呼吸感公文流排版。"""
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
    assert "ck-flow-section" in html
    assert "核心网关高并发" in html
    assert "1 项风险" in html
    assert "1. 核心路由压测超过 2000 QPS 频繁断流" in html
    assert "ck-flow-high" in html
    assert "高风险" in html
    assert "跟进人: 架构组" in html
    assert "潜在危害：" in html
    assert "大促交易中断资损" in html
    assert "应对措施：" in html
    assert "临时扩容 4 台网关前置限流" in html

    assert "提升泵防汛隐患" in html
    assert "ck-flow-medium" in html
    assert "中风险" in html
    # 未指定跟进人彻底隐去，绝不显示待认领
    assert "跟进人: 待认领" not in html
    assert "待认领" not in html
    assert "现场未定（待现场勘测后补充预案）" in html

    # 验证无 emoji
    assert "💥" not in html
    assert "🛡️" not in html
    assert "🔴" not in html


def test_text_to_html_roundtrip():
    """测试 Markdown 文本解析到 HTML 渲染的链路稳定性。"""
    action_text = """
1. **[网关压测流控]**
   - 交付推流 SDK 补丁(高优先 · 张伟)
     > 完成时限：周五前
     > 交付标准：报告及文档
     > 前置条件：临时 Token
"""
    actions = _parse_actions_from_text(action_text)
    assert len(actions) == 1
    assert actions[0]["category"] == "网关压测流控"
    assert actions[0]["task"] == "交付推流 SDK 补丁"
    assert actions[0]["priority"] == "high"
    assert actions[0]["owner"] == "张伟"
    assert actions[0]["deadline"] == "周五前"
    assert actions[0]["deliverable"] == "报告及文档"
    assert actions[0]["dependency"] == "临时 Token"

    html = render_actions_html("待办测试", action_text)
    assert "交付推流 SDK 补丁" in html
    assert "高优先" in html
    assert "责任人: 张伟" in html
    assert "完成时限: 周五前" in html
    assert "交付标准：" in html
    assert "前置条件：" in html
