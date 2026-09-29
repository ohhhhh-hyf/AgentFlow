"""agenda_minutes 字段规范化的特征测试（characterization）：钉住**既有**行为。

来历：这套「新旧字段双向兼容」的规范化写了两遍——``SingleAgendaItemModel`` 的
``__post_init__``/``validate``（管 LLM 单议题输出）与 ``_enforce_agenda_invariants``
（管组装最终条目），两者规则**细节并不相同**。同时 ``_normalize_conclusion_points``
在两处各有一份**逻辑逐字节相同**的拷贝（仅 docstring 不同）：

* ``domain/meeting/tasks/agenda_minutes/steps/agenda_minutes_agent.py``
* ``tools/exports/html/agenda_minutes.py``

``tools/`` 反向依赖 ``domain/`` 是本仓库刻意避免的（见 ``tools/core/domain_hooks.py``
的说明），且这个函数的键表是领域语料词，不适合放进 tools 通用层——所以两份拷贝
**不合并**，改由本测试断言它们输出一致：任何一侧被单独改动都会立刻红。

本套件断言的是「现状」，不表示现状都对。三处分歧已在下方显式标注为已知行为，
其中结论字段的 ``str(list)`` 回环是**已知缺陷**（修复会改变结构化输出，故未动）。

另外附一节 ``test_threshold_constants``：把从散落字面量里抽出的判定阈值常量
（``alignment_engine`` / ``agenda_minutes_agent``）取值钉住——抽取过程不许改数，
将来调参必须一并改测试，从而强迫评估对齐行为。同名不同义的 0.8（人名相似度
vs 匿名占比）刻意保留为两个独立常量，也在此断言不被合并。

用法::

    python -m tests.test_agenda_coercion
"""
from __future__ import annotations

from domain.meeting.tasks.agenda_minutes import alignment_engine
from domain.meeting.tasks.agenda_minutes.agenda_parser import (
    AgendaItemParsed,
    AgendaPlan,
)
from domain.meeting.tasks.agenda_minutes.alignment_engine import (
    AgendaAlignment,
    AlignmentResult,
)
from domain.meeting.tasks.agenda_minutes.steps import agenda_minutes_agent as agent_mod
from domain.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    AgendaMinutesAgent,
    SingleAgendaItemModel,
)
from domain.meeting.tasks.agenda_minutes.steps.agenda_minutes_agent import (
    _normalize_conclusion_points as ncp_agent,
)
from tools.exports.html.agenda_minutes import _normalize_conclusion_points as ncp_exports

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


# ── 输入矩阵 ────────────────────────────────────────────────
NCP_CASES: list[object] = [
    None,
    False,
    "",
    "   ",
    "单一结论",
    [],
    ["a", "b"],
    ["只有一条"],
    ("t1", "t2"),
    {"集合式"},
    "['x', 'y']",
    '["x", "y"]',
    "['只有一项']",
    "['a', 'b', 'c']",
    "通过。生效前置约束：1）补齐材料 2）再上会",
    "同意；反对；弃权",
    "同意;反对;弃权",
    "① 甲 ② 乙 ③ 丙",
    "一是A 二是B 三是C",
    "1. 甲\n2. 乙",
    "(1) 甲 (2) 乙",
    "第一，甲 第二，乙",
    "无其他阻塞",
    "现场无遗留问题",
    "发布前置条件：X。结论通过",
    "现场未决卡点：Y",
    "A。注意事项：B",
    ["a", ["b", "c"]],
    ["", "  ", "d"],
    "混合。1）甲；2）乙",
    "  \n  \n ",
    "['① 甲', '② 乙']",
]


def _item(**kw) -> dict:
    return kw


ITEM_CASES: list[tuple[str, dict]] = [
    ("全新字段", _item(
        target_and_audience=["T"], content_and_evidence=["C"],
        process_and_interaction=["P"], conclusion_and_status="判定",
        action_items=[{"who": "甲"}],
    )),
    ("全旧字段", _item(
        proposal_highlights=["T"],
        deliberation_details={"key_metrics": ["C"], "feedback_concerns": ["P"]},
        resolution="判定", action_commitments=[{"who": "甲"}],
    )),
    ("新旧都填且内容不同", _item(
        target_and_audience=["新T"], proposal_highlights=["旧T"],
        content_and_evidence=["新C"], deliberation_details={"key_metrics": ["旧C"]},
        process_and_interaction=["新P"], conclusion_and_status="新判定", resolution="旧判定",
        action_items=[{"who": "新"}], action_commitments=[{"who": "旧"}],
    )),
    ("空list内容+有dict内容", _item(
        content_and_evidence=[], process_and_interaction=[],
        deliberation_details={"key_metrics": ["dictC"], "feedback_concerns": ["dictP"]},
    )),
    ("内容为dict形态", _item(
        content_and_evidence={"key_metrics": ["mk"], "facts_and_options": ["fo"]},
        process_and_interaction={"feedback_concerns": ["fc"], "focus_debates": ["fd"]},
    )),
    ("结论多点", _item(conclusion_and_status="同意；反对；弃权")),
    ("结论为str_list畸形", _item(resolution="['① 甲', '② 乙']", conclusion_and_status="")),
    ("字段缺失", _item(presenter="汇报人")),
    ("全空", _item()),
]


def _plan() -> AgendaPlan:
    return AgendaPlan(
        meta=type(AgendaPlan().meta)(
            theme="测试主题", date_time="2026-09-29", attendees="甲、乙"
        ),
        items=[
            AgendaItemParsed(seq="01", title="议题一", presenters=["甲"], raw_presenter="甲"),
            AgendaItemParsed(seq="02", title="议题二", presenters=["乙"], raw_presenter="乙"),
        ],
    )


def _alignment(plan: AgendaPlan) -> AlignmentResult:
    return AlignmentResult(
        plan=plan,
        alignments=[
            AgendaAlignment(item=plan.items[0], status="discussed", start_index=0),
            AgendaAlignment(item=plan.items[1], status="skipped", start_index=-1),
        ],
    )


def _enforce_first(data: dict, agent: AgendaMinutesAgent, plan: AgendaPlan) -> dict:
    """按真实管线跑 _enforce，返回序号 01 的条目。"""
    raw = {
        "meeting_meta": {},
        "agenda_items": [{**data, "agenda_seq": "01"}],
        "adhoc_items": [],
    }
    res = agent._enforce_agenda_invariants(raw, _alignment(plan))
    return res["agenda_items"][0]


def test_ncp_copies_agree() -> None:
    """两份 _normalize_conclusion_points 拷贝必须逐字节等价（漂移哨兵）。"""
    bad: list[str] = []
    for case in NCP_CASES:
        a, e = ncp_agent(case), ncp_exports(case)
        if a != e:
            bad.append(f"{case!r}: agent={a!r} exports={e!r}")
    check(
        f"_normalize_conclusion_points 两副本输出一致（{len(NCP_CASES)} 例）",
        not bad,
        "；".join(bad[:3]),
    )


def test_known_shape_rules() -> None:
    """钉住若干有代表性的规范化结果（回归时能指出具体哪条变了）。"""
    check("单条字符串结论归一为单元素列表", ncp_agent("单一结论") == ["单一结论"], repr(ncp_agent("单一结论")))
    check("分号多点结论拆条", ncp_agent("同意；反对；弃权") == ["同意", "反对", "弃权"], repr(ncp_agent("同意；反对；弃权")))
    check("str(list) 畸形被修复", ncp_agent("['x', 'y']") == ["x", "y"], repr(ncp_agent("['x', 'y']")))
    check("带圈号前缀被剥离", ncp_agent("['① 甲', '② 乙']") == ["甲", "乙"], repr(ncp_agent("['① 甲', '② 乙']")))
    check("空/None 归一为空列表", ncp_agent(None) == [] and ncp_agent("") == [], repr(ncp_agent(None)))
    # 噪声条目「无其他阻塞」的丢弃规则是**行首锚定**的（正则 ^），所以：
    #   行首命中 → 丢；同行中段命中 → 保留；单条被丢光 → 末尾 `return cleaned or [s]` 回退原串。
    # 三种形态都钉住（其中"单条回退"看起来是笔误，但属现状）。
    check("噪声行首命中即丢弃", ncp_agent("同意\n无其他阻塞") == ["同意"], repr(ncp_agent("同意\n无其他阻塞")))
    check("噪声非行首不丢弃", ncp_agent("同意。无其他阻塞") == ["同意。无其他阻塞"], repr(ncp_agent("同意。无其他阻塞")))
    check("★噪声单条被丢光后回退原串（去噪失效）", ncp_agent("无其他阻塞") == ["无其他阻塞"], repr(ncp_agent("无其他阻塞")))
    check("分号切分后中段噪声被丢弃", ncp_agent("同意；无其他阻塞；弃权") == ["同意", "弃权"], repr(ncp_agent("同意；无其他阻塞；弃权")))
    check("嵌套列表被展平", ncp_agent(["a", ["b", "c"]]) == ["a", "b", "c"], repr(ncp_agent(["a", ["b", "c"]])))


def test_validate_pins() -> None:
    """钉住 SingleAgendaItemModel.validate 的规范化为（LLM 单议题输出侧）。"""
    by_case = {name: SingleAgendaItemModel.validate(dict(d)) for name, d in ITEM_CASES}

    full_new = by_case["全新字段"]
    check("全新字段：target 原样保留", full_new.target_and_audience == ["T"], repr(full_new.target_and_audience))
    check("全新字段：旧字段被同步回填", full_new.proposal_highlights == ["T"], repr(full_new.proposal_highlights))
    check("全新字段：结论单条归一为字符串", full_new.conclusion_and_status == "判定", repr(full_new.conclusion_and_status))

    old_only = by_case["全旧字段"]
    check("全旧字段：由 deliberation_details 提升", old_only.content_and_evidence == ["C"], repr(old_only.content_and_evidence))
    check("全旧字段：新字段被同步回填", old_only.target_and_audience == ["T"], repr(old_only.target_and_audience))

    both = by_case["新旧都填且内容不同"]
    check("新旧都填：新字段胜出", both.target_and_audience == ["新T"] and both.content_and_evidence == ["新C"], repr(both.target_and_audience))
    check("新旧都填：结论取新值", both.conclusion_and_status == "新判定", repr(both.conclusion_and_status))

    # ★ 已知分歧 1：content 为空 list 且 dict 里有内容时，validate 认定「空 list 就是答案」
    #   （不回落 dict），而 _enforce 认为空 list 等于「没给」并回落 dict。
    empty_list = by_case["空list内容+有dict内容"]
    check(
        "★已知分歧：validate 遇空 list 不回落 dict（content 为空）",
        empty_list.content_and_evidence == [],
        repr(empty_list.content_and_evidence),
    )

    dict_shape = by_case["内容为dict形态"]
    check("内容 dict 形态：key_metrics+facts_and_options 合并", dict_shape.content_and_evidence == ["mk", "fo"], repr(dict_shape.content_and_evidence))


def test_enforce_pins() -> None:
    """钉住 _enforce_agenda_invariants 的规范化行为（组装最终条目侧）。"""
    agent = AgendaMinutesAgent(client=None)  # type: ignore[arg-type] 该方法不使用 client
    plan = _plan()

    empty_list = _enforce_first(dict(dict(ITEM_CASES)[("空list内容+有dict内容")]), agent, plan)
    check(
        "★已知分歧：_enforce 遇空 list 回落 dict（content 取到 dictC）",
        empty_list["content_and_evidence"] == ["dictC"],
        repr(empty_list["content_and_evidence"]),
    )

    missing = _enforce_first({}, agent, plan)
    check(
        "★已知分歧：_enforce 对缺失 target 注入默认议题串",
        missing["target_and_audience"] == ["既定议题审议：议题一"],
        repr(missing["target_and_audience"]),
    )

    multi = _enforce_first(dict(dict(ITEM_CASES)[("结论多点")]), agent, plan)
    check(
        "★已知分歧：_enforce 的结论恒为字符串（不拆条）",
        multi["conclusion_and_status"] == "同意；反对；弃权",
        repr(multi["conclusion_and_status"]),
    )

    skipped = agent._enforce_agenda_invariants(
        {"meeting_meta": {}, "agenda_items": [], "adhoc_items": []},
        _alignment(plan),
    )["agenda_items"][1]
    check("未讨论议题零证据置空", skipped["status_tag"] == "本次未讨论" and skipped["content_and_evidence"] == [], repr(skipped))


def test_conclusion_str_list_round_trip() -> None:
    """★已知缺陷：validate 修好的结论被 _enforce 的 str() 变回 repr 字符串。

    真实管线是 validate → extracted → _enforce，所以列表型结论会在最后一步被
    ``str(list)`` 写成 ``"['甲', '乙']"``。用户可见的 Markdown 没事（渲染层
    ``_safe_str`` 会再规范化一次），但**结构化的 conclusion_and_status 字段**
    存的是 repr 串，直接消费该字段的下游会拿到畸形值。
    此处钉住现状：修复它会改变结构化输出，属于独立变更，需与产品确认后再做。
    """
    chained = SingleAgendaItemModel.validate(
        {"conclusion_and_status": "同意；反对；弃权"}
    )
    check("validate 后结论为列表", chained.conclusion_and_status == ["同意", "反对", "弃权"], repr(chained.conclusion_and_status))

    agent = AgendaMinutesAgent(client=None)  # type: ignore[arg-type]
    item = _enforce_first(dict(chained.__dict__), agent, _plan())
    check(
        "★已知缺陷：经 _enforce 后结论回落为 repr 字符串",
        item["conclusion_and_status"] == "['同意', '反对', '弃权']",
        repr(item["conclusion_and_status"]),
    )


def test_threshold_constants() -> None:
    """§判定阈值：把抽出的具名常量的**取值**钉住。

    这些常量是从散落的字面量里按语义抽出来的（同一数值可能对应不同语义，见
    alignment_engine 顶部注释）。断言取值 = 断言"抽取过程中没有改数"；将来
    真要调参，必须连同本测试一起改，从而强迫评估对齐行为。
    """
    want = {
        "NAME_MATCH_ACCEPT": (alignment_engine.NAME_MATCH_ACCEPT, 0.8),
        "NAME_MATCH_EXACT": (alignment_engine.NAME_MATCH_EXACT, 1.0),
        "_ANON_RATIO_FOR_CONTENT_TRACK": (alignment_engine._ANON_RATIO_FOR_CONTENT_TRACK, 0.8),
        "_HUB_SPEAKER_BLOCK_MIN": (alignment_engine._HUB_SPEAKER_BLOCK_MIN, 25),
        "_SWITCH_ENTER_SCORE": (alignment_engine._SWITCH_ENTER_SCORE, 3.0),
        "_SWITCH_FORCE_SCORE": (alignment_engine._SWITCH_FORCE_SCORE, 4.5),
        "_SWITCH_MARGIN": (alignment_engine._SWITCH_MARGIN, 2.0),
        "_CONFLICT_SCORE": (alignment_engine._CONFLICT_SCORE, 2.0),
        "_SUSTAIN_SCORE": (alignment_engine._SUSTAIN_SCORE, 1.0),
        "_IN_AGENDA_CONFLICT_SCORE": (alignment_engine._IN_AGENDA_CONFLICT_SCORE, 2.5),
        "_RESUME_SCORE": (alignment_engine._RESUME_SCORE, 2.0),
        "_DUAL_SPEAKER_SHORT_CHARS": (alignment_engine._DUAL_SPEAKER_SHORT_CHARS, 100),
        "_NOISE_SHORT_CHARS": (alignment_engine._NOISE_SHORT_CHARS, 30),
        "_EVIDENCE_CHAR_BUDGET": (agent_mod._EVIDENCE_CHAR_BUDGET, 12000),
        "_TYPE_DETECT_TRANSCRIPT_CHARS": (agent_mod._TYPE_DETECT_TRANSCRIPT_CHARS, 5000),
        "_ITEM_MAX_TOKENS": (agent_mod._ITEM_MAX_TOKENS, 2000),
        "_DEFAULT_CONCURRENCY": (agent_mod._DEFAULT_CONCURRENCY, "4"),
    }
    bad = [f"{k}={got!r}(期望{exp!r})" for k, (got, exp) in want.items() if got != exp]
    check(f"判定阈值常量取值未改（{len(want)} 项）", not bad, "；".join(bad))

    # NAME_MATCH_ACCEPT 与 _ANON_RATIO_FOR_CONTENT_TRACK 取值相同但**必须**是两个语义，
    # 这里断言它们确实是两个独立对象（合并成一个会掩盖"人名的0.8"与"占比的0.8"的区别）
    check(
        "同名不同义的常量未被合并",
        alignment_engine.NAME_MATCH_ACCEPT == alignment_engine._ANON_RATIO_FOR_CONTENT_TRACK == 0.8,
        "",
    )


def main() -> int:
    test_ncp_copies_agree()
    test_known_shape_rules()
    test_validate_pins()
    test_enforce_pins()
    test_conclusion_str_list_round_trip()
    test_threshold_constants()
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
