# 拆分自 test_core_schema_artifacts.py，覆盖：test_action_items_render, test_risk_items_render…

"""tools/core 零 LLM 自测：画像选档（``profile=user`` → data/{uid}/user.json）、清洗、职业模板合并。

用法::

    python -m tests.test_core
"""

from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from core.runner.profiles import (
    classify_profile,
    filter_identity_fields,
    is_user_profile_file,
    load_role_mapping,
    read_user_profile,
    resolve_profile_file,
    resolve_role_template,
    resolve_role_to_template_key,
    sanitize_user_profile,
    user_profile_path,
)
from tests.support.expectations import expect
import pytest

pytestmark = pytest.mark.integration

def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        data if isinstance(data, str) else json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    return path

def _root(tmp: Path) -> Path:
    """搭一个最小工程根：公共画像目录 + data/{uid}/。"""
    profiles = tmp / "assets" / "profiles"
    _write(profiles / "object.json", {"name": "", "perspective": "objective"})
    _write(
        profiles / "developer.json",
        {
            "name": "开发人员",
            "role": "软件研发与系统实现工程师",
            "persona_type": "role_template",
            "perspective": "personal",
            "focus_areas": ["需求、验收标准与技术实现方案", "任务分工、排期与进度节点"],
            "responsibilities": ["理解需求并确认技术实现方案"],
            "constraints": ["不臆造技术可行性结论"],
        },
    )
    return tmp

USER_OK = {
    "name": "赵衡",
    "name_aliases": ["小赵", "赵工"],
    "role": "后端工程师",
    "role_template": "developer",
    "personality": "务实，讨厌含糊的截止日期",
    "preferences": ["先写我的待办和接口依赖"],
}

def test_action_items_render() -> None:
    """验证待办事项卡片式清单（4个核心维度、自适应输出、无原句）及降级拼装。"""
    from domains.meeting.tasks.actions.steps.actions_render import ActionItemsRender
    from domains.meeting.memory.render import _parse_actions_from_text, render_actions_html

    # 1. 结构化草稿测试（扁平 actions）
    state = {
        "lines": {
            "actions": {
                "draft": {
                    "actions": [
                        {
                            "title": "音视频SDK推流适配",
                            "item": "完成音视频推流协议适配与压测",
                            "owner": "张伟",
                            "deadline": "周五前",
                            "collaborators": [],
                            "acceptance_criteria": "压测报告及文档",
                            "dependency": "需后端先提供鉴权Token",
                            "evidence": "张伟周五前把推流适配好",
                        },
                        {
                            "title": "联调鉴权网关",
                            "item": "与基础架构团队联调鉴权网关",
                            "owner": "张伟",
                            "deadline": None,
                            "collaborators": [],
                            "acceptance_criteria": None,
                            "dependency": None,
                            "evidence": "张伟再跟架构联调一下",
                        },
                        {
                            "title": "梳理数据看表口径",
                            "item": "梳理数据看表口径",
                            "owner": "李莉",
                            "deadline": "09-28",
                            "collaborators": [],
                            "acceptance_criteria": None,
                            "dependency": None,
                            "evidence": "李莉把看表口径理一下",
                        },
                        {
                            "title": "申请预发布压测机器",
                            "item": "申请预发布压测机器",
                            "owner": None,
                            "deadline": None,
                            "collaborators": [],
                            "acceptance_criteria": "机器分配就绪",
                            "dependency": None,
                            "evidence": "尽快去运维申请压测机",
                        },
                    ],
                }
            }
        }
    }
    draft_text = ActionItemsRender.render_draft(state)
    expect("**音视频SDK推流适配**： 完成音视频推流协议适配与压测（责任方：张伟）"
        in draft_text, "待办草稿标题与正文同一行并带责任方", draft_text)
    expect("**联调鉴权网关**： 与基础架构团队联调鉴权网关（责任方：张伟）" in draft_text, "包含第二条待办", draft_text)
    expect("**梳理数据看表口径**： 梳理数据看表口径（责任方：李莉）" in draft_text, "包含第三条待办", draft_text)
    expect("**申请预发布压测机器**： 申请预发布压测机器" in draft_text, "包含第四条待办", draft_text)
    expect("待认领" not in draft_text, "未分配待办无待认领", draft_text)
    expect(" - 时间节点：周五前" in draft_text, "包含交付时限：周五前", draft_text)
    expect(" - 验收交付：压测报告及文档" in draft_text, "包含交付标准：压测报告及文档", draft_text)
    expect(" - 前置依赖：需后端先提供鉴权Token" in draft_text, "包含前置条件：需后端先提供鉴权Token", draft_text)
    expect(" - 验收交付：机器分配就绪" in draft_text, "包含交付标准：机器分配就绪", draft_text)
    expect("张伟周五前把推流适配好" not in draft_text, "彻底去除原句引用", draft_text)

    # 2. 空状态测试
    empty_state = {"lines": {"actions": {"draft": {}}}}
    empty_text = ActionItemsRender.render_draft(empty_state)
    expect(empty_text == "暂无明确待办事项", "空待办输出暂无明确待办事项", empty_text)

    # 3. HTML 与解析测试
    parsed = _parse_actions_from_text(draft_text)
    expect(len(parsed) == 4, "文本能正确解析出 4 条待办", str(parsed))
    expect(parsed[0].get("title") == "音视频SDK推流适配", "解析项 1 标题正确", str(parsed[0]))
    expect(parsed[0].get("owner") == "张伟", "解析项 1 包含责任人张伟", str(parsed[0]))
    expect(parsed[0].get("acceptance_criteria") == "压测报告及文档", "解析项 1 包含交付物", str(parsed[0]))
    expect(parsed[0].get("dependency") == "需后端先提供鉴权Token", "解析项 1 包含依赖", str(parsed[0]))
    expect(parsed[1].get("item") == "与基础架构团队联调鉴权网关", "解析项 2 正文正确", str(parsed[1]))
    expect(not parsed[3].get("owner"), "解析项 4 无未确定责任人", str(parsed[3]))
    html = render_actions_html("待办事项清单", draft_text)
    expect("ck-flow-item" in html, "HTML 公文流渲染成功包含 ck-flow-item", html[:200])
    expect("完成音视频推流协议适配与压测" in html, "HTML 包含待办正文", html[:500])

    # 4. ActionItemsReport 校验测试
    from domains.meeting.reports import ActionItemsReport
    report_data = {
        "actions": [
            {
                "title": "接口联调",
                "item": "完成音视频推流协议适配与压测",
                "owner": "张伟",
                "deadline": "周五前",
                "collaborators": [],
                "acceptance_criteria": "压测报告及文档",
                "dependency": "需后端先提供鉴权Token",
                "evidence": "张伟周五前把推流适配好",
            }
        ],
        "quality_warning": None,
        "personalized_text": None,
    }
    validated_report = ActionItemsReport.validate(report_data)
    expect(validated_report.actions[0]["title"] == "接口联调", "ActionItemsReport 校验成功通过且保留扁平字段", str(validated_report))


def test_risk_items_render() -> None:
    """验证风险分析卡片式清单（4个核心维度、自适应输出、无原句）及降级拼装。"""
    from domains.meeting.tasks.risks.steps.risks_render import RiskRender
    from domains.meeting.memory.render import _parse_risks_from_text, render_risks_html

    # 1. 结构化草稿测试（含具象短语话题多风险聚合）
    state = {
        "lines": {
            "risks": {
                "draft": {
                    "risks": [
                        {
                            "category": "核心网关压测流控与断流",
                            "risk": "核心路由在压测 QPS 超过 2000 时出现频繁断流",
                            "severity": "high",
                            "impact": "大促峰值期间接入层存在服务雪崩风险",
                            "mitigation": "周工本周内完成异步队列削峰改造并组织复测",
                            "owner": "周工",
                            "source": "张工说QPS一上两千就断流",
                        },
                        {
                            "category": "核心网关压测流控与断流",
                            "risk": "鉴权网关跨机房调用存在单点超时抖动",
                            "severity": "medium",
                            "impact": "高峰期引发级联超时重试，拖垮下游服务",
                            "mitigation": "增设本地缓存与降级熔断开关",
                            "owner": "周工",
                        },
                        {
                            "category": "跨团队基础鉴权Token审批",
                            "risk": "跨团队联调所需的基础鉴权 Token 审批流程过长",
                            "severity": "high",
                            "impact": "直接导致音视频推流 SDK 联调进度延期 1-2 天",
                            "mitigation": None,
                            "owner": None,
                            "source": "审批卡了三天了",
                        },
                        {
                            "category": "老旧机型暗黑模式对比度",
                            "risk": "部分老旧机型在暗黑模式下存在文本对比度缺失",
                            "severity": "low",
                            "impact": "极端夜间场景下轻微影响用户阅读体验",
                            "mitigation": "",
                            "owner": "",
                        },
                    ]
                }
            }
        }
    }
    draft_text = RiskRender.render_draft(state)
    expect("1. **[核心网关压测流控与断流]**" in draft_text, "风险草稿包含[核心网关压测流控与断流]业务板块主行", draft_text)
    expect("核心路由在压测 QPS 超过 2000 时出现频繁断流 (周工)" in draft_text, "包含具体隐患及内联责任人周工", draft_text)
    expect("鉴权网关跨机房调用存在单点超时抖动 (周工)" in draft_text, "同板块事项聚拢在[核心网关压测流控与断流]下", draft_text)
    expect("2. **[跨团队基础鉴权Token审批]**" in draft_text, "包含[跨团队基础鉴权Token审批]业务板块主行", draft_text)
    expect("跨团队联调所需的基础鉴权 Token 审批流程过长" in draft_text and "待认领" not in draft_text, "未指定责任人时不输出待认领", draft_text)
    expect("3. **[老旧机型暗黑模式对比度]**" in draft_text, "包含[老旧机型暗黑模式对比度]业务板块主行", draft_text)
    expect("> 风险级别：" not in draft_text, "不再单列风险级别行", draft_text)
    expect("> 责任主体：" not in draft_text, "不再单列责任主体行", draft_text)
    expect("> 潜在危害：大促峰值期间接入层存在服务雪崩风险" in draft_text, "包含潜在危害：大促峰值期间接入层存在服务雪崩风险", draft_text)
    expect("> 现场对策：周工本周内完成异步队列削峰改造并组织复测" in draft_text, "包含应对措施：周工本周内完成异步队列削峰改造并组织复测", draft_text)
    expect("现场对策：无" not in draft_text and "现场对策：未提及" not in draft_text, "无应对措施时自适应隐去整行", draft_text)
    expect("张工说QPS一上两千就断流" not in draft_text, "彻底去除原句引用", draft_text)
    expect("## 一、高风险" not in draft_text and "## 二、中低风险" not in draft_text, "无大标题分组", draft_text)

    # 2. 空状态测试
    empty_state = {"lines": {"risks": {"draft": {}}}}
    empty_text = RiskRender.render_draft(empty_state)
    expect(empty_text == "暂无明确风险事项", "空风险输出暂无明确风险事项", empty_text)

    # 3. HTML 与解析测试
    parsed = _parse_risks_from_text(draft_text)
    expect(len(parsed) == 4, "文本能正确解析出 4 条风险", str(parsed))
    expect(parsed[0].get("category") == "核心网关压测流控与断流", "解析项 1 业务板块正确", str(parsed[0]))
    expect(parsed[0].get("owner") == "周工", "解析项 1 责任人为周工", str(parsed[0]))
    expect("削峰改造" in str(parsed[0].get("mitigation")), "解析项 1 包含应对方案", str(parsed[0]))
    expect(parsed[1].get("category") == "核心网关压测流控与断流", "解析项 2 同属网关架构", str(parsed[1]))
    expect(not parsed[2].get("owner"), "解析项 3 无责任人", str(parsed[2]))
    html = render_risks_html("风险分析", draft_text)

    expect("ck-flow-item" in html, "HTML 公文流渲染成功包含 ck-flow-item", html[:200])
    expect("待认领" not in html, "HTML 公文流不包含待认领", html[:200])
