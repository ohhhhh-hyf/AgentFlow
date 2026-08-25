"""把老师重点映射到已有 Catalog KP，并算出本次 S/A/B/C。"""
from __future__ import annotations

import re
from typing import Any

_SENT_SPLIT = re.compile(r"(?<=[。！？；;\n])")
_STRONG = ("必考", "一定出", "每届必出", "必须背", "务必掌握", "拉开分差", "一定要会", "年年有")
_MEDIUM = ("重点", "考到的概率", "考到概率", "着重", "要会")
_LIGHT = ("了解一下", "了解即可", "有印象", "了解就行", "有个印象")
_EXAM_STRONG = ("必考", "每届必出", "年年有", "一定出", "出大题")
_EXAM_MID = ("选择题", "填空", "选择填空", "出现过", "证明题", "计算题", "简答", "判断题", "论述")
_ERROR = ("不能", "不要", "陷阱", "反例", "慎", "容易错", "混淆", "误用", "漏")
_COUNT_RE = re.compile(r"([0-9]+|十[一二三四五六七八九]?|[一二三四五六七八九两])\s*道")
_CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_EXAM_RANK = {"none": 0, "weak": 1, "medium": 2, "strong": 3}


def _clean(text: object) -> str:
    return " ".join(str(text or "").split()).strip()


def _compact(text: object) -> str:
    blob = re.sub(r"\s+", "", str(text or "")).lower()
    return blob.replace("比", "/")


def _norm(text: object) -> str:
    return re.sub(r"[的地得与和及/]", "", _compact(text))


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_clean(x) for x in value if _clean(x)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def flatten_points(catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    if not catalog:
        return points
    for chapter in catalog.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for topic in chapter.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            for point in topic.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                if str(point.get("node_status") or "active") in {"merged", "deprecated"}:
                    continue
                if not _clean(point.get("id")) or not _clean(point.get("name")):
                    continue
                if _is_exam_pack(point.get("name") or ""):
                    continue
                row = dict(point)
                row["chapter"] = _clean(point.get("chapter")) or _clean(chapter.get("name"))
                row["topic"] = _clean(point.get("topic")) or _clean(topic.get("name"))
                points.append(row)
    return points


def _stems(name: str) -> list[str]:
    raw = _clean(name)
    out = [raw]
    for suffix in (
        "的定义",
        "的概念",
        "的性质",
        "的分类",
        "的一般方法",
        "的计算方法",
        "的常用技巧",
        "的应用",
        "判断流程",
        "典型例子",
        "替换规则",
    ):
        if raw.endswith(suffix) and len(raw) - len(suffix) >= 3:
            out.append(raw[: -len(suffix)])
    numbered = re.match(r"^第[一二三四五六七八九十0-9]+个(.+)$", raw)
    if numbered and len(_compact(numbered.group(1))) >= 4:
        out.append(numbered.group(1))
    kinded = re.match(r"^第[一二三四五六七八九十0-9]+类(.+)$", raw)
    if kinded and len(_compact(kinded.group(1))) >= 3:
        out.append(kinded.group(1))
    return out


def _is_exam_pack(name: str) -> bool:
    """卷面包装名不是可复习知识点，避免抢走真正被点名的点。"""
    raw = _clean(name)
    if raw in {"高频考点", "考点汇总", "期末复习", "复习建议", "考法提示"}:
        return True
    return bool(re.search(r"(综合题|判断题|选择题|填空题|应用题)$", raw))


def _uniq_needles(names: list[str], *, min_len: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = _compact(name)
        if len(key) < min_len or key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _name_needles(point: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for name in [_clean(point.get("name")), *_as_list(point.get("aliases"))]:
        names.extend(_stems(name))
    return _uniq_needles(names, min_len=3)


def _needles(point: dict[str, Any]) -> list[str]:
    names = list(_name_needles(point))
    names.extend(_as_list(point.get("knowledge_items")))
    return _uniq_needles(names, min_len=3)


def _hit_in(text: str, compact: str, needle: str) -> bool:
    raw = _clean(needle)
    if len(raw) < 3:
        return False
    if raw in text:
        return True
    key = _compact(raw)
    if len(key) >= 3 and key in compact:
        return True
    folded = _norm(raw)
    return len(folded) >= 3 and folded in _norm(text)


def _sentences(teacher: str) -> list[str]:
    parts = [_clean(p) for p in _SENT_SPLIT.split(teacher or "")]
    return [p for p in parts if len(p) >= 4]


def _emphasis(sentences: list[str]) -> int:
    blob = "".join(sentences)
    if any(mark in blob for mark in _LIGHT) and not any(mark in blob for mark in _STRONG):
        return 1
    if any(mark in blob for mark in _STRONG):
        return 3
    if any(mark in blob for mark in _MEDIUM):
        return 2
    return 1 if sentences else 0


def _exam_signal(sentences: list[str]) -> str:
    blob = "".join(sentences)
    if any(mark in blob for mark in _EXAM_STRONG):
        return "strong"
    if any(mark in blob for mark in _EXAM_MID):
        return "medium"
    if sentences:
        return "weak"
    return "none"


def _errors(sentences: list[str]) -> str:
    hits = [sent for sent in sentences if any(mark in sent for mark in _ERROR)]
    return " ".join(hits[:2])


def _focus_items(point: dict[str, Any], sentences: list[str]) -> list[str]:
    blob = "".join(sentences)
    compact = _compact(blob)
    found: list[str] = []
    for item in _as_list(point.get("knowledge_items")):
        if _hit_in(blob, compact, item) and item not in found:
            found.append(item)
    return found


def _is_light(blob: str) -> bool:
    if any(mark in blob for mark in _LIGHT):
        return True
    return bool(re.search(r"了解.{0,12}(一下|即可|就行|就好)", blob or ""))


def _name_span(sent: str, point: dict[str, Any]) -> int:
    compact = _compact(sent)
    spans = [len(_compact(n)) for n in _name_needles(point) if _hit_in(sent, compact, n)]
    return max(spans) if spans else 0


def _item_span(sent: str, point: dict[str, Any]) -> int:
    compact = _compact(sent)
    spans = [
        len(_compact(n))
        for n in _as_list(point.get("knowledge_items"))
        if len(_compact(n)) >= 4 and _hit_in(sent, compact, n)
    ]
    return max(spans) if spans else 0


def _family_key(point: dict[str, Any]) -> str:
    raw = _clean(point.get("name"))
    kinded = re.match(r"^第[一二三四五六七八九十0-9]+类(.+)$", raw)
    if kinded:
        raw = kinded.group(1)
    for suffix in ("判断流程", "典型例子", "的补定义", "替换规则", "的计算方法", "的常用技巧"):
        if raw.endswith(suffix) and len(raw) - len(suffix) >= 3:
            raw = raw[: -len(suffix)]
            break
    return _compact(raw)


def _drop_contained_names(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同句并列命中时，短名被长名包含则丢掉短名，避免「考点」抢走整块必考。"""
    names = [_compact(p.get("name")) for p in points]
    keep: list[dict[str, Any]] = []
    for point, name in zip(points, names):
        if any(name != other and name in other for other in names):
            continue
        keep.append(point)
    return keep or points


def _collapse_family(sent: str, points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一族知识点只留一个代表，避免「第一类/第二类/流程」同时占满重点。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        groups.setdefault(_family_key(point), []).append(point)
    for short in list(groups):
        for long in list(groups):
            if short != long and short in long and short in groups and long in groups:
                groups[short].extend(groups.pop(long))
    compact = _norm(sent)
    out: list[dict[str, Any]] = []
    for members in groups.values():
        if len(members) == 1:
            out.extend(members)
            continue
        out.append(
            max(
                members,
                key=lambda p: (
                    1 if _norm(p.get("name")) in compact else 0,
                    1 if any(tok in _clean(p.get("name")) for tok in ("流程", "分类", "方法", "规则")) else 0,
                    int(str(p.get("importance") or 0) or 0),
                    int(str(p.get("teacher_emphasis") or 0) or 0),
                    -len(_clean(p.get("name"))),
                ),
            )
        )
    return out


def _owned_sentences(sentences: list[str], points: list[dict[str, Any]]) -> dict[str, list[str]]:
    """一句老师原话只归最具体的 KP。"""
    owned: dict[str, list[str]] = {_clean(p.get("id")): [] for p in points}
    for sent in sentences:
        named = [p for p in points if _name_span(sent, p) > 0]
        if named:
            compact_sent = _compact(sent)
            explicit = [
                p for p in named
                if _compact(p.get("name")) in compact_sent
            ]
            cands = _collapse_family(sent, _drop_contained_names(explicit or named))
        else:
            scored = [(p, _item_span(sent, p)) for p in points]
            scored = [(p, span) for p, span in scored if span > 0]
            if not scored:
                continue
            best = max(span for _p, span in scored)
            cands = [point for point, span in scored if span == best]
            cands = [
                max(cands, key=lambda p: (int(str(p.get("importance") or 0) or 0), len(_clean(p.get("name")))))
            ]
        for point in cands:
            owned.setdefault(_clean(point.get("id")), []).append(sent)
    return owned


def activate_from_catalog(catalog: dict[str, Any] | None) -> list[dict[str, Any]]:
    """无老师重点时：按目录 importance 激活 KP，不做老师原话匹配。

    只出 S/A/B：importance < 3 的低重要性知识点不进入本次清单
    （无老师语境下不存在「老师轻点」的补充语义，避免出现悬空的 C/补充档）。
    """
    points = flatten_points(catalog)
    activated: list[dict[str, Any]] = []
    for point in points:
        try:
            importance = int(str(point.get("importance") or 3) or 3)
        except (TypeError, ValueError):
            importance = 3
        if importance < 3:
            continue
        row = dict(point)
        row["session_emphasis"] = "0"
        row["session_focus_items"] = _as_list(point.get("knowledge_items"))[:3]
        row["session_exam_signal"] = str(point.get("exam_signal") or "none")
        row["session_error_signal"] = ""
        row["session_difficulty_signal"] = ""
        row["session_related_points"] = []
        row["session_quotes"] = []
        row["session_practice_count"] = ""
        row["session_special_requirement"] = ""
        row["_light"] = False
        row["_score"] = _raw_score(row)
        activated.append(row)
    # 分位定档：前 20%→S、20-50%→A、50-80%→B、后 20%→DROP
    _quantile_assign(activated, allow_c=False)
    # DROP 硬约束：importance≥4 提到 B（长期重要性不因分层消失），只真丢 imp3
    kept: list[dict[str, Any]] = []
    for row in activated:
        if row["session_priority"] == "DROP":
            if _rank(row.get("importance")) >= 4:
                row["session_priority"] = "B"
                kept.append(row)
            continue
        kept.append(row)
    activated[:] = kept
    _cap_priorities(
        activated,
        s_max=8,
        a_max=8,
        b_max=10,
        allow_c=False,
        drop_b=True,  # 无老师重点：S/A 超限降档，B 超限直接丢弃，只有 S/A/B
    )
    activated.sort(
        key=lambda p: (
            {"S": 0, "A": 1, "B": 2, "C": 3}.get(p.get("session_priority"), 9),
            -p.get("_score", 0),
        )
    )
    return activated


def activate_points(catalog: dict[str, Any] | None, teacher: str) -> list[dict[str, Any]]:
    """有老师文本时激活：importance≥3 的知识点都出卡（老师没点名也保留，
    按基础分排）；老师点到的再按语气提档/降档。"""
    points = flatten_points(catalog)
    teacher = teacher or ""
    if not teacher.strip():
        return activate_from_catalog(catalog)
    sentences = _sentences(teacher)
    owned = _owned_sentences(sentences, points)
    activated: list[dict[str, Any]] = []

    for point in points:
        hits = list(owned.get(_clean(point.get("id"))) or [])
        try:
            importance = int(str(point.get("importance") or 3) or 3)
        except (TypeError, ValueError):
            importance = 3
        if not hits and importance < 3:
            continue  # 没被老师点到且重要性低 → 不出卡
        row = dict(point)
        row["_mentioned"] = bool(hits)
        if hits:
            row["session_emphasis"] = str(_emphasis(hits))
            row["session_focus_items"] = _focus_items(point, hits)
            row["session_exam_signal"] = _exam_signal(hits)
            err_sents = [
                sent
                for sent in hits
                if any(mark in sent for mark in _ERROR)
            ]
            row["session_error_signal"] = _errors(err_sents or hits)
            row["session_difficulty_signal"] = (
                "hard" if any(x in "".join(hits) for x in ("拉开分差", "较难", "难点")) else ""
            )
            row["session_related_points"] = _related_in_hits(point, hits, points)
            row["session_quotes"] = [_clean(sent) for sent in hits[:3] if _clean(sent)]
            blob = "".join(hits)
            row["_light"] = _is_light(blob) and not any(mark in blob for mark in _STRONG)
        else:
            row["session_emphasis"] = "0"
            row["session_focus_items"] = _as_list(point.get("knowledge_items"))[:3]
            row["session_exam_signal"] = str(point.get("exam_signal") or "none")
            row["session_error_signal"] = ""
            row["session_difficulty_signal"] = ""
            row["session_related_points"] = []
            row["session_quotes"] = []
            row["_light"] = False
        row["session_practice_count"] = ""
        row["session_special_requirement"] = ""
        row["_score"] = _raw_score(row)
        activated.append(row)

    # 分位定档：前 20%→S、20-50%→A、50-80%→B、后 20%→C（补充表）
    _quantile_assign(activated, allow_c=True)
    # 硬约束：
    # 1) 被点名（_mentioned）→ 不低于 B（轻提也不落补充表，老师点过=本次相关）
    # 2) importance≥5 且老师原话含强词（必考等）→ 强制 S（明显核心不被分位挤掉）
    for row in activated:
        if not row.get("_mentioned"):
            continue
        if row["session_priority"] == "C":
            row["session_priority"] = "B"
        blob = "".join(row.get("session_quotes") or [])
        if _rank(row.get("importance")) >= 5 and any(
            mark in blob for mark in _STRONG
        ):
            row["session_priority"] = "S"
    selected_ids = {_clean(p.get("id")) for p in activated}
    extra: list[dict[str, Any]] = []
    for row in list(activated):
        if row.get("session_priority") not in {"S", "A"}:
            continue
        for name in _as_list(row.get("prerequisites")):
            prereq = _find_by_name(points, name)
            if not prereq or _clean(prereq.get("id")) in selected_ids:
                continue
            add = dict(prereq)
            add["session_emphasis"] = "0"
            add["session_focus_items"] = []
            add["session_exam_signal"] = "none"
            add["session_error_signal"] = ""
            add["session_difficulty_signal"] = ""
            add["session_related_points"] = []
            add["session_quotes"] = []
            add["session_practice_count"] = ""
            add["session_special_requirement"] = ""
            add["_light"] = False
            add["_prereq_of"] = _clean(row.get("name"))
            add["_score"] = _raw_score(add) + 8
            add["session_priority"] = "B"
            extra.append(add)
            selected_ids.add(_clean(add.get("id")))
    activated.extend(extra)
    _cap_priorities(
        activated,
        s_max=8,
        a_max=8,
        b_max=10,
        allow_c=True,  # 有老师重点：S/A 超限降档，B 超 10 降 C 作为补充
    )
    _attach_session_practice(activated, teacher)
    activated.sort(key=lambda p: ({"S": 0, "A": 1, "B": 2, "C": 3}.get(p.get("session_priority"), 9), -p.get("_score", 0)))
    return activated


def _related_in_hits(
    point: dict[str, Any], hits: list[str], points: list[dict[str, Any]]
) -> list[str]:
    """同一句老师原话里点到的其他 Catalog KP，用作本次组合关系。"""
    mine = _clean(point.get("id"))
    found: list[str] = []
    for sent in hits:
        compact = _compact(sent)
        for other in points:
            if _clean(other.get("id")) == mine:
                continue
            names = [_clean(other.get("name")), *_as_list(other.get("aliases"))]
            if any(_hit_in(sent, compact, name) for name in names):
                label = _clean(other.get("name"))
                if label and label not in found:
                    found.append(label)
    return found


def _find_by_name(points: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    want = _compact(name)
    for point in points:
        if _compact(point.get("name")) == want:
            return point
        if want in {_compact(a) for a in _as_list(point.get("aliases"))}:
            return point
    return None


def _raw_score(point: dict[str, Any]) -> int:
    """排序/封顶用分：importance 基础分 + 老师提到/强调加分 + 考试信号 + 缺项。"""
    importance = int(str(point.get("importance") or 3) or 3)
    hist = int(str(point.get("teacher_emphasis") or 0) or 0)
    exam = _EXAM_RANK.get(str(point.get("session_exam_signal") or "none"), 0)
    catalog_exam = _EXAM_RANK.get(str(point.get("exam_signal") or "none"), 0)
    missing = min(4, len(_as_list(point.get("note_missing_items"))))
    mentioned = 1 if point.get("_mentioned") else 0
    blob = "".join(point.get("session_quotes") or [])
    strong = 1 if any(mark in blob for mark in _STRONG) else 0
    return (
        importance * 8 + mentioned * 10 + strong * 15
        + hist * 5 + exam * 8 + catalog_exam * 4 + missing * 3
    )


def _rank(value: Any, default: int = 3, lo: int = 1, hi: int = 5) -> int:
    """枚举/数值归一化到 [lo, hi]；缺失或非法取 default。"""
    try:
        n = int(str(value or "") or default)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _quantile_assign(rows: list[dict[str, Any]], *, allow_c: bool) -> None:
    """按综合分 _score 分位定档：前 20%→S、20-50%→A、50-80%→B、后 20%→C/DROP。

    - 边界同分并档（不拆散同分组，切点向后拉到同分区间末尾）
    - 少于 5 个点退化：最高分→S、次高→A、其余→B（小目录也分层）
    - allow_c=True（有老师）：后 20% 记 C（补充表）；否则记 DROP（调用方过滤）
    就地改 row["session_priority"]。
    """
    n = len(rows)
    srt = sorted(rows, key=lambda r: -int(r.get("_score") or 0))
    if n < 5:
        for i, r in enumerate(srt):
            r["session_priority"] = "S" if i == 0 else "A" if i == 1 else "B"
        return

    def cut(frac: float) -> int:
        idx = int(n * frac)
        if idx <= 0:
            return 0
        if idx >= n:
            return n
        score = int(srt[idx - 1].get("_score") or 0)
        while idx < n and int(srt[idx].get("_score") or 0) == score:
            idx += 1
        return idx

    s_end = cut(0.20)
    a_end = cut(0.50)
    b_end = cut(0.80)
    for i, r in enumerate(srt):
        if i < s_end:
            r["session_priority"] = "S"
        elif i < a_end:
            r["session_priority"] = "A"
        elif i < b_end:
            r["session_priority"] = "B"
        else:
            r["session_priority"] = "C" if allow_c else "DROP"


def _cap_priorities(
    rows: list[dict[str, Any]],
    *,
    s_max: int = 5,
    a_max: int = 5,
    b_max: int = 4,
    allow_c: bool = True,
    drop_b: bool = False,
) -> None:
    """档位人数封顶，多出来的按分数往下降，避免目录一碎清单就膨胀。

    - allow_c=True（有老师重点）：B 超限降 C（老师轻点语义）
    - allow_c=False 且 drop_b=True（无老师重点）：B 超限按分数直接丢弃
      ——无老师语境下「补充」档没有语义，B 里分数最低的直接不进入清单。
    """

    def dedupe(grade: str, nxt: str) -> None:
        pool = [row for row in rows if row.get("session_priority") == grade]
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in pool:
            groups.setdefault(_family_key(row), []).append(row)
        for short in list(groups):
            for long in list(groups):
                if short != long and short in long and short in groups and long in groups:
                    groups[short].extend(groups.pop(long))
        for members in groups.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda row: -int(row.get("_score") or 0))
            for row in members[1:]:
                row["session_priority"] = nxt

    def demote(grade: str, nxt: str, limit: int) -> None:
        pool = [row for row in rows if row.get("session_priority") == grade]
        pool.sort(key=lambda row: -int(row.get("_score") or 0))
        for row in pool[limit:]:
            row["session_priority"] = nxt

    dedupe("S", "A")
    demote("S", "A", s_max)
    dedupe("A", "B")
    demote("A", "B", a_max)
    if allow_c:
        dedupe("B", "C")
        demote("B", "C", b_max)
    elif drop_b:
        pool = [row for row in rows if row.get("session_priority") == "B"]
        pool.sort(key=lambda row: -int(row.get("_score") or 0))
        for row in pool[b_max:]:
            rows.remove(row)


def _to_count(raw: str) -> str:
    text = (raw or "").strip()
    if text.isdigit():
        return str(int(text))
    if text in _CN_NUM:
        return str(_CN_NUM[text])
    return ""


def _attach_session_practice(rows: list[dict[str, Any]], teacher: str) -> None:
    """从老师原话里抽题量和书写要求，按命中句或强调档挂到对应 KP。"""
    for row in rows:
        row["session_practice_count"] = row.get("session_practice_count") or ""
        row["session_special_requirement"] = row.get("session_special_requirement") or ""
    for sent in _sentences(teacher):
        compact = _compact(sent)
        hit_rows = [
            row
            for row in rows
            if any(_hit_in(sent, compact, needle) for needle in _needles(row))
        ]
        if any(mark in sent for mark in ("书写", "规范")):
            for row in hit_rows:
                row["session_special_requirement"] = "writing"
        for match in _COUNT_RE.finditer(sent):
            count = _to_count(match.group(1))
            if not count:
                continue
            if hit_rows:
                for row in hit_rows:
                    row["session_practice_count"] = count
                continue
            left = sent[: match.start()]
            last_strong = max((left.rfind(mark) for mark in _STRONG), default=-1)
            last_medium = max((left.rfind(mark) for mark in _MEDIUM), default=-1)
            if last_strong < 0 and last_medium < 0:
                continue
            grade = "S" if last_strong > last_medium else "A"
            for row in rows:
                if row.get("session_priority") == grade and not row.get("session_practice_count"):
                    row["session_practice_count"] = count


