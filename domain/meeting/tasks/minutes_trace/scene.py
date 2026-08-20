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
用 4–8 条 `- ` 短要点概括会议目的、核心讨论、已确认事项与当前阻塞。不要写成一段。

# 主要议题
按主题归并 3–6 个议题。每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。
各小节正文用 `- ` 分点，一条一事。不要按发言人流水账。原文没有的小段写「未提及」。

# 关键决策与明确要求
仅记录已经明确确认、决定或要求执行的事项。没有则整节不写。

# 行动项与后续安排
仅提取原文明示的后续任务。负责人和时间未说明则写「未明确」。没有则整节不写。

# 会议结论
## 已形成的共识与要求
## 未决与分歧
## 风险、阻塞与待跟进
子节没有内容则不写。"""

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
    "团队例会": """# 内容总结
用 4–8 条 `- ` 短要点概括本期进展、关键问题与需协调事项。不要写成一段。

# 主要议题
按主题归并 3–6 个议题。**侧重：进展与达成 / 问题与偏差 / 风险与阻塞 / 协调与支持**。
每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 关键决策与明确要求
仅记录已确认的决定或要求。没有则整节不写。

# 行动项与后续安排
仅提取原文明示的后续任务；负责人和时间未说明则写「未明确」。没有则整节不写。

# 会议结论
## 已形成的共识与要求
## 未决与分歧
## 风险、阻塞与待跟进
子节没有内容则不写。""",
    "项目决策与评审": """# 内容总结
用 4–8 条 `- ` 短要点概括评审对象、总体结论（通过/不通过/有条件通过）、主要依据与关键风险。不要写成一段。

# 评审对象与范围
简述被评审的对象、范围与评审方式（现场/资料/分专业）。原文没有则整节不写。

# 主要议题
按主题归并 3–6 个议题。**侧重：评审结论 / 依据与标准 / 风险与条件 / 整改要求**。
每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 评审结论
**明确结论**：通过 / 不通过 / 有条件通过（结论不明确则写「未下最终结论」）。
## 满足项与依据
## 问题项与整改要求
子节没有内容则不写。

# 行动项与后续安排
仅提取原文明示的后续任务（含整改项、遗留复核）；负责人和时间未说明则写「未明确」。没有则整节不写。""",
    "专项讨论会": """# 内容总结
用 4–8 条 `- ` 短要点概括专项问题、讨论结论与待办。不要写成一段。

# 问题界定
用 2–4 条 `- ` 明确本次讨论的核心问题是什么、边界在哪。原文没有则写「未提及」。

# 主要议题
按问题分解归并 2–4 个讨论点。**侧重：问题界定 / 讨论与分析 / 方案建议 / 结论**。
每个讨论点包含：问题与事实、讨论观点、建议与方案、讨论小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 关键决策与明确要求
仅记录已确认的决定或要求。没有则整节不写。

# 行动项与后续安排
仅提取原文明示的后续任务；负责人和时间未说明则写「未明确」。没有则整节不写。

# 会议结论
## 已形成的共识与要求
## 未决与分歧
## 风险、阻塞与待跟进
子节没有内容则不写。""",
    "研讨会": """# 内容总结
用 4–8 条 `- ` 短要点概括研讨主题、各方主要观点与形成的共识。不要写成一段。

# 研讨主题与背景
1–3 条 `- ` 说明主题、背景与讨论目的。原文没有则整节不写。

# 主要议题
按讨论主题归并 3–6 个议题。**侧重：各方观点 / 分歧点 / 共识 / 结论**。
每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 主要分歧与共识
## 主要分歧
## 已形成共识
子节没有内容则不写。

# 后续安排
仅提取原文明示的后续任务或交流安排；负责人和时间未说明则写「未明确」。没有则整节不写。""",
    "脑暴/讨论": """# 内容总结
用 4–8 条 `- ` 短要点概括产生的想法/方案、归类与初步取舍。不要写成一段。

# 主要议题
按想法类别归并 3–6 个议题。**侧重：提出的想法 / 讨论与评估 / 初步取舍 / 待验证**。
每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 想法与方案汇总
按类别列出本场提出的想法/方案（`- ` 一条一个），标注提出方（若有）。没有则整节不写。

# 初步取舍与待验证
## 初步倾向
## 待验证事项
子节没有内容则不写。

# 后续安排
仅提取原文明示的后续任务（含验证/试点）；负责人和时间未说明则写「未明确」。没有则整节不写。""",
    "采访/对话": """# 内容总结
用 4–8 条 `- ` 短要点概括被访者/对话方的核心观点、关键结论与未来计划。不要写成一段。

# 主要议题
按话题组织 3–6 个议题（**不按被访者/发言人分章**）。**侧重：观点与判断 / 经历与事实 / 结论 / 未来计划**。
每个议题包含：问题与事实、讨论观点、建议与方案、议题小结。各小节用 `- ` 分点。原文没有的小段写「未提及」。

# 关键结论
仅记录对话中明确表达的结论、判断或约定（若有）。没有则整节不写。

# 未来计划与承诺
仅提取对话中明确的后续安排/计划；时间未说明则写「未明确」。没有则整节不写。""",
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
