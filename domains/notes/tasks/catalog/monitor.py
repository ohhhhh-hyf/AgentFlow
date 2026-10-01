"""domains.notes.tasks.catalog.monitor —— 知识库目录质量监视与伪标题自检。"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def fake_heading_chunk_count(user_id: str, subject: str) -> int:
    """入库自检：知识库里有多少块的 heading 是"句子型伪标题"（正文被误判成标题）。

    只看形态（长度 > 24 或含逗号/句号），不看内容——它是入库标题识别的回归哨兵：
    `③ …` 经 NFKC 变 `3 …` 后曾被当成章级标题，顺着候选池长成目录里的假章节。
    """
    try:
        try:
            from domains.notes.tasks.catalog.gather import open_knowledge
        except ImportError:
            from domains.notes.tasks.catalog.gather import open_knowledge

        kb = open_knowledge(user_id=user_id)
        if kb is None:
            return 0
        chunks = kb.list_chunks(user_id=user_id, subject=subject, with_text=False) or []
    except Exception:  # noqa: BLE001 - 统计失败不影响结果
        return 0
    fake = 0
    for chunk in chunks:
        heading = str((chunk.get("metadata") or {}).get("heading") or "")
        if heading and (len(heading) > 24 or any(ch in heading for ch in "，。；,;")):
            fake += 1
    return fake


def catalog_quality_monitor(user_id: str, subject: str) -> dict[str, Any]:
    """目录体检报告：每次 catalog run 完后，如果产生了 draft，

    读刚存下的目录 json + 原文骨架算指标（零 LLM），让你一眼验收而不是读整棵树；
    任何异常都只丢指标、不影响目录结果本身。
    """
    try:
        try:
            from domains.notes.tasks.catalog.skeleton import (
                build_source_skeleton,
                catalog_quality_report,
            )
            from domains.notes.tasks.catalog.store import load_catalog
        except ImportError:
            from domains.notes.tasks.catalog.skeleton import (
                build_source_skeleton,
                catalog_quality_report,
            )
            from domains.notes.tasks.catalog.store import load_catalog

        draft = load_catalog(user_id=user_id, subject=subject)
        if not draft:
            return {}
        scope = ""
        if str(user_id or "").strip():
            scope += f"【用户ID】{str(user_id).strip()}\n"
        if str(subject or "").strip():
            scope += f"【学科/课程】{str(subject).strip()}\n"
        skeleton = build_source_skeleton(scope)
        if not skeleton.get("topics"):
            return {}
        metrics = catalog_quality_report(skeleton, draft)["metrics"]
        metrics["skeleton_kind"] = str(skeleton.get("kind") or "md")
        metrics["fake_heading_chunks"] = fake_heading_chunk_count(user_id, subject)
        return {"catalog": metrics}
    except Exception:  # noqa: BLE001 - 体检失败不影响任务结果
        logger.warning("catalog quality monitor failed", exc_info=True)
        return {}
