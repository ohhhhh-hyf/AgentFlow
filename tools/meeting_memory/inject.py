"""Build high-confidence meeting memory context for generation and citations."""
from __future__ import annotations

import re
from typing import Any

from .state import session_index, session_label, similar

# 主题词提取用的专名/数字样式（与 render 的锚点口径一致，这里只取"叫什么"）
_LATIN_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_NUM_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?(?:min|ms|h|w|s|%|万|字|卡|路|场|小时|分钟|天|周|月|年|多)"
)
_NUM_LONG_RE = re.compile(r"\d{3,}")


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _relevance(item: dict[str, Any], fact: Any | None) -> int:
    """条目与本场事实的相关度（越大越相关；0 表示查不到共同片段）。

    打分 = 最长命中 n-gram 长度 × 100 + 命中条数：先比"最长共同片段"，
    同长度再比覆盖面，避免长短条目混用同一把尺子。

    2026-09-21 修：原实现 `range(0, len-size+1, size)` 的**步长等于 n-gram 长度**，
    等于每个串只抽样 1/size 的位置——实测 18 条未决全 0 分、9 条决策全 0 分、
    15 条风险 13 条 0 分，打分等于没打（相关度门禁整体失效）。
    """
    if fact is None:
        return 1
    blob = _compact(
        " ".join([
            _clean(getattr(fact, "title", "")),
            _clean(getattr(fact, "summary", "")),
            " ".join(getattr(fact, "anchors", []) or []),
            " ".join(getattr(fact, "decisions", []) or []),
            " ".join(getattr(fact, "open_items", []) or []),
            " ".join(getattr(fact, "risks", []) or []),
        ])
    )
    text = _compact(_clean(item.get("text")))
    if not text:
        return 0
    if text in blob or blob in text:
        return 10000
    for size in range(min(8, len(text)), 3, -1):
        grams = [text[i : i + size] for i in range(len(text) - size + 1)]
        hits = sum(1 for g in grams if g in blob)
        if hits:
            return size * 100 + hits
    return 0


def _rank(
    items: list[dict[str, Any]],
    fact: Any | None,
    cap: int,
    recent: list[str] | None = None,
) -> list[dict[str, Any]]:
    """取相关性最高的 cap 条；相关度全 0 时按**最近提及**（而不是数组顺序）保底。

    2026-09-21 修：原保底是 `scored[:cap]`＝数组最前面＝**最早**那批条目。相关度
    门禁失效（见 ``_relevance``）时，区块就被最旧的一批老事项填满（实测第二场注入的
    6 条未决全是第一场最早的 action 唠叨），而"最旧"恰好是从未被后续会议验证/关闭的
    僵尸条目。``recent`` 是状态的 recent_meetings（末尾最新）：越靠后越优先；
    同场次再让带负责人/时限的条目先上（更可执行）。
    """
    order = {mid: i for i, mid in enumerate(recent or [])}

    def key(pair: tuple[int, dict[str, Any]]) -> tuple:
        score, item = pair
        mid = _clean(item.get("last_seen") or item.get("since") or item.get("meeting_id"))
        has_owner = bool(_clean(item.get("owner")) or _clean(item.get("timing")))
        return (-score, -order.get(mid, -1), 0 if has_owner else 1)

    scored = sorted(((_relevance(i, fact), i) for i in items), key=key)
    return [i for _, i in scored[:cap]]


def _append_item(
    parts: list[str],
    item: dict[str, Any],
    *,
    seq_map: dict[str, dict[str, Any]],
    meta: str,
) -> None:
    text = _clean(item.get("text"))
    if not text:
        return
    parts.append(f"- {text}（{meta}）")
    quote = _clean(item.get("quote"))
    if quote:
        parts.append(f"  原文摘录：{quote}")
    title = _clean(item.get("meeting_title"))
    if title:
        parts.append(f"  来源会议：{title}")
    mid = _clean(item.get("last_seen") or item.get("meeting_id") or item.get("closed_at") or item.get("since"))
    info = seq_map.get(mid) or {}
    time_val = _clean(item.get("time")) or _clean(info.get("time"))
    if time_val:
        parts.append(f"  会议时间：{time_val}")


def _open_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    """未决/待办 meta：``第1场·2026-09-01起，最近第2场·2026-09-08，状态 open，负责人 武思华``。

    括号内不再出现括号（场次标签改用 ``·``），渲染侧的 ``（[^（）]*）$`` 才剥得掉；
    字段顺序与词形固定，供解析端取 since/last/status/owner。
    """
    since = session_label(seq_map, _clean(item.get("since")))
    last = session_label(seq_map, _clean(item.get("last_seen") or item.get("since")))
    status = _clean(item.get("status")) or "open"
    bits = [f"{since}起", f"最近{last}", f"状态 {status}"]
    owner = _clean(item.get("owner"))
    if owner:
        bits.append(f"负责人 {owner}")
    timing = _clean(item.get("timing"))
    if timing:
        bits.append(f"时限 {timing}")
    return "，".join(bits)


def _closed_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    closed = session_label(seq_map, _clean(item.get("closed_at") or item.get("last_seen")))
    status = _clean(item.get("status")) or "done"
    bits = [f"{closed}关闭"]
    if status and status != "done":
        bits.append(f"状态 {status}")
    return "，".join(bits)


def _risk_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    status = _clean(item.get("status")) or "active"
    last = session_label(seq_map, _clean(item.get("last_seen")))
    return f"{status}，最近{last}"


def _decision_meta(item: dict[str, Any], seq_map: dict[str, dict[str, Any]]) -> str:
    first = session_label(seq_map, _clean(item.get("meeting_id") or item.get("since")))
    status = _clean(item.get("status")) or "active"
    return f"{first}已决策，状态 {status}"


def _topic_label(text: str, anchors: list[str]) -> str:
    """条目的主题词：让对照行说清"这是哪个东西的延续/风险"。

    取法（确定性，零额外调用）：
    ① 议题名逐字出现在条目里（3–12 字，取最长）——议题名本来就是这场会的板块名；
    ② 否则抓专名：拉丁词/数字带紧邻 2 字（``内部WeLink标注还差400min`` → ``WeLink标注``）；
    ③ 再退到"议题名前 2 字重合"的**最短**议题名（``端侧大概什么时候带上版本`` → ``端侧待办``，
       不取 ``端侧待办与现网拨测问题`` 这种整条项目名当标签）；
    ④ 都没有就返回空串，该行保持原格式（不硬凑主题）。
    """
    body = _clean(text)
    if not body:
        return ""
    hits = [name for name in anchors if 3 <= len(name) <= 12 and name in body]
    if hits:
        return max(hits, key=len)
    token = _LATIN_TERM.search(body)
    tail_mode = "han"
    if token is None:
        token = _NUM_UNIT_RE.search(body) or _NUM_LONG_RE.search(body)
        tail_mode = "alnum"  # 数值专名只续字母数字（910c），不把后面的汉字吞进来
    if token:
        tail = ""
        for char in body[token.end() : token.end() + 2]:
            is_han = "\u4e00" <= char <= "\u9fff"
            # 注意：汉字的 str.isalnum() 也是 True，必须显式先判汉字
            if is_han:
                if tail_mode != "han":
                    break
            elif not char.isalnum():
                break
            tail += char
        return (token.group(0) + tail)[:12]
    shorts = [name for name in anchors if 3 <= len(name) <= 6 and name[:2] in body]
    if shorts:
        return min(shorts, key=len)
    return ""


def _meeting_topics(meetings: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    """meeting_id → 该场议题名（anchors，长的在前）。"""
    out: dict[str, list[str]] = {}
    for row in meetings or []:
        if not isinstance(row, dict):
            continue
        mid = _clean(row.get("meeting_id"))
        if not mid:
            continue
        names = {_clean(x) for x in (row.get("anchors") or []) if _clean(x)}
        out[mid] = sorted(names, key=len, reverse=True)
    return out


def preview_comparison(
    state: dict[str, Any],
    fact: Any,
    seq_map: dict[str, dict[str, Any]],
    meeting_topics: dict[str, list[str]] | None = None,
) -> list[str]:
    """程序拼的历史对照（不依赖词面重合，正文锚点挂不上时它是唯一可见溯源）。

    每类给 1–3 条而不是各 1 条：实测第二场只出 4 行时，"记忆挂载"看起来几乎为空，
    而状态里其实有 19 条未决、若干闭环与风险演变可说。顺序固定：
    新增决策 / 延续事项 / 已闭环 / 风险演变，末尾追加一行计数汇总。

    每条都带**主题词**（``延续事项（现网流量｜自第1场·2026-09-01）``）：只写"延续事项"
    读者不知道延续的是哪个东西；主题取自条目所属场次的议题名或条目自带专名。
    """
    lines: list[str] = []
    # 主题词候选：项目累计议题名 + 本场议题名（本场词汇对"这条历史在讲什么"最贴切）
    state_anchors = [_clean(x) for x in (state.get("anchors") or []) if _clean(x)]
    state_anchors += [
        _clean(x) for x in (getattr(fact, "anchors", None) or []) if _clean(x)
    ]
    state_anchors = list(dict.fromkeys(state_anchors))
    state_anchors.sort(key=len, reverse=True)

    def label_for(item: dict[str, Any] | str) -> str:
        if isinstance(item, dict):
            text = _clean(item.get("text"))
            mid = _clean(
                item.get("last_seen")
                or item.get("meeting_id")
                or item.get("closed_at")
                or item.get("since")
            )
        else:
            text, mid = _clean(item), ""
        # 条目所属场次的议题名 + 项目累计议题名（同一个主题后来又叫别的名字时也能命中）
        anchors = list(
            dict.fromkeys((meeting_topics or {}).get(mid, []) + state_anchors)
        )
        anchors.sort(key=len, reverse=True)
        return _topic_label(text, anchors)

    def head(topic: str, tail: str = "") -> str:
        """括号里的拼接：有主题和场次说明就 ``（主题｜说明）``，只有一个就只写那个，都没有就空。"""
        bits = [bit for bit in (topic, tail) if bit]
        return f"（{'｜'.join(bits)}）" if bits else ""

    ranked_open = _rank(
        [
            i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
            if isinstance(i, dict) and i.get("status") == "open" and _clean(i.get("text"))
        ],
        fact,
        3,
        [str(x) for x in (state.get("recent_meetings") or [])],
    )

    hist_decisions = [
        i for i in (state.get("decisions") or [])
        if isinstance(i, dict) and _clean(i.get("text")) and i.get("status") != "superseded"
    ]
    new_decisions = [
        d for d in (getattr(fact, "decisions", None) or [])
        if _clean(d) and not any(similar(d, _clean(h.get("text"))) for h in hist_decisions)
    ]
    for decision in new_decisions[:2]:
        topic = label_for(decision)
        prefix = f"（{topic}）" if topic else ""
        lines.append(f"新增决策{prefix}：{_clean(decision)}")

    seen_open: set[str] = set()
    for item in ranked_open:
        since = session_label(seq_map, _clean(item.get("since")))
        text = _clean(item.get("text"))
        if text in seen_open:
            continue
        seen_open.add(text)
        lines.append(f"延续事项{head(label_for(item), f'自{since}')}：{text}")

    closed_now = [_clean(x) for x in (getattr(fact, "closed_items", None) or []) if _clean(x)]
    closed_hist = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and _clean(i.get("text"))
        and (
            i.get("status") == "done"
            or any(similar(_clean(i.get("text")), c) for c in closed_now)
        )
    ]
    shown_closed: set[str] = set()
    for item in closed_hist[:2]:
        text = _clean(item.get("text"))
        if text in shown_closed:
            continue
        shown_closed.add(text)
        closed_mid = _clean(item.get("closed_at"))
        # "本场"不带信息量（对照本来就是相对本场），直接省掉
        when = (
            session_label(seq_map, closed_mid)
            if item.get("status") == "done" and closed_mid in seq_map
            else ""
        )
        lines.append(f"已闭环{head(label_for(item), when)}：{text}")
    for text in closed_now[:2]:
        if any(text in shown for shown in shown_closed):
            continue
        shown_closed.add(text)
        lines.append(f"已闭环{head(label_for(text))}：{text}")

    hist_risks = [i for i in (state.get("risks") or []) if isinstance(i, dict) and _clean(i.get("text"))]
    fact_risks = [_clean(r) for r in (getattr(fact, "risks", None) or []) if _clean(r)]
    evolved: list[str] = []
    for hist in hist_risks:
        if hist.get("status") == "dormant":
            continue  # 已沉寂的风险不能写成"持续"（只有 active/mitigated 才谈演变）
        for cur in fact_risks:
            if not similar(_clean(hist.get("text")), cur):
                continue
            last = session_label(seq_map, _clean(hist.get("last_seen")))
            topic = label_for(hist)
            if re.search(r"(已解决|已缓解|已消除|风险解除|不再存在|完成整改)", cur):
                evolved.append(f"风险演变{head(topic, f'缓解，{last}')}：{cur}")
            elif hist.get("status") == "mitigated":
                evolved.append(f"风险演变{head(topic, '再发，本场')}：{cur}")
            else:
                evolved.append(f"风险演变{head(topic, f'持续，{last}')}：{_clean(hist.get('text'))}")
            break
    if not evolved:
        for item in _rank([i for i in hist_risks if i.get("status") == "active"], fact, 2):
            last = session_label(seq_map, _clean(item.get("last_seen")))
            evolved.append(
                f"风险演变{head(label_for(item), f'持续，{last}')}：{_clean(item.get('text'))}"
            )
    lines.extend(evolved[:2])

    if lines:
        counts = {
            "新增决策": sum(1 for x in lines if x.startswith("新增决策")),
            "延续未决": len(seen_open),
            "已闭环": len(shown_closed),
            "风险演变": len(evolved[:2]),
        }
        summary = "、".join(f"{k} {v} 条" for k, v in counts.items() if v)
        lines.append(f"本场历史对照合计：{summary}")
    return lines[:10]


def build_memory_context(
    *,
    project_id: str,
    project: dict[str, Any],
    state: dict[str, Any],
    bind: Any,
    meetings: list[dict[str, Any]] | None = None,
    current_fact: Any | None = None,
) -> tuple[str, list[str]]:
    if not project_id or not state:
        return "", []
    seq_map = session_index(meetings or [], project_id)
    evidence = getattr(bind, "evidence", []) or []
    parts = [
        "【会议记忆】",
        f"项目：{_clean(project.get('name')) or _clean(state.get('name')) or project_id}",
    ]
    if evidence:
        parts.append("命中依据：" + "、".join(str(x) for x in evidence[:8]))

    opens = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and (i.get("status") or "open") == "open"
    ]
    closed = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and i.get("status") == "done"
    ]
    risks = [
        i for i in (state.get("risks") or [])
        if isinstance(i, dict) and i.get("status") in {"active", "mitigated", "dormant"}
    ]
    active_risks = [i for i in risks if i.get("status") == "active"]
    mitigated = [i for i in risks if i.get("status") == "mitigated"]
    dormant = [i for i in risks if i.get("status") == "dormant"]
    decisions = [
        i for i in (state.get("decisions") or [])
        if isinstance(i, dict) and i.get("status") != "superseded"
    ]

    recent = [str(x) for x in (state.get("recent_meetings") or []) if str(x).strip()]
    ranked_open = _rank(opens, current_fact, 6, recent)
    ranked_closed = _rank(closed, current_fact, 4, recent)
    # 名额分开算：过去是 active 5 条 + mitigated 2 条再 [:5] 截断，
    # 只要 active 满额，「已缓解」永远不出现（风险演变只有坏消息、没有闭环）。
    ranked_risks = _rank(active_risks, current_fact, 5, recent)
    ranked_mitigated = _rank(mitigated, current_fact, 2, recent)
    # 沉寂风险不再静默丢弃：给一格让模型知道"这事没人提了"，别当成现状写。
    ranked_dormant = _rank(dormant, current_fact, 1, recent)
    ranked_decisions = _rank(decisions[-8:], current_fact, 6, recent)

    if ranked_open:
        parts.append("\n【延续事项】")
        for item in ranked_open:
            _append_item(parts, item, seq_map=seq_map, meta=_open_meta(item, seq_map))
    if ranked_closed:
        parts.append("\n【已闭环】")
        for item in ranked_closed:
            _append_item(parts, item, seq_map=seq_map, meta=_closed_meta(item, seq_map))
    if ranked_risks or ranked_mitigated or ranked_dormant:
        parts.append("\n【风险演变】")
        for item in ranked_risks:
            _append_item(parts, item, seq_map=seq_map, meta=_risk_meta(item, seq_map))
        for item in ranked_mitigated:
            _append_item(parts, item, seq_map=seq_map, meta=_risk_meta(item, seq_map))
        for item in ranked_dormant:
            _append_item(parts, item, seq_map=seq_map, meta=_risk_meta(item, seq_map))
    if ranked_decisions:
        parts.append("\n【历史决策】")
        for item in ranked_decisions:
            _append_item(parts, item, seq_map=seq_map, meta=_decision_meta(item, seq_map))

    comparison: list[str] = []
    if current_fact is not None:
        comparison = preview_comparison(
            state, current_fact, seq_map, meeting_topics=_meeting_topics(meetings)
        )
        if comparison:
            parts.append("\n【历史对照素材】")
            for line in comparison:
                parts.append(f"- {line}")

    return "\n".join(parts).strip(), comparison


__all__ = ["build_memory_context", "preview_comparison"]
