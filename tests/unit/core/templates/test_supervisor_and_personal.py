# 拆分自 test_column_projection.py，覆盖：test_supervisor_unavailable_flow, test_supervisor_contract_and_unavailable, test_personal_risk_attribution_in_pack…

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
    expect(line_state.get("degraded") is False, "审核调用失败 → 本线不降级（照常渲染）", f"{line_state.get('degraded')}")
    expect((line_state.get("review") or {}).get("decision") == "approve", "审核调用失败 → 保守 approve", "")
    expect("结构契约" in str(line_state.get("review_unavailable") or ""), "审核调用失败 → 记录原因（供 quality_warning/monitor）", f"{line_state.get('review_unavailable')}")
    expect(bool(out.get("quality_degraded")), "仍标记 quality_degraded（如实提示未做质量把关）", "")
    route = stub._make_route("minutes")
    state_after = {"lines": {"minutes": {"review": line_state["review"], "revision_count": 0}}}
    expect(route(state_after) == "__end__", "路由不再走 fallback（approve → __end__）", f"{route(state_after)}")


def test_supervisor_contract_and_unavailable() -> None:
    """审核契约必填/联动说明 + 审核调用失败时的保守放行取值。"""
    from domains.meeting.tasks.minutes.contracts import MINUTES_SUPERVISOR_OUTPUT_CONTRACT as contract
    from domains.meeting.tasks.minutes.contracts import MinutesSupervisorContract
    from core.graph.nodes import DomainNodes

    expect("所有字段与检查项都必须出现" in contract, "契约说明含「所有字段与检查项都必须出现」", "")
    expect("decision=approve 时检查项必须全 pass" in contract and "reject 必须至少一个检查项 fail" in contract, "契约说明含 decision 联动规则", "")
    expect("仅当 decision=revise 时填写" not in contract and "字段必须出现" in contract, "feedback 说明不再只说「仅当 revise 时填写」", "")
    cfg = {"reject_review": {
        "decision": "reject",
        "feedback": [],
        "facts_check": {"status": "fail", "findings": ["x"]},
        "perspective_check": {"status": "pass", "findings": []},
        "consistency_check": {"status": "fail", "findings": ["y"]},
    }}
    payload = DomainNodes._conservative_review(cfg)
    expect(payload["decision"] == "approve" and payload["feedback"] == []
          and all(payload[k] == {"status": "pass", "findings": []}
                  for k in ("facts_check", "perspective_check", "consistency_check")), "审核不可用 → 保守 approve（检查项全 pass、feedback 空）", f"{payload}")
    expect(bool(MinutesSupervisorContract.checks), "契约仍声明 checks 非空（契约类不变量）", "")


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
    expect(risks[0].startswith("徐玥：") and risks[1].startswith("武思华："), "真人 pack：有归属的风险条目带「姓名：」前缀", str(risks))
    expect(risks[2] == "930 窗口期不多了", "真人 pack：看不出归属的全局风险不加前缀", str(risks))
    expect(pack["open_questions"] == ["合规材料审批何时批下来"], "真人 pack：派生问句（原文没有逐字表述）不硬归人", str(pack["open_questions"]))
    obj = host._meeting_pack({**state, "objective_perspective": True}, "minutes")
    expect(obj["risks"] == understanding["risks"]
          and obj["open_questions"] == understanding["open_questions"], "客观 pack：不加任何前缀（零外溢）", str(obj["risks"]))


def test_personal_no_full_fallback() -> None:
    """P1-10 真人不再"裁空回退全量" + P2-F 命中表进审核上下文与三条检查。

    回归背景：命中块告诉草稿"哪些是他的"、模型照做裁成空（本场确实没他的事），
    但程序 ``subset_upstream_items`` 会把**全员条目**塞回他的视角——"赵衡视角"输出
    全员待办就是这么来的。职业模板保留回退（它更容易整类漏），真人必须选空即空。
    """
    from core.execution.gate import enforce_minutes_draft, subset_upstream_items

    upstream = ["接口联调周五前给测试", "端侧版本下周带上", "数据标注这周归档"]
    expect(subset_upstream_items(upstream, [], fallback_full=False) == [], "真人：选空 → 空（不再回退全量）", "")
    expect(subset_upstream_items(upstream, [], fallback_full=True) == upstream, "职业模板：选空 → 仍回退全量（行为不变）", "")
    expect(subset_upstream_items(upstream, ["端侧版本下周带上"], fallback_full=False)
          == ["端侧版本下周带上"], "真人：选中能对上的 → 只留对上的（上游原序原文）", "")
    expect(subset_upstream_items(upstream, ["完全无关的一句"], fallback_full=False) == [], "真人：一条都对不上 → 空（不回退全量）", "")
    expect(subset_upstream_items(upstream, []) == upstream, "默认参数仍是回退全量（老调用不静默改行为）", "")

    draft = {
        "headline": "进展同步",
        "key_decisions": [],
        "risks_and_blockers": [],
        "unresolved_questions": ["端侧版本下周带上"],
    }
    understanding = {"meeting_purpose": "进展同步", "decisions": ["引擎并发先借资源"],
                     "risks": ["双录还没确认"], "open_questions": ["端侧版本下周带上"]}
    personal = enforce_minutes_draft(dict(draft), understanding, mode="personal")
    expect(personal["key_decisions"] == [] and personal["risks_and_blockers"] == []
          and personal["unresolved_questions"] == ["端侧版本下周带上"], "enforce（真人）：选空的两项是空、选中的对齐上游原文", str(personal))
    role = enforce_minutes_draft(dict(draft), understanding, mode="role_template")
    expect(role["key_decisions"] == ["引擎并发先借资源"] and role["risks_and_blockers"] == ["双录还没确认"], "enforce（职业模板）：选空的两项回退全量", str(role))
    objective = enforce_minutes_draft(dict(draft), understanding, mode="objective")
    expect(objective["key_decisions"] == ["引擎并发先借资源"] and len(objective["risks_and_blockers"]) == 1, "enforce（客观）：三项全量拷贝（与模式判定无关）", "")

    # P2-F：客观审核提示词仍要求分工归口明确
    from domains.meeting.tasks.minutes.prompts import MINUTES_SUPERVISOR_DOMAIN_PROMPT as MINUTES_SUPERVISOR_PROMPT

    expect("personally_relevant_points 条条具备明确责任归口" in MINUTES_SUPERVISOR_PROMPT,
           "审核提示词：分工条目责任归口明确", "")


def test_person_reference_rules() -> None:
    """人名口径：本人动作省主语、他人动作写真名；客观/职业保持第三人称。"""
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_GENERATION_SYSTEM_PROMPT as OBJECTIVE,
        MINUTES_PERSONAL_GENERATION_PROMPT as PERSONAL,
        MINUTES_PERSONAL_SUPERVISOR_PROMPT as REVIEW,
    )

    expect("客观中立第三人称" in PERSONAL, "个人草稿：客观中立第三人称", "")
    expect("本人动作动宾短语开头、省略主语" in PERSONAL and "他人动作保留真实姓名" in PERSONAL,
           "个人草稿：本人动作省主语 + 他人动作写真名", "")
    expect("本人动作动宾短语开头、省略主语" in REVIEW and "他人动作保留真实姓名" in REVIEW,
           "个人审核：人名口径与草稿一致", "")
    expect("客观中立第三人称" in OBJECTIVE, "客观草稿：第三人称", "")


def test_assignment_scope_rules() -> None:
    """分工范围：个人契约/提示词采用本人相关 + 重点协同两组；客观契约按责任人分工。"""
    from domains.meeting.tasks.minutes.contracts import (
        MINUTES_GENERATION_OUTPUT_CONTRACT,
        MINUTES_PERSONAL_GENERATION_OUTPUT_CONTRACT,
    )
    from domains.meeting.tasks.minutes.prompts import (
        MINUTES_PERSONAL_GENERATION_PROMPT as PERSONAL,
        MINUTES_SUPERVISOR_DOMAIN_PROMPT as REVIEW,
    )

    expect("**本人相关**" in MINUTES_PERSONAL_GENERATION_OUTPUT_CONTRACT
          and "**重点协同**" in MINUTES_PERSONAL_GENERATION_OUTPUT_CONTRACT,
          "个人契约：行动分本人相关 / 重点协同两组", "")
    expect("先输出组名行 **本人相关**：" in PERSONAL and "再输出组名行 **重点协同**：" in PERSONAL,
           "个人提示词：组名行顺序固定", "")
    expect("只使用 possible_actions / collaborations" in PERSONAL,
           "个人提示词：行动只来自本人投影", "")
    expect("每条 2–3 句完整句、交代责任人、具体任务、协同对象与交付时限" in MINUTES_GENERATION_OUTPUT_CONTRACT,
           "客观契约：按明确责任人分工写", "")
    expect("personally_relevant_points 条条具备明确责任归口" in REVIEW,
           "审核提示词：分工条目责任归口明确", "")
    expect("我的事项" not in PERSONAL and "我的事项" not in MINUTES_PERSONAL_GENERATION_OUTPUT_CONTRACT,
           "不再使用旧组名「我的事项」", "")
