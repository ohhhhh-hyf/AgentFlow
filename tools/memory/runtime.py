"""给 runner 用的注入 / 回写门面（会议域记忆已迁移到 tools.meeting_memory）。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .graph import inject_graph, merge_graph
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

GRAPH_LINES = frozenset({"graph"})
MEMORY_LINES = GRAPH_LINES


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
    """解析归属并生成各线注入文本（当前仅 notes.graph）。失败返回空注入，不抛。"""
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
        rec = None
        if bind.project_id:
            rec = materialize(project_root, domain, user_id, bind)
        extra: dict[str, str] = {}
        if rec:
            graph_text = inject_graph(rec)
            for line in line_names:
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
    """把本次产出写入同一 bind（当前仅 notes.graph）。未绑定且不应新建则跳过。"""
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
        stamp = now_stamp()
        if (domain or "").strip() == "notes":
            label = (subject or bind.project_key or "").strip()
            record = merge_notes(record, understanding, stamp, label)
        if reports.get("graph") is not None:
            record = merge_graph(record, reports["graph"])
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

            get_embedder(user_id=user_id).sync_record(user_id, domain, record)
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


__all__ = ["GRAPH_LINES", "MEMORY_LINES", "persist", "prepare"]
