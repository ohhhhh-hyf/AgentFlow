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
            "timing_anchor": "周五 18:00 前",
            "acceptance_criteria": "压测报告与 API 文档",
            "dependency": "基础架构组签发临时 Token",
        },
        {
            "category": "网关压测流控",
            "task": "申请预发布集群机器配额",
            "owner": "待认领",
            "timing_anchor": None,
            "acceptance_criteria": None,
            "dependency": None,
        },
    ]

    text = ActionItemsRender.render_items(items)
    assert "1. **[网关压测流控]**" in text
    assert "- 完成 SDK 适配补丁并进行 2000 QPS 压测 (责任人：张伟)" in text
    assert "> 时间节点：周五 18:00 前" in text
    assert "> 交付验收：压测报告与 API 文档" in text
    assert "> 前置依赖：基础架构组签发临时 Token" in text
    assert "- 申请预发布集群机器配额" in text
    assert "待认领" not in text
    # 极简项不应出现未明确占位符
    assert "时间节点：无" not in text
    assert "交付验收：无" not in text
    assert "前置依赖：无" not in text


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


def test_actions_risks_no_default_medium_fallback():
    """验证当待办与风险未显式指定级别时，HTML 渲染不默认兜底输出「中优先」或「中风险」，优雅留白。"""
    # 1. 待办纯净文本：无优先级标记
    clean_action_text = """
1. **[网关架构优化]**
   - 完成推流 SDK 适配补丁 (责任人：张伟)
     > 完成时限：周五 18:00 前
   - 申请预发布独立集群机器配额
"""
    actions = _parse_actions_from_text(clean_action_text)
    assert len(actions) == 2
    assert actions[0]["priority"] == ""
    assert actions[1]["priority"] == ""

    html_actions = render_actions_html("待办测试", clean_action_text)
    assert "中优先" not in html_actions
    assert "高优先" not in html_actions
    assert "低优先" not in html_actions
    assert "责任人: 张伟" in html_actions

    # 2. 风险纯净文本：无严重等级标记
    clean_risk_text = """
1. **[高并发系统治理]**
   - 核心路由压测超过 2000 QPS 频繁断流 (架构组)
     > 潜在危害：大促交易中断
   - 鉴权网关跨机房调用存在单点超时抖动
"""
    risks = _parse_risks_from_text(clean_risk_text)
    assert len(risks) == 2
    assert risks[0]["severity"] == ""
    assert risks[1]["severity"] == ""

    html_risks = render_risks_html("风险测试", clean_risk_text)
    assert "中风险" not in html_risks
    assert "高风险" not in html_risks
    assert "低风险" not in html_risks
    assert "跟进人: 架构组" in html_risks
    assert "大促交易中断" in html_risks




def test_actions_prompts_and_contracts_positive_hygiene():
    """验证待办提示词与契约已实现全正向引导，零禁止性恐吓词，零测试人名与工程泄漏。"""
    from domains.meeting.tasks.actions.prompts import (
        ACTION_ITEMS_GENERATION_SYSTEM_PROMPT,
        ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT,
        ACTION_ITEMS_RENDER_PROMPT,
    )
    from domains.meeting.tasks.actions.contracts import (
        ActionItemsGenerationContract,
        ActionItemsSupervisorContract,
    )

    combined = (
        ACTION_ITEMS_GENERATION_SYSTEM_PROMPT
        + ACTION_ITEMS_SUPERVISOR_DOMAIN_PROMPT
        + ACTION_ITEMS_RENDER_PROMPT
        + str(ActionItemsGenerationContract.to_output_contract())
        + str(ActionItemsSupervisorContract.to_output_contract())
    )

    # 1. 验证负向禁止性字眼清零
    for forbidden_word in ["严禁", "禁止", "杜绝", "草草收尾"]:
        assert forbidden_word not in combined, f"待办提示词或契约中仍包含负向禁止词: {forbidden_word}"

    # 2. 验证私有测试人名与领域泄漏项清零
    for leaked_term in ["申家坤", "徐玥", "930", "特种人员", "人员进出场资料闭环"]:
        assert leaked_term not in combined, f"待办提示词或契约中仍包含泄漏词汇: {leaked_term}"

    # 3. 验证评级梯队与分类打架内耗已消除
    assert "全选中优先" not in combined
    assert "未拉开梯度" not in combined


def test_risks_prompts_and_contracts_positive_hygiene():
    """验证风险提示词与契约已实现全正向引导，零禁止性恐吓词，零特定领域泄漏。"""
    from domains.meeting.tasks.risks.prompts import (
        RISK_GENERATION_SYSTEM_PROMPT,
        RISK_SUPERVISOR_DOMAIN_PROMPT,
        RISK_RENDER_PROMPT,
    )
    from domains.meeting.tasks.risks.contracts import (
        RiskGenerationContract,
        RiskSupervisorContract,
    )

    combined = (
        RISK_GENERATION_SYSTEM_PROMPT
        + RISK_SUPERVISOR_DOMAIN_PROMPT
        + RISK_RENDER_PROMPT
        + str(RiskGenerationContract.to_output_contract())
        + str(RiskSupervisorContract.to_output_contract())
    )

    # 1. 验证负向禁止性字眼清零
    for forbidden_word in ["严禁", "禁止", "杜绝", "绝不"]:
        assert forbidden_word not in combined, f"风险提示词或契约中仍包含负向禁止词: {forbidden_word}"

    # 2. 验证特定场景词汇软引导清零
    for leaked_term in ["会翻车", "防汛与排水隐患", "现场实体质量隐患"]:
        assert leaked_term not in combined, f"风险提示词或契约中仍包含泄漏词汇: {leaked_term}"

    # 3. 验证评级梯队内耗已消除
    assert "全选中风险" not in combined
    assert "扎堆中风险" not in combined


def test_action_items_report_validation_new_schema():
    """验证待办报告校验器（ActionItemsReport）完全兼容无 priority 及包含 timing_anchor/collaborators/acceptance_criteria 的新契约。"""
    from domains.meeting.reports import ActionItemsReport

    # 1. 纯新契约（无 priority，含时间节点、协同配合、交付验收）
    payload = {
        "actions": [
            {
                "category": "外业检查情况",
                "task": "检查并处理卢萨卡点提升桶位置雨水倒灌问题，通过技术措施解决",
                "owner": "施工组",
                "deadline": "会后",
                "timing_anchor": "会后",
                "collaborators": "运维团队",
                "acceptance_criteria": "通过技术措施解决雨水倒灌问题",
                "deliverable": "整改方案与复测记录",
                "dependency": "现场脚手架搭建就绪",
                "status": "explicit",
                "evidence": "检查并处理卢萨卡点提升桶位置雨水倒灌问题",
                "confidence": "high",
            }
        ],
        "quality_warning": None,
        "personalized_text": "### 外业检查情况\n- 检查并处理卢萨卡点提升桶位置雨水倒灌问题",
    }
    report = ActionItemsReport.validate(payload)
    assert len(report.actions) == 1
    act = report.actions[0]
    assert act["task"].startswith("检查并处理卢萨卡点")
    assert act["owner"] == "施工组"
    assert act["timing_anchor"] == "会后"
    assert act["acceptance_criteria"] == "通过技术措施解决雨水倒灌问题"
    assert "priority" not in act

    # 2. 遗留数据兼容（含 legacy priority）
    payload_legacy = {
        "actions": [
            {
                "task": "临时修复防汛板",
                "owner": "施工组",
                "deadline": "今天",
                "priority": "high",
                "status": "explicit",
                "evidence": "今天先把防汛板立起来",
                "confidence": "high",
            }
        ]
    }
    report_legacy = ActionItemsReport.validate(payload_legacy)
    assert len(report_legacy.actions) == 1
    assert report_legacy.actions[0]["priority"] == "high"


def test_action_items_assigned_actions_compatibility() -> None:
    """验证客观全员待办契约（assigned_actions）的校验器兼容性与渲染链路."""
    from domains.meeting.models import ActionItems
    from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender

    payload_assigned = {
        "assigned_actions": [
            {
                "category": "架构改造",
                "task": "完成新旧契约解耦与单测编写",
                "owner": "核心团队",
                "deadline": "周五",
                "timing_anchor": "周五前",
                "collaborators": "测试组",
                "acceptance_criteria": "全量单测通过",
                "deliverable": "PR",
                "dependency": "无",
                "status": "explicit",
                "evidence": "周五前完成解耦",
                "confidence": "high",
            }
        ],
        "unassigned_actions": [
            {
                "category": "日常维护",
                "task": "跟进线上告警指标监控",
                "owner": None,
                "deadline": None,
                "timing_anchor": None,
                "collaborators": None,
                "acceptance_criteria": None,
                "deliverable": None,
                "dependency": None,
                "status": "inferred",
                "evidence": "后续多关注监控",
                "confidence": "medium",
            }
        ],
    }

    # 1. ActionItems validate 校验器能够自动映射兼容
    inst = ActionItems.validate(payload_assigned)
    assert len(inst.my_actions) == 1
    assert inst.my_actions[0]["task"] == "完成新旧契约解耦与单测编写"
    assert len(inst.unassigned_actions) == 1
    assert hasattr(inst, "assigned_actions")
    assert inst.assigned_actions[0]["owner"] == "核心团队"

    # 2. 渲染器能够双键兼容读取并正确渲染清单
    state = {
        "objective_perspective": True,
        "lines": {"actions": {"draft": payload_assigned}},
    }
    extracted = ActionItemsRender.extract_actions(state)
    assert len(extracted) == 2
    rendered_text = ActionItemsRender.render_draft(state)
    assert "完成新旧契约解耦与单测编写" in rendered_text
    assert "核心团队" in rendered_text
    assert "跟进线上告警指标监控" in rendered_text
    # 3. 验证经过 LLMClient 结构化解析器时不会被剥离 assigned_actions
    import json
    from infra.llm.llmclient import LLMClient
    raw_json = json.dumps(payload_assigned)
    parsed = LLMClient._parse_and_validate(
        raw_json,
        ActionItems,
        allow_missing=frozenset({"my_actions", "delegated_actions"}),
    )
    assert len(parsed.assigned_actions) == 1
    assert len(parsed.my_actions) == 1
    assert parsed.assigned_actions[0]["task"] == "完成新旧契约解耦与单测编写"
    assert parsed.my_actions[0]["task"] == "完成新旧契约解耦与单测编写"


def test_understanding_contract_lightweight_for_actions_and_risks():
    """验证 actions 和 risks 单独或组合激活时，契约自动走轻量极简段落，且 actions 包含 decisions。"""
    from domains.meeting.meeting_core.contracts import (
        build_core_contract_for_tasks,
        is_actions_risks_only_tasks,
    )

    # 1. actions 单线：启用轻量段落，不含 context_and_reasoning，包含 decisions
    contract_str, omitted = build_core_contract_for_tasks(["actions"])
    assert "segment_title" in contract_str
    assert "context_and_reasoning" not in contract_str
    assert "key_facts" not in contract_str
    assert "decisions" in contract_str
    assert "decisions" not in omitted
    assert is_actions_risks_only_tasks(["actions"]) is True

    # 2. risks 单线：启用轻量段落，不含 context_and_reasoning
    contract_str_r, omitted_r = build_core_contract_for_tasks(["risks"])
    assert "segment_title" in contract_str_r
    assert "context_and_reasoning" not in contract_str_r
    assert "key_facts" not in contract_str_r
    assert is_actions_risks_only_tasks(["risks"]) is True

    # 3. actions + risks 组合：依然启用轻量段落
    contract_str_ar, omitted_ar = build_core_contract_for_tasks(["actions", "risks"])
    assert "segment_title" in contract_str_ar
    assert "context_and_reasoning" not in contract_str_ar
    assert is_actions_risks_only_tasks(["actions", "risks"]) is True

    # 4. 混入 minutes 或 minutes_trace：严格使用全量段落（包含 context_and_reasoning 和 key_facts）
    contract_str_m, _ = build_core_contract_for_tasks(["minutes", "actions"])
    assert "context_and_reasoning" in contract_str_m
    assert "key_facts" in contract_str_m
    assert is_actions_risks_only_tasks(["minutes", "actions"]) is False

    contract_str_t, _ = build_core_contract_for_tasks(["minutes_trace", "risks"])
    assert "context_and_reasoning" in contract_str_t
    assert "key_facts" in contract_str_t
    assert is_actions_risks_only_tasks(["minutes_trace", "risks"]) is False

    # 5. 开启跨会记忆：强制全量段落
    contract_str_mem, _ = build_core_contract_for_tasks(["actions"], memory_on=True)
    assert "context_and_reasoning" in contract_str_mem
    assert "key_facts" in contract_str_mem
    assert is_actions_risks_only_tasks(["actions"], memory_on=True) is False


def test_orchestrator_shared_context_supplies_transcript_for_actions_and_risks():
    """验证编排层为 actions 和 risks 注入会议原文与顺藤摸瓜指引，且 actions 包注入 decisions。"""
    from domains.meeting.orchestrator import MeetingAgentSystem

    orch = object.__new__(MeetingAgentSystem)
    state = {
        "perspective": "objective",
        "transcript": "【讨论实录】张三：我承诺周五前完成接口改造。李四：网关并发突破 10000 时存在熔断风险。王总：大家必须在周日前完成上线验收。",
        "meeting_understanding": {
            "meeting_purpose": "周例会",
            "scene": "通用",
            "speakers": [{"name": "张三"}, {"name": "李四"}, {"name": "王总"}],
            "session_segments": [{"segment_title": "架构改造"}],
            "decisions": ["王总明确：必须在周日前完成上线验收", "同意架构改造方案"],
            "action_hints": [{"action": "完成接口改造", "owner": "张三"}],
            "risk_hints": [{"risk": "网关并发突破 10000 时存在熔断风险", "owner": "李四"}],
        },
        "lines": {},
    }

    # 1. 验证 actions 上下文含原文与指引
    ctx_actions = orch._line_shared_context(state, "actions")
    assert "【讨论实录】张三：我承诺周五前完成接口改造" in ctx_actions
    assert "深度结合【会议原文】全面穷尽挖掘" in ctx_actions
    pack_actions = orch._meeting_pack(state, "actions")
    assert "decisions" in pack_actions
    assert "王总明确：必须在周日前完成上线验收" in pack_actions["directive_decisions"][0]

    # 2. 验证 risks 上下文含原文与指引
    ctx_risks = orch._line_shared_context(state, "risks")
    assert "【讨论实录】张三：我承诺周五前完成接口改造" in ctx_risks
    assert "深度结合【会议原文】全面穷尽挖掘" in ctx_risks


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))


