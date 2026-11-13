"""纪要流式生成后处理清洗体系 (极简自包含正则与字符串规整，0ms 开销).

职责:
1. clean_markdown_fence: 剥离代码围栏与大模型开场白，保证首字符为 '#';
2. clean_heading_brackets: 防御性清洗标题行中偶发的方括号 '[]';
3. collapse_multiple_newlines: 连续 3+ 空行收敛为标准 2 个换行;
4. prune_empty_subsections: 裁剪无实质内容的空子栏与套话行 ("无", "未提及", "暂无");
5. localize_agenda_headings_for_en: 英文模式下将中文数字序号转换为罗马数字序号;
6. postprocess_minutes_markdown: 统一后处理管道.
"""
from __future__ import annotations

import re

# 匹配首行代码围栏及可能的前言寒暄
_FENCE_START_RE = re.compile(r"^\s*```(?:markdown)?\s*\n", flags=re.IGNORECASE)
_FENCE_END_RE = re.compile(r"\n\s*```\s*$", flags=re.IGNORECASE)

# 标题行内部方括号清洗正则: 匹配标题行内的 [xxx] 并替换为 xxx
_HEADING_LINE_RE = re.compile(r"^(#+[^\n]*)$", flags=re.MULTILINE)
_INLINE_BRACKETS_RE = re.compile(r"\[([^\]\n]+)\]")

# 中文数字转罗马数字映射 (最高支持到二十)
_ZH_TO_ROMAN = {
    "一": "I",
    "二": "II",
    "三": "III",
    "四": "IV",
    "五": "V",
    "六": "VI",
    "七": "VII",
    "八": "VIII",
    "九": "IX",
    "十": "X",
    "十一": "XI",
    "十二": "XII",
    "十三": "XIII",
    "十四": "XIV",
    "十五": "XV",
    "十六": "XVI",
    "十七": "XVII",
    "十八": "XVIII",
    "十九": "XIX",
    "二十": "XX",
}

# 匹配标题中的中文序号: 如 '## 一. ' 或 '### 一、 ' 或 '## 一 '
_ZH_NUMERAL_HEADING_RE = re.compile(
    r"^(#{2,3}\s*)([一二三四五六七八九十]+)[\.、\s]*\s*",
    flags=re.MULTILINE,
)

# 套话无意义内容关键词
_EMPTY_BOILERPLATE_RE = re.compile(
    r"^\s*(?:无|暂无|未提及|无明确决议|无相关决议|本栏省略|本栏隐去|略)\s*[。.]?\s*$",
    flags=re.IGNORECASE,
)


def clean_markdown_fence(text: str) -> str:
    """剥离首尾代码围栏及可能的寒暄开场白，确保输出直接以 '#' 开始."""
    if not text:
        return ""
    cleaned = text.strip()

    # 1. 剥离外层代码围栏
    if cleaned.startswith("```"):
        cleaned = _FENCE_START_RE.sub("", cleaned)
    if cleaned.endswith("```"):
        cleaned = _FENCE_END_RE.sub("", cleaned)
    cleaned = cleaned.strip()

    # 2. 若存在多余寒暄（首字符非 # 且文档中含有 #），定位至首个一级标题
    if cleaned and not cleaned.startswith("#"):
        first_h1 = cleaned.find("#")
        if first_h1 != -1:
            cleaned = cleaned[first_h1:].strip()

    return cleaned


def clean_heading_brackets(text: str) -> str:
    """防御性剔除标题行中偶发的方括号，例如 '# [全文摘要]' -> '# 全文摘要'，'## 一. [议题]' -> '## 一. 议题'."""
    def _clean_line(match: re.Match) -> str:
        line = match.group(1)
        return _INLINE_BRACKETS_RE.sub(r"\1", line)

    return _HEADING_LINE_RE.sub(_clean_line, text)


def collapse_multiple_newlines(text: str) -> str:
    """收敛连续 3 个及以上的换行符为段落间标准的 2 个换行 (\n\n)."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def prune_empty_subsections(text: str) -> str:
    """裁剪无实质内容的空三级子栏（形如 '### 结论定调\n\n暂无' 或 '### 结论定调\n\n### 下一项'）."""
    lines = text.splitlines()
    result_lines: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        # 仅针对三级子栏 (###) 进行空值判定与清理
        if line.startswith("### "):
            # 查看该子栏下方是否有内容，直至下一个标题或文档结束
            sub_body_lines: list[str] = []
            j = i + 1
            while j < n and not lines[j].startswith("#"):
                sub_body_lines.append(lines[j])
                j += 1

            # 评估内容是否为空或仅有套话
            sub_body_text = "\n".join(sub_body_lines).strip()
            is_empty_or_boilerplate = (
                not sub_body_text
                or bool(_EMPTY_BOILERPLATE_RE.match(sub_body_text))
            )

            if is_empty_or_boilerplate:
                # 剔除该标题及套话行，跳过至下一个标题
                i = j
                continue
            else:
                result_lines.append(line)
                i += 1
        else:
            result_lines.append(line)
            i += 1

    return "\n".join(result_lines)


def localize_agenda_headings_for_en(text: str) -> str:
    """将议题标题中的中文数字序号本地化为罗马数字 (如 '## 一. ' -> '## I. ')."""
    def _replace_zh_numeral(match: re.Match) -> str:
        prefix = match.group(1)
        zh_num = match.group(2)
        roman = _ZH_TO_ROMAN.get(zh_num, zh_num)
        return f"{prefix}{roman}. "

    return _ZH_NUMERAL_HEADING_RE.sub(_replace_zh_numeral, text)


def postprocess_minutes_markdown(raw_markdown: str, lang: str = "zh") -> str:
    """统合后处理管道: 剥离围栏 -> 清除标题方括号 -> 英文序号本地化 -> 空子栏清理 -> 空行收敛."""
    if not raw_markdown:
        return ""

    # 1. 剥离代码围栏与开场白
    processed = clean_markdown_fence(raw_markdown)

    # 2. 清除标题方括号
    processed = clean_heading_brackets(processed)

    # 3. 若为英文模式，执行序号罗马化
    if (lang or "").strip().lower().startswith("en"):
        processed = localize_agenda_headings_for_en(processed)

    # 4. 裁剪无实质内容的空三级子栏
    processed = prune_empty_subsections(processed)

    # 5. 规整空行
    processed = collapse_multiple_newlines(processed)

    return processed
