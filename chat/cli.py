# -*- coding: utf-8 -*-
"""终端入口：交互式知识问答。

用法::

    python -m chat.cli --user 1 --subject math

进入后连续提问；输入 ``exit`` / ``quit`` / ``q`` 退出，空行跳过。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_client.config import load_env  # noqa: E402

from .chat import ChatSession  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="知识库/记忆多源检索问答（终端）")
    parser.add_argument("--user", default="1", help="用户 ID（必填，决定知识库与记忆范围）")
    parser.add_argument("--subject", default="", help="学科（可选，只约束笔记/资料知识库；会议记忆按用户全量）")
    parser.add_argument("--history", type=int, default=8, help="保留的对话轮数（默认 8）")
    parser.add_argument("--session", default="", help="会话 ID（默认新建；传已有 ID 可恢复历史与已知用户信息）")
    parser.add_argument("--env", default=str(ROOT / ".env"), help=".env 文件路径")
    return parser.parse_args()


async def _amain(args: argparse.Namespace) -> int:
    load_env(Path(args.env))
    session = ChatSession(
        args.user, args.subject, session_id=args.session or None,
        history_limit=args.history,
    )
    scope = f"用户 {args.user}" + (f" · 学科 {args.subject}" if args.subject else "")
    if args.session:
        print(f"已回到之前会话，可继续使用 🤪")
    else:
        print(f"知识问答已就绪（{scope}）会话 {session.session_id}。输入问题开始，exit 退出。")
    print("-" * 60)
    while True:
        try:
            line = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            return 0
        if not line:
            continue
        if line.lower() in {"exit", "quit", "q"}:
            print("再见。")
            return 0
        try:
            result = await session.ask(line)
        except Exception as exc:  # noqa: BLE001
            print(f"(回答失败：{type(exc).__name__}: {exc})")
            continue
        print("🤖:", result["answer"])
        if result["sources"]:
            seen: list[str] = []
            for s in result["sources"]:
                if s and s not in seen:
                    seen.append(s)
            print("  [来源]", "；".join(seen))
        print("-" * 60)


def main() -> int:
    # 终端输入容错：SSH 客户端（Xshell/Putty 等）默认 GBK 编码时，Python 3.10
    # 按 UTF-8 解码 stdin 会抛 UnicodeDecodeError——改用 replace 兜底（乱码不崩）
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 不支持 reconfigure 的 stdin（如管道）
        pass
    args = _parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
