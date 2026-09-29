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
AGENDA_DIR = (
    PROJECT_ROOT / "data" / "1" / "agenda"
    if (PROJECT_ROOT / "data" / "1" / "agenda").exists()
    else PROJECT_ROOT / "agenda"
)


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
    """核心防幻觉单测：验证 Test 1 中发言块独立路由。
    
    结果：
    - 议题01（小艺慧记，申家坤）：申家坤未参会未发言，如实判为 skipped，块数为 0；
    - 议题02（翻译海外，刘畅）：正常讨论，为 discussed；
    - 议题03（HAG）：未参会，为 skipped；
    - 议题04（SpeechASR，陆敬怡等）：陆敬怡发言准确归入议题04（不再被孤立标题抢占到议题01），为 discussed。
    """
    docx_path = AGENDA_DIR / "test1" / "商评1.docx"
    txt_path = AGENDA_DIR / "test1" / "商评1.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 1 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    res = align_agenda_with_transcript(plan, transcript)
    assert len(res.alignments) == 4
    # 核心判决：02 与 04 有效讨论，01 与 03 确实未讨论
    assert res.discussed_count == 2
    assert res.skipped_count == 2

    a1, a2, a3, a4 = res.alignments
    assert a1.item.seq == "01"
    assert a1.status == "skipped"
    assert a1.matched_blocks == []

    assert a2.item.seq == "02"
    assert a2.status == "discussed"
    assert "刘畅" in a2.matched_speakers
    assert len(a2.matched_blocks) > 30

    assert a3.item.seq == "03"
    assert a3.status == "skipped"
    assert a3.matched_blocks == []

    assert a4.item.seq == "04"
    assert a4.status == "discussed"
    assert "陆敬怡" in a4.matched_speakers
    assert len(a4.matched_blocks) > 100

    # 验证按现场研讨真实流向排序：先讨论的 02，随后 04，最后是 skipped 的 01 和 03
    chrono = res.chronological_alignments
    assert len(chrono) == 4
    assert [c.item.seq for c in chrono] == ["02", "04", "01", "03"]


def test_alignment_engine_test2_all_presenters_grounding():
    """验证 Test 2 中 9 项议题依靠汇报人主权发言彻底解决标题错位问题。"""
    docx_path = AGENDA_DIR / "test2" / "商评2.docx"
    txt_path = AGENDA_DIR / "test2" / "商评2.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 2 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(txt_path.read_text(encoding="utf-8"))

    res = align_agenda_with_transcript(plan, transcript)
    assert len(res.alignments) == 9
    assert res.discussed_count == 9

    align_map = {a.item.seq: a for a in res.alignments}

    # 郑爽准确回到 04 IDS，而不是留在小艺慧记或 HAG
    assert "郑爽" in align_map["04"].matched_speakers
    assert len(align_map["04"].matched_blocks) > 100

    # 陈啟锴在 05 HAG
    assert "陈啟锴" in align_map["05"].matched_speakers
    assert len(align_map["05"].matched_blocks) > 100

    # 陆敬怡在 06 SpeechASR
    assert "陆敬怡" in align_map["06"].matched_speakers

    # 孙鹤鸣在 07 SpeechTTS
    assert "孙鹤鸣" in align_map["07"].matched_speakers

    # 张昊辰在 08 HiTranslationService
    assert "张昊辰" in align_map["08"].matched_speakers

    # 验证现场换序（Permutations）：现场 SpeechTTS (07) 发生于 SpeechASR (06) 之前
    chrono2 = res.chronological_alignments
    assert len(chrono2) == 9
    chrono_seqs = [c.item.seq for c in chrono2]
    assert chrono_seqs.index("07") < chrono_seqs.index("06")


def test_agenda_minutes_agent_chronological_ordering():
    """验证纪要输出列表严格按现场讨论先后顺序（跟随文本），且标题来自议程单。"""
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(seq="01", title="议程原案A：小艺慧记发布", presenters=["申家坤"]),
            AgendaItemParsed(seq="02", title="议程原案B：翻译海外发布", presenters=["刘畅"]),
            AgendaItemParsed(seq="03", title="议程原案C：HAG商用评审", presenters=["沙彬斌"]),
            AgendaItemParsed(seq="04", title="议程原案D：SpeechASR评审", presenters=["陆敬怡"]),
        ]
    )
    # 现场先讨论议题02，再讨论议题04，议题01和03未讨论
    transcript = (
        "刘畅 00:20:00\n关于翻译海外发布，时延120ms...\n\n"
        "陆敬怡 00:40:00\n关于SpeechASR评审，通用测试集下降0.7个点..."
    )
    alignment_res = align_agenda_with_transcript(plan, transcript)
    assert [c.item.seq for c in alignment_res.chronological_alignments] == ["02", "04", "01", "03"]

    class DummyClient:
        pass

    agent = AgendaMinutesAgent(DummyClient())
    enforced = agent._enforce_agenda_invariants({}, alignment_res)
    items = enforced["agenda_items"]
    assert [it["agenda_seq"] for it in items] == ["02", "04", "01", "03"]
    assert items[0]["agenda_title"] == "议程原案B：翻译海外发布"
    assert items[0]["discussion_state"] == "discussed"
    assert items[0]["time_range"] == "00:20"
    assert items[1]["agenda_title"] == "议程原案D：SpeechASR评审"
    assert items[1]["discussion_state"] == "discussed"
    assert items[1]["time_range"] == "00:40"
    assert items[2]["agenda_title"] == "议程原案A：小艺慧记发布"
    assert items[2]["discussion_state"] == "skipped"
    assert items[2]["time_range"] == "—"
    assert items[3]["agenda_title"] == "议程原案C：HAG商用评审"
    assert items[3]["discussion_state"] == "skipped"
    assert items[3]["time_range"] == "—"


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
    assert items[0]["resolution"] == "原则同意"

    # 议题 2：未讨论议题的脑补事实被 100% 确定性清空置空
    assert items[1]["agenda_seq"] == "02"
    assert items[1]["agenda_title"] == "官方议题B：关于音频降噪的架构审议"
    assert items[1]["status_tag"] == "本次未讨论"
    assert items[1]["discussion_state"] == "skipped"
    assert items[1]["proposal_highlights"] == []
    assert items[1]["deliberation_details"]["key_metrics"] == []
    assert items[1]["resolution"] == ""


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
    assert "### 议题 01 · 翻译海外HiTranslationService 21.1.1.300商用版本发布" in md_output
    assert "#### 1. 目标与对象" in md_output
    assert "#### 2. 内容与依据" in md_output
    assert "#### 3. 过程与互动" in md_output
    assert "#### 4. 结论与状态" in md_output
    assert "#### 5. 行动与效果" in md_output
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
    assert "目标与对象" in html_output
    assert "内容与依据" in html_output
    assert "过程与互动" in html_output
    assert "结论与状态" in html_output
    assert "行动与效果" in html_output
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


@pytest.mark.asyncio
async def test_agenda_minutes_fallback_in_orchestrator():
    """测试当 Supervisor 驳回降级时，Orchestrator 产出完整的 Markdown 纪要而非裸字典。"""
    from domain.meeting.orchestrator import MeetingAgentSystem
    class DummyClient:
        pass
    orch = MeetingAgentSystem(client=DummyClient())

    draft = {
        "meeting_meta": {"theme": "降级测试例会", "date_time": "2026/09/28"},
        "agenda_items": [
            {
                "agenda_seq": "01",
                "agenda_title": "测试议题一",
                "presenter": "张工",
                "status_tag": "[审议通过]",
                "proposal_highlights": ["方案陈述"],
                "resolution": "同意",
                "discussion_state": "discussed",
            }
        ],
    }
    state = {
        "lines": {"agenda_minutes": {"draft": draft}},
        "title": "降级测试例会",
    }

    fallback_node = orch._make_fallback_node("agenda_minutes")
    out = await fallback_node(state)

    line_out = out["lines"]["agenda_minutes"]
    assert line_out["degraded"] is True
    rendered_text = line_out["rendered"]
    # 验证降级产物是完整的 Markdown 而非 str(dict)
    assert "# 议程纪要" in rendered_text
    assert "### 议题 01 · 测试议题一" in rendered_text
    assert len(line_out["structure"]) == 1


@pytest.mark.asyncio
async def test_fail_fast_when_agenda_empty():
    """测试若未能从输入提取出会前议程单，Agent 立即 Fail-Fast，绝不反向解析转写污染骨架。"""
    class DummyClient:
        pass

    agent = AgendaMinutesAgent(DummyClient())
    with pytest.raises(ValueError, match="未能从输入文档中解析出会前既定议程单"):
        await agent.run("这里只有会议转写，没有议程表格也没有任何议程序号...")


@pytest.mark.asyncio
async def test_agenda_minutes_agent_map_reduce_concurrency():
    """验证 Map-Reduce 并发抽取架构：多议题并发提取且跳过项零 Token 调用。"""
    shared_context = """【既定议程单】
| 编号 | 议题名称 | 汇报人 |
| --- | --- | --- |
| 1 | 议题A：输入法引擎优化 | 赵鑫岳 |
| 2 | 议题B：语音识别模型评审 | 陆敬怡 |
| 3 | 议题C：离线翻译轻量化 | 张三（未出席） |

【会议原文】
赵鑫岳 00:10:00
输入法引擎进行了全链路重构，时延由 120ms 下降至 85ms，本次提请商用。

陆敬怡 00:30:00
SpeechASR 模型完成通用测试集验证，虽然劣化 40ms 但现网表现可控，整体结论 go。
"""
    called_labels: list[str] = []

    class MockClient:
        async def structured(self, sys, user, model_cls, contract, label="", max_tokens=None):
            called_labels.append(label)
            if "item_01" in label:
                return model_cls(
                    presenter="赵鑫岳",
                    status_tag="[审议通过]",
                    proposal_highlights=["输入法引擎全链路重构"],
                    deliberation_details={"key_metrics": ["时延 85ms"], "feedback_concerns": []},
                    resolution="同意商用发布",
                    action_commitments=[],
                )
            elif "item_02" in label:
                return model_cls(
                    presenter="陆敬怡",
                    status_tag="[审议通过]",
                    proposal_highlights=["SpeechASR 模型测试"],
                    deliberation_details={"key_metrics": ["劣化 40ms"], "feedback_concerns": []},
                    resolution="整体结论 go",
                    action_commitments=[],
                )
            raise ValueError(f"Unexpected label {label}")

        async def text(self, sys, user, label="", max_tokens=None):
            return "输入法与语音识别评审顺利通过，未参会议题顺延。"

    agent = AgendaMinutesAgent(MockClient())
    res = await agent.run(shared_context)

    # 1. 验证仅讨论过的 01 和 02 调用了单议题抽取 LLM，03 未调用
    assert "agenda_minutes/item_01" in called_labels
    assert "agenda_minutes/item_02" in called_labels
    assert not any("item_03" in lbl for lbl in called_labels)

    # 2. 验证结果包含完整的 3 个议题且骨架锁定
    items = res.agenda_items
    assert len(items) == 3
    assert items[0]["agenda_seq"] == "01"
    assert items[0]["discussion_state"] == "discussed"
    assert "85ms" in items[0]["deliberation_details"]["key_metrics"][0]

    assert items[1]["agenda_seq"] == "02"
    assert items[1]["discussion_state"] == "discussed"
    assert items[1]["resolution"] == "整体结论 go"

    # 3. 验证未讨论的 03 确定性置空
    assert items[2]["agenda_seq"] == "03"
    assert items[2]["discussion_state"] == "skipped"
    assert items[2]["status_tag"] == "本次未讨论"
    assert items[2]["proposal_highlights"] == []

    # 4. 验证总体评价已去除
    assert not res.meeting_meta.get("overview_headline")


def test_enhanced_state_machine_roadsign_and_buffer_isolation():
    """验证泛化性增强特性：
    1. 致谢语义消歧（答辩抗辩 vs. 真实收尾）；
    2. 主持人串场路标（精确人名/称谓/泛指）；
    3. 设备闲聊识别；
    4. 转场缓冲带隔离（闲聊与调麦不污染上一议题）。
    """
    from domain.meeting.tasks.agenda_minutes.alignment_engine import (
        _is_session_closing,
        _is_opening_signal,
        _is_equipment_or_chitchat,
        _detect_host_roadsign,
        align_agenda_with_transcript,
    )

    # 1. 致谢消歧
    assert _is_session_closing("整体结论是go，闭环之后再发，谢谢各位评委，好，拜拜") is True
    assert _is_session_closing("那我先下了，拜拜") is True
    assert _is_session_closing("谢谢评委提醒，我再解释一下原因") is False
    assert _is_session_closing("感谢老师提出的建议，我们后续版本会纳入考虑") is False

    # 2. 开场与设备闲聊
    assert _is_opening_signal("各位评委好，我来共享一下屏幕，开始汇报") is True
    assert _is_opening_signal("下面由我汇报本次版本") is True
    assert _is_equipment_or_chitchat("喂喂喂，能听到我声音吗？") is True
    assert _is_equipment_or_chitchat("大家稍等两分钟，我先倒杯水") is True
    assert _is_equipment_or_chitchat("这次版本主要优化了SpeechASR在离线长语音场景下的性能时延") is False

    # 3. 主持人交通警察路标
    plan = AgendaPlan(
        items=[
            AgendaItemParsed(seq="01", title="小艺慧记版本发布", presenters=["申家坤"]),
            AgendaItemParsed(seq="02", title="翻译海外需求评审", presenters=["刘畅"]),
            AgendaItemParsed(seq="03", title="SpeechASR评测", presenters=["陆敬怡", "林宇珂"]),
        ]
    )
    hubs = {"高雄", "徐锋"}

    # 主持人精准呼叫称谓（"林工"）
    seq, is_gen = _detect_host_roadsign("高雄", "辛苦刘工，下面有请林工汇报下一个议题", plan, hubs)
    assert seq == "03"
    assert is_gen is False

    # 主持人呼叫议题专名（"小艺慧记"）
    seq, is_gen = _detect_host_roadsign("高雄", "好的，我们切到下一个，小艺慧记", plan, hubs)
    assert seq == "01"
    assert is_gen is False

    # 主持人泛指串场
    seq, is_gen = _detect_host_roadsign("徐锋", "好的那有请下一位", plan, hubs)
    assert seq is None
    assert is_gen is True

    # 非主持人讨论内容不误报（如汇报人描述幻灯片布局"下面这个区域"）
    seq, is_gen = _detect_host_roadsign("刘畅", "然后小艺下面这个区域是配置项", plan, hubs)
    assert seq is None
    assert is_gen is False

    # 4. 转场缓冲带隔离测试：会间闲聊调设备不污染议题
    synthetic_transcript = """
刘畅 00:10:00
各位评委好，我来汇报翻译海外需求。本次核心是俄罗斯节点迁移与时延优化。
高雄 00:11:00
这个迁移会影响现网吗？
刘畅 00:11:20
不会，双机房热备，结论是go，闭环后发邮件，谢谢各位评委，好，拜拜。
高雄 00:12:00
好的辛苦刘畅。
李四 00:12:10
喂喂喂，能听到吗？大家稍微等两分钟，我去倒杯水。
高雄 00:14:00
下面有请林工汇报 SpeechASR。
林宇珂 00:14:20
各位评委晚上好，我来共享一下桌面，本次 SpeechASR 主要是 4.300 补丁版本。
高雄 00:15:00
时延指标怎么样？
林宇珂 00:15:20
时延下降 15%，整体结论是go，多谢大家拜拜。
"""
    res = align_agenda_with_transcript(plan, synthetic_transcript)
    assert res.discussed_count == 2
    a2 = [a for a in res.alignments if a.item.seq == "02"][0]
    a3 = [a for a in res.alignments if a.item.seq == "03"][0]

    # 验证议题 02 与 03 都被正常匹配且包含对应主讲人
    assert "刘畅" in a2.matched_speakers
    assert "林宇珂" in a3.matched_speakers

    # 核心验证：转场期间李四的倒水和调麦闲聊没有被贪婪污染到议题 02 的证据中！
    a2_evidence = a2.evidence_text
    assert "我去倒杯水" not in a2_evidence
    assert "喂喂喂" not in a2_evidence
    assert "俄罗斯节点" in a2_evidence


def test_agenda_types_registry_and_specs():
    """测试 9 大会议类型注册表与 Spec 规范定义。"""
    from domain.meeting.tasks.agenda_minutes.types import (
        AGENDA_TYPE_REGISTRY,
        detect_agenda_type,
        get_agenda_type_spec,
    )
    from domain.meeting.tasks.agenda_minutes.prompts import build_single_item_prompt

    assert len(AGENDA_TYPE_REGISTRY) == 9
    expected_types = [
        "decision_approval",
        "review_selection",
        "planning_strategy",
        "alignment_consensus",
        "info_sync",
        "retrospective",
        "brainstorming",
        "release_broadcast",
        "knowledge_share",
    ]
    for tid in expected_types:
        spec = get_agenda_type_spec(tid)
        assert spec.type_id == tid
        assert spec.type_name
        assert spec.core_purpose
        assert spec.core_output
        assert len(spec.pillars) == 5
        guidance = spec.format_prompt_guidance()
        assert spec.type_name in guidance
        assert "1. 目标与对象" in guidance
        assert "5. 行动与效果" in guidance

    # 测试未知类型安全降级
    fallback_spec = get_agenda_type_spec("non_existent_type")
    assert fallback_spec.type_id == "decision_approval"

    # 测试 build_single_item_prompt 动态拼接
    prompt = build_single_item_prompt(fallback_spec)
    assert "决策审批型" in prompt
    assert "target_and_audience" in prompt
    assert "action_items" in prompt


def test_detect_agenda_type_all_categories():
    """测试基于会议主题与上下文的 9 大类型智能路由器。"""
    from domain.meeting.tasks.agenda_minutes.types import detect_agenda_type

    # 1. 决策审批型
    assert detect_agenda_type("智慧域商用发布评审").type_id == "decision_approval"
    assert detect_agenda_type("关于2026年项目立项与预算审批会").type_id == "decision_approval"

    # 2. 评审选型型
    assert detect_agenda_type("向量数据库技术方案选型评审会").type_id == "review_selection"
    assert detect_agenda_type("大模型基础设施架构评审与供应商评选").type_id == "review_selection"

    # 3. 规划策略型
    assert detect_agenda_type("2026年Q3业务战略与路线图规划会").type_id == "planning_strategy"
    assert detect_agenda_type("年度研发优先级排序与资源规划研讨").type_id == "planning_strategy"

    # 4. 对齐共识型
    assert detect_agenda_type("前后端系统接口契约对齐与联调拉通会").type_id == "alignment_consensus"
    assert detect_agenda_type("跨部门协作职责边界敲定会").type_id == "alignment_consensus"

    # 5. 信息同步型
    assert detect_agenda_type("开发团队周例会及阻塞项同步").type_id == "info_sync"
    assert detect_agenda_type("敏捷迭代每日站会").type_id == "info_sync"

    # 6. 复盘归因型
    assert detect_agenda_type("0618线上突发故障根因分析与复盘会").type_id == "retrospective"
    assert detect_agenda_type("端午大促项目复盘总结会").type_id == "retrospective"

    # 7. 创意发散型
    assert detect_agenda_type("AI原生产品创新头脑风暴工作坊").type_id == "brainstorming"
    assert detect_agenda_type("增长黑客发散创意研讨会").type_id == "brainstorming"

    # 8. 发布传播型
    assert detect_agenda_type("智能终端新一代操作系统全网发布宣贯会").type_id == "release_broadcast"
    assert detect_agenda_type("对外公告与媒体答疑口径统一会").type_id == "release_broadcast"

    # 9. 知识分享型
    assert detect_agenda_type("Agent架构底层原理解析与技术沙龙").type_id == "knowledge_share"
    assert detect_agenda_type("新员工代码规范培训与知识分享").type_id == "knowledge_share"

    # 10. 兜底测试
    assert detect_agenda_type("常规会议讨论").type_id == "decision_approval"


def test_single_agenda_item_model_bi_directional_compat():
    """测试 SingleAgendaItemModel 在 1~5 纯干货字段与老字段之间的双向平滑兼容。"""
    from domain.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import SingleAgendaItemModel

    # 1. 传入全新 1~5 字段
    new_data = {
        "presenter": "刘畅",
        "status_tag": "[原则同意]",
        "target_and_audience": ["申请商用准入许可", "面向评委会"],
        "content_and_evidence": ["双机房热备部署", "时延降至 85ms"],
        "process_and_interaction": ["评委质询故障逃逸，出具演练日志释疑"],
        "conclusion_and_status": "原则同意发布，灰度比例10%内",
        "action_items": [{"owner": "刘畅", "task": "签署核查单", "deadline": "9月30日"}],
    }
    model1 = SingleAgendaItemModel.validate(new_data)
    assert model1.target_and_audience == ["申请商用准入许可", "面向评委会"]
    assert model1.content_and_evidence == ["双机房热备部署", "时延降至 85ms"]
    assert model1.process_and_interaction == ["评委质询故障逃逸，出具演练日志释疑"]
    assert model1.conclusion_and_status == "原则同意发布，灰度比例10%内"
    assert len(model1.action_items) == 1
    # 验证老字段被完全向上兼容填充
    assert model1.proposal_highlights == model1.target_and_audience
    assert model1.deliberation_details["key_metrics"] == model1.content_and_evidence
    assert model1.deliberation_details["feedback_concerns"] == model1.process_and_interaction
    assert model1.resolution == model1.conclusion_and_status
    assert model1.action_commitments == model1.action_items

    # 2. 传入老字段数据，验证自动映射至 1~5 字段
    legacy_data = {
        "presenter": "沙彬斌",
        "status_tag": "[审议通过]",
        "proposal_highlights": ["升级微服务架构"],
        "deliberation_details": {
            "key_metrics": ["吞吐量提升 30%"],
            "feedback_concerns": ["关注内存增长风险"],
        },
        "resolution": "方案通过，按计划上线",
        "action_commitments": [{"owner": "沙彬斌", "task": "压测", "deadline": "下周"}],
    }
    model2 = SingleAgendaItemModel.validate(legacy_data)
    assert model2.target_and_audience == ["升级微服务架构"]
    assert model2.content_and_evidence == ["吞吐量提升 30%"]
    assert model2.process_and_interaction == ["关注内存增长风险"]
    assert model2.conclusion_and_status == "方案通过，按计划上线"
    assert len(model2.action_items) == 1
    assert model2.action_items[0]["owner"] == "沙彬斌"


def test_shangping1_ocr_alignment_discussed_and_skipped():
    """验证从 OCR 识别出的商评1议程单在对齐引擎中的表现。
    
    核心目标：
    - 议题 02（刘畅）：必须 discussed，且刘畅绝不能被误判为 Hub Speaker；
    - 议题 04（SpeechASR）：必须 discussed；
    - 议题 01 与 03：skipped。
    """
    ocr_shangping = """
**会议主题**：智慧域商用发布评审
**会议时间**：2026/06/15（周一）16:00-18:00（UTC+08:00）Beijing
- **全程与会人/主持人**：徐锋；索勋飞；吴友国；王昊；黄江；何瑄；左飞
- **分段列席人**：申家坤；方思邈；李腾飞；郑本令；沙彬斌；陈锴；刘畅；陈坤

| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| :--- | :--- | :--- | :--- |
| 01 | 小艺慧记 CeliaMinutesService 1.4.5.500 版本发布商用版本 | 申家坤 | 15min |
| 02 | 翻译海外 HiTranslationService 21.1.1.300 商用版本发布 | 刘畅 | 15min |
| 03 | HAG 3.6.5.300 版本商用发布评审 | 沙彬斌；陈锴 | 15min |
| 04 | SpeechASR 1.4.5.302 商用版本评审 | 陆敬怡；林宇珂；赖朝辉 | 15min |
"""
    docx_path = AGENDA_DIR / "test1" / "商评1.docx"
    if not docx_path.is_file():
        pytest.skip("商评1.docx not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(ocr_shangping)

    res = align_agenda_with_transcript(plan, transcript)
    assert res.discussed_count == 2
    assert res.skipped_count == 2

    # 验证议题 02 成功对齐刘畅
    a2 = res.alignments[1]
    assert a2.item.seq == "02"
    assert a2.status == "discussed"
    assert "刘畅" in a2.matched_speakers
    assert len(a2.matched_blocks) >= 50

    # 验证议题 04 成功对齐陆敬怡
    a4 = res.alignments[3]
    assert a4.item.seq == "04"
    assert a4.status == "discussed"
    assert "陆敬怡" in a4.matched_speakers


def test_test5_academic_forum_dual_identity_and_multiline():
    """验证 test5 西工大（学术论坛模式）：
    - 组织主席张晓雷兼任议题04主讲人（双重身份仲裁）；
    - 转写中连续空行与多段发言顺利切块；
    - 4 项特邀报告全部有效对齐讨论。
    """
    docx_path = AGENDA_DIR / "test5" / "西工大会议.docx"
    if not docx_path.is_file():
        pytest.skip("西工大会议.docx not found")

    ocr_test5 = """
**会议名称**：CCF语音专委“走进高校”系列活动 第三站：西北工业大学
- **时间**：2022年11月05日 09:30-11:30
- **全程与会人/主持人**：张晓雷

| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| :--- | :--- | :--- | :--- |
| 01 | 面向智能声学与临境通信应用的多通道声信号感知、处理与重构 | 陈景东 | 09:30-10:00 |
| 02 | 智能语音技术的新进展——NPU-ASLP Lab视角 | 谢磊 | 10:00-10:30 |
| 03 | 软硬联合优化的声学前端探索 | 付中华 | 10:30-11:00 |
| 04 | 鲁棒语音处理与安全 | 张晓雷 | 11:00-11:30 |
"""
    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(ocr_test5)

    res = align_agenda_with_transcript(plan, transcript)
    assert res.discussed_count == 4
    assert res.skipped_count == 0

    assert "陈景东" in res.alignments[0].matched_speakers
    assert "谢磊" in res.alignments[1].matched_speakers
    assert "付中华" in res.alignments[2].matched_speakers
    assert "张晓雷" in res.alignments[3].matched_speakers


def test_test6_annual_summit_native_host_and_keynotes():
    """验证 test6 学术年会（年会模式）：
    - 文本端自省发言人“主持人”并隔离串场；
    - 5 项特邀报告全部有效对齐讨论。
    """
    docx_path = AGENDA_DIR / "test6" / "学术年会.docx"
    if not docx_path.is_file():
        pytest.skip("学术年会.docx not found")

    ocr_test6 = """
- **全程与会人/主持人**：俞凯；高虹

| 序号 | 议题名称 | 汇报人/主讲人 | 预计时长 |
| :--- | :--- | :--- | :--- |
| 01 | 语音模仿与鉴别 | 陶建华 | 09:30-10:15 |
| 02 | 声学所语音识别最新进展及应用 | 颜永红 | 10:30-11:15 |
| 03 | 百度语音在建模技术、多模态和芯片方面的最新进展 | 贾磊 | 11:15-12:00 |
| 04 | 声纹识别应用的技术挑战 | 郑方 | 13:00-13:45 |
| 05 | 语音合成中的自然韵律多样性建模 | 俞凯 | 13:45-14:30 |
"""
    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    plan = parse_agenda_text(ocr_test6)

    res = align_agenda_with_transcript(plan, transcript)
    assert res.discussed_count == 5
    assert res.skipped_count == 0

    assert "陶建华" in res.alignments[0].matched_speakers
    assert "颜永红" in res.alignments[1].matched_speakers
    assert "贾磊" in res.alignments[2].matched_speakers
    assert "郑方" in res.alignments[3].matched_speakers
    assert "俞凯" in res.alignments[4].matched_speakers


def test_shangping2_typo_chenqicuo_reconciled():
    """验证 商评2 中 OCR 识别错字（陈啟错）的自动纠错与对齐：
    1. match_presenter_name 识别 错 与 锴 的 OCR 易混变体，打分达 0.95；
    2. parse_agenda_text 传入 transcript 时自动校准为真实发言人 陈啟锴；
    3. align_agenda_with_transcript 将第 5 项（HAG）成功判定为 discussed，不再沦为 [本次未讨论]。
    """
    from domain.meeting.tasks.agenda_minutes.agenda_parser import (
        match_presenter_name,
        parse_agenda_text,
    )
    from domain.meeting.tasks.agenda_minutes.alignment_engine import align_agenda_with_transcript

    # 1. 变体与形似容错打分
    assert match_presenter_name("陈啟错", "陈啟锴") >= 0.9
    assert match_presenter_name("陈启蒙", "陈啟锴") == 0.0  # 杜绝异人同姓字辈误伤

    docx_path = AGENDA_DIR / "test2" / "商评2.docx"
    txt_path = AGENDA_DIR / "test2" / "商评2.txt"
    if not docx_path.is_file() or not txt_path.is_file():
        pytest.skip("Test 2 files not found")

    doc = docx.Document(str(docx_path))
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    # 模拟 OCR 出现错别字 陈啟错
    agenda_with_typo = txt_path.read_text(encoding="utf-8").replace("陈啟锴", "陈啟错")
    assert "陈啟错" in agenda_with_typo

    plan = parse_agenda_text(agenda_with_typo, transcript=transcript)
    hag_item = next(it for it in plan.items if "HAG" in it.title)
    assert "陈啟锴" in hag_item.presenters

    res = align_agenda_with_transcript(plan, transcript)
    hag_align = next(a for a in res.alignments if "HAG" in a.item.title)
    assert hag_align.status == "discussed"
    assert len(hag_align.matched_blocks) > 0
    assert res.discussed_count == 9
    assert res.skipped_count == 0


def test_agenda_minutes_table_full_conclusion_no_truncation():
    """验证总览表格核心结论优化：
    1. 表头列名由 '核心结论与后续安排' 简化为 '核心结论'；
    2. HTML 与 Markdown 输出均不产生 [:80] / [:57] 机械截断；
    3. 列表型结论自动平铺为分号拼接的干净正文，杜绝 Python repr 形如 ['...'] 的括号引号污染。
    """
    from tools.exports.html.agenda_minutes import (
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


def test_agenda_parser_test7_table_without_presenter():
    """验证 test7 议程解析：
    1. 适配表头为 | 序号 | 时间 | 环节 | 内容说明 | 的表结构；
    2. 无汇报人列时正常解析为 5 项，title 为环节，description 为内容说明；
    3. 完整保留何刚总致辞、互动交流、任务令签署与授予、全体合影等核心议程。
    """
    ocr_test7 = """
会议日程表
会议主题：何刚总北研所交流会
会议时间：2026年09月23日9:00—11:00
会议地点：北研所Q1-A031

| 序号 | 时间 | 环节 | 内容说明 |
| :--- | :--- | :--- | :--- |
| 01 | 09:00-09:10 | 视频观看 | 活动开场视频播放 |
| 02 | 09:10-09:30 | 何刚总致辞 | 领导致辞 |
| 03 | 09:30-10:30 | 互动交流 | 现场问答、自由交流与讨论 |
| 04 | 10:30-10:40 | 任务令签署与授予 | 任务令签署仪式及授予环节 |
| 05 | 10:40-10:50 | 全体合影 | 全体参会人员合影留念 |
"""
    plan = parse_agenda_text(ocr_test7)
    assert plan.meta.theme == "何刚总北研所交流会"
    assert len(plan.items) == 5

    assert plan.items[0].seq == "01"
    assert plan.items[0].title == "视频观看"
    assert plan.items[0].description == "活动开场视频播放"
    assert plan.items[0].presenters == []

    assert plan.items[1].seq == "02"
    assert plan.items[1].title == "何刚总致辞"
    assert plan.items[1].description == "领导致辞"

    assert plan.items[2].seq == "03"
    assert plan.items[2].title == "互动交流"
    assert plan.items[2].description == "现场问答、自由交流与讨论"

    assert plan.items[3].seq == "04"
    assert plan.items[3].title == "任务令签署与授予"
    assert plan.items[3].description == "任务令签署仪式及授予环节"

    assert plan.items[4].seq == "05"
    assert plan.items[4].title == "全体合影"
    assert plan.items[4].description == "全体参会人员合影留念"


def test_alignment_engine_test7_anonymous_speaker_logs():
    """验证 test7 匿名说话人日志（Track B: Content & Roadsign Alignment）：
    1. group_transcript_blocks 成功解析 '发言者 1 00:00:03' 等全部 488 个发言块；
    2. 自适应路由嗅探识别出 Track B (CONTENT)；
    3. 状态机精准锚定 4 项已讨论议题与 1 项未讨论议题（01视频观看因未录制跳过）；
    4. 骨架后置强约束生成正确的时序重构与区间（00:00 ~ 00:18, 00:18 ~ 01:18 等）。
    """
    docx_path = AGENDA_DIR / "test7" / "说话人日志.docx"
    if not docx_path.is_file():
        pytest.skip("说话人日志.docx not found")

    import docx
    doc = docx.Document(docx_path)
    transcript = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    blocks = group_transcript_blocks(transcript)
    assert len(blocks) == 488
    assert blocks[0].speaker == "发言者 1"
    assert blocks[0].timestamp == "00:00:03"

    ocr_test7 = """
会议主题：何刚总北研所交流会
会议时间：2026年09月23日9:00—11:00

| 序号 | 时间 | 环节 | 内容说明 |
| :--- | :--- | :--- | :--- |
| 01 | 09:00-09:10 | 视频观看 | 活动开场视频播放 |
| 02 | 09:10-09:30 | 何刚总致辞 | 领导致辞 |
| 03 | 09:30-10:30 | 互动交流 | 现场问答、自由交流与讨论 |
| 04 | 10:30-10:40 | 任务令签署与授予 | 任务令签署仪式及授予环节 |
| 05 | 10:40-10:50 | 全体合影 | 全体参会人员合影留念 |
"""
    plan = parse_agenda_text(ocr_test7)
    res = align_agenda_with_transcript(plan, transcript)

    # 4 项讨论，1 项跳过
    assert res.discussed_count == 4
    assert res.skipped_count == 1

    align_map = {a.item.seq: a for a in res.alignments}

    # 01 视频观看 未播放，确定性置空
    assert align_map["01"].status == "skipped"
    assert len(align_map["01"].matched_blocks) == 0

    # 02 何刚总致辞 命中致辞路标
    assert align_map["02"].status == "discussed"
    assert len(align_map["02"].matched_blocks) > 30
    assert align_map["02"].start_index == 0

    # 03 互动交流 命中团队交流路标
    assert align_map["03"].status == "discussed"
    assert len(align_map["03"].matched_blocks) > 300

    # 04 任务令签署与授予 命中任务令签发仪式路标
    assert align_map["04"].status == "discussed"
    assert len(align_map["04"].matched_blocks) > 10

    # 05 全体合影 命中尾声合影留念路标
    assert align_map["05"].status == "discussed"
    assert len(align_map["05"].matched_blocks) >= 2

    # 验证时序重构与骨架锁定
    class DummyClient:
        pass

    agent = AgendaMinutesAgent(DummyClient())
    enforced = agent._enforce_agenda_invariants({}, res)
    items = enforced["agenda_items"]

    # 讨论过的按现场研讨先后排列，未讨论的置于末尾
    assert [it["agenda_seq"] for it in items] == ["02", "03", "04", "05", "01"]
    assert items[0]["agenda_title"] == "何刚总致辞"
    assert items[0]["time_range"] == "00:00 ~ 00:18"
    assert items[0]["discussion_state"] == "discussed"

    assert items[1]["agenda_title"] == "互动交流"
    assert items[1]["time_range"] == "00:18 ~ 01:18"
    assert items[1]["discussion_state"] == "discussed"

    assert items[2]["agenda_title"] == "任务令签署与授予"
    assert items[2]["time_range"] == "01:18 ~ 01:21"
    assert items[2]["discussion_state"] == "discussed"

    assert items[3]["agenda_title"] == "全体合影"
    assert items[3]["time_range"] == "01:22"
    assert items[3]["discussion_state"] == "discussed"

    assert items[4]["agenda_title"] == "视频观看"
    assert items[4]["time_range"] == "—"
    assert items[4]["discussion_state"] == "skipped"


def test_paddle_ocr_join_row_texts_avoids_name_concatenation():
    """测试 PaddleOCR 同行拼接时，避免将汇报人与记录人无缝粘连为单个姓名。"""
    from tools.ocr.paddle_ocr import _join_row_texts

    # 汇报人与记录人相邻
    merged = _join_row_texts(["陆敬怡;林宇珂;赖朝辉", "王旭"])
    assert merged == "陆敬怡;林宇珂;赖朝辉 王旭"
    assert "赖朝辉王旭" not in merged

    # 带分号结尾的正常列表
    merged_semi = _join_row_texts(["沙彬斌；", "陈啟锴"])
    assert merged_semi == "沙彬斌；陈啟锴"


def test_prepare_agenda_ocr_prompt_text_filters_sidebar_and_preserves_columns():
    """测试 prepare_agenda_ocr_prompt_text 能正确过滤左侧装饰性侧栏标签，并按水平行聚类。"""
    from domain.meeting.tasks.agenda_minutes.agenda_extractor import prepare_agenda_ocr_prompt_text

    raw_lines = [
        {"text": "会议主题：智慧域商用发布评审", "bbox": [[250, 580], [450, 580], [450, 600], [250, 600]]},
        # 左侧装饰标签 (x=50 < 150)
        {"text": "会议议题", "bbox": [[50, 980], [100, 980], [100, 1000], [50, 1000]]},
        {"text": "Agenda", "bbox": [[50, 1010], [100, 1010], [100, 1030], [50, 1030]]},
        # 议题 1 行内各列 (y~950)
        {"text": "1", "bbox": [[255, 950], [270, 950], [270, 970], [255, 970]]},
        {"text": "小艺慧记版本发布", "bbox": [[350, 950], [600, 950], [600, 970], [350, 970]]},
        {"text": "15min", "bbox": [[770, 950], [820, 950], [820, 970], [770, 970]]},
        {"text": "申家坤", "bbox": [[1140, 950], [1190, 950], [1190, 970], [1140, 970]]},
        # 议题 2 行内各列 (y~1010)
        {"text": "翻译海外商用发布", "bbox": [[350, 1010], [600, 1010], [600, 1030], [350, 1030]]},
        {"text": "15min", "bbox": [[770, 1010], [820, 1010], [820, 1030], [770, 1030]]},
        {"text": "刘畅", "bbox": [[1140, 1010], [1190, 1010], [1190, 1030], [1140, 1030]]},
    ]

    res = prepare_agenda_ocr_prompt_text(raw_lines)
    # 验证左侧侧栏装饰性标签已被过滤
    assert "会议议题" not in res
    assert "Agenda" not in res
    # 验证同一行内单元格用 "  |  " 明确分隔
    assert "1  |  小艺慧记版本发布  |  15min  |  申家坤" in res
    assert "翻译海外商用发布  |  15min  |  刘畅" in res
