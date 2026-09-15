from __future__ import annotations

import logging
import re

from client import LLMClient

logger = logging.getLogger(__name__)

from ....models import Catalog
from ..contracts import CATALOG_SLIM_GENERATION_OUTPUT_CONTRACT
from ..gather import (
    _norm_name,
    build_catalog_briefing,
    build_catalog_position_map,
    subject_from_context,
    user_id_from_context,
)
from ..merge import merge_catalog, normalize_catalog_enums
from ..prompts import CATALOG_GENERATION_SYSTEM_PROMPT
from ..store import load_catalog


def _clean(value: object) -> str:
    return str(value or "").strip()


# LLM 输出契约的 KP 字段白名单：契约外的惯性字段（如 confidence）不入落盘
_LLM_KP_FIELDS = frozenset({
    "id", "name", "aliases", "chapter", "topic", "knowledge_type",
    "knowledge_items", "importance", "difficulty", "teacher_emphasis",
    "foundational_level", "exam_signal", "note_coverage", "note_missing_items",
    "practice_type", "completion_criteria", "learning_role", "risk_tags",
    "prerequisites", "related_points", "relation", "evidence",
    "sources", "source_documents", "source_chunk_ids",
    "node_status", "change_type",
})


def _infer_practice_type(point: dict) -> list[str]:
    kind = str(point.get("knowledge_type") or "").strip()
    name = _clean(point.get("name"))
    items = " ".join(str(item) for item in (point.get("knowledge_items") or []))
    blob = f"{name} {items}"
    # 判定词只保留跨学科的功能形态词（文体词），不含任何具体学科词汇
    if kind == "formula" or any(word in blob for word in ("公式", "方程")):
        return ["recall", "calculate"]
    if kind == "theorem" or any(word in blob for word in ("定理", "证明")):
        return ["prove", "apply"]
    if kind == "method" or any(word in blob for word in ("求算", "步骤", "方法", "变换")):
        return ["calculate", "choose_method"]
    if kind == "application":
        return ["apply"]
    if any(word in blob for word in ("区别", "比较", "条件", "适用")):
        return ["recall", "distinguish"]
    return ["recall", "can_explain"][:1]


def _infer_completion_criteria(point: dict) -> list[str]:
    practices = set(point.get("practice_type") or [])
    out = ["can_recall", "can_explain"]
    if "distinguish" in practices:
        out.append("can_distinguish")
    if "calculate" in practices:
        out.append("can_solve_standard")
    if "choose_method" in practices:
        out.append("can_choose_method")
    if "prove" in practices:
        out.append("can_prove")
    if "apply" in practices:
        out.append("can_apply")
    return out


def _infer_learning_role(point: dict) -> str:
    kind = str(point.get("knowledge_type") or "").strip()
    try:
        foundational = int(str(point.get("foundational_level") or "0") or "0")
    except (TypeError, ValueError):
        foundational = 0
    if foundational >= 4:
        return "foundation"
    if kind == "method":
        return "core_method"
    if kind == "application":
        return "application"
    if kind == "mixed":
        return "integration"
    return "core_concept"


def _infer_risk_tags(point: dict) -> list[str]:
    kind = str(point.get("knowledge_type") or "").strip()
    name = _clean(point.get("name"))
    items = " ".join(str(item) for item in (point.get("knowledge_items") or []))
    blob = f"{name} {items}"
    risks: list[str] = []
    # 判定词只保留跨学科的功能形态词（文体词），不含任何具体学科词汇
    if any(word in blob for word in ("条件", "适用", "边界", "限制")):
        risks.append("condition_check")
    if kind == "formula" or any(word in blob for word in ("公式", "符号")):
        risks.append("formula_misuse")
    if kind == "method" or any(word in blob for word in ("步骤", "求算", "方法")):
        risks.append("method_selection")
    if kind == "theorem" or any(word in blob for word in ("证明", "定理")):
        risks.append("proof_format")
    if any(word in blob for word in ("易错", "混淆", "区别")):
        risks.append("concept_confusion")
    return risks or ["concept_confusion"]


def _backfill_slim_point_fields(catalog: dict) -> dict:
    for ch in catalog.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ch_name = _clean(ch.get("name"))
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            tp_name = _clean(tp.get("name"))
            for point in tp.get("knowledge_points") or []:
                if not isinstance(point, dict):
                    continue
                point.setdefault("chapter", ch_name)
                point.setdefault("topic", tp_name)
                point.setdefault("teacher_emphasis", "0")
                point.setdefault("foundational_level", "3")
                point.setdefault("exam_signal", "none")
                point.setdefault("note_coverage", "mentioned")
                point.setdefault("note_missing_items", [])
                point.setdefault("sources", [])
                point.setdefault("source_documents", [])
                point.setdefault("source_chunk_ids", [])
                point.setdefault("teacher_focus_items", [])
                point.setdefault("note_covered_items", [])
                point.setdefault("aliases", [])
                point.setdefault("prerequisites", [])
                point.setdefault("related_points", [])
                point.setdefault("evidence", [])
                if not point.get("practice_type"):
                    point["practice_type"] = _infer_practice_type(point)
                if not point.get("completion_criteria"):
                    point["completion_criteria"] = _infer_completion_criteria(point)
                if not point.get("learning_role"):
                    point["learning_role"] = _infer_learning_role(point)
                if not point.get("risk_tags"):
                    point["risk_tags"] = _infer_risk_tags(point)
    return catalog


def _reorder_by_source_order(catalog: dict, position: dict[str, int]) -> dict:
    """按资料原文顺序重排 chapters / topics / knowledge_points（确定性，零 token）。

    LLM 不一定按输入顺序输出（提示词里也要求了，但不能只靠它），这一步用
    ``build_catalog_position_map`` 的名字→位置表做兜底：章按"自身或名下知识点最早出现的
    位置"排序、主题与知识点同理；位置表里没有的节点排到最后并保持原有相对顺序
    （Python 的 sort 是稳定排序）。只调整列表顺序，不动 id/字段。
    """
    if not position:
        return catalog

    above = 10 ** 9

    def pos_of(name: object) -> int | None:
        key = _norm_name(name)
        return position.get(key) if key else None

    def point_pos(point: dict) -> int:
        value = pos_of(point.get("name"))
        return above if value is None else value

    def topic_pos(topic: dict) -> int:
        own = pos_of(topic.get("name"))
        if own is not None:
            return own
        values = [
            point_pos(p)
            for p in (topic.get("knowledge_points") or [])
            if isinstance(p, dict)
        ]
        values = [v for v in values if v < above]
        return min(values) if values else above

    def chapter_pos(chapter: dict) -> int:
        # 章的位置取"其下最早节点"，不看章名：章名常直接取自某个主题
        # （章名常取自其下某个主题），用章名查会把整章拉到那个主题的位置，破坏整体单调。
        values = [
            topic_pos(t)
            for t in (chapter.get("topics") or [])
            if isinstance(t, dict)
        ]
        values = [v for v in values if v < above]
        if values:
            return min(values)
        own = pos_of(chapter.get("name"))
        return own if own is not None else above

    out = dict(catalog)
    chapters = [c for c in (out.get("chapters") or []) if isinstance(c, dict)]
    for chapter in chapters:
        topics = [t for t in (chapter.get("topics") or []) if isinstance(t, dict)]
        for topic in topics:
            points = [p for p in (topic.get("knowledge_points") or []) if isinstance(p, dict)]
            points.sort(key=point_pos)
            topic["knowledge_points"] = points
        topics.sort(key=topic_pos)
        chapter["topics"] = topics
    chapters.sort(key=chapter_pos)
    out["chapters"] = chapters
    return out


def _strip_llm_extra_fields(catalog: dict) -> dict:
    """剔除 LLM 输出中契约外的 KP 字段（如 confidence），只保留白名单。

    契约是 LLM 输出模板的唯一依据；浅校验不拦多余字段，
    这里在 merge 前做确定性过滤，保证 LLM 惯性字段不进落盘。
    """
    for ch in catalog.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            points = [p for p in (tp.get("knowledge_points") or []) if isinstance(p, dict)]
            tp["knowledge_points"] = [
                {k: v for k, v in p.items() if k in _LLM_KP_FIELDS} for p in points
            ]
    return catalog


def _catalog_structure_issues(catalog: dict) -> list[str]:
    """结构保真校验：返回问题列表（空列表 = 通过）。

    覆盖三类不合格结构：
    - 结构缺失：章空 / 章无主题 / 主题无知识点
    - 三层占位：章-主题-KP 三层同名（纯凑层级）
    - 空占位：主题下唯一同名 KP 且无 knowledge_items（内容为空壳）
    """
    issues: list[str] = []
    chapters = [c for c in (catalog.get("chapters") or []) if isinstance(c, dict)]
    if not chapters:
        return ["chapters 为空"]
    for ch in chapters:
        ch_name = _clean(ch.get("name"))
        topics = [t for t in (ch.get("topics") or []) if isinstance(t, dict)]
        if not topics:
            issues.append(f"章「{ch_name}」没有主题")
            continue
        for tp in topics:
            tp_name = _clean(tp.get("name"))
            kps = [p for p in (tp.get("knowledge_points") or []) if isinstance(p, dict)]
            if not kps:
                issues.append(f"主题「{tp_name}」没有知识点")
                continue
            kp_name = _clean(kps[0].get("name")) if len(kps) == 1 else ""
            # 三层全同名占位（章下唯一主题、主题下唯一 KP 且三者同名）
            if len(topics) == 1 and len(kps) == 1 and ch_name and ch_name == tp_name == kp_name:
                issues.append(f"章「{ch_name}」-主题-KP 三层同名占位")
                continue
            # 主题 == 唯一 KP 同名且无实质内容（knowledge_items 为空）
            if len(kps) == 1 and tp_name and tp_name == kp_name:
                items = [i for i in (kps[0].get("knowledge_items") or []) if _clean(i)]
                if not items:
                    issues.append(f"主题「{tp_name}」唯一同名 KP 无 knowledge_items（空占位）")
    return issues


def _norm_cmp(text: object) -> str:
    return re.sub(r"[\s:：,，。；;、（）()\[\]【】]+", "", str(text or "").lower())


def _repair_fallback_point(name: str, chapter: str, topic: str, kid: str) -> dict:
    """标题回退的最小 KP（与 merge._fill_empty_topics 同款语义，供修复器复用）。"""
    return {
        "id": kid,
        "name": name,
        "chapter": chapter,
        "topic": topic,
        "knowledge_type": "mixed",
        "knowledge_items": [name],
        "importance": "3",
        "difficulty": "3",
        "note_coverage": "mentioned",
        "sources": [],
        "evidence": [],
        "aliases": [],
        "prerequisites": [],
        "related_points": [],
    }


def _repair_catalog_structure(catalog: dict) -> tuple[dict, list[str]]:
    """确定性结构修复（零 token）：能修的修，修不了的留给重试。

    可修（与 _catalog_structure_issues 的问题一一对应）：
    - 主题无知识点 → 标题回退补点（merge._fill_empty_topics 同款语义）；
    - 主题下唯一同名 KP 无 knowledge_items（空壳）→ 补 items=[主题名]；
    - 章-主题-KP 三层同名 → KP 具体化改名（取 items[0] / aliases[0] 当更具体的
      名，原 KP 名下移进 items）——消除纯凑层级；无可用信息时保留给重试；
    - KP 缺 id → 前序补号。
    不可修（信息不足，必须重试）：chapters 为空、章无主题。
    返回 (修复后的 catalog, 仍存在的问题列表)。
    """
    repairs: list[str] = []
    chapters = [c for c in (catalog.get("chapters") or []) if isinstance(c, dict)]
    # 先扫已有 kp id 集，供回退补点与缺 id 补号取号
    used_ids: set[str] = set()
    for ch in chapters:
        for tp in (ch.get("topics") or []):
            if not isinstance(tp, dict):
                continue
            for point in (tp.get("knowledge_points") or []):
                if isinstance(point, dict) and _clean(point.get("id")):
                    used_ids.add(_clean(point["id"]))
    next_seq = 1

    def _take_kp_id() -> str:
        nonlocal next_seq
        while f"kp_{next_seq:03d}" in used_ids:
            next_seq += 1
        kid = f"kp_{next_seq:03d}"
        used_ids.add(kid)
        next_seq += 1
        return kid

    for ch in chapters:
        ch_name = _clean(ch.get("name"))
        topics = [t for t in (ch.get("topics") or []) if isinstance(t, dict)]
        ch["topics"] = topics
        for tp in topics:
            tp_name = _clean(tp.get("name"))
            kps = [p for p in (tp.get("knowledge_points") or []) if isinstance(p, dict)]
            # 主题无知识点 → 标题回退补点（merge._fill_empty_topics 同款语义）
            if not kps and tp_name:
                kps = [_repair_fallback_point(tp_name, ch_name, tp_name, _take_kp_id())]
                tp["knowledge_points"] = kps
                repairs.append(f"主题「{tp_name}」无知识点 → 标题回退补点")
            single_same = len(kps) == 1 and tp_name and _clean(kps[0].get("name")) == tp_name
            # 空壳：唯一同名 KP 无 items → 补 items
            if single_same and len(topics) >= 1:
                kp = kps[0]
                items = [i for i in (kp.get("knowledge_items") or []) if _clean(i)]
                if not items:
                    kp["knowledge_items"] = [tp_name]
                    repairs.append(f"主题「{tp_name}」空壳 KP → 补 knowledge_items")
            # 三层同名 → KP 具体化改名
            if (
                len(topics) == 1
                and len(kps) == 1
                and ch_name
                and tp_name
                and ch_name == tp_name == _clean(kps[0].get("name"))
            ):
                kp = kps[0]
                items = [i for i in (kp.get("knowledge_items") or []) if _clean(i)]
                aliases = [_clean(a) for a in (kp.get("aliases") or []) if _clean(a)]
                new_name = ""
                if items and _norm_cmp(items[0]) != _norm_cmp(ch_name):
                    new_name = items[0]
                elif aliases and _norm_cmp(aliases[0]) != _norm_cmp(ch_name):
                    new_name = aliases[0]
                if new_name:
                    kp["name"] = new_name
                    kp["knowledge_items"] = [tp_name] + [i for i in items if _norm_cmp(i) != _norm_cmp(new_name)]
                    kp["aliases"] = [a for a in aliases if _norm_cmp(a) != _norm_cmp(new_name)]
                    repairs.append(
                        f"章「{ch_name}」三层同名占位 → KP 具体化为「{new_name}」"
                    )
    patched = 0
    for ch in chapters:
        for tp in (ch.get("topics") or []):
            if not isinstance(tp, dict):
                continue
            for point in (tp.get("knowledge_points") or []):
                if isinstance(point, dict) and not _clean(point.get("id")):
                    point["id"] = _take_kp_id()
                    patched += 1
    if patched:
        repairs.append(f"补 KP id {patched} 个")
    if repairs:
        logger.info("catalog repair: %s", "; ".join(repairs))
    return catalog, _catalog_structure_issues(catalog)


def _enforce_catalog_structure(catalog: dict) -> dict:
    """确定性修正（零 token）：importance 与知识单元数对齐（prompt 校准规则的程序化）。

    - items ≥3 且 importance <3 → 提到 3（内容充实的 KP 不应低评）
    - items == 0 且 importance ≥3 → 降到 2（空占位不虚高）
    不改动树形结构本身（结构问题交给 issues 重试）。
    """
    _raised = 0
    _lowered = 0
    for ch in catalog.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for tp in ch.get("topics") or []:
            if not isinstance(tp, dict):
                continue
            for kp in tp.get("knowledge_points") or []:
                if not isinstance(kp, dict):
                    continue
                items_n = len([i for i in (kp.get("knowledge_items") or []) if _clean(i)])
                try:
                    importance = int(str(kp.get("importance") or "0") or "0")
                except (TypeError, ValueError):
                    importance = 0
                if items_n >= 3 and importance < 3:
                    kp["importance"] = "3"
                    _raised += 1
                elif items_n == 0 and importance >= 3:
                    kp["importance"] = "2"
                    _lowered += 1
    logger.info("catalog enforce: raised=%d lowered=%d", _raised, _lowered)
    return catalog


def _restore_from_skeleton(catalog: dict, shared_context: str) -> dict:
    """按原文骨架补齐模型漏掉的 T/P（零 LLM）。骨架不可用时原样返回。

    只增不减：模型已有的节点不动；骨架里缺失的主题/知识点按原文位置补回
    （``node_status=program_restore``），便于事后一眼看出"哪些是程序补的"。
    """
    from ..skeleton import build_source_skeleton, restore_from_skeleton

    try:
        skeleton = build_source_skeleton(shared_context)
        if not skeleton.get("topics"):
            return catalog
        out, report = restore_from_skeleton(catalog, skeleton)
    except Exception:  # noqa: BLE001 - 骨架校验失败不阻断目录生成
        logger.warning("catalog skeleton restore failed", exc_info=True)
        return catalog
    if report["restored_topics"] or report["restored_points"]:
        logger.info(
            "catalog skeleton restore topics=%d points=%d demoted=%d merged=%d llm_added=%d",
            len(report["restored_topics"]),
            len(report["restored_points"]),
            len(report["demoted_kept"]),
            len(report["merged_topics"]),
            report["llm_added"],
        )
    return out


def _source_position_map(shared_context: str) -> dict[str, int]:
    """保序用的位置表：原文骨架优先（精确），回退知识库元数据（P1 的 page/chunk_index）。"""
    from ..skeleton import build_source_skeleton, skeleton_position_map

    try:
        skeleton = build_source_skeleton(shared_context)
        position = skeleton_position_map(skeleton)
        if position:
            return position
    except Exception:  # noqa: BLE001 - 骨架不可用时回退
        logger.warning("catalog skeleton position failed, fallback to kb", exc_info=True)
    return build_catalog_position_map(shared_context)


class CatalogAgent:
    """首次建目录；已有目录则增量合并，保持节点 ID 稳定。"""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def run(self, shared_context: str) -> Catalog:
        briefing = build_catalog_briefing(shared_context)
        draft = await self.client.structured(
            CATALOG_GENERATION_SYSTEM_PROMPT,
            briefing,
            Catalog,
            CATALOG_SLIM_GENERATION_OUTPUT_CONTRACT, label='catalog/agent')
        data = _strip_llm_extra_fields(draft.model_dump())
        data = _backfill_slim_point_fields(data)
        data = _enforce_catalog_structure(data)
        # 骨架权威校验（零 LLM）：模型漏掉的 T/P 按原文骨架补回；已知的"降级/合并"通过
        # 必须传 shared_context：骨架要靠【用户ID】定位 data/{user}/ocr/{subject} 的合并稿，
        # 传 briefing（提示词正文，不含用户标签）会解析出空 user，既丢掉骨架还原、
        # 又让知识库回退到无主目录 data/knowledge/chromadb。
        data = _restore_from_skeleton(data, shared_context)
        # 检测 → 确定性修复（零 token）→ 复验：能修的修，修不了的硬伤才重试
        data, issues = _repair_catalog_structure(data)
        if issues:
            # 结构不达标：带问题清单重试一次（仍失败则用本次结果，交由 merge/兜底，
            # 不引入无限循环）
            retry_briefing = (
                briefing
                + "\n\n【结构校验未通过】\n"
                + "\n".join(f"- {item}" for item in issues)
                + "\n请按结构规则修正上述问题后重新输出完整目录。"
            )
            try:
                retry = await self.client.structured(
                    CATALOG_GENERATION_SYSTEM_PROMPT,
                    retry_briefing,
                    Catalog,
                    CATALOG_SLIM_GENERATION_OUTPUT_CONTRACT, label='catalog/agent')
                data = _strip_llm_extra_fields(retry.model_dump())
                data = _backfill_slim_point_fields(data)
                data = _enforce_catalog_structure(data)
                data = _restore_from_skeleton(data, shared_context)
                # 重试输出同样过修复器（消除小缺陷，避免带伤进 merge）
                data, _ = _repair_catalog_structure(data)
            except Exception:  # noqa: BLE001 - 重试失败沿用首次结果
                pass
        merged = merge_catalog(
            load_catalog(
                user_id=user_id_from_context(shared_context),
                subject=subject_from_context(shared_context),
            ),
            data,
        )
        merged = normalize_catalog_enums(merged)
        # importance 最终校准：merge 会给 KP 回填 knowledge_items，
        # 校准须在回填完成后执行（以最终 items 数为准）
        merged = _enforce_catalog_structure(merged)
        # 确定性保序：目录顺序回到资料原文顺序（放在 merge 之后，因为 merge 的顺序
        # 是"draft 优先 + 历史遗留章节追加到末尾"，会把顺序再改一次）
        order_before = [
            str(c.get("name") or "")
            for c in (merged.get("chapters") or [])
            if isinstance(c, dict)
        ]
        try:
            merged = _reorder_by_source_order(merged, _source_position_map(shared_context))
        except Exception:  # noqa: BLE001 - 保序失败不影响目录生成
            logger.warning("catalog reorder failed, keep llm order", exc_info=True)
        order_after = [
            str(c.get("name") or "")
            for c in (merged.get("chapters") or [])
            if isinstance(c, dict)
        ]
        if order_after and order_after != order_before:
            logger.info("catalog reordered by source order chapters=%s", order_after)
        return Catalog.validate(merged)
