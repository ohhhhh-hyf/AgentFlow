# -*- coding: utf-8 -*-
"""意图识别 Agent —— 任务 schema 与依赖规则。

字段名与现有 runner/CLI 参数打通：
- runner（--task library/catalog/checklist/quiz/minutes_*）：--file --user_id --subject --project --chapter
- tools.ocr（--input --output）
- chat.cli（--user --subject）

依赖为「确定性兜底」：LLM 给出的 needs 与规则取并集（保守串行）。
"""
from __future__ import annotations

from typing import Any

# 任务 schema：domain / 必需参数 / 可选参数 / 说明
TASK_SPECS: dict[str, dict[str, Any]] = {
    # ── notes 域 ──
    "ocr": {
        "domain": "notes", "required": ["input"], "optional": ["output"],
        "desc": "图片识别成 Markdown（tools.ocr：--input 图片 --output 输出md）",
    },
    "library": {
        "domain": "notes", "required": ["file", "user_id"], "optional": ["subject"],
        "desc": "资料入库（runner：--file 源文件，--user_id 用户，--subject 学科）",
    },
    "catalog": {
        "domain": "notes", "required": ["user_id", "subject"], "optional": ["file"],
        "desc": "知识目录（runner：--user_id --subject；--file 可选=老师划重点文本）",
    },
    "checklist": {
        "domain": "notes", "required": ["user_id", "subject"], "optional": ["file"],
        "desc": "复习清单（runner：--user_id --subject；--file 可选=老师划重点文本）",
    },
    "quiz": {
        "domain": "notes", "required": ["file"], "optional": ["subject", "chapter"],
        "desc": "自测题（runner：--file 笔记原文；--subject/--chapter 可选）",
    },
    "knowledge_graph": {
        "domain": "notes", "required": ["user_id", "subject"], "optional": [],
        "desc": "知识图谱（runner：--user_id --subject）",
    },
    # ── meeting 域 ──
    "minutes_generation": {
        "domain": "meeting", "required": ["file"], "optional": ["user_id", "project"],
        "desc": "会议纪要（runner：--file 会议原文；--user_id/--project 可选）",
    },
    "minutes_trace": {
        "domain": "meeting", "required": ["file"], "optional": ["user_id", "keypoints", "notes"],
        "desc": "纪要溯源/对齐（runner：--file 会议原文；keypoints/notes 为同目录侧车文件，可选）",
    },
    "risk": {
        "domain": "meeting", "required": ["file"], "optional": ["user_id"],
        "desc": "风险分析（runner：--file 会议原文/纪要）",
    },
    "multi_styles": {
        "domain": "meeting", "required": ["file"], "optional": ["user_id"],
        "desc": "多样式纪要（runner：--file 会议原文/纪要）",
    },
    "action_items": {
        "domain": "meeting", "required": ["file"], "optional": [],
        "desc": "行动项/待办提取（runner：--file 会议原文/纪要）",
    },
    "mindmap": {
        "domain": "meeting", "required": ["file"], "optional": [],
        "desc": "会议思维导图（runner：--file 会议原文/纪要）",
    },
    # ── 独立 ──
    "review": {
        "domain": "notes", "required": ["file"], "optional": ["user_id", "subject"],
        "desc": "笔记审查/审校（runner：--file 笔记原文）",
    },
    "chat": {
        "domain": "chat", "required": [], "optional": ["user", "subject"],
        "desc": "问答（chat：--user 必填由调用方兜底；--subject 可选）",
    },
}

# 确定性依赖：task -> 它依赖的前置任务（该任务需要先做完这些，才能执行）
# 只在 plan 里同时存在时才生效（如"只入库不OCR"时 library 不依赖 ocr）
DEPENDS: dict[str, set[str]] = {
    "library": {"ocr"},  # 入库可用 OCR 产物（先识别再入库）
    "catalog": {"library"},  # 目录基于已入库知识库
    "checklist": {"catalog"},  # 复习基于目录
    "minutes_trace": {"minutes_generation"},  # 溯源/对齐基于纪要
    "action_items": {"minutes_generation"},  # 行动项基于纪要
    "mindmap": {"minutes_generation"},  # 导图基于纪要
}

# 参数归一：哪些参数是「文件/路径列表」（多值），哪些是标量
LIST_PARAMS = {"file", "input", "keypoints", "notes"}
SCALAR_PARAMS = {"user_id", "subject", "output", "user", "project", "chapter"}


# 任务别名（LLM 常见变体名 → 规范任务名）
TASK_ALIASES: dict[str, str] = {
    "meeting_minutes": "minutes_generation",
    "minutes": "minutes_generation",
    "minute_generation": "minutes_generation",
    "generate_minutes": "minutes_generation",
    "summary": "minutes_generation",
    "summarize": "minutes_generation",
    "meeting_summary": "minutes_generation",
    "minutes_summary": "minutes_generation",
    "纪要": "minutes_generation",
    "会议纪要": "minutes_generation",
    "总结纪要": "minutes_generation",
    "待办": "action_items",
    "待办提取": "action_items",
    "行动项": "action_items",
    "行动事项": "action_items",
    "todo": "action_items",
    "risk": "risk",
    "风险": "risk",
    "风险分析": "risk",
    "风险提取": "risk",
    "风险点": "risk",
    "risk_extract": "risk",
    "risk_extraction": "risk",
    "extract_risks": "risk",
    "multi_styles": "multi_styles",
    "多样式": "multi_styles",
    "多样式纪要": "multi_styles",
    "多风格纪要": "multi_styles",
    "mindmap": "mindmap",
    "思维导图": "mindmap",
    "trace": "minutes_trace",
    "溯源": "minutes_trace",
    "溯源纪要": "minutes_trace",
    "notes_ingest": "library",
    "ingest": "library",
    "import": "library",
    "入库": "library",
    "知识入库": "library",
    "资料入库": "library",
    "knowledge_catalog": "catalog",
    "catalog_generation": "catalog",
    "目录": "catalog",
    "知识目录": "catalog",
    "生成目录": "catalog",
    "review_list": "checklist",
    "清单": "checklist",
    "复习清单": "checklist",
    "知识清单": "checklist",
    "生成清单": "checklist",
    "quiz_questions": "quiz",
    "出题": "quiz",
    "自测题": "quiz",
    "知识图谱": "knowledge_graph",
    "knowledge_map": "knowledge_graph",
    "graph": "knowledge_graph",
    "kg": "knowledge_graph",
    "审校": "review",
    "笔记审查": "review",
    "笔记审校": "review",
    "review_notes": "review",
    "识别": "ocr",
    "OCR": "ocr",
    "chat_qa": "chat",
}


def normalize_task_name(raw: str) -> str:
    name = str(raw or "").strip()
    if name in TASK_SPECS:
        return name
    return TASK_ALIASES.get(name.lower(), "")


def known_tasks() -> list[str]:
    return sorted(TASK_SPECS)


def task_domain(task: str) -> str:
    spec = TASK_SPECS.get(task) or {}
    return str(spec.get("domain") or "unknown")


def normalize_params(task: str, params: dict[str, Any] | None) -> dict[str, Any]:
    """按任务 schema 归一参数：文件类转 list，标量去空，丢弃未知字段。"""
    spec = TASK_SPECS.get(task)
    if spec is None:
        return {}
    allowed = set(spec.get("required") or []) | set(spec.get("optional") or [])
    out: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key not in allowed:
            continue
        if key in LIST_PARAMS:
            items = value if isinstance(value, list) else [value]
            items = [str(x).strip() for x in items if str(x or "").strip()]
            if items:
                out[key] = items
        elif key in SCALAR_PARAMS:
            text = str(value or "").strip()
            if text and text.lower() != "null":
                out[key] = text
    return out


def missing_params(task: str, params: dict[str, Any]) -> list[str]:
    """该任务还缺哪些必需参数（供提示用户补）。"""
    spec = TASK_SPECS.get(task)
    if spec is None:
        return []
    return [key for key in (spec.get("required") or []) if not params.get(key)]
