"""给 runner 用的注入 / 回写门面。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .entities import is_key_candidate, pick_project_key
from .graph import inject_graph, merge_graph
from .meeting import inject_meeting, merge_meeting
from .notes import merge_notes
from .resolve import Bind, materialize, resolve
from .store import (
    append_history,
    history_path,
    now_stamp,
    record_path,
    save_record,
    shape_record,
)

logger = logging.getLogger(__name__)

MEETING_LINES = frozenset({"minutes_generation", "multi_styles"})
GRAPH_LINES = frozenset({"knowledge_graph"})
MEMORY_LINES = MEETING_LINES | GRAPH_LINES


def _dump(report: object) -> dict[str, Any]:
    if report is None:
        return {}
    if hasattr(report, "model_dump"):
        data = report.model_dump()
        return data if isinstance(data, dict) else {}
    return dict(report) if isinstance(report, dict) else {}


def prepare(
    project_root: Path,
    domain: str,
    user_id: str,
    transcript: str,
    line_names: list[str],
    explicit_id: str | None = None,
    subject: str | None = None,
) -> tuple[Bind, dict[str, str]]:
    """解析归属并生成各线注入文本。失败返回空注入，不抛。"""
    try:
        bind = resolve(
            project_root,
            domain,
            user_id,
            transcript,
            explicit_id,
            subject,
        )
        if (domain or "").strip() == "notes":
            if bind.project_id:
                logger.info(
                    "笔记记忆绑定学科 %s（%s）",
                    bind.project_key or bind.project_id,
                    "新建" if bind.create else "增量",
                )
            else:
                logger.info("笔记记忆未绑定：需要 --user_id 与 --subject")
        elif bind.project_id:
            logger.info(
                "记忆绑定 %s（短名 %s，强命中 %s，弱命中 %s）",
                bind.project_id,
                bind.project_key or "—",
                bind.strong,
                bind.hits,
            )
        elif bind.create:
            logger.info("记忆将新建项目")
        else:
            logger.info("记忆未绑定项目，本次不注入（最佳弱命中 %s）", bind.hits)
        rec = None
        if bind.project_id:
            rec = materialize(project_root, domain, user_id, bind)
        extra: dict[str, str] = {}
        if rec:
            meeting_text = inject_meeting(rec, transcript)
            graph_text = inject_graph(rec)
            for line in line_names:
                if line in MEETING_LINES and meeting_text:
                    extra[line] = meeting_text
                if line in GRAPH_LINES and graph_text:
                    extra[line] = graph_text
        try:
            from tools.monitor.side import record_memory_prepare

            record_memory_prepare(
                bound=bool(bind.project_id),
                created=bool(bind.create),
                strong=int(bind.strong or 0),
                hits=int(bind.hits or 0),
                inject_chars=sum(len(v or "") for v in extra.values()),
                project_id=str(bind.project_id or ""),
            )
        except Exception:  # noqa: BLE001
            pass
        return bind, extra
    except Exception:  # noqa: BLE001
        logger.warning("记忆准备失败，本次不注入", exc_info=True)
        try:
            from tools.monitor.side import record_memory_prepare

            record_memory_prepare(bound=False)
        except Exception:  # noqa: BLE001
            pass
        return Bind(project_id=None, create=False), {}


def _purpose_text(understanding: dict[str, Any] | None) -> str:
    if not isinstance(understanding, dict):
        return ""
    for key in ("meeting_purpose", "note_purpose", "purpose"):
        text = str(understanding.get(key) or "").strip()
        if text:
            return text
    return ""


def _has_meeting_content(understanding: dict[str, Any] | None) -> bool:
    """新建档案门槛：理解里有无实质会议内容（议题/决策/未决/行动线索）。

    防止「匹配不上就新建」把闲聊/无关转写也建成档案；
    会议纪要通常至少有一个议题或决策。
    """
    if not isinstance(understanding, dict):
        return False
    return bool(
        understanding.get("topics")
        or understanding.get("decisions")
        or understanding.get("open_questions")
        or understanding.get("action_hints")
    )


def _refresh_identity(
    record: dict[str, Any],
    bind: Bind,
    reports: dict[str, Any],
    understanding: dict[str, Any] | None = None,
    transcript: str = "",
) -> None:
    from .entities import entity_names, entity_type, normalize_entities

    ents = entity_names(record.get("entities"))
    ent_map = normalize_entities(record.get("entities"))
    for token in bind.entities:
        name = str(token).strip()
        if not name or name in ent_map:
            continue
        ent_map[name] = {
            "name": name,
            "type": entity_type(name),
            "first_seen": "",
            "last_seen": "",
            "status": "active",
            "sessions": [],
        }
        ents.append(name)
    record["entities"] = sorted(
        ent_map.values(), key=lambda e: str(e.get("first_seen") or "")
    )[:24]

    generic_titles = {
        "客观会议纪要",
        "用户视角会议纪要",
        "多样式纪要输出",
        "知识图谱输出",
    }
    title = ""
    purpose = _purpose_text(understanding)
    for key in ("minutes_generation", "multi_styles", "knowledge_graph"):
        dump = _dump(reports.get(key))
        cand = str(dump.get("title") or "").strip()
        if cand and cand not in generic_titles and not cand.endswith("视角会议纪要"):
            title = cand
            break
    title = purpose or title
    name = str(record.get("display_name") or "").strip()
    if not name or name in generic_titles:
        record["display_name"] = title or (ents[0] if ents else record.get("project_id") or "")
    elif title and title != name:
        aliases = [str(a) for a in (record.get("name_aliases") or []) if str(a).strip()]
        if title not in aliases:
            aliases.append(title)
        record["name_aliases"] = aliases[-8:]

    locked = str(record.get("project_key") or "").strip()
    incoming_key = pick_project_key(
        purpose,
        transcript or "",
        str(record.get("display_name") or ""),
    )
    if not locked:
        locked = incoming_key
        if locked:
            record["project_key"] = locked
    elif incoming_key and incoming_key != locked and is_key_candidate(incoming_key):
        aliases = [str(a) for a in (record.get("name_aliases") or []) if str(a).strip()]
        if incoming_key not in aliases:
            aliases.append(incoming_key)
        record["name_aliases"] = aliases[-8:]
    if locked:
        ent_list = list(record.get("entities") or [])
        locked_ent = next(
            (e for e in ent_list if isinstance(e, dict) and e.get("name") == locked),
            None,
        )
        rest = [e for e in ent_list if not (isinstance(e, dict) and e.get("name") == locked)]
        if locked_ent:
            record["entities"] = [locked_ent] + rest[:23]


def persist(
    project_root: Path,
    domain: str,
    user_id: str,
    bind: Bind,
    reports: dict[str, Any],
    understanding: dict[str, Any] | None = None,
    transcript: str = "",
    subject: str | None = None,
) -> dict[str, Any] | None:
    """把本次产出写入同一 bind。未绑定且不应新建则跳过。"""
    try:
        record = materialize(project_root, domain, user_id, bind)
        if record is None:
            logger.info("记忆未绑定项目，本次不写回")
            try:
                from tools.monitor.side import record_memory_persist

                record_memory_persist(ok=False)
            except Exception:  # noqa: BLE001
                pass
            return None
        # 新建门槛（仅会议域）：匹配不上触发新建，但本场无实质会议内容 → 不建档
        if bind.create and (domain or "").strip() == "meeting":
            if not _has_meeting_content(understanding):
                logger.info("新建档案但本场无实质会议内容，跳过写回")
                try:
                    from tools.monitor.side import record_memory_persist

                    record_memory_persist(ok=False)
                except Exception:  # noqa: BLE001
                    pass
                return None
        stamp = now_stamp()
        if (domain or "").strip() == "notes":
            label = (subject or bind.project_key or "").strip()
            record = merge_notes(record, understanding, stamp, label)
        else:
            _refresh_identity(record, bind, reports, understanding, transcript)
            record = merge_meeting(
                record, reports, stamp, understanding, transcript
            )
        if reports.get("knowledge_graph") is not None:
            record = merge_graph(record, reports["knowledge_graph"])
        record["user_id"] = user_id
        record["updated_at"] = stamp
        record["run_count"] = int(record.get("run_count") or 0) + 1
        record = shape_record(record, domain)
        pid = str(record["project_id"])
        save_record(record_path(project_root, domain, user_id, pid), record)
        append_history(
            history_path(project_root, domain, user_id, pid),
            {
                "project_id": pid,
                "run_count": record["run_count"],
                "lines": sorted(reports.keys()),
                "subject": record.get("subject") or "",
            },
        )
        # 方案 B：同步向量索引（档案级 + 摘录级，可重建；失败不影响主流程）
        try:
            from .embed import get_embedder

            get_embedder().sync_record(user_id, domain, record)
        except Exception:  # noqa: BLE001 - 向量同步失败不阻断写回
            logger.warning("记忆向量同步异常，跳过", exc_info=True)
        logger.info(
            "记忆已更新：%s/%s 第 %s 次（%s）",
            user_id,
            pid,
            record["run_count"],
            record.get("subject") or record.get("project_key") or "—",
        )
        try:
            from tools.monitor.side import record_memory_persist

            record_memory_persist(ok=True, run_count=int(record["run_count"] or 0), project_id=pid)
        except Exception:  # noqa: BLE001
            pass
        return record
    except Exception:  # noqa: BLE001
        logger.warning("记忆写回失败，不影响主流程", exc_info=True)
        try:
            from tools.monitor.side import record_memory_persist

            record_memory_persist(ok=False)
        except Exception:  # noqa: BLE001
            pass
        return None


__all__ = ["GRAPH_LINES", "MEETING_LINES", "MEMORY_LINES", "persist", "prepare"]
