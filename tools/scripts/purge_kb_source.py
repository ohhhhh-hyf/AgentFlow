"""按来源文件清掉知识库中的旧知识块（用于被污染的 OCR 合并稿"代际替换"）。

场景：旧的 OCR 合并稿（如把校名页眉识别成正文的那一版）已入库，重新 OCR 后文件名为
新的时间戳，旧块不会被自动清理，而 catalog 的 briefing 正是从知识库取块的——旧块不清，
目录里的假章节就会反复出现。

    # 先看这个用户/学科库里有哪些来源
    python tools/scripts/purge_kb_source.py --user 1 --subject 物理 --list

    # 只删某个来源（文件名，含扩展名）
    python tools/scripts/purge_kb_source.py --user 1 --subject 物理 --source ocr_20260915_152054.md

    # 删除该学科下全部 ocr_ 合并稿（旧批次一起换掉）
    python tools/scripts/purge_kb_source.py --user 1 --subject 物理 --source "ocr_*"

不带 --source 时只做 --list 的展示，不会删除任何东西。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.config import load_env  # noqa: E402

load_env(ROOT / ".env")

from domain.notes.tasks.library.report import kb_from_env  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="按来源清知识库块")
    ap.add_argument("--user", default="", help="user_id（与接口 X-User-Id 一致）")
    ap.add_argument("--subject", default="", help="学科（学科拼音，如 wuli/物理）")
    ap.add_argument("--collection", default="default")
    ap.add_argument("--source", default="", help="文件名或通配（如 'ocr_*'）；不传则只列清单")
    ap.add_argument("--list", dest="list_only", action="store_true", help="只列出来源与块数，不删除")
    args = ap.parse_args()

    kb = kb_from_env(args.user)
    sources = kb.list_files(collection=args.collection, user_id=args.user, subject=args.subject)
    print(f"范围 user={args.user!r} subject={args.subject!r} 来源文件数={len(sources)}")
    for name in sources:
        chunks = kb.list_chunks(
            collection=args.collection,
            filename=name,
            user_id=args.user,
            subject=args.subject,
            with_metadata=True,
            with_text=False,
        )
        print(f"  - {name}  块={len(chunks)}")
    if not args.source or args.list_only:
        print("\n仅展示（未删除）。指定 --source 才会清理。")
        return 0

    from fnmatch import fnmatch

    targets = [name for name in sources if fnmatch(name, args.source) or name == args.source]
    if not targets:
        print(f"\n没有匹配 {args.source!r} 的来源，未做删除。")
        return 1
    print(f"\n将删除 {len(targets)} 个来源：{targets}")
    removed = kb.delete_sources(
        targets, collection=args.collection, user_id=args.user, subject=args.subject
    )
    print(f"已删除知识块 {removed} 个。")
    after = kb.list_files(collection=args.collection, user_id=args.user, subject=args.subject)
    print(f"删除后来源文件数={len(after)}，剩余：{after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
