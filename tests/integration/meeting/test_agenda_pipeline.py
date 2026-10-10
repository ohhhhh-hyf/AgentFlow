"""tests/integration/meeting/test_agenda_pipeline.py -- 议程驱动型会议纪要端到端生成工作流集成测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import docx
import pytest

from domains.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
    clean_presenter_names,
    parse_agenda_text,
)
from domains.meeting.tasks.agenda_minutes.alignment_engine import (
    align_agenda_with_transcript,
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

def test_agenda_minutes_fallback_in_orchestrator():
    """测试当 Supervisor 驳回降级时，Orchestrator 产出完整的 Markdown 纪要而非裸字典。"""
    import asyncio

    async def _run():
        from domains.meeting.orchestrator import MeetingAgentSystem
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
        assert "### 测试议题一" in rendered_text
        assert len(line_out["structure"]) == 1

    asyncio.run(_run())

def test_fail_fast_when_agenda_empty():
    """测试若未能从输入提取出会前议程单，Agent 立即 Fail-Fast，绝不反向解析转写污染骨架。"""
    import asyncio

    async def _run():
        class DummyClient:
            pass

        agent = AgendaMinutesAgent(DummyClient())
        with pytest.raises(ValueError, match="未能从输入文档中解析出会前既定议程单"):
            await agent.run("这里只有会议转写，没有议程表格也没有任何议程序号...")

    asyncio.run(_run())

def test_agenda_minutes_agent_map_reduce_concurrency():
    """验证 Map-Reduce 并发抽取架构：多议题并发提取且跳过项零 Token 调用。"""
    import asyncio

    async def _run():
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

    asyncio.run(_run())

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
        meta=type(AgendaPlan().meta)(theme="技术研讨交流会", date_time="2026-09-30", attendees="全体"),
        items=[
            AgendaItemParsed(seq="01", title="高密度任务签署", presenters=["张三"], raw_presenter="张三"),
            AgendaItemParsed(seq="02", title="低密度噪音过场", presenters=["李四"], raw_presenter="李四"),
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
        meta=type(AgendaPlan().meta)(theme="", date_time="2026/09/30", attendees="何总、涂总及各战队"),
        items=[
            AgendaItemParsed(seq="01", title="活动开场视频播放", presenters=[], raw_presenter=""),
            AgendaItemParsed(seq="02", title="何刚总致辞", presenters=["何刚"], raw_presenter="何刚总"),
            AgendaItemParsed(seq="03", title="互动交流（现场问答、自由交流与讨论）", presenters=[], raw_presenter=""),
            AgendaItemParsed(seq="04", title="任务令签署与授予", presenters=["涂总", "何总"], raw_presenter="涂总、何总"),
            AgendaItemParsed(seq="05", title="全体合影", presenters=[], raw_presenter=""),
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



