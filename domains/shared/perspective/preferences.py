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

# 本人分组的组名：供 render_action_groups_block 等程序化骨架使用。
SELF_GROUP_NAME = "与我相关"
SELF_GROUP_ROW = f"**{SELF_GROUP_NAME}**："


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
from core.runner.text import clean_text as _clean

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


def build_user_channel(
    user: dict[str, Any] | None,
    *,
    track: str = "",
    transcript: str = "",
) -> str:
    """理解层的「本用户称呼」块：统一人名写法，引导 Track A/B 双轨理解。

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

    current_track = track
    if not current_track and transcript:
        from .hits import detect_personal_perspective_track
        current_track = detect_personal_perspective_track(transcript, user_profile=profile)

    if current_track == "CONTENT":
        alias_str = "；别称：" + "、".join(aliases) if aliases else ""
        return "\n".join([
            f"【{CHANNEL_TITLE}与代号指引 (Track B 模式)】",
            f"- 目标用户：{name}（全称）{alias_str}。",
            "- 识别规则：由于原文发言人冒号前包含较多匿名代号（如发言人1/2/Speaker 1），请特别注意发言正文：",
            f"  1. 若正文中出现“我是{name}”或通过上下文点名确定某发言人为{name}，其陈述直接作为{name}的事实与承诺记录；",
            f"  2. 提取 action_hints 与 risks 时，凡正文点名要求{name}落实的事项，责任人如实记为「{name}」；",
            f"  3. 严禁凭空将所有发言人1机械推断为{name}，必须有正文点名或应答依据。",
        ])

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
