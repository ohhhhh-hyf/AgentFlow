# -*- coding: utf-8 -*-
"""意图识别 Agent —— 终端入口。

    python -m intent_agent.cli "把ocr_file里的图片识别后入库到数学"
    python -m intent_agent.cli "帮我出数学的复习清单" --user_id 1
    python -m intent_agent.cli "先识别会议录音纪要，再列行动项" --project P1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intent_agent import parse  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="意图识别：一句话 → 任务 Plan")
    parser.add_argument("text", help="用户的一句话")
    parser.add_argument("--user_id", default="", help="默认用户 ID（上下文兜底）")
    parser.add_argument("--user", default="", help="默认用户（chat 用，别名 user_id）")
    parser.add_argument("--subject", default="", help="默认学科")
    parser.add_argument("--project", default="", help="默认项目 ID")
    parser.add_argument("--env", default=str(ROOT / ".env"), help=".env 路径")
    args = parser.parse_args()

    ctx_params = {
        "user_id": args.user_id or args.user,
        "user": args.user or args.user_id,
        "subject": args.subject,
        "project": args.project,
    }
    ctx_text = "\n".join(f"{k}={v}" for k, v in ctx_params.items() if v)

    plan = parse(args.text, context=ctx_text, ctx_params=ctx_params)
    data = plan.to_dict()

    print("=" * 56)
    print("整体解释:", data["explanation"])
    print()
    for i, item in enumerate(data["plan"], 1):
        print(f"[{i}] {item['task']}（{item['domain']}）")
        if item["note"]:
            print(f"    说明: {item['note']}")
        if item["params"]:
            print(f"    参数: {item['params']}")
        if item["missing"]:
            print(f"    ⚠ 缺: {item['missing']}（需要用户补全/上传）")
        if item["needs"]:
            print(f"    依赖: 先做 {item['needs']}")
    print()
    groups = data.get("execution") or []
    if groups:
        seq = []
        for g in groups:
            if len(g) > 1:
                seq.append("‖".join(g))  # 并行
            else:
                seq.append(g[0])
        print("执行顺序:", " → ".join(seq))
        for g in groups:
            if len(g) > 1:
                print(f"  并行: {g} 无相互依赖，可同时执行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
