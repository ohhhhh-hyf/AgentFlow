"""tools.template_router.base —— 模板路由·基础层：常量与无依赖工具（判型/解析/计数/文本工具）。"""
from __future__ import annotations

from __future__ import annotations
import hashlib
import json
import logging
import os
import re
from typing import Any
from tools.template_prompt import PLACEHOLDER_RULES, SPEC_RULES


logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


_PLACEHOLDER_RE = re.compile(r"\[([^\[\]]+)\]")


_ENUM_SEP_RE = re.compile(r"\s*/\s*")


_MISSING_HINT_RE = re.compile(r"未明确|未提及|无$")


_CN_RE = re.compile(r"[\u4e00-\u9fff]")


_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")


_HINT_WORD_RE = re.compile(r"根据|未明确|未提及|列出|原文|填写|说明|名称|内容|主题")


_SPEC_KEYWORDS = ("JSON", "数组", "示例", "格式规范", "严格输出", "输出格式")


_SPEC_EXAMPLE_MARKERS = ("输入：", "输出：", "```", "示例输入", "示例输出", "输出示例")


_SPEC_SPLIT_MARKERS = (
    "# 输出示例",
    "# 示例",
    "## 示例",
    "## 输出示例",
    "输出示例",
    "示例：",
)


_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


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


_COMPILE_CACHE: dict[str, str] = {}


_COMPILE_FAIL_COUNTS: dict[str, int] = {}


_COMPILE_FAIL_SKIP_THRESHOLD = 3


_COMPILE_CACHE_VERSION = "v24-char-scope-readable"


_CN_NUM = {
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


def is_router_enabled() -> bool:
    """路由开关：``TEMPLATE_ROUTER=off``（或 0/false/no）关闭，默认开启。"""
    value = os.getenv("TEMPLATE_ROUTER", "on").strip().lower()
    return value not in ("0", "false", "off", "no")


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


def _table_row_confidence_score(row: list[str]) -> tuple[int, int]:
    """按明确性/信息量粗排表格行，超出用户行数时保留更可信的行。"""
    text = " ".join(str(c or "").strip() for c in row)
    empty_markers = {"", "未提及", "未明确", "无", "暂无", "—", "-", "N/A", "n/a"}
    cells = [str(c or "").strip() for c in row]
    meaningful = [c for c in cells if c not in empty_markers]
    score = 0
    score += len(meaningful) * 10
    score += min(len(re.findall(r"[\u4e00-\u9fff]", text)), 80)
    score += 12 if re.search(r"\d|月|日|周|前|后|截止|完成|负责人|负责", text) else 0
    score += 10 if re.search(r"张|王|李|赵|钱|孙|周|吴|郑|陈|林|刘|黄|负责人|团队|部门", text) else 0
    score += 8 if re.search(r"风险|阻塞|延期|超时|缺口|问题|影响|应对|缓解", text) else 0
    score -= 30 * sum(1 for c in cells if c in empty_markers)
    score -= 20 if re.search(r"待确认|不确定|可能|大概|似乎", text) else 0
    return score, len(text)


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
    """字数软提示（仅注入模型）。全文预算约束整篇；本段/本栏预算只约束对应节。"""
    try:
        from tools.template_eval import (
            parse_document_char_budget,
            parse_section_char_budgets,
            parse_table_row_hints,
        )
    except Exception:  # noqa: BLE001
        return []
    lines: list[str] = []
    budget = parse_document_char_budget(template or "")
    sections = parse_section_char_budgets(template or "")
    tables = parse_table_row_hints(template or "")
    if budget.get("hi"):
        lo, hi = budget.get("lo"), budget.get("hi")
        lo_i = int(lo or hi)
        hi_i = int(hi)
        mid = (lo_i + hi_i) // 2
        lines.extend(
            [
                f"【全文篇幅】汉字合计约 {lo_i}–{hi_i} 字（目标约 {mid}，必须 ≤{hi_i}）。",
                "这是整篇上限，不是某一节的上限。先按栏目写全，再整体压缩或扩写使合计落入区间。",
            ]
        )
    if sections:
        bits = [
            f"「{item['title']}」本段约 {item['hi']} 字"
            for item in sections
        ]
        lines.append("【段落篇幅】" + "；".join(bits) + "。只约束该节，不要用它去压其它节或表格。")
    if tables:
        bits = [f"「{item['title']}」约 {item['rows']} 行" for item in tables]
        lines.append("【表格行数】" + "；".join(bits) + "。")
    if not lines:
        return []
    lines.append(
        "【严禁写入正文】不得出现「约N字」「全文合计…字」「字数」等元说明。"
    )
    return lines


_CHAR_META_LINE_RE = re.compile(
    r"^\s*(?:>\s*)?(?:全文(?:合计)?|合计|共计)?\s*约?\s*"
    r"\d+\s*(?:[-–—~～至到]\s*\d+\s*)?字\s*[。．.]?\s*$"
)


_CHAR_META_TAIL_RE = re.compile(
    r"(?:\s|[，,；;。．])?(?:全文(?:合计)?|合计|共计)?\s*约\s*"
    r"\d+(?:\s*[-–—~～至到]\s*\d+)?\s*字\s*[。．.]?\s*$"
)


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


def _hint_clean(hint: str) -> str:
    """占位说明 → 用户可读的灰字提示（去技术化：去「从原文提炼」等长前缀）。

    例：'从原文提炼会议核心讨论与结论，通顺完整句；本段约200字；无则写「未提及」'
      → '会议核心讨论与结论（约200字；无则写「未提及」）'
    """
    text = " ".join((hint or "").split()).strip()
    for prefix in ("从原文提炼", "根据原文", "从内容来源提炼", "按原文", "从会议原文提炼"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip("，,；;：:")
            break
    # 去掉「通顺完整句」「主谓齐全」等工程化约束
    text = re.sub(r"[，,；;]\s*(?:通顺完整句|主谓齐全|无缺字漏字|可多句|语句通顺)", "", text)
    return text.strip() or "待填写"


def _hint_short(hint: str) -> str:
    """占位说明 → 表头短词（取首个顿号/逗号/空格前的短词，≤6 字）。

    例：'任务内容' → '任务'；'负责人姓名' → '负责人'；'截止时间' → '截止时间'
    """
    text = _hint_clean(hint)
    head = re.split(r"[，,；;、\s（(]", text, maxsplit=1)[0].strip()
    head = re.sub(r"^(?:该|本|此)[栏项条]", "", head).strip()
    if head and len(head) <= 8:
        return head
    # 过长则截断
    return text[:8] if text else "待填写"


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
- 仅「全文合计约 x 字」或模板总述中的全文预算约束**整篇**；占位内「本段约N字 / 100字以内」**只限该栏**
- 先按各栏主题写全实质内容，再对照各自约束调节；不要用某一段的字数去压缩其它段或表格
- 当内容多于用户要求：先保留结论、数字、负责人、期限、明确风险/行动等高价值信息，删去寒暄、重复、背景铺垫、低确定性猜测和不影响结论的枝节；压缩后仍要语句完整。
- 当内容少于用户要求：可以把原文中已出现的相关事实稍作展开、合并上下文说清楚，但**绝对不能编造**原文没有的事实、数字、责任人、期限或评价。
- 模板写「简洁 / 粗略 / 概要 / 无需深入」时：省略展开论证与次要枝节，但**每栏仍须写清原文中与该栏相关的主要事实与要点**（可多句），禁止每栏只剩一句空泛套话而丢掉可写的关键信息
- 若存在全文预算：全部字段汉字合计落在区间内；若仅有段落预算：只约束对应字段

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
- 若模板写了「约N行 / N条左右」，最多输出 N 行。候选项多于 N 行时，按置信度和重要性选择：
  1) 原文明确点名的人/团队/事项/风险优先；
  2) 有数字、日期、负责人、截止时间、影响、应对措施的优先；
  3) 与栏目标题高度相关、可直接执行或直接影响结论的优先；
  4) 信息缺失多、只是泛泛表态、重复或低确定性的候选项后置或删除。
- 候选项少于 N 行时，不要为了凑行数编造；只输出有依据的行，必要时一行写「未提及」。
"""


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


async def _client_text(
    client: Any,
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    temperature: float = 0.0,
    use_cache: bool = False,
    label: str = "",
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
                label=label,
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


def _strip_heading_number(title: str) -> str:
    """去掉「一、」「1.」「## 」等编号前缀，便于比对栏目名。"""
    t = (title or "").strip()
    t = re.sub(r"^#{1,6}\s*", "", t)
    t = re.sub(r"^[0-9一二三四五六七八九十两]+[、.．\s]+", "", t)
    return t.strip()


def clear_compile_caches() -> None:
    """测试/调试用：清空编译缓存与失败计数。"""
    _COMPILE_CACHE.clear()
    _COMPILE_FAIL_COUNTS.clear()


def _table_topic_from_context(lines: list[str], idx: int) -> str:
    """根据表格附近标题/表头猜测主题。"""
    nearby: list[str] = []
    for j in range(max(0, idx - 4), min(len(lines), idx + 1)):
        nearby.append(lines[j])
    text = "\n".join(nearby)
    if re.search(r"风险|阻塞|问题", text):
        return "risk"
    if re.search(r"待办|行动|任务|负责人|截止|下一步|后续", text):
        return "action"
    return "any"


_MODIFY_SYSTEM = """你是模板修改器：基于用户**当前模板**与**修改意见**，输出更新后的占位符模板。

## 规则

1. **只改用户点名的地方**：修改意见没提到的段落、表格、标题，一律原样保留（结构、占位说明、字数约束都不动）。
2. 修改意见提到加/删/改段落、表格列、字数、标题时，按意见调整；没提到的不要自作主张新增栏目。
3. 沿用占位符写法（`[短说明]`），占位说明保持简短口语（如「会议纪要，约200字」），不要写长技术句。
4. **不额外加栏目包装标题**：段落/表格直接给内容与占位，不要为「纪要」「风险表」这类内容段
   自作主张加 `## 纪要` / `## 风险识别` 标题；仅当修改意见明确要求独立栏目标题时才加。
5. 字数约束作用域：段落级写「本段约N字」，全文级才写「全文合计约N字」；字数只写进占位说明，不写固定文字行。
6. 表格：保留表头/分隔行/数据行模板；加列就在表头与数据行都加。
7. 只输出更新后的模板正文，不要解释，不要 Markdown 代码围栏。

【当前模板】
{template}

【修改意见】
{instruction}
"""


_BANNER_RE = re.compile(r"^【版式】.+$", re.M)


_SLOT_LINE_RE = re.compile(
    r"^（(?:生成时填写|本段约\d+.*?生成时填写|约\d+行.*?生成时填写|"
    r"会议标题，生成时填写|标题，生成时填写)）$"
)


_OLD_FILL_RE = re.compile(r"【(?:填这里：)?([^】]+)】")


def _format_budget_banner(template: str) -> str:
    """把全文/本段/表格行数约定写成用户能看懂的一行说明。"""
    try:
        from tools.template_eval import (
            parse_document_char_budget,
            parse_section_char_budgets,
            parse_table_row_hints,
        )
    except Exception:  # noqa: BLE001
        return "【版式】按下方标题和表格生成。空着的位置会按会议自动填写。"
    parts: list[str] = []
    full = parse_document_char_budget(template or "")
    if full.get("hi"):
        lo, hi = full.get("lo"), int(full["hi"])
        if lo and int(lo) != hi:
            parts.append(f"全文约{int(lo)}-{hi}字")
        else:
            parts.append(f"全文约{hi}字")
    else:
        parts.append("全文不限")
    for item in parse_section_char_budgets(template or ""):
        parts.append(f"{item['title']}：本段约{item['hi']}字")
    for item in parse_table_row_hints(template or ""):
        parts.append(f"{item['title']}：约{item['rows']}行")
    return "【版式】" + "。".join(parts) + "。空着的位置会按会议自动填写。"


def _field_slot_line(hint: str) -> str:
    text = " ".join((hint or "").split()).strip()
    section = re.search(r"本段约\s*(\d+(?:\s*[-–—~～至到]\s*\d+)?)\s*字", text)
    if section:
        return f"（本段约{section.group(1).replace('至', '-').replace('到', '-')}字，生成时填写）"
    full = re.search(r"全文(?:合计)?约\s*(\d+(?:\s*[-–—~～至到]\s*\d+)?)\s*字", text)
    if full:
        return f"（全文约{full.group(1).replace('至', '-').replace('到', '-')}字，生成时填写）"
    return "（生成时填写）"


def _is_slot_body(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return True
    if _SLOT_LINE_RE.match(body):
        return True
    if body in {"（生成时填写）", "生成时填写", "待填写", "＿＿＿＿", "____"}:
        return True
    if _OLD_FILL_RE.fullmatch(body):
        return True
    return False


def _split_by_heading(text: str) -> list[tuple[str, str, str]]:
    """[(标题行含# 或空, 标题文字, 节正文不含标题)]。"""
    lines = (text or "").splitlines()
    blocks: list[tuple[str, str, list[str]]] = [("", "", [])]
    for line in lines:
        head = re.match(r"^(#{1,6}\s+)(.+)$", line.strip())
        if head:
            blocks.append((line.strip(), head.group(2).strip(), []))
        else:
            blocks[-1][2].append(line)
    return [
        (prefix, title, "\n".join(body).strip())
        for prefix, title, body in blocks
        if prefix or title or "\n".join(body).strip()
    ]


