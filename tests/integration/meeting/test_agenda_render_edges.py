# 拆分自 test_agenda_render.py，覆盖：test_auto_structure_and_render_sub_bullets, test_zero_terminology_and_substantive_fail_safe…

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

def test_auto_structure_and_render_sub_bullets():
    """测试核心内容与核心认知自动分组分点结构化（加粗主题 + 二级子列表）。"""
    from infra.exporters.html.agenda_minutes import (
        auto_structure_bullet,
        format_agenda_minutes_markdown,
        render_agenda_minutes_html,
    )

    sample_dense = (
        "ASR效果问题：存在多个上下文能力、热词误闯、垂域误闯等问题单，但仅对两个问题做了根因分析。"
        "评审质疑未分析的问题如何评估，王旭解释上下文能力分多个单子，部分已分析，部分需持续分析。"
        "耿安峰说明整体指标：通用测试集4.0较现网下降0.7个百分点，主要受热词影响，如“温度开到18°”被识别为热词“18°”，导致结果错误；"
        "分类测试集除快语速、车控等专项外均有提升。评审要求明确现网与测试环境数据对比，并补充问题影响描述。"
    )

    # 1. 验证 auto_structure_bullet 单独拆分
    structured = auto_structure_bullet(sample_dense)
    assert "**ASR效果问题**：" in structured
    assert "\n- 存在多个上下文能力" in structured
    assert "\n- 耿安峰说明整体指标" in structured
    # 杜绝机械序号
    assert "1." not in structured and "1）" not in structured

    # 2. 验证 Markdown 渲染输出（一级 - 加粗主题，二级 2 空格缩进 - ）
    mock_draft = {
        "meeting_meta": {
            "date_time": "2026-09-30",
            "agenda_stats": "既定议题 1 项",
        },
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "智慧语音算法版本评审",
                "presenter": "王旭",
                "agenda_category": "approval",
                "status_tag": "审议通过",
                "time_range": "00:10 ~ 00:40",
                "background_and_goals": "按计划评审 ASR 4.0 算法版本商用就绪度。",
                "core_content": [sample_dense],
                "core_insights": (
                    "**算法发布原则与策略**：\n"
                    "- 准入红线：通用测试集指标必须收敛至现网基线以上；\n"
                    "- 专项验收：车控与车载高噪场景需补充专项闭环评测。"
                ),
                "action_items": [],
                "discussion_state": "discussed",
            }
        ],
    }

    md_out = format_agenda_minutes_markdown(mock_draft)
    assert "- **ASR效果问题**：" in md_out
    assert "  - 存在多个上下文能力" in md_out
    assert "  - 耿安峰说明整体指标" in md_out
    assert "> - **算法发布原则与策略**：" in md_out
    assert ">   - 准入红线：" in md_out

    # 3. 验证 HTML 渲染输出（包含 sub-bullet-list 与 content-group）
    html_out = render_agenda_minutes_html("智慧语音算法版本评审", md_out, mock_draft)
    assert 'class="content-group"' in html_out
    assert 'class="content-topic-title"' in html_out
    assert 'class="sub-bullet-list"' in html_out
    assert "<strong>ASR效果问题</strong>：" in html_out
    assert 'class="insight-group"' in html_out
    assert "<strong>算法发布原则与策略</strong>：" in html_out


def test_zero_terminology_and_substantive_fail_safe() -> None:
    """验证零术语兜底与议题筛选升级：
    1. SingleAgendaItemModel.validate 消除 approval 默认偏置与审议通过自动脑补；
    2. Test 7（北研所交流会）实录仿真：
       - 开场视频与合影作为过场被剔除；
       - 任务令签署与授予绝不被机械判定为 approval，且定调标签恒为空（不盖章）；
       - 互动交流汇报人正确映射为标准公文风（答疑嘉宾及现场参会团队）；
       - 会议大类为非审批，总览表格 100% 严格折叠为 3 列，无第 4 列结论定调；
    3. 高证据密度反向保活机制（Fail-Safe）：
       - 即使 LLM 误标 is_substantive_agenda=False，事实密度充实（>=5块且>=150字）强制保活。
    """
    from domains.meeting.tasks.agenda_minutes.agenda_parser import AgendaItemParsed, AgendaPlan
    from domains.meeting.tasks.agenda_minutes.alignment_engine import (
        AgendaAlignment,
        AlignmentResult,
        DiscussionBlock,
    )
    from domains.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
        AgendaMinutesAgent,
        SingleAgendaItemModel,
    )

    # 1. 验证 SingleAgendaItemModel.validate 零术语兜底
    m_task = SingleAgendaItemModel.validate({
        "agenda_title": "任务令签署与授予",
        "agenda_category": "approval",  # 历史模版残留
        "status_tag": "",
    })
    assert m_task.agenda_category == "share"
    assert m_task.status_tag == ""

    m_speech = SingleAgendaItemModel.validate({
        "agenda_title": "何刚总致辞",
        "agenda_category": "share",
        "status_tag": "",
    })
    assert m_speech.agenda_category == "share"
    assert m_speech.status_tag == ""

    m_review_empty_tag = SingleAgendaItemModel.validate({
        "agenda_title": "ASR 4.0 准入评审",
        "agenda_category": "approval",
        "status_tag": "",  # 现场无结论
    })
    assert m_review_empty_tag.agenda_category == "approval"
    assert m_review_empty_tag.status_tag == ""  # 绝不脑补“审议通过”

    # 2. 验证高证据密度反向保活安全网
    agent = AgendaMinutesAgent(client=None)  # type: ignore[arg-type]
    plan_fs = AgendaPlan(
        meta=type(AgendaPlan().meta)(theme="技术研讨交流会", attendees="全体"),
        items=[
            AgendaItemParsed(seq="01", title="高密度任务签署", presenters=["张三"]),
            AgendaItemParsed(seq="02", title="低密度噪音过场", presenters=["李四"]),
        ],
    )
    blocks_high = [
        DiscussionBlock(speaker="张三", timestamp=f"00:{i:02d}", content="高密度发言关键决策" * 10, index=i)
        for i in range(6)
    ]
    blocks_low = [
        DiscussionBlock(speaker="李四", timestamp="01:00", content="短发言吆喝", index=10)
    ]
    align_fs = AlignmentResult(
        plan=plan_fs,
        alignments=[
            AgendaAlignment(item=plan_fs.items[0], status="discussed", matched_blocks=blocks_high),
            AgendaAlignment(item=plan_fs.items[1], status="discussed", matched_blocks=blocks_low),
        ],
    )
    raw_fs = {
        "meeting_meta": {"theme": "技术研讨交流会"},
        "agenda_items": [
            {"agenda_seq": "01", "agenda_title": "高密度任务签署", "is_substantive_agenda": False, "agenda_category": "share", "status_tag": ""},
            {"agenda_seq": "02", "agenda_title": "低密度噪音过场", "is_substantive_agenda": False, "agenda_category": "share", "status_tag": ""},
        ],
    }
    res_fs = agent._enforce_agenda_invariants(raw_fs, align_fs)
    items_fs = res_fs["agenda_items"]
    # 高密度项被安全网救回，低密度项被正常剔除
    assert len(items_fs) == 1
    assert items_fs[0]["agenda_title"] == "高密度任务签署"

    # 3. 验证 Test 7 完整流程仿真
    plan_t7 = AgendaPlan(
        meta=type(AgendaPlan().meta)(theme="", attendees="何总、涂总及各战队"),
        items=[
            AgendaItemParsed(seq="01", title="活动开场视频播放", presenters=[]),
            AgendaItemParsed(seq="02", title="何刚总致辞", presenters=["何刚"]),
            AgendaItemParsed(seq="03", title="互动交流（现场问答、自由交流与讨论）", presenters=[]),
            AgendaItemParsed(seq="04", title="任务令签署与授予", presenters=["涂总", "何总"]),
            AgendaItemParsed(seq="05", title="全体合影", presenters=[]),
        ],
    )
    align_01 = AgendaAlignment(item=plan_t7.items[0], status="discussed", matched_blocks=[])
    align_02 = AgendaAlignment(item=plan_t7.items[1], status="discussed", matched_blocks=[
        DiscussionBlock(speaker="何刚", timestamp="00:00", content="各位战队同事大家好，今天我们齐聚北研所，明确下一阶段攻坚方向。" * 3, index=1),
        DiscussionBlock(speaker="何刚", timestamp="00:05", content="我们要扎实做好算法演进与工程交付，坚定信心！" * 2, index=2),
    ])
    align_03 = AgendaAlignment(item=plan_t7.items[2], status="discussed", matched_blocks=[
        DiscussionBlock(speaker="何刚", timestamp="00:18", content="大家有什么具体问题，随时提。" * 2, index=3),
        DiscussionBlock(speaker="发言者5", timestamp="00:25", content="何总，我们端侧时延这块目前面临算力受限挑战，希望统筹协调。" * 2, index=4),
    ])
    align_04 = AgendaAlignment(item=plan_t7.items[3], status="discussed", matched_blocks=[
        DiscussionBlock(speaker="涂总", timestamp="01:18", content="下面进行战队任务令签署与授予仪式，请各战队队长上台领令。" * 2, index=5),
        DiscussionBlock(speaker="何总", timestamp="01:20", content="任务令就是军令状，责任到人，务必按期高质量达成！" * 2, index=6),
    ])
    align_05 = AgendaAlignment(item=plan_t7.items[4], status="discussed", matched_blocks=[
        DiscussionBlock(speaker="主持人", timestamp="01:21", content="大家看镜头，三二一。", index=7),
    ])
    align_res = AlignmentResult(
        plan=plan_t7,
        alignments=[align_01, align_02, align_03, align_04, align_05],
    )
    raw_draft = {
        "meeting_meta": {"theme": ""},
        "agenda_items": [
            {
                "agenda_seq": "02", "agenda_title": "何刚总致辞", "agenda_category": "share", "status_tag": "",
                "background_and_goals": "总结前期工作，明确北研所各战队攻坚目标。",
                "core_content": ["**战略方向定调**：\n- 强化算法研发与工程落地协同。"],
                "core_insights": "坚持技术深耕与产品化结合。",
            },
            {
                "agenda_seq": "03", "agenda_title": "互动交流（现场问答、自由交流与讨论）", "agenda_category": "share", "status_tag": "",
                "presenter": "发言者 5",
                "background_and_goals": "围绕各战队技术攻坚难点展开现场答疑与研讨。",
                "core_content": ["**端侧算力与时延瓶颈**：\n- 现场就资源调配展开深入交流。"],
                "core_insights": "加强底层系统对算法的支撑。",
            },
            {
                "agenda_seq": "04", "agenda_title": "任务令签署与授予", "agenda_category": "approval", "status_tag": "",
                "background_and_goals": "举行任务令签署仪式，压实攻坚责任。",
                "core_content": ["**军令状签署**：\n- 各战队队长领令并作表态发言。"],
                "core_insights": "以任务令为契约狠抓执行。",
            },
        ],
    }

    res = agent._enforce_agenda_invariants(raw_draft, align_res)
    items = res["agenda_items"]
    # 01 (开场视频) 与 05 (合影) 被剔除，仅保留 02, 03, 04
    assert len(items) == 3
    assert [it["agenda_seq"] for it in items] == ["02", "03", "04"]

    # 汇报人规则化：互动交流不写匿名“发言者 5”，写“何刚（答疑嘉宾）及现场参会团队”
    assert items[1]["presenter"] == "何刚（答疑嘉宾）及现场参会团队"

    # 零术语兜底：任务令签署与授予绝不打上“审议通过”标签，且非审批属性
    assert items[2]["agenda_category"] != "approval"
    assert items[2]["status_tag"] == ""

    # 总览表格排版校验：100% 严格折叠为 3 列形态，绝无“结论定调”与“审议通过”
    md_out = format_agenda_minutes_markdown(res)
    assert "| 议题名称 | 汇报人 | 议题时长 |" in md_out
    assert "结论定调" not in md_out
    assert "审议通过" not in md_out
    # 标题分析不带“议题02”等僵硬前缀
    assert "### 何刚总致辞" in md_out
    assert "### 议题02" not in md_out
    assert "- **结论定调**：" not in md_out
