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
    # 验证独立轻卡片基础结构
    assert "ck-card" in html
    assert "核心网关压测流控" in html
    assert "交付音视频推流 SDK 适配补丁" in html
    assert "ck-pill-high" in html
    assert "高优先" in html
    assert "责任人: 张伟" in html
    assert "完成时限: 周五 18:00 前" in html
    assert "ck-card-drawer" in html
    assert "交付标准：" in html
    assert "压测报告与 API 文档" in html
    assert "前置条件：" in html
    assert "基础架构组签发临时 Token" in html

    # 验证极简项（无抽屉，未分配责任人彻底隐去，绝不显示待认领，无 1. 2. 序号与条数统计）
    assert "申请预发布独立集群机器配额" in html
    assert not re.search(r'class="ck-card-title">\s*\d+[\.、]', html)
    assert "项待办" not in html
    assert "责任人: 待认领" not in html
    assert "待认领" not in html

    # 验证无 emoji 和无伪复选框
    assert "[ ]" not in html
    assert "📌" not in html
    assert "🎯" not in html


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


def test_category_grouping_multi_items():
    """测试一个大点（业务板块）下聚拢多条事项，大点作为一张卡片，其内部聚合多条事项。"""
    action_text = """
1. **[现场实体整改]**
   - 细化检查验收组提出的问题并编制方案(中优先 · 田组长)
     > 交付标准：处理方案
   - 编制现场实体整改方案并逐一整改(中优先 · 龚总)
     > 交付标准：整改方案
   - 局部损伤修补与卫生打扫(中优先)
     > 完成时限：正式交付之前

2. **[内业资料]**
   - 汇总三个厂区资料于卢萨卡(中优先 · 龚总)
"""
    html = render_actions_html("多事项聚合测试", action_text)
    # 应只有 2 个卡片（2 个大点板块），而不是 4 个卡片
    assert html.count('class="ck-card ck-flow-group"') == 2
    # 事项总数为 4 条
    assert html.count('class="ck-flow-item"') == 4
    # 大点标题在卡片头部只出现一次
    assert html.count('<span class="ck-card-category-text">现场实体整改</span>') == 1
    assert html.count('<span class="ck-card-category-text">内业资料</span>') == 1


def test_text_priority_over_raw_data_and_generic_cat_suppression():
    """测试当同时传入 text 与 data 时，优先采用已聚类归纳的 text，避免逐条割裂与重复标题。"""
    raw_draft_items = [
        {"category": "人员统计数量完善", "task": "完善人员统计数量，将厂家服务人员等计入团队人员", "priority": "medium"},
        {"category": "特种人员证件更新", "task": "与国内人力资源对接，完善特种人员证件有效期更新", "priority": "medium"},
    ]
    grouped_text = """
2. **[人员履约和合同履约]**
   - 完善人员统计数量，将厂家服务人员等计入团队人员(中优先)
   - 与国内人力资源对接，完善特种人员证件有效期更新(中优先)
"""
    # 模拟 save_report_artifacts 同时把 text 与 data 传入
    html = render_actions_html("待办清单", grouped_text, data={"actions": raw_draft_items})

    # 1. 应当聚拢在宏观主题「人员履约和合同履约」下，只有 1 个卡片
    assert html.count('class="ck-card ck-flow-group"') == 1
    assert '<span class="ck-card-category-text">人员履约和合同履约</span>' in html
    # 2. 绝不应该出现草稿阶段细碎的临时标题作为独立卡片
    assert "人员统计数量完善" not in html
    assert "特种人员证件更新" not in html
    # 3. 事项都在该卡片内紧凑罗列
    assert html.count('class="ck-flow-item"') == 2

    # 测试通用分类无意义标题栏抑制
    generic_text = """
- 检查机房应急供电设备(高优先)
- 备份数据库配置文件(中优先)
"""
    html_gen = render_actions_html("待办清单", generic_text)
    assert '<span class="ck-card-category-text">综合待办</span>' not in html_gen
    assert '<span class="ck-card-category-text">综合事项</span>' not in html_gen
    assert html_gen.count('class="ck-flow-item"') == 2


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))


