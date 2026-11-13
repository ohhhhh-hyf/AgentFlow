"""独立模板加载与元数据解析引擎 (零旧代码依赖).

职责:
1. 根据模式 (normal / agenda) 与语言 (zh / en) 加载 Markdown 模板;
2. 议题模式自动优先从 agenda_templates 读取, 缺失时平滑回退 templates;
3. 正则解析并剥离 <!-- layout ... --> 元数据 (mode, container);
4. 正则解析并剥离 <!-- requirement ... --> 写作背景要求;
5. 提供纯净的 Markdown 正文与结构化元数据供 Agent 消费.
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
class TemplateMetadata:
    """模板元数据载体."""

    mode: Literal["column_major", "topic_major", "normal"] = "column_major"
    container: str = ""
    requirement: str = ""
    source_path: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class TemplateResult:
    """模板读取与解析后的完整产物."""

    text: str
    meta: TemplateMetadata
    sections: list[str] = field(default_factory=list)

    def __iter__(self):
        """支持作为二元组解构: text, metadata = load_template(...)"""
        yield self.text
        yield {
            "layout": {
                "mode": self.meta.mode,
                "container": self.meta.container,
            },
            "requirement": self.meta.requirement,
            "sections": self.sections,
        }


def parse_template_metadata(raw_content: str) -> tuple[str, TemplateMetadata]:
    """解析并物理剥离 HTML 注释元数据, 返回 (纯净文本, 元数据对象)."""
    meta = TemplateMetadata()
    cleaned = raw_content

    # 1. 抽取并剥离 <!-- requirement ... -->
    m_req = _REQUIREMENT_BLOCK_RE.search(cleaned)
    if m_req:
        meta.requirement = m_req.group(1).strip()
        cleaned = cleaned[: m_req.start()] + cleaned[m_req.end() :]

    # 2. 抽取并剥离 <!-- layout ... -->
    m_layout = _LAYOUT_BLOCK_RE.search(cleaned)
    if m_layout:
        inline_val = (m_layout.group(1) or "").strip()
        body_val = (m_layout.group(2) or "").strip()

        if inline_val:
            meta.mode = "topic_major" if "topic_major" in inline_val.lower() else "column_major"

        # 解析多行 key: value
        if body_val:
            for line in body_val.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    if k == "mode":
                        meta.mode = "topic_major" if v.lower() == "topic_major" else "column_major"
                    elif k == "container":
                        meta.container = v
                    else:
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
        TemplateResult: 包含纯净 Markdown 文本、元数据及一级栏目清单
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

    return TemplateResult(text=cleaned_text, meta=metadata, sections=sections)
