"""types/__init__.py -- 9 大会议类型注册表与轻量类型探测路由器。

对外提供：
- BaseAgendaTypeSpec, PillarGuide
- ALL_AGENDA_TYPES: 包含全部 9 类幕后导师的列表
- AGENDA_TYPE_REGISTRY: 按 type_id 索引的字典
- get_agenda_type_spec(type_id): 安全获取类型实例
- detect_agenda_type(theme, titles, transcript_sample): 依据会议主题、议题标题与实录样本自动路由
"""
from __future__ import annotations

import logging
from typing import Sequence

from .base import BaseAgendaTypeSpec, PillarGuide
from .decision_approval import DecisionApprovalTypeSpec
from .review_selection import ReviewSelectionTypeSpec
from .planning_strategy import PlanningStrategyTypeSpec
from .alignment_consensus import AlignmentConsensusTypeSpec
from .info_sync import InfoSyncTypeSpec
from .retrospective import RetrospectiveTypeSpec
from .brainstorming import BrainstormingTypeSpec
from .release_broadcast import ReleaseBroadcastTypeSpec
from .knowledge_share import KnowledgeShareTypeSpec

logger = logging.getLogger(__name__)

ALL_AGENDA_TYPES: list[BaseAgendaTypeSpec] = [
    DecisionApprovalTypeSpec(),
    ReviewSelectionTypeSpec(),
    PlanningStrategyTypeSpec(),
    AlignmentConsensusTypeSpec(),
    InfoSyncTypeSpec(),
    RetrospectiveTypeSpec(),
    BrainstormingTypeSpec(),
    ReleaseBroadcastTypeSpec(),
    KnowledgeShareTypeSpec(),
]

AGENDA_TYPE_REGISTRY: dict[str, BaseAgendaTypeSpec] = {
    spec.type_id: spec for spec in ALL_AGENDA_TYPES
}

DEFAULT_AGENDA_TYPE = DecisionApprovalTypeSpec()


def get_agenda_type_spec(type_id: str) -> BaseAgendaTypeSpec:
    """按 type_id 获取会议类型规范，未命中时回退默认决策审批型。"""
    if not type_id:
        return DEFAULT_AGENDA_TYPE
    return AGENDA_TYPE_REGISTRY.get(type_id.strip().lower(), DEFAULT_AGENDA_TYPE)


def detect_agenda_type(
    theme: str = "",
    titles: Sequence[str] | None = None,
    transcript_sample: str = "",
    context: str = "",
) -> BaseAgendaTypeSpec:
    """根据会议主题、议题标题列表与现场实录前导文本，智能判定会议所属第一性目的类型。

    判定优先级：
    1. 会议主题 (theme) 显式关键词强加权匹配；
    2. 议题标题 (titles) 多数投票匹配；
    3. 实录文本 (transcript_sample/context) 关键词密度；
    4. 缺省兜底为决策审批型 (decision_approval)。
    """
    theme_lower = (theme or "").lower()
    titles_lower = [str(t).lower() for t in (titles or []) if t]
    sample = (transcript_sample or context or "")[:5000].lower()

    scores: dict[str, int] = {spec.type_id: 0 for spec in ALL_AGENDA_TYPES}

    # 1. 扫描主题 theme (权重 10 * 关键词长度)
    if theme_lower:
        for spec in ALL_AGENDA_TYPES:
            for kw in spec.keywords:
                if kw.lower() in theme_lower:
                    scores[spec.type_id] += 10 * len(kw)

    # 2. 统计议题标题 titles 命中情况（权重 3 * 关键词长度）
    for title in titles_lower:
        for spec in ALL_AGENDA_TYPES:
            for kw in spec.keywords:
                if kw.lower() in title:
                    scores[spec.type_id] += 3 * len(kw)

    # 3. 统计实录样本中的关键词出现频率 (权重 1)
    if sample:
        for spec in ALL_AGENDA_TYPES:
            for kw in spec.keywords:
                if kw.lower() in sample:
                    scores[spec.type_id] += 1

    best_type_id, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score > 0:
        matched = AGENDA_TYPE_REGISTRY[best_type_id]
        logger.info("会议类型探测：综合得分命中【%s】(%s, score=%d)", matched.type_name, matched.type_id, best_score)
        return matched

    return DEFAULT_AGENDA_TYPE


__all__ = [
    "BaseAgendaTypeSpec",
    "PillarGuide",
    "ALL_AGENDA_TYPES",
    "AGENDA_TYPE_REGISTRY",
    "DEFAULT_AGENDA_TYPE",
    "get_agenda_type_spec",
    "detect_agenda_type",
    "DecisionApprovalTypeSpec",
    "ReviewSelectionTypeSpec",
    "PlanningStrategyTypeSpec",
    "AlignmentConsensusTypeSpec",
    "InfoSyncTypeSpec",
    "RetrospectiveTypeSpec",
    "BrainstormingTypeSpec",
    "ReleaseBroadcastTypeSpec",
    "KnowledgeShareTypeSpec",
]
