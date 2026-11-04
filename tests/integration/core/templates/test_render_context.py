# 拆分自 test_column_projection.py，覆盖：test_render_context_personal_injection, test_render_view_directive, test_render_context_person_transcript…

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

pytestmark = pytest.mark.integration

def test_render_context_personal_injection() -> None:
    """装配那一轮也要拿到命中块/偏好块 + 渲染提示词的"真人聚焦"口径。

    回归背景（2026-09-21 用户实测）：草稿那轮有命中块/偏好块，但**逐栏填充（真正写正文
    的地方）**没有——它看不到"他是谁、他关心什么"，于是把个人视角摊回整场，读起来与
    客观没区别。这里锁住：命中块进所有非客观线、偏好块只进纪要线；渲染提示词写明聚焦口径。
    """
    from domains.meeting.orchestrator import _Nodes
    class _Host(_Nodes):
        """只借方法；用真实 _render_context，其余依赖最小化。"""

        def __init__(self) -> None:
            pass

        def _meeting_pack(self, state, line_name):
            return {"meeting_purpose": "进展"}

        def _compact_user(self, user):
            return dict(user)

        def _compact_perspective(self, profile):
            return dict(profile or {})

        def _length_budget_line(self, state, line_name):
            return ""

        def _mode_label(self, state):
            return "objective" if state.get("objective_perspective") else "personal"

    hits = "【本用户命中（程序判定，带依据）】申家坤：命中 1 处。\n- [强] action_hints[0].owner：细对口径"
    state = {
        "transcript": "申家坤：我下来找他们细对一下。",
        "meeting_understanding": {"meeting_purpose": "进展"},
        "user": {"name": "申家坤", "preferences": ["先写我负责的待办"]},
        "user_hits_block": hits,
        "perspective_profile": {"personal_summary": "与本场相关：口径细对。"},
        "objective_perspective": False,
        "line_extra": {},
        "lines": {"minutes": {"draft": {"headline": "进展"}, "review": {}}},
    }
    host = _Host()
    for line, want_hit, want_pref in (
        ("minutes", False, False),
        ("minutes_styles", True, True),
        ("actions", False, False),
        ("risks", True, False),
    ):
        text = host._render_context(state, line)
        expect(("本用户命中" in text) is want_hit, f"渲染上下文（{line}）：命中块 {'有' if want_hit else '不注入'}", text[-160:])
        expect(("本用户偏好" in text) is want_pref, f"渲染上下文（{line}）：偏好块 {'有' if want_pref else '不注入'}", text[-160:])
    objective = host._render_context({**state, "objective_perspective": True, "user": {"perspective": "objective"}}, "minutes")
    expect("本用户命中" not in objective and "本用户偏好" not in objective, "渲染上下文（客观）：命中块与偏好块都不注入", "")


def test_render_view_directive() -> None:
    """逐栏填充器仍支持本视角纪律；会议个人钩子已不再注入纪律。"""
    import asyncio

    from domains.meeting.orchestrator import _Nodes
    from core.templates.router import fill_placeholder_template
    from core.templates.router._placeholder import _column_fill_user

    template = "# 通用纪要\n\n# [全文摘要]\n[一段话概括]\n\n# [要点梳理]\n[分点列具体事实]\n"
    mark = "【本视角纪律】"
    directive = f"{mark}\n- 只写本人相关内容\n- 本人动作省主语"

    class _Stub:
        """只记 (system, user)，不调 LLM。"""

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def stream_text(self, system_prompt, user_prompt, **kwargs):
            self.calls.append((system_prompt, user_prompt))
            yield "本栏正文（占位）。"

        async def text(self, system_prompt, user_prompt, **kwargs):
            self.calls.append((system_prompt, user_prompt))
            return '{"fields": {"1": "x", "2": "y"}, "tables": []}'

    class _Host(_Nodes):
        def __init__(self) -> None:
            pass

    stub = _Stub()
    asyncio.run(
        fill_placeholder_template(
            stub, "来源", template, source_han=9000, directives=directive
        )
    )
    expect(bool(stub.calls) and all(mark in user for _, user in stub.calls), "逐栏填充：每一栏的用户消息都带本视角纪律", str([user.splitlines()[0] for _, user in stub.calls]))
    expect(all("真人模式聚焦" not in system for system, _ in stub.calls), "逐栏填充：system 里没有领域渲染提示词（这正是要向用户消息下发纪律的原因）", "")

    host = _Host()
    personal = {"user": {"name": "申家坤"}}
    expect(host._render_directives(personal, "minutes") == ""
          and host._render_directives(personal, "minutes_styles") == "", "钩子：个人纪要线不再注入本视角纪律", "")
    expect(host._render_directives({**personal, "objective_perspective": True}, "minutes") == ""
          and host._render_directives(personal, "actions") == ""
          and host._render_directives(
              {"user": {"persona_type": "role_template", "name": "开发人员"}}, "minutes"
          ) == "", "钩子：客观、非纪要线、职业模板 → 都不注入", "")

    user = _column_fill_user(
        "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
        others=["要点梳理"], directives=directive,
    )
    expect(user.index("【本栏说明】") < user.index(mark) < user.index("【内容来源】"), "纪律排在【本栏说明】之后、【内容来源】之前", "")
    expect(mark not in _column_fill_user(
              "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
              others=["要点梳理"], directives="",
          ), "纪律为空 → 不出现该段（客观路径一字不变）", "")


def test_render_context_person_transcript() -> None:
    """真人模式的渲染上下文：会议原文按人裁剪（别人发言折叠），客观路径原样整篇。

    为什么非裁不可（2026-09-21 实测）：纪律写进消息开头（691 字）也压不过眼前的整场原文，
    真人模式照样输出整场（提及他的段落只占 12%、正文 9082 字）。裁掉别人的发言后同一份输入
    降到 6266 字，全文摘要出现「与你直接相关的是…」，且 930 节点/单卡四路等全局结论仍在。
    """
    from domains.meeting.orchestrator import _Nodes

    transcript = (
        "项目会\n"
        "申家坤 00:00:01\n" + "我们先过接口这块的对齐情况，把上周遗留的两条也一起带上。" * 4 + "\n"
        "武思华 00:00:10\n" + "这个问题由我来跟，细节我明天说清楚。" * 6 + "\n"
        "申家坤 00:00:40\n" + "小坤这边的权限单我提了，回流数据表也要一起加上。" * 4 + "\n"
        "武思华 00:00:50\n" + "另外引擎那部分我一起讲一下大概情况。" * 6 + "\n"
        "李梦甜 00:01:10\n申家坤那边的双录还没确认。\n"
    )

    class _Host(_Nodes):
        def __init__(self) -> None:
            pass

        def _meeting_pack(self, state, line_name):
            return {}

        def _compact_user(self, user):
            return dict(user)

        def _compact_perspective(self, profile):
            return {}

        def _length_budget_line(self, state, line_name):
            return ""

    host = _Host()
    state = {
        "transcript": transcript,
        "user": {"name": "申家坤", "name_aliases": ["小坤"]},
        "meeting_understanding": {},
        "perspective_profile": {},
        "objective_perspective": False,
        "line_extra": {},
        "lines": {"minutes": {"draft": {}, "review": {}}},
    }
    person_text = host._person_transcript(state)
    expect("另外引擎那部分我一起讲一下大概情况" not in person_text
          and "这个问题由我来跟，细节我明天说清楚。" not in person_text, "真人：别人的段被折叠（原文里那些长段不见了）", "")
    expect("你 00:00:01" in person_text and "我们先过接口这块的对齐情况" in person_text, "真人：他自己的段留下且块首改称「你」", person_text[:120])
    expect("李梦甜 00:01:10" in person_text and "双录还没确认" in person_text, "真人：提到他的别人的段也留（引述保真名）", "")

    sliced = host._render_context(state, "minutes")
    expect("会议原文" not in sliced, "真人纪要渲染上下文：已脱水（不注入会议原文）", "")
    expect("已批准纪要草稿" in sliced and "用户画像" not in sliced, "真人纪要渲染上下文：仅草稿与审核结论", "")
    trace_ctx = host._render_context(state, "minutes_trace")
    expect("会议原文" in trace_ctx, "溯源线（trace）：仍保留会议原文供正则回溯证据", "")

    objective = host._render_context({**state, "objective_perspective": True}, "minutes")
    expect("会议原文" not in objective, "客观纪要渲染上下文：已脱水（不注入会议原文）", "")

    # 分组骨架块当前由编排层置空（user_action_groups_block=""），不再注入渲染上下文。
    # 状态通道守护（2026-09-22 真链路事故）：LangGraph 只传 MeetingState 里声明过的 key，
    # 未声明的写入被静默丢掉——骨架块写了，草稿/审核/渲染全程收不到（单元测试注入 dict 掩盖了）。
    from domains.meeting.models import MeetingState

    expect("user_action_groups_block" in MeetingState.__annotations__
          and "user_hits_block" in MeetingState.__annotations__
          and "user_radar_block" in MeetingState.__annotations__, "状态通道：视角节点写的块都在 MeetingState 里声明（否则被 LangGraph 丢掉）", "")
    expect("user_action_groups_block" in Path("domains/meeting/orchestrator.py").read_text(
              encoding="utf-8"
          ) and "user_radar_block" in Path("domains/meeting/orchestrator.py").read_text(
              encoding="utf-8"
          ), "状态通道：视角节点确实写入骨架 key 与雷达 key", "")

    # 素材裁剪（2026-09-21 追加）：理解包里"别人为主语"的条目在真人装配轮去掉——
    # 实测「行动项与分工」栏会把 key_points 直接变成条目（157 条里 49 条以别人为主语），
    # 纪律压不住素材；裁完同一份输入的分工栏 8/8 都是他的条目（原来 5/8）。
    pack = {
        "meeting_brief": "进展",
        "topics": [
            {
                "title": "长文本",
                "discussion": "武思华提出先测接口，徐玥要求本周出结论，讨论集中在人力上",  # 别人为主 → 裁
                "key_points": [
                    "长文本实测 8~9 万字不行，手头最大 40 多秒",   # 无人称全局事实 → 留
                    "申家坤回去改配置，明天给结论",                  # 点名他 → 留
                    "武思华明天找他们要数据，看能不能要到",          # 别人为主语 → 裁
                    "徐玥要求 930 前至少单卡四路",                   # 别人为主语 → 裁
                ],
            },
            {
                "title": "引擎并发",
                "discussion": "申家坤讲了长文本实测情况，其他人补充",  # 提到他 → 留
                "key_points": ["申家坤负责压测"],
            },
        ],
        "decisions": ["930 前至少单卡四路"],
        "risks": ["武思华找对方批权限一直不批"],
    }
    pack_state = {
        **state,
        "meeting_understanding": {
            "speakers": [{"name": "申家坤"}, {"name": "武思华"}, {"name": "徐玥"}]
        },
    }
    trimmed_pack = host._person_pack(pack, pack_state)
    expect(len(trimmed_pack["topics"][0]["key_points"]) == 2
          and "长文本实测 8~9 万字不行" in trimmed_pack["topics"][0]["key_points"][0]
          and "申家坤回去改配置" in trimmed_pack["topics"][0]["key_points"][1], "素材裁剪：别人为主语的条目去掉，他的与无人称全局事实都留", str(trimmed_pack["topics"][0]["key_points"]))
    expect(trimmed_pack["decisions"] == ["930 前至少单卡四路"]
          and trimmed_pack["risks"] == ["武思华找对方批权限一直不批"], "素材裁剪：decisions / risks 不动（全局结论与风险仍进上下文）", "")
    expect(trimmed_pack["topics"][0]["discussion"] == ""
          and trimmed_pack["topics"][1]["discussion"] == "申家坤讲了长文本实测情况，其他人补充", "素材裁剪：别人为主的「议题讨论经过」同样去掉（2026-09-22 追加）", f"{[tp.get('discussion') for tp in trimmed_pack['topics']]}")
    expect(len(host._person_pack(pack, {**pack_state, "objective_perspective": True})["topics"][0]["key_points"]) == 4
          and host._person_pack(
              pack, {**pack_state, "objective_perspective": True}
          )["topics"][0]["discussion"].startswith("武思华提出")
          and len(host._person_pack(
              pack, {**pack_state, "user": {"name": "开发人员", "persona_type": "role_template"}}
          )["topics"][0]["key_points"]) == 4, "素材裁剪：客观档与职业模板都不裁（原样返回，含讨论经过）", "")

    role = host._render_context(
        {**state, "user": {"name": "开发人员", "persona_type": "role_template"}}, "minutes"
    )
    expect("已按人裁剪" not in role, "职业模板：没有真人姓名可裁 → 走整篇", "")

    expect(host._person_transcript({**state, "user": {"name": "查无此人"}}) == "", "裁不动时退回空串（调用方用整篇）：无关姓名", "")


def test_render_context_trim_and_supervisor_soften_and_expand_skip() -> None:
    """验证：
    1. 审核 revise 软化：检查项全 pass 时快速放行 approve，有 fail 时保留 revise。
    2. 渲染上下文裁剪：纪要线原文 >8000 字时智能切片，原文 <=8000 字时保持完整。
    3. 渲染扩写短文跳过：原文 <5000 字时，避免无效强制 expand。
    """
    from core.schema.validation import soften_unsubstantial_revise
    from domains.meeting.orchestrator import _Nodes

    # 1. 审核快速放行验证
    all_pass_revise = {
        "decision": "revise",
        "feedback": ["建议文笔更简练，段落适当合并"],
        "facts_check": {"status": "pass", "findings": []},
        "perspective_check": {"status": "pass", "findings": []},
        "consistency_check": {"status": "pass", "findings": []},
    }
    softened, note = soften_unsubstantial_revise(dict(all_pass_revise))
    expect(softened["decision"] == "approve", "全 pass 的 revise → 软化为 approve", f"{softened}")
    expect(bool(softened.get("revise_downgraded")), "全 pass 的 revise → 标记 revise_downgraded", "")
    expect(softened["feedback"] == [], "全 pass 的 revise → feedback 清空保契约合法", "")
    expect(len(softened.get("advisory_feedback", [])) == 1, "全 pass 的 revise → 原 feedback 保存至 advisory_feedback", "")

    has_fail_revise = {
        "decision": "revise",
        "feedback": ["数字错误需修正"],
        "facts_check": {"status": "fail", "findings": ["金额 1000 万写成 100 万"]},
        "perspective_check": {"status": "pass", "findings": []},
    }
    kept, note2 = soften_unsubstantial_revise(dict(has_fail_revise))
    expect(kept["decision"] == "revise" and note2 is None, "有 fail 检查项的 revise → 保持 revise 不软化", f"{kept}")

    # 2. 渲染上下文长文本裁剪验证
    class _Host(_Nodes):
        def __init__(self) -> None:
            pass
        def _meeting_pack(self, state, line_name):
            return {"topics": ["技术改造架构方案与实施路径"]}
        def _compact_user(self, user):
            return dict(user or {})
        def _compact_perspective(self, profile):
            return {}
        def _length_budget_line(self, state, line_name):
            return ""

    host = _Host()
    long_raw = ("项目部关于系统架构升级与推进改造的正式研讨。\n"
                "张经理表示：本次改造核心聚焦数据库吞吐瓶颈与缓存高并发优化，预计十月底全面验收上线。\n"
                + "其他参与人员就日常事务性与行政配合内容进行零散沟通。\n" * 400)
    expect(len(long_raw) > 8000, "测试用长文本超过 8000 字", f"{len(long_raw)}")

    state_long = {
        "transcript": long_raw,
        "user": {"name": "张经理"},
        "meeting_understanding": {},
        "perspective_profile": {},
        "objective_perspective": True,
        "line_extra": {},
        "lines": {
            "minutes": {
                "draft": {"executive_summary": "本次改造核心聚焦数据库吞吐瓶颈与缓存高并发优化，预计十月底全面验收上线。"},
                "review": {},
            }
        },
    }
    ctx_long = host._render_context(state_long, "minutes")
    expect("会议原文" not in ctx_long, "长原文客观纪要渲染上下文：脱水后不含原文切片", "")
    expect("数据库吞吐瓶颈" in ctx_long, "长原文客观纪要渲染上下文：保留草稿核心事实点", "")
    expect(len(ctx_long) < len(long_raw) * 0.7, "长原文客观纪要渲染上下文：脱水后体积大幅缩减（远小于原长文本）", f"{len(ctx_long)} vs {len(long_raw)}")

    # 3. 渲染短文本不强制 expand
    from core.runtime.render import _doc_han
    expect(_doc_han({"transcript": "短会议原文" * 100}) < 5000, "短文本原文统计字数正确识别", "")
