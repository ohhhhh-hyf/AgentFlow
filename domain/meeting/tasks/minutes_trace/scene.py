"""场景骨架：不同会议场景给不同的组织侧重，通用为兜底。

结构统一（内容总结 / 主要议题 / 关键决策 / 行动项 / 会议结论），
但各场景在议题侧重、小结侧重上不同；「按问题切 3–6 个议题、不按人分章」是
所有场景的硬约束（见 structure.py 与生成 prompt）。

骨架正文存放在同目录 ``scenes/*.md``（便于直接编辑模板），是场景差异化骨架的
唯一来源；``_DEFAULT_FORMAT`` 仅作文件缺失时的内置兜底（通用结构，不绑定场景）。
"""
from __future__ import annotations

import re
from pathlib import Path

GENERIC_SCENE = "通用"

_SCENES_DIR = Path(__file__).resolve().parent / "scenes"

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

_ASSIGN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*('{3}|\"{3})",
    re.M,
)


def _scene_file(label: str) -> Path:
    """场景 label → scenes 目录下的 md 文件（斜杠以 _ 代，如 脑暴/讨论 → 脑暴_讨论.md）。"""
    fname = label.replace("/", "_") + ".md"
    return _SCENES_DIR / fname


def load_scene_format(label: str) -> str:
    """按场景读取骨架正文；差异化骨架只存 scenes/*.md，文件缺失时回退内置通用骨架。"""
    scene = normalize_scene_label(label or "")
    if not scene:
        scene = GENERIC_SCENE
    try:
        path = _scene_file(scene)
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    except OSError:
        pass
    return _DEFAULT_FORMAT


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
        fmt = load_scene_format(GENERIC_SCENE)
    return req, fmt


def scene_spec(pack: dict[str, str], label: str = "") -> tuple[str, str]:
    """按场景返回骨架：该场景的侧重格式 + 场景化要求；未知/空回通用。"""
    scene = normalize_scene_label(label or "")
    fmt = load_scene_format(scene) if scene else ""
    if not fmt:
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
    "load_scene_format",
    "normalize_scene_label",
    "parse_scene_pack",
    "scene_spec",
]
