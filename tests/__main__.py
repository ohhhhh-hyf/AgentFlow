"""``python -m tests`` —— 运行全量测试套件（支持参数透传）。"""
from __future__ import annotations

import sys
import pytest


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        args = ["tests", "-q"]
    return int(pytest.main(args))


if __name__ == "__main__":
    sys.exit(main())
