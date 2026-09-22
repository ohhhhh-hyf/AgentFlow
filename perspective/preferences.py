"""用户偏好 → 纪要指令块（只调顺序与详略，不改事实）。

为什么单独一块、不走视角建模：偏好是"怎么写"的元指令，不是"谁是相关方"的事实判断。
让它经过一次 LLM（视角建模）只是多一层信息损耗——实测那条链路里模型产出的
``preference_signals`` 被两份 compact 白名单同时丢弃，等于白跑；现在由程序直接
把 user.json 的 preferences/personality 编成指令，只注入纪要线。

两条硬约束：
1. 全部指令都限定在「顺序与详略」，事实口径仍以原文/上游为准（标题行写明）；
2. ``personality`` 只允许命中白名单映射成语气类指令，**绝不把性格原文写进 prompt**
   （原文一旦进 prompt，模型很容易写成"他很不满"这类评价）。
"""
from __future__ import annotations

import re
from typing import Any

BLOCK_TITLE = "本用户偏好（只调顺序与详略，不改事实）"
# 注入范围：只有纪要线（引擎侧按同一常量判断，避免两处各写一份）
PREFERENCE_LINES = frozenset({"minutes", "minutes_styles"})

# ── 本视角纪律（逐栏填充/装配那一轮的写作纪律）─────────────────────
# 为什么还要一份：带模板时正文由 ``tools.templates.router`` 的通用填充器写，它的 system
# 里**没有**领域渲染提示词（只有「你只写本栏正文」），模板渲染提示词那条路根本不执行。
# 于是个人模式会照着模板栏名（全文摘要 / 分段速览）把整场会都写出来——实测 8172 字、
# 超本篇参考上限 48%，和客观纪要看不出差别。所以取舍纪律要作为"本栏写作纪律"显式下发。
VIEW_DIRECTIVE_TITLE = "本视角纪律"
# 本人那一组的组名：末尾三栏（结论与决定 / 行动项与分工 / 待确认与风险）统一用它——
# 组长名带"事项"只能套在"行动项"那一类上，落到结论/风险栏就说不通（结论不是"事项"）。
SELF_GROUP_NAME = "与我相关"
SELF_GROUP_ROW = f"**{SELF_GROUP_NAME}**："
PERSONAL_VIEW_DIRECTIVE = (
    f"【{VIEW_DIRECTIVE_TITLE}】按下面的取舍纪律写本栏"
    "（**栏名、结构与事实口径照模板不变**；模板写作要求里若写「客观、非人格化」，"
    "真人模式下**人称与取舍以本纪律为准**）：\n"
    "- **相关＝点名，不是「属于他的关注领域」**：只有 ①原文点到他的姓名/别称，"
    "②他有发言的那一段，③直接挂在他负责的模块与指标上的事项，才算他的；"
    "**别把整场按关注领域都收进来**。\n"
    "- **本栏主旨按「他能带走什么」理解**：模板栏名若是「全文摘要」「分段速览」「全文要点」，"
    "真人模式下只写**与他相关的部分**（其余用一个短句交代场合与全局结论即可），"
    "**不要因为栏名带「全文」就把整场都写进来**。\n"
    "- **会议原文只当证据**：用来补他相关部分的细节（数字、时限、原话）；"
    "**不要照着原文把整场再讲一遍**——取舍以【已批准纪要草稿】为准。\n"
    "- 给的会议原文**已按人裁剪**（`省略 N 段与本人无关的发言` 处是别人主讲的内容）："
    "不要补全省略部分、不要凭常识推断；要全局结论就从【已批准纪要草稿】与【会议理解】取。\n"
    "- **以本人为叙事主线**：他参与的进展、表态、承诺、被点名事项写开写足；"
    "**别人主讲、且与他无关的板块压成一句带过**（不列分条、不搬数字；"
    "表格只留与他相关的行）；别人主讲但结论影响全局的，只留结论一句。\n"
    "- **末尾三栏（结论与决定 / 行动项与分工 / 待确认与风险）都按「人」分组，形状照抄**"
    "（组名行独占一行、不加 `- `；块内 `- ` 一条一行；没有内容的块不出现）：\n"
    f"  {SELF_GROUP_ROW}\n"
    "  - （本人条目，不写自己的姓名）\n"
    "  **他人姓名**：\n"
    "  - （该人的条目，不重复姓名）\n"
    "- 同一栏内的口径：**自己的部分放最前**、条目内**不写自己的姓名**"
    "（组名已说明归属，不必每条重复姓名；本人动作仍按下面的省主语句式）；"
    "**他人的按其姓名分组**（姓名照原文），组内同样 `- ` 一条一行；"
    "草稿里已有的组名行**原样保留、独占一行、不加 `- `**，其下条目照抄（不补姓名）；"
    f"**有明确归属才分组**：看不出归属的全局项平铺在最前、不加任何姓名、也不冠「{SELF_GROUP_NAME}」；"
    "某一块没有内容就不出现该组。他的条目一条不落，是这一栏的主体；"
    "确需他配合的外部依赖并进自己那块写成一句。\n"
    "- 影响全局的结论、范围纳入/排除、关键数字仍**不得漏**"
    "（审核按「遗漏直接影响该姓名的关键全局决策」判）。\n"
    "- **人名口径**：**本人动作省主语**（中文允许省略，读者默认省略的主语是自己："
    "「今天先把配置改完，明天给结论」）；**他人动作写真名**（「王工要求周五前完成联调」）；"
    "需要点明归属时才用「你」（待办、提醒、被点名），首现可锚定一次「你（姓名）」；"
    "分工、责任人、引语与第三人姓名**一律真名**；**同一句与相邻两句不混用**「你」与真名。\n"
    "- 内容来源给了【本用户命中】时**以它为准**：命中条目必须写到位，"
    "未命中的条目不要写成他的事；命中表写明「未命中」时，正文不给他派活。\n"
    "- 整栏确实与他无关时，按该栏缺省写法给一句兜底（如「无」「未提及」），**不要留空栏**。"
)

# 专属个人模板（personal_minutes.md）纪律：与原生工作台契约相配合，无针对通用模板栏名的对抗指令
PERSONAL_TEMPLATE_VIEW_DIRECTIVE = (
    f"【{VIEW_DIRECTIVE_TITLE}】按本模板的个人工作台视角要求写本栏（**以本模板栏名与说明为第一准则**）：\n"
    "- **以本人为叙事主线**：优先展现本人牵头/负责的模块、交付与排查项；他人的事项若为本人的前置输入或协同依赖则成句体现，纯属他人的闭门事项不予展开。\n"
    "- **人名口径**：**本人动作省主语**（中文允许省略，读者默认省略的主语是自己：「今天先把配置改完，明天给结论」）；**他人动作写真名**（「王工要求周五前完成联调」）；需要点明归属时才用「你」（待办、提醒、被点名）；分工、责任人、引语与第三人姓名一律真名；同一句与相邻两句不混用「你」与真名。\n"
    "- **分栏组名**：行动项与风险卡点栏中，归属本人的条目排在最前并独占一行「**与我相关**：」，他人分工按姓名分组「**姓名**：」；前置依赖列在「**前置依赖**：」下；没有内容的组不出现。\n"
    "- 内容来源给了【本用户命中】时**以它为准**：命中条目必须写到位，未命中的条目不要写成他的事；命中表写明「未命中」时，正文不给他派活。\n"
    "- 涉及本人的关键数字、日期、承诺、交付口径不得遗漏；整栏确实与本人无关时按缺省写法兜底（如「无」「未提及」），不要留空栏。"
)


# 偏好关键词 → 可执行指令（白名单；命不中的偏好原样列成"偏好说明"，由模型按标题约束执行）
# 关键词取"意图词"不取名词：裸「结论」会命中「实验结论/会议结论」（用户要的是写全，不是先给结论）。
_PREFERENCE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("待办", "行动项", "todo", "to-do"), "先列「本用户命中」的待办，再写其余"),
    (
        ("简洁", "精简", "简短", "别太长", "不要太长", "少一点"),
        "整体精简：删铺陈与套话，只留结论/数字/责任人/时限",
    ),
    (("先给结论", "先说结论", "先说结果", "先看结论", "结论先行"), "每段先给结论口径，再补依据"),
    (("详细", "细节", "写全", "不要省略"), "细节写全：原文有的数字、时限、口径、责任人不省略"),
    (("数字", "口径", "金额"), "关键数字与口径优先保留，写全单位与对比基准"),
    (("风险", "阻塞", "问题"), "风险与阻塞单独成段，写清影响面与谁在跟"),
    (
        ("上级", "领导", "老板", "主管", "指示", "指示与行动"),
        "关注上级要求与指示，相关结论与行动项紧随本人分组优先呈现",
    ),
    # 与上一条互斥：「不要省略」属上一条，这里只认"少写/不要写/别写"的减法意图
    (("少写", "不要写", "别写"), "未点名且不在关注域内的条目可以少写"),
)

# 性格关键词 → 只允许"语气/详略"类指令（硬编码小表；命不中就不写这一行）
# 措辞用括号不用冒号：块里由 ``build_preference_block`` 统一加「语气：」前缀，避免两个冒号连排。
_PERSONALITY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("务实", "直接", "干脆", "雷厉"), "表述直接（先结论后细节，不用客套）"),
    (
        ("严谨", "较真", "细致", "含糊", "讨厌"),
        "含糊说法不写（「尽快/稍后/差不多了」换成原文的时限或「待确认」）",
    ),
    (("技术", "工程", "细节控"), "技术细节（接口/参数/版本/依赖）优先保留"),
    (("委婉", "温和", "平和"), "语气平和，不加评价性措辞"),
)
from tools.core.text import clean_text as _clean

_MAX_RULES = 4      # 映射出的可执行指令条数上限
_MAX_FREE = 3       # 未命中的偏好原样列出条数上限
_MAX_PREFS = 6      # 读入的偏好条数上限（下游另有输出上限，这里只防超长列表）
_MAX_ITEM = 40      # 每条偏好/性格的字符上限（超长截断，避免把整段话塞进 prompt）
_MAX_TOTAL = 6      # 整块条数上限


def _clip(text: str, limit: int = _MAX_ITEM) -> str:
    return text if len(text) <= limit else text[:limit].rstrip()


def _match_rules(text: str, rules: tuple[tuple[tuple[str, ...], str], ...]) -> list[str]:
    hit = [statement for keys, statement in rules if any(key in text for key in keys)]
    return hit


def as_text_list(value: Any, *, cap: int, clip: int = _MAX_ITEM) -> list[str]:
    """容忍三种写法：``None`` / 单个字符串 / 字符串数组（写 JSON 时不必纠结）。

    为什么容错：``name_aliases``、``personality``、``preferences`` 都是"一串短句"，
    手写 JSON 时很容易写成单字符串；旧实现会把单字符串**按字符迭代**（"家坤" → ['家','坤']，
    全被短于 2 字丢掉）或 ``str(list)`` 成 "['务实', …]"（能碰巧命中关键词但很脏）。
    这里统一：清洗、去空、去重、单条截断、总量封顶。
    """
    if value is None:
        return []
    items = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple, set)) else []
    out: list[str] = []
    for item in items:
        text = _clip(_clean(item), clip)
        if text and text not in out:
            out.append(text)
        if len(out) >= cap:
            break
    return out


def build_preference_block(user: dict[str, Any] | None) -> str:
    """把画像偏好编成纪要指令块；没有可用内容（或客观视角）时返回空串。

    客观视角不注入：那份画像里本来就没有个人偏好，硬塞会让客观纪要带上"先写我的待办"。
    ``personality`` 允许是字符串或数组（多个性格短句各匹配一次语气白名单）。
    """
    profile = user if isinstance(user, dict) else {}
    if str(profile.get("perspective") or "").strip().lower() == "objective":
        return ""

    statements: list[str] = []
    free_notes: list[str] = []

    for text in as_text_list(profile.get("preferences"), cap=_MAX_PREFS):
        matched = _match_rules(text, _PREFERENCE_RULES)
        if matched:
            statements.extend(matched)
        elif len(free_notes) < _MAX_FREE:
            free_notes.append(text)

    tone: list[str] = []
    for trait in as_text_list(profile.get("personality"), cap=4):
        tone.extend(_match_rules(trait, _PERSONALITY_RULES))  # 命不中 → 不写，绝不落原文

    lines: list[str] = []
    seen: set[str] = set()
    for statement in statements:
        if statement in seen or len(lines) >= _MAX_RULES:
            continue
        seen.add(statement)
        lines.append(statement)
    for statement in tone:
        if statement in seen or len(lines) >= _MAX_TOTAL:
            continue
        seen.add(statement)
        lines.append(f"语气：{statement}")
    for note in free_notes:
        if len(lines) >= _MAX_TOTAL:
            break
        lines.append(f"偏好说明（按「只调顺序与详略」执行）：{note}")

    if not lines:
        return ""
    return "\n".join([f"【{BLOCK_TITLE}】"] + [f"- {line}" for line in lines])


# ── 本用户称呼表（注入理解层，统一人名写法）──────────────────────
# 人名的"统一称呼"只有理解层能做：下游（视角裁剪、待办 owner、跨场记忆、审核）都只认
# 理解层写下的那个字符串；视角建模那轮连原文都看不到，改不了人名。所以把"全称+别称"
# 提前告诉理解层，是最便宜也最关键的一步（零新增调用，百字以内输入）。
CHANNEL_TITLE = "本用户称呼"
_MAX_ALIASES = 6
_MAX_ALIAS_CHARS = 12


def address_aliases(user: dict[str, Any] | None) -> list[str]:
    """可用的会上别称：≥2 字、去掉与姓名/角色/部门重复的、按声明顺序去重、超长截断。"""
    profile = user if isinstance(user, dict) else {}
    name = _clean(profile.get("name"))
    blocked = {_clean(profile.get("role")), _clean(profile.get("department")), name}
    out: list[str] = []
    for alias in as_text_list(profile.get("name_aliases"), cap=_MAX_ALIASES, clip=_MAX_ALIAS_CHARS):
        if len(alias) < 2 or alias in blocked or alias in out:
            continue
        out.append(alias)
    return out


def build_user_channel(user: dict[str, Any] | None) -> str:
    """理解层的「本用户称呼」块：统一人名写法，但不许猜编号发言人。

    三种情况不注入（返回空串）：
    - 客观视角：不针对任何人；
    - 职业模板（``persona_type == role_template``）：``name`` 是"开发人员"这类通称、不是人名，
      当称呼会让模型把职业名写进 owner（提示词明令禁止的那件事）；
    - 没有姓名：无从点名。
    """
    profile = user if isinstance(user, dict) else {}
    if str(profile.get("perspective") or "").strip().lower() == "objective":
        return ""
    if str(profile.get("persona_type") or "").strip().lower() == "role_template":
        return ""
    name = _clean(profile.get("name"))
    if not name:
        return ""
    aliases = address_aliases(profile)
    head = f"【{CHANNEL_TITLE}】{name}（全称）"
    if aliases:
        head += "；别称：" + "、".join(aliases)
    lines = [
        head + "。",
        f"原文出现这些称呼时统一写成「{name}」；speakers / owner 能对上这些称呼的也写「{name}」。",
        "对不上不要猜：发言者1 / 发言人A 这类编号不等于本用户"
        + ("（除非上面的别称里显式写了它）。" if aliases else "。"),
    ]
    return "\n".join(lines)


_SUPERVISOR_STOPWORDS = frozenset(
    {
        "自己", "本人", "我们", "大家", "上级", "领导", "主管", "老板", "他人", "对方",
        "组长", "指示", "要求", "安排", "行动", "意见", "关注", "跟进", "决策", "她的",
        "他的", "他们", "她们", "各个", "各位",
    }
)


def extract_supervisors(user: dict[str, Any] | None) -> list[str]:
    """从用户画像中提取上级/领导姓名（用于优先级与分组排序）。"""
    profile = user if isinstance(user, dict) else {}
    if not profile:
        return []

    self_name = _clean(profile.get("name"))
    aliases = set(address_aliases(profile))
    blocked = {self_name, *aliases, *_SUPERVISOR_STOPWORDS}

    supervisors: list[str] = []

    def _add(cand: str) -> None:
        c = _clean(cand)
        if 2 <= len(c) <= 4 and c not in blocked and c not in supervisors:
            supervisors.append(c)

    # 1. 显式字段声明
    for key in ("supervisor", "leader", "reports_to", "manager"):
        val = profile.get(key)
        if isinstance(val, str):
            _add(val)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                _add(str(item))

    # 2. 从偏好/说明中提取
    prefs = as_text_list(profile.get("preferences"), cap=10)
    for text in prefs:
        for m in re.finditer(r"([^\s，,。；;：:]{2,4})\s*(?:是|为)\s*(?:我的)?(?:直接)?(?:上级|领导|老板|主管|TL|组长)", text):
            _add(m.group(1))
        for m in re.finditer(r"(?:直接)?(?:上级|领导|老板|主管|汇报对象|汇报给)\s*(?:是|为|[：:\s])\s*([^\s，,。；;：:]{2,4})", text):
            _add(m.group(1))
        for m in re.finditer(r"(?:关注|跟进|落实|执行)\s*([^\s，,。；;：:]{2,4})\s*的\s*(?:指示|要求|意见|安排|决策)", text):
            _add(m.group(1))

    return supervisors


__all__ = [
    "BLOCK_TITLE",
    "CHANNEL_TITLE",
    "PREFERENCE_LINES",
    "address_aliases",
    "build_preference_block",
    "build_user_channel",
    "extract_supervisors",
]
