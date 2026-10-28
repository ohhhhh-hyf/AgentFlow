"""Step 3：minutes prompt map + 议程专用输出契约 + 议程审核 prompt 清理 + 辅助材料规约。"""
from __future__ import annotations

import asyncio

from domains.meeting.models_generated import Minutes
from domains.meeting.tasks.minutes.contracts import (
    MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT,
    MINUTES_GENERATION_OUTPUT_CONTRACT,
)
from domains.meeting.tasks.minutes.prompt_map import (
    is_agenda_view,
    minutes_prompt_set,
    prompt_label,
    render_template_prompt,
)
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    NOTES_PROMPT_BLOCK,
    VISION_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_PERSONAL,
    VIEW_ROLE_TEMPLATE,
)

_CONTRACT_KEYS = (
    "headline",
    "executive_summary",
    "key_decisions",
    "personally_relevant_points",
    "risks_and_blockers",
    "unresolved_questions",
    "history_comparison",
)


def test_minutes_generation_steps_do_not_parse_view_from_context() -> None:
    """防回归：生产代码不得重新引入 context → view 的反解析。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "domains" / "meeting"
    forbidden = ("resolve_prompt_view", "resolve_render_prompt")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(name in text for name in forbidden):
            offenders.append(str(path))
    assert not offenders, offenders


def test_minutes_prompt_no_content_examples() -> None:
    """Prompt 只保留通用规则与格式占位符，不夹带具体栏目名/指标/措辞示例。"""
    # 1. 指标类型不锁定，按原文实际业务要素展开
    assert "吞吐/延迟/时限/金额" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "关键数据" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "不预设会议类型" in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 2. 普通模板渲染不列具体栏目名/标题示例
    assert "讲座概况" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "评审概况" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "会议概况" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "【要点梳理】" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "### 1. 业务板块/功能方向名称" not in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "模板中声明为单段概括/概览的栏目" in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "模板中声明为业务研讨/要点类的栏目" in MINUTES_RENDER_TEMPLATE_PROMPT
    assert "按模板声明的三级标题层级设立小节" in MINUTES_RENDER_TEMPLATE_PROMPT

    # 3. 议题模板渲染不列具体栏目名/措辞示例
    assert "【要点梳理】" not in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "推荐以" not in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "模板中的议题研讨类栏目" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert "按模板要求的列表格式" in MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT

    # 4. 不再出现具体会议类型软引导
    assert "企业交付/技术评审" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "研讨/辩论/访谈" not in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 5. 决议措辞不引用具体句式
    assert "格式如：事项名称 + 统一定调与指标" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "[事项名称] + [定调/指标]" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "如“【事项】统一定调/指标要求”" not in MINUTES_AGENDA_GENERATION_PROMPT
    assert "以业务事项为主干，直接陈述定调结论" in MINUTES_AGENDA_GENERATION_PROMPT
    assert "如“某某建议/某某指出”" not in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "如“【事项】定调结论”" not in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "口语化发言前缀" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "规范公文决议体" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT

    # 6. 发言动词不再给具体负向示例
    assert "某某提出/某某认为/某某指出" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "某某提出/某某指出" not in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert "避免机械堆砌发言动词" in MINUTES_OBJECTIVE_GENERATION_PROMPT

    # 7. 笔记/视觉材料不列具体示例
    assert "（如吐槽、疑问、随手标记）" not in NOTES_PROMPT_BLOCK
    assert "个人批注、主观评论与随手标记" in NOTES_PROMPT_BLOCK
    assert "（如PPT、屏幕截图、现场拍照、白板记录、数据报表等）" not in VISION_PROMPT_BLOCK
    assert "会议视觉材料的识别文本" in VISION_PROMPT_BLOCK


def test_prompt_sets_by_view() -> None:
    agenda = minutes_prompt_set(VIEW_AGENDA_OBJECTIVE)
    assert agenda.generation is MINUTES_AGENDA_GENERATION_PROMPT
    assert agenda.supervisor is MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert is_agenda_view(agenda.view)
    assert prompt_label(agenda.view) == "agenda"

    personal = minutes_prompt_set(VIEW_PERSONAL)
    assert personal.generation is MINUTES_PERSONAL_GENERATION_PROMPT
    assert personal.supervisor is MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert prompt_label(personal.view) == "personal"

    # role_template 沿用 objective prompts（与既有行为一致），但保留 view 标签
    role = minutes_prompt_set(VIEW_ROLE_TEMPLATE)
    assert role.view == VIEW_ROLE_TEMPLATE
    assert role.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert role.supervisor is MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert prompt_label(role.view) == "objective"

    # 未知 view 回退 objective，不抛 500
    fallback = minutes_prompt_set("unknown")
    assert fallback.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT


def test_render_template_prompt_only_agenda_differs() -> None:
    """渲染只分 agenda / 非 agenda；personal、role_template 共用普通 prompt。"""
    for view in ("", "objective", "personal", "role_template"):
        assert is_agenda_view(view) is False
        assert render_template_prompt(view) is MINUTES_RENDER_TEMPLATE_PROMPT

    assert is_agenda_view(VIEW_AGENDA_OBJECTIVE) is True
    assert (
        render_template_prompt(VIEW_AGENDA_OBJECTIVE)
        is MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    )


def test_render_prompts_keep_overview_anchor_and_column_heading_rule() -> None:
    """渲染首条必须锁住 [0] 概览锚点，并禁止用会议标题替换栏目标题。"""
    for prompt in (
        MINUTES_RENDER_TEMPLATE_PROMPT,
        MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    ):
        assert "（[0]，全场概览项）" in prompt
        assert (
            "栏目标题只写模板方括号内的文字" in prompt
            or "栏目标题必须与模板方括号内文字完全一致" in prompt
        )
        assert "`## [讨论概述]` → `## 讨论概述`" in prompt
        assert "不得用会议标题或草稿 headline 替换" in prompt


def test_agenda_contract_clean() -> None:
    contract = MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    assert "个人" not in contract
    assert "MeetingUnderstanding" not in contract
    for key in _CONTRACT_KEYS:
        assert f'"{key}"' in contract
    # 与共享契约保持同一组 key，便于下游 Minutes 模型校验
    for key in _CONTRACT_KEYS:
        assert f'"{key}"' in MINUTES_GENERATION_OUTPUT_CONTRACT


def test_agenda_agent_uses_agenda_contract() -> None:
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured["system"] = system
            captured["contract"] = contract
            return Minutes(headline="")

    agent = MinutesGenerationAgent(FakeClient())
    agenda_context = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n\n"
        "会议理解：\n{}\n"
    )
    asyncio.run(
        agent.run(
            agenda_context,
            view="agenda_objective",
            source_transcript="tagged transcript",
        )
    )
    assert captured["contract"] == MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    combined = captured["system"] + "\n" + captured["contract"]
    assert "个人模式下" not in combined
    assert "来自MeetingUnderstanding" not in combined
    assert "MeetingUnderstanding" not in combined

    captured.clear()
    normal_context = "视角模式：objective\n\n会议理解：\n{}\n"
    asyncio.run(agent.run(normal_context, view="objective"))
    assert captured["contract"] == MINUTES_GENERATION_OUTPUT_CONTRACT


def test_supervisor_prompts_share_scope_without_carry_claims() -> None:
    for prompt in (
        MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
        MINUTES_PERSONAL_SUPERVISOR_PROMPT,
        MINUTES_AGENDA_SUPERVISOR_PROMPT,
    ):
        assert "搬运项免审" not in prompt
        assert "上游事实搬运项" not in prompt
        assert "历史记忆隔离审查" not in prompt
        assert "本轮送审范围" in prompt
        assert "只审送审稿中实际出现的内容" in prompt
        assert "历史记忆审查" in prompt
        assert "key_decisions" not in prompt
        # 既有放行规则必须保留
        assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in prompt


# ── 议题辅助材料 prompt 规约 ──────────────────────────────────────────────────

def test_agenda_prompt_mentions_aux() -> None:
    """议程生成 prompt 必须枚举三个可选辅助字段。"""
    prompt = MINUTES_AGENDA_GENERATION_PROMPT
    assert "【用户核心关键点】" in prompt
    assert "【用户划线原话与笔记】" in prompt
    assert "【视觉信息参考(OCR)】" in prompt


def test_agenda_prompt_skeleton_precedence() -> None:
    """“唯一事实底座”必须收窄为议程骨架/归属，辅助材料只补事实。"""
    prompt = MINUTES_AGENDA_GENERATION_PROMPT
    assert "议程骨架与事实归属的唯一底座" in prompt
    assert "辅助材料仅补充事实、参数、原话与数据" in prompt
    assert "你以此为唯一事实底座" not in prompt


def test_agenda_prompt_truth_line_allows_aux() -> None:
    """真实性底线保留“决策以打标转写为准”，但允许辅助材料补充事实。"""
    prompt = MINUTES_AGENDA_GENERATION_PROMPT
    assert "所有人名、决策与议题归属以打标转写为准" in prompt
    assert "辅助材料仅补充事实、参数与原话" in prompt
    assert "所有数据、人名、决策严格以打标转写文本为准" not in prompt


def test_agenda_aux_block_boundary_only() -> None:
    """议程边界 block 只写边界，不复制共享字段规则。"""
    block = AGENDA_AUX_PROMPT_BLOCK
    assert "【议程骨架优先】" in block
    assert "不得新增、删除、改名或重排议题" in block
    assert "不得改变议题归属" in block
    assert "不得单独形成新的拍板决议" in block
    assert "无法归属到任何审定议题的辅助事实" in block
    assert "## 用户关键点参考" not in block
    assert "## 用户笔记参考" not in block
    assert "## 视觉信息参考 (OCR)" not in block


def test_normal_prompt_unchanged() -> None:
    """普通 objective / personal prompt 不被议程措辞污染。"""
    for prompt in (
        MINUTES_OBJECTIVE_GENERATION_PROMPT,
        MINUTES_PERSONAL_GENERATION_PROMPT,
    ):
        assert "议程骨架与事实归属的唯一底座" not in prompt
        assert "【议程骨架优先】" not in prompt
        assert "辅助材料使用规约" not in prompt
    assert "## 三、全员客观纪要专有规则" in MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert (
        "## 三、个人视角纪要专有规则（个人工作看板）"
        in MINUTES_PERSONAL_GENERATION_PROMPT
    )


# ── 边界：议程草稿未按议题输出 ────────────────────────────────────────────────

def test_agenda_draft_without_headings_still_completes() -> None:
    """议题草稿没有 ### 标题时，agent 仍正常返回（best-effort，不做程序化拦截）。"""
    captured: dict = {}

    class FakeClient:
        async def structured(self, system, user, model, contract, **kwargs):
            captured["system"] = system
            captured["contract"] = contract
            return Minutes(
                headline="无议题标题的纪要",
                executive_summary=["一段没有 ### 标题的正文。"],
            )

    agent = MinutesGenerationAgent(FakeClient())
    agenda_context = (
        "议题模式：agenda_enhanced\n"
        "视角模式：objective\n\n"
        "会议理解：\n{}\n"
    )
    result = asyncio.run(
        agent.run(
            agenda_context,
            view="agenda_objective",
            source_transcript="tagged transcript",
        )
    )

    # 没有 ### 标题也不抛错、不拦截，草稿照常返回
    assert result.headline == "无议题标题的纪要"
    assert result.executive_summary == ["一段没有 ### 标题的正文。"]
    # 确实走的是议程契约
    assert captured["contract"] == MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
