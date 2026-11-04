# 拆分自 test_meeting_memory.py，覆盖：test_state_scope_isolation, test_registry_module_binding, test_state_lifecycle_consistency…

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

def test_state_scope_isolation() -> None:
    """阶段三：同 module 跨场延续；不同 module 的同名条目不误配；升级边界不重复建档。"""
    f1 = _fact(
        meeting_id="m1", time="2026-09-01",
        open_items=["补充鉴权测试用例"],
        risks=["鉴权接口偶发超时"],
        decisions=["鉴权走二级缓存"],
        action_items=[],
        topics=[{
            "module": "鉴权网关", "title": "鉴权方案选型",
            "decisions": ["鉴权走二级缓存"], "actions": [],
            "risks": ["鉴权接口偶发超时"],
            "open_issues": ["补充鉴权测试用例"],
        }],
    )
    st = update_state({}, f1, "p1", "P")
    opens = st.get("open_items") or []
    expect(bool(opens) and opens[0].get("module") == "鉴权网关"
          and opens[0].get("topic_title") == "鉴权方案选型", "新条目带原生作用域", str(opens))
    expect(all(i.get("module") == "鉴权网关" for i in st.get("risks") or [])
          and all(i.get("module") == "鉴权网关" for i in st.get("decisions") or []), "风险/决策同样带作用域", str(st.get("risks")) + str(st.get("decisions")))

    f2 = _fact(
        meeting_id="m2", time="2026-09-02", title="推进会",
        open_items=["补充鉴权测试用例"], risks=[], decisions=[], action_items=[],
        topics=[{
            "module": "日志模块", "title": "日志排查",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补充鉴权测试用例"],
        }],
    )
    st = update_state(st, f2, "p1", "P")
    opens = st.get("open_items") or []
    expect(len(opens) == 2 and {i.get("module") for i in opens} == {"鉴权网关", "日志模块"}, "不同 module 的同名条目不误配（各存一份）", str(opens))

    f3 = _fact(
        meeting_id="m3", time="2026-09-03", title="推进会",
        open_items=["补充鉴权测试用例"], risks=[], decisions=[], action_items=[],
        topics=[{
            "module": "鉴权网关", "title": "鉴权压测复盘",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补充鉴权测试用例"],
        }],
    )
    st = update_state(st, f3, "p1", "P")
    opens = st.get("open_items") or []
    auth_rows = [i for i in opens if i.get("module") == "鉴权网关"]
    expect(len(opens) == 2 and len(auth_rows) == 1
          and auth_rows[0].get("last_seen") == "m3", "同 module 跨场匹配延续（不重复建档）", str(opens))

    # 升级边界：旧条目（无 module）再出现时按同一件事匹配，并补上原生作用域
    legacy = update_state(
        {}, _fact(meeting_id="m1", time="2026-09-01", open_items=["补齐来源字段"],
                  risks=[], decisions=[], action_items=[]),
        "p1", "P",
    )
    expect((legacy.get("open_items") or [{}])[0].get("module") in (None, ""), "旧数据（无 topics）条目无作用域", str(legacy.get("open_items")))
    f2b = _fact(
        meeting_id="m2", time="2026-09-02", title="推进会",
        open_items=["补齐来源字段"], risks=[], decisions=[], action_items=[],
        topics=[{
            "module": "记忆体系", "title": "来源字段",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补齐来源字段"],
        }],
    )
    st2 = update_state(legacy, f2b, "p1", "P")
    rows = st2.get("open_items") or []
    expect(len(rows) == 1 and rows[0].get("module") == "记忆体系"
          and rows[0].get("last_seen") == "m2", "升级边界：旧条目按同一件事匹配并补上作用域", str(rows))

    # 闭环作用域门：同域闭环改状态；不同域同名条目不被连带关闭
    f_close = _fact(
        meeting_id="m4", time="2026-09-04", title="收口",
        open_items=[], risks=[], action_items=[],
        decisions=["补充鉴权测试用例已完成"],
        closed_items=["补充鉴权测试用例已完成"],
        topics=[{
            "module": "鉴权网关", "title": "鉴权收口",
            "decisions": ["补充鉴权测试用例已完成"], "actions": [], "risks": [],
            "open_issues": [],
        }],
    )
    st = update_state(st, f_close, "p1", "P")
    opens = st.get("open_items") or []
    auth_row = next(i for i in opens if i.get("module") == "鉴权网关")
    log_row = next(i for i in opens if i.get("module") == "日志模块")
    expect(auth_row.get("status") == "done" and auth_row.get("closed_at") == "m4", "同域闭环改状态（closed_at 落场次）", str(auth_row))
    expect(log_row.get("status") == "open", "不同域同名条目不被连带关闭", str(log_row))


def test_registry_module_binding(tmp_path: Path) -> None:
    """阶段五：议题 module 并入 registry anchors / _fact_blob；同 module 可命中 topic 级信号。"""
    tmp = tmp_path
    from domains.meeting.memory.bind import _fact_blob, _project_hits

    u = {
        "meeting_purpose": "网关鉴权改造评审",
        "meeting_brief": "评审鉴权方案",
        "topics": [
            {"topic_id": "T1", "module": "网关核心架构", "title": "鉴权方案选型",
             "decisions": [], "actions": [], "risks": [], "open_issues": []},
            {"topic_id": "T2", "module": "会议纪要", "title": "泛词模块",
             "decisions": [], "actions": [], "risks": [], "open_issues": []},
        ],
    }
    t = "李工：网关鉴权改造评审，主从切换降级策略未定。"
    persist_after_run(
        tmp, "u9", "", "req_m", t,
        {"minutes": {"headline": "网关鉴权改造评审"}}, u,
        meeting_time="2026-09-01",
    )
    rows = list_meetings(tmp, "u9")
    expect(bool(rows and rows[-1].get("topics")), "meetings.jsonl 行带 topics", str(rows[-1].keys()) if rows else "")
    reg = load_registry(tmp, "u9")
    project = next(iter((reg.get("projects") or {}).values()))
    anchors = project.get("anchors") or []
    expect("网关核心架构" in anchors, "议题 module 并入 registry anchors", str(anchors))
    expect("会议纪要" not in anchors, "泛词 module 不并入", str(anchors))

    fact = extract_meeting_fact(u, t, request_id="req_n", time="2026-09-07")
    blob = _fact_blob(fact)
    expect("网关核心架构" in blob, "_fact_blob 纳入议题 module", blob)
    hits = _project_hits(project, fact)
    expect("网关核心架构" in hits["topic_anchors"]
          and "网关核心架构" not in hits["strong_anchors"], "module 作为 topic 级信号命中（不冒充强锚点）", str(hits))


def test_state_lifecycle_consistency() -> None:
    """状态一致性：风险吃 closed_items、双轨不重复存、events 跨场保留。"""
    from domains.meeting.memory.state import similar

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
    expect(not twins, "同一件事不在未决/待办各存一份", str(twins))
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
    expect(any(r.get("status") == "mitigated" and r.get("closed_at") == "m3" for r in st.get("risks") or []), "风险吃 closed_items → mitigated（改前只有文本自带已解决才转）", str(st.get("risks")))
    mids = {str(e.get("meeting_id")) for e in st.get("events") or []}
    expect({"m1", "m2", "m3"} <= mids, "events 跨场保留（改前只留最近 40 条＝一场）", str(sorted(mids)))


def test_persist_no_project_and_headline(tmp_path: Path) -> None:
    tmp = tmp_path
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
    expect(len(projects) == 1, "第一场不传 project 仍建档", str(projects.keys()))
    pid = next(iter(projects))
    name = str(projects[pid].get("name") or "")
    expect("小艺慧记Agent" in name and "复盘纪要" not in name, "项目名是核心专名而非 headline", name)
    rows = list_meetings(tmp, "u1")
    expect(rows and rows[-1].get("title") == "小艺一期复盘纪要", "jsonl 标题可用 headline 展示", str(rows))
    expect(rows[-1].get("project_id") == pid, "jsonl project_id 不是 headline 的 safe_id", str(rows[-1].get("project_id")))
    persist_after_run(
        tmp, "u1", "", "req_a", t1, {"minutes": {"headline": "小艺一期复盘纪要"}}, u1,
        meeting_time="2026-09-01",
    )
    expect(sum(1 for r in list_meetings(tmp, "u1") if r.get("meeting_id") == "m_req_a") == 1, "同一 request_id 重跑覆盖而非双倍场次", str([r.get("meeting_id") for r in list_meetings(tmp, "u1")]))

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
    expect(len(reg2.get("projects") or {}) == 1, "第二场不传 project 不裂成两个项目", str((reg2.get("projects") or {}).keys()))
    st = load_state(tmp, "u1", pid)
    seq = session_index(list_meetings(tmp, "u1"), pid)
    expect({info["seq"] for info in seq.values()} == {1, 2}, "两场都有场次号", str(seq))
    expect("2026-09-01" in session_label(seq, "m_req_a"), "有用户时间的场次标签带日期", session_label(seq, "m_req_a"))
    actions = [i for i in (st.get("actions") or []) if isinstance(i, dict)]
    opens = [i for i in (st.get("open_items") or []) if isinstance(i, dict)]
    expect(any(i.get("owner") == "赵衡" for i in actions), "待办写入 actions 且带负责人", str(actions))
    closed = [i for i in opens + actions if i.get("status") == "done"]
    expect(bool(closed) or any("记忆引用" in str(i.get("text")) and i.get("status") == "done" for i in opens + actions), "关闭是改状态而不是删除", str(opens + actions))
    risks = [i for i in (st.get("risks") or []) if isinstance(i, dict)]
    expect(any(i.get("status") == "mitigated" for i in risks), "风险本场缓解 → mitigated", str(risks))
    ctx, comparison = build_memory_context(
        project_id=pid,
        project=projects[pid],
        state=st,
        bind=type("B", (), {"evidence": ["test"]})(),
        meetings=list_meetings(tmp, "u1"),
        current_fact=_fact(title="小艺慧记Agent周会", summary="继续", anchors=["小艺慧记Agent"]),
    )
    expect("第1场" in ctx or "第2场" in ctx, "注入使用第N场而不是 meeting_id 当展示", ctx[:400])
    expect("【已闭环】" in ctx or "已闭环" in "\n".join(comparison), "注入含已闭环或对照素材", ctx[:500])
    items = parse_memory_items(ctx)
    expect(len(items) >= 1, "新注入格式可被引用解析", str(items))


def test_persist_scope_roundtrip(tmp_path: Path) -> None:
    """落盘→重放：module 命名漂移仍同域延续；rebuild 与落盘 state 一致（含 topics/scope）。"""
    tmp = tmp_path
    u1 = {
        "meeting_purpose": "小艺慧记Agent网关鉴权评审",
        "topics": [{
            "topic_id": "T1", "module": "网关核心架构", "title": "鉴权方案选型",
            "decisions": [],
            "actions": [{"task": "完成缓存保护设计", "owner": "李工", "deadline": "10-10"}],
            "risks": [], "open_issues": ["主从切换降级策略未定"],
        }],
    }
    t1 = "李工：小艺慧记Agent网关鉴权评审，完成缓存保护设计。"
    persist_after_run(
        tmp, "u4", "小艺慧记Agent", "r1", t1,
        {"minutes": {"headline": "小艺慧记Agent网关鉴权评审"}}, u1,
        meeting_time="2026-09-01",
    )
    u2 = {
        "meeting_purpose": "小艺慧记Agent鉴权推进会",
        "topics": [{
            "topic_id": "T1", "module": "网关鉴权优化", "title": "鉴权压测复盘",
            "decisions": [],
            "actions": [{"task": "完成缓存保护设计", "owner": "李工", "deadline": "10-20"}],
            "risks": [], "open_issues": ["主从切换降级策略未定"],
        }],
    }
    t2 = "李工：小艺慧记Agent鉴权推进，主从切换降级策略未定，缓存保护设计继续。"
    persist_after_run(
        tmp, "u4", "小艺慧记Agent", "r2", t2,
        {"minutes": {"headline": "小艺慧记Agent鉴权推进会"}}, u2,
        meeting_time="2026-09-07",
    )
    reg = load_registry(tmp, "u4")
    pid = next(iter(reg["projects"]))
    st = load_state(tmp, "u4", pid)
    actions = [i for i in st.get("actions") or [] if i.get("text") == "完成缓存保护设计"]
    expect(len(actions) == 1 and actions[0].get("last_seen") == "m_r2"
          and actions[0].get("module") == "网关核心架构", "命名漂移仍同域延续（落盘链路）", str(actions))
    meetings = list_meetings(tmp, "u4")
    rebuilt = rebuild_state(
        meetings, pid, project_name=str(reg["projects"][pid].get("name") or pid)
    )
    expect(json.dumps(rebuilt, ensure_ascii=False, sort_keys=True)
          == json.dumps(st, ensure_ascii=False, sort_keys=True), "rebuild 与落盘 state 一致（含 topics/scope）", "")
