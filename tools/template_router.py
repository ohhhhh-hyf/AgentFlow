"""template_router.py —— 模板路由层：自动判型 + 三路分派，无痛插入。

解决"模糊模板 / 自然语言描述模板"输出效果差的问题。三类模板自动分派：

- ``placeholder``（类型一）：含 ``[xxx]`` 占位符 → 程序解析结构，生成
  「固定文字 + 字段清单」的精确填充指令，LLM 只填内容、不猜格式
- ``spec``（类型二）：格式指令 + 示例（输入→输出配对）→ 指令/示例分离，
  示例原样作 few-shot 进用户消息，强化格式学习
- ``natural``（类型三）：用户用自然语言描述想要的样子 → LLM 编译成
  占位符模板（``maybe_compile_natural_template``），再复用类型一路径

设计约束（无痛插入的承诺）：

1. 纯函数为主，**不 import 任何任务线 / domain**；``maybe_compile_natural_template``
   内部延迟 import ``llm_client``，仅当确为 natural 类型时才创建 client
2. ``route_template`` 任何异常 / 解析失败都返回 ``None``，调用方回退旧路径
3. 环境变量 ``TEMPLATE_ROUTER=off`` 一键关闭路由，恢复旧行为
4. 校验函数 ``validate_rendered_output`` 只读无副作用，绝不改写渲染结果
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re

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
# 类型二示例信号
_SPEC_EXAMPLE_MARKERS = ("输入：", "输出：", "```", "示例输入", "示例输出")
# 示例段切分标题（按出现顺序优先）
_SPEC_SPLIT_MARKERS = (
    "# 输出示例",
    "# 示例",
    "## 示例",
    "## 输出示例",
    "输出示例",
    "示例：",
)

# 编译缓存（进程内）：sha256(描述) → 编译后的占位符模板文本
_COMPILE_CACHE: dict[str, str] = {}
# 编译失败黑名单：避免对同一段描述反复尝试
_COMPILE_FAILED: set[str] = set()


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
    if any(kw in text for kw in _SPEC_KEYWORDS) and any(
        marker in text for marker in _SPEC_EXAMPLE_MARKERS
    ):
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
        "输出与模板逐字符对齐」执行。模板结构已由系统解析如下：",
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

    - 类型一 → 结构解析 + 精确填充指令（prompt 复用 template_prompt，
      user 附加结构清单）
    - 类型二 → 指令/示例分离（prompt 复用 template_prompt 并追加类型声明，
      user 分【格式指令】/【示例】两段）
    - 类型三 → 编译由 bootstrap 侧 ``maybe_compile_natural_template`` 先行完成，
      此处一律回退旧路径（``None``），由调用方按旧行为原样拼模板
    - 开关关闭 / 解析异常 / 解析不到结构 → 回退旧路径（``None``）
    """
    if not is_router_enabled():
        return None
    kind = detect_template_kind(template)
    try:
        if kind == "placeholder":
            segments = parse_placeholder_template(template)
            if not any(s["kind"] == "field" for s in segments):
                return None
            return template_prompt, _build_placeholder_user(
                context, template, segments
            )
        if kind == "spec":
            instruction, example = split_spec_template(template)
            if not example:
                return None
            prompt = (
                template_prompt
                + "\n\n（本模板已判定为格式规范模板：示例仅用于演示格式，"
                + "禁止照抄示例输入内容，严格按指令段结构输出。）"
            )
            return prompt, _build_spec_user(
                context, template, instruction, example
            )
    except Exception:  # noqa: BLE001 - 路由失败一律回退旧路径，绝不影响现有逻辑
        logger.warning("模板路由处理异常，已回退旧路径", exc_info=True)
    return None


# ── 渲染输出校验（只读，无副作用）──────────────────────────────

def validate_rendered_output(
    rendered: str,
    template: str,
    kind: str | None = None,
) -> list[str]:
    """校验渲染输出，返回错误列表；空列表 = 通过。

    仅用于提示/排查，**不修改任何输出**：

    - 类型一：残留 ``[占位符]`` 检测 + 较长固定文字抽查
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
        for text in fixed[:3]:
            if text not in rendered:
                errors.append(f"模板固定文字丢失：{text[:30]!r}")
                break
    elif kind == "spec":
        stripped = rendered.strip()
        if ("JSON" in template or "数组" in template) and stripped.startswith("["):
            try:
                json.loads(stripped)
            except Exception as exc:
                errors.append(f"输出不是合法 JSON：{exc}")
    return errors


# ── 类型三：自然语言描述 → 占位符模板编译 ──────────────────────

_COMPILE_PROMPT = """你是模板编译器。用户用自然语言描述想要的输出格式，请把它编译成「占位符模板」。

「占位符模板」的定义：
- 固定文字（标题、表头、段落标签等）原样保留
- 可变内容用 [说明] 占位：说明里写清「内容来源 + 信息不足时的默认写法」
  （如 [根据会议内容提取项目名称；未明确则写"未提及"]）
- 多选一用 [a / b / c] 表示，允许含 emoji（如 [✅已完成 / 🔄进行中 / ⛔阻塞 / 未明确]）
- 表格用 Markdown 表格；含 [xxx] 的表格行 = 行模板（按内容生成对应行数）
- 未明确说明的格式细节，按中文会议纪要的常规惯例合理补全（标题层级、段落、列表、表格）

规则：
1. 只输出编译后的模板本身，不要解释、不要 Markdown 代码块包装
2. 描述有歧义时，在占位符说明里如实标注你的理解（如「标题按会议主题内容理解」），不要悄悄编造缺失信息
3. 若描述完全无法理解成任何输出格式，只输出：__NEED_CLARIFICATION__"""


async def maybe_compile_natural_template(text: str) -> str:
    """自然语言描述 → 占位符模板（进程内缓存，同描述只编译一次）。

    - 开关关闭（``TEMPLATE_ROUTER=off``）或非 natural 类型：原样返回
    - 编译成功（输出为占位符模板）：返回编译结果
    - 编译失败 / 输出澄清标记 / 网络异常：返回原文并记录 warning
      （调用方按旧路径继续，绝不阻塞）
    """
    if not is_router_enabled():
        return text
    if not text or not text.strip():
        return text
    if detect_template_kind(text) != "natural":
        return text
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if key in _COMPILE_CACHE:
        return _COMPILE_CACHE[key]
    if key in _COMPILE_FAILED:
        return text
    try:
        from llm_client import LLMClient  # 延迟 import，避免顶层耦合

        client = LLMClient()
        compiled = (await client.text(_COMPILE_PROMPT, text)).strip()
        if (
            not compiled
            or compiled == "__NEED_CLARIFICATION__"
            or detect_template_kind(compiled) != "placeholder"
        ):
            _COMPILE_FAILED.add(key)
            logger.warning("自然语言模板编译未能理解，已按原样处理（原逻辑）")
            return text
        _COMPILE_CACHE[key] = compiled
        return compiled
    except Exception:  # noqa: BLE001 - 编译失败不阻塞运行
        _COMPILE_FAILED.add(key)
        logger.warning("自然语言模板编译失败，已按原样处理（原逻辑）", exc_info=True)
        return text


__all__ = [
    "detect_template_kind",
    "is_router_enabled",
    "maybe_compile_natural_template",
    "parse_placeholder_template",
    "route_template",
    "split_spec_template",
    "validate_rendered_output",
]
