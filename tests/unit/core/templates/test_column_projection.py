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
from tests.unit.core.templates._common import (
    BODY_CAPTION_TPL,
    CAPTION_TPL,
    FAIL,
    FILL_RULE_KEYS,
    FILL_TPL,
    KNOWN_PENDING_BRACKET_LITERALS,
    PASS,
    SCALAR_BASELINE_BY_DIR,
    SHAPE_RULE_KEYS,
    TEMPLATE_SHAPE_SNIPPETS,
    _active_dir,
    check,
)

def test_supervisor_unavailable_flow() -> None:
    """"审核不可用"整链路：节点返回保守 approve + 不 degraded；路由走 __end__（不再降级）。

    旧行为：审核调用失败 → reject_review + degraded → route 走 fallback → 用户拿到
    确定性拼装文本（低结构化闲聊型输入实测踩中）。新行为：保守放行 + 质量警告。
    """
    import asyncio

    from core.graph.nodes import DomainNodes

    class _Boom:
        async def review(self, context: str):  # noqa: ANN001
            raise RuntimeError("supervisor 输出无法满足结构契约：字段不一致：缺失=['feedback']")

    class _Stub(DomainNodes):
        MAX_REVISIONS = 1
        _task_lines = {"minutes": {
            "supervisor_attr": "sup",
            "reject_review": {
                "decision": "reject",
                "feedback": [],
                "facts_check": {"status": "fail", "findings": ["内容空洞"]},
                "perspective_check": {"status": "pass", "findings": []},
                "consistency_check": {"status": "fail", "findings": ["口径不一致"]},
            },
        }}
        _line_cn_names = {"minutes": "纪要"}

        def __init__(self) -> None:
            self.sup = _Boom()

        def _supervisor_context(self, state: dict, line_name: str) -> str:  # noqa: D102
            return "审核上下文"

    stub = _Stub()
    node = stub._make_supervisor_node("minutes")
    out = asyncio.run(node({"lines": {"minutes": {"draft": {"headline": "闲聊"}}}}))
    line_state = out["lines"]["minutes"]
    check("审核调用失败 → 本线不降级（照常渲染）", line_state.get("degraded") is False, f"{line_state.get('degraded')}")
    check("审核调用失败 → 保守 approve", (line_state.get("review") or {}).get("decision") == "approve", "")
    check("审核调用失败 → 记录原因（供 quality_warning/monitor）",
          "结构契约" in str(line_state.get("review_unavailable") or ""), f"{line_state.get('review_unavailable')}")
    check("仍标记 quality_degraded（如实提示未做质量把关）", bool(out.get("quality_degraded")), "")
    route = stub._make_route("minutes")
    state_after = {"lines": {"minutes": {"review": line_state["review"], "revision_count": 0}}}
    check("路由不再走 fallback（approve → __end__）", route(state_after) == "__end__", f"{route(state_after)}")

def test_minutes_chain_consistency() -> None:
    """纪要链路口径一致（2026-09 审计 ① ② ③）：形态单点化 + 摘要预算合一 + 审核两句。

    审计发现的矛盾：①摘要条数/句数在草稿 prompt（2–8 条、1–5 句）、契约（≤4 条、
    ≤3 句）、渲染 prompt 三处互斥；②形态在草稿/渲染 prompt 里是旧口径
    （每条以分类标签开头、每栏至少 2 个分类标签、20–80 字、加粗每条 2–3 处），
    与装配侧冲突——"每栏至少 2 个分类标签"正是标签复用（行20「盖章互动」×4）的成因；
    ③审核"无锚点空条/关键遗漏"会把合规的合并段判成空条，是剩余降级路径。
    """
    from domains.meeting.tasks.minutes.contracts import MINUTES_GENERATION_OUTPUT_CONTRACT as gen_contract
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as draft,
        MINUTES_RENDER_PROMPT as render,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as supervisor,
    )
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    # ③ 形态单点化：渲染路径逐字包含同一份规则（草稿已解耦）
    for label, text in (
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("纪要渲染 prompt", render),
    ):
        check(f"{label} 逐字包含 BODY_FORMAT_RULES（单点维护）", BODY_FORMAT_RULES in text, "")
    check("纪要草稿已与排版规则解耦（不包含 BODY_FORMAT_RULES）", BODY_FORMAT_RULES not in draft, "")
    check("形态单点：人分组用 `**姓名**：` 独占行、本人那组叫「与我相关」、不把人名写成 `##`",
          "「人」不是板块" in BODY_FORMAT_RULES
          and "（本人那一组写 `**与我相关**：`）" in BODY_FORMAT_RULES
          and "不得把人名或「与我相关」写成 `##` 标题" in BODY_FORMAT_RULES, "")
    check("形态单点：受控二级缩进显式场景触发口径到位",
          "受控二级缩进（显式场景触发）" in BODY_FORMAT_RULES
          and "现状/问题 与 解决方案 并存时" in BODY_FORMAT_RULES
          and "赞成观点/优势 与 潜在顾虑/风险 并存时" in BODY_FORMAT_RULES
          and "核心交付物 包含多个并列指标/模块/时限时" in BODY_FORMAT_RULES, "")
    stale = ["每栏至少 2 个分类标签", "每条 20–80 字", "每条 2–3 处（分类标签"]
    hit = [k for k in stale if any(k in t for t in (PLACEHOLDER_RULES, draft, render))]
    check("旧形态口径已从全部路径清除", not hit, f"残留={hit}")

    # ② 摘要分段：三处同一套（段数按内容、单段 ≤约 200 字——**只按字数口径**），旧数字已清除
    check("草稿 prompt / 契约都不再设固定段数上限",
          "≤4 段" not in draft and "≤4 段" not in gen_contract, "")
    check("草稿 prompt / 契约同写「不超过约 200 字」（单一维度，句数只作写法建议）",
          "不超过约 200 字" in draft and "不超过约 200 字" in gen_contract
          and "3 句或约" not in draft and "3 句或约" not in gen_contract, "")

    # ④ 篇幅口径三层同源（2026-09-22）：要求线（进 prompt）→ 拆分线（×1.2）→ 检查线（×1.5）
    # 兜底（重写/按句界截断）在动作层，不再有硬编码的 320/200。
    from core.execution.gate import (
        _CHECK_RATIO,
        _ITEM_CHECK_HAN,
        _ITEM_REQUIRE_HAN,
        _PARA_CHECK_HAN,
        _PARA_REQUIRE_HAN,
        _PARA_SPLIT_HAN,
        _SPLIT_RATIO,
    )
    check("三层数字有序：要求线 < 拆分线 ≤ 检查线（段落）／要求线 < 检查线（条目）",
          _PARA_REQUIRE_HAN < _PARA_SPLIT_HAN <= _PARA_CHECK_HAN
          and _ITEM_REQUIRE_HAN < _ITEM_CHECK_HAN,
          f"段落 {_PARA_REQUIRE_HAN}/{_PARA_SPLIT_HAN}/{_PARA_CHECK_HAN}，条目 {_ITEM_REQUIRE_HAN}/{_ITEM_CHECK_HAN}")
    check("检查线/拆分线由要求线派生（不再硬编码 320/200）",
          _PARA_CHECK_HAN == int(_PARA_REQUIRE_HAN * _CHECK_RATIO)
          and _PARA_SPLIT_HAN == int(_PARA_REQUIRE_HAN * _SPLIT_RATIO)
          and _ITEM_CHECK_HAN == int(_ITEM_REQUIRE_HAN * _CHECK_RATIO), "")
    check("prompt 里的要求线与代码常量一致（单一来源，必须同时改）",
          f"不超过约 {_PARA_REQUIRE_HAN} 字" in BODY_FORMAT_RULES
          and f"单条不超过约 {_ITEM_REQUIRE_HAN} 字" in BODY_FORMAT_RULES, "")
    from core.execution.gate import advisory_issues as _adv
    check("advisory 阈值取自派生常量（默认值不再硬编码）",
          _adv.__kwdefaults__.get("para_han") == _PARA_CHECK_HAN
          and _adv.__kwdefaults__.get("long_han") == _ITEM_CHECK_HAN, "")
    check("契约声明「段数/句数是表达预算，不构成删事实的理由」",
          "不构成删事实的理由" in gen_contract, "")
    old_summary = [
        k
        for k in ("全篇 2–8 条", "每段最多 3 句", "2–8 条", "≤4 段", "每段 2–5 句", "2–5 句")
        if k in draft or k in gen_contract or k in render
    ]
    check("旧的互斥摘要口径已清除", not old_summary, f"残留={old_summary}")

    # ① 审核两句：合并段不算空条 + 关键遗漏按事实判（各只保留一份，不许重复）
    check("审核 prompt：合并型摘要段不算空条", "合并型摘要段不算空条" in supervisor, "")
    check("审核 prompt：关键遗漏按事实判、不按条数判",
          "按事实判，不按条数判" in supervisor, "")
    check("审核 prompt：不拦截/要拦截各只一份（旧的重复块已合并）",
          supervisor.count("不拦截：") == 1 and supervisor.count("要拦截：") == 1,
          f"不拦截={supervisor.count('不拦截：')} 要拦截={supervisor.count('要拦截：')}")

def test_understanding_trim_lists() -> None:
    """理解裁剪：可空名单与必须写全名单不许重叠，两名单并集 = 契约全部字段。

    回归背景：两张名单各写一份（后者写死在 agent 里），曾出现 risk_hints
    同时被列为「可空」和「必须写全」，且必须写全名单漏掉 topics/risks/open_questions。
    """
    from dataclasses import fields as dc_fields

    from domains.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )
    from domains.meeting.models import MeetingUnderstanding

    order = [f.name for f in dc_fields(MeetingUnderstanding)]
    cases = (
        ("minutes", {"speakers"}),
        ("risks", {"topics"}),
        ("actions", {"topics", "speakers"}),
    )
    for line, skip in cases:
        text = _trim_instruction(line, skip)
        blank_line = next(l for l in text.splitlines() if "键名必须保留、值给空数组" in l)
        keep_line = next(l for l in text.splitlines() if "必须照常" in l)
        # 只取名单本体：「仅供 X 线使用」里的线名可能恰好等于字段名（risks）
        blank_part = blank_line.split("空数组 []**：", 1)[-1]
        keep_part = keep_line.split("（", 1)[-1].split("）", 1)[0]
        blank_fields = {f for f in order if f in blank_part}
        keep_fields = {f for f in order if f in keep_part}
        check(f"裁剪名单-{line}：可空与必须写全不重叠",
              not (blank_fields & keep_fields),
              f"重叠={sorted(blank_fields & keep_fields)}")
        check(f"裁剪名单-{line}：两名单并集 = 契约全部字段",
              blank_fields | keep_fields == set(order),
              f"缺={sorted(set(order) - (blank_fields | keep_fields))}")
        check(f"裁剪名单-{line}：可空名单与本线裁剪一致",
              blank_fields == skip, f"实际={sorted(blank_fields)}")
    check("无可裁剪字段时不拼裁剪指令", _trim_instruction("", set()) == "", "")

def test_overview_cap_and_column_scope() -> None:
    """概括/背景栏：逐栏给出上限与边界，且不许跨栏复述。

    回归背景（now.xlsx 实测）：`exchange_forum` 的 [沟通背景与目的] 无上限 →
    模型写出 2764 字、45 句的单段，并把 [信息同步] 的明细又复述一遍。
    对策：字段清单里逐栏给"最多 3 段、每段不超过 400 字"+「本栏不复述」，
    栏位自己声明了尺寸的以模板为准；规则层加「一栏只写自己的事」。
    """
    from core.templates.router._base import _describe_field
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    from core.templates.router._detect import _parse_field
    from core.templates.length_budget import budget_line

    # ① 未声明尺寸的概括栏：拿到默认上限 + 边界
    plain = _describe_field(1, _parse_field("一段话概括参与方、沟通主题与目的、达成的结果"))
    check("首栏（概括·无尺寸）拿到「只写一段」口径与 400 上限",
          "只写一段完整概括" in plain and "不超过 400 字" in plain, f"{plain[:80]}")
    check("首栏（概括·无尺寸）不套硬编码会议要素（避免非例会语义打架）",
          not any(k in plain for k in ("谁/什么场合", "覆盖哪几块", "以分享为主")),
          f"{plain[:120]}")
    check("首栏（概括·无尺寸）带「本栏不复述」边界",
          "本栏不复述" in plain and "归各自栏目" in plain, f"{plain[:80]}")
    non_first = _describe_field(2, _parse_field("一段话概括参与方、沟通主题与目的、达成的结果"))
    check("非首栏概括栏统一为单段上限 400 字（不要求下限）",
          "单栏上限 400 字" in non_first and "单段写完" in non_first,
          f"{non_first[:80]}")
    # 首栏自称"交代…"并已自列要素（就医/宣讲/研讨）：补下限口径，但不套会议专用四要素
    authored = _describe_field(
        1, _parse_field("一段话交代患者基本信息、就诊科室与时间、本次就诊的核心主诉与初步判断")
    )
    check("自述要素的首栏拿到下限口径（只写一段）",
          "只写一段完整概括" in authored and "按本栏说明把要素交代完整" in authored,
          f"{authored[:100]}")
    check("自述要素的首栏不套会议专用四要素（避免语义打架）",
          "以分享为主" not in authored and "谁/什么场合" not in authored, f"{authored[:100]}")

    # ② 自己声明了尺寸的概括栏：以模板为准，不叠加默认上限
    sized = _describe_field(1, _parse_field("一段话概括：先写这段文本是什么；**单段不超过约 200 字**，信息多就拆段"))
    check("已声明尺寸的概括栏不被叠加默认上限",
          "不超过 400 字" not in sized and "本栏不复述" in sized,
          f"{sized[:90]}")

    # ③ 取材来源句（「从概况与原文提取下一步」）不算概括栏，不给概况规格
    ref = _describe_field(
        2, _parse_field("**从概况与原文提取下一步**（不要因为已写进风险表就不写）：核心交付物、验收标准")
    )
    check("取材来源句不被误判为概括栏",
          "400 字" not in ref, f"{ref[:80]}")

    # ④ 规则层：自由渲染、共用形态规则都写了这份口径
    for label, text in (
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("共用形态规则", BODY_FORMAT_RULES),
    ):
        check(f"{label}：概括栏上限口径到位",
              "最多 3 段、每段不超过 400 字" in text or "单段不超过 400 字" in text, "")
    check("篇幅优先级明确（模板栏位上限不被动态预算覆盖）",
          "模板显式栏位上限 > 本动态总预算 > 默认形态规则" in budget_line(5000), "")

def test_enum_normalize_fallback() -> None:
    """形态标签已彻底解绑：MeetingUnderstanding 不再强依赖 scene 粗粒度标签。"""
    from dataclasses import fields as dc_fields
    from domains.meeting.models_generated import MeetingUnderstanding
    from domains.meeting.meeting_core import prompts as core_prompts

    field_names = {f.name for f in dc_fields(MeetingUnderstanding)}
    check("理解层模型：已彻底解绑 scene 字段", "scene" not in field_names, f"{field_names}")

    text = "\n".join(
        str(getattr(core_prompts, name))
        for name in dir(core_prompts)
        if name.isupper() and isinstance(getattr(core_prompts, name), str)
    )
    check("理解 prompt：已移除 scene 7 个枚举的死板限制", "只能填这 7 个值之一" not in text, "")

def test_scene_hint_from_template() -> None:
    """scene_hint 补丁已彻底拔除：编排层不再强行覆盖模型输出。"""
    src = Path("domains/meeting/orchestrator.py").read_text(encoding="utf-8")
    check("编排层：不再导入 scene_hint", "scene_hint" not in src, "")
    check("编排层：不再有 scene 暴力覆盖代码", 'data["scene"] = hint' not in src, "")

def test_allow_missing_on_trimmed_fields() -> None:
    """单线裁剪字段允许缺键：模型把"输出 []"理解成"键不用写"时不再白跑一轮重试。

    回归背景（2026-09-18 15:51 实测）：单线 minutes 会裁剪 risk_hints，裁剪指令写的是
    "输出空数组 []"，但模型常把整个键省掉 → 契约要求字段集合完全一致 →
    `结构化校验失败` → 针对性重试一次（+20s，第二次才把键补上）。
    """
    import json
    from dataclasses import fields as dc_fields

    from infra.llm.client import LLMClient
    from domains.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )
    from domains.meeting.models_generated import MeetingUnderstanding

    base = {
        f.name: ("一段话" if "list" not in str(f.type) else [])
        for f in dc_fields(MeetingUnderstanding)
    }
    trimmed = {k: v for k, v in base.items() if k != "speakers"}

    out = LLMClient._parse_and_validate(
        json.dumps(trimmed), MeetingUnderstanding, frozenset({"speakers"})
    )
    check("裁剪字段缺键时补默认 []（不再抛错重试）", out.speakers == [], f"{out.speakers}")
    try:
        LLMClient._parse_and_validate(json.dumps(trimmed), MeetingUnderstanding)
        failed = False
    except Exception:  # noqa: BLE001
        failed = True
    check("未声明 allow_missing 时缺键仍严格报错（不放松其它字段）", failed, "")
    unkept = {k: v for k, v in base.items() if k != "topics"}
    try:
        LLMClient._parse_and_validate(
            json.dumps(unkept), MeetingUnderstanding, frozenset({"speakers"})
        )
        failed2 = False
    except Exception:  # noqa: BLE001
        failed2 = True
    check("非裁剪字段缺键仍报错（只在裁剪集合内放宽）", failed2, "")

    trim = _trim_instruction("minutes", ("speakers",))
    check("裁剪指令写明「键名必须保留、值给空数组 []」",
          "键名必须保留" in trim and "不要省略键名" in trim, trim[:80])

    with_extra = dict(base)
    with_extra["action_hints"] = []
    with_extra["dependencies"] = []
    with_extra["risk_hints"] = []
    out_extra = LLMClient._parse_and_validate(json.dumps(with_extra), MeetingUnderstanding)
    check("模型输出多余顶层字段时自动清洗放行（不抛错重试）",
          isinstance(out_extra, MeetingUnderstanding) and not hasattr(out_extra, "action_hints"), "")

    from core.execution.hard_execution import enforce_upstream_carry, MINUTES_CARRY_MAP

    degraded_draft = {
        "headline": "进展同步",
        "key_decisions": ["自研模型按期上线"],
        "risks_and_blockers": ["显存不足需要切分"],
    }
    preserved = enforce_upstream_carry(degraded_draft, {}, MINUTES_CARRY_MAP)
    check("上游理解为空时保留草稿已有决议与风险（不暴力抹除）",
          preserved["key_decisions"] == ["自研模型按期上线"]
          and preserved["risks_and_blockers"] == ["显存不足需要切分"], "")

    src = Path("domains/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    check("理解 agent：把裁剪集合 + speakers 传给 allow_missing",
          "allow_missing=missable" in src and 'missable = skipped | {"speakers"}' in src, "")

def test_understanding_skip_never_retries() -> None:
    """每条线的理解裁剪字段都允许缺键：模型省略被裁剪字段时不再白跑重试。

    回归背景（2026-09-18）：单线跑 minutes 会裁剪 risk_hints，模型把"输出空数组 []"理解成
    "整个键不用写" → 契约要求字段集合完全一致 → 校验失败 → 针对性重试一次（+20s）。
    用户实测在 讲座概况、对话概况 等场景都出现——**同一处路径**（理解阶段按线裁剪，
    与模板无关），所以修的是线级机制，30 个模板一起覆盖。
    """
    import asyncio
    import json
    from dataclasses import fields as dc_fields

    from infra.llm.client import LLMClient
    from domains.meeting.meeting_core.meeting_understanding_agent import (
        MeetingUnderstandingAgent,
    )
    from domains.meeting.models_generated import MeetingUnderstanding
    from domains.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS

    class _FakeUnderstandingClient:
        """只回一份"省略了裁剪字段"的 JSON；按 structured 的 allow_missing 语义校验。"""

        def __init__(self, skip: set[str]) -> None:
            self.skip = set(skip)
            self.calls = 0

        async def structured(self, system, user, model, contract, *, label="", allow_missing=(), **kw):
            self.calls += 1
            payload = {
                f.name: ("一段话" if "list" not in str(f.type) else [])
                for f in dc_fields(model)
            }
            for key in self.skip:  # 模拟模型把被裁剪字段的键整个省掉
                payload.pop(key, None)
            return LLMClient._parse_and_validate(
                json.dumps(payload), model, frozenset(allow_missing)
            )

    list_fields = {
        f.name for f in dc_fields(MeetingUnderstanding) if "list" in str(f.type)
    }
    for line, skip in UNDERSTANDING_SKIP_FIELDS.items():
        fake = _FakeUnderstandingClient(set(skip))
        agent = MeetingUnderstandingAgent(fake)  # type: ignore[arg-type]
        out = asyncio.run(agent.run("会议原文：略。", focus_line=line, skip_fields=skip))
        blanks = [k for k in skip if k in list_fields]
        check(f"裁剪字段缺键不报错、一次调用成功（{line} 线：{sorted(skip)}）",
              all(getattr(out, k) == [] for k in blanks) and fake.calls == 1,
              f"calls={fake.calls}")
    check("裁剪集合覆盖 minutes/actions/risks 三条线",
          set(UNDERSTANDING_SKIP_FIELDS) == {"minutes", "actions", "risks"}, "")

    src = Path("domains/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    check("理解 agent：同一裁剪集合既写进指令也传给 allow_missing（speakers 常空、缺键不算错）",
          "allow_missing=missable" in src and "键名必须保留" in src
          and 'missable = skipped | {"speakers"}' in src, "")
    node_src = Path("domains/meeting/orchestrator.py").read_text(encoding="utf-8")
    check("理解裁剪按选线 + 模板栏位（发布会类不抽用不到的字段）",
          "skip_fields_for_template(template)" in node_src
          and "skip_fields=skip" in node_src, "")

def test_template_aware_understanding_skip() -> None:
    """minutes 单线：理解层再按**模板栏位**裁一次（模板没有风险/未决栏就不抽）。

    回归背景（2026-09-18 耗时复盘）：minutes 的 pack 只取
    brief/purpose/scene/topics/decisions/risks/open_questions——
    action_hints / risk_hints / dependencies 这条线从不消费；risks / open_questions 也只
    在模板真有风险/未决栏时才进正文。而理解层输出是整条链最贵的中间件：它要进草稿、审核、
    装配每一次调用的上下文（实测一篇 6000 字发布会实录抽了 6.2k token / 1.3 万字符）。
    发布会四栏、讲座四栏、课堂四栏、访谈三栏都用不到这两栏，属于纯浪费。
    """
    from domains.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS, _Nodes
    from domains.meeting.understanding_skip import skip_fields_for_template

    base = set(UNDERSTANDING_SKIP_FIELDS["minutes"])
    check("minutes 基础裁剪带走 action_hints/risk_hints/dependencies",
          {"action_hints", "risk_hints", "dependencies"} <= base, f"{sorted(base)}")

    d = _active_dir()

    def load(name: str) -> str:
        return (d / f"{name}.md").read_text(encoding="utf-8")

    both = frozenset({"risks", "open_questions"})
    mb = load("media_briefing")
    check("新闻发布：无风险/未决栏 → 再跳 risks/open_questions",
          skip_fields_for_template(mb) == both, f"{sorted(skip_fields_for_template(mb))}")
    check("通用纪要：[要点梳理] 含「待确认与风险」→ 一个都不跳",
          skip_fields_for_template(load("general_minutes")) == frozenset(),
          f"{sorted(skip_fields_for_template(load('general_minutes')))}")
    check("团队例会：协作需求提到阻塞 → risks 保留",
          "risks" not in skip_fields_for_template(load("team_meeting")), "")
    check("项目进度：有「风险预警」栏 → risks 保留（open_questions 无落点仍可跳）",
          "risks" not in skip_fields_for_template(load("project_progress")),
          f"{sorted(skip_fields_for_template(load('project_progress')))}")
    check("讲座/访谈/课堂/产品发布：四类都用不到风险与未决 → 全跳",
          all(
              skip_fields_for_template(load(n)) == both
              for n in (
                  "special_lecture",
                  "interview_transcript",
                  "class_transcript",
                  "product_launch",
                  "media_qa_session",
                  "admission_briefing",
              )
          ),
          "",
      )
    check("空模板 → 不裁（宁多不漏）", skip_fields_for_template("") == frozenset(), "")

    # 覆盖率守卫：29 个模板都要得出结论，且只可能跳这两个字段
    allowed = {"risks", "open_questions"}
    out_of_range: list[tuple[str, list[str]]] = []
    trimmed: list[str] = []
    for md in sorted(d.glob("*.md")):
        if md.stem.lower() == "readme":
            continue
        got = skip_fields_for_template(md.read_text(encoding="utf-8"))
        if not got <= allowed:
            out_of_range.append((md.stem, sorted(got)))
        if got == both:
            trimmed.append(md.stem)
    check("每个模板的裁剪结论都落在允许集合内", not out_of_range, f"{out_of_range}")
    check("至少 10 个模板（发布会/讲座/课堂/访谈类）拿到两栏裁剪",
          len(trimmed) >= 10, f"仅 {len(trimmed)} 个：{trimmed}")

    # 节点侧合并：单线 minutes + 模板 → 五项；多线/无模板不裁
    merged = frozenset(base | both)

    def skip_of(names: list[str], tpl: str = "") -> frozenset[str]:
        return _Nodes._understanding_skip(object(), names, tpl)

    check("单线 minutes + 新闻发布模板 → 五项一起跳",
          skip_of(["minutes"], mb) == merged, f"{sorted(skip_of(['minutes'], mb))}")
    check("多线请求不裁（理解还要服务待办/风险线）",
          skip_of(["minutes", "actions"], mb) == frozenset(), "")
    check("未给模板的单线 minutes → 只跳基础三项",
          skip_of(["minutes"]) == frozenset(base), f"{sorted(skip_of(['minutes']))}")
    check("其它线不受模板影响（actions 线模板不给也不改集合）",
          skip_of(["actions"], mb) == UNDERSTANDING_SKIP_FIELDS["actions"], "")

    from domains.meeting.meeting_core.meeting_understanding_agent import (
        _trim_instruction,
    )

    trim = _trim_instruction("minutes", sorted(merged))
    check("裁剪指令把五项都列进「值给空数组 []」",
          "键名必须保留" in trim and all(k in trim for k in merged), trim[:120])
    check("裁剪指令的「必须照常输出」名单里不含被裁字段",
          all(k not in trim.split("其余字段")[1].split("必须照常")[0] for k in merged), "")

    # 节点侧：裁剪集合确实随 state 里的模板变化（不是建节点时定死）
    import asyncio

    class _FakeAgent:
        def __init__(self) -> None:
            self.seen: list[tuple[str, frozenset[str]]] = []
            self.channel = None

        async def run(self, transcript, *, focus_line="", skip_fields=(), user_channel=""):
            self.seen.append((focus_line, frozenset(skip_fields)))
            self.channel = user_channel

            class _Out:
                @staticmethod
                def model_dump() -> dict:
                    return {"scene": "通用"}

            return _Out()

    fake = _FakeAgent()

    class _Host(_Nodes):
        """只借 _Nodes 的方法与状态读取；不跑父类 __init__（不建 LLM 客户端）。"""

        def __init__(self, agent) -> None:
            self.meeting_understanding_agent = agent

    host = _Host(fake)
    node = _Nodes._make_meeting_understanding_node(host, ["minutes"])
    asyncio.run(node({"transcript": "原文略。", "templates": {"minutes": mb}}))
    asyncio.run(
        node(
            {
                "transcript": "原文略。",
                "templates": {"minutes": load("general_minutes")},
            }
        )
    )
    asyncio.run(node({"transcript": "原文略。"}))
    check("节点按 state 模板定裁剪：新闻发布五项 / 通用纪要三项 / 无模板三项",
          [frozenset(s) for _, s in fake.seen] == [merged, frozenset(base), frozenset(base)],
          f"{[(f, sorted(s)) for f, s in fake.seen]}")
    check("节点只在裁剪非空时报线名（无裁剪则不给 focus）",
          [f for f, _ in fake.seen] == ["minutes", "minutes", "minutes"], "")

    # 本用户称呼表由节点按 state 画像现算（客观/无画像 → 空串，不注入）
    asyncio.run(node({"transcript": "原文略。", "user": {"name": "赵衡", "name_aliases": ["小赵"]}}))
    check("节点把称呼表传给理解层",
          "赵衡（全称）" in (fake.channel or "") and "小赵" in (fake.channel or ""), str(fake.channel))
    asyncio.run(node({"transcript": "原文略。", "user": {"perspective": "objective", "name": "赵衡"}}))
    check("客观视角不传称呼表", not fake.channel, str(fake.channel))

def test_long_generation_output_cap() -> None:
    """长生成调用必须有输出上限：本地端点没有隐含上限，一次退化 = 49k token / 9 分钟。

    回归背景（2026-09-18 实测）：装配退化成"写不完"——49,074 token / 86,447 字符 / 551 秒，
    被 max_tokens 截断后 JSON 不可解析 → 四栏全空 → 整篇重填，一条纪要跑满 10 分钟。
    """
    from core.templates.length_budget import (
        OUTPUT_CAP_MAX,
        OUTPUT_CAP_MIN,
        effective_doc_budget,
        output_token_cap,
        target_han,
    )

    check("原文过短（<300 汉字）不给档位预算", effective_doc_budget(200) is None, "")
    check("8k–20k 档：预算 1680–5500",
          effective_doc_budget(12000) == (1680, 5500), f"{effective_doc_budget(12000)}")
    check("模板声明优先于档位（当前 30 个模板都没声明 → 全走档位）",
          effective_doc_budget(12000, "# [栏]\n[说明]") == (1680, 5500), "")
    caps = [output_token_cap(h) for h in (200, 12000, 60000)]
    check("输出上限随原文规模递增且夹在 1200–12000",
          OUTPUT_CAP_MIN <= caps[0] <= caps[1] <= caps[2] <= OUTPUT_CAP_MAX, f"{caps}")
    check("失控量级：8k–20k 原文 → 6600 token（本地约 1 分钟，原来 49k/9 分钟）",
          output_token_cap(12000) == 6600, f"{output_token_cap(12000)}")
    check("无预算的短原文给中性目标 4000", target_han(None, "") == 4000, "")

    # 模板说明里的「短语 20 字内」曾被解析成 hi=20 的小节上限（讲座 [核心观点与论证]，
    # 2026-09-19 实测）：每跑一次都报软提示，且该栏一旦出现散文段会被切成 20 字碎块。
    # 这里钉住"不存在可疑的小节预算"（正常栏级尺寸都在 80 字以上），防止同类写法再犯。
    from core.templates.template_eval import parse_section_char_budgets as _psb

    suspicious = []
    for md in sorted(_active_dir().glob("*.md")):
        for b in _psb(md.read_text(encoding="utf-8")):
            if (b.get("hi") or 10**9) < 80:
                suspicious.append((md.stem, b["title"], b["hi"]))
    check("没有 <80 字的「可疑小节预算」（数字+字 的说明性写法已清除）",
          not suspicious, f"{suspicious}")

    placeholder_src = Path("core/templates/router/_placeholder.py").read_text(encoding="utf-8")
    check("装配：max_tokens 来自目标字数换算并写进两个路径",
          "max_tokens=cap" in placeholder_src
          and "output_token_cap(source_han, template)" in placeholder_src, "")
    render_src = Path("core/runtime/render.py").read_text(encoding="utf-8")
    check("渲染/压缩/展开/返工四处都经 _render_run 带上限",
          render_src.count("_render_run(") >= 5
          and "source_han=_doc_han(state)" in render_src, "")
    # 装配路径的下限兑现（2026-09-19 实测：55 次运行全走 assemble，"低于下限" 6 次静默通过）
    check("装配路径补一轮「低于下限 15% → 扩写」（无硬伤且更长才采用）",
          'fill_mode == "assemble"' in render_src
          and "assemble too short" in render_src
          and "han < int(lo_i * 0.85)" in render_src
          and "_EXPAND_REVISION.format(han=han, lo=lo_i, hi=hi_i)" in render_src, "")
    minutes_src = Path(
        "domains/meeting/tasks/minutes/steps/minutes_render.py"
    ).read_text(encoding="utf-8")
    check("纪要渲染步接受并透传 max_tokens",
          "max_tokens=max_tokens" in minutes_src and "max_tokens: int | None = None" in minutes_src, "")
    budget_src = Path("core/templates/length_budget.py").read_text(encoding="utf-8")
    check("【篇幅预算】写明超上限会被截断", "超过上限的输出会被截断" in budget_src, "")

def test_column_fill_concurrency_and_early_stop() -> None:
    """逐栏填充：一栏一次调用、栏间并发、失败只重试该栏；退化（重复/超长）流式早停。

    回归背景（2026-09-18 实测）：整篇 JSON 装配退化时写出 49,074 token / 86,447 字符，
    551 秒后才被 max_tokens 截断，JSON 不可解析 → 四栏全空 → 整篇重填。逐栏后爆炸半径
    只有一栏，流式下发现重复/超长立刻放弃，只重试那一栏。
    """
    import asyncio
    import re as _re

    from core.templates.router._placeholder import (
        _degenerate_reason,
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    check("新闻发布：4 个标量栏、无表格（走逐栏路径）",
          len(plan["scalars"]) == 4 and not plan["row_templates"],
          f"{len(plan['scalars'])}/{len(plan['row_templates'])}")

    class _FakeStream:
        """脚本化流式客户端：按「第 N/M 栏」分派分块，并统计并发与每栏调用次数。"""

        def __init__(self, scripts: dict) -> None:
            self.scripts = scripts
            self.users: list[str] = []
            self.counts: dict[int, int] = {}
            self.caps: list[int] = []
            self.in_flight = 0
            self.max_in_flight = 0

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            self.caps.append(max_tokens)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            try:
                chunks = self.scripts[idx]
                if callable(chunks):
                    chunks = chunks(self.counts[idx])
                for chunk in chunks:
                    await asyncio.sleep(0)
                    yield chunk
            finally:
                self.in_flight -= 1

    good = {
        1: ["发布会概况：主办方、三块板块与整体基调。"],
        2: ["- **要点**：核心信息一条。"],
        3: ["**表态**：官方口径。"],
        4: ["**主持人**：问题？\n**发言人**：回应。"],
    }
    client = _FakeStream(dict(good))
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    check("逐栏填充：四栏各一次调用", client.counts == {1: 1, 2: 1, 3: 1, 4: 1}, f"{client.counts}")
    check("逐栏填充：栏间并发（同时在飞 ≥2）", client.max_in_flight >= 2, f"{client.max_in_flight}")
    check("逐栏填充：输出上限透传到每次调用（6600）",
          bool(client.caps) and all(c == 6600 for c in client.caps), f"{client.caps}")
    check("逐栏填充：拼装出四栏正文、标题由程序生成、无残留占位符",
          bool(text)
          and "# 发布会概况" in text
          and "[发布会概况]" not in text
          and all(chunks[0] in text for chunks in good.values()),
          (text or "")[:80])
    check("逐栏填充：每栏只拿自己的说明 + 其它栏名（防越栏）",
          all("【本栏说明】" in u for u in client.users)
          and "只写第 1/4 栏（发布会概况）" in client.users[0]
          and "[核心信息]" in client.users[0], "")
    check("逐栏填充：带上【本篇目标】（目标长度写进指令区）",
          all("【本篇目标】" in u for u in client.users), "")

    para = "同一段话反复出现，这段特意写长一点以触发退化判据，并确保累计长度越过检查阈值。" * 3
    scripts = dict(good)
    scripts[2] = lambda attempt: (
        [para + "\n\n"] * 3 if attempt == 1 else ["- **要点**：重试后的内容。"]
    )
    client2 = _FakeStream(scripts)
    text2 = asyncio.run(
        fill_placeholder_by_columns(client2, "内容来源略。", mb, plan, source_han=12000)
    )
    check("退化早停：重复段落被中止，且只重试该栏（其它栏一次）",
          client2.counts == {1: 1, 2: 2, 3: 1, 4: 1}, f"{client2.counts}")
    check("退化早停：最终用重试后的内容", bool(text2) and "重试后的内容" in text2, (text2 or "")[:60])

    scripts3 = dict(good)
    scripts3[3] = lambda attempt: (
        ["这是一段用来把输出撑到上限之外的填充文字。" * 600]
        if attempt == 1
        else ["**表态**：重试内容。"]
    )
    client3 = _FakeStream(scripts3)
    text3 = asyncio.run(
        fill_placeholder_by_columns(client3, "内容来源略。", mb, plan, source_han=12000)
    )
    check("超长早停：输出超上限即中止并只重试该栏",
          client3.counts == {1: 1, 2: 1, 3: 2, 4: 1} and bool(text3) and "重试内容" in text3,
          f"{client3.counts}")

    long_para = "这是一段足够长的重复段落文本内容，长度要超过判据下限。"  # ≥24 字才参与判据
    check("退化判据：同段重复 3 次命中、2 次不命中",
          "重复" in _degenerate_reason("\n\n".join([long_para] * 3))
          and _degenerate_reason("\n\n".join([long_para] * 2)) == ""
          and _degenerate_reason("短句。\n\n短句。\n\n短句。") == "", "")

    pp = (_active_dir() / "project_progress.md").read_text(encoding="utf-8")
    check("有表格的模板不走逐栏路径（返回 None，交给整篇 JSON）",
          asyncio.run(
              fill_placeholder_by_columns(
                  _FakeStream({}), "略", pp, plan_placeholder_fill(pp)
              )
          )
          is None,
          "")

def test_column_fill_overlong_item_rewrite() -> None:
    """逐栏填充：单条超长（`- ` 条目 >200 汉字）当硬问题 → 只重写中招那一栏，并下发具体修法。

    回归背景（2026-09-22 实测「端侧待办与现网推测问题」转写，同一输入相邻两次运行）：
    要点梳理栏把 12 条待确认 + 20 条风险各用「；」压成一条（233 字 / 519 字）原样落盘——
    审核在渲染之前（看不到栏内文字）、渲染层只把它当 advisory 记账，于是无人拦。
    现在这一栏会被定位、重写一次（一次单栏调用），渲染层行为不变。
    """
    import asyncio
    import re as _re

    from core.execution.gate import overlong_items
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)
    long_bullet = "- **表态**：" + "官方口径说明" * 45 + "。"
    good = {
        1: "发布会概况：主办方、三块板块与整体基调。",
        2: "- **要点**：核心信息一条。",
        4: "**主持人**：问题？\n**发言人**：回应。",
    }

    class _FakeStream:
        """脚本化流式客户端：第 3 栏首轮给一条超长条，重写轮给分条版本。"""

        def __init__(self) -> None:
            self.users: list[str] = []
            self.counts: dict[int, int] = {}

        async def stream_text(self, system, user, *, max_tokens=None, label="", **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.users.append(user)
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield long_bullet if self.counts[idx] == 1 else (
                    "- **表态**：官方口径一条。\n- **口径**：另一条。"
                )
            else:
                yield good[idx]

    client = _FakeStream()
    text = asyncio.run(
        fill_placeholder_by_columns(client, "内容来源略。", mb, plan, source_han=12000)
    )
    check("超长条：判据命中（>200 汉字的一条）", bool(overlong_items(long_bullet)), "")
    check("超长条：只重写中招那一栏（其余栏各一次）",
          client.counts == {1: 1, 2: 1, 3: 2, 4: 1}, f"{client.counts}")
    check("超长条：重写时下发具体修法（拆成多条 `- `、一条一个事项）",
          "拆成多条" in client.users[-1] and "一条一个事项" in client.users[-1],
          client.users[-1][-160:] if client.users else "")
    check("超长条：重写后的内容进了正文", "官方口径一条" in (text or ""), (text or "")[:60])
    check("超长条：最终正文不再有超长条", bool(text) and overlong_items(text) == [], "")

def test_column_fill_overlong_minutes_strategies() -> None:
    """验证 minutes 策略 A（调大判定阈值）与策略 B（频次门槛）有效性。

    - 策略 A：单个条目在 230~250 字（如司法/技术详细举证），设置 overlong_han=280 时不触发重写；
    - 策略 B：单条 290 字超过 280，但只有 1 条（未达到 min_count=2），不触发重写；
    - 频次触发：达到 2 条 290 字时，触发重写；
    - 极端超长：即使只有 1 条，但达到 380 字（>=350），依然安全兜底触发重写。
    """
    import asyncio
    import re as _re
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan = plan_placeholder_fill(mb)

    good = {
        1: "发布会概况：主办方、三块板块与整体基调。",
        2: "- **要点**：核心信息一条。",
        4: "**主持人**：问题？\n**发言人**：回应。",
    }

    # 测试 1: 策略 A + 策略 B（1 条 245 字，完全不触发重写，仅 1 次调用）
    court_evidence_bullet = "- **证据一**：" + "原告提交供货合同及对账单证明交付" * 15 + "。"  # ~240 字

    class _Client1:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield court_evidence_bullet if idx == 3 else good[idx]

    c1 = _Client1()
    asyncio.run(
        fill_placeholder_by_columns(
            c1, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("minutes策略A：1条245字证据条目（<=280字）不触发重写", c1.counts.get(3) == 1, f"{c1.counts}")

    # 测试 2: 策略 B（1 条 290 字，>280 但只有 1 条 < 2，容忍放行不触发重写）
    single_long_bullet = "- **证据一**：" + "原告提交供货合同及对账单证明交付" * 18 + "。"  # ~290 字

    class _Client2:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield single_long_bullet if idx == 3 else good[idx]

    c2 = _Client2()
    asyncio.run(
        fill_placeholder_by_columns(
            c2, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("minutes策略B：单条290字虽超280但仅1条（未达频次2），容忍放行不触发重写", c2.counts.get(3) == 1, f"{c2.counts}")

    # 测试 3: 策略 B 触发（2 条 290 字，达到频次 2，触发单栏重写）
    two_long_bullets = single_long_bullet + "\n" + single_long_bullet

    class _Client3:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield two_long_bullets if self.counts[idx] == 1 else "- **证据1**：拆分一。\n- **证据2**：拆分二。"
            else:
                yield good[idx]

    c3 = _Client3()
    asyncio.run(
        fill_placeholder_by_columns(
            c3, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("minutes策略B触发：2条290字达到频次门槛，触发该栏重写", c3.counts.get(3) == 2, f"{c3.counts}")

    # 测试 4: 极端大段挤压兜底（1 条 380 字，>=350，即使只有 1 条依然触发重写安全兜底）
    extreme_bullet = "- **表态**：" + "大段文字挤压挤压" * 48 + "。"  # ~386 字

    class _Client4:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            if idx == 3:
                yield extreme_bullet if self.counts[idx] == 1 else "- **表态**：拆分后内容。"
            else:
                yield good[idx]

    c4 = _Client4()
    asyncio.run(
        fill_placeholder_by_columns(
            c4, "内容来源略。", mb, plan, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("极端超长兜底：单条380字（>=350）即使仅1条也触发安全重写", c4.counts.get(3) == 2, f"{c4.counts}")

def test_column_fill_high_density_exemption() -> None:
    """验证高信息密度重点事实栏（新闻发布会核心信息、法庭举证等）免于过度重写。

    - 新闻发布会第 2 栏 [核心信息]：按模板要求合并指标与举措，即使 2 条每条 310 字（>280 且 count=2），
      识别为高密度事实栏（放宽阈值至 380），不触发多余单栏重写；
    - 庭审记录第 2 栏 [举证与法庭调查]：明确声明「不设字数上限、写全优先」，详细质证条目（320 字）直接放行；
    - 对比项新闻发布会第 3 栏 [官方表态]：属于显式字数约束栏（每条 40–120 字），超长时仍严格受控重写。
    """
    import asyncio
    import re as _re
    from core.templates.router._placeholder import (
        fill_placeholder_by_columns,
        plan_placeholder_fill,
    )

    # 1. 新闻发布会核心信息栏测试
    mb = (_active_dir() / "media_briefing.md").read_text(encoding="utf-8")
    plan_mb = plan_placeholder_fill(mb)

    # 2 条每条约 310 字的高密度政策与多指标条目
    dense_bullet = "- **政策措施**：" + "本季度落实增量政策工具并下达投资预算" * 15 + "。"  # ~310 字
    two_dense_bullets = dense_bullet + "\n" + dense_bullet

    good_mb = {
        1: "发布会概况：主办方与整体基调。",
        3: "- **表态**：官方口径一条。",
        4: "**主持人**：提问？\n**发言人**：回答。",
    }

    class _ClientMB:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield two_dense_bullets if idx == 2 else good_mb[idx]

    c_mb = _ClientMB()
    text_mb = asyncio.run(
        fill_placeholder_by_columns(
            c_mb, "内容来源略。", mb, plan_mb, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("高密度豁免：新闻发布会[核心信息]包含2条310字详实条目时不触发重写（仅1次调用）",
          c_mb.counts.get(2) == 1, f"{c_mb.counts}")
    check("高密度豁免：核心信息正文完整保留", "增量政策工具" in (text_mb or ""), "")

    # 2. 庭审记录 [举证与法庭调查] 测试
    court = (_active_dir() / "court_transcript.md").read_text(encoding="utf-8")
    plan_court = plan_placeholder_fill(court)

    # 举证栏详细质证条目（约 320 字）
    evidence_bullet = (
        "## 举证与质证\n"
        "- **证据一(原告提交供货单及对账确认函)**：证明原告已于约定时间足额供货，"
        + "被告对真实性无异议但辩称存在质量瑕疵未能如期投产故拒绝结算尾款" * 8 + "。"
    )
    good_court = {
        1: "庭审概况：案号与当事人。",
        3: "- **庭审结果**：择期宣判。",
    }

    class _ClientCourt:
        def __init__(self):
            self.counts = {}

        async def stream_text(self, system, user, **kw):
            idx = int(_re.search(r"第 (\d+)/", user).group(1))
            self.counts[idx] = self.counts.get(idx, 0) + 1
            yield evidence_bullet if idx == 2 else good_court.get(idx, "内容。")

        async def text(self, *a, **kw):
            return '{"tables": [[["原告", "诉讼请求", "事实理由"]]]}'

    c_court = _ClientCourt()
    text_court = asyncio.run(
        fill_placeholder_by_columns(
            c_court, "内容来源略。", court, plan_court, source_han=12000, overlong_han=280, overlong_min_count=2
        )
    )
    check("高密度豁免：庭审记录[举证与法庭调查]详实证据条目不触发重写（仅1次调用）",
          c_court.counts.get(2) == 1, f"{c_court.counts}")
    check("高密度豁免：法庭调查举证正文完整保留", "对账确认函" in (text_court or ""), "")

def test_personal_risk_attribution_in_pack() -> None:
    """真人模式：分钟线 pack 的风险/未决按原文补出归属（「姓名：」前缀）；客观零外溢。"""
    from domains.meeting.orchestrator import MeetingAgentSystem

    transcript = (
        "申家坤 00:00:05\n今天过长文本线。\n"
        "徐玥 00:00:20\n我这边还有一个风险：合规材料还没批下来，审批拖着会影响你的报告交付。\n"
        "武思华 00:00:45\n我的风险是接口权限没批，可能影响我这边的测试进度。\n"
    )
    understanding = {
        "speakers": [{"name": "申家坤"}, {"name": "徐玥"}, {"name": "武思华"}],
        "topics": [],
        "decisions": [],
        "risks": [
            "合规材料还没批下来，审批拖着会影响你的报告交付",
            "接口权限没批，可能影响测试进度",  # 轻度改写：靠 12 字探针对上原文
            "930 窗口期不多了",
        ],
        "open_questions": ["合规材料审批何时批下来"],
    }
    host = object.__new__(MeetingAgentSystem)  # 不跑 __init__（会建 LLM client）
    state = {
        "transcript": transcript,
        "user": {"name": "申家坤", "name_aliases": ["家坤"]},
        "objective_perspective": False,
        "meeting_understanding": understanding,
    }
    pack = host._meeting_pack(state, "minutes")
    risks = list(pack["risks"])
    check("真人 pack：有归属的风险条目带「姓名：」前缀",
          risks[0].startswith("徐玥：") and risks[1].startswith("武思华："), str(risks))
    check("真人 pack：看不出归属的全局风险不加前缀",
          risks[2] == "930 窗口期不多了", str(risks))
    check("真人 pack：派生问句（原文没有逐字表述）不硬归人",
          pack["open_questions"] == ["合规材料审批何时批下来"], str(pack["open_questions"]))
    obj = host._meeting_pack({**state, "objective_perspective": True}, "minutes")
    check("客观 pack：不加任何前缀（零外溢）",
          obj["risks"] == understanding["risks"]
          and obj["open_questions"] == understanding["open_questions"], str(obj["risks"]))

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
    from domains.meeting.meeting_core.prompts import MEETING_UNDERSTANDING_SYSTEM_PROMPT
    from domains.meeting.models_generated import MeetingUnderstanding
    from domains.meeting.orchestrator import (
        _EMPTY_MEETING_UNDERSTANDING,
        UNDERSTANDING_SKIP_FIELDS,
        _Nodes,
    )

    spec = MeetingUnderstandingGenerationContract.to_json_template()
    check("契约含 speakers 字段（name/role/org）",
          "speakers" in spec and all(k in spec for k in ("name", "role", "org")), spec[:60])
    check("生成模型有 speakers 且按数组校验",
          "speakers" in {f.name for f in dc_fields(MeetingUnderstanding)}
          and "speakers 必须是数组" in Path("domains/meeting/models_generated.py").read_text(encoding="utf-8"),
          "")
    check("空结构常量带 speakers（降级路径不炸）", _EMPTY_MEETING_UNDERSTANDING.get("speakers") == [], "")

    prompt = MEETING_UNDERSTANDING_SYSTEM_PROMPT
    check("理解 prompt：称呼按姓名、角色、原始编号回退，不猜姓名",
          "发言人与角色对照" in prompt and "姓名 > 原文明确角色 > 原始编号" in prompt
          and "只有编号时保留原始编号" in prompt and "不猜姓名、不新编编号" in prompt, "")
    check("理解 prompt：姓名不再从 participants 语义里挤（单列字段）",
          "speakers：" in prompt, "")

    check("speakers 不在任何线的裁剪集合里（人名所有线都要）",
          all("speakers" not in skip for skip in UNDERSTANDING_SKIP_FIELDS.values()), "")
    for line in ("minutes", "minutes_trace"):
        keep = _Nodes._understanding_needle_keep.get(line)  # 类属性，不用实例
        check(f"{line}：审核摘录白名单含 speakers", bool(keep) and "speakers" in keep, f"{sorted(keep or [])}")

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
        check(f"{line} 的 pack 带 speakers（{names}）", names == ["王毅"], f"{pack.get('speakers')}")

    draft_prompt = Path("domains/meeting/tasks/minutes/prompts.py").read_text(encoding="utf-8")
    check("草稿 prompt 指明人名绑定看 speakers、不猜姓名",
          "`speakers` 字段" in draft_prompt and "不要凭称号猜姓名" in draft_prompt, "")

def test_qa_name_priority() -> None:
    """新闻发布会/媒体问答：能确定是谁就用姓名，不得用「主持人」「发言人」顶替已知姓名。

    回归背景（2026-09-18 实测）：两栏原口径是"能对应到人就用称呼（姓名优先，其次角色）"，
    示例又写成 ``**主持人**：…`` 换行 ``**发言人**：…`` → 提问方清一色落到角色上
    （同一篇里答方能用上姓名、提问方仍是「主持人」）。发布会的专业写法是"媒体名＋记者/姓名"，
    所以这里把"姓名优先"改成硬口径，并去掉纯角色示例的锚定。
    """
    d = _active_dir()
    brief = (d / "media_briefing.md").read_text(encoding="utf-8")
    qa = (d / "media_qa_session.md").read_text(encoding="utf-8")

    brief_spec = next(l for l in brief.splitlines() if "一问一答" in l or "一条问答独立成段" in l)
    check("新闻发布：一问一答为一条记录（按提问顺序输出，示例答方写姓名）",
          "一问一答为一条记录" in brief_spec
          and ("`**记者（人民日报 张宇）**：…`" in brief_spec or "`**记者**：…`" in brief_spec)
          and "`**陈立**：…`" in brief_spec, brief_spec[:70])
    check("新闻发布：答方能确定写姓名、无法确定写「**答**」",
          "能确定写姓名" in brief_spec and "无法确定写「**答**」" in brief_spec, "")
    check("新闻发布：提问方按确定度回退",
          "提问方按确定度回退" in brief_spec, "")

    qa_spec = next(l for l in qa.splitlines() if "一条问答独立成段" in l)
    check("媒体问答：一问一答＝一条记录（逐条呈现，示例答方写姓名）",
          "一问一答＝一条记录" in qa_spec
          and ("逐条编号" in qa_spec or "逐条输出" in qa_spec)
          and "`**陈立**：…`" in qa_spec, qa_spec[:70])
    check("媒体问答：回应方能确定姓名才写姓名（「答」只作无姓名兜底）",
          "回应方能确定姓名才写姓名" in qa_spec and "不能确定就写「**答**」" in qa_spec
          and "全篇统一用同一个称呼" in qa_spec, "")
    check("媒体问答：称呼只写姓名/媒体名，机构不得单独充当身份",
          "机构只能跟在人名/媒体名后" in qa_spec and "不得单独充当身份" in qa_spec, "")
    check("媒体问答：提问方按确定度回退（不确定就不写名字）",
          "**提问方按确定度回退**" in qa_spec
          and "都不确定就不写名字、写成「问」" in qa_spec, "")

    from core.templates.body_rules import BODY_FORMAT_RULES

    rule = next(l for l in BODY_FORMAT_RULES.splitlines() if "成员称呼" in l)
    check("全局称呼规则：文中出现过姓名就用姓名（已知姓名不得退回角色）",
          "原文任何位置出现过该人的姓名就用姓名" in rule
          and "已知姓名时不得退回角色" in rule, rule[:80])
    check("全局称呼规则：角色与编号仍是后手，并禁止张冠李戴",
          "确实没有姓名才用角色" in rule and "沿用原文编号" in rule
          and "张冠李戴" in rule, "")
    # 2026-09-19 实测（肖楠场）：提问方被写成"张楠"——问答段之外出现 0 次，属无支撑造名。
    check("全局称呼规则：问答用名必须有问答段之外的支撑（无支撑退角色）",
          "问答/对话中使用的姓名必须有支撑" in rule
          and "在问答段之外的原文里出现过" in rule
          and "没有支撑的一律按上述顺序回退" in rule, rule[-140:])
    check("全局称呼规则：还要能确定对应的就是本次提问/回应的人（不确定不得用）",
          "还要能确定对应的就是本次提问或回应的人" in rule
          and "但无法确定对应关系的，**不得使用**" in rule, "")
    check("全局称呼规则：同音/近音变体取主流写法、全篇统一",
          "同音/近音变体" in rule and "取全场主流写法" in rule and "全篇统一" in rule, "")

    asr = next(l for l in BODY_FORMAT_RULES.splitlines() if "语音识别错" in l)
    check("语音识别规则补人名三条：变体统一 / 外文名用职务 / 禁止造名",
          "人名另加三条" in asr
          and "取全场主流写法、全篇统一" in asr
          and "外文/音译人名没把握写全就用职务或角色称呼" in asr
          and "禁止造名" in asr and "对称联想" in asr, asr[-160:])

    understanding = Path("domains/meeting/meeting_core/prompts.py").read_text(encoding="utf-8")
    check("理解层：原文出现姓名时统一用姓名、不推断不编造",
          "原文任何位置出现姓名就统一用姓名" in understanding
          and "不推断、不编造" in understanding, "")

def test_supervisor_contract_and_unavailable() -> None:
    """审核契约必填/联动说明 + 审核调用失败时的保守放行取值。"""
    from domains.meeting.tasks.minutes.contracts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT as contract
    from domains.meeting.tasks.minutes.contracts import MinutesSupervisorContract
    from core.graph.nodes import DomainNodes

    check("契约说明含「所有字段与检查项都必须出现」", "所有字段与检查项都必须出现" in contract, "")
    check("契约说明含 decision 联动规则",
          "decision=approve 时检查项必须全 pass" in contract and "reject 必须至少一个检查项 fail" in contract, "")
    check("feedback 说明不再只说「仅当 revise 时填写」",
          "仅当 decision=revise 时填写" not in contract and "字段必须出现" in contract, "")
    cfg = {"reject_review": {
        "decision": "reject",
        "feedback": [],
        "facts_check": {"status": "fail", "findings": ["x"]},
        "perspective_check": {"status": "pass", "findings": []},
        "consistency_check": {"status": "fail", "findings": ["y"]},
    }}
    payload = DomainNodes._conservative_review(cfg)
    check("审核不可用 → 保守 approve（检查项全 pass、feedback 空）",
          payload["decision"] == "approve" and payload["feedback"] == []
          and all(payload[k] == {"status": "pass", "findings": []}
                  for k in ("facts_check", "perspective_check", "consistency_check")),
          f"{payload}")
    check("契约仍声明 checks 非空（契约类不变量）", bool(MinutesSupervisorContract.checks), "")

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
    from domains.meeting.meeting_core.prompts import MEETING_UNDERSTANDING_SYSTEM_PROMPT
    from domains.shared.perspective import build_user_channel

    prompt = MEETING_UNDERSTANDING_SYSTEM_PROMPT
    check("理解 prompt：称呼表把别称归全称、编号发言人不绑",
          "【本用户称呼】" in prompt and "永远不等于本用户" in prompt
          and "归到全称那一个写法" in prompt,
          "")
    check("理解 prompt：仍是「不猜姓名」的口径（只统一既有称呼）",
          "不猜姓名" in prompt and "不要拿用户姓名去替换别人" in prompt, "")

    block = build_user_channel(
        {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    )
    check("称呼表含全称与别称", "赵衡（全称）" in block and "小赵、赵工" in block, block)
    check("称呼表写明统一写法与不猜编号",
          "统一写成「赵衡」" in block and "发言者1" in block, block)
    check("客观视角不注入", build_user_channel({"perspective": "objective", "name": "赵衡"}) == "", "")
    check("职业模板不注入（姓名是职业通称，不能当人名）",
          build_user_channel({"name": "开发人员", "persona_type": "role_template"}) == "", "")
    check("没有姓名不注入", build_user_channel({"name": "  "}) == "", "")

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
    check("称呼表拼在裁剪指令之后、会议原文之前",
          stub.user.index("【本次输出裁剪】")
          < stub.user.index("本用户称呼")
          < stub.user.index("会议原文："),
          stub.user[:120])
    asyncio.run(agent.run("原文", user_channel=""))
    check("无称呼表时不注入空块（用户消息仍以会议原文开头）",
          "本用户称呼" not in stub.user and stub.user.startswith("会议原文："), stub.user[:60])

def test_perspective_skip_for_personal() -> None:
    """P1-C：真人命中非空时跳过视角建模（省一轮核心调用），改用程序合成。

    回归背景：视角建模那轮看不到原文（输入只有理解 JSON + 画像），"他是谁"由理解层的
    称呼表 + 命中表决定；有命中时它的产出字段（attention_points / responsibilities /
    possible_actions / evidence）程序都能算，再跑一轮只是复述。唯一保留 LLM 的是
    "真人 + 完全没命中 + 挂 role_template"。
    """
    import asyncio

    from domains.meeting.orchestrator import _Nodes
    from domains.shared.perspective import PerspectiveModeling

    class _Spy:
        def __init__(self, behave: str = "raise") -> None:
            self.calls = 0
            self.behave = behave

        async def run(self, input_context, user_json):
            self.calls += 1
            if self.behave == "raise":
                raise AssertionError("这一路不该调用视角建模 LLM")

            class _Out:
                @staticmethod
                def model_dump() -> dict:
                    return {"confidence": "high", "name": "赵衡", "inferred_role": "后端工程师"}

            return _Out()

    class _Host(_Nodes):
        """只借 _Nodes 的方法；不跑父类 __init__（不建 LLM 客户端）。"""

        def __init__(self, agent) -> None:
            self.perspective_modeling_agent = agent

        def _understanding(self, state):
            return state.get("meeting_understanding") or {}

    user = {"name": "赵衡", "name_aliases": ["小赵", "赵工"], "role": "后端工程师"}
    understanding = {
        "speakers": [{"name": "赵衡"}],
        "action_hints": [{"text": "接口联调周五前给测试", "owner": "赵衡", "timing": "周五前"}],
        "decisions": [],
        "risks": [],
        "open_questions": [],
        "topics": [],
    }
    empty_understanding = {"speakers": [], "action_hints": [], "decisions": [], "risks": [],
                           "open_questions": [], "topics": []}

    spy = _Spy()
    out = asyncio.run(
        _Host(spy)._make_perspective_node(["minutes"])(
            {"user": user, "meeting_understanding": understanding, "objective_perspective": False}
        )
    )
    check("命中非空（单线）：没有调用视角建模 LLM", spy.calls == 0, f"calls={spy.calls}")
    PerspectiveModeling.validate(out["perspective_profile"])  # 合成必须过 schema（全字段必填）
    check("命中非空：合成模型过 schema，且要点/依据来自命中",
          out["perspective_profile"]["name"] == "赵衡"
          and "接口联调周五前给测试" in out["perspective_profile"]["attention_points"]
          and bool(out["perspective_profile"]["evidence"]),
          str(out["perspective_profile"])[:120])
    check("命中表写进 state（供草稿/审核）",
          (out.get("user_hits") or {}).get("confidence") == "high"
          and "本用户命中" in (out.get("user_hits_block") or ""),
          str(out.get("user_hits_block"))[:70])

    spy2 = _Spy("ok")
    asyncio.run(
        _Host(spy2)._make_perspective_node(["minutes"])(
            {
                "user": dict(user, role_template="developer"),
                "meeting_understanding": empty_understanding,
                "objective_perspective": False,
            }
        )
    )
    check("未命中 + 有职业底：仍然跑建模（唯一保留）", spy2.calls == 1, f"calls={spy2.calls}")

    spy3 = _Spy("ok")
    asyncio.run(
        _Host(spy3)._make_perspective_node(["minutes", "actions"])(
            {"user": user, "meeting_understanding": understanding, "objective_perspective": False}
        )
    )
    check("多线请求：不跳（保待办/风险线的视角模型）", spy3.calls == 1, f"calls={spy3.calls}")

    # 保守口径（2026-09-21 定）：画像里有可扫关注域（挂职业底 / 自写 focus_areas 等）→ 一律走建模。
    # 理由：命中表只按姓名查，"没点名但落在他关注域"的条目只有建模能捞；只有极简画像才允许跳过。
    spy5 = _Spy("ok")
    asyncio.run(
        _Host(spy5)._make_perspective_node(["minutes"])(
            {
                "user": dict(user, focus_areas=["接口契约与依赖", "排期节点"]),
                "meeting_understanding": understanding,
                "objective_perspective": False,
            }
        )
    )
    check("自写关注域 + 命中非空：仍走建模（保守口径）", spy5.calls == 1, f"calls={spy5.calls}")

    spy4 = _Spy("ok")
    out4 = asyncio.run(
        _Host(spy4)._make_perspective_node(["minutes"])(
            {
                "user": {k: v for k, v in user.items()},
                "meeting_understanding": empty_understanding,
                "objective_perspective": False,
            }
        )
    )
    check("未命中 + 无职业底：跳过并合成「本场未点到」（不跑 LLM）",
          spy4.calls == 0 and "未点到" in out4["perspective_profile"]["personal_summary"],
          f"calls={spy4.calls} {out4['perspective_profile']['personal_summary']}")

def test_personal_no_full_fallback() -> None:
    """P1-10 真人不再"裁空回退全量" + P2-F 命中表进审核上下文与三条检查。

    回归背景：命中块告诉草稿"哪些是他的"、模型照做裁成空（本场确实没他的事），
    但程序 ``subset_upstream_items`` 会把**全员条目**塞回他的视角——"赵衡视角"输出
    全员待办就是这么来的。职业模板保留回退（它更容易整类漏），真人必须选空即空。
    """
    from core.execution.gate import enforce_minutes_draft, subset_upstream_items

    upstream = ["接口联调周五前给测试", "端侧版本下周带上", "数据标注这周归档"]
    check("真人：选空 → 空（不再回退全量）",
          subset_upstream_items(upstream, [], fallback_full=False) == [], "")
    check("职业模板：选空 → 仍回退全量（行为不变）",
          subset_upstream_items(upstream, [], fallback_full=True) == upstream, "")
    check("真人：选中能对上的 → 只留对上的（上游原序原文）",
          subset_upstream_items(upstream, ["端侧版本下周带上"], fallback_full=False)
          == ["端侧版本下周带上"], "")
    check("真人：一条都对不上 → 空（不回退全量）",
          subset_upstream_items(upstream, ["完全无关的一句"], fallback_full=False) == [], "")
    check("默认参数仍是回退全量（老调用不静默改行为）",
          subset_upstream_items(upstream, []) == upstream, "")

    draft = {
        "headline": "进展同步",
        "key_decisions": [],
        "risks_and_blockers": [],
        "unresolved_questions": ["端侧版本下周带上"],
    }
    understanding = {"meeting_purpose": "进展同步", "decisions": ["引擎并发先借资源"],
                     "risks": ["双录还没确认"], "open_questions": ["端侧版本下周带上"]}
    personal = enforce_minutes_draft(dict(draft), understanding, mode="personal")
    check("enforce（真人）：选空的两项是空、选中的对齐上游原文",
          personal["key_decisions"] == [] and personal["risks_and_blockers"] == []
          and personal["unresolved_questions"] == ["端侧版本下周带上"], str(personal))
    role = enforce_minutes_draft(dict(draft), understanding, mode="role_template")
    check("enforce（职业模板）：选空的两项回退全量",
          role["key_decisions"] == ["引擎并发先借资源"] and role["risks_and_blockers"] == ["双录还没确认"],
          str(role))
    objective = enforce_minutes_draft(dict(draft), understanding, mode="objective")
    check("enforce（客观）：三项全量拷贝（与模式判定无关）",
          objective["key_decisions"] == ["引擎并发先借资源"] and len(objective["risks_and_blockers"]) == 1, "")

    # P2-F：审核上下文带命中块 + 审核提示词三条
    from domains.meeting.tasks.minutes.prompts import MINUTES_SUPERVISOR_DOMAIN_PROMPT as MINUTES_SUPERVISOR_PROMPT

    # 注：提示词里有 ** 加粗标记，断言别跨标记取串
    check("审核提示词含命中表三条检查",
          "命中表三条" in MINUTES_SUPERVISOR_PROMPT
          and "在命中表内" in MINUTES_SUPERVISOR_PROMPT
          and "不得当负责人或发言人" in MINUTES_SUPERVISOR_PROMPT
          and "至少用上一条命中条目" in MINUTES_SUPERVISOR_PROMPT, "")
    check("审核提示词允许「命中表未命中 → 分工为空」",
          "分工栏为空是允许的" in MINUTES_SUPERVISOR_PROMPT, "")

def test_person_reference_rules() -> None:
    """人名口径（方案③，2026-09-21 定）：本人动作省主语、他人动作写真名、
    待办/提醒/被点名才用「你」，分工与引语一律真名，同句与相邻两句不混用；
    客观与职业模板仍是第三人称、不许出现「你」「您」。

    口径演进：① 起初三处（草稿硬规则 / 渲染纪律 / 审核视角偏差）一律禁止「你」「您」
    → 个人视角读起来与他无关；② 改成"真人正文用第二人称「你」" → 实测同一上下文两次跑
    出来一次「你」37 次、另一次 11 次且与真名混排，读着别扭（本 session 用户反馈）；
    ③ 现在按"中文允许省主语"的口径——叙述本人动作省主语，他人动作写名，只在需要点明
    归属时用「你」。审校三条都同步：允许省主语、拦他人动作缺主语、拦同句混用。
    """
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as GEN,
        MINUTES_RENDER_PROMPT as RENDER,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as REVIEW,
    )

    check("草稿：真人模式本人动作省主语 + 他人动作写真名",
          "本人动作**省主语**" in GEN and "他人动作写真名" in GEN, "")
    check("草稿：不再无条件禁止「你」「您」", "禁止正文「你」「您」" not in GEN, "")
    check("草稿：真人口径段同步（省主语 / 只在该用时用「你」/ 人名照写）",
          "只保留与该姓名直接相关内容" in GEN and "照原文写真名" in GEN
          and "不混用" in GEN, "")
    check("渲染：人名口径四条齐备（省主语 / 真名 / 你 / 不混用）",
          "本人动作省主语" in RENDER and "他人动作写真名" in RENDER
          and "只有待办/提醒/被点名才用「你」" in RENDER
          and "同一句与相邻两句不混用" in RENDER, "")
    check("渲染：不再写「正文用第二人称「你」指代本人」那种全篇「你」的口径",
          "正文用第二人称「你」指代本人" not in RENDER, "")
    check("通顺性：给本人动作省主语开口子（否则被判半截句）",
          "真人模式叙述本人动作时主语可省" in RENDER, "")
    check("审核：客观/职业模板出现「你」「您」仍要拦",
          "**客观/职业模板**正文出现「你」「您」" in REVIEW, "")
    check("审核：真人模式把分工/责任人写成「你」要拦",
          "真人模式把分工/责任人/引语里的人名写成「你」" in REVIEW
          and "真名要保真" in REVIEW, "")
    check("审核：新增两条——他人动作缺主语、同句混用都要拦",
          "真人模式他人动作缺主语" in REVIEW and "混用「你」与真名" in REVIEW, "")

def test_assignment_scope_rules() -> None:
    """分工范围：真人档只列他的条目，客观/职业模板仍按分工条数（2026-09-21 收紧）。

    根因（实测分工栏里带出武思华/范炳杰/盛晋珲的条目）：不是模型不听话，是契约就这么写的——
    ``personally_relevant_points`` 的字段说明与提示词都写「条数 = 有明确责任人 + 明确职责的
    分工数」，通篇没限定本人；草稿照契约列了全场分工，渲染只是照抄。所以四处一起收：
    ① 契约字段说明 ② 提示词字段小节 ③ 草稿真人视角段 ④ 审核一条（渲染后没有审核环节，
    那一侧只能靠纪律，见 test_render_view_directive）。
    """
    from domains.meeting.tasks.minutes.contracts import MINUTES_GENERATION_OUTPUT_CONTRACT
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as GEN,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as REVIEW,
    )

    check("契约：真人模式草稿即产出组名行（与我相关 / 每位他人一行）；客观口径不变",
          "先给一个组名元素 `**与我相关**：`" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "他人每位各给一个组名元素 `**姓名**：`" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "条目不重复姓名" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "确需他配合的合并成一句" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "客观/职业模板按有明确责任人的分工条数写" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：结论与决定同口径分组（本人「与我相关」/ 他人「姓名」/ 无归属平铺）",
          "key_decisions" in MINUTES_GENERATION_OUTPUT_CONTRACT  # 字段名在契约里
          and "**上游 decisions 是纯文本、没有归属，要对照会议原文补出归属**"
          in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "归属本人的先写一行 `**与我相关**：` 再列其条目" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "归属他人的写一行 `**姓名**：` 再列其条目" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：同为决策的写法不再用「我的事项」旧名（三栏统一组名）",
          "我的事项" not in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    # 旧组名漂移守护：组名只在「与我相关」一处口径里——任何一份 prompt 源文件残留
    # 「我的事项」都会让模型在旧名/新名之间二选一（上次的教训：两处口径打架，模型照旧的写）。
    stale_group = [
        str(path)
        for path in (
            Path("domains/meeting/tasks/minutes/contracts.py"),
            Path("domains/meeting/tasks/minutes/prompts.py"),
            Path("domains/shared/perspective/preferences.py"),
            Path("domains/shared/perspective/hits.py"),
            Path("core/templates/body_rules.py"),
        )
        if "我的事项" in path.read_text(encoding="utf-8")
    ]
    check("旧组名「我的事项」已在全部 prompt 源文件清除", not stale_group, f"残留={stale_group}")
    check("契约：风险/未决「有明确归属才分组」，分组写法自述；客观口径保留",
          "风险（客观全量" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "**有明确归属才分组**" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "**分组写法**：" in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "看不出归属的不写姓名、平铺在最前" in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("契约：不再用「与某栏一致」的交叉引用（换模板/改栏名也不会被带偏）",
          "与行动项一致" not in MINUTES_GENERATION_OUTPUT_CONTRACT
          and "与风险栏一致" not in MINUTES_GENERATION_OUTPUT_CONTRACT,
          "")
    check("提示词字段小节：条数口径分档（客观/职业=分工数；真人=命中表里他的待办数）",
          "条数 = 有明确责任人 + 明确职责的分工数**（客观/职业模板）" in GEN
          and "条数 = 命中表里他的待办数）" in GEN
          and "**不写自己的姓名**" in GEN
          and "按姓名分组" in GEN,
          "")
    check("草稿真人视角段：自己的在前不写姓名、他人的带姓名前缀，未命中写 []",
          "不写自己的姓名**" in GEN and "命中表没给他派活时自己的部分写 []" in GEN, "")
    check("审核：两种归属形态都接受，但归属必须可核、组名行须与条目对应",
          "末尾三栏（结论与决定 / 行动项与分工 / 待确认与风险）必须**按人分块**" in REVIEW
          and "组名与组内条目必须对应" in REVIEW
          and "他自己的条目**不得写自己的姓名**" in REVIEW,
          "")
    check("审核：有明确归属却未标出要拦、无归属不加姓名不算缺陷（条件句）",
          "**分工归属（真人模式）**" in REVIEW
          and "有明确归属却未标出" in REVIEW
          and "无归属的全局项不加姓名是允许的" in REVIEW
          and "客观/职业模板按有明确责任人的分工条数写，不按本条拦" in REVIEW,
          "")
    check("审核：正当依赖不算（避免误拦）", "上游出包后才能联调」这类正当依赖不算" in REVIEW, "")
    check("提示词里不留任何真实人名示例（全局提示词不得锚定到某个用户）",
          all(name not in MINUTES_GENERATION_OUTPUT_CONTRACT + GEN + REVIEW
              for name in ("申家坤", "徐玥", "武思华", "陈贺")),
          "")

def test_render_context_personal_injection() -> None:
    """装配那一轮也要拿到命中块/偏好块 + 渲染提示词的"真人聚焦"口径。

    回归背景（2026-09-21 用户实测）：草稿那轮有命中块/偏好块，但**逐栏填充（真正写正文
    的地方）**没有——它看不到"他是谁、他关心什么"，于是把个人视角摊回整场，读起来与
    客观没区别。这里锁住：命中块进所有非客观线、偏好块只进纪要线；渲染提示词写明聚焦口径。
    """
    from domains.meeting.orchestrator import _Nodes
    from domains.meeting.tasks.minutes.prompts import MINUTES_RENDER_PROMPT

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
    for line, want_pref in (("minutes", True), ("minutes_styles", True), ("actions", False), ("risks", False)):
        text = host._render_context(state, line)
        check(f"渲染上下文（{line}）：命中块（非客观线都有）",
              "本用户命中" in text, text[-160:])
        check(f"渲染上下文（{line}）：偏好块 {'有' if want_pref else '不注入'}",
              ("本用户偏好" in text) is want_pref, text[-160:])
    objective = host._render_context({**state, "objective_perspective": True, "user": {"perspective": "objective"}}, "minutes")
    check("渲染上下文（客观）：命中块与偏好块都不注入",
          "本用户命中" not in objective and "本用户偏好" not in objective, "")

    check("渲染提示词：真人模式以本人为叙事主线（非相关板块可压缩）",
          "真人模式聚焦" in MINUTES_RENDER_PROMPT
          and "以本人为叙事主线" in MINUTES_RENDER_PROMPT
          and "可压缩成一句带过" in MINUTES_RENDER_PROMPT, "")
    check("渲染提示词：真人聚焦不得漏全局结论（与审核口径对齐）",
          "影响全局的结论、范围纳入/排除、关键数字仍不得漏" in MINUTES_RENDER_PROMPT, "")
    check("渲染提示词：给了命中表就以它为准",
          "以它为准" in MINUTES_RENDER_PROMPT
          and "未命中的条目不要写成他的事" in MINUTES_RENDER_PROMPT, "")

def test_render_view_directive() -> None:
    """装配那一轮的「本视角纪律」：模板路径正文是通用填充器逐栏写的，纪律必须随栏下发。

    回归背景（2026-09-21 用户第二轮实测「还是整体输出」）：上一版把聚焦规则写进
    ``MINUTES_RENDER_PROMPT``，但**带模板时那条路根本不执行**——逐栏填充的 system 只有
    「你只写本栏正文」，正文只按模板栏名（全文摘要 / 分段速览）走，于是真人模式照样写成
    整场纪要（实测 8172 字、超本篇参考上限 48%，与客观版看不出区别）。这里锁住：
    纪律进每一栏的用户消息、经领域钩子只在真人纪要线生效、客观与其它线一字不变。
    """
    import asyncio

    from domains.meeting.orchestrator import _Nodes
    from domains.shared.perspective import PERSONAL_VIEW_DIRECTIVE, VIEW_DIRECTIVE_TITLE
    from core.templates.router import fill_placeholder_template
    from core.templates.router._placeholder import _column_fill_user

    template = "# 通用纪要\n\n# [全文摘要]\n[一段话概括]\n\n# [要点梳理]\n[分点列具体事实]\n"
    mark = f"【{VIEW_DIRECTIVE_TITLE}】"

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
            stub, "来源", template, source_han=9000, directives=PERSONAL_VIEW_DIRECTIVE
        )
    )
    check("逐栏填充：每一栏的用户消息都带本视角纪律",
          bool(stub.calls) and all(mark in user for _, user in stub.calls),
          str([user.splitlines()[0] for _, user in stub.calls]))
    check("逐栏填充：system 里没有领域渲染提示词（这正是要向用户消息下发纪律的原因）",
          all("真人模式聚焦" not in system for system, _ in stub.calls), "")

    host = _Host()
    personal = {"user": {"name": "申家坤"}}
    check("钩子：真人纪要线（minutes / minutes_styles）→ 有纪律",
          mark in host._render_directives(personal, "minutes")
          and mark in host._render_directives(personal, "minutes_styles"), "")
    check("钩子：客观、非纪要线、职业模板 → 都不注入",
          host._render_directives({**personal, "objective_perspective": True}, "minutes") == ""
          and host._render_directives(personal, "actions") == ""
          and host._render_directives(
              {"user": {"persona_type": "role_template", "name": "开发人员"}}, "minutes"
          ) == "",
          "")

    from domains.shared.perspective import PERSONAL_TEMPLATE_VIEW_DIRECTIVE
    personal_custom = {
        "user": {"name": "申家坤"},
        "templates": {"minutes": "# [本场概况与本人定调]\n[说明]\n"},
    }
    check(
        "钩子：真人模式 + 专属个人模板 → 注入 PERSONAL_TEMPLATE_VIEW_DIRECTIVE",
        host._render_directives(personal_custom, "minutes") == PERSONAL_TEMPLATE_VIEW_DIRECTIVE,
        host._render_directives(personal_custom, "minutes")[:60],
    )
    check(
        "钩子：真人模式 + 通用模板 → 注入通用纪律 PERSONAL_VIEW_DIRECTIVE",
        host._render_directives(personal, "minutes") == PERSONAL_VIEW_DIRECTIVE,
        "",
    )
    check(
        "钩子：客观模式 + 专属个人模板 → 绝不注入（客观纪要 100% 零影响）",
        host._render_directives({**personal_custom, "objective_perspective": True}, "minutes") == "",
        "",
    )

    user = _column_fill_user(
        "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
        others=["要点梳理"], directives=PERSONAL_VIEW_DIRECTIVE,
    )
    check("纪律排在【本栏说明】之后、【内容来源】之前",
          user.index("【本栏说明】") < user.index(mark) < user.index("【内容来源】"), "")
    check("纪律为空 → 不出现该段（客观路径一字不变）",
          mark not in _column_fill_user(
              "来源", template, index=1, total=2, hint="一段话概括", title="全文摘要",
              others=["要点梳理"], directives="",
          ),
          "")
    check("纪律自带优先级：模板写「客观、非人格化」时人称与取舍以纪律为准",
          "人称与取舍以本纪律为准" in PERSONAL_VIEW_DIRECTIVE
          and "栏名、结构与事实口径照模板不变" in PERSONAL_VIEW_DIRECTIVE, "")
    check("纪律含六条硬口径（相关=点名 / 聚焦 / 不漏全局 / 人名口径 / 命中表为准 / 不留空栏）",
          all(
              clause in PERSONAL_VIEW_DIRECTIVE
              for clause in (
                  "相关＝点名，不是「属于他的关注领域」",
                  "以本人为叙事主线",
                  "别人主讲、且与他无关的板块压成一句带过",
                  "关键数字仍**不得漏**",
                  "本人动作省主语",
                  "他人动作写真名",
                  "同一句与相邻两句不混用",
                  "以它为准",
                  "不要留空栏",
                  "已按人裁剪",
              )
          ),
          "")

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
    sliced = host._render_context(state, "minutes")
    check("真人：原文块改标为「已按人裁剪」", "会议原文（真人模式·已按人裁剪）" in sliced, "")
    check("真人：别人的段被折叠（原文里那些长段不见了）",
          "另外引擎那部分我一起讲一下大概情况" not in sliced
          and "这个问题由我来跟，细节我明天说清楚。" not in sliced, "")
    check("真人：他自己的段留下且块首改称「你」",
          "你 00:00:01" in sliced and "我们先过接口这块的对齐情况" in sliced, sliced[:120])
    check("真人：提到他的别人的段也留（引述保真名）",
          "李梦甜 00:01:10" in sliced and "双录还没确认" in sliced, "")
    check("真人：非纪要线（trace/mindmap）不动原文",
          "已按人裁剪" not in host._render_context(state, "minutes_trace"), "")
    check("真人纪要渲染上下文：草稿与用户画像保留", "用户画像" in sliced and "已批准会议纪要草稿" in sliced, "")
    trace_ctx = host._render_context(state, "minutes_trace")
    check("溯源线（trace）：仍保留会议原文供正则回溯证据", "会议原文" in trace_ctx, "")

    objective = host._render_context({**state, "objective_perspective": True}, "minutes")
    check("客观：整篇原文原样、无裁剪标记",
          "已按人裁剪" not in objective and "另外引擎那部分我一起讲一下大概情况" in objective, "")
    check("客观纪要渲染上下文：保留会议原文", "会议原文" in objective, "")

    # 分组骨架块（2026-09-22）：把「要出现哪些组名行」变成可照抄的清单——模型只复制、不重排。
    grid = {**state, "user_action_groups_block": "【本用户分栏分组骨架】\n**与我相关**："}
    check("真人渲染上下文注入「分栏分组骨架」块",
          "**与我相关**：" in host._render_context(grid, "minutes"), "")
    check("客观不注入骨架块（零外溢）",
          "**与我相关**：" not in host._render_context(
              {**grid, "objective_perspective": True}, "minutes"
          ),
          "")
    # 状态通道守护（2026-09-22 真链路事故）：LangGraph 只传 MeetingState 里声明过的 key，
    # 未声明的写入被静默丢掉——骨架块写了，草稿/审核/渲染全程收不到（单元测试注入 dict 掩盖了）。
    from domains.meeting.models import MeetingState

    check("状态通道：视角节点写的块都在 MeetingState 里声明（否则被 LangGraph 丢掉）",
          "user_action_groups_block" in MeetingState.__annotations__
          and "user_hits_block" in MeetingState.__annotations__
          and "user_radar_block" in MeetingState.__annotations__,
          "")
    check("状态通道：视角节点确实写入骨架 key 与雷达 key",
          "user_action_groups_block" in Path("domains/meeting/orchestrator.py").read_text(
              encoding="utf-8"
          ) and "user_radar_block" in Path("domains/meeting/orchestrator.py").read_text(
              encoding="utf-8"
          ),
          "")

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
    check("素材裁剪：别人为主语的条目去掉，他的与无人称全局事实都留",
          len(trimmed_pack["topics"][0]["key_points"]) == 2
          and "长文本实测 8~9 万字不行" in trimmed_pack["topics"][0]["key_points"][0]
          and "申家坤回去改配置" in trimmed_pack["topics"][0]["key_points"][1],
          str(trimmed_pack["topics"][0]["key_points"]))
    check("素材裁剪：decisions / risks 不动（全局结论与风险仍进上下文）",
          trimmed_pack["decisions"] == ["930 前至少单卡四路"]
          and trimmed_pack["risks"] == ["武思华找对方批权限一直不批"], "")
    check("素材裁剪：别人为主的「议题讨论经过」同样去掉（2026-09-22 追加）",
          trimmed_pack["topics"][0]["discussion"] == ""
          and trimmed_pack["topics"][1]["discussion"] == "申家坤讲了长文本实测情况，其他人补充",
          f"{[tp.get('discussion') for tp in trimmed_pack['topics']]}")
    check("素材裁剪：客观档与职业模板都不裁（原样返回，含讨论经过）",
          len(host._person_pack(pack, {**pack_state, "objective_perspective": True})["topics"][0]["key_points"]) == 4
          and host._person_pack(
              pack, {**pack_state, "objective_perspective": True}
          )["topics"][0]["discussion"].startswith("武思华提出")
          and len(host._person_pack(
              pack, {**pack_state, "user": {"name": "开发人员", "persona_type": "role_template"}}
          )["topics"][0]["key_points"]) == 4, "")

    role = host._render_context(
        {**state, "user": {"name": "开发人员", "persona_type": "role_template"}}, "minutes"
    )
    check("职业模板：没有真人姓名可裁 → 走整篇",
          "已按人裁剪" not in role, "")

    check("裁不动时退回空串（调用方用整篇）：无关姓名",
          host._person_transcript({**state, "user": {"name": "查无此人"}}) == "", "")

def test_column_extraction_robustness_and_timeout() -> None:
    """分栏抽取宽容度与自适应超时容限测试：
    1. 首行多写标题自动去皮（# 标题、## 标题：、**标题**：、【标题】均安全剥离）
    2. 正文正常列表与加粗条目不被误剥离
    3. 模板拼装阶段单标题保证
    4. clean_template_render_text 剔除相邻同名冗余标题行
    5. empty_section_issues 豁免相邻同名标题不报空栏
    6. _stream_column 能够透传 timeout 参数给底层 stream_text
    """
    import asyncio
    from core.templates.router._placeholder import (
        _strip_redundant_column_heading,
        assemble_placeholder_output,
        _stream_column,
    )
    from core.execution.gate import (
        clean_template_render_text,
        empty_section_issues,
    )

    # 1. 首行多写各种标题变体
    c1 = _strip_redundant_column_heading("## 核心政策：\n1. 积极的财政政策\n2. 稳健的货币政策", "核心政策")
    check("首行 ## 标题： 自动剥离", c1 == "1. 积极的财政政策\n2. 稳健的货币政策", f"c1={c1}")

    c2 = _strip_redundant_column_heading("# 核心政策\n\n1. 积极的财政政策", "核心政策")
    check("首行 # 标题 自动剥离（含紧随空行）", c2 == "1. 积极的财政政策", f"c2={c2}")

    c3 = _strip_redundant_column_heading("**核心政策**：\n- 措施一\n- 措施二", "核心政策")
    check("首行 **标题**： 自动剥离", c3 == "- 措施一\n- 措施二", f"c3={c3}")

    c4 = _strip_redundant_column_heading("【核心政策】\n1. 措施一", "核心政策")
    check("首行 【标题】 自动剥离", c4 == "1. 措施一", f"c4={c4}")

    # 2. 正常正文不误剥离
    c5 = _strip_redundant_column_heading("1. 积极推进核心政策的落地与执行。", "核心政策")
    check("正文正常句子包含栏名不被误剥离", c5 == "1. 积极推进核心政策的落地与执行。", f"c5={c5}")

    c6 = _strip_redundant_column_heading("- **核心政策**：本年度持续优化营商环境。", "核心政策")
    check("正文行首列表项不被误剥离", c6 == "- **核心政策**：本年度持续优化营商环境。", f"c6={c6}")

    # 3. 模板拼装阶段单标题保证
    tpl = "# 政府报告\n\n# [核心政策]\n[写核心政策]\n\n# [重点工作]\n[写重点工作]\n"
    fields = {
        "1": "## 核心政策：\n1. 财政支持加力",
        "2": "**重点工作**\n1. 推进产业升级",
    }
    assembled = assemble_placeholder_output(tpl, fields)
    check("assemble_placeholder_output 自动净化首行冗余标题",
          "## 核心政策" not in assembled and "**重点工作**" not in assembled
          and "# 核心政策" in assembled and "1. 财政支持加力" in assembled
          and "# 重点工作" in assembled and "1. 推进产业升级" in assembled,
          f"assembled={assembled}")

    # 4. clean_template_render_text 剔除相邻同名冗余标题行
    dirty = "# 核心政策\n## 核心政策：\n1. 财政支持加力\n"
    cleaned, notes = clean_template_render_text(dirty)
    check("clean_template_render_text 剔除相邻同名冗余标题",
          "## 核心政策" not in cleaned and "# 核心政策" in cleaned and "1. 财政支持加力" in cleaned,
          f"cleaned={cleaned}, notes={notes}")

    # 5. empty_section_issues 豁免相邻同名标题不报空栏
    raw_dup = "# 核心政策\n# 核心政策\n1. 财政支持加力\n"
    issues = empty_section_issues(raw_dup, tpl)
    check("empty_section_issues 豁免相邻同名标题不报空栏",
          not any("核心政策" in is_ for is_ in issues),
          f"issues={issues}")

    # 6. _stream_column 能够透传 timeout 参数与采样惩罚参数
    class MockStreamClient:
        def __init__(self):
            self.passed_kwargs = {}
        async def stream_text(self, system, user, **kwargs):
            self.passed_kwargs = kwargs
            yield "测试内容"

    client = MockStreamClient()
    out = asyncio.run(_stream_column(client, "user", cap=1000, ceiling=2000, label="test", timeout=95.0, presence_penalty=0.15, temperature=0.35))
    check("_stream_column 成功透传 timeout 与采样惩罚参数",
          client.passed_kwargs.get("timeout") == 95.0
          and client.passed_kwargs.get("presence_penalty") == 0.15
          and client.passed_kwargs.get("temperature") == 0.35
          and out == "测试内容",
          f"{client.passed_kwargs}")

    # 7. 清单/重点工作栏目前置注入【要点纪律】，普通栏目不注入
    from core.templates.router._placeholder import _column_fill_user, plan_placeholder_fill, fill_placeholder_by_columns
    u_work = _column_fill_user("context", "# [重点工作]\n[写工作]", index=1, total=1, hint="", title="重点工作", others=[])
    check("重点工作栏目提示词前置注入要点纪律", "【要点纪律】" in u_work and "严禁循环复述" in u_work, f"{u_work}")
    u_time = _column_fill_user("context", "# [会议时间]\n[写时间]", index=1, total=1, hint="", title="会议时间", others=[])
    check("普通非清单栏目不注入要点纪律", "【要点纪律】" not in u_time, f"{u_time}")

    # 8. fill_placeholder_by_columns 对重栏目首轮施加 presence_penalty=0.15
    class _CaptureStreamClient:
        def __init__(self):
            self.calls = []
        async def stream_text(self, system, user, **kwargs):
            self.calls.append(kwargs)
            yield "1. 扎实推进产业创新升级。\n2. 深入实施绿色低碳转型。"

    tpl_heavy = "# 政府工作\n\n# [重点工作]\n[写重点工作]\n"
    plan_heavy = plan_placeholder_fill(tpl_heavy)
    cap_client = _CaptureStreamClient()
    # 只取副作用（填充 cap_client.calls），返回值本身不用
    asyncio.run(fill_placeholder_by_columns(cap_client, "context", tpl_heavy, plan_heavy))
    check("重点工作首轮调用自动配置 presence_penalty=0.15",
          len(cap_client.calls) > 0 and cap_client.calls[0].get("presence_penalty") == 0.15,
          f"{cap_client.calls}")

    # 9. LLMClient._stream_sync 序列化 presence_penalty 与 frequency_penalty
    from infra.llm.client import LLMClient
    from unittest.mock import patch, MagicMock
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = [b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n', b'data: [DONE]\n\n']
    captured_req = []
    with patch("urllib.request.urlopen", side_effect=lambda req, timeout=None: (captured_req.append(req), mock_resp)[1]):
        llm = LLMClient(api_key="sk-test", base_url="http://fake.api", model="test-model", provider="openai")
        # 只取副作用（消费生成器以触发 urlopen 并填充 captured_req）
        list(llm._stream_sync([{"role": "user", "content": "hi"}], presence_penalty=0.2, frequency_penalty=0.1))
        import json
        req_body = json.loads(captured_req[0].data.decode("utf-8"))
        check("LLMClient 请求体包含 presence_penalty 与 frequency_penalty",
              req_body.get("presence_penalty") == 0.2 and req_body.get("frequency_penalty") == 0.1,
              f"{req_body}")

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
    check("全 pass 的 revise → 软化为 approve", softened["decision"] == "approve", f"{softened}")
    check("全 pass 的 revise → 标记 revise_downgraded", bool(softened.get("revise_downgraded")), "")
    check("全 pass 的 revise → feedback 清空保契约合法", softened["feedback"] == [], "")
    check("全 pass 的 revise → 原 feedback 保存至 advisory_feedback", len(softened.get("advisory_feedback", [])) == 1, "")

    has_fail_revise = {
        "decision": "revise",
        "feedback": ["数字错误需修正"],
        "facts_check": {"status": "fail", "findings": ["金额 1000 万写成 100 万"]},
        "perspective_check": {"status": "pass", "findings": []},
    }
    kept, note2 = soften_unsubstantial_revise(dict(has_fail_revise))
    check("有 fail 检查项的 revise → 保持 revise 不软化", kept["decision"] == "revise" and note2 is None, f"{kept}")

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
    check("测试用长文本超过 8000 字", len(long_raw) > 8000, f"{len(long_raw)}")

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
    check("长原文客观纪要：打上核心事实与证据摘录标签", "会议原文（核心事实与证据摘录）" in ctx_long, "")
    check("长原文客观纪要：保留草稿核心事实点", "数据库吞吐瓶颈" in ctx_long, "")
    check("长原文客观纪要：裁剪后体积大幅缩减（远小于原长文本）", len(ctx_long) < len(long_raw) * 0.7, f"{len(ctx_long)} vs {len(long_raw)}")

    # 3. 渲染短文本不强制 expand
    from core.runtime.render import _doc_han
    check("短文本原文统计字数正确识别", _doc_han({"transcript": "短会议原文" * 100}) < 5000, "")

def test_court_transcript_template_and_concurrent_fill():
    """验证庭审记录模板增强及多栏+表格解耦并发填充能力。"""
    import asyncio
    import json
    from pathlib import Path
    from core.templates.router._placeholder import (
        fill_placeholder_template,
        plan_placeholder_fill,
        _scalar_titles,
    )

    court_tpl = Path("resources/templates/court_transcript.md").read_text(encoding="utf-8")
    check("庭审记录模板包含证明目的与质证细化规则", "证明目的" in court_tpl and "对方质证意见" in court_tpl, "")
    check("庭审记录模板包含反压缩纪律声明", "不得精简或合并" in court_tpl and "不设字数上限" in court_tpl, "")

    plan = plan_placeholder_fill(court_tpl)
    check("庭审记录模板识别出3个标量栏", len(plan["scalars"]) == 3, f"{len(plan['scalars'])}")
    check("庭审记录模板识别出1个表格行模板", len(plan["row_templates"]) == 1, f"{len(plan['row_templates'])}")
    titles = _scalar_titles(court_tpl)
    check("标量栏目名称正确提取", titles == ["庭审概况", "举证与法庭调查", "庭审结果"], f"{titles}")

    class _MockCourtClient:
        def __init__(self):
            self.stream_calls = []
            self.text_calls = []

        async def stream_text(self, system, user, **kwargs):
            self.stream_calls.append(user)
            if "（庭审概况）" in user:
                yield "本案系原告张某诉被告李某买卖合同纠纷案，由北京市海淀区人民法院依法公开开庭审理。"
            elif "（举证与法庭调查）" in user:
                yield "## 原告举证及被告质证\n- **证据一**：《供货协议书》\n  - **证明目的**：证明双方存在买卖合同关系及约定付款期限。\n  - **对方质证意见**：被告认可协议真实性与签字。\n\n## 法官询问\n- **法官询问**：李某是否已收到货款凭条？\n  - **李某陈述**：李某表示尚未收到原告补寄发票。"
            elif "（庭审结果）" in user:
                yield "合议庭组织双方进行调解，双方均同意庭后协商调解方案。本案宣布休庭。"
            else:
                yield "正文内容"

        async def text(self, system, user, **kwargs):
            self.text_calls.append(user)
            return json.dumps({
                "tables": [
                    [
                        ["原告张某", "判令被告支付货款人民币50万元及逾期利息", "双方签订供货合同且原告已完成交付，被告逾期未付"],
                        ["被告李某", "请求驳回原告诉讼请求", "原告交付货物存在严重质量瑕疵且未开具增值税专用发票"],
                    ]
                ]
            })

    mock_client = _MockCourtClient()
    rendered = asyncio.run(fill_placeholder_template(mock_client, "庭审转写上下文", court_tpl, source_han=6000))
    check("庭审记录并发填充成功产出渲染文本", bool(rendered and len(rendered) > 100), "")
    check("并发调用发生：3次流式标量栏调用", len(mock_client.stream_calls) == 3, f"{len(mock_client.stream_calls)}")
    check("并发调用发生：1次独立表格提取调用", len(mock_client.text_calls) == 1, f"{len(mock_client.text_calls)}")
    check("产出中包含表格当事人与抗辩行", "| 原告张某 |" in rendered and "| 被告李某 |" in rendered, f"{rendered}")
    check("产出中包含举证质证结构化条目", "证明目的" in rendered and "法官询问" in rendered, f"{rendered}")

