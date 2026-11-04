# 拆分自原大文件，保留：test_minutes_chain_consistency, test_understanding_trim_lists, test_overview_cap_and_column_scope…

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
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as supervisor,
    )
    from core.templates.body_rules import BODY_FORMAT_RULES
    from core.templates.template_prompt import PLACEHOLDER_RULES

    # ③ 形态单点化：渲染路径逐字包含同一份规则（草稿已解耦）
    for label, text in (
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
    ):
        expect(BODY_FORMAT_RULES in text, f"{label} 逐字包含 BODY_FORMAT_RULES（单点维护）", "")
    expect(BODY_FORMAT_RULES not in draft, "纪要草稿已与排版规则解耦（不包含 BODY_FORMAT_RULES）", "")
    expect("人名不作标题" in BODY_FORMAT_RULES
          and "按人分组用独占一行 `**姓名**：`" in BODY_FORMAT_RULES
          and "本人组用 `**与我相关**：`" in BODY_FORMAT_RULES, "形态单点：人分组用 `**姓名**：` 独占行、本人组叫「与我相关」、不把人名写成标题", "")
    expect("单条包含多个维度时用 2 空格 `  - ` 展开" in BODY_FORMAT_RULES, "形态单点：单条多维度用二级缩进", "")
    stale = ["每栏至少 2 个分类标签", "每条 20–80 字", "每条 2–3 处（分类标签"]
    hit = [k for k in stale if any(k in t for t in (PLACEHOLDER_RULES, draft))]
    expect(not hit, "旧形态口径已从全部路径清除", f"残留={hit}")

    # ② 摘要分段：三处同一套（段数按内容、单段 ≤约 200 字——**只按字数口径**），旧数字已清除
    expect("≤4 段" not in draft and "≤4 段" not in gen_contract, "草稿 prompt / 契约都不再设固定段数上限", "")
    expect("250–350 字" in draft and "段数按实际业务模块划分" in gen_contract
          and "3 句或约" not in draft and "3 句或约" not in gen_contract,
          "草稿 prompt / 契约：摘要按字数约束，段数按实际业务模块划分", "")

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
    expect(_PARA_REQUIRE_HAN < _PARA_SPLIT_HAN <= _PARA_CHECK_HAN
          and _ITEM_REQUIRE_HAN < _ITEM_CHECK_HAN, "三层数字有序：要求线 < 拆分线 ≤ 检查线（段落）／要求线 < 检查线（条目）", f"段落 {_PARA_REQUIRE_HAN}/{_PARA_SPLIT_HAN}/{_PARA_CHECK_HAN}，条目 {_ITEM_REQUIRE_HAN}/{_ITEM_CHECK_HAN}")
    expect(_PARA_CHECK_HAN == int(_PARA_REQUIRE_HAN * _CHECK_RATIO)
          and _PARA_SPLIT_HAN == int(_PARA_REQUIRE_HAN * _SPLIT_RATIO)
          and _ITEM_CHECK_HAN == int(_ITEM_REQUIRE_HAN * _CHECK_RATIO), "检查线/拆分线由要求线派生（不再硬编码 320/200）", "")
    expect(f"不超过约 {_PARA_REQUIRE_HAN} 字" in BODY_FORMAT_RULES
          and f"单条不超过约 {_ITEM_REQUIRE_HAN} 字" in BODY_FORMAT_RULES, "prompt 里的要求线与代码常量一致（单一来源，必须同时改）", "")
    from core.execution.gate import advisory_issues as _adv
    expect(_adv.__kwdefaults__.get("para_han") == _PARA_CHECK_HAN
          and _adv.__kwdefaults__.get("long_han") == _ITEM_CHECK_HAN, "advisory 阈值取自派生常量（默认值不再硬编码）", "")
    expect("段数按实际业务模块划分" in gen_contract, "契约声明段数按实际业务模块划分", "")
    old_summary = [
        k
        for k in ("全篇 2–8 条", "每段最多 3 句", "2–8 条", "≤4 段", "每段 2–5 句", "2–5 句")
        if k in draft or k in gen_contract
    ]
    expect(not old_summary, "旧的互斥摘要口径已清除", f"残留={old_summary}")

    # ① 审核范围：只审送审稿中实际出现的内容
    expect("只审送审稿中实际出现的内容" in supervisor, "审核 prompt：只审实际出现的内容", "")


def test_understanding_trim_lists() -> None:
    """理解裁剪：动态契约的 omitted 字段与保留字段互斥，未激活字段物理剔除。"""
    from domains.meeting.meeting_core.contracts import (
        ALL_CORE_FIELD_NAMES,
        build_core_contract_for_tasks,
    )

    cases = (
        ("minutes", {"action_hints", "risk_hints", "dependencies"}),
        ("risks", {"action_hints", "decisions", "dependencies"}),
        ("actions", set()),
    )
    for line, expected_omitted_subset in cases:
        contract_str, omitted = build_core_contract_for_tasks([line])
        for field in omitted:
            expect(f'"{field}"' not in contract_str, f"动态契约-{line}：被裁剪字段 {field} 物理不存在于契约定义中", f"field={field} 出现在 contract 中")
        expect(expected_omitted_subset.issubset(omitted), f"动态契约-{line}：omitted 字段符合预期", f"omitted={sorted(omitted)}")
        expect(omitted.issubset(ALL_CORE_FIELD_NAMES), f"动态契约-{line}：omitted 属于 ALL_CORE_FIELD_NAMES", f"extra={sorted(omitted - ALL_CORE_FIELD_NAMES)}")
    contract_full, omitted_empty = build_core_contract_for_tasks([])
    expect(omitted_empty == frozenset(), "全量契约时 omitted 为空", str(omitted_empty))


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
    expect("只写一段完整概括" in plain and "不超过 400 字" in plain, "首栏（概括·无尺寸）拿到「只写一段」口径与 400 上限", f"{plain[:80]}")
    expect(not any(k in plain for k in ("谁/什么场合", "覆盖哪几块", "以分享为主")), "首栏（概括·无尺寸）不套硬编码会议要素（避免非例会语义打架）", f"{plain[:120]}")
    expect("本栏不复述" in plain and "归各自栏目" in plain, "首栏（概括·无尺寸）带「本栏不复述」边界", f"{plain[:80]}")
    non_first = _describe_field(2, _parse_field("一段话概括参与方、沟通主题与目的、达成的结果"))
    expect("单栏上限 400 字" in non_first and "单段写完" in non_first, "非首栏概括栏统一为单段上限 400 字（不要求下限）", f"{non_first[:80]}")
    # 首栏自称"交代…"并已自列要素（就医/宣讲/研讨）：补下限口径，但不套会议专用四要素
    authored = _describe_field(
        1, _parse_field("一段话交代患者基本信息、就诊科室与时间、本次就诊的核心主诉与初步判断")
    )
    expect("只写一段完整概括" in authored and "按本栏说明把要素交代完整" in authored, "自述要素的首栏拿到下限口径（只写一段）", f"{authored[:100]}")
    expect("以分享为主" not in authored and "谁/什么场合" not in authored, "自述要素的首栏不套会议专用四要素（避免语义打架）", f"{authored[:100]}")

    # ② 自己声明了尺寸的概括栏：以模板为准，不叠加默认上限
    sized = _describe_field(1, _parse_field("一段话概括：先写这段文本是什么；**单段不超过约 200 字**，信息多就拆段"))
    expect("不超过 400 字" not in sized and "本栏不复述" in sized, "已声明尺寸的概括栏不被叠加默认上限", f"{sized[:90]}")

    # ③ 取材来源句（「从概况与原文提取下一步」）不算概括栏，不给概况规格
    ref = _describe_field(
        2, _parse_field("**从概况与原文提取下一步**（不要因为已写进风险表就不写）：核心交付物、验收标准")
    )
    expect("400 字" not in ref, "取材来源句不被误判为概括栏", f"{ref[:80]}")

    # ④ 规则层：自由渲染、共用形态规则都写了这份口径
    for label, text in (
        ("自由渲染 PLACEHOLDER_RULES", PLACEHOLDER_RULES),
        ("共用形态规则", BODY_FORMAT_RULES),
    ):
        expect("最多 3 段、每段不超过 400 字" in text or "单段不超过 400 字" in text, f"{label}：概括栏上限口径到位", "")
    expect("模板显式栏位上限 > 本动态总预算 > 默认形态规则" in budget_line(5000), "篇幅优先级明确（模板栏位上限不被动态预算覆盖）", "")


def test_enum_normalize_fallback() -> None:
    """形态标签已彻底解绑：MeetingUnderstanding 不再强依赖 scene 粗粒度标签。"""
    from dataclasses import fields as dc_fields
    from domains.meeting.models_generated import MeetingUnderstanding
    from domains.meeting.meeting_core import prompts as core_prompts

    field_names = {f.name for f in dc_fields(MeetingUnderstanding)}
    expect("scene" not in field_names, "理解层模型：已彻底解绑 scene 字段", f"{field_names}")

    text = "\n".join(
        str(getattr(core_prompts, name))
        for name in dir(core_prompts)
        if name.isupper() and isinstance(getattr(core_prompts, name), str)
    )
    expect("只能填这 7 个值之一" not in text, "理解 prompt：已移除 scene 7 个枚举的死板限制", "")


def test_scene_hint_from_template() -> None:
    """scene_hint 补丁已彻底拔除：编排层不再强行覆盖模型输出。"""
    src = Path("domains/meeting/orchestrator.py").read_text(encoding="utf-8")
    expect("scene_hint" not in src, "编排层：不再导入 scene_hint", "")
    expect('data["scene"] = hint' not in src, "编排层：不再有 scene 暴力覆盖代码", "")


def test_allow_missing_on_trimmed_fields() -> None:
    """单线裁剪字段允许缺键：模型把"输出 []"理解成"键不用写"时不再白跑一轮重试。

    回归背景（2026-09-18 15:51 实测）：单线 minutes 会裁剪 risk_hints，裁剪指令写的是
    "输出空数组 []"，但模型常把整个键省掉 → 契约要求字段集合完全一致 →
    `结构化校验失败` → 针对性重试一次（+20s，第二次才把键补上）。
    """
    import json
    from dataclasses import fields as dc_fields

    from infra.llm.client import LLMClient
    from domains.meeting.models_generated import MeetingUnderstanding

    base = {
        f.name: ("一段话" if "list" not in str(f.type) else [])
        for f in dc_fields(MeetingUnderstanding)
    }
    trimmed = {k: v for k, v in base.items() if k != "speakers"}

    out = LLMClient._parse_and_validate(
        json.dumps(trimmed), MeetingUnderstanding, frozenset({"speakers"})
    )
    expect(out.speakers == [], "裁剪字段缺键时补默认 []（不再抛错重试）", f"{out.speakers}")
    # 列表字段在模型层统一补默认值；字符串字段缺键仍严格报错。
    no_purpose = {k: v for k, v in base.items() if k != "meeting_purpose"}
    try:
        LLMClient._parse_and_validate(json.dumps(no_purpose), MeetingUnderstanding)
        failed = False
    except Exception:  # noqa: BLE001
        failed = True
    expect(failed, "非裁剪的字符串字段缺键仍严格报错", "")

    with_extra = dict(base)
    with_extra["unknown_field"] = "x"
    out_extra = LLMClient._parse_and_validate(json.dumps(with_extra), MeetingUnderstanding)
    expect(isinstance(out_extra, MeetingUnderstanding) and not hasattr(out_extra, "unknown_field"), "模型输出未声明顶层字段时自动清洗放行（不抛错重试）", "")

    from core.execution.hard_execution import enforce_upstream_carry, MINUTES_CARRY_MAP

    degraded_draft = {
        "headline": "进展同步",
        "key_decisions": ["自研模型按期上线"],
        "risks_and_blockers": ["显存不足需要切分"],
    }
    preserved = enforce_upstream_carry(degraded_draft, {}, MINUTES_CARRY_MAP)
    expect(preserved["key_decisions"] == ["自研模型按期上线"]
          and preserved["risks_and_blockers"] == ["显存不足需要切分"], "上游理解为空时保留草稿已有决议与风险（不暴力抹除）", "")

    src = Path("domains/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    expect("allow_missing=missable" in src and 'missable = {"speakers"}' in src
          and "missable = missable | omitted" in src, "理解 agent：把裁剪集合 + speakers 传给 allow_missing", "")


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
        expect(all(getattr(out, k) == [] for k in blanks) and fake.calls == 1, f"裁剪字段缺键不报错、一次调用成功（{line} 线：{sorted(skip)}）", f"calls={fake.calls}")
    expect(set(UNDERSTANDING_SKIP_FIELDS) == {"minutes", "actions", "risks"}, "裁剪集合覆盖 minutes/actions/risks 三条线", "")

    src = Path("domains/meeting/meeting_core/meeting_understanding_agent.py").read_text(encoding="utf-8")
    expect("allow_missing=missable" in src and 'missable = {"speakers"}' in src
          and "missable = missable | omitted" in src,
          "理解 agent：同一裁剪集合既写进指令也传给 allow_missing（speakers 常空、缺键不算错）", "")
    node_src = Path("domains/meeting/orchestrator.py").read_text(encoding="utf-8")
    expect("skip_fields_for_template" not in node_src
          and '"skip_fields": skip' in node_src, "理解裁剪只按选线，不再按模板栏位", "")


def test_template_no_longer_affects_understanding_skip() -> None:
    """minutes 单线：理解层只按选线裁剪，模板栏位不再参与。

    背景：旧逻辑按模板关键词跳过 risks/open_questions，英文模板会全部误判，
    且模板没有风险栏不代表最终纪要不需要这些事实。现已移除模板关键词层。
    """
    from domains.meeting.meeting_core.contracts import build_core_contract_for_tasks
    from domains.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS, _Nodes

    base = set(UNDERSTANDING_SKIP_FIELDS["minutes"])
    expect({"action_hints", "risk_hints", "dependencies"} <= base, "minutes 基础裁剪带走 action_hints/risk_hints/dependencies", f"{sorted(base)}")

    d = _active_dir()

    def load(name: str) -> str:
        return (d / f"{name}.md").read_text(encoding="utf-8")

    def skip_of(names: list[str], tpl: str = "") -> frozenset[str]:
        return _Nodes._understanding_skip(object(), names, tpl)

    mb = load("media_briefing")
    expect(skip_of(["minutes"], mb) == frozenset(base)
        and skip_of(["minutes"], load("general_minutes")) == frozenset(base), "模板不再影响单线 minutes 裁剪", f"{sorted(skip_of(['minutes'], mb))}")
    expect(skip_of(["minutes"], "## [Risk Alerts]\\n## [Open Questions]") == frozenset(base), "英文模板不再误跳 risks/open_questions", f"{sorted(skip_of(['minutes'], '## [Risk Alerts]'))}")
    expect(skip_of(["minutes", "actions"], mb) == frozenset({"risk_hints", "dependencies"}), "多线仍按交集裁剪（minutes + actions）", f"{sorted(skip_of(['minutes', 'actions'], mb))}")
    expect(skip_of(["actions"], mb) == UNDERSTANDING_SKIP_FIELDS["actions"], "其它线不受模板影响", "")

    contract_mb, omitted_mb = build_core_contract_for_tasks(["minutes"])
    expect(all(k in contract_mb for k in ("risks", "open_questions"))
        and not any(k in omitted_mb for k in ("risks", "open_questions")), "minutes 动态契约始终包含 risks/open_questions", f"omitted={sorted(omitted_mb)}")

    # 节点侧：模板变化不再改变 skip；focus/channel 行为保持
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
                    return {"meeting_purpose": "测试"}

            return _Out()

    fake = _FakeAgent()

    class _Host(_Nodes):
        """只借 _Nodes 的方法与状态读取；不跑父类 __init__（不建 LLM 客户端）。"""

        def __init__(self, agent) -> None:
            self.meeting_understanding_agent = agent

    host = _Host(fake)
    node = _Nodes._make_meeting_understanding_node(host, ["minutes"])
    asyncio.run(node({"transcript": "原文略。", "templates": {"minutes": mb}}))
    asyncio.run(node({"transcript": "原文略。"}))
    expect([frozenset(s) for _, s in fake.seen] == [frozenset(base), frozenset(base)], "节点传入的 skip 不随模板变化", f"{[(f, sorted(s)) for f, s in fake.seen]}")
    expect([f for f, _ in fake.seen] == ["minutes", "minutes"], "节点在裁剪非空时仍报线名", "")

    asyncio.run(
        node(
            {
                "transcript": "原文略。",
                "user": {"name": "赵衡", "name_aliases": ["小赵"]},
            }
        )
    )
    expect("赵衡（全称）" in (fake.channel or "") and "小赵" in (fake.channel or ""), "节点把称呼表传给理解层", str(fake.channel))
    asyncio.run(
        node(
            {
                "transcript": "原文略。",
                "user": {"perspective": "objective", "name": "赵衡"},
            }
        )
    )
    expect(not fake.channel, "客观视角不传称呼表", str(fake.channel))
