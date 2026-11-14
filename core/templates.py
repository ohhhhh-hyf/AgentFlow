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

# 29 款标准业务场景中文名与英文模板 ID 双向对齐表（单一事实源）
STANDARD_TEMPLATES: dict[str, str] = {
    "团队例会": "team_meeting",
    "项目进度会": "project_progress",
    "决策评审会": "decision_review",
    "工作研讨会": "workshop_session",
    "总结复盘会": "retrospective_session",
    "沟通交流会": "exchange_forum",
    "课堂记录": "class_transcript",
    "专题讲座": "special_lecture",
    "小组讨论": "group_seminar",
    "知识笔记": "knowledge_memo",
    "辩论会": "debate_forum",
    "调研访谈": "research_dialogue",
    "采访记录": "interview_transcript",
    "面试报告": "hiring_report",
    "面试复盘": "interview_debrief",
    "就医咨询": "clinical_advisory",
    "心理咨询": "psychological_session",
    "法律咨询": "legal_advisory",
    "庭审记录": "court_transcript",
    "合同审核": "contract_vetting",
    "新闻发布": "media_briefing",
    "产品发布": "product_launch",
    "政府报告": "government_bulletin",
    "媒体问答": "media_qa_session",
    "通用纪要": "general_minutes",
    "个人备忘": "personal_memo",
    "对话记录": "conversation_transcript",
    "参观游览": "site_visit_tour",
    "家校沟通": "home_school_liaison",
}

# 常见别名容错
TEMPLATE_ALIASES: dict[str, str] = {
    "通用": "general_minutes",
    "常规纪要": "general_minutes",
    "通用纪要/其他": "general_minutes",
    "通用/其他": "general_minutes",
    "其他": "general_minutes",
}

KNOWN_TEMPLATE_IDS: set[str] = set(STANDARD_TEMPLATES.values())

_YAML_MAPPING_CACHE: dict[str, str] | None = None


def _load_yaml_template_mapping() -> dict[str, str]:
    """从 YAML 配置文件中动态解析中英文映射（支持缓存与静默容错）。"""
    global _YAML_MAPPING_CACHE
    if _YAML_MAPPING_CACHE is not None:
        return _YAML_MAPPING_CACHE

    _YAML_MAPPING_CACHE = {}
    candidate_paths = [
        Path(__file__).resolve().parent.parent / "cm_template_v2_changed_0722.yaml",
        Path(__file__).resolve().parent.parent.parent / "cm_template_v2_changed_0722.yaml",
        Path.cwd() / "demo" / "cm_template_v2_changed_0722.yaml",
        Path.cwd() / "cm_template_v2_changed_0722.yaml",
    ]
    for cp in candidate_paths:
        if cp.is_file():
            try:
                import yaml

                data = yaml.safe_load(cp.read_text(encoding="utf-8"))
                templates = (data or {}).get("cm-template-v2", {}).get("templates", [])
                for t in templates:
                    raw_id = t.get("id", "")
                    name = t.get("name", "")
                    m = re.search(r"\.([^.]+)\}$", raw_id)
                    tid = m.group(1).replace("-", "_") if m else raw_id
                    if tid and name and tid != "user_customized":
                        _YAML_MAPPING_CACHE[name] = tid
                        _YAML_MAPPING_CACHE[tid.lower()] = tid
                break
            except Exception:
                continue

    return _YAML_MAPPING_CACHE


def resolve_template_id(template_value: str | None) -> str:
    """将输入的模板标识标准化为合法的英文模板 ID。

    核心逻辑：
    1. 空值或未指定 (None / '' / 纯空白) -> 返回 '' (触发上层智能模板分类器)；
    2. 废除历史 'auto' / 'none' / '自动' 等魔法字符串，只要传了具体值直接进入严格映射；
    3. 去除首尾空白，剥离可能附带的 '.md' 后缀（不区分大小写）；
    4. 命中标准英文 ID（大小写不敏感，如 'project_progress'、'TEAM_MEETING'） -> 返回标准小写英文 ID；
    5. 命中中文名称（如 '项目进度会'、'通用纪要'） -> 返回对应英文 ID；
    6. 命中别名（如 '常规纪要'、'通用'） -> 返回 'general_minutes'；
    7. 尝试动态加载 YAML 补充映射（若相关 YAML 配置文件存在）；
    8. 未知标识 -> 返回清洗后的原标识字符串（由 load_template 寻址或平滑兜底）。
    """
    if template_value is None:
        return ""
    val = template_value.strip()
    if not val:
        return ""

    if val.lower().endswith(".md"):
        val = val[:-3].strip()
    if not val:
        return ""

    folded = val.lower()

    # 1. 命中已知标准英文 ID (大小写不敏感)
    if folded in KNOWN_TEMPLATE_IDS:
        return folded

    # 2. 命中中文名称
    if val in STANDARD_TEMPLATES:
        return STANDARD_TEMPLATES[val]

    # 3. 命中别名
    if val in TEMPLATE_ALIASES:
        return TEMPLATE_ALIASES[val]
    if folded in TEMPLATE_ALIASES:
        return TEMPLATE_ALIASES[folded]

    # 4. 尝试 YAML 动态补充
    yaml_mapping = _load_yaml_template_mapping()
    if val in yaml_mapping:
        return yaml_mapping[val]
    if folded in yaml_mapping:
        return yaml_mapping[folded]

    return val


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

    canonical_id = resolve_template_id(template_id)
    if not canonical_id:
        canonical_id = "general_minutes"
    template_id = canonical_id

    file_name = f"{template_id}.md"

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
