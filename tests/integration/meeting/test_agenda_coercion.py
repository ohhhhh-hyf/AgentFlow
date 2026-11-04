# 拆分自 test_agenda_pipeline.py，覆盖：test_agenda_minutes_table_full_conclusion_no_truncation, test_agenda_minutes_dict_shape_coercion_no_leakage, test_agenda_minutes_action_items_flexible_rendering…

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

pytestmark = pytest.mark.integration

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

def test_agenda_minutes_table_full_conclusion_no_truncation():
    """验证总览表格核心结论优化：
    1. 表头列名由 '核心结论与后续安排' 简化为 '核心结论'；
    2. HTML 与 Markdown 输出均不产生 [:80] / [:57] 机械截断；
    3. 列表型结论自动平铺为分号拼接的干净正文，杜绝 Python repr 形如 ['...'] 的括号引号污染。
    """
    from infra.exporters.html.agenda_minutes import (
        format_agenda_minutes_markdown,
        render_agenda_minutes_html,
    )

    long_conclusion_list = [
        "本次评审未直接通过，定调为待补充材料。现场处置结论：晚上单独组织会议对齐时延和效果问题，由领导决策版本是否带风险上线。",
        "发布前置条件：第一，将时延劣化数据及回归测试报告补充至工作台；第二，闭环海外商用状态风险并完成法务归档。",
    ]

    mock_draft = {
        "meeting_meta": {
            "theme": "商用发布评审会",
            "date_time": "2026/06/15",
            "attendees_summary": "全体评委",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "测试长文本议题",
                "presenter": "张三",
                "time_range": "00:10 ~ 00:25",
                "status_tag": "待补充材料",
                "conclusion_and_status": long_conclusion_list,
                "discussion_state": "discussed",
            }
        ],
    }

    # 1. 验证 Markdown 输出
    md = format_agenda_minutes_markdown(mock_draft)
    assert "| 议题时长 | 结论定调 |" in md
    assert "核心结论与后续安排" not in md
    assert "| 核心结论 |" not in md
    assert "| 待办与要求 |" not in md
    # 验证完整文本保留，未被截断
    assert "闭环海外商用状态风险并完成法务归档" in md
    # 验证无 Python list repr 符号
    assert "['" not in md
    # 验证 Markdown 正文结论以分点形式罗列
    assert "> - " in md

    # 2. 验证 HTML 输出
    html = render_agenda_minutes_html("商用发布评审会", md, data=mock_draft)
    assert '<th class="col-time">议题时长</th>' in html
    assert '<th class="col-status">结论定调</th>' in html
    assert "col-actions" not in html
    assert "待办与要求" not in html
    assert "核心结论与后续安排" not in html
    assert "badge-rejected" in html  # 待补充材料自动归一化为 未通过 (badge-rejected)
    # 验证完整文本保留，未被 [:80] 截断
    assert "闭环海外商用状态风险并完成法务归档" in html
    assert "['" not in html
    # 验证卡片正文结论使用分点列表
    assert '<ul class="res-box-list">' in html

    # 3. 验证历史遗留/极端受污染的字符串形式 "['条目1', '条目2']" 自动清洗恢复
    polluted_string = (
        "['车机时延问题延期单独评审：索勋飞明确...', "
        "'其余问题要求补充材料后跟进：ASR效果问题...']"
    )
    mock_draft_polluted = {
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "测试清洗议题",
                "presenter": "李四",
                "conclusion_and_status": polluted_string,
            }
        ]
    }
    clean_html = render_agenda_minutes_html("测试", "", data=mock_draft_polluted)
    assert "['" not in clean_html
    assert "', '" not in clean_html
    assert '<ul class="res-box-list">' in clean_html


def test_agenda_minutes_dict_shape_coercion_no_leakage() -> None:
    """验证当 LLM 将核心内容输出为字典或字典字符串时，系统自动反序列化与多态解构，杜绝内存字典泄露。"""
    from infra.exporters.html.agenda_minutes import (
        auto_structure_bullet,
        coerce_bullet_entry,
        format_agenda_minutes_markdown,
        render_agenda_minutes_html,
    )
    from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import SingleAgendaItemModel

    # 1. 现场真实抓包：模型输出的 {"topic": ..., "points": [...]} 字典
    sample_topic_dict = {
        "topic": "**跨产品线规格统一与平台能力拉通**：",
        "points": [
            "- 小艺团队反馈不同产品线有独特卖点诉求，导致规格频繁变化，影响用户心智稳定，如高端与低端机型在麦克风配置上不统一；",
            "- 何刚明确原则是拉通，建议各产品线收敛为高端、低端两档规格，平台能力持续构建，产品线自行排序需求，资源有限需聚焦；",
            "- 若拉通有困难，可上升至TMT决策，提出明确诉求以保障唤醒体验一致性。",
        ],
    }

    # 测试 coerce_bullet_entry 与 auto_structure_bullet
    bullet_from_dict = auto_structure_bullet(sample_topic_dict)
    assert "**跨产品线规格统一与平台能力拉通**：" in bullet_from_dict
    assert "- 小艺团队反馈不同产品线有独特卖点诉求" in bullet_from_dict
    assert "{'topic'" not in bullet_from_dict
    assert "'points':" not in bullet_from_dict

    # 2. 字典字符串形态（如历史上因 str(dict) 漏出的字符串）
    dict_str = (
        "{'topic': '**AI能力撬动消费者购买的理想态探讨**：', "
        "'points': ['- 现场提出AI结合硬件虽提升明显，但尚未成为消费者购买决策的关键因素；', "
        "'- 何刚认为需经历量变到质变，当前消费者心智仍停留在语音助手阶段；']}"
    )
    bullet_from_str = auto_structure_bullet(dict_str)
    assert "**AI能力撬动消费者购买的理想态探讨**：" in bullet_from_str
    assert "- 现场提出AI结合硬件虽提升明显" in bullet_from_str
    assert "{'topic'" not in bullet_from_str
    assert "**{'topic'**" not in bullet_from_str

    # 3. 经过 SingleAgendaItemModel.validate 校验
    raw_data = {
        "presenter": "何刚",
        "agenda_category": "share",
        "status_tag": "",
        "background_and_goals": {"background": "探讨小艺AI能力与产品线拉通规格。"},
        "core_content": [
            sample_topic_dict,
            {
                "topic": "小艺慧记功能优化与内部工具提效",
                "points": ["- 何刚反馈小艺慧记总结能力基本可用，但无法按会议议题分段。"],
            },
        ],
        "core_insights": {
            "topic": "战略共识",
            "points": ["尊重生态商业模式，探索无绝对边界的创新路径。"],
        },
        "action_items": [],
    }

    item = SingleAgendaItemModel.validate(raw_data)
    for c in item.core_content:
        assert isinstance(c, str)
        assert "{'topic'" not in c

    # 4. 组装成完整草稿并渲染 Markdown 与 HTML
    draft = {
        "meeting_meta": {
            "theme": "智能语音战略例会",
            "date_time": "2026-10-10",
            "agenda_stats": "既定议题 1 项",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "小艺平台定位与各产品线诉求对齐",
                "presenter": "何刚",
                "agenda_category": "share",
                "status_tag": "",
                "time_range": "00:10 ~ 00:50",
                "background_and_goals": item.background_and_goals,
                "core_content": item.core_content,
                "core_insights": item.core_insights,
                "action_items": [],
            }
        ],
    }

    md_out = format_agenda_minutes_markdown(draft)
    # 绝对杜绝任何字典键名碎骨架
    assert "{'topic'" not in md_out
    assert "**{'topic'**" not in md_out
    assert "'points':" not in md_out
    assert "']}。" not in md_out

    # 验证标准一级 - 加粗主题，二级 2 空格缩进 -
    assert "- **跨产品线规格统一与平台能力拉通**：" in md_out
    assert "  - 小艺团队反馈不同产品线有独特卖点诉求" in md_out
    assert "  - 何刚明确原则是拉通" in md_out
    assert "- **小艺慧记功能优化与内部工具提效**：" in md_out
    assert "  - 何刚反馈小艺慧记总结能力基本可用" in md_out

    # 5. 验证 HTML 渲染
    html_out = render_agenda_minutes_html("智能语音战略例会", md_out, draft)
    assert "{'topic'" not in html_out
    assert "<strong>{'topic'</strong>" not in html_out
    assert 'class="content-topic-title"' in html_out
    assert "跨产品线规格统一与平台能力拉通" in html_out


def test_agenda_minutes_action_items_flexible_rendering() -> None:
    """验证后续行动表格的弹性输出：有待办出表格，无待办彻底隐去，支持异构条目容错。"""
    raw_data_with_actions = {
        "presenter": "何刚（答疑嘉宾）及现场研讨团队",
        "agenda_category": "share",
        "status_tag": "",
        "background_and_goals": "围绕小艺跨产品线协同与体验优化拉齐认知。",
        "core_content": [
            "**跨产品线规格统一**：\n- 建议产品线收敛为高端、低端两档规格；\n- 平台能力持续构建。"
        ],
        "core_insights": "平台能力需统一，规格收敛避免碎片化。",
        "action_items": [
            {
                "owner": "小艺团队",
                "task": "向产品线提出规格统一要求，推动高端/低端两档拉通",
                "deadline": "待定",
            },
            {
                "owner": "小艺慧记团队",
                "task": "实现图片输入日程、按议题分段生成纪要并优化声纹识别",
                "deadline": "尽快",
            },
            "贾维斯团队：制作分屏看广告的demo并与生态探讨可行性",
        ],
    }

    # 1. 验证 SingleAgendaItemModel 解析
    item = SingleAgendaItemModel.validate(raw_data_with_actions)
    assert len(item.action_items) == 3
    assert item.action_items[0]["owner"] == "小艺团队"
    assert item.action_items[0]["deadline"] == "待定"
    assert item.action_items[1]["owner"] == "小艺慧记团队"
    assert item.action_items[1]["deadline"] == "尽快"

    # 2. 组装多议题草稿：议题 01 有待办，议题 02 无待办
    draft = {
        "meeting_meta": {
            "theme": "战略交流会",
            "date_time": "2026-10-10",
            "agenda_stats": "既定议题 2 项",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "互动交流",
                "presenter": item.presenter,
                "agenda_category": "share",
                "status_tag": "",
                "time_range": "00:18 ~ 01:18",
                "background_and_goals": item.background_and_goals,
                "core_content": item.core_content,
                "core_insights": item.core_insights,
                "action_items": item.action_items,
            },
            {
                "agenda_seq": "02",
                "agenda_title": "何刚总致辞",
                "presenter": "何刚",
                "agenda_category": "share",
                "status_tag": "",
                "time_range": "00:00 ~ 00:18",
                "background_and_goals": "回顾北京业务历程并鼓励创新。",
                "core_content": ["**战略定位**：\n- 强调华为AI优势在于与硬件协同。"],
                "core_insights": "做硬件公司需长期主义。",
                "action_items": [],
            },
        ],
    }

    md_out = format_agenda_minutes_markdown(draft)

    # 议题 01 必须渲染第 4 栏表格
    assert "### 互动交流" in md_out
    assert "#### 4. 后续行动" in md_out
    assert "| 责任人 | 跟进事项与交付目标 | 时限节点 |" in md_out
    assert "| 小艺团队 | 向产品线提出规格统一要求，推动高端/低端两档拉通 | 待定 |" in md_out
    assert "| 小艺慧记团队 | 实现图片输入日程、按议题分段生成纪要并优化声纹识别 | 尽快 |" in md_out

    # 议题 02 必须彻底不出现第 4 栏
    parts = md_out.split("### 何刚总致辞")
    assert len(parts) == 2
    speech_part = parts[1]
    assert "#### 4. 后续行动" not in speech_part
    assert "| 责任人 | 跟进事项与交付目标 | 时限节点 |" not in speech_part

    # 3. 验证 HTML 渲染
    html_out = render_agenda_minutes_html("战略交流会", md_out, draft)
    assert '4</span> 后续行动' in html_out
    assert "小艺团队" in html_out
    assert "小艺慧记团队" in html_out
    assert '<span class="deadline-tag">待定</span>' in html_out
    assert '<span class="deadline-tag">尽快</span>' in html_out
