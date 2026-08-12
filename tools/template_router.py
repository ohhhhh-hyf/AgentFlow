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
_COMPILE_CACHE_VERSION = "v21-strip-outer-fence"


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
    if re.search(r"如[:：]", seg.get("hint") or ""):
        desc += "【注意：hint 中「如：」后仅为写法示例，禁止原样照抄，须按内容来源重写】"
    return desc


def _char_budget_lines(template: str) -> list[str]:
    """字数软提示（仅注入模型，不写入用户可见正文）。用全文预算，忽略字段内「100字以内」。"""
    try:
        from tools.template_eval import parse_document_char_budget
    except Exception:  # noqa: BLE001
        return []
    budget = parse_document_char_budget(template or "")
    if not budget.get("hi"):
        return []
    lo, hi = budget.get("lo"), budget.get("hi")
    lo_i = int(lo or hi)
    hi_i = int(hi)
    # 目标取区间中位，允许在 [lo, hi] 内浮动
    mid = (lo_i + hi_i) // 2  # 例如 200–300 → 250
    n_fields = max(1, len(re.findall(r"\[[^\[\]]+\]", template or "")))
    per = max(22, mid // max(n_fields, 1))
    if hi_i <= 300:
        dens = "各节写满该栏关键事实（可 1～3 句），删套话不删要点"
    elif hi_i <= 450:
        dens = "各节 2～3 句；写清推进与要点"
    else:
        dens = "每节 2～4 句；写清推进与要点，仍勿灌水"
    return [
        f"【全文篇幅·两遍法】约 {lo_i}–{hi_i} 字（汉字合计，目标约 {mid}，必须 ≤{hi_i} 且不宜远低于 {lo_i}）。",
        "先按栏目写全、写通顺的一版，再整体压缩或扩写使合计落入区间；"
        "禁止截断半句、禁止硬砍导致语病。",
        "【严禁写入正文】字段值与正文中不得出现「约N字」「全文合计…字」「字数」等元说明；"
        "字数只用于你内部控制，不要输出。",
        f"约 {n_fields} 栏，平均每栏约 {per} 字。{dens}。句句有据。",
    ]


# 正文中不应出现的字数元说明（整行或行尾）
_CHAR_META_LINE_RE = re.compile(
    r"^\s*(?:>\s*)?(?:全文(?:合计)?|合计|共计)?\s*约?\s*"
    r"\d+\s*(?:[-–—~～至到]\s*\d+\s*)?字\s*[。．.]?\s*$"
)
_CHAR_META_TAIL_RE = re.compile(
    r"(?:\s|[，,；;。．])?(?:全文(?:合计)?|合计|共计)?\s*约\s*"
    r"\d+(?:\s*[-–—~～至到]\s*\d+)?\s*字\s*[。．.]?\s*$"
)


def strip_char_budget_meta(text: str) -> str:
    """从渲染正文中剔除字数元说明（如「约250字」「全文合计约200-300字」）。"""
    if not text:
        return text or ""
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        ended = line.endswith("\n")
        body = line[:-1] if ended else line
        if _CHAR_META_LINE_RE.match(body.strip()):
            continue
        cleaned = _CHAR_META_TAIL_RE.sub("", body).rstrip()
        if cleaned.strip() == "" and body.strip() != "":
            # 整行被剥成空 → 丢弃
            continue
        out.append(cleaned + ("\n" if ended else ""))
    # 去掉文末多余空行
    result = "".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.rstrip() + ("\n" if text.endswith("\n") else "")


def strip_outer_markdown_fence(text: str) -> str:
    """剥掉模型误加的最外层 Markdown 代码围栏（``` / ```text / ```markdown 等）。

    只处理包住**整段**输出的外层 fence；正文内部的代码块示例不碰。
    可重复剥离（最多 3 层）。通用、不绑定业务内容。
    """
    if not text:
        return text or ""
    s = text.strip()
    if not s:
        return ""
    for _ in range(3):
        m = re.match(
            r"^```[a-zA-Z0-9_+-]*[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*$",
            s,
        )
        if m:
            s = m.group(1).strip()
            continue
        # 容错：首行 ```xxx，末行单独 ```
        if s.lstrip().startswith("```"):
            lines = s.splitlines()
            if len(lines) >= 2 and lines[0].lstrip().startswith("```"):
                # 找最后一个仅含 ``` 的行
                end_i = None
                for i in range(len(lines) - 1, 0, -1):
                    if re.fullmatch(r"[ \t]*```[ \t]*", lines[i]):
                        end_i = i
                        break
                if end_i is not None and end_i > 0:
                    s = "\n".join(lines[1:end_i]).strip()
                    continue
        break
    # fence 剥离后残留的语言标签行
    s = re.sub(
        r"^(?:text|markdown|md|plaintext|json)\s*\r?\n",
        "",
        s,
        count=1,
        flags=re.I,
    )
    return s


def _build_placeholder_user(context: str, template: str, segments: list[dict]) -> str:
    lines = [
        "类型：占位符模板。保留固定文字与表结构，只替换 [占位]。",
        "有据才写；无依据「未提及」；禁止照抄「如：」示范；禁止编造原文没有的环节/数字/履历。",
        "谁做了什么、数值日期以原文为准；预计/可能不要写成已定事实。",
        "模板点名的栏目都要覆盖：从原文提炼与该栏主题相关的信息，勿因「无同名小标题」就空写。",
        "顿号或「与/和/及」连接的主题分别写清；流程只按原文真实顺序。",
        "语句完整通顺，无缺字、无半截句。",
        *_char_budget_lines(template),
        "模板结构解析：",
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
        fixed = []
        for s in segments:
            if s["kind"] != "text":
                continue
            raw = s["text"].strip()
            if len(raw) < 4:
                continue
            # 空表行/仅竖线空白（如「| | | | | |」）不算必须保留的固定文案
            if not re.sub(r"[\s|:\-]+", "", raw):
                continue
            fixed.append(raw)
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

## 输出约定
1. fields 的 key 为字符串数字，与标量字段清单编号一致
2. tables[i] 对应第 i 个表格行模板；只输出数据行单元格，不要表头
3. 多选一只能取枚举中的一项；值中不要残留 [占位符]
4. 仅一张表时也可用 rows（= tables[0]）
5. **字段值只写该栏正文内容**，不要写 Markdown 标题（# / ##），不要重复栏目标题作前缀
6. **严禁**在任何字段值中写「约N字」「全文合计…字」「字数」等元说明
7. **严禁**用 ``` / ```text 等代码围栏包裹字段值或整段输出

## 结构（标题由模板固定文字负责）
- 模板里的 `## 栏目标题` 是固定文字，程序会原样保留；你只填方括号对应的正文
- 不要把某一栏的正文填进「文档总标题」占位里冒充栏目；有独立栏目就填到对应编号字段

## 语句通顺
- 每个字段值须是完整通顺的中文（或指令要求的短语），主谓齐全，无缺字漏字、无重复赘字、无半截句
- 禁止把多个字段内容机械粘成病句；并列信息用顿号/逗号理顺

## 篇幅与信息量（两遍法）
- 仅模板总述/固定文字中的「约 x / a-b 字」约束全文；占位内「100字以内」只限该栏
- 先按各栏主题写全实质内容，再对照全文区间整体调节
- 模板写「简洁 / 粗略 / 概要 / 无需深入」时：省略展开论证与次要枝节，但**每栏仍须写清原文中与该栏相关的主要事实与要点**（可多句），禁止每栏只剩一句空泛套话而丢掉可写的关键信息
- 全部字段汉字合计必须落在声明区间内，目标靠近区间中位；禁止截断半句

## 忠实
- 句句有据；禁止照抄「如：」示范；禁止用外部常识/百科补履历、成果或评价
- 身份/称谓栏只写原文出现的名字与角色
- 归属/数字/日期忠实原文；预计/可能/有望保持原语气，勿改成已发生

## 覆盖（栏目主题）
- 每个占位/每栏都填：按栏目标题与占位说明的主题，从内容来源提炼对应信息
- 仅当来源对该栏主题完全无信息时，才按默认写法（如「未提及」）
- 栏目标题或占位说明中用「与/和/及」并列的两侧主题，字段正文内须分别写清，勿混成一锅
- 压缩时优先保留关键结论、数字、责任人与时限；不另开无关栏

## 表格
- 列对齐；一行一条数据；人名/公司名等用内容来源原文，禁止沿用「如：」示范名
- 数字若原文是预计/有望/可能，单元格内保留该语气
- 无则按默认写法（如「未提及」）
"""


def build_placeholder_fill_user(
    context: str,
    template: str,
    *,
    revision_notes: str = "",
) -> str:
    """构造字段 JSON 填充的用户消息。"""
    plan = plan_placeholder_fill(template)
    lines = [
        "根据内容来源填充模板，只输出 JSON。",
        "固定标题/表头由模板保留，你只填 [占位] 正文；字段值里不要写 #/## 标题，不要重复栏目标题前缀。",
        "有据才写；某栏主题在来源中完全无信息时才「未提及」。",
        "勿照抄「如：」示例；勿张冠李戴；勿改数字；勿用百科补履历；勿虚构原文没有的内容。",
        "各栏按主题分别写清；「与/和/及」并列主题勿揉成一句糊涂话。",
        "简洁/粗略≠空洞：每栏写清该栏主要事实与要点，可多句。",
        *_char_budget_lines(template),
        "语句完整通顺，无半截句；严禁输出「约N字」等字数元说明。",
        "",
        "【内容来源】",
        context,
        "",
        "【模板原文】",
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
    use_cache: bool = False,
) -> str:
    """统一走 client.text 的 per-call 参数（温度/JSON/缓存）。"""
    try:
        return (
            await client.text(
                system,
                user,
                temperature=temperature,
                json_mode=json_mode,
                use_cache=use_cache,
            )
        ).strip()
    except TypeError:
        # 兼容旧版 text() 无关键字参数
        prev_temp = getattr(client, "temperature", None)
        try:
            if prev_temp is not None:
                client.temperature = temperature
            if json_mode and hasattr(client, "_post"):
                import asyncio

                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                return (
                    await asyncio.to_thread(
                        client._post, messages, json_mode=True
                    )
                ).strip()
            return (await client.text(system, user)).strip()
        finally:
            if prev_temp is not None:
                client.temperature = prev_temp


def _body_han_count(text: str) -> int:
    """正文汉字数（去掉 Markdown 标题行），供填充篇幅自检。"""
    lines: list[str] = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*#{1,6}\s+", line):
            continue
        if (line or "").strip().startswith("<!--"):
            continue
        lines.append(line)
    return len(re.findall(r"[\u4e00-\u9fff]", "\n".join(lines)))


async def fill_placeholder_template(
    client: Any,
    context: str,
    template: str,
) -> str | None:
    """类型一稳定填充：LLM 只出字段 JSON，程序拼装正文。

    约束（行数/字数/栏目分工等）全部由 prompt + 模板正文表达；
    代码只做通用结构拼装与校验（残留占位符、固定文字、去空行）。
    若模板有字数提示且明显偏短，会再给一轮「扩写」修订（不写进用户正文）。
    """
    if not template or not template.strip():
        return None
    if detect_template_kind(template) != "placeholder":
        return None
    plan = plan_placeholder_fill(template)
    if not plan["scalars"] and not plan["row_templates"]:
        return None

    try:
        from tools.template_eval import parse_document_char_budget
    except Exception:  # noqa: BLE001
        parse_document_char_budget = None  # type: ignore[assignment]
    budget = (
        parse_document_char_budget(template) if parse_document_char_budget else {}
    )

    revision = ""
    try:
        for attempt in range(3):
            raw = await _client_text(
                client,
                _PLACEHOLDER_FILL_SYSTEM,
                build_placeholder_fill_user(
                    context, template, revision_notes=revision
                ),
                json_mode=True,
                temperature=0.0 if attempt == 0 else 0.2,
            )
            fields, rows, tables = parse_fill_response(raw)
            if not tables and rows:
                tables = [rows]
            while len(tables) < len(plan["row_templates"]):
                tables.append([])
            tables = normalize_fill_tables(tables, plan["row_templates"])
            # 字段值内若误写字数元说明 / 代码围栏，先剥掉再拼装
            fields = {
                k: strip_char_budget_meta(strip_outer_markdown_fence(v)).strip()
                if isinstance(v, str)
                else v
                for k, v in fields.items()
            }
            assembled = assemble_placeholder_output(
                template,
                fields,
                tables=tables,
            )
            assembled = strip_outer_markdown_fence(assembled)
            assembled = strip_char_budget_meta(assembled)
            # 篇幅自检：偏短扩写、偏长压缩（不改结构、不写进用户正文）
            lo = budget.get("lo") if isinstance(budget, dict) else None
            hi = budget.get("hi") if isinstance(budget, dict) else None
            if (lo or hi) and attempt < 2:
                han = _body_han_count(assembled)
                lo_i = int(lo or 0)
                hi_i = int(hi or 0)
                if lo_i and han < int(lo_i * 0.85):
                    revision = (
                        f"当前各字段合计约 {han} 字，少于模板约 {lo_i}–{hi_i or lo_i} 字。"
                        "请在保持结构与忠实原文的前提下整体扩写："
                        "为各节补充原文已有的具体事实、推进与结论，语句通顺完整，"
                        "使合计接近区间中位；勿空话注水、勿截断半句、勿写字数说明。"
                    )
                    logger.info(
                        "占位符填充偏短（%s<%s），attempt=%s 请求扩写",
                        han,
                        lo_i,
                        attempt + 1,
                    )
                    continue
                if hi_i and han > hi_i:
                    target = (lo_i + hi_i) // 2 if lo_i else max(hi_i - 40, hi_i * 4 // 5)
                    revision = (
                        f"当前各字段合计约 {han} 字，超过模板上界 {hi_i} 字。"
                        f"请整体压缩改写到约 {target}–{hi_i} 字（不是截断半句）："
                        "每节改短句、删套话与次要枝节，保留关键结论、数字与归属；"
                        "压缩后语句仍须完整通顺；勿改结构、勿虚构。"
                    )
                    logger.info(
                        "占位符填充偏长（%s>%s），attempt=%s 请求压缩",
                        han,
                        hi_i,
                        attempt + 1,
                    )
                    continue
            # 强执行：截断/去粘连/空表占位后再验收
            from tools.hard_execution import gate_render_output

            gate = gate_render_output(template, assembled)
            assembled = gate["text"]
            issues = list(gate.get("issues") or [])
            if gate.get("gate_ok"):
                return assembled
            revision = "\n".join(f"- {x}" for x in issues)
            logger.info(
                "占位符填充未过门禁（attempt=%s）：%s",
                attempt + 1,
                "；".join(issues),
            )
            if attempt >= 1:
                # 多轮后仍无硬伤则接受当前拼装，交给上层 freeform/repair 的情况仅在硬伤时
                hard = list(gate.get("hard_issues") or [])
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


def _split_aspect_connectors(phrase: str) -> list[str]:
    """把「A与B」「A和B」「A及B」拆成并列要点（两侧都像短主题名时才拆）。

    例：要点概述与补充说明 → [要点概述, 补充说明]
    不拆：与会者、和平、以及（整词）、过长从句
    """
    phrase = (phrase or "").strip()
    if not phrase or not re.search(r"[与和及]", phrase):
        return [phrase] if phrase else []
    # 避免拆开「与会」「以及」等
    if "与会" in phrase or phrase.startswith("以及"):
        return [phrase]
    # 仅当连接词两侧都是短名词短语时拆分
    parts = re.split(r"[与和及]", phrase)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return [phrase]
    if all(
        2 <= len(p) <= 12 and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", p)
        for p in parts
    ):
        return parts
    return [phrase]


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


def _strip_heading_number(title: str) -> str:
    """去掉「一、」「1.」「## 」等编号前缀，便于比对栏目名。"""
    t = (title or "").strip()
    t = re.sub(r"^#{1,6}\s*", "", t)
    t = re.sub(r"^[0-9一二三四五六七八九十两]+[、.．\s]+", "", t)
    return t.strip()


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
    for m in _PLACEHOLDER_RE.finditer(compiled or ""):
        hint = m.group(1)
        if aspect not in hint:
            continue
        others = [a for a in all_aspects if a != aspect and a in hint]
        if others and re.search(r"[与和及、]", hint):
            continue
        return True
    return False


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

    # 用户用顿号/与/和/及并列的多个要点 → 必须各有独立**固定标题**小节 + 占位
    aspects = extract_listed_aspects(description)
    if len(aspects) >= 2:
        missing_heading = [
            a
            for a in aspects
            if not _aspect_has_fixed_heading(a, compiled_l, aspects)
        ]
        if missing_heading:
            issues.append(
                "用户并列要求的要点缺少固定小节标题（栏目名须写成 ## 固定文字，"
                "内容放在标题下的占位里，禁止用「# [整段内容]」吞掉栏目名）："
                + "、".join(missing_heading[:6])
            )
        missing_own = [
            a for a in aspects if not _aspect_has_own_slot(a, compiled_l, aspects)
        ]
        if missing_own and not missing_heading:
            issues.append(
                "用户并列要求的要点未各自拆成独立小节/占位："
                + "、".join(missing_own[:6])
                + "（禁止合并成「A与B」一个标题）"
            )
        # 只有 1 个占位却要求多个方面 → 覆盖不足
        if len(fields) < min(len(aspects), 3) and len(aspects) >= 3:
            issues.append(
                f"用户列了 {len(aspects)} 个要点，但模板仅 {len(fields)} 个占位，"
                "请按要点拆成多个小节"
            )
        # 仍存在「A与B」合并标题，且 A、B 都是用户并列要点 → 明确报错
        for m in re.finditer(r"(?m)^#{1,3}\s+(.+)$", compiled_l):
            clean = _strip_heading_number(m.group(1))
            if not re.search(r"[与和及]", clean):
                continue
            hit = [a for a in aspects if a in clean]
            if len(hit) >= 2:
                issues.append(
                    f"标题 {m.group(1).strip()!r} 把并列要点合并了，"
                    "请拆成各自独立的 ## 小节"
                )
                break
        # 字数约束不得出现在固定文字行
        outer = re.sub(r"\[[^\[\]]*\]", " ", compiled_l)
        if re.search(r"(?:约\s*)?\d+\s*[-–—~～]?\s*\d*\s*字", outer):
            issues.append(
                "字数约束写进了固定文字，会泄漏到正文；请只写在占位说明内"
            )

    # 「不遗漏关键…」是质量要求，不应单独开栏导致超字数
    if re.search(r"不遗漏关键|勿漏关键|不要遗漏关键", description or ""):
        if re.search(r"(?m)^##\s*关键", compiled_l):
            issues.append(
                "「不遗漏关键要点」无需单独开「## 关键…」节，请并入流程/脉络并控制总字数"
            )

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
        ctx_lines.append(
            f"可用的上游内容字段（占位说明对齐这些来源，勿编造其它栏目）：\n{schema_hint.strip()}"
        )
    ctx_block = ("\n".join(ctx_lines) + "\n\n") if ctx_lines else ""

    revision = ""
    if revision_notes.strip():
        revision = (
            "\n\n【上次编译未通过保真检查，请修正】\n"
            f"{revision_notes.strip()}\n"
            "删除用户未要求的栏目；补全用户点名结构；控制总字数提示。\n"
        )

    return f"""你是模板编译器：把中文用户用自然语言描述的"输出格式要求"，精确编译成一个可编辑的占位符模板。
{ctx_block}

## 第一步：先解析用户意图（在脑中完成，不要输出）
动手编译前，把描述拆成四层，缺的层按中文表达习惯补全：
1. **结构**：用户要哪几个部分（标题 / 元信息行 / 段落 / 列表 / 表格），先后顺序
2. **位置与固定文字**：哪些文字原样保留（标题、括号、标签、分隔符），哪些位置是可变占位
3. **体裁参照**：用户说"类似 / 像 …一样"时，该体裁的常规形态是什么
4. **约束与偏好**：数量、字数、行数、风格（正式/简洁/突出重点）、排除项（"不要…"）

## 中文表达习惯（帮助理解省略与隐含结构）
- **句间承接**：中文口语常省略主语，一句接一句的隐含顺序 = 表述顺序
- **"XX 一行"** → 该部分占一行
- **"括号里写 XX"** → 括号是固定文字，括号内是占位
- **"然后 / 接着 / 最后"** → 结构顺序
- **"类似 / 像 …一样"** → 体裁参照，不新增用户没点的栏目
- **"不要 / 别加 / 不用 …"** → 明确排除
- **数量词**："几行 / 约 N 字 / 三条" → 约束，只进占位说明

## 忠实于用户描述（最重要）
1. 只保留用户点名的结构，不增不减；顺序与用户表述一致
2. **栏目名 = 固定标题（强制）**：用户点名的每个写作栏目（如用顿号/与/和/及列出的
   「背景、对象、目的…」）必须写成：
   ```text
   ## 栏目名
   [该栏正文占位说明…]
   ```
   - `## 栏目名` 是**固定文字**（用户打开文档能看见的标题），禁止省略
   - 正文只写在标题下方的 `[占位]` 里
   - **禁止**把栏目正文写进一级标题占位：`# [一大段背景…]`（这会导致「没有标题、只有内容」）
   - **禁止**合并：`## A与B` + 一个占位；必须 `## A` / `## B` 各一节
3. 用户说"类似 XX" → 对齐该体裁常规形态，仍以用户点名部分为准
4. 数量 / 字数 / 行数约束：
   - "约 200 字" / "200-300 字" → **只**写进某个占位的说明文字内
     （如 `[…；全文合计约200-300字]`），**绝对禁止**写成单独一行固定文字或引用块
     （否则会出现在用户正文里，如「约250字」）
   - "三行" / "三条" → 对应数量占位或在说明里注明
   - "简洁 / 粗略" → 写进占位说明（省略次要枝节，但仍须覆盖该栏主要事实），不删栏目

## 占位符写法
- [短中文说明]：填什么 + 从原文哪类信息提炼 + 信息不足怎么办
- 禁止在占位里写具体答案示范（如「如：张三」）
- 默认空值：用户指定则用用户的，否则「未提及」
- 不要单独增加一个「字数说明」占位或固定行

## 描述模糊时的处理
- 有歧义时按最自然的理解补全，并在占位说明标注「按理解」
- 拿不准时宁可少加结构，不要擅自补栏目
- 完全无法理解 → 只输出 __NEED_CLARIFICATION__

## 示例（仅演示写法，不是目标结构）
用户："约200字，概括主题甲、主题乙，并梳理推进过程与主线结论"
正确编译：
```text
## 主题甲
[从原文提炼与本栏相关的信息，通顺完整句；无则写「未提及」]

## 主题乙
[从原文提炼与本栏相关的信息；无则写「未提及」]

## 推进过程
[按原文真实顺序梳理；全文合计约200字]

## 主线结论
[概括主线观点；无则写「未提及」]
```
错误编译（禁止）：
```text
# [把主题甲的内容直接当一级标题]
## 主题乙
…
约200字
```

只输出编译后的模板正文，不要解释；**禁止**用 Markdown 代码围栏（``` 或 ```text）包裹整段输出。
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


def _ensure_document_char_budget_line(source: str, compiled: str) -> str:
    """若自然语言源有全文字数而编译结果丢失，把全文预算写入首个占位说明。

    不写进固定文字行，避免 assemble 后用户正文出现「全文约××字」。
    """
    try:
        from tools.template_eval import parse_document_char_budget
    except Exception:  # noqa: BLE001
        return compiled
    src_b = parse_document_char_budget(source or "")
    if not src_b.get("hi"):
        return compiled
    dst_b = parse_document_char_budget(compiled or "")
    if dst_b.get("hi"):
        return compiled
    lo, hi = src_b.get("lo"), src_b.get("hi")
    if lo and hi:
        hint = f"全文合计约{int(lo)}-{int(hi)}字"
    else:
        hint = f"全文合计约{int(hi)}字"
    body = compiled or ""
    if hint in body or re.search(r"全文(?:合计)?约?\s*\d+", body):
        return compiled
    # 注入第一个 [占位]
    m = re.search(r"\[[^\[\]]+\]", body)
    if not m:
        return compiled
    inner = m.group(0)[1:-1].strip()
    if "全文" in inner:
        return compiled
    new_ph = f"[{inner}；{hint}]"
    return body[: m.start()] + new_ph + body[m.end() :]


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
                await _client_text(
                    client,
                    system,
                    text,
                    temperature=0.0,
                    use_cache=(attempt == 0 and not revision),
                )
            ).strip()
            last_compiled = compiled
            if not compiled or compiled == "__NEED_CLARIFICATION__":
                revision = "输出无法使用：请生成含 [占位符] 的模板，不要解释。"
                continue
            # 去掉模型误包的代码围栏（```text / ```markdown 等）
            compiled = strip_outer_markdown_fence(compiled)
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
            compiled = _ensure_document_char_budget_line(text, compiled)
            _COMPILE_CACHE[key] = compiled
            _COMPILE_FAIL_COUNTS.pop(key, None)
            return compiled

        # 两次都未完美：若最后一稿至少是 placeholder，降级采用并打 warning
        if last_compiled and detect_template_kind(last_compiled) == "placeholder":
            soft = check_compile_fidelity(text, last_compiled)
            last_compiled = _ensure_document_char_budget_line(text, last_compiled)
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
    "mindmap": "outline（Markdown 树状大纲：#/##/### 与 - 短分支；禁止表格）",
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
    "extract_listed_aspects",
    "fill_placeholder_template",
    "is_router_enabled",
    "maybe_compile_natural_template",
    "normalize_fill_tables",
    "parse_fill_response",
    "parse_placeholder_template",
    "plan_placeholder_fill",
    "route_template",
    "split_spec_template",
    "strip_char_budget_meta",
    "strip_outer_markdown_fence",
    "validate_rendered_output",
]
