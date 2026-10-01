"""catalog 的"内容词表 + 形态规则"单一来源（可配置、跨学科泛化）。

分层原则（越往上越通用，越往下越依赖语言/学科）：

1. **形态规则**：与学科无关的字面形态——序号前缀（`一、`/`1.2`/`第3节`）、圈号（`①`）、
   `（续）`、编号标题、页框/联系信息、句末标点。见 `tools/knowledge/source_role.py`
   与 `skeleton.py` 的前缀正则。
2. **结构判定**：与语言无关的**形状**——父子同名、唯一子节点同名、同名同级重复、
   顺序单调、覆盖完整。判定写在各自的消费点（如 `skeleton.placeholder_shape`、
   `merge._retitle_duplicate_topic`），不依赖任何词表。
3. **内容词表**（本模块）："辅助性内容"与"占位名"这类**跨学科通用的学习材料类别**。
   它们不是数据样本，但确实与语言/习惯有关，所以集中在此、并允许按学科覆盖。

覆盖方式（`.env`，逗号分隔；给空值 = 关闭该类判定）::

    CATALOG_ITEM_MARKS=例题,易错,小结        # 追加到"辅助性内容"词表
    CATALOG_ITEM_MARKS=                     # 关闭该类
    CATALOG_TITLE_MARKS=定义,定理            # 覆盖"知识标题"词表
    CATALOG_PLACEHOLDER_RE=^(核心|其他)$     # 整体替换占位名形态正则

词表只用于**降级/计数**（把辅助内容收进 items、统计占位名），绝不用于决定结构：
结构与顺序永远来自原文骨架或候选池位置（见 `skeleton.py`）。
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

# ── 辅助性内容（例题/易错/小结…）：不建节点，收进父节点的 knowledge_items ──
_DEFAULT_ITEM_MARKS = (
    "例题", "易错", "注意", "总结", "步骤", "题型", "技巧", "提醒", "小结",
    "练习", "习题", "示例", "思考", "作业", "考点",
)
# ── 知识标题形态（定义/定理/…）：标题里出现即视为"知识点味"的标题 ──
_DEFAULT_TITLE_MARKS = (
    "定义", "性质", "定理", "规则", "方法", "公式",
    "例题", "易错", "注意", "总结", "步骤",
)
# ── 占位名形态：结构合法性不该靠无信息名字撑（不是枚举见过的名字，而是形态）──
_DEFAULT_PLACEHOLDER_RE = (
    r"^(?:核心|主要|基本|重点|关键|其他|其它|补充|全部|整体|相关|若干)*"
    r"(?:知识|知识点|知识内容|知识概要|内容|内容概要|概念|要点|重点|概要|概述|"
    r"简介|说明|小结|总结|其他|其它|导论|绪论)$"
)
# 页框/目录类短标题（跨语料的功能形态，无具体机构名/地名）
_DEFAULT_NOISE_TITLE_RE = (
    r"(tel[:：]|电话|印刷|https?://|www\.|\.com\b"
    r"|第\s*\d+\s*页|page\s*\d+|^\s*页\s*$"
    r"|.{0,10}(?:大学|学院|学校|研究院|研究所|公司|中心)\s*$"
    r"|(?:university|college|institute)\b)"
)
_DEFAULT_NOISE_SHORT_TITLES = ("页", "目录")
_DEFAULT_BODY_LIKE_ENDINGS = ("。", "；", ";", ".", "！", "？", "!", "?")


# ── 细粒度点（"XXX 的适用条件/常见变形/例题"这类）：降级进父 KP 的 items ──
_DEFAULT_FINE_GRAIN_MARKS = (
    "使用条件", "适用条件", "成立条件", "边界条件", "限制条件", "条件检查",
    "常见变形", "变形技巧", "计算技巧", "替换规则", "判断步骤", "判断流程", "证明步骤",
    "例题", "典型例子", "题型", "选择题", "填空题", "计算题", "证明题", "综合题",
    "注意", "易错", "误区", "陷阱", "提醒", "小结", "总结", "变量含义", "符号说明",
)
# 后缀式降级：`XXX 的适用条件` → `XXX`；只取适合做尾缀的那批
_DEFAULT_FINE_SUFFIX_MARKS = (
    "使用条件", "适用条件", "成立条件", "常见变形", "计算技巧", "例题", "易错", "注意",
)


def fine_grain_marks() -> tuple[str, ...]:
    """细粒度点词表（可配置：``CATALOG_FINE_GRAIN_MARKS``）。"""
    return _env_marks("CATALOG_FINE_GRAIN_MARKS", _DEFAULT_FINE_GRAIN_MARKS)


def fine_suffix_marks() -> tuple[str, ...]:
    """后缀式降级词表（可配置：``CATALOG_FINE_SUFFIX_MARKS``）。"""
    return _env_marks("CATALOG_FINE_SUFFIX_MARKS", _DEFAULT_FINE_SUFFIX_MARKS)


@lru_cache(maxsize=8)
def fine_grain_re() -> re.Pattern[str]:
    marks = fine_grain_marks()
    return re.compile("|".join(re.escape(mark) for mark in marks)) if marks else re.compile(r"(?!x)x")


def _env_marks(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """从 `.env` 读词表：未设置 → 默认；设置 → 以配置为准（空值 = 关闭该判定）。"""
    raw = os.getenv(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def item_marks() -> tuple[str, ...]:
    """辅助性内容词表（例题/易错/小结…）。"""
    return _env_marks("CATALOG_ITEM_MARKS", _DEFAULT_ITEM_MARKS)


def title_marks() -> tuple[str, ...]:
    """知识标题词表（定义/定理/…），用于候选打分与"知识点味"判定。"""
    return _env_marks("CATALOG_TITLE_MARKS", _DEFAULT_TITLE_MARKS)


@lru_cache(maxsize=8)
def _mark_re(marks: tuple[str, ...]) -> re.Pattern[str] | None:
    if not marks:
        return None
    return re.compile("|".join(re.escape(mark) for mark in marks))


def is_item_heading(text: object) -> bool:
    """辅助性内容标题（例题/易错/小结…）：不建节点。词表为空时一律返回 False。"""
    pattern = _mark_re(item_marks())
    return bool(pattern.search(str(text or ""))) if pattern else False


@lru_cache(maxsize=4)
def placeholder_re() -> re.Pattern[str]:
    """占位名形态正则（可用 ``CATALOG_PLACEHOLDER_RE`` 整体替换）。"""
    raw = os.getenv("CATALOG_PLACEHOLDER_RE")
    return re.compile(raw if raw is not None else _DEFAULT_PLACEHOLDER_RE)


def is_placeholder_name(text: object) -> bool:
    """占位名（核心知识点/知识概要/其他…）：**按形态**判定，不枚举见过的具体名字。

    与结构判定配合使用：``章名 == 其唯一主题名``、``主题名 == 其唯一 KP 名`` 这类
    "凑层级"形状在任何学科下都该被识别（见 `merge._retitle_duplicate_topic`），
    而本函数只负责"名字本身没有信息量"这一半。
    """
    blob = "".join(str(text or "").split())
    return bool(blob) and bool(placeholder_re().match(blob))


@lru_cache(maxsize=4)
def noise_title_re() -> re.Pattern[str]:
    return re.compile(_DEFAULT_NOISE_TITLE_RE, re.I)


def noise_short_titles() -> set[str]:
    return set(_DEFAULT_NOISE_SHORT_TITLES)


def body_like_endings() -> tuple[str, ...]:
    return _DEFAULT_BODY_LIKE_ENDINGS
