"""测试数据构造器。

Step 5/6 会把各测试文件里重复的状态与草稿构造逻辑逐步收敛到这里。
当前先提供最小可用的 Minutes 草稿构造器，避免继续复制同一份 7 字段字典。
"""
from __future__ import annotations

from typing import Any


def minutes_draft(**overrides: Any) -> dict[str, Any]:
    """返回满足 Minutes 契约的最小 7 字段草稿。"""
    draft: dict[str, Any] = {
        "headline": "测试会议",
        "executive_summary": ["测试概览"],
        "key_decisions": [],
        "personally_relevant_points": [],
        "risks_and_blockers": [],
        "unresolved_questions": [],
        "history_comparison": [],
    }
    draft.update(overrides)
    return draft


def meeting_fact(**overrides: Any):
    """返回一份满足 MeetingFact 的基线事实（测试共享）。"""
    from domains.meeting.memory.extract import MeetingFact

    data: dict[str, Any] = {
        "meeting_id": "m_1",
        "time": "2026-09-01",
        "time_source": "user",
        "title": "小艺慧记Agent开发进展阶段复盘",
        "summary": "复盘小艺慧记Agent第一阶段",
        "anchors": ["小艺慧记Agent"],
        "project_candidates": ["小艺慧记Agent"],
        "decisions": ["8月18日前优化 minutes_trace"],
        "open_items": ["是否默认开启记忆引用"],
        "action_items": [{"text": "补齐记忆引用来源字段", "owner": "赵衡", "timing": "8月19日前"}],
        "risks": ["记忆可解释性不足"],
        "closed_items": [],
        "quotes": [],
    }
    data.update(overrides)
    return MeetingFact.from_dict(data)


AGENDA_BASE = (
    "议题模式：agenda_enhanced\n"
    "视角模式：objective\n\n"
    "【会议原文】\n讨论了指标。\n\n"
)

KEYPOINTS_TAG = "【用户核心关键点】\n流程审批量同比增长46%"

NOTES_TAG = (
    "【用户划线原话与笔记】\n"
    "- 原话：\"上线时间定在周五\" | 备注：确认发布窗口"
)

VISION_TAG = "【视觉信息参考(OCR)】\n服务器CPU使用率峰值82%"


def agenda_context(*tags: str) -> str:
    """议题模式共享上下文（可选附加辅助材料标签块）。"""
    parts = [AGENDA_BASE.rstrip(), "会议理解：\n{}"]
    if tags:
        parts.insert(
            1,
            "════════════════════════════════════════\n" + "\n\n".join(tags),
        )
    return "\n\n".join(parts)


def normal_context(*tags: str) -> str:
    """普通客观模式共享上下文（可选附加辅助材料标签块）。"""
    parts = ["视角模式：objective\n\n【会议原文】\n讨论了指标。", "会议理解：\n{}"]
    if tags:
        parts.insert(
            1,
            "════════════════════════════════════════\n" + "\n\n".join(tags),
        )
    return "\n\n".join(parts)
