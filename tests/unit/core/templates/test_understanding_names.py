# 拆分自 test_prompt_contracts.py，覆盖：test_qa_name_priority, test_understanding_speakers_field, test_understanding_user_channel…

"""tests/unit/core/templates/test_column_projection.py -- 逐栏并发填充、直出快线与模型执行单元测试。"""

from __future__ import annotations
import logging
import re
import sys
from pathlib import Path
import pytest
from core.templates.router._base import iter_placeholders, split_template_meta
from core.templates.router._detect import parse_placeholder_template
from core.templates.router._gate import scan_fixed_bracket_literals, validate_rendered_output
from core.templates.router._placeholder import plan_placeholder_fill
from tests.support.expectations import expect
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
)

def test_qa_name_priority() -> None:
    """新闻发布会/媒体问答：能确定身份就写姓名或媒体名，不能确定才回退「问/答」。

    回归背景（2026-09-18 实测）：两栏原口径是"能对应到人就用称呼（姓名优先，其次角色）"，
    示例又写成纯角色 → 提问方清一色落到角色上。当前模板已改为「提问方/答复方」结构，
    但保留核心口径：具体发言人姓名或官方身份优先，无法确定才写「问」「答」。
    """
    d = _active_dir()
    brief = (d / "media_briefing.md").read_text(encoding="utf-8")
    qa = (d / "media_qa_session.md").read_text(encoding="utf-8")

    # 新闻发布 [Q&A环节]
    assert "一问一答成组呈现" in brief
    assert "提问行「**提问方**：提问核心焦点」" in brief
    assert "回答行「**答复方**：明确结论与官方政策口径」" in brief
    assert "提问方写明媒体机构或记者身份（未提及写「**问**」）" in brief
    assert "答复方写明具体发言人或官方身份（未提及写「**答**」）" in brief

    # 媒体问答
    assert "一问一答成组呈现" in qa
    assert "提问行「**提问方**：提问核心焦点」" in qa
    assert "回答行「**答复方**：明确结论与政策事实依据」" in qa
    assert "提问方写明媒体机构与记者身份（未提及写「**问**」）" in qa
    assert "答复方写明具体发言人姓名或官方身份（确实无姓名写「**答**」）" in qa

    # 全局正文规则：称呼优先级与不得造名
    from core.templates.body_rules import BODY_FORMAT_RULES

    assert "问答/对话的一轮为一组" in BODY_FORMAT_RULES
    assert "姓名 > 原文角色 > 原始编号" in BODY_FORMAT_RULES
    assert "不推断姓名" in BODY_FORMAT_RULES

    understanding = Path("domains/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    assert "优先使用真实姓名" in understanding
    assert "不推断、不编造" in understanding


def test_understanding_speakers_field() -> None:
    """理解层 speakers：姓名↔角色的结构化落点（Q&A/表态/概况的人名绑定不再靠每栏重推）。

    回归背景（2026-09-18 实测）：发布会 Q&A 的回应方写不出姓名，退化成 `**答**：`（甚至空白），
    提问方也出现「主持人（慕尼黑安全会议）」这种"机构凑身份位"的写法。根因不是规则，而是
    **姓名与角色的绑定没有落点**——理解层只有 topics[].participants（语义是"谁参与该议题"），
    渲染时每栏都得从几万字原文里重新推一次"这段是谁在说"，原文标签是角色时就直接放弃。
    """
    from dataclasses import fields as dc_fields

    from domains.meeting.meeting_core.contracts import (
        MeetingUnderstandingGenerationContract,
    )
    from domains.meeting.meeting_core.prompts import build_understanding_prompt
    from domains.meeting.meeting_core.understanding_profiles import TASK_PROFILES
    from domains.meeting.models_generated import MeetingUnderstanding
    from domains.meeting.orchestrator import (
        _EMPTY_MEETING_UNDERSTANDING,
        UNDERSTANDING_SKIP_FIELDS,
        _Nodes,
    )

    spec = MeetingUnderstandingGenerationContract.to_json_template()
    expect("speakers" in spec and all(k in spec for k in ("name", "role", "org")), "契约含 speakers 字段（name/role/org）", spec[:60])
    expect("speakers" in {f.name for f in dc_fields(MeetingUnderstanding)}, "生成模型有 speakers 且为字段列表", "")
    expect(_EMPTY_MEETING_UNDERSTANDING.get("speakers") == [], "空结构常量带 speakers（降级路径不炸）", "")

    prompt = build_understanding_prompt(TASK_PROFILES["minutes"], task="minutes")
    expect("优先使用真实姓名" in prompt and "只有编号时如实保留原始编号" in prompt
          and "不推断、不编造" in prompt, "理解 prompt：称呼按姓名、角色、原始编号回退，不猜姓名", "")
    expect("speakers：" in prompt, "理解 prompt：姓名从 speakers 单列字段来，不从 participants 语义挤", "")

    expect(all("speakers" not in skip for skip in UNDERSTANDING_SKIP_FIELDS.values()), "speakers 不在任何线的裁剪集合里（人名所有线都要）", "")
    for line in ("minutes", "minutes_trace"):
        keep = _Nodes._understanding_needle_keep.get(line)  # 类属性，不用实例
        expect(bool(keep) and "speakers" in keep, f"{line}：审核摘录白名单含 speakers", f"{sorted(keep or [])}")

    # pack 侧：所有线都能拿到对照表（实测渲染退化的直接原因就是它不在包里）
    state = {
        "meeting_understanding": {
            "meeting_brief": "略", "meeting_purpose": "略",
            "speakers": [{"name": "王毅", "role": "发言人", "org": "外交部"}],
            "topics": [], "decisions": [], "risks": [], "open_questions": [],
        }
    }
    for line in ("minutes", "minutes_trace", "actions", "risks", "mindmap"):
        pack = _Nodes._meeting_pack(object(), state, line)
        names = [s.get("name") for s in pack.get("speakers") or []]
        expect(names == ["王毅"], f"{line} 的 pack 带 speakers（{names}）", f"{pack.get('speakers')}")

    draft_prompt = Path("domains/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    expect("speakers 提供真实姓名" in draft_prompt
          and "本人动作动宾短语开头、省略主语；他人动作保留真实姓名" in draft_prompt,
          "草稿 prompt：人名绑定 speakers，他人动作写真名", "")


def test_understanding_user_channel() -> None:
    """理解层「本用户称呼表」：别称归全称、编号发言人不绑、客观/职业模板不注入。

    回归背景（P0-A 2026-09-21）：下游（视角裁剪、待办 owner、跨场记忆、审核）只认理解层
    写下的那个名字字符串——实测同一个人在三场里被写成「发言者1 / 小赵 / 赵工」，状态里
    他的三条待办漂在三个"名字"下，个人模式分工栏因对不上姓名而选空、程序又回退全量。
    视角建模那轮连原文都看不到，治不了人名；只有理解层能统一（零新增调用，约百字输入）。
    """
    import asyncio

    from domains.meeting.meeting_core.meeting_understanding_agent import (
        MeetingUnderstandingAgent,
    )
    from domains.meeting.meeting_core.prompts import build_understanding_prompt
    from domains.meeting.meeting_core.understanding_profiles import TASK_PROFILES
    from domains.shared.perspective import build_user_channel

    prompt = build_understanding_prompt(TASK_PROFILES["minutes"], task="minutes")
    expect("【本用户称呼】" in prompt and "统一归一到全称" in prompt, "理解 prompt：称呼表把别称归全称", "")
    expect("不推断、不编造" in prompt and "真实姓名" in prompt, "理解 prompt：仍是「不猜姓名」的口径", "")

    block = build_user_channel(
        {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    )
    expect("赵衡（全称）" in block and "小赵、赵工" in block, "称呼表含全称与别称", block)
    expect("统一写成「赵衡」" in block and "发言者1" in block, "称呼表写明统一写法与不猜编号", block)
    expect(build_user_channel({"perspective": "objective", "name": "赵衡"}) == "", "客观视角不注入", "")
    expect(build_user_channel({"name": "开发人员", "persona_type": "role_template"}) == "", "职业模板不注入（姓名是职业通称，不能当人名）", "")
    expect(build_user_channel({"name": "  "}) == "", "没有姓名不注入", "")

    class _Stub:
        """只记录用户消息，不真的调模型。"""

        def __init__(self) -> None:
            self.user = ""

        async def structured(self, system, user, model_cls, contract, **kw):
            self.user = user
            return {"_stub": True}

    stub = _Stub()
    agent = MeetingUnderstandingAgent(stub)
    asyncio.run(
        agent.run(
            "发言者1：这周我把接口联调完。小赵：行，我下午提单。",
            focus_line="minutes",
            skip_fields={"risks"},
            user_channel=block,
        )
    )
    expect("【本次输出裁剪】" not in stub.user
          and stub.user.index("本用户称呼") < stub.user.index("会议原文："), "称呼表拼在会议原文之前，且无裁剪指令", stub.user[:120])
    asyncio.run(agent.run("原文", user_channel=""))
    expect("本用户称呼" not in stub.user and stub.user.startswith("会议原文："), "无称呼表时不注入空块（用户消息仍以会议原文开头）", stub.user[:60])
