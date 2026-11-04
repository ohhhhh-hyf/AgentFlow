# 拆分自原大文件，保留：test_history_comparison_section, test_anchor_guards, test_comparison_topic_labels…

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

def test_history_comparison_section() -> None:
    """历史对照小节：程序算好的对照无条件落地，零锚点也要可见。"""
    from domains.meeting.memory.render import COMPARISON_TITLE, apply_memory_citations

    body = "# 纪要\n本次会议只讨论了别的议题，与历史条目没有词面重合。\n"
    ctx = "【会议记忆】\n项目：X\n\n【延续事项】\n- 补齐记忆引用来源字段（第1场·2026-09-01起，最近第1场·2026-09-01，状态 open）\n"
    comp = ["新增决策：记忆引用展示放到文末", "已闭环（第1场·2026-09-01）：记忆可解释性不足"]
    out = apply_memory_citations(body, ctx, comparison=comp)
    expect(f"## {COMPARISON_TITLE}" in out and "新增决策：记忆引用展示放到文末" in out, "零锚点也输出「历史对照」小节", out)
    again = apply_memory_citations(out, ctx, comparison=comp)
    expect(again.count(f"## {COMPARISON_TITLE}") == 1 and again.count("## 历史记忆引用") == 0, "重复调用不叠加对照/溯源小节", again)


def test_anchor_guards() -> None:
    """锚点守卫 + 4 字放宽：泛化短语/单位词/满篇 token 不锚；4 字重合能锚且显示完整短语。"""
    from domains.meeting.memory.render import MemoryItem, _best_span, _NeedleStats

    generic = MemoryItem(kind="open", text="范炳杰下来找他们拆现网流量数据")
    line = "微服务接口当前由腾意去测，下来找他们对一下；"
    expect(_best_span(line, generic) is None, "泛化短语不锚（改前把现网流量条目挂到微服务那句上）", "")
    unit = MemoryItem(kind="risk", text="内部WeLink标注还差400min，数据都是打断的")
    unit_line = "49min会议转写要13分多，约原始音频的1/3。"
    expect(_best_span(unit_line, unit) is None, "单位词 min 不锚（同字不同事）", "")
    topic_line = "内部WeLink打标完成201、还差300多。"
    span = _best_span(topic_line, unit)
    expect(span is not None and topic_line[span[0]:span[1]] == "内部WeLink打标完成201", "专名 WeLink 正常锚定", str(span))
    # 4 字重合：跨场复述后只剩 4 字是常态，放宽后要能锚，且片段扩到句读边界（不是「控件链路」这种裸词）
    topic4 = MemoryItem(kind="risk", text="控件链路太长，自己拉不动，需产品去推")
    line4 = "控件链路这边还是自己拉不动，需要产品去推，控件改动等群里再说。"
    span4 = _best_span(line4, topic4)
    expect(span4 is not None, "4 字重合能锚（改前 5 字门槛把这类全挡掉）", str(span4))
    expect(span4 is not None and line4[span4[0]:span4[1]].startswith("控件链路")
          and len(line4[span4[0]:span4[1]]) >= 6, "锚点文本扩到句读边界、可读", line4[span4[0]:span4[1]] if span4 else "")
    common = MemoryItem(kind="decision", text="网页demo先集成已有功能，后面逐步加非实时转写等")
    lines = [f"第{i}行 demo 相关说明。" for i in range(20)]
    stats = _NeedleStats(lines)
    expect(_best_span(lines[0], common, stats) is None, "满篇出现的 token 不锚（行频守卫）", "")


def test_comparison_topic_labels() -> None:
    """对照行主题词：读条目原生 module/topic_title（不再正则猜词，消灭畸形标签）。"""
    from domains.meeting.memory.inject import _topic_label_v2

    expect(_topic_label_v2({"module": "网关核心架构", "topic_title": "鉴权方案选型"}) == "网关核心架构·鉴权方案选型", "module+title 拼 module·title", "")
    expect(_topic_label_v2({"module": "现网流量"}) == "现网流量", "只有 module 也输出", "")
    expect(_topic_label_v2({"module": "引擎并发", "title": "现网流量拆解"}) == "引擎并发·现网流量拆解", "fact 议题形状（title 键）同样识别", "")
    expect(_topic_label_v2({"text": "内部WeLink标注还差400min"}) == "", "无原生字段返回空串（旧数据不硬凑）", "")
    expect(_topic_label_v2({"text": "内部专项标注还差400min"}) == ""
          and _topic_label_v2({"text": "端侧大概什么时候带上版本"}) == "", "不再从数字/专名猜词（400min/端侧 畸形标签消失）", "")

    f1 = _fact(
        meeting_id="m1",
        time="2026-09-01",
        anchors=["现网流量", "控件链路"],
        open_items=["范炳杰下来找他们拆现网流量数据", "内部WeLink标注还差400min，数据都是打断的"],
        decisions=["加固控件链路稳定性"],
        action_items=[],
        topics=[
            {
                "module": "引擎并发", "title": "现网流量拆解",
                "decisions": [], "actions": [], "risks": [],
                "open_issues": ["范炳杰下来找他们拆现网流量数据"],
            },
            {
                "module": "标注链路", "title": "内部标注缺口",
                "decisions": [], "actions": [], "risks": [],
                "open_issues": ["内部WeLink标注还差400min，数据都是打断的"],
            },
            {
                "module": "控件链路", "title": "控件稳定性",
                "decisions": ["加固控件链路稳定性"], "actions": [], "risks": [], "open_issues": [],
            },
        ],
    )
    st_pre = update_state({}, f1, "p1", "小艺慧记Agent")
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        anchors=["引擎并发"],
        decisions=["本场新增一条"],
        risks=[],
        open_items=[],
        action_items=[],
        topics=[
            {
                "module": "引擎并发", "title": "并发压测",
                "decisions": ["本场新增一条"], "actions": [], "risks": [], "open_issues": [],
            },
        ],
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
    expect(any("（引擎并发·现网流量拆解｜" in line for line in comparison), "条目对照行带原生主题", str(comparison))
    expect(any("（标注链路·内部标注缺口｜" in line for line in comparison), "不同议题的条目各带自己的主题", str(comparison))
    expect(any("新增决策（引擎并发·并发压测）" in line for line in comparison), "本场字符串条目（新增决策）用本场议题反查主题", str(comparison))
    expect(not any("（WeLink标注" in line or "（400min" in line for line in comparison), "旧版猜词标签不再出现", str(comparison))
    expect(any("主题：引擎并发·现网流量拆解" in line for line in ctx.splitlines()), "素材块以主题子行标注原生议题", ctx[-400:])


def test_closed_announcement_in_open_issues() -> None:
    """完成宣告只出现在 open_issues 时也能闭环（此前必漏）；未完成表述不得误判。"""
    u1 = {
        "meeting_purpose": "前端白屏排查",
        "topics": [{
            "topic_id": "T1", "module": "前端渲染", "title": "白屏排查",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补充日志采样用例"],
        }],
    }
    f1 = extract_meeting_fact(
        u1, "李工：白屏排查，补充日志采样用例待补。", request_id="r1", time="2026-09-01"
    )
    expect(f1.closed_items == [], "未完成表述不进闭句清单", str(f1.closed_items))
    st = update_state({}, f1, "p1", "P")

    u2 = {
        "meeting_purpose": "前端白屏收口",
        "topics": [{
            "topic_id": "T1", "module": "前端渲染", "title": "白屏排查",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补充日志采样用例已完成", "关闭策略待定", "解决方案未确认"],
        }],
    }
    f2 = extract_meeting_fact(
        u2, "李工：补充日志采样用例已完成；关闭策略待定。", request_id="r2", time="2026-09-02"
    )
    expect("补充日志采样用例已完成" in f2.closed_items, "open_issues 完成宣告进闭句清单", str(f2.closed_items))
    expect("关闭策略待定" not in f2.closed_items
          and "解决方案未确认" not in f2.closed_items, "裸词「关闭/解决」不误判（强完成标记口径）", str(f2.closed_items))
    st = update_state(st, f2, "p1", "P")
    rows = [i for i in st.get("open_items") or [] if i.get("text") == "补充日志采样用例"]
    expect(bool(rows) and rows[0].get("status") == "done"
          and rows[0].get("closed_at") == "m_r2", "只出现在 open_issues 的完成宣告把条目标成 done", str(rows))
    expect(all(
              i.get("status") == "open"
              for i in (st.get("open_items") or [])
              if i.get("text") in {"关闭策略待定", "解决方案未确认"}
          ), "敞口表述仍保持 open", str(st.get("open_items")))

    # 作用域门：另一 module 的相近完成宣告不得跨域关闭
    st_iso = update_state({}, f1, "p1", "P")
    u2b = {
        "meeting_purpose": "日志排查",
        "topics": [{
            "topic_id": "T1", "module": "日志模块", "title": "日志排查",
            "decisions": [], "actions": [], "risks": [],
            "open_issues": ["补充日志采样用例已完成"],
        }],
    }
    f2b = extract_meeting_fact(
        u2b, "王工：补充日志采样用例已完成。", request_id="r4", time="2026-09-04"
    )
    st_iso = update_state(st_iso, f2b, "p1", "P")
    rows = [i for i in st_iso.get("open_items") or [] if i.get("text") == "补充日志采样用例"]
    expect(bool(rows) and rows[0].get("status") == "open", "不同 module 的完成宣告不跨域关闭（作用域门）", str(rows))


def test_scoped_citations() -> None:
    """阶段四：历史条目只挂进主题重合的章节（消灭跨议题张冠李戴）。"""
    from domains.meeting.memory.render import apply_memory_citations

    ctx = (
        "【会议记忆】\n项目：P\n\n"
        "【延续事项】\n"
        "- 网关时延指标要压到200ms以内（第1场·2026-09-01起，最近第1场·2026-09-01，状态 open）\n"
        "  主题：网关核心架构·鉴权方案\n"
        "- 前端渲染白屏排查收尾（第1场·2026-09-01起，最近第1场·2026-09-01，状态 open）\n"
        "  主题：前端渲染·白屏排查\n"
    )
    body = (
        "# 纪要\n"
        "## 鉴权方案选型与延迟优化\n"
        "本场确认鉴权链路基线，时延指标要压到200ms以内。\n"
        "## 前端渲染改造\n"
        "前端渲染白屏排查收尾，渲染链路时延指标也顺带看了一眼。\n"
    )
    out = apply_memory_citations(body, ctx)
    auth, render_sec = out.split("## 前端渲染改造", 1)
    expect("(#memory-1)" in auth, "同议题章节内正常锚定", auth)
    expect("(#memory-1)" not in render_sec, "跨议题不误锚（鉴权条目不进前端渲染章节）", render_sec)
    expect("(#memory-2)" in render_sec and "(#memory-2)" not in auth, "另一议题条目只进自己的章节", out)
    expect("#### 溯源 memory-1" in out and "#### 溯源 memory-2" in out, "锚点仍按完整条目表编号（溯源卡片对得上）", out[-300:])
    # 幂等：重复调用不再叠加
    again = apply_memory_citations(out, ctx)
    expect(again.count("(#memory-1)") == 1 and again.count("## 历史记忆引用") == 1, "重复调用不重复标注", again)

    # 旧数据（无原生作用域）保持全局匹配：零回归
    ctx_legacy = (
        "【会议记忆】\n项目：P\n\n"
        "【延续事项】\n"
        "- 历史遗留的对接口径（第1场·2026-09-01起，最近第1场·2026-09-01，状态 open）\n"
    )
    body_legacy = (
        "# 纪要\n## 前端渲染改造\n"
        "前端渲染白屏排查收尾，历史遗留的对接口径顺带过了一遍。\n"
    )
    out2 = apply_memory_citations(body_legacy, ctx_legacy)
    expect("(#memory-1)" in out2, "旧数据（无作用域）仍全局锚定（零回归）", out2)

    # 固定栏名正文（minutes_styles 形态）不触发作用域切池：保持全局
    styles_body = (
        "# 多样式纪要\n"
        "## 会议性质\n"
        "网关时延指标要压到200ms以内这事在鉴权链路里说了。\n"
        "## 总体结论\n"
        "前端渲染白屏排查收尾，整体顺利。\n"
    )
    out3 = apply_memory_citations(styles_body, ctx)
    expect("(#memory-1)" in out3 and "(#memory-2)" in out3, "固定栏名正文不触发作用域切池（保留全局匹配）", out3)


def test_comparison_richness() -> None:
    """历史对照要够厚：多类多条 + 场次标注 + 计数汇总（只出 4 行时"记忆挂载"看起来几乎为空）。"""
    open_items = ["是否默认开启记忆引用", "确认记忆开关默认值"]
    f1 = _fact(meeting_id="m1", time="2026-09-01", open_items=open_items)
    st_pre = update_state({}, f1, "p1", "小艺慧记Agent")  # 注入发生在写回之前
    f2 = _fact(
        meeting_id="m2",
        time="2026-09-07",
        title="推进会",
        decisions=["8月18日前优化 minutes_trace", "新增一条本场决策"],
        risks=["记忆可解释性不足"],
        open_items=open_items,
        action_items=[{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": ""}],
        closed_items=["补齐记忆引用来源字段"],
    )
    meetings = [f1.as_dict(), f2.as_dict()]
    for row in meetings:
        row["project_id"] = "p1"  # list_meetings 的行都带 project_id，否则场次解析成"未知场次"
    lines = preview_comparison(st_pre, f2, session_index(meetings, "p1"))
    expect(len(lines) >= 5, "对照行数 ≥ 5（改前封顶 4 行）", str(lines))
    expect(sum(1 for x in lines if x.startswith("延续事项")) >= 2, "延续事项多条（改前只 1 条）", str(lines))
    expect(any("第1场" in x for x in lines), "带场次标注", str(lines))
    expect(any(x.startswith("已闭环") for x in lines), "含已闭环类", str(lines))
    expect(lines and lines[-1].startswith("本场历史对照合计"), "末尾有计数汇总行", str(lines[-1:]))


def test_selection_relevance_and_recency() -> None:
    """选材：相关度可算 + 全 0 时按最近场次保底（不是取数组最旧的）。"""
    from domains.meeting.memory.inject import _relevance

    f = _fact(
        title="小艺慧记Agent周会",
        summary="周会",
        anchors=["小艺慧记Agent"],
        decisions=[],
        open_items=[],
        risks=[],
        action_items=[],
    )
    expect(_relevance({"text": "小艺慧记Agent内测进展"}, f) > 0, "相同片段能算分", "")
    expect(_relevance({"text": "完全无关的天气与球赛"}, f) == 0, "无关条目 0 分", "")
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
    expect(bool(order) and "上一场遗留的对接口径" in order[0], "全 0 分时最近场次优先（改前取最旧的僵尸条目）", str(order))
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
    expect("久未提及的老风险" in ctx2 and "dormant" in ctx2, "沉寂风险保留在【风险演变】并标注 dormant", ctx2)
