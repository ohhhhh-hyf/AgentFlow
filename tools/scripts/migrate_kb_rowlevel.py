"""迁移存量知识库到「单库 + 行级」模型。

旧模型：collection 名 = ``{user_id}__{subject}``（如 ``1__math``，L2 空间）。
新模型：统一 collection ``knowledge``（cosine 空间），chunk metadata 补
``owner=user_id`` / ``subject=subject``，检索按 where 行级过滤。

做法：
1. 枚举旧 collection，从名字解析 (user_id, subject)；
2. 读出每个 collection 的 文档/向量/metadata（向量直接复用，不重编码）；
3. 写入统一 ``knowledge`` collection（cosine 空间），metadata 补 owner/subject；
4. 校验写入条数后删除旧 collection（默认 --keep 保留旧库不删）。

用法：python tools/scripts/migrate_kb_rowlevel.py [--keep]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llm_client.config import load_env  # noqa: E402

load_env(ROOT / ".env")

from tools.knowledge.config import KnowledgeToolConfig  # noqa: E402
from tools.knowledge.vector_store import VectorStore  # noqa: E402
from tools.knowledge.tool import KB_COLLECTION  # noqa: E402


def parse_legacy_name(name: str) -> tuple[str, str]:
    """旧 collection 名 ``{user_id}__{subject}`` → (user_id, subject)。"""
    if "__" in name:
        uid, subj = name.split("__", 1)
        return uid.strip(), subj.strip()
    return "", name


def migrate(store: VectorStore, keep: bool = False) -> None:
    store.client.get_or_create_collection(
        KB_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    target = store.client.get_collection(store._internal(KB_COLLECTION))
    migrated = 0
    legacy = store.list_collections()
    for item in legacy:
        name = item["name"]
        if name == KB_COLLECTION or name.startswith("c_"):
            continue
        user_id, subject = parse_legacy_name(name)
        source_coll = store.client.get_collection(store._internal(name))
        got = source_coll.get(include=["embeddings", "documents", "metadatas"])
        ids = got.get("ids") or []
        if not ids:
            print(f"[跳过] {name}: 无数据")
            continue
        metas = []
        for meta in got.get("metadatas") or []:
            m = dict(meta or {})
            if user_id:
                m["owner"] = user_id
            if subject:
                m["subject"] = subject
            metas.append(m)
        target.upsert(
            ids=ids,
            embeddings=got.get("embeddings"),
            documents=got.get("documents"),
            metadatas=metas,
        )
        count = target.count()
        print(f"[迁移] {name} → {KB_COLLECTION}（owner={user_id or '—'}, "
              f"subject={subject or '—'}）: {len(ids)} 条, 目标库现有 {count} 条")
        migrated += len(ids)
        if not keep:
            try:
                store.client.delete_collection(store._internal(name))
                print(f"[删除] 旧 collection {name}")
            except Exception as exc:  # noqa: BLE001
                print(f"[警告] 删除 {name} 失败: {exc}")
    print(f"完成：共迁移 {migrated} 条到统一库 {KB_COLLECTION}（当前总数 {target.count()}）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留旧 collection 不删除")
    args = ap.parse_args()
    store = VectorStore(KnowledgeToolConfig())
    migrate(store, keep=args.keep)


if __name__ == "__main__":
    main()
