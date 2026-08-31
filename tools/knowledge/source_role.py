"""入库资料角色与标题层级。

来源角色只作为证据标签；目录骨架由标题层级、标题质量和内容价值共同决定。
"""
from __future__ import annotations

import re
from pathlib import Path

ROLE_MATERIAL = "material"
ROLE_NOTES = "notes"
ROLE_TEACHER = "teacher"
ROLE_UNKNOWN = "unknown"

_TEACHER_MARKS = ("teacher", "划重点", "focus", "最后一课")
_NOTES_MARKS = ("note", "笔记", "notebook", "错题本")
_MATERIAL_EXTS = {".pdf", ".docx", ".pptx", ".xlsx"}
_TEACHER_RE = re.compile(r"(老师|教师|划重点|考试范围|必考|重点\s*[:：]|最后一课)")
_MATERIAL_RE = re.compile(r"(课件|讲义|教材|课程目标|教学目标|contents|chapter|section)", re.I)
_NOTES_RE = re.compile(r"(笔记|错题|易错|例题|知识点|总结|注意|我的|课堂记录|复习)", re.I)

_CHAPTER = re.compile(
    r"^(?:#{1,2}\s+)?第[一二三四五六七八九十百零0-9]+章\s*[：:\s]*(.+)$"
)
_SECTION = re.compile(
    r"^(?:#{1,3}\s+)?(?:第[一二三四五六七八九十百零0-9]+节|[一二三四五六七八九十]+、)\s*(.+)$"
)
_MD_HEAD = re.compile(r"^(#{1,4})\s+(.+)$")
_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(.+)$")
_SENT_END_RE = re.compile(r"[。！？；;]$")
# 兜底标题：行首特征词（定义/定理/易错/例题…）。标题行不进正文块，会丢内容，
# 所以只认「纯短语」或「特征词+冒号+≤6 字短语」——带实质内容的句子不当标题。
_TITLE_HEAD_RE = re.compile(
    r"^(?:定义|定理|性质|公式|方法|概念|原理|规则|证明|分类|区别|结论|特征)"
    r"(?:[\d一二三四五六七八九十]?\s*[：:]?\s*.{0,10})?$"
)
_ITEM_ONLY_HEAD_RE = re.compile(
    r"^(?:例题|例[0-9一二三四五六七八九十]|易错|注意|重点|总结|要点|技巧|步骤|题型|提醒|小结)"
    r"(?:[\d一二三四五六七八九十]?\s*[：:]?\s*.{0,12})?$"
)
_GENERIC_HEAD_RE = re.compile(
    r"^(?:定义|定理|性质|公式|方法|概念|原理|规则|证明|分类|区别|结论|特征)"
    r"[\d一二三四五六七八九十]?$"
)


def is_ocr_notes_file(filename: str) -> bool:
    """OCR 入库产物（ocr_时间戳.md）一律按学生笔记，不看正文里有没有「笔记」二字。"""
    stem = Path(filename or "").stem.lower()
    return stem.startswith("ocr_")


def classify_source_role(filename: str, text: str = "") -> str:
    """推断来源角色：文件名强信号优先，内容其次，格式兜底。

    文件名含 note/笔记 → 笔记；含 teacher/划重点/focus → 老师。
    OCR 导出的 ``ocr_*.md`` 视为学生笔记。
    避免学生笔记里出现「必考/重点」等词就被整体误判成老师文本。
    """
    name = Path(filename or "").name.lower()
    stem = Path(filename or "").stem.lower()
    suffix = Path(filename or "").suffix.lower()
    blob = f"{name} {stem}"
    sample = str(text or "")[:4000]
    if any(mark in blob for mark in _TEACHER_MARKS):
        return ROLE_TEACHER
    if any(mark in blob for mark in _NOTES_MARKS) or is_ocr_notes_file(filename):
        return ROLE_NOTES
    if _TEACHER_RE.search(sample):
        return ROLE_TEACHER
    if _NOTES_RE.search(sample):
        return ROLE_NOTES
    if suffix in _MATERIAL_EXTS or _MATERIAL_RE.search(sample):
        return ROLE_MATERIAL
    return ROLE_UNKNOWN


def heading_level(line: str) -> tuple[int, str] | None:
    """返回 (层级, 标题)。1=chapter, 2=topic, 3=knowledge_point。"""
    text = " ".join(str(line or "").split()).strip()
    if not text or len(text) > 80:
        return None
    md = _MD_HEAD.match(text)
    if md:
        return min(len(md.group(1)), 3), md.group(2).strip()
    chapter = _CHAPTER.match(text)
    if chapter:
        title = chapter.group(1).strip() or text
        return 1, title
    section = _SECTION.match(text)
    if section:
        return 2, section.group(1).strip()
    numbered = _NUM_HEAD.match(text)
    if numbered:
        depth = numbered.group(1).count(".") + 1
        return min(depth, 3), numbered.group(2).strip()
    # 兜底只接收带明确对象的知识标题；例题/注意/步骤等细碎容器留作正文证据。
    if _ITEM_ONLY_HEAD_RE.match(text) or _GENERIC_HEAD_RE.match(text):
        return None
    if len(text) <= 28 and not _SENT_END_RE.search(text) and _TITLE_HEAD_RE.match(text):
        return 3, text
    return None
