from __future__ import annotations

import logging
import re

from client import LLMClient

logger = logging.getLogger(__name__)

from ....models import Catalog
from ..contracts import CATALOG_SLIM_GENERATION_OUTPUT_CONTRACT
from ..gather import build_catalog_briefing, subject_from_context, user_id_from_context
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
        return Catalog.validate(merged)
