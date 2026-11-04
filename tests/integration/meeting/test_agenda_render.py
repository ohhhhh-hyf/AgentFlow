# 拆分自原大文件，保留：test_markdown_and_html_render, test_agenda_minutes_categories_rendering…

"""tests/integration/meeting/test_agenda_pipeline.py -- 议程驱动型会议纪要端到端生成工作流集成测试。"""

from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import docx
import pytest
from domains.meeting.agenda_engine import (
    clear_agenda_engine_cache,
    probe_valid_agendas,
    process_agenda_for_minutes,
)
from domains.meeting.agenda_vision import (
    agenda_plan_to_markdown,
    vision_json_to_agenda_plan,
)
from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    clear_agenda_parser_cache,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    clear_alignment_cache,
    group_transcript_blocks,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
    SingleAgendaItemModel,
)
from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_render import (
    AgendaMinutesRender,
)
from infra.exporters.html.agenda_minutes import (
    format_agenda_minutes_markdown,
    render_agenda_minutes_html,
)

PROJECT_ROOT = Path(__file__).resolve().parent

while PROJECT_ROOT.parent != PROJECT_ROOT and not (PROJECT_ROOT / "domains").exists():
    PROJECT_ROOT = PROJECT_ROOT.parent

AGENDA_DIR = (
    PROJECT_ROOT / "data" / "1" / "agenda"
    if (PROJECT_ROOT / "data" / "1" / "agenda").exists()
    else PROJECT_ROOT / "agenda"
)

_EN_AGENDA_JSON = {
    "theme": "Architecture Workshop",
    "date_time": "2026-10-27",
    "attendees": ["Facilitator"],
    "agenda_items": [
        {"seq": "01", "title": "Opening Remarks"},
        {"seq": "02", "title": "Architecture Review"},
        {"seq": "03", "title": "Release Plan"},
    ],
}

_EN_TRACK_B_TRANSCRIPT = (
    "[00:00:05] Speaker 1: Good morning everyone. Welcome.\n\n"
    "[00:00:15] Speaker 1: Let's start with the opening remarks.\n\n"
    "[00:05:00] Speaker 2: Now let's move on to the architecture review. "
    "The gateway redesign reduces latency to 120 ms.\n\n"
    "[00:15:00] Speaker 3: Next, the release plan. "
    "We have three milestones and will launch in December.\n"
)

def _clear_all_agenda_caches() -> None:
    clear_agenda_parser_cache()
    clear_alignment_cache()
    clear_agenda_engine_cache()

def test_markdown_and_html_render():
    """测试 Markdown 与 HTML 双模态渲染产物。"""
    draft = {
        "meeting_meta": {
            "theme": "智慧域商用发布评审",
            "date_time": "2026/06/15 16:00-18:00",
            "attendees_summary": "徐锋、高雄、刘畅、陆敬怡",
            "agenda_stats": "既定议题共 2 项（有效审议 1 项 · 本次未讨论 1 项）",
            "overview_headline": "海外翻译顺利过会，未讨论议题顺延。",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "翻译海外HiTranslationService 21.1.1.300商用版本发布",
                "presenter": "刘畅",
                "time_range": "00:20 ~ 00:34",
                "status_tag": "[审议通过]",
                "proposal_highlights": ["推进俄罗斯首站存储与新加坡集群部署。"],
                "deliberation_details": {
                    "key_metrics": ["时延保持在 120ms 以内", "双关流程已全部闭环"],
                    "feedback_concerns": ["高雄关注国内海外版本是否分拆及现网影响。"],
                },
                "resolution": "会议原则同意该版本商用发布，要求按五要素闭环报告。",
                "action_commitments": [
                    {"owner": "刘畅", "task": "补齐五要素闭环报告", "deadline": "6月17日"}
                ],
                "discussion_state": "discussed",
            },
            {
                "agenda_seq": "02",
                "agenda_title": "HAG 3.6.5.300版本商用发布评审",
                "presenter": "沙彬斌、陈啟锴",
                "status_tag": "[本次未讨论]",
                "proposal_highlights": ["既定议题全称：HAG 3.6.5.300版本商用发布评审"],
                "deliberation_details": {"key_metrics": [], "feedback_concerns": []},
                "resolution": "现场录音转写未见针对本议题的汇报或审议讨论记录，建议后续单独对齐或顺延至下期例会。",
                "action_commitments": [],
                "discussion_state": "skipped",
            },
        ],
        "adhoc_items": [
            {
                "title": "全网现网发布安全排查要求",
                "speaker": "高雄",
                "content": "强调各团队严格落实双关与配置隔离，严防现网逃逸。",
                "action": "各模块负责人会后逐项排查确认。",
            }
        ],
    }

    # 1. 验证 Markdown 格式
    md_output = format_agenda_minutes_markdown(draft)
    assert "# 议程纪要" in md_output
    assert "与会人员" not in md_output
    assert "## 议题总览" in md_output
    assert "第一部分" not in md_output
    assert "| 翻译海外HiTranslationService 21.1.1.300商用版本发布 | 刘畅 | 00:20 ~ 00:34 | `审议通过` |" in md_output
    assert "| HAG 3.6.5.300版本商用发布评审 | 沙彬斌、陈啟锴 | — | `本次未讨论` |" in md_output
    assert "## 议题分析" in md_output
    assert "第二部分" not in md_output
    assert "### 翻译海外HiTranslationService 21.1.1.300商用版本发布" in md_output
    assert "#### 1. 背景与目标" in md_output
    assert "#### 2. 核心内容" in md_output
    assert "#### 3. 核心认知" in md_output
    assert "#### 4. 后续行动" in md_output
    assert "总体评价" not in md_output
    assert "第三部分" not in md_output
    assert "临时追加议题" not in md_output

    # 2. 验证 HTML 格式（LaTeX Paper 风格，无 emoji）
    html_output = render_agenda_minutes_html("智慧域商用发布评审", md_output, draft)
    assert "<!DOCTYPE html>" in html_output
    assert "<title>议程纪要</title>" in html_output
    assert "<h1>议程纪要</h1>" in html_output
    assert "与会人员" not in html_output
    assert "ck-doc" in html_output
    assert "议题总览" in html_output
    assert '<th class="col-time">议题时长</th>' in html_output
    assert '<th class="col-status">结论定调</th>' in html_output
    assert "col-actions" not in html_output
    assert "待办与要求" not in html_output
    assert "议题分析" in html_output
    assert "背景与目标" in html_output
    assert "核心内容" in html_output
    assert "核心认知" in html_output
    assert "后续行动" in html_output
    assert "col-seq" not in html_output
    assert "总体评价与导向" not in html_output
    assert "badge-approved" in html_output
    assert "badge-skipped" in html_output
    assert "card-skipped" in html_output
    assert "card-skipped-body" in html_output
    assert "skipped-banner" in html_output
    # 验证去除 AI 味：彻底清除 emoji 符号
    for emoji in ["📅", "📊", "👥", "📋", "📑", "💬", "📌", "ℹ️"]:
        assert emoji not in html_output
    # 验证元信息与未讨论横幅不使用斜体
    assert ".ck-doc-meta {\n      font-style: normal;" in html_output
    assert ".skipped-banner {\n      background: #f2efe8;\n      border-radius: 2px;\n      padding: 2px 8px;\n      font-size: 0.78rem;\n      color: #666666;\n      font-style: normal;" in html_output

    # 3. 验证 Render 类的 render_draft 与 extract_structure
    state = {"lines": {"agenda_minutes": {"draft": draft}}}
    assert AgendaMinutesRender.render_draft(state).startswith("# 议程纪要")
    extracted = AgendaMinutesRender.extract_structure(state)
    assert len(extracted) == 2
    assert extracted[0]["agenda_seq"] == "01"


def test_agenda_minutes_categories_rendering():
    """测试评审类(approval)、非审批类(share/consensus)的状态定调与差异化排版。"""
    from domains.meeting.tasks.agenda_minutes.contracts import (
        normalize_status_tag,
        STATUS_TAG_APPROVED,
        STATUS_TAG_CONDITIONAL,
        STATUS_TAG_REJECTED,
        STATUS_TAG_SKIPPED,
        STATUS_TAG_EMPTY,
    )
    from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import SingleAgendaItemModel

    # 1. 验证归一化逻辑
    assert normalize_status_tag("通过", category="approval") == STATUS_TAG_APPROVED
    assert normalize_status_tag("材料不齐待补充", category="approval") == STATUS_TAG_REJECTED
    assert normalize_status_tag("原则同意", category="approval") == STATUS_TAG_CONDITIONAL
    assert normalize_status_tag("任何状态", category="share") == STATUS_TAG_EMPTY
    assert normalize_status_tag("达成一致", category="consensus") == STATUS_TAG_EMPTY
    assert normalize_status_tag("存在技术分歧待拉通", category="consensus") == STATUS_TAG_EMPTY
    assert normalize_status_tag("通过", category="share", is_skipped=True) == STATUS_TAG_SKIPPED

    # 2. 验证 SingleAgendaItemModel validate 行为
    item_share = SingleAgendaItemModel.validate({
        "agenda_category": "share",
        "presenter": "陈景东",
        "status_tag": "审议通过",  # 分享类输入审批状态被自动清空
        "target_and_audience": ["多通道声信号感知前沿技术分享"],
        "content_and_evidence": ["提出阵列声学感知新范式"],
        "process_and_interaction": ["评委针对近远场模型提出探讨"],
        "conclusion_and_status": "沉淀了智能声学与临境通信的处理范式",
    })
    assert item_share.agenda_category == "share"
    assert item_share.status_tag == ""

    item_consensus = SingleAgendaItemModel.validate({
        "agenda_category": "consensus",
        "presenter": "张工",
        "status_tag": "方案存在分歧待拉通",
        "conclusion_and_status": "排期尚未对齐，待各模块下周一前复核",
    })
    assert item_consensus.agenda_category == "consensus"
    assert item_consensus.status_tag == ""

    # 3. 验证 Markdown 格式渲染差异化
    multi_draft = {
        "meeting_meta": {
            "theme": "综合技术研讨与评审例会",
            "date_time": "2026/09/30 09:30-12:00",
            "agenda_stats": "既定议题共 4 项（有效审议 3 项 · 本次未讨论 1 项）",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "智慧域核心版本发布评审",
                "presenter": "赵工",
                "agenda_category": "approval",
                "status_tag": "审议通过",
                "time_range": "09:30 ~ 10:00",
                "target_and_audience": ["版本发布放行审查"],
                "content_and_evidence": ["各项压测与自动化用例 100% 达标"],
                "process_and_interaction": ["安全评委确认无现网遗留风险"],
                "conclusion_and_status": "准予放行商用发布。",
                "action_items": [],
                "discussion_state": "discussed",
            },
            {
                "agenda_seq": "02",
                "agenda_title": "智能声学感知与重构技术前沿分享",
                "presenter": "陈教授",
                "agenda_category": "share",
                "status_tag": "",
                "time_range": "10:00 ~ 10:45",
                "target_and_audience": ["学术与工业界前沿知识同步"],
                "content_and_evidence": ["多通道声信号麦克风阵列处理算法演进"],
                "process_and_interaction": ["针对混响环境鲁棒性展开学术研讨"],
                "conclusion_and_status": "建立了基于物理声学与数据驱动联合建模的长期技术路线认知。",
                "action_items": [],
                "discussion_state": "discussed",
            },
            {
                "agenda_seq": "03",
                "agenda_title": "多模块端到端时延优化协同对齐",
                "presenter": "李工",
                "agenda_category": "consensus",
                "status_tag": "存在分歧",
                "time_range": "10:45 ~ 11:30",
                "target_and_audience": ["跨团队拉通降低端到端耗时"],
                "content_and_evidence": ["当前链路总耗时 180ms，目标压减至 120ms"],
                "process_and_interaction": ["算法团队与客户端团队对资源开销归属存在不同看法"],
                "conclusion_and_status": "双方对责任分工存在分歧，责成下周专项拉通磋商。",
                "action_items": [{"owner": "李工", "task": "组织端到端耗时拆解专项会", "deadline": "周五"}],
                "discussion_state": "discussed",
            },
            {
                "agenda_seq": "04",
                "agenda_title": "轻量化离线识别预研规划",
                "presenter": "王工",
                "agenda_category": "approval",
                "status_tag": "本次未讨论",
                "time_range": "—",
                "discussion_state": "skipped",
            },
        ],
    }

    md_out = format_agenda_minutes_markdown(multi_draft)
    # 验证议题总览表格中定调列
    assert "| 智慧域核心版本发布评审 | 赵工 | 09:30 ~ 10:00 | `审议通过` |" in md_out
    assert "| 智能声学感知与重构技术前沿分享 | 陈教授 | 10:00 ~ 10:45 | — |" in md_out  # 分享类显示破折号
    assert "| 多模块端到端时延优化协同对齐 | 李工 | 10:45 ~ 11:30 | — |" in md_out  # 协同类亦为非审批，不设审批定调标签，显示破折号
    assert "| 轻量化离线识别预研规划 | 王工 | — | `本次未讨论` |" in md_out

    # 验证议题详情正文
    # 议题 01：评审类
    assert "### 智慧域核心版本发布评审" in md_out
    assert "- **结论定调**：`审议通过`" in md_out
    assert "#### 1. 背景与目标" in md_out
    assert "#### 2. 核心内容" in md_out
    assert "#### 3. 核心认知" in md_out
    # 议题 01 action_items 为空，自适应不渲染第四栏
    assert "#### 4. 后续行动" not in md_out.split("### 智慧域核心版本发布评审")[1].split("### 智能声学感知与重构技术前沿分享")[0]

    # 议题 02：分享类（无结论定调，无后续行动，自适应 3 栏闭环）
    assert "### 智能声学感知与重构技术前沿分享" in md_out
    assert "### 智能声学感知与重构技术前沿分享\n\n- **汇报人/责任单位**：陈教授\n\n#### 1. 背景与目标" in md_out
    assert "#### 3. 核心认知" in md_out
    assert "#### 4. 后续行动" not in md_out.split("### 智能声学感知与重构技术前沿分享")[1].split("### 多模块端到端时延优化协同对齐")[0]

    # 议题 03：协同类（非审批类，无结论定调，但有行动项，呈现第4栏）
    assert "### 多模块端到端时延优化协同对齐" in md_out
    assert "### 多模块端到端时延优化协同对齐\n\n- **汇报人/责任单位**：李工\n\n#### 1. 背景与目标" in md_out
    assert "#### 3. 核心认知" in md_out
    assert "#### 4. 后续行动" in md_out.split("### 多模块端到端时延优化协同对齐")[1]

    # 4. 验证 HTML 渲染差异化
    html_out = render_agenda_minutes_html("综合技术研讨与评审例会", md_out, multi_draft)
    # 评审类徽标
    assert "badge-approved" in html_out
    assert "✅ 审议通过" in html_out
    # 跳过项徽标
    assert "badge-skipped" in html_out
    # 分享类与协同类在卡片标题旁留空（无 badge，且彻底去除机械序号徽标）
    assert '<div class="agenda-card" id="topic-02">\n            <div class="card-header">\n                <div class="card-title-group">\n                    <h3 class="topic-name">智能声学感知与重构技术前沿分享</h3>\n                </div>\n                \n            </div>' in html_out
    assert '<div class="agenda-card" id="topic-03">\n            <div class="card-header">\n                <div class="card-title-group">\n                    <h3 class="topic-name">多模块端到端时延优化协同对齐</h3>\n                </div>\n                \n            </div>' in html_out
    # 核心认知第 3 栏展示
    assert '<div class="pillar-label"><span class="pillar-num">3</span> 核心认知</div>' in html_out
