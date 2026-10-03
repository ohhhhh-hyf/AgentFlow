"""Project state: object lifecycle, events, session numbers."""
from __future__ import annotations

import re
from typing import Any

from .extract import MeetingFact
from core.runner.text import clean_text as _clean


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def similar(left: str, right: str) -> bool:
    a, b = _compact(left), _compact(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    limit = min(12, len(a), len(b))
    for size in range(limit, 4, -1):
        grams = {a[i:i + size] for i in range(len(a) - size + 1)}
        if any(gram in b for gram in grams):
            return True
    return False


def _quote(fact: Any, kind: str, text: str) -> str:
    for item in getattr(fact, "quotes", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == kind and similar(str(item.get("text") or ""), text):
            return _clean(item.get("quote"))
    return ""


def _merge_unique(old: list[str], new: list[str], cap: int = 24) -> list[str]:
    out: list[str] = []
    for item in list(old or []) + list(new or []):
        text = _clean(item)
        if text and text not in out:
            out.append(text)
    return out[:cap]


def _next_id(rows: list[dict[str, Any]], prefix: str) -> str:
    n = 0
    for row in rows:
        mid = _clean(row.get("item_id"))
        if not mid.startswith(prefix):
            continue
        tail = mid[len(prefix):].lstrip("_")
        try:
            n = max(n, int(tail))
        except ValueError:
            continue
    return f"{prefix}{n + 1}"


def _touch(row: dict[str, Any], fact: Any, *, quote_kind: str, text: str) -> None:
    row["last_seen"] = fact.meeting_id
    row["meeting_title"] = _clean(fact.title) or row.get("meeting_title") or ""
    if _clean(getattr(fact, "time", "")):
        row["time"] = _clean(fact.time)
    row["time_source"] = getattr(fact, "time_source", "") or row.get("time_source") or "unknown"
    quote = _quote(fact, quote_kind, text)
    if quote:
        row["quote"] = quote


def _new_item(
    fact: Any,
    *,
    item_id: str,
    text: str,
    status: str,
    quote_kind: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "item_id": item_id,
        "text": text,
        "status": status,
        "since": fact.meeting_id,
        "last_seen": fact.meeting_id,
        "meeting_title": _clean(fact.title),
        "time": _clean(getattr(fact, "time", "")),
        "time_source": getattr(fact, "time_source", "") or "unknown",
        "quote": _quote(fact, quote_kind, text),
    }
    if extra:
        row.update(extra)
    return row


def _find_similar(rows: list[dict[str, Any]], text: str) -> dict[str, Any] | None:
    return next((r for r in rows if similar(str(r.get("text") or ""), text)), None)


# module 匹配阈值。为什么是 0.2 而不是方案文档伪代码写的 0.4：文档的设计示例要求
# “网关核心架构”与“网关鉴权优化”不被隔离，而按 _module_overlap 的覆盖率口径两者只
# 共享“网关”一个 2-gram（1/5 = 0.2）——0.4 会把文档点名要保留的场景判成隔离。
# 0.2 同时保住隔离性：“日志模块” vs “网关鉴权”交集为空，仍为 0。
_MODULE_MATCH_MIN = 0.2


def _module_overlap(a: str, b: str, n: int = 2) -> float:
    """两个 module 名的 n-gram 重合率（交集 / 较短一侧的 gram 数）。

    不用精确相等：跨场次议题 module 命名会漂移（"网关核心架构" vs "网关鉴权优化"），
    精确相等会把同一项目的条目误判成新条目、重复建档。覆盖率口径让"一长一短、
    短的被长的包含"（如 "基础架构" ⊂ "基础架构与中间件"）得 1.0。
    """
    if not a or not b:
        return 0.0
    ga = {a[i:i + n] for i in range(len(a) - n + 1)} if len(a) >= n else {a}
    gb = {b[i:i + n] for i in range(len(b) - n + 1)} if len(b) >= n else {b}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def _find_topic_for_item(
    text: str, topics: list[dict[str, Any]] | None
) -> tuple[str, str]:
    """从议题树找到包含该条目的议题，返回 (module, topic_title)。

    条目本来就由提取层从议题树拍平而来（同源），精确相等命中绝大多数；
    措辞微差用 ``similar`` 兜底。找不到返回空串 → 条目不写作用域，
    后续匹配走全局（与改造前行为一致）。
    """
    query = _clean(text)
    if not query:
        return "", ""
    for topic in topics or []:
        if not isinstance(topic, dict):
            continue
        texts = list(topic.get("decisions") or [])
        texts += [
            (item.get("text") if isinstance(item, dict) else "")
            for item in (topic.get("actions") or [])
        ]
        texts += list(topic.get("risks") or [])
        texts += list(topic.get("open_issues") or [])
        # key_points / conclusion 也要收：闭环池（_closed_items）包含这两类字段，
        # 归属回查必须与闭环池同源，否则闭环的作用域门拿不到 module，只能放行。
        key_points = topic.get("key_points")
        if isinstance(key_points, list):
            texts += [_clean(x) for x in key_points]
        texts.append(topic.get("conclusion") or "")
        for value in texts:
            candidate = _clean(value)
            if not candidate:
                continue
            if candidate == query or similar(query, candidate):
                return _clean(topic.get("module")), _clean(topic.get("title"))
    return "", ""


def _scoped_hit(
    pool: list[dict[str, Any]],
    text: str,
    module: str,
) -> dict[str, Any] | None:
    """作用域优先的条目匹配（议题内延续 / 跨议题隔离）。

    1. 条目有 module：先在同 module（2-gram 重合 ≥ ``_MODULE_MATCH_MIN``）的旧条目里找；
    2. 同域内确无同项时**不跨 module 匹配**——不同议题的同名条目各归各（验收：不误配）；
    3. 无 module 的旧条目（升级前建档）仍参与匹配：旧数据行为不变，且升级边界上
       同一件事再出现不会重复建档。
    """
    if not module:
        return _find_similar(pool, text)
    scoped = [
        row for row in pool
        if _module_overlap(module, _clean(row.get("module"))) >= _MODULE_MATCH_MIN
    ]
    if scoped:
        hit = _find_similar(scoped, text)
        if hit is not None:
            return hit
    legacy = [row for row in pool if not _clean(row.get("module"))]
    return _find_similar(legacy, text) if legacy else None


def _fill_scope(row: dict[str, Any], module: str, title: str) -> None:
    """给升级前建档的旧条目补原生作用域（只补空值，不覆盖已有归属）。"""
    if module and not _clean(row.get("module")):
        row["module"] = module
        row["topic_title"] = title or _clean(row.get("topic_title"))


_MITIGATED_RE = re.compile(r"(已解决|已缓解|已消除|风险解除|不再存在|完成整改)")
_DORMANT_AFTER = 2


def _upsert_open(
    rows: list[dict[str, Any]],
    values: list[str],
    fact: Any,
    *,
    kind: str,
    extras: list[dict[str, str]] | None = None,
    other: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """未决/待办共用入口。

    ``other``：另一条同名列表（未决 ↔ 待办）。两条列表此前互不查询，同一件事会
    以两种措辞各存一份（实测 7 组重复对），区块又在去重之后才把两者拼接 →
    同一事实占两个名额、还获得两次被锚定的机会。这里跨列表查重：
    命中对面那条就把 owner/timing/状态补到它身上，不再另存一份。
    """
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    pool = out + [r for r in (other or []) if isinstance(r, dict) and _clean(r.get("text"))]
    events: list[dict[str, Any]] = []
    extra_by_text = {
        _clean(e.get("text")): e for e in (extras or []) if _clean(e.get("text"))
    }
    for value in values:
        text = _clean(value)
        if not text:
            continue
        module, topic_title = _find_topic_for_item(
            text, getattr(fact, "topics", None) or []
        )
        hit = _scoped_hit(pool, text, module)
        meta = extra_by_text.get(text) or {}
        if hit is None:
            item_id = _next_id(out, "a" if kind == "action" else "o")
            row = _new_item(
                fact,
                item_id=item_id,
                text=text,
                status="open",
                quote_kind=kind,
                extra={
                    "kind": kind,
                    "owner": _clean(meta.get("owner")),
                    "timing": _clean(meta.get("timing")),
                    "module": module,
                    "topic_title": topic_title,
                },
            )
            out.append(row)
            pool.append(row)
            events.append({
                "type": "added",
                "item_id": item_id,
                "kind": kind,
                "text": text,
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
        else:
            prev = hit.get("status") or "open"
            _touch(hit, fact, quote_kind=kind, text=text)
            _fill_scope(hit, module, topic_title)
            if meta.get("owner"):
                hit["owner"] = _clean(meta.get("owner"))
            if meta.get("timing"):
                hit["timing"] = _clean(meta.get("timing"))
            if prev in {"done", "dropped"}:
                hit["status"] = "open"
                events.append({
                    "type": "reopened",
                    "item_id": hit.get("item_id"),
                    "kind": kind,
                    "text": text,
                    "meeting_id": fact.meeting_id,
                    "time": _clean(getattr(fact, "time", "")),
                })
    # 跨列表合并过的行不在 out 里，但它的 owner/状态已更新；out 只回自己的行
    return out[:40], events


def _scope_allows(row_module: str, event_module: str) -> bool:
    """事件（闭环/缓解）的作用域门：两侧都有原生 module 且不同域 → 不匹配。

    为什么闭环也要隔离（2026-10 验收：不同 module 的同名条目不会误配）：
    `similar` 是 4 字重合即命中的宽口径，「补充测试用例」这类同名条目在不同议题里
    会被主闭环文本连带关闭。任一侧没有原生作用域（旧数据 / 无法归属的闭环表述）
    → 放行，保持旧行为（宁可暂时留一条已完成的旧条目，不错关别的议题的同名条目）。
    """
    if not event_module or not row_module:
        return True
    return _module_overlap(event_module, row_module) >= _MODULE_MATCH_MIN


def _close_items(
    rows: list[dict[str, Any]],
    closed: list[str],
    fact: Any,
    *,
    done_status: str = "done",
    event_type: str = "done",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """本场宣告已闭环的条目改状态（不删除）。

    ``done_status``：open/action 用 ``done``，risk 用 ``mitigated``——
    风险过去没有闭环通道（只有条目文本里出现"已解决"才转 mitigated），
    实测"池子不稳定"被明确宣告解决后仍以 active 挂在【风险演变】里。
    """
    if not closed:
        return rows, []
    closed_scoped = [
        (text, _find_topic_for_item(text, getattr(fact, "topics", None) or [])[0])
        for text in (_clean(c) for c in closed)
        if text
    ]
    if not closed_scoped:
        return rows, []
    events: list[dict[str, Any]] = []
    for row in rows:
        text = _clean(row.get("text"))
        if not text or (row.get("status") == done_status):
            continue
        row_module = _clean(row.get("module"))
        if not any(
            similar(text, closed_text) and _scope_allows(row_module, closed_module)
            for closed_text, closed_module in closed_scoped
        ):
            continue
        row["status"] = done_status
        row["closed_at"] = fact.meeting_id
        _touch(row, fact, quote_kind="closed", text=text)
        events.append({
            "type": event_type,
            "item_id": row.get("item_id"),
            "kind": row.get("kind") or "open",
            "text": text,
            "meeting_id": fact.meeting_id,
            "time": _clean(getattr(fact, "time", "")),
        })
    return rows, events


def _upsert_risks(
    rows: list[dict[str, Any]],
    risks: list[str],
    fact: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    events: list[dict[str, Any]] = []
    for value in risks:
        text = _clean(value)
        if not text:
            continue
        status = "mitigated" if _MITIGATED_RE.search(text) else "active"
        module, topic_title = _find_topic_for_item(
            text, getattr(fact, "topics", None) or []
        )
        hit = _scoped_hit(out, text, module)
        if hit is None:
            item_id = _next_id(out, "r")
            out.append(_new_item(
                fact,
                item_id=item_id,
                text=text,
                status=status,
                quote_kind="risk",
                extra={"module": module, "topic_title": topic_title},
            ))
            events.append({
                "type": "risk_added" if status == "active" else "mitigated",
                "item_id": item_id,
                "kind": "risk",
                "text": text,
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
        else:
            prev = hit.get("status") or "active"
            _touch(hit, fact, quote_kind="risk", text=text)
            _fill_scope(hit, module, topic_title)
            hit["status"] = status
            if prev != status:
                events.append({
                    "type": "mitigated" if status == "mitigated" else "reopened",
                    "item_id": hit.get("item_id"),
                    "kind": "risk",
                    "text": text,
                    "meeting_id": fact.meeting_id,
                    "time": _clean(getattr(fact, "time", "")),
                })
    return out[:40], events


def _age_meetings(recent: list[str], last_seen: str) -> int:
    if not last_seen:
        return 99
    if last_seen not in recent:
        return max(len(recent), 1)
    return len(recent) - 1 - recent.index(last_seen)


def _apply_dormant(rows: list[dict[str, Any]], recent: list[str], fact: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") != "active":
            continue
        if _clean(row.get("last_seen")) == fact.meeting_id:
            continue
        if _age_meetings(recent, _clean(row.get("last_seen"))) >= _DORMANT_AFTER:
            row["status"] = "dormant"
            events.append({
                "type": "dormant",
                "item_id": row.get("item_id"),
                "kind": "risk",
                "text": _clean(row.get("text")),
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
    return events


def _upsert_decisions(
    rows: list[dict[str, Any]],
    decisions: list[str],
    fact: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out = [dict(r) for r in rows if isinstance(r, dict) and _clean(r.get("text"))]
    events: list[dict[str, Any]] = []
    for value in decisions:
        text = _clean(value)
        if not text:
            continue
        module, topic_title = _find_topic_for_item(
            text, getattr(fact, "topics", None) or []
        )
        hit = _scoped_hit(out, text, module)
        if hit is None:
            item_id = _next_id(out, "d")
            out.append({
                "item_id": item_id,
                "text": text,
                "status": "active",
                "meeting_id": fact.meeting_id,
                "last_seen": fact.meeting_id,
                "meeting_title": _clean(fact.title),
                "time": _clean(getattr(fact, "time", "")),
                "time_source": getattr(fact, "time_source", "") or "unknown",
                "quote": _quote(fact, "decision", text),
                "module": module,
                "topic_title": topic_title,
            })
            events.append({
                "type": "decision_added",
                "item_id": item_id,
                "kind": "decision",
                "text": text,
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
            continue
        prev_text = _clean(hit.get("text"))
        _touch(hit, fact, quote_kind="decision", text=text)
        _fill_scope(hit, module, topic_title)
        if hit.get("status") == "superseded":
            continue
        if prev_text == text or prev_text in _compact(text) or _compact(text) in prev_text:
            hit["status"] = "reaffirmed"
            events.append({
                "type": "reaffirmed",
                "item_id": hit.get("item_id"),
                "kind": "decision",
                "text": text,
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
        else:
            old_id = hit.get("item_id")
            hit["status"] = "superseded"
            hit["superseded_by"] = ""
            item_id = _next_id(out, "d")
            new = {
                "item_id": item_id,
                "text": text,
                "status": "active",
                "meeting_id": fact.meeting_id,
                "last_seen": fact.meeting_id,
                "meeting_title": _clean(fact.title),
                "time": _clean(getattr(fact, "time", "")),
                "time_source": getattr(fact, "time_source", "") or "unknown",
                "quote": _quote(fact, "decision", text),
                "supersedes": old_id,
                "module": module,
                "topic_title": topic_title,
            }
            hit["superseded_by"] = item_id
            out.append(new)
            events.append({
                "type": "superseded",
                "item_id": item_id,
                "kind": "decision",
                "text": text,
                "meeting_id": fact.meeting_id,
                "time": _clean(getattr(fact, "time", "")),
            })
    return out[-60:], events


def backfill_meeting_titles(state: dict[str, Any], meetings: list[dict[str, Any]]) -> dict[str, Any]:
    titles: dict[str, str] = {}
    for meeting in meetings:
        mid = _clean(meeting.get("meeting_id"))
        title = _clean(meeting.get("title"))
        if mid and title:
            titles[mid] = title
    if not titles:
        return state
    out = dict(state or {})
    for key in ("open_items", "actions", "risks", "decisions"):
        rows: list[dict[str, Any]] = []
        for item in out.get(key) or []:
            if not isinstance(item, dict):
                rows.append(item)
                continue
            row = dict(item)
            if not _clean(row.get("meeting_title")):
                mid = _clean(row.get("last_seen") or row.get("meeting_id") or row.get("since"))
                if mid in titles:
                    row["meeting_title"] = titles[mid]
            rows.append(row)
        out[key] = rows
    return out


def sort_project_meetings(meetings: list[dict[str, Any]], project_id: str) -> list[dict[str, Any]]:
    rows = [
        m for m in (meetings or [])
        if isinstance(m, dict) and _clean(m.get("project_id")) == project_id
    ]

    def key(m: dict[str, Any]) -> tuple:
        src = _clean(m.get("time_source")) or ("user" if _clean(m.get("time")) else "unknown")
        time_val = _clean(m.get("time"))
        mid = _clean(m.get("meeting_id"))
        if src == "user" and time_val:
            return (0, time_val, mid)
        return (1, mid)

    return sorted(rows, key=key)


def session_index(meetings: list[dict[str, Any]], project_id: str) -> dict[str, dict[str, Any]]:
    """meeting_id → {seq, time, title}."""
    out: dict[str, dict[str, Any]] = {}
    for i, meeting in enumerate(sort_project_meetings(meetings, project_id), start=1):
        mid = _clean(meeting.get("meeting_id"))
        if not mid:
            continue
        out[mid] = {
            "seq": i,
            "time": _clean(meeting.get("time")),
            "title": _clean(meeting.get("title")),
            "time_source": _clean(meeting.get("time_source")) or (
                "user" if _clean(meeting.get("time")) else "unknown"
            ),
        }
    return out


def session_label(seq_map: dict[str, dict[str, Any]], meeting_id: str) -> str:
    """场次标签：``第2场·2026-09-08``。

    用 ``·`` 而不是括号：这个标签会被写进注入块的括号 meta
    （``（第2场·2026-09-08起，最近…）``），括号嵌套会让渲染侧的 meta 剥离正则失效
    （实测 15/15 条条目的正文混进内部 meta，卡片上出现「（第1场（2026-09-01）起…」）。
    """
    info = seq_map.get(meeting_id) or {}
    seq = info.get("seq")
    if not seq:
        return "未知场次"
    time_val = _clean(info.get("time"))
    if time_val:
        return f"第{seq}场·{time_val}"
    return f"第{seq}场"


def update_state(state: dict[str, Any], fact: Any, project_id: str, project_name: str = "") -> dict[str, Any]:
    out = dict(state or {})
    out["project_id"] = project_id
    out["name"] = project_name or out.get("name") or project_id
    out["anchors"] = _merge_unique(out.get("anchors") or [], getattr(fact, "anchors", []) or [])

    events: list[dict[str, Any]] = [e for e in (out.get("events") or []) if isinstance(e, dict)]

    decisions, ev = _upsert_decisions(out.get("decisions") or [], getattr(fact, "decisions", []) or [], fact)
    out["decisions"] = decisions
    events.extend(ev)

    opens, ev = _upsert_open(
        out.get("open_items") or [],
        getattr(fact, "open_items", []) or [],
        fact,
        kind="open",
        other=out.get("actions") or [],  # 跨列表查重（上一场的待办）
    )
    events.extend(ev)
    action_rows = list(getattr(fact, "action_items", None) or [])
    action_texts = [_clean(a.get("text") if isinstance(a, dict) else a) for a in action_rows]
    actions, ev = _upsert_open(
        out.get("actions") or [],
        [t for t in action_texts if t],
        fact,
        kind="action",
        extras=[a for a in action_rows if isinstance(a, dict)],
        other=opens,  # 跨列表查重：同一件事不在未决/待办各存一份
    )
    events.extend(ev)

    closed = getattr(fact, "closed_items", []) or []
    opens, ev = _close_items(opens, closed, fact)
    events.extend(ev)
    actions, ev = _close_items(actions, closed, fact)
    events.extend(ev)
    out["open_items"] = opens
    out["actions"] = actions

    risks, ev = _upsert_risks(out.get("risks") or [], getattr(fact, "risks", []) or [], fact)
    events.extend(ev)
    # 风险也吃 closed_items（记 mitigated + closed_at）：此前只有"条目文本自带已解决"
    # 一条通道，闭环信号到不了风险表（实测"池子不稳定"已宣告解决仍留在 active）。
    risks, ev = _close_items(risks, closed, fact, done_status="mitigated", event_type="mitigated")
    events.extend(ev)

    recent = [str(x) for x in (out.get("recent_meetings") or []) if str(x).strip()]
    if fact.meeting_id in recent:
        recent.remove(fact.meeting_id)
    recent.append(fact.meeting_id)
    out["recent_meetings"] = recent[-8:]
    events.extend(_apply_dormant(risks, out["recent_meetings"], fact))
    out["risks"] = risks

    bits = [getattr(fact, "summary", "") or ""]
    active_open = [
        _clean(i.get("text"))
        for i in (out.get("open_items") or []) + (out.get("actions") or [])
        if isinstance(i, dict) and i.get("status") == "open"
    ]
    active_risks = [
        _clean(i.get("text"))
        for i in out.get("risks") or []
        if isinstance(i, dict) and i.get("status") == "active"
    ]
    if active_open:
        bits.append("未决：" + "；".join(active_open[:5]))
    if active_risks:
        bits.append("风险：" + "；".join(active_risks[:4]))
    out["summary"] = " ".join(bit for bit in bits if bit)[:800]
    # 事件按"最近 N 场"保留（而不是只留最近 40 条）：40 条≈一场的量，
    # 实测两场之后磁盘上只剩最后一场的审计，跨场轨迹全丢。
    keep = set(out["recent_meetings"])
    kept = [e for e in events if _clean(e.get("meeting_id")) in keep]
    out["events"] = kept[-240:]
    return out


def rebuild_state(
    meetings: list[dict[str, Any]],
    project_id: str,
    project_name: str = "",
) -> dict[str, Any]:
    """Replay meetings.jsonl so retries of the same meeting_id stay idempotent."""
    state: dict[str, Any] = {}
    for row in sort_project_meetings(meetings, project_id):
        fact = MeetingFact.from_dict(row)
        state = update_state(state, fact, project_id, project_name)
    return state


__all__ = [
    "backfill_meeting_titles",
    "rebuild_state",
    "session_index",
    "session_label",
    "similar",
    "sort_project_meetings",
    "update_state",
]
