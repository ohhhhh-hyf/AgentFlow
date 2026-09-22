"""``python -m tests`` —— 跑全部零 LLM 自测套件，汇总一行结果。

为什么有这个入口：套件分散在四个子系统（core / template_router / meeting_memory /
perspective），改动 cross-cutting 的东西时要跑四遍；这里给一个命令、一个退出码。
单个套件仍可单独跑（``python -m tests.test_core``），排查问题时更省事。
"""
from __future__ import annotations

import importlib
import sys

SUITES = (
    "tests.test_core",
    "tests.test_template_router",
    "tests.test_meeting_memory",
    "tests.test_perspective",
    "tests.test_draft_scrape",
    "tests.test_engine_smoke",
)


def main() -> int:
    failed: list[str] = []
    for name in SUITES:
        module = importlib.import_module(name)
        code = int(module.main())
        print(f"-- {name}: {'OK' if code == 0 else 'FAIL'}")
        if code:
            failed.append(name)
    print()
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"ALL PASS（{len(SUITES)} 个套件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
