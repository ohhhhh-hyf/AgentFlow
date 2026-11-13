"""阶段四单元自测：纪要端到端流式直出 Agent、Prompts 体系与多源装配器。"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(DEMO_ROOT))

import pytest
from tasks.minutes.agenda.alignment import ValidAgendaItem
from tasks.minutes.agent import (
    build_minutes_user_message,
    clean_markdown_fence,
    generate_minutes,
    stream_minutes_agent,
)
from tasks.minutes.multi_source import (
    build_aux_rules_for_prompt,
    build_multi_source_context,
)
from tasks.minutes.prompts import (
    AGENDA_COLUMN_MAJOR_PROMPT,
    AGENDA_TOPIC_MAJOR_PROMPT,
    NORMAL_MINUTES_PROMPT,
    select_minutes_prompt,
)


def test_prompts_selection():
    """测试三大 System Prompt 路由选择与核心契约。"""
    # 1. 普通纪要
    prompt_normal = select_minutes_prompt(is_agenda=False)
    assert prompt_normal == NORMAL_MINUTES_PROMPT
    assert "纯净 Markdown 直出" in prompt_normal
    assert "方括号 `[...]`" in prompt_normal
    assert "# 栏目名" in prompt_normal

    # 2. 议题纪要 (栏目主序)
    prompt_col = select_minutes_prompt(is_agenda=True, layout_mode="column_major")
    assert prompt_col == AGENDA_COLUMN_MAJOR_PROMPT
    assert "## 一. [审定议题全称]" in prompt_col
    assert "严禁自行改名、合并、拆分或重排" in prompt_col

    # 3. 议题纪要 (议题主序容器)
    prompt_topic = select_minutes_prompt(is_agenda=True, layout_mode="topic_major")
    assert prompt_topic == AGENDA_TOPIC_MAJOR_PROMPT
    assert "议题主序容器模式" in prompt_topic
    assert "### 要点梳理" in prompt_topic
    assert "### 结论定调" in prompt_topic


def test_multi_source_assembly():
    """测试多源辅助材料（keypoints, notes, vision）的装配与规约拼接。"""
    texts = {
        "keypoints": ["重点关注 TPS 突破 5000", "Q4 营销预算控制在 200 万内"],
        "notes": [
            {"quote": "我们底线是保证核心交易不丢单", "note": "重点记下这句"},
            {"quote": "下周五前出方案"},
        ],
        "vision": "架构拓扑图显示双机房主备切换",
    }
    aux_context, labels = build_multi_source_context(texts)
    assert set(labels) == {"keypoints", "notes", "vision"}
    assert "【辅助参考材料】" in aux_context
    assert "TPS 突破 5000" in aux_context
    assert "核心交易不丢单" in aux_context
    assert "架构拓扑图显示" in aux_context

    rules = build_aux_rules_for_prompt(labels)
    assert "用户核心关键点参考规约" in rules
    assert "用户划线原话与笔记参考规约" in rules
    assert "视觉信息参考规约" in rules

    # 测试空材料
    empty_ctx, empty_labels = build_multi_source_context({})
    assert empty_ctx == ""
    assert empty_labels == []
    assert build_aux_rules_for_prompt(empty_labels) == ""


def test_clean_markdown_fence():
    """测试防御性清理大模型开头结尾的 markdown 代码围栏。"""
    raw_1 = "```markdown\n# 全文摘要\n内容...\n```"
    assert clean_markdown_fence(raw_1) == "# 全文摘要\n内容..."

    raw_2 = "```\n# 全文摘要\n内容...\n```"
    assert clean_markdown_fence(raw_2) == "# 全文摘要\n内容..."

    raw_clean = "# 全文摘要\n内容..."
    assert clean_markdown_fence(raw_clean) == "# 全文摘要\n内容..."


def test_build_minutes_user_message_normal_sandwich():
    """测试普通模式黄金三明治结构（实录材料在前，模板规范殿后，执行指令收尾）。"""
    transcript = "张三：今天讨论支付系统改造。李四：同意。"
    template_content = "# 全文摘要\n[概述]\n\n# 要点梳理\n[细节]"
    aux_context = "【辅助参考材料】\n- 关键点：保稳定"

    msg = build_minutes_user_message(
        is_agenda=False,
        formatted_transcript=transcript,
        valid_agendas=[],
        template_content=template_content,
        aux_context=aux_context,
    )

    # 验证三明治顺序：实录在前 -> 辅助居中 -> 模板规范殿后 -> 执行指令收尾
    idx_transcript = msg.find("【会议原文转写实录】")
    idx_aux = msg.find("【辅助参考材料】")
    idx_template = msg.find("【输出模板规范】")
    idx_cmd = msg.find("【执行指令】")

    assert idx_transcript != -1
    assert idx_aux != -1
    assert idx_template != -1
    assert idx_cmd != -1
    assert idx_transcript < idx_aux < idx_template < idx_cmd
    assert template_content in msg


def test_build_minutes_user_message_agenda_dual_anchoring():
    """测试议程模式前后双锚定（头部清单导航 + 尾部清单重申临门一脚）。"""
    agendas = [
        ValidAgendaItem(seq="1", title="支付系统云原生架构改造", presenters=["张三"]),
        ValidAgendaItem(seq="2", title="2026年Q4营销预算分配", presenters=["李四"]),
    ]
    tagged_transcript = "【议题一：支付系统云原生架构改造】\n张三：开始汇报。"
    template_content = "# 全文摘要\n[概述]\n\n# 议题梳理\n[逐个议题展开]"

    msg = build_minutes_user_message(
        is_agenda=True,
        formatted_transcript=tagged_transcript,
        valid_agendas=agendas,
        template_content=template_content,
    )

    # 验证头部锚定
    idx_top_anchor = msg.find("【现场审定的有效议题清单】（头部锚定")
    idx_transcript = msg.find("【会议打标转写实录】")
    idx_template = msg.find("【输出模板规范】")
    idx_tail_anchor = msg.find("【核心议程约束与执行指令】（尾部重申")

    assert idx_top_anchor != -1
    assert idx_transcript != -1
    assert idx_template != -1
    assert idx_tail_anchor != -1

    # 验证严格顺序：头部锚定 -> 打标实录 -> 模板规范 -> 尾部重申
    assert idx_top_anchor < idx_transcript < idx_template < idx_tail_anchor

    # 验证议题名称在头部与尾部均完整出现两次
    assert msg.count("支付系统云原生架构改造") >= 2
    assert msg.count("2026年Q4营销预算分配") >= 2


def test_stream_minutes_agent_mock_normal(tmp_path: Path):
    """测试普通纪要端到端流式直出：NDJSON 分块输出与文件落盘。"""
    import asyncio

    async def _test():
        mock_tokens = [
            "# 全文摘要\n",
            "本次会议全面研讨了交易核心链路架构改造方案，拍板推进云原生改造。\n\n",
            "# 要点梳理\n",
            "## 架构设计\n",
            "- 方案明确：采用分布式架构保障高可用。\n\n",
            "# 结论定调\n",
            "- **支付系统升级**：下周五前完成基准压测。\n",
        ]

        async def fake_stream_text(prompt: str, system: str = ""):
            for t in mock_tokens:
                yield t

        mock_client = MagicMock()
        mock_client.stream_text.side_effect = fake_stream_text

        out_file = tmp_path / "test_minutes.md"
        events: list[dict] = []

        async for line in stream_minutes_agent(
            transcript="张三：讨论支付架构。李四：下周五完成基准压测。",
            template_id="general_minutes",
            output_path=out_file,
            llm_client=mock_client,
        ):
            event = json.loads(line)
            events.append(event)

        # 验证 chunk 帧
        chunks = [e for e in events if e.get("type") == "chunk"]
        assert len(chunks) == len(mock_tokens)
        assert "".join(c["text"] for c in chunks) == "".join(mock_tokens)

        # 验证 done 帧
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["code"] == 0
        assert done_events[0]["message"] == "success"
        assert done_events[0]["data"]["file_name"] == "test_minutes.md"

        # 验证本地文件落盘
        assert out_file.is_file()
        saved_text = out_file.read_text(encoding="utf-8")
        assert saved_text == "".join(mock_tokens).strip()

    asyncio.run(_test())


def test_stream_minutes_agent_mock_agenda_topic_major(tmp_path: Path):
    """测试议题纪要 (Topic Major) 端到端流式直出：议题模板加载与双锚定注入。"""
    import asyncio

    async def _test():
        captured_prompt = {}

        async def fake_stream_text(prompt: str, system: str = ""):
            captured_prompt["prompt"] = prompt
            captured_prompt["system"] = system
            yield "# 全文摘要\n本次全场共审定两项议题...\n\n"
            yield "# 议题梳理\n## 一. 支付系统重构\n### 要点梳理\n- 方案明确: 落地实施。"

        mock_client = MagicMock()
        mock_client.stream_text.side_effect = fake_stream_text

        out_file = tmp_path / "agenda_minutes.md"

        extra_data = {
            "agenda_plan": [
                {"title": "支付系统重构", "speaker": "张三"},
                {"title": "市场增长规划", "speaker": "李四"},
            ]
        }

        # 真实讨论需大于 40 字以通过实质性研讨判定
        transcript = (
            "张三：各位好，今天由我向大家做支付系统重构方案的深入汇报。本次重构基于云原生微服务体系架构设计，全面改造核心链路，压测 TPS 峰值达到 5000，整体延迟降低了 40%。\n\n"
            "李四：接下来由我汇报市场增长规划方案。在 Q4 阶段我们重点推进华东与华南大区的精准获客投放，规划投入预算 200 万元，预计实现新注册用户环比增长 35%。"
        )

        content, done = await generate_minutes(
            transcript=transcript,
            template_id="general_minutes",
            extra=extra_data,
            output_path=out_file,
            llm_client=mock_client,
        )

        # 验证生成内容与 done 状态
        assert "# 全文摘要" in content
        assert "# 议题梳理" in content
        assert done["code"] == 0

        # 验证送入大模型的 Prompt 包含了 Topic Major 系统指令与前后双锚定
        assert "议题主序容器模式" in captured_prompt["system"]
        assert "【现场审定的有效议题清单】" in captured_prompt["prompt"]
        assert "【核心议程约束与执行指令】" in captured_prompt["prompt"]
        assert "支付系统重构" in captured_prompt["prompt"]
        assert "市场增长规划" in captured_prompt["prompt"]

    asyncio.run(_test())
