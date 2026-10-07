"""Tests for consensus_decision task refactoring.

Verifies:
1. Template existence and validation in resources/templates/consensus_decision.md
2. Auto-routing to default consensus_decision template in app/tasks.py
3. LINE_KINDS configuration as LLM_DOCUMENT
4. format_consensus_decision_markdown 2-section format, 3-column table, zero emoji
5. parse_consensus_decision_markdown parsing
6. render_consensus_decision_html and domain hook integration
"""
from __future__ import annotations

from pathlib import Path
import pytest

from app.config import (
    DEFAULT_CONSENSUS_DECISION_TEMPLATE,
    PROJECT_ROOT,
    resolve_template_format,
)
from app.tasks import _template_file
from core.runtime.kinds import LLM_DOCUMENT
from domains.meeting.domain_config import LINE_KINDS
from domains.meeting.hooks import HOOKS
from infra.exporters.html.consensus_decision import (
    format_consensus_decision_markdown,
    parse_consensus_decision_markdown,
    render_consensus_decision_html,
)


def test_template_file_and_content():
    """验证 resources/templates/consensus_decision.md 存在且内容合规。"""
    tpl_path = PROJECT_ROOT / "resources" / "templates" / "consensus_decision.md"
    assert tpl_path.is_file(), f"模板文件不存在: {tpl_path}"

    content = tpl_path.read_text(encoding="utf-8")
    assert "## [决策总览]" in content
    assert "## [决策细节]" in content
    assert "| 议题 | 共识成色 | 最终决议 |" in content
    assert "决策背景" in content
    assert "最终决议" in content
    assert "得失权衡" in content
    assert "讨论要点" in content

    # 验证模板门禁解析：检查不应报固定中括号字面量异常
    from core.templates.router._gate import scan_fixed_bracket_literals
    fixed_hits = scan_fixed_bracket_literals(content)
    assert not fixed_hits, f"模板不应包含固化的未替换方括号字面量: {fixed_hits}"


def test_template_registration_and_autorouting():
    """验证 consensus_decision 模板在注册表中且 app.tasks._template_file 能自动解析。"""
    # 注册表解析
    fmt = resolve_template_format(DEFAULT_CONSENSUS_DECISION_TEMPLATE)
    assert fmt is not None
    assert "## 决策总览" in fmt or "## [决策总览]" in fmt

    # 留空自动解析
    resolved_path = _template_file("meeting", "consensus_decision", "")
    assert resolved_path is not None
    resolved_content = resolved_path.read_text(encoding="utf-8")
    assert "决策总览" in resolved_content
    assert "决策细节" in resolved_content


def test_domain_line_kind():
    """验证 consensus_decision 为 LLM_DOCUMENT。"""
    assert LINE_KINDS["consensus_decision"] == LLM_DOCUMENT


def test_format_consensus_decision_markdown():
    """验证 Markdown 格式化：两栏结构、首屏3列表格极简决议、4维度顺序(背景->讨论->权衡->最终决议)、子列表分点、零 emoji。"""
    draft = {
        "summary": {"health_headline": "全局共识收敛良好"},
        "issues": [
            {
                "topic": "网关架构自研",
                "consensus_grade": "hard_alignment",
                "accord": "全场一致决定由技术中台牵头推行自研轻量网关方案，10月25日前完成首轮接口规范评审与立项，各业务线排期按时配合联调改造。",
                "trigger": "现有商业网关授权即将到期，高并发场景下出现毛刺瓶颈。",
                "pro_side": {"speakers": ["技术中台"], "stance": "内部原型已跑通自研风险可控"},
                "con_side": {"speakers": ["业务线"], "stance": "过渡期内严禁影响主干发版"},
                "trade_off": {
                    "gain": "彻底消除商业授权费用并预计提升35%吞吐量",
                    "sacrifice": "需抽调2名核心研发投入3周工期",
                },
                "key_quote": "原型已跑通，风险可控。",
            },
            {
                "topic": "周会时间固定调整",
                "consensus_grade": "conditional_concession",
                "accord": "自下周起常规周会固定调整为每周二上午10:00召开。",
                "trigger": "原周五下午例会常与跨部门紧急发版冲突。",
                # 无 trade_off，无 pro/con -> 弹性缺项
            },
        ],
    }

    md = format_consensus_decision_markdown(draft, title="架构方案评审会")

    # 两栏结构
    assert "## 决策总览" in md
    assert "## 决策细节" in md

    # 3列表格：最终决议极简动作定调（15-25字）
    assert "| 议题 | 共识成色 | 最终决议 |" in md
    assert "| **网关架构自研** | [一致赞成] | 全场一致决定由技术中台牵头推行自研轻量网关方案。 |" in md
    assert "| **周会时间固定调整** | [附带前提] | 自下周起常规周会固定调整为每周二上午10:00召开。 |" in md

    # 决策细节顺序：背景 -> 讨论要点 -> 得失权衡 -> 最终决议 (压轴)
    assert "### 1. 网关架构自研" in md
    pos_bg = md.find("- **决策背景**：")
    pos_ds = md.find("- **讨论要点**：")
    pos_td = md.find("- **得失权衡**：")
    pos_ac = md.find("- **最终决议**：")

    assert pos_bg != -1 and pos_ds != -1 and pos_td != -1 and pos_ac != -1
    assert pos_bg < pos_ds < pos_td < pos_ac, "四组顺序必须为：背景 -> 讨论要点 -> 得失权衡 -> 最终决议"

    # 子列表分点
    assert "  - 现有商业网关授权即将到期，高并发场景下出现毛刺瓶颈。" in md
    assert "  - 技术中台主张内部原型已跑通自研风险可控" in md
    assert "  - 业务线关注过渡期内严禁影响主干发版" in md
    assert "  - 收益：彻底消除商业授权费用并预计提升35%吞吐量" in md
    assert "  - 代价：需抽调2名核心研发投入3周工期" in md
    assert "  - 全场一致决定由技术中台牵头推行自研轻量网关方案" in md

    # 议题2弹性缺项验证（无 trade_off 与讨论要点则不输出，决议依然压轴）
    assert "### 2. 周会时间固定调整" in md
    pos_bg2 = md.find("### 2. 周会时间固定调整")
    chunk2 = md[pos_bg2:]
    assert "- **决策背景**：" in chunk2
    assert "- **最终决议**：" in chunk2
    assert "- **讨论要点**：" not in chunk2
    assert "- **得失权衡**：" not in chunk2

    # 严禁任何 emoji
    import re
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe0f\u200d]|[\u2300-\u23ff]|[\u2b50\u2b55]"
    )
    assert not emoji_pattern.search(md), f"Markdown 包含 emoji: {emoji_pattern.findall(md)}"


def test_parse_and_html_rendering():
    """验证 Markdown 解析以及 HTML 导出（含状态微胶囊、子列表、决议压轴、零 emoji）。"""
    sample_md = """# 架构方案评审会 · 共识决策

## 决策总览

| 议题 | 共识成色 | 最终决议 |
| :--- | :---: | :--- |
| **网关架构自研** | [一致赞成] | 确定自研轻量网关。 |
| **老接口兼容方案** | [附带前提] | 采用双轨并行过渡机制。 |
| **测试环境独占** | [争执未决] | 各方存在争议，会后继续拉齐。 |

## 决策细节

### 1. 网关架构自研
- **决策背景**：
  - 商业授权即将到期，急需自主可控方案。
- **讨论要点**：
  - 技术中台强调原型已跑通风险可控。
  - 业务线关注主干发版不能受阻。
- **得失权衡**：
  - 收益：彻底消除商业授权费用。
  - 代价：短期消耗2名核心研发工期。
- **最终决议**：
  - 确定由技术中台牵头自研轻量网关并于10月底落地。

### 2. 老接口兼容方案
- **决策背景**：
  - 防止老业务直接调用异常。
- **最终决议**：
  - 采用双轨并行过渡机制，下季度末强制下线。

### 3. 测试环境独占
- **决策背景**：
  - 多条线抢占同一套环境导致阻塞。
- **讨论要点**：
  - 运维与研发各执一词未能达成一致。
- **最终决议**：
  - 各方存在争议，会后由负责人组织专题拉齐。
"""
    parsed = parse_consensus_decision_markdown(sample_md)
    assert len(parsed["overview"]) == 3
    assert len(parsed["issues"]) == 3

    issue1 = parsed["issues"][0]
    assert issue1["topic"] == "网关架构自研"
    assert issue1["brief_accord"] == "确定自研轻量网关。"
    assert "确定由技术中台牵头" in issue1["accord"]
    assert len(issue1["discussion_items"]) == 2
    assert len(issue1["tradeoff_items"]) == 2

    # HTML 渲染
    html = render_consensus_decision_html("架构方案评审会", sample_md)
    assert "<!doctype html>" in html
    assert "决策总览" in html
    assert "决策细节" in html

    # 状态微胶囊 (Status Pills)
    assert "cd-pill-hard" in html
    assert "cd-pill-conditional" in html
    assert "cd-pill-disagreement" in html
    assert "一致赞成" in html
    assert "附带前提" in html
    assert "争执未决" in html

    # 表格展示 brief_accord
    assert "确定自研轻量网关。" in html

    # 卡片细节：子列表与最终决议压轴高亮
    assert "cd-card" in html
    assert "cd-val-list" in html
    assert "cd-row-accord" in html
    assert "商业授权即将到期，急需自主可控方案。" in html
    assert "确定由技术中台牵头自研轻量网关并于10月底落地。" in html

    # 验证 HTML 中卡片内最终决议在得失权衡之后
    pos_html_td = html.find("得失权衡")
    pos_html_ac = html.find('<div class="cd-row cd-row-accord">', pos_html_td)
    assert pos_html_ac != -1, "HTML 中卡片最终决议应在得失权衡之后压轴渲染"

    # 严禁任何 emoji
    import re
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf\ufe0f\u200d]|[\u2300-\u23ff]|[\u2b50\u2b55]"
    )
    assert not emoji_pattern.search(html), f"HTML 包含 emoji: {emoji_pattern.findall(html)}"


def test_hooks_html_for_consensus_decision():
    """验证 domains.meeting.hooks.HOOKS.html_for('consensus_decision', ...) 正确分发。"""
    sample_text = """# 会议 · 共识决策

## 决策总览

| 议题 | 共识成色 | 最终决议 |
| :--- | :---: | :--- |
| **测试议题** | [一致赞成] | 确定按方案A推进 |

## 决策细节

### 1. 测试议题
- **决策背景**：现状痛点
- **最终决议**：确定按方案A推进
"""
    html = HOOKS.html_for("consensus_decision", "测试会议", sample_text, {})
    assert html is not None
    assert "<!doctype html>" in html
    assert "cd-pill-hard" in html
    assert "测试议题" in html


def test_outputs_export_integration(tmp_path):
    """验证 infra.exporters.outputs.save_report_artifacts 对 consensus_decision 正确写出 md 与 html。"""
    from app.config import load_domain
    from infra.exporters.outputs import save_report_artifacts

    ctx = load_domain("meeting")
    ctx.user_id = "test_user"
    sample_text = """# 架构决策 · 共识决策

## 决策总览

| 议题 | 共识成色 | 最终决议 |
| :--- | :---: | :--- |
| **自研网关** | [一致赞成] | 确定自研方案并于10月底落地 |

## 决策细节

### 1. 自研网关
- **决策背景**：商业授权到期
- **最终决议**：确定自研方案并于10月底落地
"""
    report = {"text": sample_text, "title": "架构决策"}
    paths = save_report_artifacts(ctx, "consensus_decision", report)

    assert "text" in paths
    assert "html" in paths
    assert paths["text"].name == "consensus_decision.md"
    assert paths["html"].name == "consensus_decision.html"

    md_content = paths["text"].read_text(encoding="utf-8")
    assert "决策总览" in md_content
    assert "自研网关" in md_content

    html_content = paths["html"].read_text(encoding="utf-8")
    assert "<!doctype html>" in html_content
    assert "cd-pill-hard" in html_content
    assert "自研网关" in html_content


def test_gate_whitelist_consensus_tags():
    """验证模板门禁 validate_rendered_output 不会将 [一致赞成]、[附带前提]、[争执未决] 误判为残留占位符。"""
    from core.templates.router._gate import validate_rendered_output
    tpl_path = PROJECT_ROOT / "resources" / "templates" / "consensus_decision.md"
    template = tpl_path.read_text(encoding="utf-8")

    sample_output = """# 测试会议 · 共识决策

## 决策总览

| 议题 | 共识成色 | 最终决议 |
| --- | :---: | --- |
| 人员履约与合同履约资料完善 | [一致赞成] | 施工部和管理组完善进出场时间 |
| 现场实体整改事项 | [附带前提] | 管理组和总包单位制定整改方案 |
| 环境排期事项 | [争执未决] | 会后由负责人组织专题拉齐 |

## 决策细节

### 1. 人员履约与合同履约资料完善
- **决策背景**：
  - 需在验收报告前闭合资料。
- **最终决议**：
  - 施工部按期完成闭合。
"""
    errors = validate_rendered_output(sample_output, template)
    leftover_errors = [e for e in errors if "输出残留占位符" in e]
    assert not leftover_errors, f"共识状态标签被误报为残留占位符: {leftover_errors}"


def test_parse_and_render_unbolded_variants():
    """验证模型即便产出未加粗小标题（如 决策背景：、讨论要点：、得失权衡：、最终决议：），HTML 依然能完整解析与渲染各栏。"""
    unbolded_md = """## 决策总览

| 议题 | 共识成色 | 最终决议 |
| --- | :---: | --- |
| 人员履约与合同履约资料完善 | 一致赞成 | 施工部完善资料并于报告前闭合 |

## 决策细节

### 1. 人员履约与合同履约资料完善

决策背景：
- 受疫情及本项目作为EPC项目的特点影响，人员资料尚需完善。
- 上述事项需在验收报告形成之前完成闭合。

讨论要点：
- 验收组要求施工部和管理组进一步完善进出场时间及护照资料。
- 验收组指出技术组未将厂家服务人员计入团队。

得失权衡：
- 收益：人员履约资料完整闭合，验收报告可顺利出具。
- 代价：管理组需投入额外人力核对护照及更新资料。

最终决议：
- 施工部和管理组完善相关资料并在验收报告形成之前完成闭合。
"""
    parsed = parse_consensus_decision_markdown(unbolded_md)
    assert len(parsed["issues"]) == 1
    issue = parsed["issues"][0]

    assert len(issue["background_items"]) == 2
    assert "受疫情" in issue["background_items"][0]
    assert len(issue["discussion_items"]) == 2
    assert "验收组要求" in issue["discussion_items"][0]
    assert len(issue["tradeoff_items"]) == 2
    assert "收益：人员履约资料完整闭合" in issue["tradeoff_items"][0]
    assert "施工部和管理组完善相关资料" in issue["accord"]

    # 验证 HTML 渲染包含所有四栏且不是只有最终决议
    html = render_consensus_decision_html("验收会", unbolded_md)
    assert "决策背景" in html
    assert "受疫情及本项目作为EPC项目的特点影响" in html
    assert "讨论要点" in html
    assert "验收组要求施工部和管理组进一步完善" in html
    assert "得失权衡" in html
    assert "收益：人员履约资料完整闭合" in html
    assert "最终决议" in html
    assert "施工部和管理组完善相关资料" in html


