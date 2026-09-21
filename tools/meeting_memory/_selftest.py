"""会议记忆零 LLM 衡约：身份、不传 project 接续、状态机、时间/场次。

用法::

    python -m tools.meeting_memory._selftest
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from .bind import (
    bind_meeting,
    is_strong_anchor,
    is_weak_project_name,
    pick_project_name,
    project_core,
)
from .extract import MeetingFact, extract_meeting_fact
from .inject import build_memory_context, preview_comparison
from .render import parse_memory_items
from .runtime import persist_after_run, resolve_bind
from .state import rebuild_state, session_index, session_label, update_state
from .store import list_meetings, load_registry, load_state

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        return
    FAIL.append(name if not detail else f"{name} :: {detail}")


def _fact(**kwargs) -> MeetingFact:
    data = {
        "meeting_id": "m_1",
        "time": "2026-09-01",
        "time_source": "user",
        "title": "小艺慧记Agent开发进展阶段复盘",
        "summary": "复盘小艺慧记Agent第一阶段",
        "anchors": ["小艺慧记Agent"],
        "project_candidates": ["小艺慧记Agent"],
        "decisions": ["8月18日前优化 minutes_trace"],
        "open_items": ["是否默认开启记忆引用"],
        "action_items": [{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": "8月19日前"}],
        "risks": ["记忆可解释性不足"],
        "closed_items": [],
        "quotes": [],
    }
    data.update(kwargs)
    return MeetingFact.from_dict(data)


def test_identity_helpers() -> None:
    check(
        "会种尾巴剥到同一核心名",
        project_core("小艺慧记Agent开发进展阶段复盘") == "小艺慧记Agent"
        and project_core("小艺慧记Agent推进会") == "小艺慧记Agent",
        f"{project_core('小艺慧记Agent开发进展阶段复盘')!r}",
    )
    check("中英混合专名是强锚点", is_strong_anchor("小艺慧记Agent"), "")
    check("议题动词短语不是强锚点", not is_strong_anchor("任务目录整理"), "")
    check("议题名是弱项目名", is_weak_project_name("任务目录整理"), "")
    check("混合专名不是弱项目名", not is_weak_project_name("小艺慧记Agent"), "")
    fact = _fact(title="任务目录整理")
    check(
        "抽项目名跳过弱议题、落到混合专名",
        pick_project_name(fact) == "小艺慧记Agent",
        pick_project_name(fact),
    )


def test_bind_explicit_warning() -> None:
    registry = {
        "projects": {
            "foo": {"name": "foo", "aliases": [], "anchors": ["完全无关专名XYZ"]},
        }
    }
    bind = bind_meeting(registry, _fact(), explicit_project="foo")
    check("显式 project 仍是 high", bind.confidence == "high" and bind.mode == "explicit", bind.as_dict())
    check("显式无重叠带 warning", bool(bind.warning), bind.warning)


def test_bind_title_variants() -> None:
    registry = {
        "projects": {
            "xiaoyi": {
                "name": "小艺慧记Agent",
                "aliases": ["小艺慧记Agent开发进展阶段复盘"],
                "anchors": ["小艺慧记Agent"],
            }
        }
    }
    later = _fact(
        meeting_id="m_2",
        title="小艺慧记Agent推进会",
        summary="推进小艺慧记Agent内测",
        anchors=["小艺慧记Agent"],
    )
    bind = bind_meeting(registry, later)
    check(
        "标题换会种仍 high 绑到同一项目",
        bind.is_bound and bind.project_id == "xiaoyi",
        bind.as_dict(),
    )


def test_extract_time_and_actions() -> None:
    understanding = {
        "meeting_purpose": "复盘小艺慧记Agent开发进展",
        "topics": [{"title": "任务目录整理", "key_points": ["已完成目录整理"], "conclusion": None}],
        "decisions": ["8月18日前优化 minutes_trace"],
        "open_questions": ["是否默认开启记忆引用"],
        "risks": ["记忆可解释性不足"],
        "action_hints": [
            {"action": "补齐记忆引用来源字段", "owner": "赵衡", "timing": "8月19日前", "kind": "assignment", "evidence": "赵衡在8月19日前补齐"}
        ],
    }
    empty_time = extract_meeting_fact(understanding, "赵衡：补齐来源。", request_id="r1", time="")
    check("空 time 记为 unknown，不填 now()", empty_time.time == "" and empty_time.time_source == "unknown", empty_time.time)
    stamped = extract_meeting_fact(understanding, "赵衡：补齐来源。", request_id="r1", time="2026-09-01")
    check("传入 time 记为 user", stamped.time == "2026-09-01" and stamped.time_source == "user", "")
    check("action_hints 进入 fact.action_items", any(a["text"] == "补齐记忆引用来源字段" for a in stamped.action_items), str(stamped.action_items))
    check("完成表述进入 closed_items", any("已完成" in x for x in stamped.closed_items), str(stamped.closed_items))
    check("锚点含混合专名核心", "小艺慧记Agent" in stamped.anchors, str(stamped.anchors))


def test_persist_no_project_and_headline(tmp: Path) -> None:
    u1 = {
        "meeting_purpose": "复盘小艺慧记Agent开发进展",
        "topics": [{"title": "任务目录整理", "key_points": [], "conclusion": None}],
        "decisions": ["先把任务目录整理完"],
        "open_questions": ["是否默认开启记忆引用"],
        "risks": ["记忆可解释性不足"],
        "action_hints": [{"action": "补齐记忆引用来源字段", "owner": "赵衡", "timing": "8月19日前"}],
    }
    t1 = "周宁：今天复盘小艺慧记Agent开发进展。赵衡去补齐记忆引用来源字段。"
    persist_after_run(
        tmp, "u1", "", "req_a", t1, {"minutes": {"headline": "小艺一期复盘纪要"}}, u1,
        meeting_time="2026-09-01",
    )
    reg = load_registry(tmp, "u1")
    projects = reg.get("projects") or {}
    check("第一场不传 project 仍建档", len(projects) == 1, str(projects.keys()))
    pid = next(iter(projects))
    name = str(projects[pid].get("name") or "")
    check(
        "项目名是核心专名而非 headline",
        "小艺慧记Agent" in name and "复盘纪要" not in name,
        name,
    )
    rows = list_meetings(tmp, "u1")
    check("jsonl 标题可用 headline 展示", rows and rows[-1].get("title") == "小艺一期复盘纪要", str(rows))
    check("jsonl project_id 不是 headline 的 safe_id", rows[-1].get("project_id") == pid, str(rows[-1].get("project_id")))
    persist_after_run(
        tmp, "u1", "", "req_a", t1, {"minutes": {"headline": "小艺一期复盘纪要"}}, u1,
        meeting_time="2026-09-01",
    )
    check(
        "同一 request_id 重跑覆盖而非双倍场次",
        sum(1 for r in list_meetings(tmp, "u1") if r.get("meeting_id") == "m_req_a") == 1,
        str([r.get("meeting_id") for r in list_meetings(tmp, "u1")]),
    )

    u2 = {
        "meeting_purpose": "推进小艺慧记Agent内测",
        "topics": [{"title": "记忆引用展示", "key_points": [], "conclusion": None}],
        "decisions": ["记忆引用展示放到文末", "是否默认开启记忆引用已完成"],
        "open_questions": [],
        "risks": ["记忆可解释性不足已缓解"],
        "action_hints": [],
    }
    t2 = "周宁：继续推进小艺慧记Agent。记忆引用已缓解可解释性不足的问题。是否默认开启记忆引用已完成。"
    persist_after_run(
        tmp, "u1", "", "req_b", t2, {"minutes": {"headline": "小艺内测推进会"}}, u2,
        meeting_time="2026-09-07",
    )
    reg2 = load_registry(tmp, "u1")
    check("第二场不传 project 不裂成两个项目", len(reg2.get("projects") or {}) == 1, str((reg2.get("projects") or {}).keys()))
    st = load_state(tmp, "u1", pid)
    seq = session_index(list_meetings(tmp, "u1"), pid)
    check("两场都有场次号", {info["seq"] for info in seq.values()} == {1, 2}, str(seq))
    check("有用户时间的场次标签带日期", "2026-09-01" in session_label(seq, "m_req_a"), session_label(seq, "m_req_a"))
    actions = [i for i in (st.get("actions") or []) if isinstance(i, dict)]
    opens = [i for i in (st.get("open_items") or []) if isinstance(i, dict)]
    check("待办写入 actions 且带负责人", any(i.get("owner") == "赵衡" for i in actions), str(actions))
    closed = [i for i in opens + actions if i.get("status") == "done"]
    check("关闭是改状态而不是删除", bool(closed) or any("记忆引用" in str(i.get("text")) and i.get("status") == "done" for i in opens + actions), str(opens + actions))
    risks = [i for i in (st.get("risks") or []) if isinstance(i, dict)]
    check("风险本场缓解 → mitigated", any(i.get("status") == "mitigated" for i in risks), str(risks))
    ctx, comparison = build_memory_context(
        project_id=pid,
        project=projects[pid],
        state=st,
        bind=type("B", (), {"evidence": ["test"]})(),
        meetings=list_meetings(tmp, "u1"),
        current_fact=_fact(title="小艺慧记Agent周会", summary="继续", anchors=["小艺慧记Agent"]),
    )
    check("注入使用第N场而不是 meeting_id 当展示", "第1场" in ctx or "第2场" in ctx, ctx[:400])
    check("注入含已闭环或对照素材", "【已闭环】" in ctx or "已闭环" in "\n".join(comparison), ctx[:500])
    items = parse_memory_items(ctx)
    check("新注入格式可被引用解析", len(items) >= 1, str(items))


def test_state_machine() -> None:
    f1 = _fact(meeting_id="m1", time="2026-09-01")
    st = update_state({}, f1, "p1", "小艺慧记Agent")
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        open_items=[],
        action_items=[],
        closed_items=["是否默认开启记忆引用"],
        risks=["记忆可解释性不足已缓解"],
        decisions=["8月18日前优化 minutes_trace"],
    )
    st = update_state(st, f2, "p1", "小艺慧记Agent")
    opens = st.get("open_items") or []
    check(
        "未决关闭后仍保留 done 记录",
        any(i.get("status") == "done" and "记忆引用" in str(i.get("text")) for i in opens),
        str(opens),
    )
    check(
        "决策相似则 reaffirmed 而不是重复追加",
        sum(1 for d in st.get("decisions") or [] if "minutes_trace" in str(d.get("text"))) == 1,
        str(st.get("decisions")),
    )
    f3 = _fact(
        meeting_id="m3",
        time="2026-09-14",
        open_items=[],
        action_items=[],
        closed_items=[],
        risks=["记忆可解释性不足"],
        decisions=[],
    )
    st = update_state(st, f3, "p1", "小艺慧记Agent")
    check(
        "已缓解风险再提 → 重新 active",
        any(i.get("status") == "active" and "可解释" in str(i.get("text")) for i in st.get("risks") or []),
        str(st.get("risks")),
    )
    f4 = _fact(meeting_id="m4", time="2026-09-21", open_items=[], action_items=[], risks=[], decisions=[], closed_items=[])
    f5 = _fact(meeting_id="m5", time="2026-09-28", open_items=[], action_items=[], risks=[], decisions=[], closed_items=[])
    st = update_state(st, f4, "p1", "小艺慧记Agent")
    st = update_state(st, f5, "p1", "小艺慧记Agent")
    # 把「可解释」在 m3 激活后，m4/m5 未再提，应变 dormant
    check(
        "连续两场未提的活跃风险进入 dormant",
        any(i.get("status") == "dormant" for i in st.get("risks") or []),
        str(st.get("risks")),
    )


def test_rebuild_idempotent() -> None:
    meetings = [
        _fact(meeting_id="m1", project_id="p1").as_dict(),
        _fact(meeting_id="m1", project_id="p1", title="覆盖同一场").as_dict(),
    ]
    # jsonl 语义是 replace by id；rebuild 只应见到一场。模拟去重后的列表。
    unique = [meetings[-1]]
    st = rebuild_state(unique, "p1", "小艺")
    check("rebuild 按去重后的场次折叠", len(st.get("recent_meetings") or []) == 1, str(st.get("recent_meetings")))


def test_pending_two_projects(tmp: Path) -> None:
    persist_after_run(
        tmp, "u2", "项目甲", "a1",
        "甲项目周会。锚点AlphaCore。",
        {"minutes": {"headline": "甲周会"}},
        {
            "meeting_purpose": "推进项目甲 AlphaCore",
            "topics": [{"title": "甲进度"}],
            "decisions": ["甲继续"],
            "open_questions": [],
            "risks": [],
            "action_hints": [],
        },
        meeting_time="2026-09-01",
    )
    persist_after_run(
        tmp, "u2", "项目乙", "b1",
        "乙项目周会。锚点BetaCore。",
        {"minutes": {"headline": "乙周会"}},
        {
            "meeting_purpose": "推进项目乙 BetaCore",
            "topics": [{"title": "乙进度"}],
            "decisions": ["乙继续"],
            "open_questions": [],
            "risks": [],
            "action_hints": [],
        },
        meeting_time="2026-09-02",
    )
    reg = load_registry(tmp, "u2")
    check("两个显式项目保持分立", len(reg.get("projects") or {}) == 2, str((reg.get("projects") or {}).keys()))
    ambiguous = extract_meeting_fact(
        {"meeting_purpose": "例会", "topics": [{"title": "例会"}], "decisions": [], "open_questions": [], "risks": []},
        "今天开例会推进工作。",
        request_id="c1",
        time="2026-09-03",
    )
    bind = resolve_bind(reg, ambiguous, "", "u2", list_meetings(tmp, "u2"))
    check(
        "双项目且无专名时不 high 错绑",
        not bind.is_bound,
        bind.as_dict(),
    )


def test_empty_time_sessions() -> None:
    meetings = [
        {"meeting_id": "m_a", "project_id": "p", "time": "", "time_source": "unknown", "title": "A"},
        {"meeting_id": "m_b", "project_id": "p", "time": "2026-09-01", "time_source": "user", "title": "B"},
    ]
    seq = session_index(meetings, "p")
    check("有用户时间的场次排在未知时间之前", seq["m_b"]["seq"] == 1 and seq["m_a"]["seq"] == 2, str(seq))
    check("未知时间标签不含伪造日期", session_label(seq, "m_a") == "第2场", session_label(seq, "m_a"))


def test_understanding_skip_memory() -> None:
    from domain.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS, _Nodes

    skip = _Nodes._understanding_skip(object(), ["minutes"], "", True)
    check(
        "memory=true 时 minutes 理解保留 action_hints",
        "action_hints" not in skip,
        str(sorted(skip)),
    )
    skip_off = _Nodes._understanding_skip(object(), ["minutes"], "")
    check(
        "默认仍跳过 action_hints",
        "action_hints" in skip_off and "action_hints" in UNDERSTANDING_SKIP_FIELDS["minutes"],
        str(sorted(skip_off)),
    )


def test_meta_protocol_round_trip() -> None:
    """meta 协议：producer 不写括号嵌套、parser 剥得净，状态/负责人进得了卡片。

    2026-09-21 实测回归：inject 的 meta 里场次标签带括号（``第1场（2026-09-01）``），
    render 的 ``（[^）]*）$`` 剥不掉 → 15/15 条条目正文混进内部 meta，卡片上出现
    「…（第1场（2026-09-01）起，最近第1场」。这里锁住两侧的协议。
    """
    from .render import apply_memory_citations

    f1 = _fact(meeting_id="m1", time="2026-09-01")
    st = update_state({}, f1, "p1", "小艺慧记Agent")
    ctx, _ = build_memory_context(
        project_id="p1",
        project={"name": "小艺慧记Agent"},
        state=st,
        bind=type("B", (), {"evidence": []})(),
        meetings=[f1.as_dict()],
        current_fact=f1,
    )
    items = parse_memory_items(ctx)
    check("注入 meta 不含嵌套括号", "（第1场（" not in ctx and "（第2场（" not in ctx, ctx[:300])
    check("解析后正文不残留内部 meta",
          bool(items) and all("第1场" not in i.text and "状态" not in i.text for i in items),
          str(items))
    check("解析出状态/负责人/时限",
          any(i.status == "open" for i in items)
          and any(i.owner == "赵衡" for i in items)
          and any(i.timing == "8月19日前" for i in items),
          str(items))
    body = (
        "# 纪要\n"
        "会议确认补齐记忆引用来源字段由赵衡负责推进。\n"
        "风险上，记忆可解释性不足仍未解决。\n"
    )
    out = apply_memory_citations(body, ctx)
    check("卡片带状态行（状态机终于有出口）",
          "状态：未闭环" in out and "负责人 赵衡" in out and "时限 8月19日前" in out,
          out[-400:])
    check("正文锚点挂在条目原文上", "](#memory-" in out, out)


def test_history_comparison_section() -> None:
    """历史对照小节：程序算好的对照无条件落地，零锚点也要可见。"""
    from .render import COMPARISON_TITLE, apply_memory_citations

    body = "# 纪要\n本次会议只讨论了别的议题，与历史条目没有词面重合。\n"
    ctx = "【会议记忆】\n项目：X\n\n【延续事项】\n- 补齐记忆引用来源字段（第1场·2026-09-01起，最近第1场·2026-09-01，状态 open）\n"
    comp = ["新增决策：记忆引用展示放到文末", "已闭环（第1场·2026-09-01）：记忆可解释性不足"]
    out = apply_memory_citations(body, ctx, comparison=comp)
    check("零锚点也输出「历史对照」小节",
          f"## {COMPARISON_TITLE}" in out and "新增决策：记忆引用展示放到文末" in out,
          out)
    again = apply_memory_citations(out, ctx, comparison=comp)
    check("重复调用不叠加对照/溯源小节",
          again.count(f"## {COMPARISON_TITLE}") == 1 and again.count("## 历史记忆引用") == 0,
          again)


def test_anchor_guards() -> None:
    """锚点守卫 + 4 字放宽：泛化短语/单位词/满篇 token 不锚；4 字重合能锚且显示完整短语。"""
    from .render import MemoryItem, _best_span, _NeedleStats

    generic = MemoryItem(kind="open", text="范炳杰下来找他们拆现网流量数据")
    line = "微服务接口当前由腾意去测，下来找他们对一下；"
    check("泛化短语不锚（改前把现网流量条目挂到微服务那句上）",
          _best_span(line, generic) is None, "")
    unit = MemoryItem(kind="risk", text="内部WeLink标注还差400min，数据都是打断的")
    unit_line = "49min会议转写要13分多，约原始音频的1/3。"
    check("单位词 min 不锚（同字不同事）", _best_span(unit_line, unit) is None, "")
    topic_line = "内部WeLink打标完成201、还差300多。"
    span = _best_span(topic_line, unit)
    check("专名 WeLink 正常锚定", span is not None and topic_line[span[0]:span[1]] == "内部WeLink打标完成201", str(span))
    # 4 字重合：跨场复述后只剩 4 字是常态，放宽后要能锚，且片段扩到句读边界（不是「控件链路」这种裸词）
    topic4 = MemoryItem(kind="risk", text="控件链路太长，自己拉不动，需产品去推")
    line4 = "控件链路这边还是自己拉不动，需要产品去推，控件改动等群里再说。"
    span4 = _best_span(line4, topic4)
    check("4 字重合能锚（改前 5 字门槛把这类全挡掉）", span4 is not None, str(span4))
    check("锚点文本扩到句读边界、可读",
          span4 is not None and line4[span4[0]:span4[1]].startswith("控件链路")
          and len(line4[span4[0]:span4[1]]) >= 6,
          line4[span4[0]:span4[1]] if span4 else "")
    common = MemoryItem(kind="decision", text="网页demo先集成已有功能，后面逐步加非实时转写等")
    lines = [f"第{i}行 demo 相关说明。" for i in range(20)]
    stats = _NeedleStats(lines)
    check("满篇出现的 token 不锚（行频守卫）",
          _best_span(lines[0], common, stats) is None, "")


def test_comparison_topic_labels() -> None:
    """对照行要说清"是哪个东西的延续/风险"：主题词取自场次议题名或条目自带专名。"""
    from .inject import _topic_label

    anchors = ["端侧待办与现网拨测问题", "现网流量", "控件链路", "数据表", "端侧待办", "OCR"]
    check("议题名逐字出现 → 用议题名",
          _topic_label("范炳杰下来找他们拆现网流量数据", anchors) == "现网流量", "")
    check("议题名前缀重合 → 取最短的那个议题名（不拿整条项目名当标签）",
          _topic_label("端侧大概什么时候带上版本", anchors) == "端侧待办", "")
    check("专名 + 紧邻汉字 → WeLink标注",
          _topic_label("内部WeLink标注还差400min，数据都是打断的", anchors) == "WeLink标注", "")
    check("数字专名 → 910c",
          _topic_label("910c机器是模型的问题还是机器的问题待验证", anchors) == "910c", "")
    check("没主题就不硬凑", _topic_label("今天下午茶喝了咖啡", anchors) == "", "")

    f1 = _fact(
        meeting_id="m1",
        time="2026-09-01",
        anchors=["现网流量", "控件链路"],
        open_items=["范炳杰下来找他们拆现网流量数据", "内部WeLink标注还差400min，数据都是打断的"],
    )
    st_pre = update_state({}, f1, "p1", "小艺慧记Agent")
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        anchors=["引擎并发"],
        decisions=[],
        risks=[],
        open_items=[],
        action_items=[],
    )
    meetings = [f1.as_dict(), f2.as_dict()]
    for row in meetings:
        row["project_id"] = "p1"
    ctx, comparison = build_memory_context(
        project_id="p1",
        project={"name": "小艺慧记Agent"},
        state=st_pre,
        bind=type("B", (), {"evidence": []})(),
        meetings=meetings,
        current_fact=f2,
    )
    check("对照行带主题词", any("（现网流量｜" in line for line in comparison), str(comparison))
    check("对照行带专名主题", any("（WeLink标注｜" in line for line in comparison), str(comparison))
    check("素材块与对照同格式（模型照抄）",
          any("（现网流量｜" in line for line in ctx.splitlines()), ctx[-400:])


def test_comparison_richness() -> None:
    """历史对照要够厚：多类多条 + 场次标注 + 计数汇总（只出 4 行时"记忆挂载"看起来几乎为空）。"""
    f1 = _fact(meeting_id="m1", time="2026-09-01")
    st_pre = update_state({}, f1, "p1", "小艺慧记Agent")  # 注入发生在写回之前
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        decisions=["8月18日前优化 minutes_trace", "新增一条本场决策"],
        risks=["记忆可解释性不足"],
        open_items=["是否默认开启记忆引用"],
        action_items=[{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": ""}],
        closed_items=["补齐记忆引用来源字段"],
    )
    meetings = [f1.as_dict(), f2.as_dict()]
    for row in meetings:
        row["project_id"] = "p1"  # list_meetings 的行都带 project_id，否则场次解析成"未知场次"
    lines = preview_comparison(st_pre, f2, session_index(meetings, "p1"))
    check("对照行数 ≥ 5（改前封顶 4 行）", len(lines) >= 5, str(lines))
    check("延续事项多条（改前只 1 条）",
          sum(1 for x in lines if x.startswith("延续事项")) >= 2, str(lines))
    check("带场次标注", any("第1场" in x for x in lines), str(lines))
    check("含已闭环类", any(x.startswith("已闭环") for x in lines), str(lines))
    check("末尾有计数汇总行", lines and lines[-1].startswith("本场历史对照合计"), str(lines[-1:]))


def test_selection_relevance_and_recency() -> None:
    """选材：相关度可算 + 全 0 时按最近场次保底（不是取数组最旧的）。"""
    from .inject import _relevance

    f = _fact(
        title="小艺慧记Agent周会",
        summary="周会",
        anchors=["小艺慧记Agent"],
        decisions=[],
        open_items=[],
        risks=[],
        action_items=[],
    )
    check("相同片段能算分", _relevance({"text": "小艺慧记Agent内测进展"}, f) > 0, "")
    check("无关条目 0 分", _relevance({"text": "完全无关的天气与球赛"}, f) == 0, "")
    old = {"item_id": "o1", "text": "陈年旧账：找人对接", "status": "open", "since": "m1", "last_seen": "m1"}
    fresh = {"item_id": "o2", "text": "上一场遗留的对接口径", "status": "open", "since": "m1", "last_seen": "m2"}
    state = {"open_items": [old, fresh], "actions": [], "recent_meetings": ["m1", "m2"]}
    ctx, _ = build_memory_context(
        project_id="p1",
        project={"name": "小艺慧记Agent"},
        state=state,
        bind=type("B", (), {"evidence": []})(),
        meetings=[],
        current_fact=f,
    )
    order = [line for line in ctx.splitlines() if line.startswith("- ")]
    check("全 0 分时最近场次优先（改前取最旧的僵尸条目）",
          bool(order) and "上一场遗留的对接口径" in order[0], str(order))
    # 沉寂风险不能静默丢弃：要带着 dormant 状态出现，模型才知道"这事没人提了"
    dormant_state = {
        "open_items": [],
        "actions": [],
        "recent_meetings": ["m1", "m2", "m3", "m4"],
        "risks": [{"item_id": "r1", "text": "久未提及的老风险", "status": "dormant", "last_seen": "m1"}],
    }
    ctx2, _ = build_memory_context(
        project_id="p1",
        project={"name": "小艺慧记Agent"},
        state=dormant_state,
        bind=type("B", (), {"evidence": []})(),
        meetings=[],
        current_fact=f,
    )
    check("沉寂风险保留在【风险演变】并标注 dormant",
          "久未提及的老风险" in ctx2 and "dormant" in ctx2, ctx2)


def test_state_lifecycle_consistency() -> None:
    """状态一致性：风险吃 closed_items、双轨不重复存、events 跨场保留。"""
    from .state import similar

    st = update_state({}, _fact(meeting_id="m1", time="2026-09-01"), "p1", "小艺慧记Agent")
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        open_items=["补齐记忆引用来源字段"],
        action_items=[{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": ""}],
        decisions=[],
        risks=["新冒出来的口径风险"],
        closed_items=[],
    )
    st = update_state(st, f2, "p1", "小艺慧记Agent")
    twins = [
        (a.get("text"), o.get("text"))
        for a in st.get("actions") or []
        for o in st.get("open_items") or []
        if similar(str(a.get("text")), str(o.get("text")))
    ]
    check("同一件事不在未决/待办各存一份", not twins, str(twins))
    f3 = _fact(
        meeting_id="m3",
        time="2026-09-14",
        title="推进会",
        open_items=[],
        action_items=[],
        decisions=[],
        risks=[],
        closed_items=["记忆可解释性不足"],
    )
    st = update_state(st, f3, "p1", "小艺慧记Agent")
    check(
        "风险吃 closed_items → mitigated（改前只有文本自带已解决才转）",
        any(r.get("status") == "mitigated" and r.get("closed_at") == "m3" for r in st.get("risks") or []),
        str(st.get("risks")),
    )
    mids = {str(e.get("meeting_id")) for e in st.get("events") or []}
    check("events 跨场保留（改前只留最近 40 条＝一场）", {"m1", "m2", "m3"} <= mids, str(sorted(mids)))


def test_review_panel_ledger_group() -> None:
    """双栏右栏分两段：本场证据（带 [n]）+ 历史台账（无 [n]，灰底）；左栏不再重复台账。

    零锚点时退回单栏页，台账留在正文小节（那是记忆唯一的可见通道）。
    """
    from .render import render_minutes_html

    body = "# 纪要\n会上过了长文本时延。内部WeLink打标完成201、还差300多。\n"
    ledger = (
        "\n## 历史对照\n\n"
        "- 新增决策：主干侧主动锻炼由己方做处理\n"
        "- 新增决策（商品版本）：商品版本需求包括录音机命名字数、仿写流失\n"
        "- 延续事项（现网流量｜自第1场·2026-09-01）：范炳杰下来找他们拆现网流量数据\n"
        "- 已闭环（双录信号｜第1场·2026-09-01）：范炳杰这周更新一个版本把双录信号问题刷掉\n"
        "- 已闭环：解决了端侧麦克风加媒体音播报幻觉问题\n"
        "- 风险演变（WeLink标注｜持续，第1场·2026-09-01）：内部WeLink标注还差400min\n"
        "- 本场历史对照合计：新增决策 2 条、延续未决 1 条、已闭环 2 条、风险演变 1 条\n"
    )
    appendix = (
        "\n## 历史记忆引用\n\n#### 溯源 memory-1\n> WeLink标注进度\n"
        "状态：持续中\n来源会议：某会\n会议时间：2026-09-01\n"
    )
    anchored = body.replace("内部WeLink", "内部[WeLink](#memory-1)") + ledger + appendix
    html = render_minutes_html("会议纪要", anchored)
    left = html.split('class="ck-review-left"', 1)[1].split("ck-review-rule", 1)[0]
    right = html.split('class="ck-review-right"', 1)[1]
    check("左栏不再出现「历史对照」（改由右栏承载）", "历史对照" not in left, left[-300:])
    check("右栏下段标题是「状态演进」",
          '<summary class="ck-proof-toggle">状态演进（' in right, right[-400:])
    check("不再输出分组标签与台账注记",
          'ck-ev-group' not in right and 'ck-ledger-note' not in right
          and '本场证据 · 正文可点' not in right and '台账取自记忆状态' not in right, "")
    ledger_part = right.split("ck-ledger", 1)[1]
    check("状态演进灰底无 [n] 序号", "ck-ev-cite-tag" not in ledger_part, "")
    check("每类一张卡、卡内各自编号（延续1+闭环2+新增2 → 3 张卡 3 个 <ol>）",
          ledger_part.count('class="ck-ledger-card"') == 3
          and ledger_part.count('<ol class="ck-ledger-list">') == 3
          and ledger_part.count("<li>") == 5, "")
    check("卡头带类别与条数",
          'ck-ledger-count">（1）' in ledger_part and 'ck-ledger-count">（2）' in ledger_part, "")
    check("卡片顺序固定 延续事项 → 已闭环 → 新增决策",
          ledger_part.index('data-kind="延续事项"') < ledger_part.index('data-kind="已闭环"')
          < ledger_part.index('data-kind="新增决策"'), "")
    check("右栏不出现风险演变（只在正文对照里）",
          "风险演变" not in ledger_part and "内部WeLink标注还差400min" not in ledger_part, "")
    check("演进条目带主题与场次",
          "现网流量" in right and "自第1场·2026-09-01" in right, "")
    check("不写无信息量的「本场」", "（本场）" not in right and "· 本场" not in right, "")
    check("证据卡片仍在（带行内锚点）", "ck-ev ck-mem-card" in right, "")

    plain = body + ledger
    html2 = render_minutes_html("会议纪要", plain)
    check("零锚点单栏页保留正文里的对照小节", "历史对照" in html2, "")


def main() -> int:
    test_identity_helpers()
    test_bind_explicit_warning()
    test_bind_title_variants()
    test_extract_time_and_actions()
    test_state_machine()
    test_rebuild_idempotent()
    test_empty_time_sessions()
    test_understanding_skip_memory()
    test_meta_protocol_round_trip()
    test_history_comparison_section()
    test_anchor_guards()
    test_comparison_topic_labels()
    test_comparison_richness()
    test_review_panel_ledger_group()
    test_selection_relevance_and_recency()
    test_state_lifecycle_consistency()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        test_persist_no_project_and_headline(tmp)
        test_pending_two_projects(tmp)
    print(f"pass {len(PASS)}  fail {len(FAIL)}")
    for name in FAIL:
        print("FAIL", name)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
