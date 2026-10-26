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
    resolve_prompt_view,
)
from domains.meeting.tasks.minutes.prompts import (
    AGENDA_AUX_PROMPT_BLOCK,
    MINUTES_AGENDA_GENERATION_PROMPT,
    MINUTES_AGENDA_RENDER_PROMPT,
    MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT,
    MINUTES_AGENDA_SUPERVISOR_PROMPT,
    MINUTES_OBJECTIVE_GENERATION_PROMPT,
    MINUTES_OBJECTIVE_RENDER_PROMPT,
    MINUTES_OBJECTIVE_SUPERVISOR_PROMPT,
    MINUTES_PERSONAL_GENERATION_PROMPT,
    MINUTES_PERSONAL_RENDER_PROMPT,
    MINUTES_PERSONAL_SUPERVISOR_PROMPT,
    MINUTES_RENDER_TEMPLATE_PROMPT,
)
from domains.meeting.tasks.minutes.steps.minutes_agent import MinutesGenerationAgent
from domains.meeting.views import (
    VIEW_AGENDA_OBJECTIVE,
    VIEW_OBJECTIVE,
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


def test_resolve_prompt_view() -> None:
    assert (
        resolve_prompt_view("议题模式：agenda_enhanced\n视角模式：objective")
        == VIEW_AGENDA_OBJECTIVE
    )
    assert resolve_prompt_view("视角模式：personal") == VIEW_PERSONAL
    assert resolve_prompt_view("视角模式：role_template") == VIEW_ROLE_TEMPLATE
    assert resolve_prompt_view("视角模式：objective") == VIEW_OBJECTIVE
    assert resolve_prompt_view("") == VIEW_OBJECTIVE


def test_prompt_sets_by_view() -> None:
    agenda = minutes_prompt_set(VIEW_AGENDA_OBJECTIVE)
    assert agenda.generation is MINUTES_AGENDA_GENERATION_PROMPT
    assert agenda.supervisor is MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert agenda.render is MINUTES_AGENDA_RENDER_PROMPT
    assert agenda.render_template is MINUTES_AGENDA_RENDER_TEMPLATE_PROMPT
    assert is_agenda_view(agenda.view)
    assert prompt_label(agenda.view) == "agenda"

    personal = minutes_prompt_set(VIEW_PERSONAL)
    assert personal.generation is MINUTES_PERSONAL_GENERATION_PROMPT
    assert personal.supervisor is MINUTES_PERSONAL_SUPERVISOR_PROMPT
    assert personal.render is MINUTES_PERSONAL_RENDER_PROMPT
    assert personal.render_template is MINUTES_RENDER_TEMPLATE_PROMPT
    assert prompt_label(personal.view) == "personal"

    # role_template 沿用 objective prompts（与既有行为一致），但保留 view 标签
    role = minutes_prompt_set(VIEW_ROLE_TEMPLATE)
    assert role.view == VIEW_ROLE_TEMPLATE
    assert role.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT
    assert role.supervisor is MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert role.render is MINUTES_OBJECTIVE_RENDER_PROMPT
    assert role.render_template is MINUTES_RENDER_TEMPLATE_PROMPT
    assert prompt_label(role.view) == "objective"

    # 未知 view 回退 objective，不抛 500
    fallback = minutes_prompt_set("unknown")
    assert fallback.generation is MINUTES_OBJECTIVE_GENERATION_PROMPT


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
    asyncio.run(agent.run(agenda_context, source_transcript="tagged transcript"))
    assert captured["contract"] == MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
    combined = captured["system"] + "\n" + captured["contract"]
    assert "个人模式下" not in combined
    assert "来自MeetingUnderstanding" not in combined
    assert "MeetingUnderstanding" not in combined

    captured.clear()
    normal_context = "视角模式：objective\n\n会议理解：\n{}\n"
    asyncio.run(agent.run(normal_context))
    assert captured["contract"] == MINUTES_GENERATION_OUTPUT_CONTRACT


def test_agenda_supervisor_prompt_drops_upstream_carry_claims() -> None:
    prompt = MINUTES_AGENDA_SUPERVISOR_PROMPT
    assert "搬运项免审" not in prompt
    assert "上游事实搬运项" not in prompt
    assert "历史记忆隔离审查" not in prompt
    assert "本轮送审范围" in prompt
    assert "历史记忆审查" in prompt
    # 既有放行规则必须保留
    assert "属于符合公文规范的表述优化，予以充分认可并放行通过" in prompt

    # 普通 objective/personal 审核 prompt 不受影响
    assert "搬运项免审" in MINUTES_OBJECTIVE_SUPERVISOR_PROMPT
    assert "搬运项免审" in MINUTES_PERSONAL_SUPERVISOR_PROMPT


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
        agent.run(agenda_context, source_transcript="tagged transcript")
    )

    # 没有 ### 标题也不抛错、不拦截，草稿照常返回
    assert result.headline == "无议题标题的纪要"
    assert result.executive_summary == ["一段没有 ### 标题的正文。"]
    # 确实走的是议程契约
    assert captured["contract"] == MINUTES_AGENDA_GENERATION_OUTPUT_CONTRACT
