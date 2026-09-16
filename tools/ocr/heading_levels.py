"""跨页标题层级归一（确定性，零 LLM）。

问题：OCR 逐页整理时，每页的级号由**该页版面**决定（页顶/居中/字高 → `#` 数量），
天然是"页内相对"的；合并成一份稿子后，同一逻辑层在不同页会落在不同级号上
（同一个二级标题在 A 页是 `##`、在 B 页是 `###`）。骨架按"树深度 → 章/主题/
知识点"解析时，这种漂移会把**主题当成章**（假章），下游再给空章补同名主题、
改名成占位名。数字编号标题有 ``normalize_heading_numbering`` 兜底，
**无编号标题此前完全没有保护**。

本模块只做"结构性自洽"的归一，不做任何语义猜测，只重写标题行的 `#` 数量，
正文一字不动，幂等：

- R1 同名同级别：同一标题名（含「X（续）」按基名归一）在全篇必须是同一级号；
- R2 续写容器：「X」与「X（续）」之间的标题整体下移，使其最浅层 = X 的级别 + 1
  （「（续）」证明 X 是一个跨页容器，夹在中间的标题属于它，而不是与它同级）。

语义层的判断（"这个标题是独立知识范围，还是某一范围的侧面"）交给 LLM 侧：
见 ``RECONSTRUCT_SYSTEM_PROMPT`` 的层级铁律与跨页层级锚点。
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

MAX_LEVEL = 6
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# 「X（续）」→ 基名 X（与 skeleton._cont_name 同款语义，此处本地实现以免跨层依赖）
_CONT_RE = re.compile(r"[（(]\s*续\s*[）)]|续\s*$")
_PUNCT_RE = re.compile(r"[\s:：,，。；;、（）()\[\]【】《》“”\"'·\-—_]+")


def split_heading(line: str) -> tuple[int, str] | None:
    """标题行 → (级号, 标题文本)；非标题返回 None。"""
    matched = _HEADING_RE.match((line or "").strip())
    if not matched:
        return None
    return len(matched.group(1)), matched.group(2).strip()


def base_name(text: str) -> str:
    """标题基名：「X（续）」→「X」（去掉续写标记）。"""
    return _CONT_RE.sub("", (text or "").strip()).strip()


def name_key(text: str) -> str:
    """名字归一化键（去空白/标点/大小写），用于"同名"判定。"""
    return _PUNCT_RE.sub("", base_name(text).lower())


def _collect(markdown: str) -> list[dict]:
    """收集标题（行号/级号/原名/基名键）。"""
    heads: list[dict] = []
    for idx, line in enumerate((markdown or "").splitlines()):
        hit = split_heading(line)
        if not hit:
            continue
        level, title = hit
        key = name_key(title)
        if not key:
            continue
        heads.append({"line": idx, "level": level, "title": title, "key": key})
    return heads


def _unify_same_name(heads: list[dict]) -> int:
    """R1：同名（基名）标题统一级号 —— 取**最浅**的那一级。

    取最浅而不是取多数：续页的（续）标题往往比开篇页多，取多数会把章级别拉深
    （极端情况整篇丢掉章层）；而"同一个名字在别处更浅"本身就是"它是容器"的证据。
    同名同级还会与骨架的「同名同级合并」修补配合，把重复容器并成一个。
    """
    levels: dict[str, list[int]] = defaultdict(list)
    for head in heads:
        levels[head["key"]].append(head["level"])
    chosen = {key: min(found) for key, found in levels.items()}
    fixed = 0
    for head in heads:
        want = chosen[head["key"]]
        if head["level"] != want:
            head["level"] = want
            fixed += 1
    return fixed


def _demote_continuation_spans(heads: list[dict]) -> int:
    """R2：「X」与「X（续）」之间的标题整体下移，使区间内最浅层 = X 级别 + 1。

    只在真的更浅/同级时才平移（delta > 0），并且只平移该区间内的标题，
    区间外一律不动 —— 影响面可控、可回归。
    """
    positions: dict[str, list[int]] = defaultdict(list)
    for idx, head in enumerate(heads):
        positions[head["key"]].append(idx)
    moved = 0
    for key, idxs in positions.items():
        if len(idxs) < 2:
            continue
        base_level = heads[idxs[0]]["level"]
        for start, end in zip(idxs, idxs[1:]):
            span = list(range(start + 1, end))
            if not span:
                continue
            shallowest = min(heads[i]["level"] for i in span)
            delta = (base_level + 1) - shallowest
            if delta <= 0:
                continue
            for i in span:
                heads[i]["level"] = min(MAX_LEVEL, heads[i]["level"] + delta)
            moved += 1
    return moved


def normalize_heading_levels(markdown: str) -> tuple[str, dict[str, int]]:
    """按 R1/R2 归一标题级号；返回 (新 Markdown, 统计)。幂等。"""
    text = markdown or ""
    heads = _collect(text)
    stats = {"heads": len(heads), "unified": 0, "spans": 0}
    if len(heads) < 2:
        return text, stats
    stats["unified"] = _unify_same_name(heads)
    stats["spans"] = _demote_continuation_spans(heads)
    if not stats["unified"] and not stats["spans"]:
        return text, stats
    rows = text.splitlines()
    for head in heads:
        level = max(1, min(MAX_LEVEL, head["level"]))
        rows[head["line"]] = f"{'#' * level} {head['title']}"
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("heading level normalize: %s", stats)
    return "\n".join(rows), stats


__all__ = [
    "base_name",
    "name_key",
    "normalize_heading_levels",
    "split_heading",
]
