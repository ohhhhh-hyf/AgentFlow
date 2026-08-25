"""唯一解析入口：显式 id > 短名强命中 > 弱实体重叠 > 首个项目新建 > 不确定则不绑。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .entities import (
    extract_entities,
    is_key_candidate,
    overlap_score,
    pick_project_key,
)
from .store import (
    empty_record,
    list_records,
    load_record,
    next_project_id,
    record_path,
    safe_id,
)

MIN_WEAK_HITS = 2
MIN_HITS = MIN_WEAK_HITS  # 兼容旧引用：弱 n-gram 门槛


@dataclass(frozen=True)
class Bind:
    """一次运行的项目归属。inject 与 write 必须用同一份。"""

    project_id: str | None
    create: bool
    hits: int = 0
    strong: int = 0
    entities: tuple[str, ...] = ()
    project_key: str = ""


def identity_keys(record: dict[str, Any]) -> list[str]:
    """档案上可用于强命中的短名：已锁定 key、合格短别名；缺省则从 purpose 回推。"""
    keys: list[str] = []
    locked = str(record.get("project_key") or "").strip()
    if locked:
        keys.append(locked)
    for alias in record.get("name_aliases") or []:
        text = str(alias or "").strip()
        if text and is_key_candidate(text) and text not in keys:
            keys.append(text)
    if keys:
        return keys
    meeting = record.get("meeting") if isinstance(record.get("meeting"), dict) else {}
    inferred = pick_project_key(
        str((meeting or {}).get("purpose") or record.get("display_name") or ""),
        str(record.get("display_name") or ""),
    )
    return [inferred] if inferred else []


def _score_record(transcript: str, found: list[str], rec: dict[str, Any]) -> tuple[int, int]:
    from .entities import entity_names

    stored = entity_names(rec.get("entities"))
    stored.extend(str(a).strip() for a in (rec.get("name_aliases") or []) if str(a).strip())
    name = str(rec.get("display_name") or "").strip()
    if name:
        stored.append(name)
    weak = overlap_score(found, stored)
    strong = 0
    for key in identity_keys(rec):
        if key and key in (transcript or ""):
            strong = 1
            break
    return strong, weak


def resolve_notes(
    project_root: Path,
    user_id: str,
    subject: str | None = None,
    explicit_id: str | None = None,
) -> Bind:
    """笔记归属：同一用户只按学科名分档，不做实体模糊挂钩。"""
    label = (subject or explicit_id or "").strip()
    if not (user_id or "").strip() or not label:
        return Bind(project_id=None, create=False)
    pid = safe_id(label)
    rec = load_record(record_path(project_root, "notes", user_id, pid))
    return Bind(
        project_id=pid,
        create=not bool(rec),
        project_key=label,
    )


def resolve(
    project_root: Path,
    domain: str,
    user_id: str,
    transcript: str,
    explicit_id: str | None = None,
    subject: str | None = None,
) -> Bind:
    """解析本次应归属的项目。

    笔记域：user_id + 学科名（--subject，或 --project 当作学科）。
    会议域：
    - 显式 id：直接采用（文件不存在也算绑定，回写时建档）
    - 用户下还没有任何项目：标记 create，回写时分配新 id
    - 库存短名（project_key / 合格别名 / 从 purpose 回推的引号专名）出现在原文：1 次即可归入
    - 否则原文弱实体与某一库存唯一重叠 ≥ 2：归入
    - 多项目并列或证据不足：不绑（不注入、不新建）
    """
    user_id = (user_id or "").strip()
    if not user_id:
        return Bind(project_id=None, create=False)

    if (domain or "").strip() == "notes":
        return resolve_notes(project_root, user_id, subject, explicit_id)

    found = extract_entities(transcript)
    entities = tuple(found)
    existing = list_records(project_root, domain, user_id)

    explicit = (explicit_id or "").strip()
    if explicit:
        return Bind(project_id=safe_id(explicit), create=False, entities=entities)

    if not existing:
        return Bind(project_id=None, create=True, entities=entities)

    scored: list[tuple[int, int, str, str]] = []
    for rec in existing:
        pid = str(rec.get("project_id") or "")
        if not pid:
            continue
        strong, weak = _score_record(transcript, found, rec)
        keys = identity_keys(rec)
        scored.append((strong, weak, pid, keys[0] if keys else ""))

    if not scored:
        return Bind(project_id=None, create=True, entities=entities)

    best_strong = max(row[0] for row in scored)
    if best_strong >= 1:
        winners = [row for row in scored if row[0] == best_strong]
        if len(winners) == 1:
            strong, weak, pid, key = winners[0]
            return Bind(
                project_id=pid,
                create=False,
                hits=weak,
                strong=strong,
                entities=entities,
                project_key=key,
            )
        # 多项目并列：先按 project_key 合并（同一档案因历史场次/误建出现多条时，
        # 取 run_count 最大的那条绑定，避免同 key 重复档案导致永久无法关联记忆）
        from collections import defaultdict

        groups: dict[str, list[tuple[tuple[int, int, str, str], int]]] = defaultdict(list)
        for row in winners:
            _strong, _weak, _pid, _key = row
            key_name = _key or _pid
            rec = next((r for r in existing if str(r.get("project_id") or "") == _pid), {})
            try:
                runs = int(rec.get("run_count") or 0)
            except (TypeError, ValueError):
                runs = 0
            groups[key_name].append((row, runs))
        merged: dict[str, tuple[int, int, str, str]] = {}
        for key_name, items in groups.items():
            best = max(items, key=lambda x: (x[1], x[0][1]))  # run_count 大优先，weak 大其次
            merged[key_name] = best[0]
        dedup = list(merged.values())
        if len(dedup) == 1:
            strong, weak, pid, key = dedup[0]
            return Bind(
                project_id=pid,
                create=False,
                hits=weak,
                strong=strong,
                entities=entities,
                project_key=key,
            )
        return Bind(
            project_id=None,
            create=False,
            hits=max(row[1] for row in dedup),
            strong=best_strong,
            entities=entities,
        )

    # ── embedding 语义归属（方案 B：规则未命中时用向量相似度找回同一项目）──
    # 只在该层可用且候选唯一达标时绑定；多候选并列或不可用 → 继续走弱实体规则。
    from .embed import MEMORY_EMBED_MIN_SCORE, get_embedder

    embedder = get_embedder(user_id=user_id)
    if embedder.enabled:
        try:
            cands = [
                c for c in embedder.search_projects(transcript, user_id, top_k=3)
                if float(c.get("score") or 0.0) >= MEMORY_EMBED_MIN_SCORE
            ]
            if cands:
                top = cands[0]
                second_ok = len(cands) > 1 and float(cands[1].get("score") or 0.0) >= MEMORY_EMBED_MIN_SCORE
                if not second_ok:
                    return Bind(
                        project_id=str(top["project_id"]),
                        create=False,
                        hits=int(float(top.get("score") or 0.0) * 100),
                        strong=0,
                        entities=entities,
                        project_key=str(top.get("project_key") or ""),
                    )
        except Exception:  # noqa: BLE001 - 语义层异常降级回规则
            logger.warning("记忆语义归属失败，降级规则匹配", exc_info=True)

    best_weak = max(row[1] for row in scored)
    winners = [row for row in scored if row[1] == best_weak and row[1] >= MIN_WEAK_HITS]
    if best_weak >= MIN_WEAK_HITS and len(winners) == 1:
        strong, weak, pid, key = winners[0]
        return Bind(
            project_id=pid,
            create=False,
            hits=weak,
            strong=strong,
            entities=entities,
            project_key=key,
        )
    # 都不匹配：视为「新项目首会」→ 新建（支持同一用户多个独立项目）。
    # 注意：输入被假定为会议纪要；若担心无关/闲聊输入也会建档，
    # persist 有「新建门槛」——理解无实质内容（无议题/决策/未决）时跳过写回。
    return Bind(
        project_id=None,
        create=True,
        hits=best_weak,
        entities=entities,
    )


def materialize(
    project_root: Path,
    domain: str,
    user_id: str,
    bind: Bind,
) -> dict | None:
    """得到可读写的 record。create 时分配新 id；未绑定返回 None。"""
    if bind.project_id:
        path = record_path(project_root, domain, user_id, bind.project_id)
        rec = load_record(path)
        return rec or empty_record(user_id, bind.project_id, domain)
    if bind.create:
        pid = next_project_id(list_records(project_root, domain, user_id))
        return empty_record(user_id, pid, domain)
    return None


__all__ = [
    "Bind",
    "MIN_HITS",
    "MIN_WEAK_HITS",
    "extract_entities",
    "identity_keys",
    "materialize",
    "resolve",
    "resolve_notes",
]
