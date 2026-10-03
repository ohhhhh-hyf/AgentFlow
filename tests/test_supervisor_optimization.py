"""审核短路与理解瘦身（零 LLM）：快速门禁 / 规则守卫 / 送审瘦身 / 契约口径。

覆盖 SUPERVISOR_AND_UNDERSTANDING_OPTIMIZATION_PLAN 的落地点：
- 步骤三：``_make_supervisor_node`` 短会（<2000 字符）与极简输入（议题≤2 且发言人≤2）
  快速放行；降级草稿不短路；``review_bypassed`` 与"审核失败"语义分离；
- 步骤五：``quick_facts_guardrail`` 人名在册 / 数字忠实；2000~5000 区间全过放行、
  命中红线照常送审、``SUPERVISOR_GUARDRAIL`` 可关；
- 步骤四：送审稿剔除搬运三字段（程序强对齐），审核 prompt 收缩到提炼字段；
- 步骤一/二：理解契约 30~60 字骨架口径 + 纪要生成"骨架为纲回原文"引导。

用法::

    python -m tests.test_supervisor_optimization
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

from core.execution.guardrails import (
    guardrail_fast_path_enabled,
    quick_facts_guardrail,
)
from core.runtime.supervisor_slice import compact_draft_for_review

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


# ── 桩：supervisor / 系统半实例化（与 test_engine_smoke 同范式，零 LLM）──

class _StubSupervisor:
    """桩审核：记录调用次数与送审上下文；可配置返回决定或直接抛错。"""

    def __init__(self, decision: str = "approve", raise_exc: bool = False) -> None:
        self.calls = 0
        self.last_context = ""
        self.decision = decision
        self.raise_exc = raise_exc

    async def review(self, context: str) -> dict:
        self.calls += 1
        self.last_context = context
        if self.raise_exc:
            raise RuntimeError("stub supervisor boom")
        return {
            "decision": self.decision,
            "feedback": [],
            "facts_check": {"status": "pass", "findings": []},
            "perspective_check": {"status": "pass", "findings": []},
            "consistency_check": {"status": "pass", "findings": []},
        }


def _make_system(stub: _StubSupervisor):
    from domains.meeting.orchestrator import MeetingAgentSystem

    system = object.__new__(MeetingAgentSystem)  # 不跑 __init__（会建 LLM client）
    system._task_lines = {
        "minutes": {
            "agent_attr": "minutes_agent",
            "supervisor_attr": "minutes_supervisor",
            "empty_draft": {},
            "reject_review": {
                "facts_check": {"status": "fail", "findings": ["x"]},
                "perspective_check": {"status": "fail", "findings": ["x"]},
                "consistency_check": {"status": "fail", "findings": ["x"]},
            },
        }
    }
    system._line_cn_names = {"minutes": "纪要"}
    system.minutes_supervisor = stub
    return system


def _state(
    transcript: str,
    *,
    draft: dict | None = None,
    topics: list | None = None,
    speakers: list | None = None,
    degraded: bool = False,
) -> dict:
    return {
        "transcript": transcript,
        "meeting_understanding": {
            "meeting_purpose": "冒烟",
            "topics": topics if topics is not None else [{"title": "T1"}],
            "speakers": speakers if speakers is not None else [{"name": "张工"}],
        },
        "user": {},
        "perspective_profile": {},
        "objective_perspective": True,
        "line_extra": {},
        "line_modes": {},
        "templates": {},
        "lines": {
            "minutes": {
                "draft": draft if draft is not None else {"headline": "x"},
                "degraded": degraded,
            }
        },
    }


def _pad(text: str, target: int) -> str:
    while len(text) < target:
        text += "另外接口联调排期下周对齐。"
    return text


_SHORT = "张工：本场过一下进度，下周出报表。"
_CLEAN_DRAFT = {
    "headline": "缓存保护设计评审",
    "executive_summary": ["张工确认缓存保护设计下周完成，时延指标压到200ms以内。"],
    "personally_relevant_points": [],
}


# ── 步骤五：guardrail 单元 ────────────────────────────────────

def test_guardrail_names() -> None:
    transcript = "张工：缓存保护设计下周完成。李总：时延指标压到200ms以内。"
    okay = quick_facts_guardrail(
        {
            "executive_summary": [
                "**与我相关**：本周并行走查。",
                "**张工**：缓存保护设计下周完成。",
                "李总要求时延指标压到200ms以内。",
            ]
        },
        [{"name": "张工"}],
        transcript,
    )
    check("组名行标签与在册人名都不误报", okay == (True, []), str(okay))

    unknown = quick_facts_guardrail(
        {"executive_summary": ["**王强**：负责联调。", "赵敏提出下周一评审。"]},
        [{"name": "张工"}],
        transcript,
    )
    check("陌生组名行人名被拦",
          not unknown[0] and any("王强" in item for item in unknown[1]), str(unknown))
    check("陌生「姓名+动词」人名被拦",
          any("赵敏" in item for item in unknown[1]), str(unknown))

    alias = quick_facts_guardrail(
        {"personally_relevant_points": ["**赵衡**：完成来源字段补齐。"]},
        [{"name": "赵衡"}],
        "小赵：我来补齐来源字段。",
    )
    check("别名归一（全称在 speakers 里）不算陌生", alias[0], str(alias))

    stopword = quick_facts_guardrail(
        {"executive_summary": ["本场确认了基线，会议明确了下周排期。"]},
        [{"name": "张工"}],
        transcript,
    )
    check("结构词（本场/会议）不误报为陌生名", stopword[0], str(stopword))


def test_guardrail_numbers() -> None:
    transcript = "张工：QPS 从 5000 提升到 8000，接口时延 200ms，延期3天。"

    good = quick_facts_guardrail(
        {"executive_summary": ["QPS 从5000提升到8000，时延压到200ms以内，延期3天。"]},
        [],
        transcript,
    )
    check("原文可定位的数字放行", good == (True, []), str(good))

    inflated = quick_facts_guardrail(
        {"executive_summary": ["QPS 从5000提升到50000。"]}, [], transcript
    )
    check("数字放大（5000→50000）被拦",
          not inflated[0] and any("50000" in item for item in inflated[1]), str(inflated))

    unit = quick_facts_guardrail(
        {"executive_summary": ["相关事项延期3周。"]}, [], transcript
    )
    check("单位篡改（3天→3周）被拦",
          not unit[0] and any("3周" in item for item in unit[1]), str(unit))

    decoy = quick_facts_guardrail(
        {"executive_summary": ["并发量 1200。"]}, [], "张工：并发 1200 已确认。"
    )
    check("完整数字串比对（1200 不撞 12000 的子串）",
          decoy[0], str(decoy))
    real = quick_facts_guardrail(
        {"executive_summary": ["并发量 120。"]}, [], "张工：并发 1200 已确认。"
    )
    check("120 不等于 1200（不因子串放行）",
          not real[0] and any("120" in item and "1200" not in item for item in real[1]),
          str(real))


def test_guardrail_skip_keys_and_env() -> None:
    history_only = quick_facts_guardrail(
        {"history_comparison": ["延续事项（引擎｜自第1场）：李工负责缓存保护设计。"]},
        [],
        "本场没有历史相关原文。",
    )
    check("历史对照不参与原文落地校验", history_only == (True, []), str(history_only))

    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "off"}):
        check("SUPERVISOR_GUARDRAIL=off 关闭激进放行",
              guardrail_fast_path_enabled() is False, "")
    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "on"}):
        check("SUPERVISOR_GUARDRAIL=on 开启", guardrail_fast_path_enabled() is True, "")

    saved = os.environ.pop("SUPERVISOR_GUARDRAIL", None)
    try:
        check("未配置时默认开启（与 TEMPLATE_ROUTER 同口径）",
              guardrail_fast_path_enabled() is True, "")
    finally:
        if saved is not None:
            os.environ["SUPERVISOR_GUARDRAIL"] = saved


# ── 步骤三/五：supervisor 节点短路 ─────────────────────────────

def test_fast_path_short_meeting() -> None:
    stub = _StubSupervisor()
    system = _make_system(stub)
    node = system._make_supervisor_node("minutes")
    out = asyncio.run(node(_state(_SHORT, draft=_CLEAN_DRAFT)))
    sub = (out.get("lines") or {}).get("minutes") or {}
    check("短会不调 LLM 审核", stub.calls == 0, f"calls={stub.calls}")
    check("短会返回确定性 approve（检查项全 pass）",
          sub.get("review", {}).get("decision") == "approve"
          and sub.get("review", {}).get("facts_check", {}).get("status") == "pass",
          str(sub.get("review")))
    check("短路标记为 review_bypassed（≠ 审核失败）",
          str(sub.get("review_bypassed", "")).startswith("short_meeting:")
          and not sub.get("review_unavailable"),
          str(sub.get("review_bypassed")))

    # 降级草稿（Agent 失败）不短路：留一轮审核+返工的自愈机会
    stub2 = _StubSupervisor()
    system2 = _make_system(stub2)
    out2 = asyncio.run(
        system2._make_supervisor_node("minutes")(
            _state(_SHORT, draft={}, degraded=True)
        )
    )
    sub2 = (out2.get("lines") or {}).get("minutes") or {}
    check("降级草稿不短路（照常送审）", stub2.calls == 1, f"calls={stub2.calls}")
    check("降级草稿送审无 bypass 标记", not sub2.get("review_bypassed"), str(sub2))


def test_fast_path_few_party() -> None:
    long_text = _pad("张工：本场过一下进度。李总：下周出报表。", 2600)  # > 2000，非短会
    stub = _StubSupervisor()
    system = _make_system(stub)
    out = asyncio.run(
        system._make_supervisor_node("minutes")(
            _state(
                long_text,
                draft=_CLEAN_DRAFT,
                topics=[{"title": "T1"}],
                speakers=[{"name": "张工"}, {"name": "李总"}],
            )
        )
    )
    sub = (out.get("lines") or {}).get("minutes") or {}
    check("议题≤2 且发言人≤2 的极简会议快速放行",
          stub.calls == 0
          and str(sub.get("review_bypassed", "")).startswith("few_topics:"),
          f"calls={stub.calls} bypass={sub.get('review_bypassed')}")

    stub2 = _StubSupervisor()
    system2 = _make_system(stub2)
    asyncio.run(
        system2._make_supervisor_node("minutes")(
            _state(
                _pad("张工：过进度。", 6000),  # 长会（> 门禁上限 5000）→ 必走 LLM
                draft=_CLEAN_DRAFT,
                topics=[{"title": "T1"}],
                speakers=[{"name": "张工"}, {"name": "李总"}],
            )
        )
    )
    check("长会不因议题少而短路（篇幅优先送审）", stub2.calls == 1, f"calls={stub2.calls}")

    # 极简输入在门禁区间内同样成立（3000 字、1 议题 1 发言人 → few_topics 短路）
    stub_few = _StubSupervisor()
    system_few = _make_system(stub_few)
    out_few = asyncio.run(
        system_few._make_supervisor_node("minutes")(
            _state(
                _pad("张工：缓存保护设计下周完成，时延指标压到200ms以内。", 3000),
                draft=_CLEAN_DRAFT,
                topics=[{"title": "T1"}],
                speakers=[{"name": "张工"}],
            )
        )
    )
    sub_few = (out_few.get("lines") or {}).get("minutes") or {}
    check("中篇极简会议（区间内）走 few_topics 短路",
          stub_few.calls == 0
          and str(sub_few.get("review_bypassed", "")).startswith("few_topics:"),
          f"calls={stub_few.calls} bypass={sub_few.get('review_bypassed')}")

    stub3 = _StubSupervisor()
    system3 = _make_system(stub3)
    asyncio.run(
        system3._make_supervisor_node("minutes")(
            _state(long_text, draft=_CLEAN_DRAFT, topics=[{"title": "T1"}], speakers=[])
        )
    )
    check("发言人清单缺失时保守送审", stub3.calls == 1, f"calls={stub3.calls}")


def test_guardrail_band() -> None:
    transcript = _pad("张工：缓存保护设计下周完成，时延指标压到200ms以内。", 2200)
    check("测试原文落在 2000~5000 区间", 2000 <= len(transcript) <= 5000, str(len(transcript)))

    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "on"}):
        # 全过 → 免审放行
        stub = _StubSupervisor()
        system = _make_system(stub)
        out = asyncio.run(
            system._make_supervisor_node("minutes")(
                _state(
                    transcript,
                    draft=_CLEAN_DRAFT,
                    topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    speakers=[{"name": "张工"}, {"name": "李总"}],
                )
            )
        )
        sub = (out.get("lines") or {}).get("minutes") or {}
        check("区间内规则全过 → 免审放行",
              stub.calls == 0 and sub.get("review_bypassed") == "rule_guardrail_pass",
              f"calls={stub.calls} bypass={sub.get('review_bypassed')}")

        # 命中红线（数字未落地）→ 照常送审
        bad_draft = {
            "headline": "缓存保护设计评审",
            "executive_summary": ["张工确认 QPS 提升到50000，时延压到200ms以内。"],
        }
        stub2 = _StubSupervisor()
        system2 = _make_system(stub2)
        asyncio.run(
            system2._make_supervisor_node("minutes")(
                _state(
                    transcript,
                    draft=bad_draft,
                    topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    speakers=[{"name": "张工"}, {"name": "李总"}],
                )
            )
        )
        check("命中红线（幻觉数字）→ 送 LLM 复核", stub2.calls == 1, f"calls={stub2.calls}")

    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "off"}):
        stub3 = _StubSupervisor()
        system3 = _make_system(stub3)
        asyncio.run(
            system3._make_supervisor_node("minutes")(
                _state(
                    transcript,
                    draft=_CLEAN_DRAFT,
                    topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    speakers=[{"name": "张工"}, {"name": "李总"}],
                )
            )
        )
        check("SUPERVISOR_GUARDRAIL=off → 不启用激进放行", stub3.calls == 1, f"calls={stub3.calls}")

    # 规则执行异常 → 按"未通过"处理，照常送审（不阻断主流程）
    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "on"}), patch(
        "core.graph.nodes.quick_facts_guardrail", side_effect=RuntimeError("boom")
    ):
        stub4 = _StubSupervisor()
        system4 = _make_system(stub4)
        asyncio.run(
            system4._make_supervisor_node("minutes")(
                _state(
                    transcript,
                    draft=_CLEAN_DRAFT,
                    topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    speakers=[{"name": "张工"}, {"name": "李总"}],
                )
            )
        )
        check("规则执行异常 → 照常送 LLM 复核", stub4.calls == 1, f"calls={stub4.calls}")

    # 记忆未注入却产出历史对照：确定性契约检查拦下（送审），不得免审放行
    fake_comparison = dict(_CLEAN_DRAFT)
    fake_comparison["history_comparison"] = ["延续事项（缓存保护｜自第1场）：缓存保护设计"]
    with patch.dict(os.environ, {"SUPERVISOR_GUARDRAIL": "on"}):
        stub5 = _StubSupervisor()
        system5 = _make_system(stub5)
        asyncio.run(
            system5._make_supervisor_node("minutes")(
                _state(
                    transcript,
                    draft=fake_comparison,
                    topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
                    speakers=[{"name": "张工"}, {"name": "李总"}],
                )
            )
        )
        check("无记忆注入却产出历史对照 → 送审", stub5.calls == 1, f"calls={stub5.calls}")

        # 记忆已注入（memory_context 非空）→ 对照合法，规则全过仍免审
        stub6 = _StubSupervisor()
        system6 = _make_system(stub6)
        state6 = _state(
            transcript,
            draft=fake_comparison,
            topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
            speakers=[{"name": "张工"}, {"name": "李总"}],
        )
        state6["lines"]["minutes"]["memory_context"] = "【会议记忆】\n项目：X\n"
        out6 = asyncio.run(system6._make_supervisor_node("minutes")(state6))
        check("记忆已注入时对照合法（规则全过 → 免审）",
              stub6.calls == 0
              and ((out6.get("lines") or {}).get("minutes") or {}).get("review_bypassed")
              == "rule_guardrail_pass",
              f"calls={stub6.calls}")


def test_review_unavailable_unchanged() -> None:
    """审核调用失败语义不变：保守放行 + review_unavailable + quality_degraded。"""
    stub = _StubSupervisor(raise_exc=True)
    system = _make_system(stub)
    out = asyncio.run(
        system._make_supervisor_node("minutes")(
            _state(
                _pad("张工：过进度。", 6000),
                draft=_CLEAN_DRAFT,
                topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
            )
        )
    )
    sub = (out.get("lines") or {}).get("minutes") or {}
    check("审核不可用：保守放行 + review_unavailable",
          str(sub.get("review_unavailable", "")).startswith("RuntimeError"),
          str(sub.get("review_unavailable")))
    check("审核不可用：quality_degraded 照旧", out.get("quality_degraded") is True, "")


# ── 步骤四：送审瘦身 ─────────────────────────────────────────

def test_review_context_slimming() -> None:
    draft = dict(_CLEAN_DRAFT)
    draft["key_decisions"] = ["采用二级缓存方案ABC"]
    draft["risks_and_blockers"] = ["多实例缓存不一致XYZ"]
    draft["unresolved_questions"] = ["降级策略未定QQQ"]
    draft["history_comparison"] = ["延续事项（网关）：缓存保护设计"]

    stub = _StubSupervisor()
    system = _make_system(stub)
    asyncio.run(
        system._make_supervisor_node("minutes")(
            _state(
                _pad("张工：缓存保护设计下周完成。", 6000),  # 长会 → 必走 LLM，可检查送审上下文
                draft=draft,
                topics=[{"title": "A"}, {"title": "B"}, {"title": "C"}],
            )
        )
    )
    ctx = stub.last_context
    check("送审上下文剔除搬运三字段",
          "key_decisions" not in ctx
          and "采用二级缓存方案ABC" not in ctx
          and "多实例缓存不一致XYZ" not in ctx
          and "降级策略未定QQQ" not in ctx,
          ctx[-600:])
    check("送审上下文保留提炼字段",
          "executive_summary" in ctx and "缓存保护设计下周完成" in ctx, ctx[-600:])
    check("送审上下文保留历史对照（程序注入，供对照核验）",
          "history_comparison" in ctx, ctx[-600:])

    # 直接单测：drop_keys 只影响命中的键，其它线（默认）零变化
    compacted = compact_draft_for_review(
        {"key_decisions": ["a"], "executive_summary": ["b"]},
        drop_keys=frozenset({"key_decisions"}),
    )
    check("compact 单测：drop_keys 整键剔除", "key_decisions" not in compacted, str(compacted))
    kept = compact_draft_for_review({"key_decisions": ["a"], "executive_summary": ["b"]})
    check("compact 单测：不传 drop_keys 行为不变", "key_decisions" in kept, str(kept))

    # notes 域调用（不带 drop_keys）不受影响：base 域行为由默认参数保证
    from domains.notes.orchestrator import NotesAgentSystem  # noqa: F401  (导入可达性）

    check("notes 域可导入（共用引擎，默认参数零影响）", True, "")


# ── 步骤一/二：契约与 prompt 口径 ────────────────────────────

def test_prompt_contracts() -> None:
    from domains.meeting.meeting_core import contracts as core_contracts
    from domains.meeting.meeting_core import prompts as core_prompts
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT,
    )

    understanding_prompt = core_prompts.MEETING_UNDERSTANDING_SYSTEM_PROMPT
    contract_text = core_contracts.MEETING_UNDERSTANDING_GENERATION_OUTPUT_CONTRACT
    check("理解层 prompt：context_and_debate 30~60字骨架",
          "30~60字" in understanding_prompt and "100~200字" not in understanding_prompt, "")
    check("理解层契约：描述同步为 30~60字",
          "30~60字" in contract_text and "100~200字" not in contract_text, "")

    check("纪要生成：明确「骨架为纲、回原文挖血肉」分工",
          "回到会议原文" in MINUTES_GENERATION_SYSTEM_PROMPT
          and "理解层是骨架" in MINUTES_GENERATION_SYSTEM_PROMPT, "")
    check("审核 prompt：搬运免审声明 + 不再要求逐字核对",
          "免审" in MINUTES_SUPERVISOR_DOMAIN_PROMPT
          and "enforce_minutes_draft" in MINUTES_SUPERVISOR_DOMAIN_PROMPT
          and "与上游不一致" not in MINUTES_SUPERVISOR_DOMAIN_PROMPT,
          "")
    check("审核 prompt：reject 三条件与 approve 首选口径保留",
          "reject 的三个可判定条件" in MINUTES_SUPERVISOR_DOMAIN_PROMPT
          and "拿不准就选它" in MINUTES_SUPERVISOR_DOMAIN_PROMPT, "")


def main() -> int:
    test_guardrail_names()
    test_guardrail_numbers()
    test_guardrail_skip_keys_and_env()
    test_fast_path_short_meeting()
    test_fast_path_few_party()
    test_guardrail_band()
    test_review_unavailable_unchanged()
    test_review_context_slimming()
    test_prompt_contracts()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for item in FAIL:
        print("FAIL", item)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
