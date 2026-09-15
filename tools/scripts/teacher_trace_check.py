"""对拍：老师重点在场时，P1 新增的两处保序是否影响 溯源/重要性/老师重点 回填。

跑两遍 display 侧流水线：
  A = 现行（补缺 → 保序 → 规模合并 → 保序 → 溯源回填 → 粒度合并 → 关联校准 → 信号计算）
  B = 旧行为（去掉两处保序）
逐 KP 比较 teacher_emphasis / teacher_focus_items / teacher_evidence / sources /
source_chunk_ids / evidence / importance / exam_signal / review_weight。
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["KNOWLEDGE_FAKE"] = "1"

import domain.notes.tasks.catalog.gather as gather  # noqa: E402

TEACHER = "今天强调：厄米算符本征态的正交性必考，证明要会；另外算符对易式是重点。"
SCOPE = "【用户ID】__selftest__\n【学科/课程】wuli\n"
CTX = SCOPE + f"【老师重点】\n{TEACHER}\n"


class FakeKB:
    def __init__(self, rows):
        self._rows = rows

    def list_chunks(self, **_kw):
        return [{"text": r.get("text", ""), "metadata": dict(r)} for r in self._rows]

    def list_files(self, **_kw):
        return ["ocr_20990101_000000.md"]


def rows():
    src = "ocr_20990101_000000.md"

    def row(heading, chapter, topic, text, ci, score, kind):
        return {
            "source": src, "chapter": chapter, "topic": topic, "heading": heading,
            "heading_path_text": f"{chapter} / {topic} / {heading}" if topic else heading,
            "page": "", "chunk_index": f"{ci}-0", "heading_score": str(score),
            "heading_kind": kind, "content_tags": "theorem", "contains_formula": "0",
            "role": "notes", "text": text, "content_fingerprint": f"fp{ci}",
        }

    return [
        row("厄米算符本征态的正交性", "厄米算符本征值与本征态的特性", "正交性与完备性",
            "厄米算符属于不同本征值的本征态必然正交，这是厄米算符本征态的正交性。", 0, 7, "knowledge_point"),
        row("幂级数解法", "一维谐振子", "核心知识点",
            "用幂级数解法构造递推关系，得到厄米多项式解。", 9, 5, "knowledge_point"),
        row("一维束缚态", "一维束缚态", "", "一维定态薛定谔方程与波函数连续性条件。", 20, 3, "evidence"),
    ]


def draft():
    return {
        "course": "wuli",
        "chapters": [
            {
                "id": "ch_001",
                "name": "厄米算符本征值与本征态的特性",
                "topics": [{
                    "id": "tp_001",
                    "name": "正交性与完备性",
                    "knowledge_points": [{
                        "id": "kp_001",
                        "name": "厄米算符本征态的正交性",
                        "knowledge_type": "theorem",
                        "knowledge_items": ["不同本征值的本征态正交", "连续谱用 δ 函数正交归一"],
                        "importance": "4",
                        "difficulty": "3",
                    }],
                }],
            },
            {
                "id": "ch_002",
                "name": "一维谐振子",
                "topics": [{
                    "id": "tp_002",
                    "name": "核心知识点",
                    "knowledge_points": [{
                        "id": "kp_002",
                        "name": "幂级数解法",
                        "knowledge_type": "method",
                        "knowledge_items": ["构造递推关系"],
                        "importance": "3",
                        "difficulty": "4",
                    }],
                }],
            },
        ],
    }


FIELDS = (
    "teacher_emphasis", "teacher_focus_items", "teacher_evidence",
    "sources", "source_chunk_ids", "evidence", "content_fingerprint",
    "importance", "exam_signal", "review_weight", "difficulty", "knowledge_items",
)


def flatten(cat):
    out = {}
    for ch in cat.get("chapters") or []:
        for tp in ch.get("topics") or []:
            for kp in tp.get("knowledge_points") or []:
                out[str(kp.get("name"))] = {f: kp.get(f) for f in FIELDS}
    return out


def run(with_order: bool):
    cat = copy.deepcopy(draft())
    cat = gather.complement_catalog_coverage(cat, CTX)
    if with_order:
        cat = gather.order_catalog_by_source(cat, CTX)
    cat = gather.trim_catalog_scale(cat, CTX)
    if with_order:
        cat = gather.order_catalog_by_source(cat, CTX)
    cat = gather.backfill_catalog_trace(cat, CTX)
    from domain.notes.tasks.catalog.merge import compact_catalog_granularity

    cat = compact_catalog_granularity(cat)
    cat = gather.calibrate_catalog_relations(cat)
    cat = gather.compute_catalog_signals(cat)
    return cat


def main() -> int:
    original = gather.open_knowledge
    gather.open_knowledge = lambda user_id="": FakeKB(rows())
    try:
        a, b = run(True), run(False)
    finally:
        gather.open_knowledge = original

    fa, fb = flatten(a), flatten(b)
    print("A（现行）章序:", [c.get("name") for c in a.get("chapters") or []])
    print("B（旧行为）章序:", [c.get("name") for c in b.get("chapters") or []])
    print(f"\nKP 集合一致: {set(fa) == set(fb)}  A={sorted(fa)}")

    same = True
    for name in sorted(set(fa) | set(fb)):
        print(f"\n--- {name}")
        for field in FIELDS:
            va, vb = fa.get(name, {}).get(field), fb.get(name, {}).get(field)
            flag = "  " if va == vb else "≠≠"
            if va != vb:
                same = False
            print(f"  {flag} {field}: A={va!r}")
            if va != vb:
                print(f"                     B={vb!r}")
    print("\n逐字段一致:", same)

    kp1 = fa.get("厄米算符本征态的正交性", {})
    print("\n老师重点是否生效:")
    print("  teacher_emphasis =", kp1.get("teacher_emphasis"))
    print("  teacher_focus_items =", kp1.get("teacher_focus_items"))
    print("  teacher_evidence =", kp1.get("teacher_evidence"))
    print("  溯源 sources =", kp1.get("sources"), "evidence =", str(kp1.get("evidence"))[:60])
    print("  importance =", kp1.get("importance"), " exam_signal =", kp1.get("exam_signal"))
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
