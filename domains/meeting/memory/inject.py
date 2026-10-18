"""Build high-confidence meeting memory context for generation and citations."""
from __future__ import annotations

import re
from typing import Any

from .state import _DOMAIN_ENTITIES, session_index, session_label, similar

from core.runner.text import clean_text as _clean


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
    action_texts = [
        _clean(a.get("text") if isinstance(a, dict) else a)
        for a in (getattr(fact, "action_items", None) or [])
    ]
    blob = _compact(
        " ".join([
            _clean(getattr(fact, "title", "")),
            _clean(getattr(fact, "summary", "")),
            " ".join(getattr(fact, "anchors", []) or []),
            " ".join(getattr(fact, "decisions", []) or []),
            " ".join(getattr(fact, "open_items", []) or []),
            " ".join(getattr(fact, "risks", []) or []),
            " ".join(action_texts),
            " ".join(getattr(fact, "closed_items", []) or []),
        ])
    )
    text = _compact(_clean(item.get("text")))
    if not text:
        return 0
    if text in blob or blob in text:
        return 10000
    score = 0
    for size in range(min(8, len(text)), 3, -1):
        grams = [text[i : i + size] for i in range(len(text) - size + 1)]
        hits = sum(1 for g in grams if g in blob)
        if hits:
            score = size * 100 + hits
            break
    if not score:
        return 0
    title_text = _compact(_clean(getattr(fact, "title", "")))
    if title_text and any(text[i : i + 4] in title_text for i in range(len(text) - 3)):
        score += 500
    return score


def _rank(
    items: list[dict[str, Any]],
    fact: Any | None,
    cap: int = 10,
    recent: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按事实命中门禁 + 弹性安全天花板 (cap，默认 10) 筛选待办。

    1. 信噪比质量门禁：计算 item 与 fact 的相关度。若存在相关度 > 0 的实质命中项，
       仅保留相关度 > 0 的实质命中项，杜绝零分无关项滥竽充数；
    2. 若所有待办相关度全为 0（如新业务讨论或测试环境），按最近提及（recent）与责任人排序保底；
    3. 弹性天花板：最多取 cap 条（默认 10 条），绝不超过上限。
    """
    order = {mid: i for i, mid in enumerate(recent or [])}

    def key(pair: tuple[int, dict[str, Any]]) -> tuple:
        score, item = pair
        mid = _clean(item.get("last_seen") or item.get("since") or item.get("meeting_id"))
        has_owner = bool(_clean(item.get("owner")) or _clean(item.get("timing")))
        return (-score, -order.get(mid, -1), 0 if has_owner else 1)

    scored = [(_relevance(i, fact), i) for i in items if isinstance(i, dict) and _clean(i.get("text"))]
    positive = [p for p in scored if p[0] > 0]
    candidates = positive if positive else scored
    candidates.sort(key=key)
    return [i for _, i in candidates[:cap]]


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
    scope = _topic_label_v2(item)
    if scope:
        # 原生作用域子行：渲染侧据此把历史证据限定到对应议题章节（不再全局盲扫）。
        parts.append(f"  主题：{scope}")
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
    """未决/待办 meta：``第1场·2026-09-01起，最近第2场·2026-09-08，状态 open，负责人 责任人``。

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


def _topic_label_v2(item: dict[str, Any]) -> str:
    """条目主题名：直接读原生 ``module`` / ``topic_title``，不再从文本猜词。

    为什么废弃正则猜词（2026-10 记忆 v2 改造）：旧实现从条目文本逆向猜主题名，
    会猜出「400min」「端侧」这类畸形标签（"内部专项标注还差400min" → "400min"）。
    原生字段由 state 写入端从议题树回查获得（``state._find_topic_for_item``）。
    旧数据没有原生字段 → 返回空串，该行保持原格式（不硬凑主题）。
    """
    module = _clean(item.get("module"))
    title = _clean(item.get("topic_title") or item.get("title"))
    if module and title:
        return f"{module}·{title}"
    return module or title or ""


def _fact_scope_index(fact: Any) -> list[tuple[str, str]]:
    """本场议题树 → [(条目文本, module·title)]。

    本场字符串条目（新增决策 / 已闭环）还没有 state 记录、拿不到原生字段，
    用本场议题树反查它们的主题（条目与议题同源，精确相等为主）。
    """
    index: list[tuple[str, str]] = []
    for topic in getattr(fact, "topics", None) or []:
        if not isinstance(topic, dict):
            continue
        label = _topic_label_v2(topic)
        if not label:
            continue
        texts = list(topic.get("decisions") or [])
        texts += [
            (item.get("text") if isinstance(item, dict) else "")
            for item in (topic.get("actions") or [])
        ]
        texts += list(topic.get("risks") or [])
        texts += list(topic.get("open_issues") or [])
        for value in texts:
            text = _clean(value)
            if text:
                index.append((text, label))
    return index


def _item_matches_text(
    item: dict[str, Any],
    target_text: str,
    fact_scope_index: list[tuple[str, str]] | None = None,
) -> bool:
    item_text = _clean(item.get("text"))
    target = _clean(target_text)
    if not item_text or not target:
        return False
    if similar(item_text, target):
        return True
    owner = _clean(item.get("owner"))
    has_same_owner = bool(owner and len(owner) >= 2 and owner in target)

    item_mod = _clean(item.get("module"))
    item_top = _clean(item.get("topic_title"))
    same_scope = False
    if fact_scope_index and (item_mod or item_top):
        for cand_text, label in fact_scope_index:
            if cand_text == target or target in cand_text or cand_text in target:
                if item_mod and item_mod in label:
                    same_scope = True
                    break
                if item_top and item_top in label:
                    same_scope = True
                    break

    entities_item = {e.lower() for e in _DOMAIN_ENTITIES if e.lower() in item_text.lower()}
    entities_target = {e.lower() for e in _DOMAIN_ENTITIES if e.lower() in target.lower()}
    shared_entities = entities_item & entities_target

    latin_item = {t.upper() for t in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", item_text)}
    latin_target = {t.upper() for t in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}", target)}
    shared_latin = latin_item & latin_target

    if len(shared_entities) + len(shared_latin) >= 2:
        return True
    if has_same_owner and (len(shared_entities) + len(shared_latin) >= 1):
        return True
    if same_scope and len(shared_entities) >= 1:
        return True
    c_item = "".join(ch for ch in item_text if "\u4e00" <= ch <= "\u9fff")
    c_target = "".join(ch for ch in target if "\u4e00" <= ch <= "\u9fff")
    if len(c_item) >= 4 and len(c_target) >= 4:
        for i in range(len(c_item) - 3):
            sub = c_item[i : i + 4]
            if sub in c_target and not any(
                g in sub for g in ("完成了", "已完成", "进行了", "讨论了", "优化了", "推进了")
            ):
                return True
    return False


def preview_comparison(
    state: dict[str, Any],
    fact: Any,
    seq_map: dict[str, dict[str, Any]],
) -> list[str]:
    """程序拼的历史对照（不依赖词面重合，正文锚点挂不上时它是唯一可见溯源）。

    每类给 1–3 条而不是各 1 条：实测第二场只出 4 行时，"记忆挂载"看起来几乎为空，
    而状态里其实有 19 条未决、若干闭环与风险演变可说。顺序固定：
    新增决策 / 延续事项 / 已闭环 / 风险演变，末尾追加一行计数汇总。

    每条都带**主题词**（``延续事项（网关核心架构·鉴权方案｜自第1场）``）：主题取自
    条目原生 module/topic_title（写入端从议题树回查，见 ``state._find_topic_for_item``），
    不再从文本正则猜；本场字符串条目（新增决策/已闭环）用本场议题树反查。
    旧条目没有原生字段 → 不写主题，保持原格式（不硬凑）。
    """
    lines: list[str] = []
    fact_scope_index = _fact_scope_index(fact)

    def label_for(item: dict[str, Any] | str) -> str:
        if isinstance(item, dict):
            return _topic_label_v2(item)
        text = _clean(item)
        if not text:
            return ""
        for candidate, label in fact_scope_index:
            if label and (candidate == text or similar(candidate, text)):
                return label
        return ""

    def head(topic: str, tail: str = "") -> str:
        """括号里的拼接：有主题和场次说明就 ``（主题｜说明）``，只有一个就只写那个，都没有就空。"""
        bits = [bit for bit in (topic, tail) if bit]
        return f"（{'｜'.join(bits)}）" if bits else ""

    closed_now = [_clean(x) for x in (getattr(fact, "closed_items", None) or []) if _clean(x)]

    open_candidates = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and i.get("status") == "open" and _clean(i.get("text"))
        and not any(_item_matches_text(i, c, fact_scope_index) for c in closed_now)
    ]
    ranked_open = _rank(
        open_candidates,
        fact,
        10,
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
    for decision in new_decisions[:5]:
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

    closed_hist = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and _clean(i.get("text"))
        and (
            i.get("status") == "done"
            or any(_item_matches_text(i, c, fact_scope_index) for c in closed_now)
        )
    ]
    shown_closed: set[str] = set()
    for item in closed_hist[:5]:
        text = _clean(item.get("text"))
        if text in shown_closed:
            continue
        shown_closed.add(text)
        closed_mid = _clean(item.get("closed_at"))
        when = (
            session_label(seq_map, closed_mid)
            if item.get("status") == "done" and closed_mid in seq_map
            else ""
        )
        lines.append(f"已闭环{head(label_for(item), when)}：{text}")
    for text in closed_now[:5]:
        if any(text in shown for shown in shown_closed):
            continue
        shown_closed.add(text)
        lines.append(f"已闭环{head(label_for(text))}：{text}")

    if lines:
        counts = {
            "新增决策": sum(1 for x in lines if x.startswith("新增决策")),
            "延续未决": len(seen_open),
            "已闭环": len(shown_closed),
        }
        summary = "、".join(f"{k} {v} 条" for k, v in counts.items() if v)
        lines.append(f"本场历史对照合计：{summary}")
    return lines[:25]


def build_memory_context(
    *,
    project_id: str,
    project: dict[str, Any],
    state: dict[str, Any],
    bind: Any,
    meetings: list[dict[str, Any]] | None = None,
    current_fact: Any | None = None,
    user: dict[str, Any] | None = None,
    perspective_mode: str = "objective",
    cap: int = 10,
) -> tuple[str, list[str]]:
    if not project_id or not state:
        return "", []
    seq_map = session_index(meetings or [], project_id)
    evidence = getattr(bind, "evidence", []) or []
    parts = [
        "══════════════════════════════════════════════════════════════",
        "【会议记忆】",
        f"项目：{_clean(project.get('name')) or _clean(state.get('name')) or project_id}",
    ]
    if evidence:
        parts.append("命中依据：" + "、".join(str(x) for x in evidence[:8]))
    parts.extend([
        "",
        "【项目推进背景】",
    ])

    opens = [
        i for i in list(state.get("actions") or []) + list(state.get("open_items") or [])
        if isinstance(i, dict) and (i.get("status") or "open") == "open"
    ]
    risks = [
        i for i in (state.get("risks") or [])
        if isinstance(i, dict) and i.get("status") in {"active", "mitigated", "dormant"}
    ]
    dormant = [i for i in risks if i.get("status") == "dormant"]

    recent = [str(x) for x in (state.get("recent_meetings") or []) if str(x).strip()]

    ranked_open: list[dict[str, Any]] = []
    mode_str = (perspective_mode or "objective").strip().lower()
    if mode_str == "personal" and isinstance(user, dict) and user:
        # 阶段三：个人视角多维收窄展示
        name = _clean(user.get("name"))
        raw_aliases = user.get("aliases") or []
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        aliases = {name} | {_clean(a) for a in raw_aliases if _clean(a)}
        aliases.discard("")

        fps = user.get("focus_person") or user.get("focus_persons") or []
        if isinstance(fps, str):
            fps = [fps]
        focus_persons = {_clean(p) for p in fps if _clean(p)}

        fts = (
            list(user.get("focus_thing") or user.get("focus_things") or [])
            + list(user.get("attention_points") or [])
        )
        if isinstance(fts, str):
            fts = [fts]
        focus_things = {_clean(t) for t in fts if _clean(t)}

        def is_self(it: dict[str, Any]) -> bool:
            owner = _clean(it.get("owner"))
            return bool(owner and any(a in owner or owner in a for a in aliases))

        def is_focus_p(it: dict[str, Any]) -> bool:
            owner = _clean(it.get("owner"))
            return bool(owner and any(p in owner or owner in p for p in focus_persons))

        def is_focus_t(it: dict[str, Any]) -> bool:
            t = _clean(it.get("text"))
            m = _clean(it.get("module"))
            top = _clean(it.get("topic_title"))
            blob = f"{m} {top} {t}"
            return bool(focus_things and any(ft in blob for ft in focus_things))

        group_self = [i for i in opens if is_self(i)]
        group_focus_p = [i for i in opens if not is_self(i) and is_focus_p(i)]
        group_focus_t = [i for i in opens if not is_self(i) and not is_focus_p(i) and is_focus_t(i)]

        filtered = (
            _rank(group_self, current_fact, cap=6, recent=recent)
            + _rank(group_focus_p, current_fact, cap=4, recent=recent)
            + _rank(group_focus_t, current_fact, cap=4, recent=recent)
        )
        seen_items: set[str] = set()
        deduped_personal: list[dict[str, Any]] = []
        for it in filtered:
            key = str(it.get("item_id") or it.get("text"))
            if key not in seen_items:
                seen_items.add(key)
                deduped_personal.append(it)
        if deduped_personal:
            ranked_open = deduped_personal[:6]
        else:
            ranked_open = _rank(opens, current_fact, cap=2, recent=recent)
    else:
        # 客观模式安全截断至 Top-8~10 (默认 cap=10)
        ranked_open = _rank(opens, current_fact, cap=cap, recent=recent)

    if ranked_open:
        for item in ranked_open:
            _append_item(parts, item, seq_map=seq_map, meta=_open_meta(item, seq_map))
    elif dormant:
        parts.append("\n【风险演变】")
        for item in _rank(dormant, current_fact, 1, recent):
            _append_item(parts, item, seq_map=seq_map, meta=_risk_meta(item, seq_map))

    comparison: list[str] = []
    if current_fact is not None:
        comparison = preview_comparison(state, current_fact, seq_map)

    parts.append("══════════════════════════════════════════════════════════════")
    return "\n".join(parts).strip(), comparison


__all__ = ["build_memory_context", "preview_comparison"]

