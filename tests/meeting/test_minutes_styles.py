"""tests/test_minutes_styles_refactor.py

全面验证 minutes_styles 重构后的：
1. 模板资产规范与 250-300 字首栏预算
2. style_template_path 路径解析严格限定在 5 大黄金模式
3. app/tasks.py 中的自动模板路由与 STYLE_CHOICES 严格门禁（只允许 5 类，其余秒判 400）
4. MultiStyles 契约与生成的模型浅校验/深校验（严格限制 5 类 mode）
5. MultiStylesSupervisorReview 检查项与语义
6. MultiStylesAgent 模式解析
7. MultiStylesRender 渲染与 HTML 导出
"""
from __future__ import annotations

import re
from pathlib import Path
import pytest

from app.config import (
    PROJECT_ROOT,
    RESOURCES_STYLES_DIR,
    STYLE_NAMES,
    style_template_path,
)
from app.schemas import Extra, TaskRequest
from app.tasks import ApiError, STYLE_CHOICES, _template_file, _validate
from core.schema.validation import OutputValidationError
from domains.meeting.hooks import HOOKS
from domains.meeting.models_generated import (
    MultiStyles,
    MultiStylesSupervisorReview,
)
from domains.meeting.tasks.minutes_styles.contracts import (
    MULTI_STYLES_GENERATION_OUTPUT_CONTRACT,
    MULTI_STYLES_SUPERVISOR_OUTPUT_CONTRACT,
    enforce_minutes_styles_sections,
)
from domains.meeting.tasks.minutes_styles.prompts import (
    MULTI_STYLES_GENERATION_SYSTEM_PROMPT,
    MULTI_STYLES_SUPERVISOR_DOMAIN_PROMPT,
    MULTI_STYLES_RENDER_PROMPT,
    MODE_BRIEF_RULES,
    MODE_TOPIC_RULES,
    MODE_REVIEW_RULES,
    MODE_RETRO_RULES,
    MODE_ALIGNMENT_RULES,
)
from domains.meeting.tasks.minutes_styles.steps.minutes_styles_agent import (
    _extract_mode,
    _MODE_RULES,
)
from domains.meeting.tasks.minutes_styles.steps.minutes_styles_render import (
    _empty_render_text,
)


def test_styles_templates_exist_and_meet_spec() -> None:
    """验证 resources/styles/ 下 5 份模板均存在且符合规范要求。"""
    assert RESOURCES_STYLES_DIR.is_dir(), f"目录不存在：{RESOURCES_STYLES_DIR}"
    expected_styles = ["brief", "topic", "review", "retro", "alignment"]

    for name in expected_styles:
        tpl_path = RESOURCES_STYLES_DIR / f"{name}.md"
        assert tpl_path.is_file(), f"模板文件缺失：{tpl_path}"
        content = tpl_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, f"模板内容过于简略：{name}"

        # 验证首栏包含 250–300 字预算说明
        assert "250–300" in content or "250-300" in content, (
            f"模板 {name} 首栏未明确标注 250–300 字预算"
        )

        # 验证栏目标题不得出现官僚化「与」字配对
        headers = re.findall(r"^##\s+\[(.*?)\]", content, re.MULTILINE)
        assert len(headers) >= 3, f"模板 {name} 栏目数不足 3 个：{headers}"
        for h in headers:
            assert "与" not in h, f"模板 {name} 栏目标题含「与」：{h}"

        # 验证模板没有被当成固定文本的方括号字面量（避免触发模板门禁 fixed text 丢失）
        from core.templates.router._gate import scan_fixed_bracket_literals
        hits = scan_fixed_bracket_literals(content)
        assert not hits, f"模板 {name} 存在嵌套或未闭合中括号字面量：{hits}"


def test_style_template_path_strictly_5_modes() -> None:
    """验证 style_template_path 仅支持 5 大模式，历史淘汰模式与非法名称均返回 None。"""
    # 标准 5 大标识
    for mode in ["brief", "topic", "review", "retro", "alignment"]:
        p = style_template_path(mode)
        assert p is not None and p.is_file()
        assert p.name == f"{mode}.md"

    # 淘汰的历史与其它名称均必须返回 None（不再做静默别名兜底）
    invalid_styles = ["time", "logic", "causal", "party", "urgency", "executive", "tradeoff", "other"]
    for bad in invalid_styles:
        assert style_template_path(bad) is None, f"{bad} 应该返回 None"

    # 缺省与空串 -> 默认 topic.md
    assert style_template_path("").name == "topic.md"
    assert style_template_path(None).name == "topic.md"


def test_style_choices_strictly_5_modes() -> None:
    """验证 STYLE_CHOICES 集合严格只包含 5 大黄金模式。"""
    expected = {"brief", "topic", "review", "retro", "alignment"}
    assert STYLE_CHOICES == expected
    assert STYLE_NAMES == frozenset(expected)


def test_api_validation_rejects_non_5_styles() -> None:
    """验证 app/tasks.py 中的 _validate 对非 5 大模式直接抛出 400 ApiError。"""
    req_valid = TaskRequest(
        texts={"transcript": "这是一场关于系统架构的讨论。"},
        extra=Extra(style="brief"),
    )
    # 合法 5 类通过
    for s in ["brief", "topic", "review", "retro", "alignment"]:
        req_valid.extra.style = s
        assert _validate(req_valid, "minutes_styles", "user_1") == "minutes_styles"

    # 历史淘汰模式与随意输入的模式全部被 400 拦截
    for bad in ["time", "logic", "causal", "party", "urgency", "executive", "tradeoff", "invalid_mode"]:
        req_bad = TaskRequest(
            texts={"transcript": "会议讨论内容"},
            extra=Extra(style=bad),
        )
        with pytest.raises(ApiError) as exc_info:
            _validate(req_bad, "minutes_styles", "user_1")
        assert exc_info.value.status == 400
        assert "extra.style 非法" in exc_info.value.message
        assert "brief" in exc_info.value.message


def test_app_tasks_template_file_routing() -> None:
    """验证 app/tasks.py 中 _template_file 对 minutes_styles 的自动模板绑定。"""
    brief_tpl = _template_file("meeting", "minutes_styles", "", style_value="brief")
    assert brief_tpl is not None and brief_tpl.name == "brief.md"

    topic_tpl = _template_file("meeting", "minutes_styles", "", style_value="topic")
    assert topic_tpl is not None and topic_tpl.name == "topic.md"

    review_tpl = _template_file("meeting", "minutes_styles", "", style_value="review")
    assert review_tpl is not None and review_tpl.name == "review.md"

    retro_tpl = _template_file("meeting", "minutes_styles", "", style_value="retro")
    assert retro_tpl is not None and retro_tpl.name == "retro.md"

    alignment_tpl = _template_file("meeting", "minutes_styles", "", style_value="alignment")
    assert alignment_tpl is not None and alignment_tpl.name == "alignment.md"

    # 空模式回退默认 topic
    default_tpl = _template_file("meeting", "minutes_styles", "", style_value="")
    assert default_tpl is not None and default_tpl.name == "topic.md"

    # 淘汰模式不命中模板
    bad_tpl = _template_file("meeting", "minutes_styles", "", style_value="time")
    assert bad_tpl is None


def test_multi_styles_models_strictly_5_modes() -> None:
    """验证 MultiStyles 生成契约及 MultiStylesSupervisorReview 审核模型严格限制 5 类。"""
    valid_data = {
        "mode": "brief",
        "title": "系统架构选型会",
        "summary": "本次会议围绕分布式网关选型拍板定调，确定了采用自研方案。",
        "sections": [
            {"title": "核心结论", "content": "全场拍板自研方案，交付节点定于下周三。"},
            {"title": "关键决策", "content": "- **网关自研** 确定实施自研轻量网关 (指标: 200QPS)"},
            {"title": "重大风险", "content": "*(经评估，本场会议各项推进正常，暂无重大阻塞风险)*"},
        ],
    }
    model = MultiStyles.validate(valid_data)
    assert model.mode == "brief"
    assert len(model.sections) == 3

    # 验证传入历史模式已被模型校验拒绝
    for bad_mode in ["time", "logic", "causal", "party", "urgency", "executive"]:
        invalid_data = {**valid_data, "mode": bad_mode}
        with pytest.raises(OutputValidationError):
            MultiStyles.validate(invalid_data)

    # 验证审核模型 MultiStylesSupervisorReview 的新检查项
    review_data = {
        "decision": "approve",
        "topic_coverage_check": {"status": "pass", "findings": ["核心议题全覆盖"]},
        "mode_alignment_check": {"status": "pass", "findings": ["符合 brief 模式定位"]},
        "formatting_quality_check": {"status": "pass", "findings": ["三段结构清晰完整"]},
        "feedback": [],
    }
    review = MultiStylesSupervisorReview.validate(review_data)
    assert review.decision == "approve"
    assert "topic_coverage_check" in review.CHECK_KEYS
    assert "mode_alignment_check" in review.CHECK_KEYS
    assert "formatting_quality_check" in review.CHECK_KEYS


def test_agent_extract_mode_and_rule_selection() -> None:
    """验证 MultiStylesAgent 对上下文组织模式的提取。"""
    assert _extract_mode("组织模式：brief\n\n会议原文...") == "brief"
    assert _extract_mode("组织模式: topic\n\n会议原文...") == "topic"
    assert _extract_mode("组织模式: review\n\n会议原文...") == "review"
    assert _extract_mode("组织模式: retro\n\n会议原文...") == "retro"
    assert _extract_mode("组织模式: alignment\n\n会议原文...") == "alignment"
    assert _extract_mode("组织模式: unknown\n\n会议原文...") == "topic"
    assert _extract_mode("无模式标注上下文") == "topic"

    # 规则块严格只有 5 类
    assert set(_MODE_RULES.keys()) == {"brief", "topic", "review", "retro", "alignment"}


def test_render_prompt_and_empty_handling() -> None:
    """验证 MultiStylesRender 的 prompt 允许 Markdown 标题，并能正确处理空草稿。"""
    assert "不要 Markdown 标题" not in MULTI_STYLES_RENDER_PROMPT
    assert "二级标题" in MULTI_STYLES_RENDER_PROMPT or "##" in MULTI_STYLES_RENDER_PROMPT

    # 验证空草稿兜底渲染
    empty_draft = {"title": "临时测试会", "sections": []}
    res = _empty_render_text(empty_draft)
    assert "临时测试会" in res
    assert "暂无结构化段落" in res


def test_minutes_styles_html_generation() -> None:
    """验证 HOOKS.html_for 生成的 HTML 包含 Markdown 转换的语义节点。"""
    title = "高管速览测试会"
    markdown = (
        "# 高管速览测试会\n\n"
        "> 本次会议围绕分布式网关选型拍板定调。\n\n"
        "## 核心结论\n\n"
        "全场拍板自研方案，交付节点定于下周三，推进顺利。\n\n"
        "## 关键决策\n\n"
        "- **网关自研** 确定实施自研轻量网关 (指标: 200QPS)\n\n"
        "## 重大风险\n\n"
        "*(经评估，本场会议各项推进正常，暂无重大阻塞风险)*\n"
    )
    html = HOOKS.html_for("minutes_styles", title, markdown, {})
    assert html is not None
    assert "<!doctype html>" in html.lower()
    assert "高管速览测试会" in html
    assert "核心结论" in html


def test_is_brief_style_detection() -> None:
    """验证 core/runtime/render.py 中 _is_brief_style 对模式与模板的精准识别。"""
    from core.runtime.render import _is_brief_style

    brief_tpl = (RESOURCES_STYLES_DIR / "brief.md").read_text(encoding="utf-8")
    topic_tpl = (RESOURCES_STYLES_DIR / "topic.md").read_text(encoding="utf-8")
    review_tpl = (RESOURCES_STYLES_DIR / "review.md").read_text(encoding="utf-8")
    retro_tpl = (RESOURCES_STYLES_DIR / "retro.md").read_text(encoding="utf-8")
    alignment_tpl = (RESOURCES_STYLES_DIR / "alignment.md").read_text(encoding="utf-8")

    # 1. minutes_styles + brief 模式（通过 line_modes / modes / 模板文本）
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "brief"}}, "") is True
    assert _is_brief_style("minutes_styles", {"modes": {"minutes_styles": "brief"}}, "") is True
    assert _is_brief_style("minutes_styles", {}, brief_tpl) is True
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "brief"}}, brief_tpl) is True

    # 2. minutes_styles 下其他 4 大模式均不可识别为 brief
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "topic"}}, topic_tpl) is False
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "review"}}, review_tpl) is False
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "retro"}}, retro_tpl) is False
    assert _is_brief_style("minutes_styles", {"line_modes": {"minutes_styles": "alignment"}}, alignment_tpl) is False

    # 3. 其他任务线哪怕传入 brief 模式或包含高管速览字样，也严禁豁免
    assert _is_brief_style("minutes", {"line_modes": {"minutes": "brief"}}, brief_tpl) is False
    assert _is_brief_style("actions", {"line_modes": {"actions": "brief"}}, brief_tpl) is False
    assert _is_brief_style("risks", {}, brief_tpl) is False


def test_produce_line_brief_length_exemption() -> None:
    """验证 produce_line 对 minutes_styles 的 brief 模式豁免下限扩写与下限咨询告警。"""
    import asyncio
    from core.runtime.render import produce_line

    async def _run() -> None:
        brief_tpl = (RESOURCES_STYLES_DIR / "brief.md").read_text(encoding="utf-8")
        topic_tpl = (RESOURCES_STYLES_DIR / "topic.md").read_text(encoding="utf-8")

        short_rendered_output = (
            "# 测试会议\n\n"
            "## 核心结论\n\n"
            + "这是精炼的核心战略拍板结论与交付节点说明。" * 10 + "\n\n"
            "## 关键决策\n\n"
            + "- **关键自研决策** 拍板推行轻量架构自研。\n" * 5 + "\n"
            "## 重大风险\n\n"
            "*(经评估，本场会议各项推进正常，暂无重大阻塞风险)*\n"
        )

        class MockRender:
            def __init__(self, text: str) -> None:
                self.text = text
                self.call_count = 0

            async def run(self, context: str, template: str = "", **kwargs) -> str:
                self.call_count += 1
                return self.text

            async def stream(self, context: str, template: str = "", **kwargs):
                self.call_count += 1
                yield self.text

        class MockEngine:
            domain_name = "meeting"

            def __init__(self, render: MockRender) -> None:
                self.minutes_styles_render = render
                self._line_cn_names = {"minutes_styles": "多样式纪要"}

            def _line_title(self, state: dict, line_name: str) -> str:
                return "多样式纪要"

            def _pre_render_hook(self, state: dict, line_name: str) -> bool:
                return False

            def _post_render_hook(self, state: dict, line_name: str) -> None:
                pass

            def _line_policy(self, line_name: str):
                class _Policy:
                    llm_render = "always"

                    def uses_llm_render(self, has_template: bool) -> bool:
                        return True

                return _Policy()

            def _render_context(self, state: dict, line_name: str) -> str:
                return "模拟渲染上下文"

            def _render_directives(self, state: dict, line_name: str) -> str:
                return ""

        long_transcript = "会议讨论很长很长。" * 1000  # 约 9000 字，_doc_han >= 5000，触发下限 1680

        # 1. 测试 brief 模式：篇幅下限豁免，不触发 expand revision，也不打低于下限咨询告警
        render_brief = MockRender(short_rendered_output)
        engine_brief = MockEngine(render_brief)
        state_brief = {
            "transcript": long_transcript,
            "templates": {"minutes_styles": brief_tpl},
            "line_modes": {"minutes_styles": "brief"},
            "lines": {"minutes_styles": {}},
        }
        queue_brief = asyncio.Queue()
        await produce_line(engine_brief, "minutes_styles", state_brief, queue_brief)

        # 仅调用 1 次初始渲染，零次 expand 修订
        assert render_brief.call_count == 1, f"brief 模式触发了额外扩写调用：{render_brief.call_count}"
        advisories_brief = state_brief["lines"]["minutes_styles"].get("render_advisory_issues") or []
        assert not any("低于本篇参考下限" in str(x) for x in advisories_brief), (
            f"brief 模式不应打出低于下限咨询告警：{advisories_brief}"
        )

        # 2. 对照测试 topic 模式：偏短正文彻底解除重试拦截，直接放行（call_count == 1），但保留 advisory 记录
        render_topic = MockRender(short_rendered_output)
        engine_topic = MockEngine(render_topic)
        state_topic = {
            "transcript": long_transcript,
            "templates": {"minutes_styles": topic_tpl},
            "line_modes": {"minutes_styles": "topic"},
            "lines": {"minutes_styles": {}},
        }
        queue_topic = asyncio.Queue()
        await produce_line(engine_topic, "minutes_styles", state_topic, queue_topic)

        # 偏短正文直接放行，零次额外扩写调用（call_count == 1）
        assert render_topic.call_count == 1, f"偏短正文应直接放行，但触发了额外扩写调用：{render_topic.call_count}"
        advisories_topic = state_topic["lines"]["minutes_styles"].get("render_advisory_issues") or []
        assert any("低于本篇参考下限" in str(x) for x in advisories_topic), (
            f"topic 模式应记录低于下限 advisory 供监控观察：{advisories_topic}"
        )

    asyncio.run(_run())


if __name__ == "__main__":
    import sys
    import pytest

    sys.exit(pytest.main([__file__]))

