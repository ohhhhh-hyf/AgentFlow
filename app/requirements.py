"""各接口必填字段声明表 + 前置校验。

请求进入任务管线前先按本表校验，缺必填字段直接 400（秒回，不触发 LLM）。
字段取值（type/style/template 等）的合法性校验仍在 tasks._validate。
"""
from __future__ import annotations

from .schemas import TaskRequest

# 各接口必填项。key 为校验标识，label 用于错误消息。
# 支持形式：
#   "user_id"          请求头 X-User-Id
#   "texts.transcript"  texts 数组中存在 type=transcript 且 content 非空
#   "texts.keypoints"   texts 数组中存在 type=keypoints 且 content 非空
#   "texts.notes"       texts 数组中存在 type=notes 且 content 非空
#   "extra.style"       extra.style 非空
#   "extra.subject"     extra.subject 非空
#   "docs"              docs 数组非空
#   "docs_any"          docs 数组非空（至少一个文件）
REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "minutes": {
        "user_id": "X-User-Id",
        "texts.transcript": "texts 中 transcript（会议转写文本）",
    },
    "actions": {
        "user_id": "X-User-Id",
        "texts.transcript": "texts 中 transcript（会议转写文本）",
    },
    "risks": {
        "user_id": "X-User-Id",
        "texts.transcript": "texts 中 transcript（会议转写文本）",
    },
    "minutes_styles": {
        "user_id": "X-User-Id",
        "texts.transcript": "texts 中 transcript（会议转写文本）",
        "extra.style": "extra.style（多样式纪要组织模式）",
    },
    "minutes_trace": {
        "user_id": "X-User-Id",
        "texts.transcript": "texts 中 transcript（会议转写文本）",
        "texts.keypoints": "texts 中 keypoints（用户重点文本）",
        "texts.notes": "texts 中 notes（用户笔记文本）",
    },
    "graph": {
        "user_id": "X-User-Id",
        "docs": "docs（笔记 .txt/.md 文件）",
    },
    "library": {
        "user_id": "X-User-Id",
        "docs_any": "docs（文件或图片）",
    },
    "catalog": {
        "user_id": "X-User-Id",
        "extra.subject": "extra.subject（学科）",
    },
    "checklist": {
        "user_id": "X-User-Id",
        "extra.subject": "extra.subject（学科）",
        "docs": "docs（catalog 文件名，如 phy_8b4dccc8.json）",
    },
}


def _has_text_type(req: TaskRequest, text_type: str) -> bool:
    return bool(((req.texts or {}).get(text_type) or "").strip())


def check_required(task: str, req: TaskRequest, user_id: str) -> list[str]:
    """返回所有缺失的必填项描述（空列表 = 全部满足）。"""
    missing: list[str] = []
    required = REQUIRED_FIELDS.get(task) or {}
    for key, label in required.items():
        if key == "user_id":
            if not (user_id or "").strip():
                missing.append(label)
        elif key == "extra.style":
            if not (req.extra.style or "").strip():
                missing.append(label)
        elif key == "extra.subject":
            if not (req.extra.subject or "").strip():
                missing.append(label)
        elif key == "docs":
            if not (req.docs or []):
                missing.append(label)
        elif key == "docs_any":
            if not (req.docs or []):
                missing.append(label)
        elif key.startswith("texts."):
            if not _has_text_type(req, key.split(".", 1)[1]):
                missing.append(label)
    return missing


__all__ = ["REQUIRED_FIELDS", "check_required"]
