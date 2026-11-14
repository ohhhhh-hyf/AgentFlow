"""独立模板加载与元数据解析引擎 (零旧代码依赖).

职责:
1. 根据模式 (normal / agenda) 与语言 (zh / en) 加载 Markdown 模板;
2. 议题模式自动优先从 agenda_templates 读取, 缺失时平滑回退 templates;
3. 正则解析并剥离 <!-- layout ... --> 元数据 (mode);
4. 物理剥离历史残留 <!-- requirement ... --> 写作背景要求 (新架构中已彻底解耦废弃);
5. 原生支持跨行、换行及内嵌复选框列表的方括号占位符 [...] 提取;
6. 提供纯净的 Markdown 正文与结构化元数据供 Agent 消费.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

_LAYOUT_BLOCK_RE = re.compile(
    r"<!--\s*layout(?:\s*:\s*([^\n>]+))?\s*\n?(.*?)-->",
    flags=re.DOTALL | re.IGNORECASE,
)
_REQUIREMENT_BLOCK_RE = re.compile(
    r"<!--\s*requirement\s*\n?(.*?)-->",
    flags=re.DOTALL | re.IGNORECASE,
)
_HEADING_1_RE = re.compile(r"^#\s+([^\n]+)$", flags=re.MULTILINE)


@dataclass
class Placeholder:
    """方括号占位符详细信息 (原生支持跨行与嵌套结构)."""

    raw: str  # 包含外层 [ ] 的完整字符串
    inner: str  # 剥离外层 [ ] 后的内部描述内容
    start: int  # 起始字符索引
    end: int  # 结束字符索引 (不包含)


def extract_placeholders(text: str) -> list[Placeholder]:
    """提取模板中的所有方括号占位符，原生支持跨行换行及内嵌括号（如 `- [ ]` 待办复选框）。

    与历史脆弱扫描器的核心差异：
    1. 不按行切分 (免受 splitlines 截断影响)，按深度栈完整匹配跨行括号；
    2. 支持内部包含 Markdown 列表、三级标题与子栏说明；
    3. 排除 Markdown 链接语法（如 `[文字](http://...)`）。
    """
    placeholders: list[Placeholder] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "[" and (i == 0 or text[i - 1] != "\\"):
            start = i
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if text[j] == "[":
                    depth += 1
                elif text[j] == "]":
                    depth -= 1
                j += 1
            if depth == 0:
                # 检查是否紧跟 ( 作为 Markdown 链接，如 [text](url)
                is_link = j < n and text[j] == "("
                if not is_link:
                    raw = text[start:j]
                    placeholders.append(
                        Placeholder(
                            raw=raw,
                            inner=raw[1:-1],
                            start=start,
                            end=j,
                        )
                    )
                i = j
                continue
        i += 1
    return placeholders


@dataclass
class TemplateMetadata:
    """模板元数据载体."""

    mode: Literal["column_major", "topic_major", "normal"] = "column_major"
    source_path: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class TemplateResult:
    """模板读取与解析后的完整产物."""

    text: str
    meta: TemplateMetadata
    sections: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)
    placeholder_items: list[Placeholder] = field(default_factory=list)

    def __iter__(self):
        """支持作为二元组解构: text, metadata = load_template(...)"""
        yield self.text
        yield {
            "layout": {
                "mode": self.meta.mode,
            },
            "sections": self.sections,
            "placeholders": self.placeholders,
        }


def parse_template_metadata(raw_content: str) -> tuple[str, TemplateMetadata]:
    """解析并物理剥离 HTML 注释元数据, 返回 (纯净文本, 元数据对象)."""
    meta = TemplateMetadata()
    cleaned = raw_content

    # 1. 抽取并物理剥离 <!-- requirement ... --> (废弃无用元数据，仅做剥离防污染)
    cleaned = _REQUIREMENT_BLOCK_RE.sub("", cleaned)

    # 2. 抽取并剥离 <!-- layout ... -->
    m_layout = _LAYOUT_BLOCK_RE.search(cleaned)
    if m_layout:
        inline_val = (m_layout.group(1) or "").strip()
        body_val = (m_layout.group(2) or "").strip()

        if inline_val:
            meta.mode = "topic_major" if "topic_major" in inline_val.lower() else "column_major"

        # 解析多行 key: value (向后兼容历史注释)
        if body_val:
            for line in body_val.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k == "mode":
                        meta.mode = "topic_major" if v.lower() == "topic_major" else "column_major"
                    elif k != "container":
                        meta.extra[k] = v

        cleaned = cleaned[: m_layout.start()] + cleaned[m_layout.end() :]

    # 3. 规整空行 (收敛连续 3+ 个换行到 2 个换行)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned, meta


def load_template(
    template_id: str = "general_minutes",
    mode: str = "normal",
    is_agenda: bool | None = None,
    lang: str = "zh",
    resources_root: Path | None = None,
) -> TemplateResult:
    """加载并解析模板文件.

    Args:
        template_id: 模板ID或文件名 (如 "general_minutes", 自动补齐 .md)
        mode: "agenda" (议题模式) 或 "normal" (普通模式)
        is_agenda: 便捷布尔值开关，设置时优先于 mode
        lang: 语言代码 ("zh" / "en")
        resources_root: resources 目录的绝对路径, 默认指向 demo/resources

    Returns:
        TemplateResult: 包含纯净 Markdown 文本、元数据、一级栏目清单及占位符清单
    """
    if is_agenda is not None:
        mode = "agenda" if is_agenda else "normal"

    if not template_id or not template_id.strip():
        template_id = "general_minutes"

    file_name = template_id if template_id.endswith(".md") else f"{template_id}.md"

    if resources_root is None:
        resources_root = Path(__file__).resolve().parent.parent / "resources"

    normal_dir = resources_root / "templates" / lang
    agenda_dir = resources_root / "agenda_templates" / lang

    target_path: Path | None = None

    if mode == "agenda":
        # 议程模式: 优先 agenda_templates, 缺失则平滑回退 normal templates
        candidate_agenda = agenda_dir / file_name
        if candidate_agenda.is_file():
            target_path = candidate_agenda
        else:
            candidate_normal = normal_dir / file_name
            if candidate_normal.is_file():
                target_path = candidate_normal
    else:
        # 普通模式: 直接读取 normal templates
        candidate_normal = normal_dir / file_name
        if candidate_normal.is_file():
            target_path = candidate_normal

    if target_path is None or not target_path.is_file():
        # 若指定模板不存在，平滑回退至通用标杆模板 general_minutes
        if template_id != "general_minutes":
            return load_template(
                template_id="general_minutes",
                mode=mode,
                is_agenda=is_agenda,
                lang=lang,
                resources_root=resources_root,
            )
        raise FileNotFoundError(
            f"未找到模板文件: template_id={template_id!r}, mode={mode!r}, lang={lang!r}. "
            f"尝试路径: agenda={agenda_dir / file_name}, normal={normal_dir / file_name}"
        )

    raw_text = target_path.read_text(encoding="utf-8")
    cleaned_text, metadata = parse_template_metadata(raw_text)
    metadata.source_path = str(target_path)

    # 提取一级标题栏目清单
    sections = _HEADING_1_RE.findall(cleaned_text)

    # 提取所有方括号占位符 (支持跨行)
    items = extract_placeholders(cleaned_text)
    placeholders = [item.inner for item in items]

    return TemplateResult(
        text=cleaned_text,
        meta=metadata,
        sections=sections,
        placeholders=placeholders,
        placeholder_items=items,
    )
