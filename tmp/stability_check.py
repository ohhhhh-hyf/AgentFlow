# -*- coding: utf-8 -*-
"""稳定性验收脚本：同一输入跑两次，对比各层输出一致性。

用法（项目根目录下）：
    python tmp\\stability_check.py

覆盖：meeting 域（会议理解 / 纪要 / 待办 / 风险）+ notes 域（笔记理解 / 知识点）。
ratio >= 0.85 视为稳定；< 0.70 说明波动明显，需要调 prompt。

临时验收脚本，不进入正式代码。
"""
from __future__ import annotations

import asyncio
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from llm_client import LLMClient  # noqa: E402
from domain.meeting.meeting_core import MeetingUnderstandingAgent  # noqa: E402
from domain.meeting.models import UserIdentity  # noqa: E402
from domain.meeting.orchestrator import MeetingAgentSystem  # noqa: E402
from domain.notes.notes_core import NotesUnderstandingAgent  # noqa: E402
from domain.notes.orchestrator import NotesAgentSystem  # noqa: E402

SUMMARY = ROOT / "domain/meeting/samples/summary/meeting_all.txt"
PROFILE = ROOT / "domain/meeting/samples/profile/object_profile.json"
NOTE = ROOT / "domain/notes/samples/note.txt"


def ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def pct_diff(a: str, b: str) -> float:
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 0.0
    return abs(la - lb) / max(la, lb) * 100


async def run_line_twice(client, system_cls, transcript, user, line, text_attr, list_attr):
    """通用：跑一条线两次，返回 (渲染文本两次, 结构化列表 JSON 两次)。"""
    system = system_cls(client=client)
    texts, lists = [], []
    for _ in range(2):
        async for event in system.run_streaming(transcript, user, lines=[line]):
            if event["type"] == "done":
                rep = event["reports"][line]
                texts.append(getattr(rep, text_attr, None) or "")
                lists.append(
                    json.dumps(getattr(rep, list_attr, None) or [], ensure_ascii=False, sort_keys=True)
                )
    return texts[0], texts[1], lists[0], lists[1]


async def main() -> None:
    transcript = SUMMARY.read_text(encoding="utf-8").strip()
    note = NOTE.read_text(encoding="utf-8").strip()
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    user = UserIdentity(**profile)
    client = LLMClient()

    print("=" * 60)
    print("稳定性验收：同一输入跑两次（temperature=0.0）")
    print("=" * 60)

    # ── meeting 域 ─────────────────────────────────────────────
    print("\n[meeting 域] 输入：meeting_all.txt（%d 字）" % len(transcript))

    print("  [1/7] 会议理解层（meeting_core）...")
    agent = MeetingUnderstandingAgent(client)
    u1 = json.dumps((await agent.run(transcript)).model_dump(), ensure_ascii=False)
    u2 = json.dumps((await agent.run(transcript)).model_dump(), ensure_ascii=False)

    print("  [2/7] 纪要正文（minutes_generation）...")
    m1, m2, _, _ = await run_line_twice(
        client, MeetingAgentSystem, transcript, user, "minutes_generation",
        "personalized_minutes", "key_decisions",
    )

    print("  [3/7] 待办（action_items）...")
    a1, a2, al1, al2 = await run_line_twice(
        client, MeetingAgentSystem, transcript, user, "action_items",
        "personalized_text", "action_items",
    )

    print("  [4/7] 风险（risk）...")
    r1, r2, rl1, rl2 = await run_line_twice(
        client, MeetingAgentSystem, transcript, user, "risk",
        "personalized_text", "risks",
    )

    # ── notes 域 ───────────────────────────────────────────────
    print("\n[notes 域] 输入：note.txt（%d 字）" % len(note))

    print("  [5/7] 笔记理解层（notes_core）...")
    nagent = NotesUnderstandingAgent(client)
    n1 = json.dumps((await nagent.run(note)).model_dump(), ensure_ascii=False)
    n2 = json.dumps((await nagent.run(note)).model_dump(), ensure_ascii=False)

    print("  [6/7] 知识点列表（points structure）...")
    print("  [7/7] 知识点渲染（points rendered）...")
    p1, p2, pl1, pl2 = await run_line_twice(
        client, NotesAgentSystem, note, None, "points",
        "personalized_text", "points",
    )

    # ── 汇总 ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    items = (
        ("meeting 会议理解", ratio(u1, u2)),
        ("meeting 纪要正文", ratio(m1, m2)),
        ("meeting 待办渲染", ratio(a1, a2)),
        ("meeting 待办列表", ratio(al1, al2)),
        ("meeting 风险渲染", ratio(r1, r2)),
        ("meeting 风险列表", ratio(rl1, rl2)),
        ("notes 笔记理解", ratio(n1, n2)),
        ("notes 知识点列表", ratio(pl1, pl2)),
        ("notes 知识点渲染", ratio(p1, p2)),
    )
    for label, r in items:
        if r >= 0.85:
            print(f"  ✓ {label}：稳定（ratio={r:.2f}）")
        elif r >= 0.70:
            print(f"  ⚠ {label}：基本稳定但建议观察（ratio={r:.2f}）")
        else:
            print(f"  ✗ {label}：波动明显（ratio={r:.2f}），需要调 prompt")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
