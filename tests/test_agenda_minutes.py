"""tests/test_agenda_minutes.py -- 议程驱动型会议纪要 (agenda_minutes) 全链路单元测试。

验证：
1. AgendaParser 对 4 类真实议程文件（表格、ASCII、元数据）的高保真解析；
2. AlignmentEngine 的发言人真名双向锚定与零证据确定性截断 (Zero-Evidence Cutoff)；
3. AgendaMinutesAgent 的 Agenda-as-Anchor 骨架绝对锁定；
4. Markdown 与 HTML 双模态渲染器格式与样式合规性；
5. API 层 _prepare 对 docs 既定议程文本与图片的提取分派。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import docx

from domain.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    parse_agenda_text,
)
from domain.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
    group_transcript_blocks,
)
from domain.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
    _extract_agenda_and_transcript,
)
from domain.meeting.tasks.agenda_minutes.steps.agenda_minutes_render import (
    AgendaMinutesRender,
)
from tools.exports.html.agenda_minutes import (
    format_agenda_minutes_markdown,
    render_agenda_minutes_html,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENDA_DIR = PROJECT_ROOT / "agenda"


def test_clean_presenter_names():
    """测试汇报人姓名清洗逻辑。"""
    assert clean_presenter_names("汇报人: 赵鑫岳 00585440") == ["赵鑫岳"]
    assert clean_presenter_names("沙彬斌; 陈啟锴") == ["沙彬斌", "陈啟锴"]
    assert clean_presenter_names("陆敬怡; 林宇珂; 赖朝辉") == ["陆敬怡", "林宇珂", "赖朝辉"]
    assert clean_presenter_names("汇报人: 林宇珂 00939670 陆敬怡 00841266") == ["林宇珂", "陆敬怡"]
    assert clean_presenter_names("索勋飞(委托高雄)") == ["索勋飞"]
    assert clean_presenter_names("非公开") == []


def test_agenda_parser_test1():
    """测试商评1议程解析（含元数据与双语表头）。"""
    txt_path = AGENDA_DIR / "test1" / "商评1.txt"
    if not txt_path.is_file():
        pytest.skip("商评1.txt not found")
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    assert "智慧域商用发布评审" in plan.meta.theme
    assert "2026/06/15" in plan.meta.date_time
    assert "全程与会人" in plan.meta.attendees
    assert len(plan.items) == 4

    assert plan.items[0].seq == "01"
    assert "小艺慧记" in plan.items[0].title
    assert plan.items[0].presenters == ["申家坤"]

    assert plan.items[1].seq == "02"
    assert "翻译海外" in plan.items[1].title
    assert plan.items[1].presenters == ["刘畅"]

    assert plan.items[2].seq == "03"
    assert "HAG" in plan.items[2].title
    assert set(plan.items[2].presenters) == {"沙彬斌", "陈啟锴"}

    assert plan.items[3].seq == "04"
    assert "SpeechASR" in plan.items[3].title
    assert set(plan.items[3].presenters) == {"陆敬怡", "林宇珂", "赖朝辉"}


def test_agenda_parser_test2_to_test4():
    """测试商评2、小艺委例会、月度洞察会的议程解析。"""
    # Test 2: 9 items
    t2_path = AGENDA_DIR / "test2" / "商评2.txt"
    if t2_path.is_file():
        plan2 = parse_agenda_text(t2_path.read_text(encoding="utf-8"))
        assert len(plan2.items) == 9
        assert plan2.items[0].presenters == ["赵鑫岳"]
        assert plan2.items[2].presenters == ["武思华"]
        assert plan2.items[5].presenters == ["林宇珂", "陆敬怡"]

    # Test 3: 4 items
    t3_path = AGENDA_DIR / "test3" / "小艺语音技术委员会.txt"
    if t3_path.is_file():
        plan3 = parse_agenda_text(t3_path.read_text(encoding="utf-8"))
        assert len(plan3.items) == 4
        assert plan3.items[0].presenters == ["周径"]
        assert plan3.items[1].presenters == ["张子晗"]
        assert plan3.items[3].presenters == ["卢凌峰"]

    # Test 4: 3 items
    t4_path = AGENDA_DIR / "test4" / "月度洞察会.txt"
    if t4_path.is_file():
        plan4 = parse_agenda_text(t4_path.read_text(encoding="utf-8"))
        assert len(plan4.items) == 3
        assert plan4.items[0].presenters == ["王海涛"]
        assert plan4.items[1].presenters == ["刘雨桉"]
        assert plan4.items[2].presenters == ["朱启源"]


def test_agenda_parser_bullet_fallback():
    """测试无表格时的序号列表降级解析。"""
    raw_list = """
    会议主题：技术前沿研讨例会
    1. 具身智能世界模型前沿洞察 汇报人：李博士
    2. 多模态长序列端侧推理优化 汇报人：王工
    3. 强化学习在声学降噪中的实践 汇报人：张研究员
    """
    plan = parse_agenda_text(raw_list)
    assert plan.meta.theme == "技术前沿研讨例会"
    assert len(plan.items) == 3
    assert plan.items[0].seq == "01"
    assert "具身智能" in plan.items[0].title
    assert plan.items[0].presenters == ["李博士"]
    assert plan.items[1].presenters == ["王工"]
    assert plan.items[2].presenters == ["张研究员"]


def test_alignment_engine_test1_grounding_and_zero_evidence():
    """核心防幻觉单测：验证 Test 1 中会议顺序变化（先议题2、再议题1、再议题4）与替代汇报人自适应绑定、未讨论议题3确定性截断。"""
    docx_path = AGENDA_DIR / "test1" / "商评1.docx"
    txt_path = AGENDA_DIR / "test1" / "商评1.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 1 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    res = align_agenda_with_transcript(plan, transcript)
    assert len(res.alignments) == 4
    # 核心判决：既定议题1（小艺慧记）、2（翻译海外）、4（SpeechASR）均有充分审议，为 discussed；议题3（HAG）未讨论，为 skipped
    assert res.discussed_count == 3
    assert res.skipped_count == 1

    a1, a2, a3, a4 = res.alignments
    assert a1.item.seq == "01"
    assert a1.status == "discussed"
    assert "陆敬怡" in a1.matched_speakers
    assert len(a1.matched_blocks) > 30

    assert a2.item.seq == "02"
    assert a2.status == "discussed"
    assert "刘畅" in a2.matched_speakers
    assert len(a2.matched_blocks) > 30

    assert a3.item.seq == "03"
    assert a3.status == "skipped"
    assert a3.matched_blocks == []

    assert a4.item.seq == "04"
    assert a4.status == "discussed"
    assert "耿安峰" in a4.matched_speakers
    assert len(a4.matched_blocks) > 100


def test_agenda_minutes_agent_enforce_invariants():
    """验证 Agenda-as-Anchor 绝对骨架锁定（大模型擅自改名/换序被强行后置纠正）。"""
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(seq="01", title="官方议题A：关于语音LLM发布的严格评审", presenters=["周径"]),
            AgendaItemParsed(seq="02", title="官方议题B：关于音频降噪的架构审议", presenters=["沙彬斌"]),
        ]
    )

    transcript = "周径 00:10:00\n关于语音大模型，我们做了以下工作..."
    alignment_res = align_agenda_with_transcript(plan, transcript)

    # 模拟大模型给出的不规范输出（擅自改短标题、改动序号）
    mock_raw = {
        "meeting_meta": {"theme": "技术研讨会"},
        "agenda_items": [
            {
                "agenda_seq": "1",
                "agenda_title": "大模型发布",  # 擅自改名
                "status_tag": "[技术共识]",
                "proposal_highlights": ["背景说明"],
                "deliberation_details": {"key_metrics": ["40ms"], "feedback_concerns": ["高雄质询"]},
                "resolution": "原则同意",
                "action_commitments": [{"owner": "周径", "task": "上线", "deadline": "月底"}],
            },
            {
                "agenda_seq": "2",
                "agenda_title": "降噪方案",  # 擅自改名且未讨论却脑补了指标
                "status_tag": "[审议通过]",
                "proposal_highlights": ["虚构背景"],
                "deliberation_details": {"key_metrics": ["99%"], "feedback_concerns": []},
                "resolution": "虚构定调",
                "action_commitments": [],
            },
        ],
    }

    class DummyClient:
        pass

    agent = AgendaMinutesAgent(DummyClient())
    enforced = agent._enforce_agenda_invariants(mock_raw, alignment_res)

    items = enforced["agenda_items"]
    assert len(items) == 2

    # 议题 1：标题 100% 被恢复为官方全称，序号规范化为 01
    assert items[0]["agenda_seq"] == "01"
    assert items[0]["agenda_title"] == "官方议题A：关于语音LLM发布的严格评审"
    assert items[0]["presenter"] == "周径"
    assert items[0]["discussion_state"] == "discussed"

    # 议题 2：未讨论议题的脑补事实被 100% 确定性截断为客观说明
    assert items[1]["agenda_seq"] == "02"
    assert items[1]["agenda_title"] == "官方议题B：关于音频降噪的架构审议"
    assert items[1]["status_tag"] == "[本次未讨论]"
    assert items[1]["discussion_state"] == "skipped"
    assert items[1]["deliberation_details"]["key_metrics"] == []
    assert "未见针对本议题" in items[1]["resolution"]


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
    assert "# 智慧域商用发布评审 · 议程全景纪要" in md_output
    assert "## 第一部分：议题完成情况一览表" in md_output
    assert "| **议题 01** | 翻译海外HiTranslationService 21.1.1.300商用版本发布 | 刘畅 | `[审议通过]` |" in md_output
    assert "| **议题 02** | HAG 3.6.5.300版本商用发布评审 | 沙彬斌、陈啟锴 | `[本次未讨论]` |" in md_output
    assert "### 议题 01 · 翻译海外HiTranslationService 21.1.1.300商用版本发布" in md_output
    assert "#### 1. 方案背景与核心诉求" in md_output
    assert "#### 2. 研讨过程与关键论据" in md_output
    assert "#### 3. 最终定调与决议共识" in md_output
    assert "#### 4. 后续行动与跟进责任" in md_output
    assert "## 第三部分：临时追加议题与重要定调" in md_output

    # 2. 验证 HTML 格式
    html_output = render_agenda_minutes_html("智慧域商用发布评审", md_output, draft)
    assert "<!DOCTYPE html>" in html_output
    assert "智慧域商用发布评审 · 议程全景纪要" in html_output
    assert "badge-approved" in html_output
    assert "badge-skipped" in html_output
    assert "card-skipped" in html_output
    assert "临时追加议题与重要定调" in html_output

    # 3. 验证 Render 类的 render_draft 与 extract_structure
    state = {"lines": {"agenda_minutes": {"draft": draft}}}
    assert AgendaMinutesRender.render_draft(state).startswith("# 智慧域商用发布评审 · 议程全景纪要")
    extracted = AgendaMinutesRender.extract_structure(state)
    assert len(extracted) == 2
    assert extracted[0]["agenda_seq"] == "01"


def test_agenda_parser_markdown_table_and_tabs():
    """测试标准 Markdown 表格与 Tab 制表符文本的高保真解析。"""
    md_table = """
| 编号 | 议题名称 | 时长 | 起止时间 | 汇报人 | 纪要人 | 议题参与人 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 小艺慧记 CeliaMinutesService 1.4.5.500 版本发布商用版本 | 15min | 16:00-16:15 | 申家坤 | 申家坤 | 方思邈；李腾飞；郑本令 |
| 2 | 翻译海外 HiTranslationService 21.1.1.300 商用版本发布 | 15min | 16:15-16:30 | 刘畅 | 刘畅 | 陈坤；赵磊；陈冬阳 |
"""
    plan = parse_agenda_text(md_table)
    assert len(plan.items) == 2
    assert plan.items[0].seq == "01"
    assert "小艺慧记" in plan.items[0].title
    assert plan.items[0].presenters == ["申家坤"]
    assert plan.items[0].duration == "15min"
    assert plan.items[0].time_range == "16:00-16:15"

    tab_text = "序号\t议题名称\t时长\t汇报人\n1\t大模型推理优化\t30分钟\t张三\n2\tAgent长期记忆\t30分钟\t李四"
    plan_tab = parse_agenda_text(tab_text)
    assert len(plan_tab.items) == 2
    assert plan_tab.items[0].seq == "01"
    assert plan_tab.items[0].title == "大模型推理优化"
    assert plan_tab.items[0].presenters == ["张三"]

    line_text = "1 智能跃迁：智能体RSI递归自我演进技术洞察 汇报人：刘雨桉\n2 AI infra优化实践 汇报人：朱启源"
    plan_line = parse_agenda_text(line_text)
    assert len(plan_line.items) == 2
    assert plan_line.items[0].seq == "01"
    assert "智能跃迁" in plan_line.items[0].title
    assert plan_line.items[0].presenters == ["刘雨桉"]


def test_ocr_serverocr_fallback_to_rapidocr(monkeypatch):
    """测试 .env 中配置 serverocr 时，服务器不可用自动降级兜底至 RapidOCR。"""
    from tools.ocr.engines import run_ocr_subprocess

    monkeypatch.setenv("OCR_ENGINE", "serverocr")
    monkeypatch.setenv("SERVER_OCR_URL", "http://127.0.0.1:59999/nonexistent")

    img_path = AGENDA_DIR / "test1" / "商评1.png"
    if not img_path.is_file():
        pytest.skip("商评1.png not found")

    res = run_ocr_subprocess(str(img_path))
    assert res.get("engine") == "rapidocr"
    assert len(res.get("lines", [])) > 0

