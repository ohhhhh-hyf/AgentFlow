from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from llm_client.config import load_env  # noqa: E402
from tools.cli import build_parser, collect_templates, parse_domain_name  # noqa: E402
from tools.runtime_context import load_domain  # noqa: E402
from tools.runner import run  # noqa: E402


def main() -> None:
    domain_name = parse_domain_name()
    ctx = load_domain(domain_name, PROJECT_ROOT)
    load_env(PROJECT_ROOT / ".env")
    args = build_parser(ctx).parse_args()
    templates = collect_templates(ctx, args)
    try:
        asyncio.run(
            run(
                ctx,
                args.file,
                args.profile,
                args.env,
                templates,
                args.tasks,
            )
        )
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        RuntimeError,
        ImportError,
        AttributeError,
        NameError,
    ) as exc:
        if isinstance(exc, (ImportError, AttributeError, NameError)):
            raise SystemExit(
                f"错误：领域装配不完整：{exc}\n"
                f"请先运行：python tools/scripts/sync_domain.py --domain {domain_name}"
            ) from exc
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
