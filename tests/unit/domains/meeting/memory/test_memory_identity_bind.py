# 拆分自 test_meeting_memory.py，覆盖：test_identity_helpers, test_bind_explicit_warning, test_bind_title_variants…

"""会议记忆零 LLM 衡约：身份、不传 project 接续、状态机、时间/场次。

用法::

    python -m tests.test_meeting_memory
"""

from __future__ import annotations
import json
from pathlib import Path
from domains.meeting.memory.bind import (
    bind_meeting,
    is_strong_anchor,
    is_weak_project_name,
    pick_project_name,
    project_core,
)
from domains.meeting.memory.extract import MeetingFact, extract_meeting_fact
from domains.meeting.memory.inject import build_memory_context, preview_comparison
from domains.meeting.memory.render import parse_memory_items
from domains.meeting.memory.runtime import persist_after_run, resolve_bind
from domains.meeting.memory.state import rebuild_state, session_index, session_label, update_state
from domains.meeting.memory.store import list_meetings, load_registry, load_state
from tests.support.expectations import expect

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
    expect(project_core("小艺慧记Agent开发进展阶段复盘") == "小艺慧记Agent"
        and project_core("小艺慧记Agent推进会") == "小艺慧记Agent", "会种尾巴剥到同一核心名", f"{project_core('小艺慧记Agent开发进展阶段复盘')!r}")
    expect(is_strong_anchor("小艺慧记Agent"), "中英混合专名是强锚点", "")
    expect(not is_strong_anchor("任务目录整理"), "议题动词短语不是强锚点", "")
    expect(is_weak_project_name("任务目录整理"), "议题名是弱项目名", "")
    expect(not is_weak_project_name("小艺慧记Agent"), "混合专名不是弱项目名", "")
    fact = _fact(title="任务目录整理")
    expect(pick_project_name(fact) == "小艺慧记Agent", "抽项目名跳过弱议题、落到混合专名", pick_project_name(fact))


def test_bind_explicit_warning() -> None:
    registry = {
        "projects": {
            "foo": {"name": "foo", "aliases": [], "anchors": ["完全无关专名XYZ"]},
        }
    }
    bind = bind_meeting(registry, _fact(), explicit_project="foo")
    expect(bind.confidence == "high" and bind.mode == "explicit", "显式 project 仍是 high", bind.as_dict())
    expect(bool(bind.warning), "显式无重叠带 warning", bind.warning)


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
    expect(bind.is_bound and bind.project_id == "xiaoyi", "标题换会种仍 high 绑到同一项目", bind.as_dict())


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
    expect(empty_time.time == "" and empty_time.time_source == "unknown", "空 time 记为 unknown，不填 now()", empty_time.time)
    stamped = extract_meeting_fact(understanding, "赵衡：补齐来源。", request_id="r1", time="2026-09-01")
    expect(stamped.time == "2026-09-01" and stamped.time_source == "user", "传入 time 记为 user", "")
    expect(any(a["text"] == "补齐记忆引用来源字段" for a in stamped.action_items), "action_hints 进入 fact.action_items", str(stamped.action_items))
    expect(any("已完成" in x for x in stamped.closed_items), "完成表述进入 closed_items", str(stamped.closed_items))
    expect("小艺慧记Agent" in stamped.anchors, "锚点含混合专名核心", str(stamped.anchors))


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
    expect(any(i.get("status") == "done" and "记忆引用" in str(i.get("text")) for i in opens), "未决关闭后仍保留 done 记录", str(opens))
    expect(sum(1 for d in st.get("decisions") or [] if "minutes_trace" in str(d.get("text"))) == 1, "决策相似则 reaffirmed 而不是重复追加", str(st.get("decisions")))
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
    expect(any(i.get("status") == "active" and "可解释" in str(i.get("text")) for i in st.get("risks") or []), "已缓解风险再提 → 重新 active", str(st.get("risks")))
    f4 = _fact(meeting_id="m4", time="2026-09-21", open_items=[], action_items=[], risks=[], decisions=[], closed_items=[])
    f5 = _fact(meeting_id="m5", time="2026-09-28", open_items=[], action_items=[], risks=[], decisions=[], closed_items=[])
    st = update_state(st, f4, "p1", "小艺慧记Agent")
    st = update_state(st, f5, "p1", "小艺慧记Agent")
    # 把「可解释」在 m3 激活后，m4/m5 未再提，应变 dormant
    expect(any(i.get("status") == "dormant" for i in st.get("risks") or []), "连续两场未提的活跃风险进入 dormant", str(st.get("risks")))


def test_rebuild_idempotent() -> None:
    meetings = [
        _fact(meeting_id="m1", project_id="p1").as_dict(),
        _fact(meeting_id="m1", project_id="p1", title="覆盖同一场").as_dict(),
    ]
    # jsonl 语义是 replace by id；rebuild 只应见到一场。模拟去重后的列表。
    unique = [meetings[-1]]
    st = rebuild_state(unique, "p1", "小艺")
    expect(len(st.get("recent_meetings") or []) == 1, "rebuild 按去重后的场次折叠", str(st.get("recent_meetings")))


def test_pending_two_projects(tmp_path: Path) -> None:
    tmp = tmp_path
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
    expect(len(reg.get("projects") or {}) == 2, "两个显式项目保持分立", str((reg.get("projects") or {}).keys()))
    ambiguous = extract_meeting_fact(
        {"meeting_purpose": "例会", "topics": [{"title": "例会"}], "decisions": [], "open_questions": [], "risks": []},
        "今天开例会推进工作。",
        request_id="c1",
        time="2026-09-03",
    )
    bind = resolve_bind(reg, ambiguous, "", "u2", list_meetings(tmp, "u2"))
    expect(not bind.is_bound, "双项目且无专名时不 high 错绑", bind.as_dict())


def test_empty_time_sessions() -> None:
    meetings = [
        {"meeting_id": "m_a", "project_id": "p", "time": "", "time_source": "unknown", "title": "A"},
        {"meeting_id": "m_b", "project_id": "p", "time": "2026-09-01", "time_source": "user", "title": "B"},
    ]
    seq = session_index(meetings, "p")
    expect(seq["m_b"]["seq"] == 1 and seq["m_a"]["seq"] == 2, "有用户时间的场次排在未知时间之前", str(seq))
    expect(session_label(seq, "m_a") == "第2场", "未知时间标签不含伪造日期", session_label(seq, "m_a"))


def test_understanding_skip_memory() -> None:
    from domains.meeting.orchestrator import UNDERSTANDING_SKIP_FIELDS, _Nodes

    skip = _Nodes._understanding_skip(object(), ["minutes"], "", True)
    expect("action_hints" not in skip, "memory=true 时 minutes 理解保留 action_hints", str(sorted(skip)))
    skip_off = _Nodes._understanding_skip(object(), ["minutes"], "")
    expect("action_hints" in skip_off and "action_hints" in UNDERSTANDING_SKIP_FIELDS["minutes"], "默认仍跳过 action_hints", str(sorted(skip_off)))


def test_meta_protocol_round_trip() -> None:
    """meta 协议：producer 不写括号嵌套、parser 剥得净，状态/负责人进得了卡片。

    2026-09-21 实测回归：inject 的 meta 里场次标签带括号（``第1场（2026-09-01）``），
    render 的 ``（[^）]*）$`` 剥不掉 → 15/15 条条目正文混进内部 meta，卡片上出现
    「…（第1场（2026-09-01）起，最近第1场」。这里锁住两侧的协议。
    """
    from domains.meeting.memory.render import apply_memory_citations

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
    expect("（第1场（" not in ctx and "（第2场（" not in ctx, "注入 meta 不含嵌套括号", ctx[:300])
    expect(bool(items) and all("第1场" not in i.text and "状态" not in i.text for i in items), "解析后正文不残留内部 meta", str(items))
    expect(any(i.status == "open" for i in items)
          and any(i.owner == "赵衡" for i in items)
          and any(i.timing == "8月19日前" for i in items), "解析出状态/负责人/时限", str(items))
    body = (
        "# 纪要\n"
        "会议确认补齐记忆引用来源字段由赵衡负责推进。\n"
        "风险上，记忆可解释性不足仍未解决。\n"
    )
    out = apply_memory_citations(body, ctx)
    expect("状态：未闭环" in out and "负责人 赵衡" in out and "时限 8月19日前" in out, "卡片带状态行（状态机终于有出口）", out[-400:])
    expect("](#memory-" in out, "正文锚点挂在条目原文上", out)
