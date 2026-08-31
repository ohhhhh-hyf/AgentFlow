"""场景骨架：不同会议场景给不同的组织侧重，通用为兜底。

结构统一（内容总结 / 主要议题 / 关键决策 / 行动项 / 会议结论），
但各场景在议题侧重、小结侧重上不同；「按问题切 3–6 个议题、不按人分章」是
所有场景的硬约束（见 structure.py 与生成 prompt）。
"""
from __future__ import annotations

import re

GENERIC_SCENE = "通用"

_DEFAULT_REQUIREMENT = (
    "忠实原文；按议题组织；事实与观点分离；讨论与决策分离；"
    "无内容的动态章节整节省略；用户批注不得写入正文。"
)

_DEFAULT_FORMAT = """# 内容总结
4-8条：目的、核心讨论、确认事项、阻塞。
# 主要议题
3-6个问题/事项；每个含：问题与事实、讨论观点、建议与方案、议题小结。
# 关键决策与明确要求
# 行动项与后续安排
# 会议结论"""

SCENE_LABELS = (
    "团队例会",
    "脑暴/讨论",
    "项目决策与评审",
    "专项讨论会",
    "研讨会",
    "采访/对话",
)

# 各场景的骨架格式（结构按场景本质差异化，不是只换侧重措辞）
_SCENE_FORMATS = {
    "团队例会": _DEFAULT_FORMAT + "\n侧重：进展与达成、问题与偏差、风险阻塞、协调支持。",
    "项目决策与评审": """# 内容总结
4-8条：评审对象、结论、依据、风险。
# 评审对象与范围
# 主要议题
3-6个问题/事项；每个含：问题与事实、讨论观点、建议与方案、议题小结。侧重：结论、依据、条件、整改。
# 评审结论
# 行动项与后续安排""",
    "专项讨论会": """# 内容总结
4-8条：专项问题、结论、待办。
# 问题界定
# 主要议题
2-4个讨论点；每个含：问题与事实、讨论观点、建议与方案、议题小结。侧重：边界、分析、方案、结论。
# 关键决策与明确要求
# 行动项与后续安排
# 会议结论""",
    "研讨会": """# 内容总结
4-8条：研讨主题、主要观点、共识。
# 研讨主题与背景
# 主要议题
3-6个话题；每个含：问题与事实、讨论观点、建议与方案、议题小结。侧重：观点、分歧、共识、结论。
# 主要分歧与共识
# 后续安排""",
    "脑暴/讨论": """# 内容总结
4-8条：想法/方案、归类、初步取舍。
# 主要议题
3-6个想法类别；每个含：问题与事实、讨论观点、建议与方案、议题小结。侧重：想法、评估、取舍、待验证。
# 想法与方案汇总
# 初步取舍与待验证
# 后续安排""",
    "采访/对话": """# 内容总结
4-8条：核心观点、关键结论、未来计划。
# 主要议题
3-6个话题；每个含：问题与事实、讨论观点、建议与方案、议题小结。侧重：观点判断、经历事实、结论计划。
# 关键结论
# 未来计划与承诺""",
}

_ASSIGN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('{3}|\"{3})",
    re.M,
)


def parse_scene_pack(raw: str) -> dict[str, str]:
    """抽出 template.txt 里的三引号赋值。"""
    text = raw or ""
    out: dict[str, str] = {}
    for match in _ASSIGN.finditer(text):
        name, quote = match.group(1), match.group(2)
        start = match.end()
        end = text.find(quote, start)
        if end < 0:
            continue
        out[name] = text[start:end]
    return out


def normalize_scene_label(text: str) -> str:
    raw = (text or "").strip().replace(" ", "")
    if not raw:
        return ""
    for label in SCENE_LABELS:
        if label in raw or raw in label:
            return label
    aliases = {
        "脑暴": "脑暴/讨论",
        "头脑风暴": "脑暴/讨论",
        "讨论会": "脑暴/讨论",
        "决策": "项目决策与评审",
        "评审": "项目决策与评审",
        "专项": "专项讨论会",
        "研讨": "研讨会",
        "例会": "团队例会",
        "采访": "采访/对话",
        "访谈": "采访/对话",
        "对话": "采访/对话",
    }
    for key, label in aliases.items():
        if key in raw:
            return label
    return ""


def heuristic_scene_label(src: str) -> str:
    """在 LLM 标签含糊或跑偏时，用会议内容做稳定兜底。"""
    text = src or ""
    if any(k in text for k in ("评审", "决策", "决议", "通过", "不通过", "风险", "阻塞")):
        return "项目决策与评审"
    if any(k in text for k in ("专项", "专题", "具体问题", "整改", "优化")):
        return "专项讨论会"
    if any(k in text for k in ("采访", "访谈", "对话", "专访", "答记者问")):
        return "采访/对话"
    if any(k in text for k in ("脑暴", "头脑风暴", "创意", "想法", "方案讨论")):
        return "脑暴/讨论"
    if any(k in text for k in ("培训", "分享", "研讨", "学习", "课程", "学术")):
        return "研讨会"
    if any(k in text for k in ("周会", "月会", "例会", "进展", "计划", "汇报")):
        return "团队例会"
    return ""


def detect_scene(
    understanding: dict | None = None,
    transcript: str = "",
) -> str:
    """判定会议场景：优先消费会议理解的 scene 字段（结构化语义判定），
    理解缺失/为「通用」/非法值时，用原文启发式作兜底。"""
    if isinstance(understanding, dict):
        label = normalize_scene_label(
            str(understanding.get("scene") or "").strip()
        )
        if label and label != GENERIC_SCENE:
            return label
    src = str(
        (understanding or {}).get("meeting_purpose")
        or (understanding or {}).get("purpose")
        or ""
    )
    src = f"{src} {transcript or ''}"
    label = heuristic_scene_label(src)
    return label or GENERIC_SCENE




def generic_spec(pack: dict[str, str], pack_raw: str = "") -> tuple[str, str]:
    """固定读取通用骨架。没有赋值块时，把整份模板当 format。"""
    data = pack if isinstance(pack, dict) else {}
    req = (data.get("common_meeting_requirement") or "").strip()
    fmt = (data.get("common_meeting_format") or "").strip()
    global_rule = (data.get("GLOBAL_CONSTRAINT") or "").strip()
    if global_rule:
        req = f"{global_rule}\n\n{req}".strip() if req else global_rule
    if not fmt and (pack_raw or "").strip() and not data:
        fmt = pack_raw.strip()
    if not req:
        req = _DEFAULT_REQUIREMENT
    if not fmt:
        fmt = _DEFAULT_FORMAT
    return req, fmt


def scene_spec(pack: dict[str, str], label: str = "") -> tuple[str, str]:
    """按场景返回骨架：该场景的侧重格式 + 场景化要求；未知/空回通用。"""
    scene = normalize_scene_label(label or "")
    fmt = _SCENE_FORMATS.get(scene)
    if fmt is None:
        return generic_spec(pack)
    data = pack if isinstance(pack, dict) else {}
    global_rule = (data.get("GLOBAL_CONSTRAINT") or "").strip()
    req = (
        f"本场景为「{scene}」：按该场景的侧重组织议题；{_DEFAULT_REQUIREMENT}"
    )
    if global_rule:
        req = f"{global_rule}\n\n{req}"
    return req, fmt




__all__ = [
    "GENERIC_SCENE",
    "SCENE_LABELS",
    "detect_scene",
    "generic_spec",
    "heuristic_scene_label",
    "normalize_scene_label",
    "parse_scene_pack",
    "scene_spec",
]
