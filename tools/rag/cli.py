"""Command line utilities for the standalone RAG component."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env

from tools.rag.config import resolve_rag_settings
from tools.rag.ingest import ingest_default, ingest_path
from tools.rag.retriever import retrieve_context


def _project_root() -> Path:
    return PROJECT_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentFlow local RAG tools")
    parser.add_argument("--env", type=Path, default=Path(".env"), help="环境变量文件")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="读取资料并写入本地 RAG 索引")
    ingest.add_argument("--domain", required=True, help="领域名，如 meeting / notes")
    ingest.add_argument("--task", required=True, help="任务线，如 risk / knowledge_graph")
    ingest.add_argument(
        "--source",
        type=Path,
        default=None,
        help="资料文件或目录；不传时读取 samples/{domain}/rag/{task} 或 samples/{domain}/rag",
    )

    search = sub.add_parser("search", help="检索本地 RAG 索引")
    search.add_argument("--domain", required=True, help="领域名，如 meeting / notes")
    search.add_argument("--task", required=True, help="任务线，如 risk / knowledge_graph")
    search.add_argument("--query", required=True, help="检索问题")
    search.add_argument("--top-k", type=int, default=None, help="返回条数")
    search.add_argument("--json", action="store_true", help="以 JSON 输出")
    return parser


def _resolve_source(path: Path, root: Path) -> Path:
    if path.is_absolute():
        return path
    return (root / path).resolve()


def main() -> int:
    root = _project_root()
    parser = build_parser()
    args = parser.parse_args()
    load_env(_resolve_source(args.env, root))
    settings = resolve_rag_settings(root)

    if args.command == "ingest":
        if args.source:
            result = ingest_path(
                _resolve_source(args.source, root),
                args.domain,
                args.task,
                settings,
            )
        else:
            result = ingest_default(args.domain, args.task, settings)
        print("[RAG] 入库完成")
        print(f"- mode: {result['mode']}")
        print(f"- source: {result['source_path']}")
        print(f"- store: {result['store_path']}")
        print(f"- documents: {result['document_count']}")
        print(f"- chunks: {result['chunk_count']}")
        return 0

    if args.command == "search":
        result = retrieve_context(
            args.domain,
            args.task,
            args.query,
            settings,
            top_k=args.top_k,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        matches = result["matches"]
        if not matches:
            print("[RAG] 未检索到相关片段")
            return 0
        print(f"[RAG] 检索到 {len(matches)} 个相关片段")
        for item in matches:
            text = item["text"].replace("\n", " ")
            preview = text[:180] + ("..." if len(text) > 180 else "")
            print(
                f"{item['rank']}. score={item['score']:.4f} "
                f"source={item['source']} chunk={item['id']}"
            )
            print(f"   {preview}")
        return 0

    parser.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
