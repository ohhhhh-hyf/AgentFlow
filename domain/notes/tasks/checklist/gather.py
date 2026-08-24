"""组装 checklist 的 LLM 输入：Catalog 激活结果 + 老师原文。"""
from __future__ import annotations

from typing import Any

from domain.notes.tasks.catalog.gather import subject_from_context, user_id_from_context
from domain.notes.tasks.catalog.store import load_catalog

from .select import activate_points


def teacher_from_context(text: str) -> str:
    """只取共享上下文里最后一段原文，避免 notes 理解 JSON 里的「原文」污染匹配。"""
    raw = text or ""
    idx = raw.rfind("原文（最高事实来源）：")
    marker_len = len("原文（最高事实来源）：")
    if idx < 0:
        idx = raw.rfind("原文：")
        marker_len = len("原文：")
    if idx >= 0:
        body = raw[idx + marker_len :]
        for stop in ("\n\n用户画像：", "\n\n已审核", "\n\n【用户ID】", "\n\n【学科/课程】", "\n\n【"):
            if stop in body:
                body = body.split(stop, 1)[0]
        body = body.strip()
        return "" if _is_placeholder_teacher(body) else body
    lines = []
    for line in raw.splitlines():
        if line.startswith("【用户ID】") or line.startswith("【学科/课程】"):
            continue
        if line.startswith("视角模式：") or line.startswith("说明："):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    if _is_placeholder_teacher(body):
        return ""
    return body


def _is_placeholder_teacher(text: str) -> bool:
    blob = (text or "").strip()
    if not blob:
        return True
    return blob.startswith("根据已") or blob.startswith("知识库资料入库")


def load_session(shared_context: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    user_id = user_id_from_context(shared_context)
    subject = subject_from_context(shared_context)
    catalog = load_catalog(user_id=user_id, subject=subject)
    teacher = teacher_from_context(shared_context)
    activated = activate_points(catalog, teacher) if catalog else []
    return catalog, activated, teacher


def build_checklist_briefing(
    catalog: dict[str, Any] | None,
    activated: list[dict[str, Any]],
    teacher: str,
) -> str:
    parts = [
        "【任务】基于已有 Catalog 写本次复习卡片，禁止新建知识点。",
        f"【课程】{(catalog or {}).get('course') or ''}",
        f"【目录版本】{(catalog or {}).get('version') or ''}",
    ]
    has_teacher = bool((teacher or "").strip())
    if not catalog:
        parts.append("【Catalog】不存在。不要编知识点，cards 必须空。")
        return "\n".join(parts)
    if has_teacher:
        parts.append("【模式】已提供老师划重点：为匹配到的 KP 写卡片，并做老师原话溯源。")
    else:
        parts.append("【模式】未提供老师划重点：不要做老师原话溯源，只依据 Catalog 与知识库写卡片。uncertain_quotes 必须空。")
    if not activated:
        if has_teacher:
            parts.append("【激活 KP】老师文本没有匹配到目录节点。cards 必须空，uncertain_quotes 收录原话要点。")
        else:
            parts.append("【激活 KP】目录中没有知识点。cards 必须空。")
    else:
        parts.append("【激活 KP】只能给下面这些 id 写卡片：")
        for row in activated:
            parts.append(
                f"- {row.get('id')} | {row.get('name')} | {row.get('session_priority')} | "
                f"type={row.get('knowledge_type')} | items={','.join(row.get('knowledge_items') or [])} | "
                f"focus={','.join(row.get('session_focus_items') or [])} | "
                f"missing={','.join(row.get('note_missing_items') or [])} | "
                f"emph={row.get('session_emphasis')} | exam={row.get('session_exam_signal')} | "
                f"error={(row.get('session_error_signal') or '')[:80]} | "
                f"related={','.join(row.get('session_related_points') or [])} | "
                f"quotes={' / '.join((row.get('session_quotes') or [])[:2])}"
            )
    parts.append("【老师划重点原文】")
    parts.append((teacher or "")[:6000] if has_teacher else "（未提供，跳过老师重点溯源）")
    return "\n".join(parts)
