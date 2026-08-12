"""template_router.py —— 模板路由层：自动判型 + 三路分派，无痛插入。

解决"模糊模板 / 自然语言描述模板"输出效果差的问题。三类模板自动分派：

- ``placeholder``（类型一）：含 ``[xxx]`` 占位符 → 程序解析结构，生成
  「固定文字 + 字段清单」的精确填充指令；优先走「字段 JSON + 程序拼装」
- ``spec``（类型二）：格式指令 + 示例（输入→输出配对）→ 指令/示例分离，
  示例原样作 few-shot 进用户消息，强化格式学习
- ``natural``（类型三）：用户用自然语言描述想要的样子 → LLM 编译成
  占位符模板（``maybe_compile_natural_template``），带保真检查与重试，
  再复用类型一路径

设计约束（无痛插入的承诺）：

1. 纯函数为主，**不 import 任何任务线 / domain**；``maybe_compile_natural_template``
   内部延迟 import ``llm_client``，仅当确为 natural 类型时才创建 client
2. ``route_template`` 任何异常 / 解析失败都返回 ``None``，调用方回退旧路径
3. 环境变量 ``TEMPLATE_ROUTER=off`` 一键关闭路由，恢复旧行为
4. ``validate_rendered_output`` 默认只读；拼装 / 修复路径另有显式 API
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from tools.template_prompt import PLACEHOLDER_RULES, SPEC_RULES

logger = logging.getLogger(__name__)

# 占位符：[xxx]（不含嵌套括号）
_PLACEHOLDER_RE = re.compile(r"\[([^\[\]]+)\]")
# 多选一分隔（如 [✅已完成 / 🔄进行中 / ⛔阻塞 / 未明确]）
_ENUM_SEP_RE = re.compile(r"\s*/\s*")
# 信息不足默认写法信号
_MISSING_HINT_RE = re.compile(r"未明确|未提及|无$")
# 中文（占位符说明多为中文）
_CN_RE = re.compile(r"[\u4e00-\u9fff]")
# emoji（状态枚举占位符）
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
# 说明式占位符信号词（纯中文但很短时兜底）
_HINT_WORD_RE = re.compile(r"根据|未明确|未提及|列出|原文|填写|说明|名称|内容|主题")
# 类型二（格式规范模板）的关键词信号
_SPEC_KEYWORDS = ("JSON", "数组", "示例", "格式规范", "严格输出", "输出格式")
# 类型二示例信号（含"输出示例"——与 _SPEC_SPLIT_MARKERS 对齐，避免误判为 natural）
_SPEC_EXAMPLE_MARKERS = ("输入：", "输出：", "```", "示例输入", "示例输出", "输出示例")
# 示例段切分标题（按出现顺序优先）
_SPEC_SPLIT_MARKERS = (
    "# 输出示例",
    "# 示例",
    "## 示例",
    "## 输出示例",
    "输出示例",
    "示例：",
)
# 表格分隔行
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
# 从自然语言描述抽取的意图线索
_CUE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("title", re.compile(r"标题|题目|主题|第一行")),
    ("time", re.compile(r"时间|日期|何时")),
    ("people", re.compile(r"参会|出席|人物|人员|谁参加|与会")),
    ("progress", re.compile(r"进展|进度|完成情况")),
    ("problem", re.compile(r"问题|风险|阻塞|困难|blocker")),
    ("next", re.compile(r"下一步|待办|行动|后续|action")),
    ("summary", re.compile(r"总结|概要|摘要|综述")),
    ("table", re.compile(r"表格|表头|列\b|markdown\s*表", re.I)),
    ("json", re.compile(r"\bJSON\b|数组|json", re.I)),
    ("decision", re.compile(r"决策|决议|拍板")),
    ("list", re.compile(r"列表|清单|分点|条目")),
    ("section_count", re.compile(r"([一二三四五六七八九十\d]+)\s*部分|([一二三四五六七八九十\d]+)\s*段|([123456789])\s*块")),
]
# 用户未提及时，编译结果不应擅自出现的「扩写」标记
_EXPANSION_GUARDS: list[tuple[re.Pattern[str], list[str], str]] = [
    (
        re.compile(r"参会|出席|人物|人员|与会"),
        ["参会人", "出席人员", "与会人员", "## 参会"],
        "参会/人员",
    ),
    (
        re.compile(r"待办|行动项|action\s*item|下一步|后续"),
        ["## 待办", "待办事项", "| 任务 |", "| 负责人 |"],
        "待办/行动",
    ),
    (
        re.compile(r"风险|阻塞|blocker"),
        ["## 风险", "风险与阻塞", "风险事项"],
        "风险",
    ),
    (
        re.compile(r"决策|决议"),
        ["## 决策", "决策事项", "决议事项"],
        "决策",
    ),
    (
        re.compile(r"时间|日期"),
        ["**时间**", "会议时间", "日期："],
        "时间",
    ),
]

# 编译缓存（进程内）：cache_key → 编译后的占位符模板文本
_COMPILE_CACHE: dict[str, str] = {}
# 编译失败计数（同 key 最多跳过连续失败，不永久拉黑）
_COMPILE_FAIL_COUNTS: dict[str, int] = {}
_COMPILE_FAIL_SKIP_THRESHOLD = 3
# 缓存版本：规则升级后自动失效旧缓存
_COMPILE_CACHE_VERSION = "v5-prompt-constraints"


def _looks_like_placeholder(content: str, next_char: str = "") -> bool:
    """判断 ``[...]`` 括号内容是否真是"占位符说明"（而非 JSON/代码/链接等）。

    占位符的特征：含中文说明词、含 emoji 状态枚举、多选一短选项；
    JSON 对象（``{...}``）、字符串字面量（``"..."``）不算占位符；
    Markdown 链接（``[文字](url)``，后随 ``(``）也不算。
    """
    content = content.strip()
    if not content:
        return False
    # Markdown 链接形态：[xxx](url)
    if next_char == "(":
        return False
    # JSON / 字面量形态：不是占位符
    if content.startswith("{") or content.startswith('"') or content.startswith("["):
        return False
    if _CN_RE.search(content):
        return True
    if _EMOJI_RE.search(content):
        return True
    parts = [p.strip() for p in _ENUM_SEP_RE.split(content) if p.strip()]
    if len(parts) >= 2 and all(len(p) <= 12 for p in parts):
        return True
    if _HINT_WORD_RE.search(content):
        return True
    return False


def is_router_enabled() -> bool:
    """路由开关：``TEMPLATE_ROUTER=off``（或 0/false/no）关闭，默认开启。"""
    value = os.getenv("TEMPLATE_ROUTER", "on").strip().lower()
    return value not in ("0", "false", "off", "no")


def detect_template_kind(text: str) -> str:
    """确定性判型（不调 LLM）：

    - 含 ``[xxx]`` 占位符 → ``placeholder``
    - 含格式指令关键词 + 示例信号 → ``spec``
    - 其余 → ``natural``（自然语言描述）
    """
    if not text or not text.strip():
        return "natural"
    if any(
        _looks_like_placeholder(
            m.group(1), next_char=text[m.end() : m.end() + 1]
        )
        for m in _PLACEHOLDER_RE.finditer(text)
    ):
        return "placeholder"
    # 整段偏散文、仅有 0-1 个疑似括号时，优先 natural，避免口语里的「例如」误判 spec
    prose_like = (
        len(text.strip()) < 400
        and "\n# " not in text
        and not text.strip().startswith("#")
        and text.count("```") == 0
    )
    if any(kw in text for kw in _SPEC_KEYWORDS) and any(
        marker in text for marker in _SPEC_EXAMPLE_MARKERS
    ):
        if prose_like and "输入：" not in text and "输出：" not in text:
            return "natural"
        return "spec"
    return "natural"


# ── 类型一：占位符模板解析 ─────────────────────────────────────

def parse_placeholder_template(template: str) -> list[dict]:
    """把占位符模板拆成段序列（交替：固定文字 / 字段）。

    返回示例：:

        [
            {"kind": "text", "text": "# "},
            {"kind": "field", "raw": "会议主题", "hint": "会议主题",
             "enum": None, "missing": False},
            {"kind": "text", "text": "\\n\\n- **时间**："},
            ...
        ]

    字段段额外字段：``enum``（多选一列表，非空即枚举）、
    ``missing``（占位符内是否声明"未明确/未提及"默认写法）。
    """
    segments: list[dict] = []
    pos = 0
    for m in _PLACEHOLDER_RE.finditer(template):
        content = m.group(1)
        is_link = template[m.end() : m.end() + 1] == "("
        if not _looks_like_placeholder(content) or is_link:
            continue  # 非占位符括号（JSON/链接等）→ 保留在后续固定文字段中
        if m.start() > pos:
            segments.append({"kind": "text", "text": template[pos : m.start()]})
        segments.append(_parse_field(content))
        pos = m.end()
    if pos < len(template):
        segments.append({"kind": "text", "text": template[pos:]})
    return segments


def _parse_field(raw: str) -> dict:
    hint = raw.strip()
    missing = bool(_MISSING_HINT_RE.search(raw))
    enum: list[str] | None = None
    candidates = [p.strip() for p in _ENUM_SEP_RE.split(raw)]
    # 多选一判定：以 / 切出 ≥2 项且每项较短（emoji 枚举 / 短选项）
    if len(candidates) >= 2 and all(1 <= len(c) <= 12 for c in candidates):
        enum = candidates
    return {
        "kind": "field",
        "raw": raw,
        "hint": hint,
        "enum": enum,
        "missing": missing,
    }


def _describe_field(index: int, seg: dict) -> str:
    desc = f"字段{index}（{seg['hint']}）"
    if seg["enum"]:
        desc += f"：多选一 {' / '.join(seg['enum'])}"
    if seg["missing"]:
        desc += "：信息不足时按占位符说明写（如「未提及」/「未明确」）"
    return desc


def _build_placeholder_user(context: str, template: str, segments: list[dict]) -> str:
    lines = [
        "本模板已判定为【类型一：占位符模板】，请直接按「保留固定文字、仅替换占位符、"
        "输出与模板结构对齐」执行。",
        "模板正文里的数量/字数/范围等说明（如约3行、约200字）必须遵守，不要全量堆砌。",
        "各小节/各表只填该位置应有的内容，不要把 A 节内容写进 B 节。",
        "模板结构已由系统解析如下：",
    ]
    field_no = 0
    for seg in segments:
        if seg["kind"] == "text":
            text = seg["text"]
            preview = text if len(text) <= 60 else text[:57] + "..."
            lines.append(f"- 固定文字（原样保留）：{preview!r}")
        else:
            field_no += 1
            lines.append(f"- {_describe_field(field_no, seg)}")
    return f"{context}\n\n模板原文：\n{template}\n\n【模板结构解析】\n" + "\n".join(lines)


# ── 类型二：格式规范模板（指令 / 示例分离）─────────────────────

def split_spec_template(template: str) -> tuple[str, str]:
    """把格式规范模板切成 (指令段, 示例段)。

    优先按示例标题切（``# 示例`` 等）；其次取最后一个代码块作为示例。
    切不出示例段时返回 ``(template, "")``。
    """
    for marker in _SPEC_SPLIT_MARKERS:
        idx = template.find(marker)
        if idx > 0:
            return template[:idx].strip(), template[idx:].strip()
    blocks = re.findall(r"```.*?```", template, flags=re.S)
    if blocks:
        example = blocks[-1]
        return template.replace(example, "").strip(), example.strip()
    return template, ""


def _build_spec_user(
    context: str,
    template: str,
    instruction: str,
    example: str,
) -> str:
    return (
        f"{context}\n\n"
        "本模板已判定为【类型二：格式规范模板】：示例仅演示格式，"
        "禁止照抄示例中的输入内容；严格按下方【格式指令】规定的字段结构与格式输出。\n\n"
        "【格式指令】\n"
        f"{instruction}\n\n"
        "【示例（仅演示格式）】\n"
        f"{example}"
    )


# ── 路由入口 ───────────────────────────────────────────────────

def route_template(
    context: str,
    template: str,
    render_prompt: str,
    template_prompt: str,
) -> tuple[str, str] | None:
    """自动判型分派，返回 ``(prompt, user)``；无法处理返回 ``None``。

    - 类型一 → 结构解析 + 精确填充指令；prompt 为基础规则 + PLACEHOLDER_RULES
      （LLM 只执行占位符填充规则，不再自行判型）
    - 类型二 → 指令/示例分离；prompt 为基础规则 + SPEC_RULES
      （LLM 只执行格式规范规则）
    - 类型三 → 编译由 bootstrap 侧 ``maybe_compile_natural_template`` 先行完成，
      此处一律回退旧路径（``None``），由调用方拼 FALLBACK_TEMPLATE_RULES
    - 开关关闭 / 解析异常 / 解析不到结构 → 回退旧路径（``None``），
      由调用方按旧行为处理（此时才需要 LLM 自行判断模板类型）
    """
    if not is_router_enabled():
        return None
    kind = detect_template_kind(template)
    try:
        if kind == "placeholder":
            segments = parse_placeholder_template(template)
            if not any(s["kind"] == "field" for s in segments):
                return None
            return template_prompt + PLACEHOLDER_RULES, _build_placeholder_user(
                context, template, segments
            )
        if kind == "spec":
            instruction, example = split_spec_template(template)
            if not example:
                return None
            return template_prompt + SPEC_RULES, _build_spec_user(
                context, template, instruction, example
            )
    except Exception:  # noqa: BLE001 - 路由失败一律回退旧路径，绝不影响现有逻辑
        logger.warning("模板路由处理异常，已回退旧路径", exc_info=True)
    return None


# ── 渲染输出校验 ──────────────────────────────────────────────

def validate_rendered_output(
    rendered: str,
    template: str,
    kind: str | None = None,
) -> list[str]:
    """校验渲染输出，返回错误列表；空列表 = 通过。

    - 类型一：残留 ``[占位符]`` 检测 + 固定文字完整性（长度≥4 的固定段）
    - 类型二：模板声明 JSON/数组且输出以 ``[`` 开头时校验 JSON 合法性
    """
    errors: list[str] = []
    if not rendered or not rendered.strip():
        return ["渲染输出为空"]
    kind = kind or detect_template_kind(template)
    if kind == "placeholder":
        leftovers = [
            f"[{m.group(1)[:20]}]".replace("\n", " ")
            for m in _PLACEHOLDER_RE.finditer(rendered)
            if _looks_like_placeholder(
                m.group(1), next_char=rendered[m.end() : m.end() + 1]
            )
        ][:5]
        if leftovers:
            errors.append(f"输出残留占位符：{'、'.join(leftovers)}")
        segments = parse_placeholder_template(template)
        fixed = [
            s["text"].strip()
            for s in segments
            if s["kind"] == "text" and len(s["text"].strip()) >= 4
        ]
        # 归一化空白后再比对，避免换行差异误报
        rendered_norm = re.sub(r"\s+", " ", rendered)
        missing_fixed = 0
        for text in fixed:
            text_norm = re.sub(r"\s+", " ", text)
            if text not in rendered and text_norm not in rendered_norm:
                missing_fixed += 1
                if missing_fixed <= 2:
                    errors.append(f"模板固定文字丢失：{text[:30]!r}")
        if missing_fixed > 2:
            errors.append(f"另有 {missing_fixed - 2} 处固定文字缺失")
    elif kind == "spec":
        stripped = rendered.strip()
        # 允许被 ``` 包裹
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
            stripped = stripped.strip()
        if ("JSON" in template or "数组" in template) and (
            stripped.startswith("[") or stripped.startswith("{")
        ):
            try:
                json.loads(stripped)
            except Exception as exc:
                errors.append(f"输出不是合法 JSON：{exc}")
    return errors


# ── 类型一：程序拼装（稳定填充）────────────────────────────────

def _line_placeholders(line: str) -> list[re.Match[str]]:
    out: list[re.Match[str]] = []
    for m in _PLACEHOLDER_RE.finditer(line):
        nxt = line[m.end() : m.end() + 1]
        if _looks_like_placeholder(m.group(1), next_char=nxt):
            out.append(m)
    return out


def _is_table_data_row(line: str) -> bool:
    if line.count("|") < 2:
        return False
    if _TABLE_SEP_RE.match(line):
        return False
    return bool(_line_placeholders(line))


def plan_placeholder_fill(template: str) -> dict[str, Any]:
    """分析模板结构（通用）：标量占位符顺序 + 表格行模板。

    不做任何业务语义判断（行数/栏目含义等约束由 prompt + 模板正文表达）。
    """
    scalars: list[dict] = []
    row_templates: list[dict[str, Any]] = []
    for line in template.splitlines(keepends=True):
        phs = _line_placeholders(line)
        if not phs:
            continue
        if _is_table_data_row(line):
            row_templates.append(
                {
                    "line": line,
                    "fields": [_parse_field(m.group(1)) for m in phs],
                }
            )
            continue
        for m in phs:
            scalars.append(_parse_field(m.group(1)))
    first = row_templates[0] if row_templates else None
    return {
        "scalars": scalars,
        "row_templates": row_templates,
        "row_line": first["line"] if first else None,
        "row_fields": list(first["fields"]) if first else [],
    }


def normalize_fill_tables(
    tables: list[list[list[str]]],
    row_templates: list[dict[str, Any]],
) -> list[list[list[str]]]:
    """通用清洗：对齐列数、去掉整行空白。不截断行数、不判断栏目语义。"""
    out: list[list[list[str]]] = []
    for i, rt in enumerate(row_templates):
        n_cols = max(len(rt.get("fields") or []), 1)
        raw_rows = tables[i] if i < len(tables) else []
        cleaned: list[list[str]] = []
        for row in raw_rows:
            cells = [("" if c is None else str(c).strip()) for c in row]
            if len(cells) < n_cols:
                cells.extend([""] * (n_cols - len(cells)))
            else:
                cells = cells[:n_cols]
            if not any(cells):
                continue
            cleaned.append(cells)
        out.append(cleaned)
    return out


def _replace_placeholders_in_line(
    line: str,
    values: list[str],
    fields: list[dict] | None = None,
) -> str:
    """按从左到右顺序，把一行内占位符替换为 values。"""
    phs = _line_placeholders(line)
    if not phs:
        return line
    ended = line.endswith("\n")
    body = line[:-1] if ended else line
    # 用 body 重新匹配，保证索引一致
    body_phs = _line_placeholders(body)
    parts: list[str] = []
    cursor = 0
    for i, m in enumerate(body_phs):
        parts.append(body[cursor : m.start()])
        val = values[i] if i < len(values) else ""
        if not val and fields and i < len(fields) and fields[i].get("missing"):
            val = "未提及"
        parts.append(str(val))
        cursor = m.end()
    parts.append(body[cursor:])
    return "".join(parts) + ("\n" if ended else "")


def assemble_placeholder_output(
    template: str,
    field_values: dict[str, str] | list[str],
    table_rows: list[list[str]] | None = None,
    tables: list[list[list[str]]] | None = None,
) -> str:
    """把字段值写回占位符模板（确定性拼装，不调 LLM）。

    Args:
        template: 占位符模板原文。
        field_values: 标量字段，按出现顺序；支持 ``{"1":..,"2":..}`` 或 list。
        table_rows: 兼容参数 = 第 0 张表的多行数据。
        tables: 多张表 ``[table0_rows, table1_rows, ...]``；优先于 table_rows。
    """
    if isinstance(field_values, list):
        scalar_list = [("" if v is None else str(v)) for v in field_values]
    else:
        # 按数字 key 排序；非数字 key 追加在后
        def _key_order(k: str) -> tuple[int, str]:
            return (int(k), k) if str(k).isdigit() else (10**9, str(k))

        scalar_list = [
            ("" if field_values[k] is None else str(field_values[k]))
            for k in sorted(field_values.keys(), key=_key_order)
        ]

    plan = plan_placeholder_fill(template)
    row_templates: list[dict[str, Any]] = plan["row_templates"]
    if tables is None:
        if table_rows is not None:
            tables = [table_rows]
        else:
            tables = []
    # 补齐表数量
    while len(tables) < len(row_templates):
        tables.append([])

    scalar_i = 0
    out_lines: list[str] = []
    # 同一行模板只展开一次（模板里每张表只有一行样例）
    expanded_row_ids: set[int] = set()

    for line in template.splitlines(keepends=True):
        phs = _line_placeholders(line)
        if not phs:
            out_lines.append(line)
            continue

        row_idx = next(
            (
                i
                for i, rt in enumerate(row_templates)
                if rt["line"] == line and i not in expanded_row_ids
            ),
            None,
        )
        if row_idx is not None:
            expanded_row_ids.add(row_idx)
            rt = row_templates[row_idx]
            n_cols = max(len(rt["fields"]), 1)
            use_rows = list(tables[row_idx]) if tables[row_idx] else []
            # 无数据时一行占位，避免多行空白表（通用，无业务语义）
            if not use_rows:
                use_rows = [["未提及"] + ["—"] * (n_cols - 1)]
            for row in use_rows:
                rendered = _replace_placeholders_in_line(
                    line, list(row), rt["fields"]
                )
                # 多行展开时每行必须独立成行；模板末行常无尾换行，
                # 若只在 line.endswith("\n") 时补换行，会把多行糊成一行（|| 粘连）
                if not rendered.endswith("\n"):
                    rendered += "\n"
                out_lines.append(rendered)
            continue

        # 标量行：按全局标量顺序取下一段 values
        n = len(phs)
        chunk = scalar_list[scalar_i : scalar_i + n]
        while len(chunk) < n:
            chunk.append("")
        fields = [_parse_field(m.group(1)) for m in phs]
        out_lines.append(_replace_placeholders_in_line(line, chunk, fields))
        scalar_i += n

    return "".join(out_lines)


_PLACEHOLDER_FILL_SYSTEM = """你是占位符填充器。根据「内容来源」与「模板原文」填写字段值。
只输出一个 JSON 对象，不要 Markdown 代码块，不要解释。

格式：
{
  "fields": {"1": "字段1的值", "2": "字段2的值"},
  "tables": [
    [["表0行1列1", "表0行1列2"], ["表0行2列1", "表0行2列2"]],
    [["表1行1列1", "表1行1列2", "表1行1列3"]]
  ]
}

通用规则（适用于任意模板，不要假设固定栏目名）：
1. fields 的 key 为字符串数字，与标量字段清单编号一致
2. tables[i] 对应第 i 个表格行模板；列顺序与该表字段清单一致
3. **以模板原文为准**：模板里写明的字数、条数/行数、范围、语气等约束必须遵守
   （例如「约200字」「约3行」「不超过5条」→ 控制体量，精选最重要内容，禁止全量堆砌）
4. 每个小节/每张表只填该位置应有的信息；不要把某一节的内容写进另一节/另一张表
5. 有可写内容时不要交空表、不要输出全空单元格行；信息不足写「未提及」或「—」
6. 多选一字段只能取枚举中的一项
7. 值中不要保留方括号占位符
8. 仅一张表时也可用兼容字段 rows（= tables[0]）"""


def build_placeholder_fill_user(
    context: str,
    template: str,
    *,
    revision_notes: str = "",
) -> str:
    """构造字段 JSON 填充的用户消息。"""
    plan = plan_placeholder_fill(template)
    lines = [
        "请根据「内容来源」填充模板，只输出 JSON。",
        "务必通读【模板原文】中的全部说明与约束（字数、行数、栏目分工等），并严格遵守。",
        "",
        "【内容来源】",
        context,
        "",
        "【模板原文】（约束以这里为准）",
        template,
        "",
        "【标量字段清单】（不含表格行内字段）",
    ]
    if not plan["scalars"]:
        lines.append("（无标量字段）")
    for i, seg in enumerate(plan["scalars"], start=1):
        lines.append(f"- {_describe_field(i, seg)}")
    lines.append("")
    lines.append("【表格行模板】→ tables[0], tables[1], ...")
    if plan["row_templates"]:
        for ti, rt in enumerate(plan["row_templates"]):
            lines.append(f"- tables[{ti}] 行样例：{rt['line'].rstrip()}")
            for i, seg in enumerate(rt["fields"], start=1):
                lines.append(f"  - 列{i}（{seg['hint']}）")
        lines.append(
            "各表独立填充；遵守模板原文对体量/条数的要求；节与表之间不要串内容。"
        )
    else:
        lines.append("（无表格行模板，tables 必须为 []）")
    if revision_notes.strip():
        lines.append("")
        lines.append("【上次输出未通过校验，请修正】")
        lines.append(revision_notes.strip())
    return "\n".join(lines)


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    # 截取最外层 {}
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _parse_row_list(rows_raw: object) -> list[list[str]]:
    rows: list[list[str]] = []
    if not isinstance(rows_raw, list):
        return rows
    for row in rows_raw:
        if isinstance(row, list):
            rows.append([("" if c is None else str(c)) for c in row])
        elif isinstance(row, dict):
            keys = sorted(
                row.keys(),
                key=lambda x: int(x) if str(x).isdigit() else 0,
            )
            rows.append(
                [("" if row[k] is None else str(row[k])) for k in keys]
            )
    return rows


def parse_fill_response(
    raw: str,
) -> tuple[dict[str, str], list[list[str]], list[list[list[str]]]]:
    """解析填充 JSON → (fields, rows兼容, tables)。"""
    data = _extract_json_object(raw) or {}
    fields_raw = data.get("fields") or data.get("values") or {}
    fields: dict[str, str] = {}
    if isinstance(fields_raw, dict):
        for k, v in fields_raw.items():
            fields[str(k)] = "" if v is None else str(v)
    elif isinstance(fields_raw, list):
        for i, v in enumerate(fields_raw, start=1):
            fields[str(i)] = "" if v is None else str(v)

    tables: list[list[list[str]]] = []
    tables_raw = data.get("tables")
    if isinstance(tables_raw, list) and tables_raw:
        for t in tables_raw:
            tables.append(_parse_row_list(t))
    rows = _parse_row_list(data.get("rows") or [])
    if not tables and rows:
        tables = [rows]
    return fields, rows, tables


async def _client_text(
    client: Any,
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    temperature: float = 0.0,
) -> str:
    """低温度调用 client.text；兼容无额外参数的 LLMClient。"""
    prev_temp = getattr(client, "temperature", None)
    try:
        if prev_temp is not None:
            client.temperature = temperature
        # 优先走 text；json_mode 时尽量用 _post
        if json_mode and hasattr(client, "_post"):
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            import asyncio

            return (
                await asyncio.to_thread(client._post, messages, json_mode=True)
            ).strip()
        return (await client.text(system, user)).strip()
    finally:
        if prev_temp is not None:
            client.temperature = prev_temp


async def fill_placeholder_template(
    client: Any,
    context: str,
    template: str,
) -> str | None:
    """类型一稳定填充：LLM 只出字段 JSON，程序拼装正文。

    约束（行数/字数/栏目分工等）全部由 prompt + 模板正文表达；
    代码只做通用结构拼装与校验（残留占位符、固定文字、去空行）。
    """
    if not template or not template.strip():
        return None
    if detect_template_kind(template) != "placeholder":
        return None
    plan = plan_placeholder_fill(template)
    if not plan["scalars"] and not plan["row_templates"]:
        return None

    revision = ""
    try:
        for attempt in range(2):
            raw = await _client_text(
                client,
                _PLACEHOLDER_FILL_SYSTEM,
                build_placeholder_fill_user(
                    context, template, revision_notes=revision
                ),
                json_mode=True,
                temperature=0.0,
            )
            fields, rows, tables = parse_fill_response(raw)
            if not tables and rows:
                tables = [rows]
            while len(tables) < len(plan["row_templates"]):
                tables.append([])
            tables = normalize_fill_tables(tables, plan["row_templates"])
            assembled = assemble_placeholder_output(
                template,
                fields,
                tables=tables,
            )
            issues = validate_rendered_output(
                assembled, template, kind="placeholder"
            )
            if not issues:
                return assembled
            revision = "\n".join(f"- {x}" for x in issues)
            logger.info(
                "占位符填充未过结构校验（attempt=%s）：%s",
                attempt + 1,
                "；".join(issues),
            )
            if attempt == 1:
                # 结构类硬伤才丢弃；否则交付第二次结果
                hard = [
                    x
                    for x in issues
                    if "残留占位符" in x or "固定文字丢失" in x or "输出为空" in x
                ]
                if not hard:
                    return assembled
        return None
    except Exception:  # noqa: BLE001
        logger.warning("占位符 JSON 填充失败，回退自由渲染", exc_info=True)
        return None


# ── 类型三：自然语言描述 → 占位符模板编译 ──────────────────────

def extract_description_cues(description: str) -> dict[str, Any]:
    """从自然语言描述抽取意图线索（规则，不调 LLM）。"""
    text = description or ""
    cues: dict[str, Any] = {"flags": set(), "section_count": None}
    for name, pat in _CUE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        if name == "section_count":
            raw = next((g for g in m.groups() if g), None)
            cues["section_count"] = _parse_count_token(raw) if raw else None
        else:
            cues["flags"].add(name)
    # 「只要/仅要/不要」语气
    cues["minimal"] = bool(re.search(r"只要|仅要|只需|不要太多|简洁|简短", text))
    cues["no_extra"] = bool(re.search(r"不要|别加|无需|不用.*表|不要.*表", text))
    return cues


def _parse_count_token(token: str) -> int | None:
    mapping = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if token.isdigit():
        return int(token)
    return mapping.get(token)


def check_compile_fidelity(description: str, compiled: str) -> list[str]:
    """检查编译结果是否忠实于用户描述；返回问题列表（空=通过）。"""
    issues: list[str] = []
    if not compiled or not compiled.strip():
        return ["编译结果为空"]
    if detect_template_kind(compiled) != "placeholder":
        return ["编译结果不是占位符模板"]
    segments = parse_placeholder_template(compiled)
    fields = [s for s in segments if s["kind"] == "field"]
    if not fields:
        issues.append("编译结果未包含可填充占位符")

    cues = extract_description_cues(description)
    flags: set[str] = cues["flags"]
    compiled_l = compiled

    # 用户点名的结构应有对应痕迹（固定字或占位说明）
    flag_needles: dict[str, list[str]] = {
        "time": ["时间", "日期"],
        "people": ["参会", "人员", "人物", "出席"],
        "progress": ["进展", "进度"],
        "problem": ["问题", "风险", "阻塞"],
        "next": ["下一步", "待办", "行动", "后续"],
        "summary": ["总结", "概要", "摘要"],
        "decision": ["决策", "决议"],
        "table": ["|"],
        "json": ["{", "["],
        "title": ["# ", "标题", "主题"],
    }
    for flag, needles in flag_needles.items():
        if flag not in flags:
            continue
        if flag == "json":
            # 自然语言说 JSON 时编译成占位符骨架也可；不强制
            continue
        if not any(n in compiled_l for n in needles):
            issues.append(f"用户提到「{flag}」但模板中未见对应结构")

    # 用户未提及时禁止扩写
    for mention_pat, markers, label in _EXPANSION_GUARDS:
        if mention_pat.search(description or ""):
            continue
        # minimal / 短描述时更严；否则仅拦明显的二级标题扩写
        hit = [m for m in markers if m in compiled_l]
        if not hit:
            continue
        if cues["minimal"] or cues["no_extra"] or len((description or "").strip()) < 80:
            issues.append(f"用户未要求「{label}」，但模板出现了：{hit[0]!r}")
        elif any(m.startswith("##") for m in hit):
            issues.append(f"用户未要求「{label}」，但模板增加了章节：{hit[0]!r}")

    # 部分数量约束
    n = cues.get("section_count")
    if isinstance(n, int) and n > 0:
        h2 = len(re.findall(r"(?m)^##\s+\S", compiled_l))
        # 也统计「1. 2. 3.」类分段
        numbered = len(re.findall(r"(?m)^\s*(?:\d+[\.、]|[一二三四五六七八九十]+[、.])\s+\S", compiled_l))
        sections = max(h2, numbered)
        if sections > n + 1:
            issues.append(
                f"用户要求约 {n} 个部分，但模板出现了 {sections} 个分段/标题"
            )

    # 短描述却编出很长模板 → 过度发挥
    desc_len = len((description or "").strip())
    if desc_len and desc_len < 60 and len(compiled_l) > max(400, desc_len * 12):
        if cues["minimal"] or cues["section_count"]:
            issues.append("编译模板相对描述过长，可能添加了用户未要求的结构")

    return issues


def _build_compile_system(
    *,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
    revision_notes: str = "",
) -> str:
    ctx_lines = []
    if domain or line_name:
        ctx_lines.append(
            f"当前任务上下文：domain={domain or '未知'}，任务线={line_name or '未知'}。"
        )
    if schema_hint.strip():
        ctx_lines.append(f"可用的上游内容字段（占位符说明应对齐这些来源，勿编造其它栏目）：\n{schema_hint.strip()}")
    ctx_block = ("\n".join(ctx_lines) + "\n\n") if ctx_lines else ""

    revision = ""
    if revision_notes.strip():
        revision = (
            "\n\n【上次编译未通过保真检查，请按下列意见修正】\n"
            f"{revision_notes.strip()}\n"
            "务必删除用户未要求的栏目，补全用户点名但缺失的结构。\n"
        )

    return f"""你是模板编译器。用户用自然语言描述想要的输出格式，请把它编译成「给人看、也好改」的占位符模板。
{ctx_block}【读者是最终用户，不是程序员】
模板必须一眼能懂，像一张可编辑的稿纸：
- 用简短中文标题/小标题组织（如 ## 进展），不要写长段系统指令
- 固定文字直接写出来（用户可改）
- 需要系统填的内容用方括号，括号里写短中文说明，读起来像「填空」
  好： [会议主题]  [纪要正文，约200字]  [风险描述]
  差： [根据已审核通过的会议分析结果中的 executive_summary 字段提取……]
- 说明控制在一句话内；默认写法用「未提及」即可
- 表格用简单 Markdown；表头用中文；**每个表只保留 1 行占位行模板**
- 用户说「三行左右/约N行」时：必须在对应小节标题写上（约N行），供后续填充限行
- 用户说「约K字」时：写进对应占位说明（如 [纪要正文，约200字]）
- 不要输出 JSON schema、不要输出「规则/注意/说明」段落、不要代码块包装

「占位符模板」形式示例（仅示范风格，勿照抄栏目）：
# [标题]

## 会议纪要
[纪要正文，约200字]

## 风险识别（约3行）
| 风险描述 | 影响程度 | 应对建议 |
| --- | --- | --- |
| [风险描述] | [高/中/低] | [应对建议] |

## 待办事项（约3行）
| 待办事项 | 负责人 | 截止时间 |
| --- | --- | --- |
| [待办事项] | [负责人] | [截止时间] |

【忠实优先——最重要】
1. 只保留用户明确要求的区块；用户没点名的章节/字段/表格一律不要加
2. 禁止按「标准会议纪要/笔记惯例」自行扩写
3. 描述很短或出现「只要/仅要/简洁」时，输出必须短小
4. 有歧义写在短占位说明里，不要静默发明栏目
5. 用户提到的数量/字数约束必须写进模板固定文字或占位说明
   （后续填充只读模板正文，代码不会单独解析业务规则）
6. 若完全无法理解，只输出：__NEED_CLARIFICATION__

其它：
- 只输出模板正文本身
- 占位说明用白话，不要写系统字段英文名
{revision}"""


def _compile_cache_key(
    text: str,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
) -> str:
    payload = "\n".join(
        [
            _COMPILE_CACHE_VERSION,
            domain or "",
            line_name or "",
            schema_hint or "",
            text,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def clear_compile_caches() -> None:
    """测试/调试用：清空编译缓存与失败计数。"""
    _COMPILE_CACHE.clear()
    _COMPILE_FAIL_COUNTS.clear()


async def maybe_compile_natural_template(
    text: str,
    *,
    domain: str = "",
    line_name: str = "",
    schema_hint: str = "",
) -> str:
    """自然语言描述 → 占位符模板（带保真检查与最多 2 次编译）。

    - 开关关闭或非 natural：原样返回
    - 编译成功且通过保真检查：返回编译结果（按 domain/line 缓存）
    - 失败：返回原文并 warning（调用方按旧路径继续，不阻塞）
    """
    if not is_router_enabled():
        return text
    if not text or not text.strip():
        return text
    if detect_template_kind(text) != "natural":
        return text

    key = _compile_cache_key(text, domain, line_name, schema_hint)
    if key in _COMPILE_CACHE:
        return _COMPILE_CACHE[key]
    if _COMPILE_FAIL_COUNTS.get(key, 0) >= _COMPILE_FAIL_SKIP_THRESHOLD:
        return text

    try:
        from llm_client import LLMClient  # 延迟 import，避免顶层耦合

        client = LLMClient()
        revision = ""
        last_compiled = ""
        for attempt in range(2):
            system = _build_compile_system(
                domain=domain,
                line_name=line_name,
                schema_hint=schema_hint,
                revision_notes=revision,
            )
            compiled = (
                await _client_text(client, system, text, temperature=0.0)
            ).strip()
            last_compiled = compiled
            if not compiled or compiled == "__NEED_CLARIFICATION__":
                revision = "输出无法使用：请生成含 [占位符] 的模板，不要解释。"
                continue
            # 去掉偶尔包裹的代码块
            if compiled.startswith("```"):
                compiled = re.sub(r"^```(?:markdown|md)?\s*", "", compiled)
                compiled = re.sub(r"\s*```$", "", compiled).strip()
            if detect_template_kind(compiled) != "placeholder":
                revision = "结果缺少 [占位符]：请把可变部分写成 [说明] 形式。"
                continue
            fidelity = check_compile_fidelity(text, compiled)
            if fidelity:
                revision = "\n".join(f"- {x}" for x in fidelity)
                logger.info(
                    "自然语言模板保真未通过（attempt=%s）：%s",
                    attempt + 1,
                    "；".join(fidelity),
                )
                continue
            _COMPILE_CACHE[key] = compiled
            _COMPILE_FAIL_COUNTS.pop(key, None)
            return compiled

        # 两次都未完美：若最后一稿至少是 placeholder，降级采用并打 warning
        if last_compiled and detect_template_kind(last_compiled) == "placeholder":
            soft = check_compile_fidelity(text, last_compiled)
            logger.warning(
                "自然语言模板保真未完全通过，仍采用编译结果（issues=%s）",
                "；".join(soft) if soft else "n/a",
            )
            _COMPILE_CACHE[key] = last_compiled
            return last_compiled

        _COMPILE_FAIL_COUNTS[key] = _COMPILE_FAIL_COUNTS.get(key, 0) + 1
        logger.warning("自然语言模板编译未能理解，已按原样处理（原逻辑）")
        return text
    except Exception:  # noqa: BLE001 - 编译失败不阻塞运行
        _COMPILE_FAIL_COUNTS[key] = _COMPILE_FAIL_COUNTS.get(key, 0) + 1
        logger.warning("自然语言模板编译失败，已按原样处理（原逻辑）", exc_info=True)
        return text


# 任务线 → 编译时内容字段提示（非 domain 硬依赖，仅字符串表）
LINE_SCHEMA_HINTS: dict[str, str] = {
    "minutes_generation": (
        "headline, executive_summary, key_decisions, risks_and_blockers, "
        "unresolved_questions, personally_relevant_points"
    ),
    "action_items": (
        "my_actions / unassigned_actions；每项含 task, owner, deadline, priority, status"
    ),
    "risk": "risks 列表（描述、等级、相关方、缓解建议等）",
    "mindmap": "outline（Markdown 大纲）",
    "points": "知识点列表（title, summary, details 等）",
    "knowledge_graph": "nodes / edges / outline",
}


__all__ = [
    "LINE_SCHEMA_HINTS",
    "assemble_placeholder_output",
    "build_placeholder_fill_user",
    "check_compile_fidelity",
    "clear_compile_caches",
    "detect_template_kind",
    "extract_description_cues",
    "fill_placeholder_template",
    "is_router_enabled",
    "maybe_compile_natural_template",
    "normalize_fill_tables",
    "parse_fill_response",
    "parse_placeholder_template",
    "plan_placeholder_fill",
    "route_template",
    "split_spec_template",
    "validate_rendered_output",
]
