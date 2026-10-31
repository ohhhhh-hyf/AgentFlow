"""智能图文纪要（图文纪要 + 段落速览智能章节）端到端集成测试。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import (
    _is_intelligent_minutes_enabled,
    _maybe_generate_visual_minutes,
    _maybe_start_section_summary_task,
)
from domains.shared.section_summary.models import SectionSummary, SectionSummaryResult


class FakePrepared:
    def __init__(self, line="minutes", transcript=""):
        self.line = line
        self.transcript = transcript
        self.ctx = MagicMock()
        self.ctx.output_dir = Path("./tmp_test_output")


def test_switch_precedence_and_fallback(monkeypatch):
    """测试开关优先使用 INTELLIGENT_MINUTES_ENABLED，并向下兼容 VISUAL_MINUTES_ENABLED。"""
    monkeypatch.delenv("INTELLIGENT_MINUTES_ENABLED", raising=False)
    monkeypatch.delenv("VISUAL_MINUTES_ENABLED", raising=False)
    assert not _is_intelligent_minutes_enabled()

    monkeypatch.setenv("VISUAL_MINUTES_ENABLED", "on")
    assert _is_intelligent_minutes_enabled()

    # INTELLIGENT_MINUTES_ENABLED 优先级高于 VISUAL_MINUTES_ENABLED
    monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "off")
    assert not _is_intelligent_minutes_enabled()

    monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")
    assert _is_intelligent_minutes_enabled()


def test_maybe_start_section_summary_task(monkeypatch):
    """测试在纪要任务开启且有逐字稿时，后台并发拉起 section_summary 任务。"""
    async def _test():
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")

        # 1. 非 minutes 任务不拉起
        p_other = FakePrepared(line="agenda", transcript="00:01 张三 开会")
        assert _maybe_start_section_summary_task(p_other, "req_1") is None

        # 2. minutes 但逐字稿为空不拉起
        p_empty = FakePrepared(line="minutes", transcript="")
        assert _maybe_start_section_summary_task(p_empty, "req_2") is None

        # 3. 开关关闭不拉起
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "off")
        p_valid = FakePrepared(line="minutes", transcript="00:01 张三 开会啦")
        assert _maybe_start_section_summary_task(p_valid, "req_3") is None

        # 4. 正常拉起并发 Task
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")
        with patch(
            "domains.shared.section_summary.agenerate_section_summary",
            new=AsyncMock(return_value=SectionSummaryResult(markdown="test", sections=[])),
        ) as mock_agent:
            task = _maybe_start_section_summary_task(p_valid, "req_4")
            assert task is not None
            res = await task
            assert res.markdown == "test"
            mock_agent.assert_awaited_once_with("00:01 张三 开会啦")

    asyncio.run(_test())


def test_maybe_generate_visual_minutes_appends_section_summary(
    monkeypatch, tmp_path
):
    """验证 visual.html 的 Markdown 包含 ## 智能章节，且原 md_text 保持纯净。"""
    async def _test():
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")

        p = FakePrepared(
            line="minutes",
            transcript="[00:01:00] 张三 启动 Q3 项目\n[00:05:00] 李四 汇报核心进展",
        )
        p.ctx.output_dir = tmp_path

        original_md = (
            "# 业务研讨会纪要\n\n## 会议总览\n\n全面回顾业务目标。\n\n## 核心进展\n\n各条线稳定推进。"
        )

        fake_sections = [
            SectionSummary(
                time_start="01:00",
                title="启动 Q3 项目",
                key_words=["启动", "Q3"],
                section_summary="张三宣布 Q3 项目正式启动。",
            ),
            SectionSummary(
                time_start="05:00",
                title="核心进展汇报",
                key_words=["进展", "指标"],
                section_summary="李四对各项核心业务指标展开详细汇报。",
            ),
        ]
        fake_summary_md = (
            "01:00  启动 Q3 项目  \n关键词：启动、Q3  \n张三宣布 Q3 项目正式启动。\n\n"
            "05:00  核心进展汇报  \n关键词：进展、指标  \n李四对各项核心业务指标展开详细汇报。"
        )
        fake_result = SectionSummaryResult(
            markdown=fake_summary_md,
            sections=fake_sections,
        )

        async def _fake_summary():
            return fake_result

        summary_task = asyncio.create_task(_fake_summary())

        captured_kwargs = {}

        async def _mock_agenerate_visual_minutes(
            minutes_markdown, meeting_transcript, output_path, **kwargs
        ):
            captured_kwargs["minutes_markdown"] = minutes_markdown
            captured_kwargs["meeting_transcript"] = meeting_transcript
            captured_kwargs["output_path"] = output_path
            # 写入真实测试产物验证
            Path(output_path).write_text("<html>fake visual minutes</html>", encoding="utf-8")

        with patch(
            "domains.shared.visual_minutes.pipeline.agenerate_visual_minutes",
            new=_mock_agenerate_visual_minutes,
        ):
            await _maybe_generate_visual_minutes(
                p, "req_test", original_md, summary_task=summary_task
            )

        # 1. 验证传入 visual_minutes 的 Markdown 包含了 ## 智能章节 及渲染后的内容
        fed_md = captured_kwargs["minutes_markdown"]
        assert "## 智能章节" in fed_md
        assert "01:00  启动 Q3 项目" in fed_md
        assert "05:00  核心进展汇报" in fed_md

        # 2. 验证原始 md_text 未被改动
        assert "## 智能章节" not in original_md
        assert original_md.startswith("# 业务研讨会纪要")

        # 3. 验证产物文件已生成
        assert (tmp_path / "visual.html").exists()

    asyncio.run(_test())


def test_maybe_generate_visual_minutes_fallback_on_summary_error(
    monkeypatch, tmp_path
):
    """当 section_summary 异常时，优雅降级，不阻断图文纪要正常生成。"""
    async def _test():
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")

        p = FakePrepared(line="minutes", transcript="无时间戳的文本")
        p.ctx.output_dir = tmp_path
        original_md = "## 议题一\n\n内容详情"

        async def _error_summary():
            raise ValueError("ASR timestamp parse failed")

        summary_task = asyncio.create_task(_error_summary())

        captured_kwargs = {}

        async def _mock_agenerate_visual_minutes(
            minutes_markdown, meeting_transcript, output_path, **kwargs
        ):
            captured_kwargs["minutes_markdown"] = minutes_markdown

        with patch(
            "domains.shared.visual_minutes.pipeline.agenerate_visual_minutes",
            new=_mock_agenerate_visual_minutes,
        ):
            await _maybe_generate_visual_minutes(
                p, "req_fallback", original_md, summary_task=summary_task
            )

        # 降级时应使用原始 Markdown，不含 ## 智能章节
        assert "## 智能章节" not in captured_kwargs["minutes_markdown"]
        assert captured_kwargs["minutes_markdown"] == original_md

    asyncio.run(_test())


def test_visual_html_contains_section_summary_and_toc(monkeypatch, tmp_path):
    """全流水线集成测试：端到端验证生成的 visual.html 中包含 ## 智能章节 正文与其 TOC 目录项。"""
    async def _test():
        monkeypatch.setenv("INTELLIGENT_MINUTES_ENABLED", "on")

        transcript = (
            "00:00 张三 同学们好，今天开启本季度架构复盘会。\n"
            "05:30 李四 针对低延迟架构，我们设计了三阶段优化。"
        )
        p = FakePrepared(line="minutes", transcript=transcript)
        p.ctx.output_dir = tmp_path

        md_text = (
            "# 架构升级研讨会纪要\n\n"
            "## 核心议题\n\n"
            "本季度团队重点攻坚高可用与低延迟架构。\n\n"
            "## 落地成效\n\n"
            "系统 P99 延迟降低 45%。\n"
        )

        fake_sections = [
            SectionSummary(
                time_start="00:00",
                title="开场与架构复盘",
                key_words=["季度复盘", "架构"],
                section_summary="张三主持并回顾本季度整体架构演进方向。",
            ),
            SectionSummary(
                time_start="05:30",
                title="低延迟三阶段优化",
                key_words=["低延迟", "阶段优化"],
                section_summary="李四详细拆解三阶段调优执行方案。",
            ),
        ]
        fake_result = SectionSummaryResult(
            markdown=(
                "00:00  开场与架构复盘  \n关键词：季度复盘、架构  \n张三主持并回顾本季度整体架构演进方向。\n\n"
                "05:30  低延迟三阶段优化  \n关键词：低延迟、阶段优化  \n李四详细拆解三阶段调优执行方案。"
            ),
            sections=fake_sections,
        )

        async def _fake_summary():
            return fake_result

        summary_task = asyncio.create_task(_fake_summary())

        # 调用真实 _maybe_generate_visual_minutes（不 mock agenerate_visual_minutes，利用默认/fallback LLM）
        await _maybe_generate_visual_minutes(
            p, "req_e2e_test", md_text, summary_task=summary_task
        )

        html_file = tmp_path / "visual.html"
        assert html_file.exists(), "visual.html 未成功生成！"
        html_content = html_file.read_text(encoding="utf-8")

        # 1. 验证 TOC 目录中包含“智能章节”
        assert '<span class="vm-toc-text">智能章节</span>' in html_content, "TOC 中缺少智能章节目录！"

        # 2. 验证 正文 包含 ## 智能章节 的标题与段落内容
        assert "智能章节</h2>" in html_content, "正文中缺少智能章节标题！"
        assert "开场与架构复盘" in html_content, "缺少第 1 个分段标题！"
        assert "低延迟三阶段优化" in html_content, "缺少第 2 个分段标题！"
        assert "张三主持并回顾本季度整体架构演进方向" in html_content, "缺少第 1 个分段速览正文！"

        # 3. 验证业务章节与总览也都在
        assert '<span class="vm-toc-text">总览</span>' in html_content
        assert '<span class="vm-toc-text">核心议题</span>' in html_content
        assert '<span class="vm-toc-text">落地成效</span>' in html_content

    asyncio.run(_test())
