# 拆分自 test_agenda_pipeline.py，覆盖：test_agenda_minutes_agent_chronological_ordering, test_agenda_minutes_agent_enforce_invariants, test_agenda_minutes_agent_map_reduce_concurrency…

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
