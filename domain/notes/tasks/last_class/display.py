"""last_class —— 期末划重点复习清单 的展示层。

agent 抽取 focus_points（程度分级 + 老师原话 + 题型 + 检索词 + 掌握要求）→
supervisor 审核 → render 按学科检索学生知识库 → 生成复习清单：
- Markdown：汇总表（知识点/重要程度/题型/掌握要求）+ 每知识点区块
  （老师原话 / 考察要求 / 笔记出处 / 课件出处）
- HTML：左侧知识点正文，右侧先挂老师原话，再按相关程度挂知识库出处（专题文件优先），多的折叠。
"""
from __future__ import annotations

import json
import re
from html import escape
from typing import Any

from .charts import (
    _render_heatmap_chart,
    _render_qtype_chart,
    _render_relations_svg,
    _render_selfcheck_svg,
)
from .kb import (
    _as_list,
    _clean,
    _is_raw_dump,
    _knowledge_blurb,
    _on_topic,
    _pick_visible_kb,
    _rank_kb_sources,
    _retrieve_point,
    _soft_clean,
    _strip_dump_tail,
    _topic_tokens,
    resolve_collection,
)


def draft_from_context(approved_context: str) -> dict[str, Any]:
    """从已批准上下文解析 focus_points 草稿。"""
    blob = approved_context or ""
    for marker in ("已批准期末划重点草稿：", "已批准last_class草稿："):
        if marker in blob:
            blob = blob.split(marker, 1)[1]
            break
    start = blob.find("{")
    if start < 0:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(blob[start:])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def original_from_context(approved_context: str) -> str:
    """提取老师划重点原文（最高事实来源）。"""
    raw = approved_context or ""
    for marker in ("原文（最高事实来源）：", "原文："):
        if marker not in raw:
            continue
        body = raw.split(marker, 1)[1]
        for stop in (
            "\n\n用户画像：",
            "\n\n已审核笔记理解：",
            "\n\n已审核用户视角：",
            "\n\n已批准",
        ):
            if stop in body:
                body = body.split(stop, 1)[0]
                break
        return body.strip()
    return ""


def subject_from_context(approved_context: str) -> str:
    """提取「【学科/课程】xxx」，决定按哪个知识库集合检索。"""
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", approved_context or "")
    return m.group(1).strip() if m else ""


def user_id_from_context(approved_context: str) -> str:
    """提取「【用户ID】xxx」，决定检索哪个用户自己的知识库。"""
    m = re.search(r"【用户ID】\s*([^【】\n]+)", approved_context or "")
    return m.group(1).strip() if m else ""


def _focus_points(draft: dict[str, Any]) -> list[dict[str, Any]]:
    items = draft.get("focus_points") or []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        out.append(
            {
                "degree": str(item.get("degree") or "重点").strip(),
                "name": name,
                "quote": _clean(item.get("quote")),
                "note": _clean(item.get("note")),
                "chapter": _clean(item.get("chapter")),
                "priority_reason": _clean(item.get("priority_reason")),
                "difficulty": _clean(item.get("difficulty")),
                "mastery": _clean(item.get("mastery")),
                "prerequisites": _as_list(item.get("prerequisites")),
                "question_types": _as_list(item.get("question_types")),
                "keywords": _as_list(item.get("keywords")),
                "practice": _as_list(item.get("practice")),
                "check_points": _as_list(item.get("check_points")),
                "related_names": _as_list(item.get("related_names")),
                "explain_what": _clean(item.get("explain_what")),
                "explain_why": _clean(item.get("explain_why")),
                "explain_trap": _clean(item.get("explain_trap")),
                "explain_how": _clean(item.get("explain_how")),
            }
        )
    return out


# ── 知识库检索（按来源类型分组）────────────────────────────────

_KB_CACHE: Any = None
# ── Markdown 复习清单 ─────────────────────────────────────────

_DEGREE_LABEL = {"必考": "【必考】", "重点": "【重点】", "了解": "【了解】"}
_PRIORITY = {"必考": "高", "重点": "中", "了解": "低"}
_QTYPE_MAP = {
    "选择": "客观题",
    "填空": "客观题",
    "计算": "计算题",
    "证明": "简答题",
    "应用": "案例分析题",
}


def _chapter_of(point: dict[str, Any]) -> str:
    chapter = _clean(point.get("chapter"))
    if chapter:
        return chapter
    name = _clean(point.get("name"))
    m_name = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*[章章节]\s*([^，。；\n|]*)", name)
    if m_name:
        title = _clean(m_name.group(2))[:12]
        return f"第{m_name.group(1)}章{f' {title}' if title else ''}"
    blob = " ".join(str(point.get(k) or "") for k in ("quote", "note", "mastery"))
    patterns = (
        r"第\s*([一二三四五六七八九十\d]+)\s*[章章节]\s*([^，。；\n]*)",
        r"([一二三四五六七八九十\d]+)\s*[章章节]\s*([^，。；\n]*)",
    )
    for pat in patterns:
        m = re.search(pat, blob)
        if m:
            title = _clean(m.group(2))[:12]
            return f"第{m.group(1)}章{f' {title}' if title else ''}"
    return "未标明章节"


def _quote_basis(point: dict[str, Any], fallback: str = "老师提及") -> str:
    reason = _clean(point.get("priority_reason"))
    if reason:
        return reason[:15]
    quote = _clean(point.get("quote"))
    if quote:
        return quote[:15]
    note = _clean(point.get("note"))
    return (note[:15] if note else fallback)


def _point_priority(point: dict[str, Any]) -> str:
    return _PRIORITY.get(str(point.get("degree") or ""), "中")


def _point_qtypes(point: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in point.get("question_types") or []:
        mapped = _QTYPE_MAP.get(str(item).strip(), str(item).strip())
        if mapped and mapped not in out:
            out.append(mapped)
    if not out:
        text = " ".join(str(point.get(k) or "") for k in ("name", "note", "mastery"))
        if any(token in text for token in ("公式", "计算", "求", "推导")):
            out.append("计算题")
        else:
            out.append("客观题")
    return out[:2]


def _qtype_distribution(point: dict[str, Any]) -> list[dict[str, float]]:
    """该考点的题型分布（每个知识点的饼图数据，权重均分）。

    优先用 agent 抽取的原始题型（选择/填空/计算/证明/应用），
    不足 2 个时回退到映射后的概括题型。
    """
    raw: list[str] = []
    for item in point.get("question_types") or []:
        t = str(item).strip()
        if t and t not in raw:
            raw.append(t)
    if len(raw) < 2:
        raw = _point_qtypes(point)
    if len(raw) < 2:
        return []
    share = round(100.0 / len(raw), 1)
    out = [{"label": t, "value": share} for t in raw]
    # 修正浮点余数，保证合计 100
    drift = 100.0 - sum(item["value"] for item in out)
    out[-1]["value"] = round(out[-1]["value"] + drift, 1)
    return out


def _difficulty(priority: str, point: dict[str, Any]) -> str:
    explicit = _clean(point.get("difficulty"))
    text = " ".join(
        str(point.get(k) or "")
        for k in ("name", "quote", "note", "priority_reason", "mastery")
    )
    if any(t in text for t in ("拉开分差", "压轴", "难点", "较难", "综合性强")):
        return "较难"
    if explicit in {"简单", "中等", "较难"}:
        return explicit
    if priority == "高" and any(t in text for t in ("证明", "推导", "综合", "应用")):
        return "较难"
    if priority in {"高", "中"}:
        return "中等"
    return "简单"


def _compact_sentence(text: str, limit: int) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _strip_file_prefix(text: str, source_file: str) -> str:
    """去掉检索原文开头的来源文件名前缀（docx/ppt 内容常以标题=文件名开头）。"""
    raw = _soft_clean(text)
    file = _clean(source_file)
    if not file:
        return raw
    first, nl, rest = raw.partition("\n")
    for prefix in (file, file.rsplit(".", 1)[0]):
        if prefix and first.startswith(prefix):
            first = first[len(prefix):].lstrip(" ：:-—，。")
            return f"{first}{nl}{rest}".strip()
        if prefix and raw.startswith(prefix):
            return raw[len(prefix):].lstrip(" ：:-—，。\n")
    return raw


def _join_unique(*parts: str) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for raw in parts:
        text = _clean(raw)
        if not text:
            continue
        key = re.sub(r"\s+", "", text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text.rstrip("。；;") + "。")
    return "".join(out)


def _core_explain(point: dict[str, Any], blurb: dict[str, Any] | None) -> list[str]:
    """核心精讲：是什么 / 为什么 / 易错与变形 / 怎么办。LLM 正文优先，库摘录补定义。"""
    name = _clean(point.get("name"))
    note = _clean(point.get("note"))
    mastery = _clean(point.get("mastery"))
    reason = _clean(point.get("priority_reason"))
    quote = _clean(point.get("quote"))
    practice = _as_list(point.get("practice"))
    checks = _as_list(point.get("check_points"))
    qtypes = "、".join(_point_qtypes(point))
    difficulty = _clean(point.get("difficulty")) or _difficulty(_point_priority(point), point)
    degree = _clean(point.get("degree")) or "重点"
    blurb_text = ""
    if blurb and blurb.get("excerpt"):
        blurb_text = _strip_file_prefix(
            _clean(blurb.get("excerpt")), _clean(blurb.get("file"))
        )

    _CANNED_WHAT = "对着看时把定义/公式、适用条件和常见变形放在一起，别只背结论。"
    what = _strip_dump_tail(_clean(point.get("explain_what")).replace(_CANNED_WHAT, ""))
    if len(what) < 40:
        fill = "" if _is_raw_dump(blurb_text) else _clean(blurb_text)
        what = _join_unique(
            what,
            fill if fill and not _is_raw_dump(fill) else "",
            note if note and note not in what else "",
            f"{name}先把定义、关键式子和使用边界钉死，再去对老师点过的变形。",
        )

    why = _clean(point.get("explain_why"))
    if len(why) < 50:
        why = _join_unique(
            why,
            f"老师强调{reason}" if reason else "",
            f"课堂原话点到：{quote}" if quote and quote[:20] not in why else "",
            f"考试多半落在{qtypes}，按{difficulty}准备。" if qtypes else f"按{difficulty}准备。",
            f"{degree}级考点，丢了会直接少一块卷面分。",
        )

    trap = _clean(point.get("explain_trap"))
    if len(trap) < 40:
        trap_bits = []
        if note and any(t in note for t in ("不能", "不要", "易错", "陷阱", "反例", "慎", "乱换", "变形", "先提")):
            trap_bits.append(note)
        if quote and len(quote) >= 16:
            trap_bits.append(f"课堂点过：{quote}")
        trap = _join_unique(
            trap,
            *trap_bits,
            f"{name}不要只背结论，先核对老师强调的限制条件和变形入口。",
        )

    how = _clean(point.get("explain_how"))
    if len(how) < 50:
        steps = [mastery] if mastery else []
        steps.extend(practice[:3])
        steps.extend(checks[:2])
        if not steps:
            load = "8-10 道" if degree == "必考" else ("4-6 道" if degree == "重点" else "1 道识别题")
            steps = [
                f"默写{name}的结论、公式和限制条件",
                f"练{load}（先基础再变形）",
                "对答案后回看错因，错题收进错题本",
            ]
        how = " → ".join(_clean(s) for s in steps if _clean(s))

    return [what, why, trap, how]


def _build_relations(points: list[dict[str, Any]]) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """构建考点关系：前置依赖边 + 关联对比边（关键词/同章兜底）。

    返回 (prereq_edges, relate_edges)：
    - prereq_edges: [(前置考点, 考点)]，方向 先掌握A再攻B
    - relate_edges: [(A, B, 关系说明)]（无方向）
    """
    names = [_clean(p.get("name")) for p in points]
    prereq_edges: list[tuple[str, str]] = []
    relate_edges: list[tuple[str, str, str]] = []
    seen_rel: set[tuple[str, str]] = set()

    def _resolve(term: str) -> str | None:
        term = _clean(term)
        if not term or len(term) < 2:
            return None
        for n in names:
            if term == n or (len(term) >= 3 and (term in n or n in term)):
                return n
        return None

    # 前置依赖：prerequisites 命中其他考点
    for p in points:
        pn = _clean(p.get("name"))
        for pr in p.get("prerequisites") or []:
            target = _resolve(pr)
            if target and target != pn and (target, pn) not in prereq_edges:
                prereq_edges.append((target, pn))
    # 互为前置的改成关联，避免双箭头打架
    both = {(a, b) for a, b in prereq_edges if (b, a) in prereq_edges}
    if both:
        prereq_edges = [(a, b) for a, b in prereq_edges if (a, b) not in both]
        for a, b in both:
            if a < b:
                key = (a, b)
                if key not in seen_rel:
                    seen_rel.add(key)
                    relate_edges.append((a, b, "互相支撑"))
    # 了解 → 同章必考/重点，补一条「打底」边
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for p in points:
        by_chapter.setdefault(_chapter_of(p), []).append(p)
    for members in by_chapter.values():
        bases = [_clean(p.get("name")) for p in members if p.get("degree") == "了解"]
        targets = [
            _clean(p.get("name"))
            for p in members
            if p.get("degree") in {"必考", "重点"}
        ]
        for base in bases:
            for tgt in targets[:2]:
                if base and tgt and (base, tgt) not in prereq_edges:
                    prereq_edges.append((base, tgt))
    # 显式关联：related_names
    for p in points:
        pn = _clean(p.get("name"))
        for rn in p.get("related_names") or []:
            other = _resolve(rn)
            if other and other != pn:
                key = tuple(sorted((pn, other)))
                if key not in seen_rel:
                    seen_rel.add(key)
                    relate_edges.append((pn, other, "对比/配套"))
    # 兜底：关键词重叠
    kw_map: dict[str, list[str]] = {}
    for p in points:
        for kw in p.get("keywords") or []:
            kw = _clean(kw)
            if len(kw) >= 2:
                kw_map.setdefault(kw, []).append(_clean(p.get("name")))
    for owners in kw_map.values():
        uniq = list(dict.fromkeys(owners))
        if len(uniq) >= 2:
            for i in range(len(uniq)):
                for j in range(i + 1, min(i + 3, len(uniq))):
                    key = tuple(sorted((uniq[i], uniq[j])))
                    if key not in seen_rel:
                        seen_rel.add(key)
                        relate_edges.append((uniq[i], uniq[j], "同考法"))
    return prereq_edges[:16], relate_edges[:14]


def _relations_markdown(
    prereq_edges: list[tuple[str, str]],
    relate_edges: list[tuple[str, str, str]],
) -> list[str]:
    """考点关系图说明：细节画在 SVG 里，这里只留一句读法。"""
    if not prereq_edges and not relate_edges:
        return []
    return ["实线箭头：先掌握左边/上游，再攻下游。虚线：对比或同考法。"]


def _heatmap(points: list[dict[str, Any]]) -> dict[str, Any]:
    """考点分布热力图数据，分组粒度自适应。

    - 章节数 >= 2：按章节聚合（饼图展示各章占比）
    - 章节数 <= 1（只有一章或未标明章节）：按知识点分组（饼图展示各考点占比），
      避免"只有一段 100%"的无意义饼图。
    返回 {"mode": "chapter"|"point", "rows": [{label, weight, density, basis}]}
    """
    chapters = {_chapter_of(p) for p in points}
    use_chapter = len(chapters) >= 2
    return _heatmap_by(points, by_chapter=use_chapter)


def _heatmap_by(points: list[dict[str, Any]], *, by_chapter: bool) -> dict[str, Any]:
    score_map = {"必考": 4, "重点": 2, "了解": 1}
    groups: dict[str, dict[str, Any]] = {}

    def _key(point: dict[str, Any]) -> str:
        return _chapter_of(point) if by_chapter else _clean(point.get("name"))

    for point in points:
        key = _key(point)
        item = groups.setdefault(key, {"score": 0, "count": 0, "basis": []})
        item["score"] += score_map.get(str(point.get("degree") or ""), 2)
        item["count"] += 1
        item["basis"].append(_quote_basis(point))

    explicit = _explicit_weights(points) if by_chapter else {}
    total = sum(int(v["score"]) for v in groups.values()) or 1
    rows: list[dict[str, Any]] = []
    used = 0
    items = sorted(groups.items(), key=lambda pair: -int(pair[1]["score"]))
    for idx, (label, data) in enumerate(items):
        if explicit and label in explicit:
            weight = explicit[label]
        elif idx == len(items) - 1:
            weight = 100 - used
        else:
            weight = round(int(data["score"]) * 100 / total)
            used += weight
        count = int(data["count"])
        if by_chapter:
            density = "极高" if count >= 5 else "高" if count >= 3 else "中" if count >= 2 else "低"
        else:
            # 按知识点：密度即重要程度
            density = "极高" if data["score"] >= 4 else "高" if data["score"] >= 2 else "低"
        rows.append(
            {
                "label": label,
                "weight": weight,
                "density": density,
                "basis": "；".join(data["basis"][:2])[:15] or "老师提及",
            }
        )
    return {"mode": "chapter" if by_chapter else "point", "rows": rows}


def _explicit_weights(points: list[dict[str, Any]]) -> dict[str, int]:
    """从老师原话/依据中读取明确分值比例；只在可识别时使用。"""
    weights: dict[str, int] = {}
    for point in points:
        chapter = _chapter_of(point)
        blob = " ".join(
            _clean(point.get(k))
            for k in ("quote", "note", "priority_reason")
        )
        m = re.search(r"([一二三四五六七八九十两\d]+)\s*成", blob)
        if m:
            raw = m.group(1)
            cn = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
            value = int(raw) if raw.isdigit() else cn.get(raw, 0)
            if value:
                weights[chapter] = max(weights.get(chapter, 0), value * 10)
        m2 = re.search(r"(\d+)\s*%", blob)
        if m2:
            weights[chapter] = max(weights.get(chapter, 0), int(m2.group(1)))
    if not weights:
        return {}
    known = sum(weights.values())
    if known >= 100:
        return weights
    missing = [c for c in {_chapter_of(p) for p in points} if c not in weights]
    if missing:
        share = max(1, (100 - known) // len(missing))
        for chapter in missing:
            weights[chapter] = share
        drift = 100 - sum(weights.values())
        weights[missing[-1]] += drift
    return weights


def _prerequisites(points: list[dict[str, Any]]) -> list[tuple[str, list[int]]]:
    candidates: dict[str, list[int]] = {}
    for idx, point in enumerate(points, start=1):
        for item in point.get("prerequisites") or []:
            item = _clean(item)
            if item:
                candidates.setdefault(item, []).append(idx)
        for key in point.get("keywords") or []:
            key = _clean(key)
            if not key or len(key) < 2:
                continue
            if any(token in key for token in ("定义", "公式", "性质", "定理", "基础", "概念")):
                candidates.setdefault(key, []).append(idx)
    if not candidates:
        for idx, point in enumerate(points[:4], start=1):
            name = _clean(point.get("name"))
            if name:
                candidates.setdefault(f"{name}的基本定义", []).append(idx)
    return [(k, v[:4]) for k, v in list(candidates.items())[:6]]


_EXAM_MARKS = (
    "开卷", "闭卷", "计算器", "平时分", "考试形式", "占到", "三成",
    "选择填空", "计算题一般", "五到六道", "全是极限",
)
_PRACTICE_MARKS = ("做十道", "做五道", "默写一遍", "默写九个", "每块做", "错题本过")
_CLASS_MARKS = ("还有两天", "对照自己的笔记", "PPT上没有", "课件没有", "口头补充")
_OTHER_MARKS = ("错题一定", "考前把错题", "比盲目", "过一遍错题")
_SKIP_SUPP = ("同学们", "下课", "好，就这些", "先说说整体结构")


def _split_sentences(text: str) -> list[str]:
    blob = re.sub(r"[\n\r]+", "。", text or "")
    parts = re.split(r"(?<=[。！？；;])", blob)
    out: list[str] = []
    for part in parts:
        item = _clean(part).strip("；;、，,")
        if len(item) < 8 or any(tag in item for tag in _SKIP_SUPP):
            continue
        if item.endswith(("。", "！", "？")):
            out.append(item)
        else:
            out.append(item + "。")
    return out


def _exam_supplements(original: str) -> dict[str, list[str]]:
    buckets = {
        "课堂补充说明": [],
        "考试形式说明": [],
        "优先练习题": [],
        "其他提示": [],
    }
    for sent in _split_sentences(original or ""):
        if any(t in sent for t in _EXAM_MARKS):
            buckets["考试形式说明"].append(sent)
        elif any(t in sent for t in _PRACTICE_MARKS):
            buckets["优先练习题"].append(sent)
        elif any(t in sent for t in _CLASS_MARKS):
            buckets["课堂补充说明"].append(sent)
        elif any(t in sent for t in _OTHER_MARKS):
            buckets["其他提示"].append(sent)
    return buckets


def _fallback_supplements(
    original: str,
    draft: dict[str, Any],
    points: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """四个栏目都要有话：先用 LLM 字段，再用原文挖掘，最后按考点归纳。"""
    mined = _exam_supplements(original)
    buckets = {
        "课堂补充说明": _as_list(draft.get("classroom_notes")),
        "考试形式说明": _as_list(draft.get("exam_hints")),
        "优先练习题": _as_list(draft.get("practice_pool")),
        "其他提示": _as_list(draft.get("other_tips")),
    }
    for key, extras in mined.items():
        buckets[key] = list(dict.fromkeys(buckets[key] + extras))
    practice = _practice_items(points)
    if practice:
        buckets["优先练习题"] = list(dict.fromkeys(buckets["优先练习题"] + practice))

    must = [p for p in points if _clean(p.get("degree")) == "必考"]
    mid = [p for p in points if _clean(p.get("degree")) == "重点"]
    low = [p for p in points if _clean(p.get("degree")) == "了解"]
    strategy = _clean(draft.get("strategy"))

    if len(buckets["课堂补充说明"]) < 2:
        extra = []
        if any(t in (original or "") for t in ("还有两天", "两天", "最后这节课")):
            extra.append("课堂把复习窗口压得很紧，先按老师点名的必考块过完，再补重点。")
        extra.append("划重点是口头交代，复习时把原话和自己的笔记/课件对上，缺的定义回笔记里补。")
        if must:
            extra.append("老师反复点名的主攻块：" + "、".join(_clean(p.get("name")) for p in must[:4]) + "。")
        buckets["课堂补充说明"] = list(dict.fromkeys(buckets["课堂补充说明"] + extra))

    if len(buckets["考试形式说明"]) < 2:
        qset: list[str] = []
        for point in points:
            qset.extend(_point_qtypes(point))
        uniq = list(dict.fromkeys(qset))
        extra = []
        if uniq:
            extra.append(f"卷面可能覆盖：{'、'.join(uniq)}。")
        if must:
            extra.append("必考块按大题准备，概念辨析多半落在选择/填空。")
        if any(
            "证明" in " ".join(_as_list(p.get("question_types")))
            or "零点" in _clean(p.get("name"))
            for p in points
        ):
            extra.append("证明题按老师点过的模板写全步骤，不要只写结论。")
        buckets["考试形式说明"] = list(dict.fromkeys(buckets["考试形式说明"] + extra)) or [
            "按老师点名的题型准备，先保证必考块会算、会写。"
        ]

    if len(buckets["优先练习题"]) < 3:
        extra = []
        for point in must[:4]:
            extra.append(f"{_clean(point.get('name'))}：默写结论后做 8-10 道（基础+变形）。")
        for point in mid[:3]:
            extra.append(f"{_clean(point.get('name'))}：做 4-6 道，专盯老师点过的易错点。")
        if low:
            extra.append(
                "了解类（"
                + "、".join(_clean(p.get("name")) for p in low[:3])
                + "）各复述一遍定义即可。"
            )
        buckets["优先练习题"] = list(dict.fromkeys(buckets["优先练习题"] + extra))

    if len(buckets["其他提示"]) < 2:
        extra = []
        if strategy:
            extra.append(strategy)
        extra.append("错题当天记「错因」，考前只过错题本，比继续盲目刷新题有效。")
        if must:
            extra.append(
                "考前默写一遍必考结论："
                + "、".join(_clean(p.get("name")) for p in must[:4])
                + "。"
            )
        buckets["其他提示"] = list(dict.fromkeys(buckets["其他提示"] + extra))

    for key, items in buckets.items():
        cleaned = [_clean(x) for x in items if _clean(x)]
        compact: list[str] = []
        seen: set[str] = set()
        for item in cleaned:
            text = item if len(item) <= 120 else _compact_sentence(item, 120)
            token = re.sub(r"[。！？；;、，,\s]", "", text)[:22]
            if not token or token in seen:
                continue
            if any(token.startswith(prev) or prev.startswith(token) for prev in seen):
                continue
            seen.add(token)
            compact.append(text)
        buckets[key] = compact[:6]
    return buckets


def _practice_items(points: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for point in points:
        for item in point.get("practice") or []:
            item = _clean(item)
            if item and item not in out:
                out.append(item)
    return out


def build_last_class_markdown(
    original: str,
    draft: dict[str, Any],
    collection: str = "default",
) -> str:
    """复习清单 Markdown：按 purpose 要求输出导航、考点、行动、备忘。"""
    points = _focus_points(draft)
    strategy = _clean(draft.get("strategy"))
    subject = ""
    m = re.search(r"【学科/课程】\s*([^【】\n]+)", original or "")
    if m:
        subject = m.group(1).strip()
    elif "【" not in (original or ""):
        # 兼容旧格式：学科/课程：xxx
        m2 = re.search(r"学科/课程：\s*([^\n【】]+)", original or "")
        if m2:
            subject = m2.group(1).strip()
    lines: list[str] = []
    lines.append(f"# 期末复习清单{f' · {subject}' if subject else ''}")
    if not points:
        lines.append("\n> 未从老师划重点文本中提取到明确的知识点。")
        return "\n".join(lines)

    ordered = sorted(
        points,
        key=lambda p: {"必考": 0, "重点": 1, "了解": 2}.get(str(p.get("degree")), 1),
    )[:20]
    source_cache = {i: _retrieve_point(collection, p) for i, p in enumerate(ordered)}
    heat_data = _heatmap(ordered)
    heat = heat_data["rows"]
    heat_mode = heat_data["mode"]

    lines.extend(["", "## 一、全局导航", "", f"### 1. 考点分布（{'按章节' if heat_mode == 'chapter' else '按知识点'}）"])
    if heat:
        for i, item in enumerate(heat, start=1):
            lines.append(
                f"- 第{i}项 {item['label']}：{item['weight']}% | "
                f"密度：{item['density']} | 依据：{item['basis']}"
            )
        chart = [{"label": h["label"], "value": h["weight"]} for h in heat]
        lines.append("")
        lines.append(f"<!-- chart:last_class_heatmap {json.dumps(chart, ensure_ascii=False)} -->")
    else:
        lines.append("未能从划重点文本中识别出考点分布。")

    lines.extend(["", "### 2. 前置知识自检清单"])
    prereqs = _prerequisites(ordered)
    if prereqs:
        for name, refs in prereqs:
            lines.append(
                f"- {name}：若不熟悉，建议优先补课；与考点 "
                f"{'、'.join(str(x) for x in refs)} 直接相关"
            )
    else:
        lines.append("本课程核心内容不依赖特定的前置知识，可直接进入复习")

    # 复习策略三档：按重要程度分组（必考/重点/了解，永不空）
    high = [p["name"] for p in ordered if _point_priority(p) == "高"]
    mid = [p["name"] for p in ordered if _point_priority(p) == "中"]
    low = [p["name"] for p in ordered if _point_priority(p) == "低"]
    lines.extend(["", "### 3. 复习策略建议"])
    if strategy:
        lines.append(f"> {strategy}")
    lines.append(
        f"**主攻模块（建议投入 65% 时间）：** {('、'.join(high[:6])) if high else '（无必考考点）'}"
        f"（理由：老师明确必考/高优先级）"
    )
    lines.append(
        f"**次重点模块（建议投入 25% 时间）：** {('、'.join(mid[:6])) if mid else '（无重点考点）'}"
        f"（理由：重点掌握，通常有小题或中档题）"
    )
    lines.append(
        f"**可快速过模块（建议投入 10% 时间）：** {('、'.join(low[:6])) if low else '（无了解类考点）'}"
        f"（理由：了解即可，概念有印象）"
    )

    # 考点关系图（前置依赖 + 对比关联，风格与知识图谱一致）
    prereq_edges, relate_edges = _build_relations(ordered)
    lines.extend(["", "### 4. 考点关系图"])
    rel_lines = _relations_markdown(prereq_edges, relate_edges)
    if rel_lines:
        lines.extend(rel_lines)
        lines.append("")
        rel_chart = {
            "points": [
                {"name": _clean(p.get("name")), "degree": str(p.get("degree") or "重点")}
                for p in ordered
            ],
            "prereq": prereq_edges,
            "relate": relate_edges,
        }
        lines.append(
            f"<!-- chart:last_class_relations {json.dumps(rel_chart, ensure_ascii=False)} -->"
        )
    else:
        lines.append("考点间未识别出明显关系。")

    lines.extend(["", "## 二、核心考点清单"])
    if len(ordered) < 8:
        lines.append(f"> 仅识别到{len(ordered)}个考点，生成结果可能不够全面，建议补充更多画重点文本内容。")
    if len(points) > 20:
        lines.append("> 因篇幅限制，仅展示前20个考点。")

    for idx, p in enumerate(ordered, start=1):
        priority = _point_priority(p)
        sources = source_cache[idx - 1]
        blurb = _knowledge_blurb(p, sources)
        qtypes = "、".join(_point_qtypes(p))
        difficulty = _difficulty(priority, p)
        lines.extend(["", f"#### {idx}. {_clean(p.get('name'))} | 优先级：{priority}", "", "**考法预判**"])
        lines.append(f"- 预测题型：{qtypes}")
        lines.append(f"- 难度等级：{difficulty}")
        # 每个考点的题型分布饼图（对应知识点，非全局）
        qdist = _qtype_distribution(p)
        if len(qdist) >= 2:
            lines.append("")
            lines.append(
                f"<!-- chart:last_class_qtype {json.dumps(qdist, ensure_ascii=False)} -->"
            )
        lines.extend(["", "**核心精讲**"])
        what, why, trap, how = _core_explain(p, blurb)
        core_text = "".join(seg for seg in (what, why, trap, how) if seg)
        lines.append(core_text)

    lines.extend(["", "## 三、行动清单", "", "### 1. 分阶段复习路径"])
    high_ids = [str(i) for i, p in enumerate(ordered, start=1) if _point_priority(p) == "高"]
    mid_ids = [str(i) for i, p in enumerate(ordered, start=1) if _point_priority(p) == "中"]
    low_ids = [str(i) for i, p in enumerate(ordered, start=1) if _point_priority(p) == "低"]
    phases = [
        ("第一阶段", "2小时", low_ids[:4] or mid_ids[:2] or high_ids[:1]),
        ("第二阶段", "4小时", high_ids[:6] or mid_ids[:4]),
        ("第三阶段", "2小时", mid_ids[:6] or low_ids[4:] or high_ids[6:]),
        ("第四阶段", "1小时", [x for x in (low_ids[4:] + mid_ids[6:] + high_ids[6:]) if x]),
    ]
    usable_phases = [p for p in phases if p[2]]
    if len(ordered) < 3:
        lines.append("考点数量较少，建议合并复习。")

    def _phase_target(point_ids: list[str]) -> str:
        """聚合阶段内考点的具体复习目标（自测点/掌握要求/练习），避免空话。"""
        parts: list[str] = []
        for pid in point_ids:
            if not pid.isdigit():
                continue
            p = ordered[int(pid) - 1]
            cps = p.get("check_points") or []
            if cps:
                parts.append(f"{p['name']}：{cps[0]}")
                continue
            m = _clean(p.get("mastery")) or _clean(p.get("note"))
            if m:
                parts.append(f"{p['name']}：{m[:30]}")
        return "；".join(parts[:4]) or "完成本阶段考点复习"

    for name, hours, ids in usable_phases:
        names = "、".join(ids)
        target = _phase_target(ids)
        lines.append(f"- {name}（建议用时：{hours}）：覆盖考点 {names}；目标：{target}。")

    lines.extend(["", "### 2. 自测检验点"])
    selfcheck_phases: list[dict[str, Any]] = []
    for idx, (_name, _hours, ids) in enumerate(usable_phases, start=1):
        checks: list[str] = []
        names: list[str] = []
        for pid in ids:
            if not pid.isdigit():
                continue
            p = ordered[int(pid) - 1]
            names.append(p["name"])
            raw_checks = p.get("check_points") or []
            if raw_checks:
                checks.extend(_clean(x) for x in raw_checks if _clean(x))
            else:
                m = _clean(p.get("mastery")) or _clean(p.get("note"))
                if m:
                    checks.append(f"{p['name']}：{m}")
                else:
                    checks.append(f"复述 {p['name']} 的结论和限制条件")
        selfcheck_phases.append(
            {
                "label": f"阶段{idx}",
                "points": "、".join(names[:4]),
                "checks": checks[:5],
            }
        )
    lines.append("")
    lines.append(
        f"<!-- chart:last_class_selfcheck {json.dumps({'phases': selfcheck_phases}, ensure_ascii=False)} -->"
    )

    supplements = _fallback_supplements(original, draft, ordered)
    lines.extend(["", "## 四、补充与备忘"])
    for title, items in supplements.items():
        lines.extend(["", f"### {title}"])
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


# ── HTML 复习清单（与 Markdown 同源渲染）──────────────────────

_DEGREE_CLS = {"必考": "degree-must", "重点": "degree-key", "了解": "degree-know"}


def _inline_markdown(text: str) -> str:
    """渲染本任务会产生的少量行内 Markdown，并做轻量公式美化。

    公式：``x_{n+1}`` → ``x<sub>n+1</sub>``、``^{3x}`` → ``<sup>3x</sup>``、
    ``√(2+x)`` 保留、``→`` 保留；先 escape 再转换，避免注入。
    """
    html = escape(text, quote=False)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # 下标：只处理显式花括号，避免把文件名下划线误渲染成公式。
    html = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", html)
    # 上标：^{3x} / ^2
    html = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", html)
    html = re.sub(r"\^([0-9]+)", r"<sup>\1</sup>", html)
    return html


_KB_LABEL_CLASS = {"笔记": "lc-cite-notes", "课件": "lc-cite-slides", "文档": "lc-cite-docs"}
def _is_sep_cell(cell: str) -> bool:
    return bool(re.fullmatch(r":?-{2,}:?", (cell or "").replace(" ", "")))


def _split_pipe_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_pipe_table(text: str) -> tuple[str, list[list[str]], str] | None:
    """把 markdown / 被压成一行的对照表拆成行；解析失败返回 None。"""
    raw = _soft_clean(text)
    if raw.count("|") < 4:
        return None
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) == 1:
        line = lines[0]
        start = line.find("|")
        if start < 0:
            return None
        before = line[:start].strip()
        tail = line[start:]
        cells = [cell.strip() for cell in tail.split("|")]
        after = ""
        while cells and not cells[-1]:
            cells.pop()
        if cells and cells[-1] and "|" not in cells[-1] and len(cells[-1]) > 18:
            # 表后还粘着说明/清单
            if not _is_sep_cell(cells[-1]) and cells[-1].count("：") + cells[-1].count("(") >= 0:
                if any(mark in cells[-1] for mark in ("清单", "能否", "注意", "10.", "复习")):
                    after = cells.pop()
        cells = [cell for cell in cells if cell and not _is_sep_cell(cell)]
        if len(cells) < 4:
            return None
        ncols = 2 if len(cells) % 2 == 0 else (3 if len(cells) % 3 == 0 else 2)
        leftover = len(cells) % ncols
        if leftover:
            extra = " ".join(cells[-leftover:])
            cells = cells[:-leftover]
            after = (extra + " " + after).strip()
        rows = [cells[i : i + ncols] for i in range(0, len(cells), ncols)]
        if len(rows) < 2:
            return None
        return before, rows, after
    start = next((i for i, ln in enumerate(lines) if ln.count("|") >= 2), None)
    if start is None:
        return None
    end = start
    while end < len(lines) and lines[end].count("|") >= 2:
        end += 1
    rows: list[list[str]] = []
    for ln in lines[start:end]:
        cells = _split_pipe_cells(ln)
        if cells and all(_is_sep_cell(cell) for cell in cells):
            continue
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return None
    return "\n".join(lines[:start]), rows, "\n".join(lines[end:])


def _table_html(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    th = "".join(f"<th>{escape(cell, quote=False)}</th>" for cell in head)
    trs = []
    for row in body:
        padded = row + [""] * max(0, len(head) - len(row))
        tds = "".join(f"<td>{escape(cell, quote=False)}</td>" for cell in padded[: len(head)])
        trs.append(f"<tr>{tds}</tr>")
    return (
        '<table class="lc-md-table"><thead><tr>'
        + th
        + "</tr></thead><tbody>"
        + "".join(trs)
        + "</tbody></table>"
    )


def _prose_html(text: str) -> str:
    body = escape(_soft_clean(text), quote=False).replace("\n", "<br>")
    if not body:
        return ""
    return f'<div class="lc-prose">{body}</div>'


def _excerpt_html(text: str, source_file: str = "") -> str:
    raw = _strip_file_prefix(_soft_clean(text), source_file)
    parsed = _parse_pipe_table(raw)
    if not parsed:
        return f'<div class="lc-cite-excerpt">{_prose_html(raw)}</div>'
    before, rows, after = parsed
    return (
        '<div class="lc-cite-excerpt">'
        + _prose_html(before)
        + _table_html(rows)
        + _prose_html(after)
        + "</div>"
    )


def _kb_cite_card(rank: int, label: str, item: dict[str, Any], *, opened: bool) -> str:
    file = escape(str(item.get("file") or "知识库"), quote=False)
    page = escape(str(item.get("page") or ""), quote=False)
    loc = f" · 第{page}页" if page else ""
    kind = _KB_LABEL_CLASS.get(label, "")
    open_attr = " open" if opened else ""
    return (
        f'<details class="lc-cite-card lc-cite-kb {kind}"{open_attr}>'
        f'<summary><span><span class="lc-cite-rank">{rank}</span>知识库 · {label}{loc}</span>'
        f'<strong>{file}</strong></summary>'
        + _excerpt_html(str(item.get("excerpt") or ""), str(item.get("file") or ""))
        + "</details>"
    )


def _review_source_cards(point: dict[str, Any] | None, sources: dict[str, list[dict]] | None) -> str:
    """精讲右侧：老师原话 + 按重要程度排列的知识库出处，多的折叠。"""
    if not point:
        return '<div class="mem-empty"></div>'
    cards: list[str] = []
    quote = _clean(point.get("quote"))
    if quote:
        cards.append(
            '<details class="lc-cite-card lc-cite-teacher" open>'
            '<summary><span>老师原话</span></summary>'
            f'<div class="lc-cite-title">「{escape(quote, quote=False)}」</div>'
            "</details>"
        )
    ranked = _rank_kb_sources(point, sources)
    visible, extra = _pick_visible_kb(point, ranked)
    if visible:
        cards.append('<div class="lc-cite-head">知识库出处（按相关程度）</div>')
        for idx, (_score, label, item) in enumerate(visible, start=1):
            cards.append(_kb_cite_card(idx, label, item, opened=False))
        extra_cards = [
            _kb_cite_card(idx, label, item, opened=False)
            for idx, (_score, label, item) in enumerate(extra, start=len(visible) + 1)
        ]
        if extra_cards:
            cards.append(
                f'<details class="lc-cite-more"><summary>更多知识库出处（{len(extra_cards)}）</summary>'
                + "".join(extra_cards)
                + "</details>"
            )
    elif quote:
        cards.append('<div class="lc-cite-miss">知识库未命中对应段落</div>')
    if not cards:
        return '<div class="mem-empty">未命中老师原话或知识库来源</div>'
    return "".join(cards)


def _line_to_html(line: str) -> tuple[str, str]:
    """返回 (kind, html)。kind 用于审阅布局决定是否全宽。"""
    if line.startswith("#### "):
        return "h4", f"<h4>{_inline_markdown(line[5:].strip())}</h4>"
    if line.startswith("### "):
        return "h3", f"<h3>{_inline_markdown(line[4:].strip())}</h3>"
    if line.startswith("## "):
        return "h2", f"<h2>{_inline_markdown(line[3:].strip())}</h2>"
    if line.startswith("# "):
        return "h1", f"<h1>{_inline_markdown(line[2:].strip())}</h1>"
    if line.startswith("> "):
        return "quote", f"<blockquote>{_inline_markdown(line[2:].strip())}</blockquote>"
    if line.startswith("- "):
        return "li", f"<ul><li>{_inline_markdown(line[2:].strip())}</li></ul>"
    return "p", f"<p>{_inline_markdown(line)}</p>"


def _last_class_review_html(
    markdown: str,
    ordered: list[dict[str, Any]],
    source_cache: dict[int, dict[str, list[dict]]],
) -> str:
    """Word 审阅式 HTML：左正文（核心精讲融合为一段、直接完整展示），右出处。

    核心精讲不再分块也不折叠：md 中「**核心精讲**」标题后紧跟一段连续文本，
    这里直接完整展示在左栏；右侧统一挂老师原话（默认展开）+ 知识库出处
    （默认只显示一行，点击展开，多的折叠）。
    """
    by_name = {_clean(point.get("name")): i for i, point in enumerate(ordered)}
    current_index: int | None = None
    in_core = False
    rows: list[str] = ['<div class="memory-review last-class-doc lc-review-doc">']

    def core_row(core_text: str) -> None:
        point = ordered[current_index] if current_index is not None else None
        sources = source_cache.get(current_index) if current_index is not None else None
        body = f'<div class="lc-core-body"><p>{_inline_markdown(core_text)}</p></div>'
        rows.append(
            '<div class="review-row lc-review-row">'
            f'<div class="review-left lc-review-left">{body}</div>'
            '<div class="review-rule"></div>'
            f'<div class="review-right lc-review-right">{_review_source_cards(point, sources)}</div>'
            "</div>"
        )

    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "**核心精讲**":
            in_core = True
            continue
        rendered = ""
        full = False
        for marker, renderer in (
            ("last_class_selfcheck", _render_selfcheck_svg),
            ("last_class_relations", _render_relations_svg),
            ("last_class_qtype", _render_qtype_chart),
            ("last_class_heatmap", _render_heatmap_chart),
        ):
            chart = re.match(rf"<!--\s*chart:{marker}\s+(.+?)\s*-->", line)
            if chart:
                rendered = renderer(chart.group(1))
                full = True
                break
        if not rendered:
            kind, rendered = _line_to_html(line)
            full = kind in {"h1", "h2", "h3"}
            if kind == "h2":
                current_index = None
            if kind == "h4":
                title = re.sub(r"^\d+\.\s*", "", line[5:].strip()).split("|", 1)[0].strip()
                if title in by_name:
                    current_index = by_name[title]
        if not rendered:
            continue
        if in_core:
            # 「核心精讲」标题后的第一段 = 融合后的精讲正文
            in_core = False
            core_row(line)
            continue
        if full:
            rows.append(f'<div class="lc-review-full">{rendered}</div>')
            continue
        rows.append(
            '<div class="review-row lc-review-row">'
            f'<div class="review-left lc-review-left">{rendered}</div>'
            '<div class="review-rule"></div>'
            '<div class="review-right lc-review-right"></div>'
            "</div>"
        )
    rows.append("</div>")
    return "\n".join(rows)


def build_last_class_html(
    original: str,
    draft: dict[str, Any],
    collection: str = "default",
) -> str:
    """复习清单 HTML：正文 + 右侧出处审阅模式。"""
    points = _focus_points(draft)
    ordered = sorted(
        points,
        key=lambda p: {"必考": 0, "重点": 1, "了解": 2}.get(str(p.get("degree")), 1),
    )[:20]
    source_cache = {i: _retrieve_point(collection, p) for i, p in enumerate(ordered)}
    markdown = build_last_class_markdown(original, draft, collection)
    body = _last_class_review_html(markdown, ordered, source_cache)
    return "\n".join(
        [
            "<style>",
            ".last-class-doc{display:block;border:1px solid #d4d0c6;background:#fff;border-radius:8px;overflow:hidden;line-height:1.72;}",
            ".lc-review-doc{display:block;}",
            ".lc-review-full{padding:18px 28px;border-bottom:1px solid #ebe8e1;background:#fff;}",
            ".lc-review-row{display:grid;grid-template-columns:minmax(0,1fr) 1px minmax(260px,34%);border-bottom:1px solid #ebe8e1;}",
            ".lc-review-left{padding:8px 24px;min-width:0;}",
            ".lc-review-right{padding:8px 10px;background:#faf9f6;}",
            ".last-class-doc h1{margin:0 0 18px;font-size:1.9rem;line-height:1.25;}",
            ".last-class-doc h2{margin:0;font-size:1.22rem;}",
            ".last-class-doc h2:first-of-type{border-top:none;}",
            ".last-class-doc h3{margin:0;font-size:1.04rem;}",
            ".last-class-doc h4{margin:0;font-size:1rem;}",
            ".last-class-doc ul{margin:0;padding-left:1.25em;}",
            ".last-class-doc li{margin:8px 0;line-height:1.78;}",
            ".last-class-doc blockquote{margin:8px 0 14px;padding:9px 12px;background:#f7f5f0;border-left:4px solid #c8c4b8;border-radius:4px;color:#4a4842;}",
            ".last-class-doc p{margin:8px 0;}",
            ".lc-heatmap-card{display:grid;grid-template-columns:150px minmax(0,1fr);gap:22px;align-items:center;margin:0;padding:16px;border:1px solid #ebe8e1;background:#fbfaf7;border-radius:8px;}",
            ".lc-pie{width:136px;aspect-ratio:1;border-radius:50%;box-shadow:inset 0 0 0 18px rgba(255,255,255,.62);}",
            ".lc-qtype-card{display:grid;grid-template-columns:96px minmax(0,1fr);gap:14px;align-items:center;margin:8px 0 12px;padding:10px 14px;border:1px dashed #d4d0c6;background:#fff;border-radius:8px;}",
            ".lc-pie-sm{width:88px;aspect-ratio:1;border-radius:50%;box-shadow:inset 0 0 0 12px rgba(255,255,255,.62);}",
            ".lc-legend{display:grid;gap:8px;}",
            ".lc-legend-item{display:grid;grid-template-columns:14px minmax(0,1fr) auto;gap:8px;align-items:center;font-size:.9rem;}",
            ".lc-dot{width:10px;height:10px;border-radius:50%;}",
            ".lc-cite-card{display:block;padding:8px 10px;border-left:3px solid #64748b;background:#fff;color:#1c1b19;text-decoration:none;border-radius:6px;margin-bottom:7px;box-shadow:0 1px 0 rgba(28,27,25,.04);}",
            ".lc-cite-teacher{border-left-color:#b3402e;background:#fff8f6;}",
            ".lc-cite-notes{border-left-color:#395f8a;}",
            ".lc-cite-slides{border-left-color:#c98a2d;}",
            ".lc-cite-docs{border-left-color:#497a78;}",
            ".lc-cite-head{font-size:.72rem;font-weight:700;letter-spacing:.04em;color:#6b6860;margin:8px 0 6px;}",
            ".lc-cite-rank{display:inline-block;min-width:1.15em;padding:0 5px;margin-right:4px;border-radius:8px;background:#64748b;color:#fff;font-size:.68rem;font-weight:700;text-align:center;line-height:1.4;}",
            ".lc-cite-card summary{cursor:pointer;display:flex;gap:6px;align-items:center;justify-content:space-between;font-size:.78rem;color:#6b6860;}",
            ".lc-cite-card summary span{display:flex;align-items:center;min-width:0;}",
            ".lc-cite-card summary strong{font-size:.78rem;color:#3a3832;font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:58%;}",
            ".lc-cite-kicker{font-size:.74rem;color:#6b6860;margin-bottom:4px;}",
            ".lc-cite-title{font-size:.86rem;font-weight:650;line-height:1.45;}",
            ".lc-cite-excerpt{font-size:.76rem;color:#6b6860;line-height:1.5;margin-top:5px;white-space:normal;}",
            ".lc-prose{white-space:pre-wrap;word-break:break-word;}",
            ".lc-md-table{width:100%;border-collapse:collapse;margin:6px 0;font-size:.76rem;}",
            ".lc-md-table th,.lc-md-table td{border:1px solid #d4d0c6;padding:4px 6px;text-align:left;vertical-align:top;}",
            ".lc-md-table th{background:#f7f5f0;color:#3a3832;}",
            ".lc-core-body{padding:6px 2px 6px 0;font-size:14px;line-height:1.95;color:#2c2a26;text-align:justify;}",
            ".lc-core-body p{margin:0;}",
            ".lc-cite-more{margin-top:6px;border:1px dashed #d4d0c6;border-radius:6px;padding:4px 8px;background:#fff;}",
            ".lc-cite-more>summary{cursor:pointer;font-size:.76rem;color:#6b6860;}",
            ".lc-cite-miss{font-size:.74rem;color:#9a968c;margin-top:6px;}",
            ".lc-graph-svg,.lc-selfcheck-svg{background:#fbfaf7;border-radius:12px;}",
            ".lc-relations-gv{margin:8px 0;background:#fff;border:1px solid #ebe8e1;border-radius:12px;padding:10px;overflow-x:auto;}",
            "@media(max-width:860px){.lc-review-row{grid-template-columns:1fr}.review-rule{height:1px}.lc-review-right{padding:10px 18px}.lc-heatmap-card{grid-template-columns:1fr}.lc-pie{width:120px}.lc-qtype-card{grid-template-columns:1fr}.lc-pie-sm{width:120px}}",
            "</style>",
            body,
        ]
    )


# ── 挂载到 state ──────────────────────────────────────────────

def attach_last_class_artifacts(state: dict[str, Any]) -> None:
    """把复习清单挂到 state 的 lines.last_class（供 Report 组装）。

    用户与学科从 line_extra 标记提取（runner 拼入），决定检索哪个集合。
    """
    from tools.domain_engine_text import line

    sub = line(state, "last_class")
    draft = dict(sub.get("draft") or {})
    original = str(state.get("transcript") or "")
    extra = (state.get("line_extra") or {}).get("last_class") or ""
    subject = subject_from_context(extra) or subject_from_context(original)
    user_id = user_id_from_context(extra)
    collection = resolve_collection(user_id=user_id, subject=subject)
    render_source = f"{original}\n\n{extra}".strip()
    draft["review_html"] = build_last_class_html(render_source, draft, collection)
    sub["rendered"] = build_last_class_markdown(render_source, draft, collection)
    sub["draft"] = draft
    sub["structure"] = draft.get("focus_points") or []
    sub["collection"] = collection


__all__ = [
    "attach_last_class_artifacts",
    "build_last_class_html",
    "build_last_class_markdown",
    "draft_from_context",
    "original_from_context",
    "subject_from_context",
    "user_id_from_context",
    "resolve_collection",
]
