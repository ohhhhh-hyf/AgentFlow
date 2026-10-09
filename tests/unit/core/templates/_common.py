"""tests/unit/core/templates/_common.py -- 模板路由测试公共基线与断言工具。"""
from __future__ import annotations

import logging
from pathlib import Path

PASS: list[str] = []
FAIL: list[str] = []

SCALAR_BASELINE_BY_DIR: dict[str, dict[str, int]] = {
    "template": {
        "class_transcript": 4, "clinical_advisory": 5, "contract_vetting": 4,
        "conversation_transcript": 4, "court_transcript": 3, "debate_forum": 4,
        "decision_review": 4, "exchange_forum": 5, "general_minutes": 3,
        "personal_minutes": 4,
        "government_bulletin": 3, "group_seminar": 4, "hiring_report": 3,
        "home_school_liaison": 4, "interview_debrief": 4, "interview_transcript": 3,
        "knowledge_memo": 3, "legal_advisory": 4, "media_briefing": 4,
        "media_qa_session": 4, "personal_memo": 4, "product_launch": 4,
        "admission_briefing": 5,
        "project_progress": 2, "psychological_session": 3, "research_dialogue": 4,
        "retrospective_session": 5, "site_visit_tour": 4, "special_lecture": 4,
        "team_meeting": 4, "workshop_session": 4,
    },
}

KNOWN_PENDING_BRACKET_LITERALS: set[str] = set()


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f" | {detail}" if detail else ""))


def _active_dir() -> Path:
    """当前生效模板目录（固定为 template）。"""
    from app.config import template_dir

    return Path(template_dir())


FILL_TPL = """# [甲栏]
[一段话概括甲栏内容]

# [乙栏]
[一段话概括乙栏内容]

# [丙栏]
[一段话概括丙栏内容]
"""

CAPTION_TPL = """# [甲栏]
[一段话概括甲]

# [进度追踪]
[按下表逐行填写各模块的进展与当前状态（一行一个模块）；不要另建表格，表内已写的明细不在别处重复]

| 模块 | 进展 |
| --- | --- |
| … | … |

# [乙栏]
[一段话概括乙]
"""

BODY_CAPTION_TPL = """# [治疗方案与医嘱]
[医嘱清单：检查安排、用药、生活方式、复诊与陪同要求各占一条，每条都是 `- ` 分点行；药品明细只写进下表]

| 药名 | 剂量 |
| --- | --- |
| … | … |
"""

SHAPE_RULE_KEYS = (
    "分组不并事实",
    "算形态缺陷",
    "大类分组",
    "禁止同名重复",
    "段落上限",
    "按需加粗",
    "未决/待澄清栏口径",
    "猜测补全",
)

FILL_RULE_KEYS = (
    "条目长度以模板显式要求为准",
    "简单且完整的行动项可以短于 30 字",
    "完整交代",
    "结论式孤条",
    "同一句话不拆多条",
    "状态标记",
    "表格栏",
    "不可拆事实可以超过 120 字",
    "最多出现 1 次",
    "禁止写「原文未提及…」这类缺失说明句",
    "不设每栏最低数量",
    "成员称呼",
    "小节之下必须分条列出",
)

TEMPLATE_SHAPE_SNIPPETS = {
    "retrospective_session": "- **改进事项名**：",
    "hiring_report": "本栏明细由下表承载",
    "hiring_report#维度": "不自行发明能力模型",
    "media_briefing": "一条讲透一个主题",
    "site_visit_tour": "都要汇总到这里",
    "knowledge_memo": "不要再以同名",
    "clinical_advisory": "每条都是 `- ` 分点行",
    "home_school_liaison": "每一件事都要落进清单",
    "project_progress": "本栏明细由下表承载",
    "project_progress#后续": "按事项分点写",
    "court_transcript": "本栏明细由下表承载",
    "team_meeting": "四要素",
    "admission_briefing": "原文点到的事实一律不得丢",
    "conversation_transcript": "未形成明确结论",
    "group_seminar": "没有统一意见时写本场达成的倾向性认识与主要分歧点",
    "class_transcript": "不得写成连续段落",
    "general_minutes": "一段写完，约 250–400 字",
    "personal_memo": "不要写「未提及」",
    "psychological_session": "不强行总结结论",
}
