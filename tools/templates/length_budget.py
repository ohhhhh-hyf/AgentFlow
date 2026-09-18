"""篇幅预算：按原文规模算出正文总量参考，供 prompt 引用（单点维护）。

为什么需要（2026-09 now.xlsx 实测 55 条）：输出/输入比在 4.3%–35% 之间游走（同批差 7 倍）——
既有 24562 字原文只出 1338 字（4.8%：条目 19–36 字、只剩结论），也有 13887 字原文出现 902 字单段。
问题不是"上限太紧"，而是**只有上限、没有下限**；旧口径"篇幅以原文为参照（同量级 90%–110%）"
对纪要既不成立（纪要必然短于原文）也无法自算。这里把"该写多长"变成**程序算好的具体数字**：
模型只负责分配（内容多靠多分条、多分段承载），不负责估量。

档位（2026-09 定稿）：下限按最初档位 +20%，上限取"事实密集的记录型"一档，两侧都留足空间——
下限治"薄"，上限治"爆炸段"；栏数与类型差异由 prompt 文字引导（不引模板 id）。

| 原文汉字 | 正文总量参考 |
|---|---|
| <3k    | 720–1800 |
| 3k–8k  | 1080–3200 |
| 8k–20k | 1680–5500 |
| ≥20k   | 2400–8000 |

总述栏（模板第 1 栏）另有下限（2026-09 now.xlsx 实测 56 条）：29 个模板里 22 个的首栏说明
只有一句"一段话概括…"，实测首栏汉字中位数约 150（最薄 88），而通用兜底只给了上限——**上限治不了薄**。
`first_column_min()` 把"总述栏该多厚"按原文规模算成具体数字，与整篇预算同源：

| 原文汉字 | tier 下限 | 首栏下限（22%，夹 180–480） |
|---|---|---|
| <3k    | 720  | 180 |
| 3k–8k  | 1080 | 238 |
| 8k–20k | 1680 | 370 |
| ≥20k   | 2400 | 480 |

480 仍能装进"1–2 段、每段 ≤400 字"，不与段落上限冲突。
"""
from __future__ import annotations

import re

_HAN_RE = re.compile(r"[\u4e00-\u9fff]")

# 档位：(原文汉字上限, 下限, 上限)
TIERS: tuple[tuple[int | None, int, int], ...] = (
    (3000, 720, 1800),
    (8000, 1080, 3200),
    (20000, 1680, 5500),
    (None, 2400, 8000),
)


# 总述栏（第 1 栏）下限：整篇下限的 22%，夹在 180–480 汉字（480 仍在"1–2 段、每段 ≤400"内）
FIRST_COL_SHARE = 0.22
FIRST_COL_MIN, FIRST_COL_MAX = 180, 480


def han_count(text: str) -> int:
    """汉字数（篇幅口径按汉字算，避免标点/拉丁字符干扰）。"""
    return len(_HAN_RE.findall(text or ""))


def length_budget(source_han: int, *, kind: str = "record") -> tuple[int, int] | None:
    """原文汉字数 → (下限, 上限)；原文过短（<300 汉字）时返回 None（不值得约束）。

    kind 仅用于微调：extractive（栏目少、装结论）取下限一侧更窄的区间。
    """
    if source_han < 300:
        return None
    for ceiling, lo, hi in TIERS:
        if ceiling is None or source_han < ceiling:
            if kind == "extractive":
                return lo, max(lo + 200, hi * 2 // 3)
            return lo, hi
    return None


def first_column_min(source_han: int) -> int | None:
    """总述栏（模板第 1 栏）的篇幅下限；原文过短（<300 汉字）时返回 None。

    只对第 1 栏要下限：明细栏写多长由原文事实量决定（逼下限会注水），
    总述栏是"只读一段"的入口，太薄＝没有交代清这场会是什么、围绕什么、结论与关键数字。
    """
    span = length_budget(source_han)
    if not span:
        return None
    return max(FIRST_COL_MIN, min(FIRST_COL_MAX, round(span[0] * FIRST_COL_SHARE)))


def budget_line(source_han: int, *, columns: int = 0) -> str:
    """生成注入 prompt 的【篇幅预算】块；原文过短时返回空串。"""
    span = length_budget(source_han)
    if not span:
        return ""
    lo, hi = span
    cols = f"，本模板 {columns} 栏" if columns else ""
    pct_lo = lo * 100 // max(source_han, 1)
    pct_hi = hi * 100 // max(source_han, 1)
    floor = first_column_min(source_han)
    first_col = (
        f"**第 1 栏（概况/总述）**写 1–2 段完整概括，不少于 {floor} 汉字（每段 ≤400）："
        "交代清谁/什么场合、围绕什么与覆盖哪几块、结论或基调，"
        "并带 1–3 个关键数字（原文没有的不编）。"
    ) if floor else ""
    return (
        f"【篇幅预算】原文约 {source_han} 汉字{cols} → 正文总量参考 {lo}–{hi} 汉字"
        f"（原文的 {pct_lo}%–{pct_hi}%）。"
        "**低于下限＝漏了原文事实**（回原文把细节写足，不是补套话）；高于上限＝有重复或注水。"
        "这是分布指引：内容多靠**多分条、多分段、多分栏**承载，不靠把一段写长；"
        "栏目少、以结论为主的模板（复盘/评审/面试/笔记/通用纪要）往下限一侧走，"
        "事实密集的记录型模板（课堂/庭审/讲座/发布）可往上限一侧走——以原文事实量为准，不硬凑也不硬压。"
        "单段 ≤400 字（概况/背景类 ≤3 段）、条目 30–120 字/条。"
        + first_col
    )


__all__ = [
    "FIRST_COL_MAX",
    "FIRST_COL_MIN",
    "FIRST_COL_SHARE",
    "TIERS",
    "budget_line",
    "first_column_min",
    "han_count",
    "length_budget",
]
