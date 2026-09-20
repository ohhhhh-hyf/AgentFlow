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
from .inject import build_memory_context
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


def main() -> int:
    test_identity_helpers()
    test_bind_explicit_warning()
    test_bind_title_variants()
    test_extract_time_and_actions()
    test_state_machine()
    test_rebuild_idempotent()
    test_empty_time_sessions()
    test_understanding_skip_memory()
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
