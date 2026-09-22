"""tools.templates.router.preview —— 模板路由·预览层：从模板解析出的「已列维度」判定。

用途：`_gate` 用 ``extract_listed_aspects`` / ``_aspect_has_fixed_heading`` / ``_aspect_has_own_slot`` 判断自然语言里的某个维度是否已在模板中有固定标题或独立槽位，避免编译时重复立栏。

历史：本模块曾同时承载"预览 ↔ 可读文本 ↔ 编辑模型"的三段转换（旧单体 template_router.py
的遗留接口）。2026-09-21 清理时确认那四个函数在本仓库无任何调用方，且只服务于
已废弃的编辑器界面，故删除；保留下来的三个判定函数仍在门禁链路里生效。
"""
from __future__ import annotations
import logging
import re
from typing import Any

from ._base import _split_aspect_connectors, _strip_heading_number, iter_placeholders
from ._detect import detect_template_kind
from ._placeholder import preview_to_template, template_to_preview

logger = logging.getLogger(__name__)


def extract_listed_aspects(description: str) -> list[str]:
    """从自然语言里抽出并列要点名（顿号 / 与 / 和 / 及），用于编译保真。

    例：
    - 「概括背景、对象、核心目的」→ 三项
    - 「整体梳理流程与核心脉络」→ [流程, 核心脉络]
    """
    text = description or ""
    aspects: list[str] = []

    def _strip_lead(chunk: str) -> str:
        # 可叠剥引导语：整体梳理…、概括…、只要三部分：…、只要…
        prev = None
        while prev != chunk:
            prev = chunk
            chunk = re.sub(
                r"^(?:请)?(?:约?\d+\s*[-–—~～]?\s*\d*\s*字)",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:只要|仅需|只需|需要)(?:约)?"
                r"(?:[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点))?"
                r"[：:，,\s]*",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:约)?"
                r"[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点)"
                r"[：:，,\s]*",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:整体|分别|依次|逐一|并|再|并请)",
                "",
                chunk,
            ).strip(" ，,：:")
            chunk = re.sub(
                r"^(?:用[^，,]{0,12})?(?:概括|梳理|说明|写清|写明|覆盖|包含|包括|"
                r"总结|提炼|描述|介绍|回顾)",
                "",
                chunk,
            ).strip(" ，,：:")
            # 尾部数量壳：「…两段」「…三部分」
            chunk = re.sub(
                r"(?:约)?[一二三四五六七八九十两\d]+\s*(?:部分|段|块|节|点)$",
                "",
                chunk,
            ).strip(" ，,：:")
        return chunk

    def _clean_piece(p: str) -> str:
        p = (p or "").strip()
        p = re.sub(r"^(?:以及|和|与|及)", "", p).strip()
        p = _strip_lead(p)
        return p.strip()

    # 按句号/分号/逗号切开，再在片段内处理顿号与「与/和/及」
    for chunk in re.split(r"[。；;\n，,]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        # 纯字数约束片段跳过
        if re.fullmatch(r"(?:约?\d+\s*[-–—~～]?\s*\d*\s*字)", chunk):
            continue
        if "、" not in chunk and not re.search(r"[与和及]", chunk):
            continue
        chunk = _strip_lead(chunk)
        if not chunk:
            continue
        pieces = (
            [p.strip() for p in chunk.split("、") if p.strip()]
            if "、" in chunk
            else [chunk]
        )
        for p in pieces:
            p = _clean_piece(p)
            if not p:
                continue
            for sub in _split_aspect_connectors(p):
                sub = _clean_piece(sub)
                # 过滤纯数字/字数
                if re.fullmatch(r"[\d\s\-–—~～字约]+", sub):
                    continue
                if 2 <= len(sub) <= 16 and re.search(r"[\u4e00-\u9fff]", sub):
                    aspects.append(sub)

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for a in aspects:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def _heading_covers_aspect_alone(
    title: str, aspect: str, all_aspects: list[str]
) -> bool:
    """标题是否单独承载某一并列要点（拒绝「A与B」合并标题冒充两侧都覆盖）。"""
    clean = _strip_heading_number(title)
    if not clean or aspect not in clean:
        return False
    others = [a for a in all_aspects if a != aspect and a in clean]
    if others and re.search(r"[与和及、]", clean):
        return False
    return True


def _heading_line_is_placeholder_only(heading_inner: str) -> bool:
    """标题行内容是否几乎只是一个占位（如 ``[写背景]``），没有固定栏目名。"""
    inner = (heading_inner or "").strip()
    # 去掉编号后再看
    inner = _strip_heading_number(inner)
    if not inner:
        return True
    # 整段就是一个 [占位]
    if re.fullmatch(r"\[[^\[\]]+\]", inner):
        return True
    # 去掉所有占位后几乎没有中文固定字
    fixed = re.sub(r"\[[^\[\]]+\]", "", inner).strip()
    return not re.search(r"[\u4e00-\u9fffA-Za-z]{2,}", fixed)


def _aspect_has_fixed_heading(
    aspect: str, compiled: str, all_aspects: list[str]
) -> bool:
    """并列要点是否有**固定文字**小节标题（栏目名可见，非「标题即占位」）。"""
    for m in re.finditer(r"(?m)^(#{1,3})\s+(.+)$", compiled or ""):
        raw_title = m.group(2).strip()
        if _heading_line_is_placeholder_only(raw_title):
            continue
        if _heading_covers_aspect_alone(raw_title, aspect, all_aspects):
            return True
    for m in re.finditer(
        r"(?m)^\s*(?:[0-9]+[\.、]|[一二三四五六七八九十]+[、.])\s*(\S.+)$",
        compiled or "",
    ):
        raw_title = m.group(1).strip()
        if _heading_line_is_placeholder_only(raw_title):
            continue
        if _heading_covers_aspect_alone(raw_title, aspect, all_aspects):
            return True
    return False


def _aspect_has_own_slot(
    aspect: str, compiled: str, all_aspects: list[str]
) -> bool:
    """并列要点是否拥有独立小节标题或独立占位说明。"""
    if _aspect_has_fixed_heading(aspect, compiled, all_aspects):
        return True
    # 占位说明单独点名该要点，且同占位未同时塞进另一并列要点
    for m in iter_placeholders(compiled or ""):
        hint = m.group(1)
        if aspect not in hint:
            continue
        others = [a for a in all_aspects if a != aspect and a in hint]
        if others and re.search(r"[与和及、]", hint):
            continue
        return True
    return False
