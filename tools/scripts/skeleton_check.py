"""P2 离线回归：真实合并稿 → 骨架 → 三种「模型抽风」的输出 → 还原后的不变式。

不调模型、不调 OCR：用 `data/{user}/ocr/{subject}/ocr_*.md`（现在是那批 21 张照片的
合并稿）当语料，构造三类常见坏输出，验证 P2 的两条硬指标仍然成立：

  1) 覆盖 100%：骨架里每个 T/P 都在目录里（节点名或 items 里）；
  2) 顺序单调：可对齐节点的骨架 order 非递减（逆序对 0）。

    python tools/scripts/skeleton_check.py --user 1 --subject wuli

三类坏输出：漏掉开头几节（模型只建了后半段）／顺序被打乱／把某个 KP 降级进 items。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.config import load_env  # noqa: E402

load_env(ROOT / ".env")

from domain.notes.tasks.catalog.gather import order_catalog_by_source  # noqa: E402
from domain.notes.tasks.catalog.skeleton import (  # noqa: E402
    build_catalog_skeleton,
    restore_from_skeleton,
    skeleton_prompt_block,
)
from tools.scripts.check_catalog_coverage import evaluate  # noqa: E402


def skeleton_for(user: str, subject: str) -> dict:
    return build_catalog_skeleton(f"【用户ID】{user}\n【学科/课程】{subject}\n")


def _draft_from_skel(skeleton: dict, *, skip_first: int, shuffle_points: bool) -> dict:
    """按骨架造一份"模型输出"：可丢掉开头 N 个**主题**（模拟漏建）、可打乱 KP 顺序。

    P5 起骨架自带章（章来自原文），有章就沿用；无章时按每 3 个主题分一组模拟模型分组。
    空主题按合同补 1 个 KP（名字用主题名，与结构修复器的回退口径一致）。
    """
    chapters: list[dict] = []
    dropped = 0

    def topic_node(topic: dict, chapter: dict) -> dict:
        points = list(topic.get("points") or [])
        if shuffle_points and len(points) > 1:
            points = points[::-1]
        node: dict = {
            "id": f"tp_{len(chapter['topics']) + 1:03d}",
            "name": topic["name"],
            "knowledge_points": [],
        }
        if not points:
            node["knowledge_points"].append(
                {"id": "kp_001", "name": topic["name"], "knowledge_items": []}
            )
        for idx, point in enumerate(points, start=1):
            node["knowledge_points"].append(
                {
                    "id": f"kp_{idx:03d}",
                    "name": point["name"],
                    "knowledge_items": [],
                    "importance": "3",
                }
            )
        return node

    if skeleton.get("chapters"):
        for chapter in skeleton["chapters"]:
            node = {
                "id": f"ch_{len(chapters) + 1:03d}",
                "name": chapter["name"],
                "topics": [],
            }
            for topic in chapter.get("topics") or []:
                if dropped < skip_first:
                    dropped += 1
                    continue
                node["topics"].append(topic_node(topic, node))
            chapters.append(node)
        return {"course": "wuli", "chapters": chapters}

    current: dict | None = None
    for idx, topic in enumerate(skeleton["topics"], start=1):
        if dropped < skip_first:
            dropped += 1
            continue
        if current is None or (idx - skip_first) % 3 == 1:
            current = {
                "id": f"ch_{len(chapters) + 1:03d}",
                "name": f"分组{len(chapters) + 1}",
                "topics": [],
            }
            chapters.append(current)
        current["topics"].append(topic_node(topic, current))
    return {"course": "wuli", "chapters": chapters}


def _demote_case(skeleton: dict) -> dict:
    """把骨架第二个主题的第一个 KP 降级进 items（合法的"合并"操作）。"""
    draft = _draft_from_skel(skeleton, skip_first=0, shuffle_points=False)
    for chapter in draft["chapters"]:
        for topic in chapter["topics"]:
            if topic["knowledge_points"]:
                victim = topic["knowledge_points"][0]
                topic["knowledge_points"] = topic["knowledge_points"][1:]
                topic["knowledge_items"] = [victim["name"]]
                return draft
    return draft


def run_case(name: str, skeleton: dict, draft: dict, ctx: str) -> bool:
    before = evaluate(skeleton, draft)
    restored, report = restore_from_skeleton(copy.deepcopy(draft), skeleton)
    ordered = order_catalog_by_source(restored, ctx)
    after = evaluate(skeleton, ordered)
    print(f"\n=== {name}")
    print(f"  还原前: 覆盖 {100 * before['coverage']:.1f}% 同级乱序 {len(before['level_violations'])} 处")
    print(f"  还原后: 覆盖 {100 * after['coverage']:.1f}% 同级乱序 {len(after['level_violations'])} 处"
          f"（补主题 {len(report['restored_topics'])} / 补知识点 {len(report['restored_points'])}"
          f" / 降级保留 {len(report['demoted_kept'])} / 合并 {len(report['merged_topics'])}）")
    if after["cross_jumps"]:
        print(f"  跨层回退 {len(after['cross_jumps'])} 处（信息性，续页合并等原文结构所致）")
    if not after["ok"]:
        print(f"  未通过：缺主题={after['uncovered_topics'][:5]} 缺KP={after['uncovered_points'][:5]}"
              f" 乱序={after['level_violations'][:3]}")
    return after["ok"]


def main() -> int:
    ap = argparse.ArgumentParser(description="P2 骨架离线回归")
    ap.add_argument("--user", required=True)
    ap.add_argument("--subject", required=True)
    args = ap.parse_args()
    ctx = f"【用户ID】{args.user}\n【学科/课程】{args.subject}\n"
    skeleton = skeleton_for(args.user, args.subject)
    if not skeleton.get("topics"):
        print("骨架为空：请检查 data/{user}/ocr/{subject}/ocr_*.md")
        return 2
    print(f"骨架：{len(skeleton['topics'])} 主题 / {skeleton['stats']['points']} 知识点"
          f"，细碎标题忽略 {skeleton['stats']['dropped_item_headings']} 个"
          f"（来源 {skeleton['source']}）")
    prompt = skeleton_prompt_block(skeleton)
    print(f"prompt 骨架段长度：{len(prompt)} 字符")

    cases = [
        ("模型漏掉开头三节", _draft_from_skel(skeleton, skip_first=3, shuffle_points=False)),
        ("模型只建后半段", _draft_from_skel(skeleton, skip_first=max(1, len(skeleton["topics"]) // 2),
                                            shuffle_points=False)),
        ("模型打乱 KP 顺序", _draft_from_skel(skeleton, skip_first=0, shuffle_points=True)),
        ("模型把 KP 降级进 items", _demote_case(skeleton)),
        ("模型输出全缺（只剩一个空章）", {"course": "wuli", "chapters": [{"id": "ch_001", "name": "全章", "topics": [{"id": "tp_001", "name": "占位", "knowledge_points": [{"id": "kp_001", "name": "占位", "importance": "1"}]}]}]}),
    ]
    results = [run_case(name, skeleton, draft, ctx) for name, draft in cases]
    print()
    print("=" * 60)
    print(f"通过 {sum(results)}/{len(results)} 项（覆盖 100% + 顺序单调）")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
