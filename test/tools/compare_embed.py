# -*- coding: utf-8 -*-
"""语义评测：参考待办（test/daiban） vs 运行结果（--results-dir，默认 test/output）。

匹配用 EmbeddingClient 余弦相似度（阈值 --thr，默认 0.70）。
输出：控制台汇总 + <results_dir>/compare_embed.md 详细报告。
用法：py compare_embed.py [--results-dir test/output_v2] [--thr 0.7]
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, r"D:\study\AgentFlow")

ROOT = Path(r"D:\study\AgentFlow")
DAIBAN_DIR = ROOT / "test" / "daiban"

EMPTY_MARKS = ("未产生明确待办", "无待办")


def parse_daiban(text: str) -> list[str]:
    items = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("###"):
            continue
        if any(m in s for m in EMPTY_MARKS):
            return []
        if s.startswith("- ") or s.startswith("* "):
            items.append(s[2:].strip())
    return items


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="test/output")
    ap.add_argument("--thr", type=float, default=0.70)
    ap.add_argument("--only", type=int, default=0, help="只评测指定序号（0=全部）")
    args = ap.parse_args()

    from llm_client.config import load_env  # noqa: E402

    load_env(ROOT / ".env")
    from tools.knowledge.config import KnowledgeToolConfig  # noqa: E402
    from tools.knowledge.vector_store import EmbeddingClient  # noqa: E402

    emb = EmbeddingClient(KnowledgeToolConfig())

    out_dir = ROOT / args.results_dir
    idxs = [args.only] if args.only else range(1, 34)

    # 收集所有待匹配文本
    rows = []
    texts: list[str] = []
    text_owner: list[tuple[int, str, int]] = []  # (row_idx, side, item_idx)
    for idx in idxs:
        daiban_path = DAIBAN_DIR / f"daiban_{idx:02d}.txt"
        result_path = out_dir / f"result_{idx:02d}.json"
        ref = (
            parse_daiban(daiban_path.read_text(encoding="utf-8"))
            if daiban_path.exists()
            else []
        )
        new_tasks: list[str] = []
        if result_path.exists():
            data = json.loads(result_path.read_text(encoding="utf-8"))
            new_tasks = [it.get("task") or "" for it in data.get("action_items") or []]
        rows.append({"idx": idx, "ref": ref, "new": new_tasks})
        row_pos = len(rows) - 1
        for i, t in enumerate(ref):
            if t.strip():
                text_owner.append((rows[row_pos]["idx"], "ref", i))
                texts.append(t)
        for j, t in enumerate(new_tasks):
            if t.strip():
                text_owner.append((rows[row_pos]["idx"], "new", j))
                texts.append(t)

    print(f"共 {len(texts)} 条文本待嵌入，分批计算...")
    vecs = emb.embed(texts)
    vec_of = {(r, s, i): v for (r, s, i), v in zip(text_owner, vecs)}

    # 逐会议匹配
    thr = args.thr
    for r in rows:
        ref_vecs = [vec_of[(r["idx"], "ref", i)] for i in range(len(r["ref"]))]
        new_vecs = [vec_of[(r["idx"], "new", j)] for j in range(len(r["new"]))]
        matched_ref: set[int] = set()
        matched_new: set[int] = set()
        pairs: list[tuple[int, int, float]] = []
        for i, rv in enumerate(ref_vecs):
            best_j, best_s = -1, 0.0
            for j, nv in enumerate(new_vecs):
                s = cos(rv, nv)
                if s > best_s:
                    best_j, best_s = j, s
            if best_j >= 0 and best_s >= thr:
                pairs.append((i, best_j, best_s))
                matched_ref.add(i)
                matched_new.add(best_j)
        r["pairs"] = pairs
        r["ref_matched"] = len(matched_ref)
        r["new_matched"] = len(matched_new)

    # 汇总
    total_ref = sum(len(r["ref"]) for r in rows)
    total_new = sum(len(r["new"]) for r in rows)
    total_ref_matched = sum(r["ref_matched"] for r in rows)
    recall = total_ref_matched / total_ref if total_ref else 0.0
    precision = total_ref_matched / total_new if total_new else 0.0
    both_empty = sum(1 for r in rows if not r["ref"] and not r["new"])
    ref_empty_new_not = sum(1 for r in rows if not r["ref"] and r["new"])
    ref_not_new_empty = sum(1 for r in rows if r["ref"] and not r["new"])
    print("======== 语义匹配汇总（cos>=%.2f）========" % thr)
    print(f"结果目录: {args.results_dir}")
    print(f"参考待办总条数: {total_ref}   本次待办总条数: {total_new}")
    print(f"参考被本次覆盖: {total_ref_matched}")
    print(f"参考召回率: {recall:.1%}    本次精确率(相对参考): {precision:.1%}")
    print(f"双方都无待办: {both_empty} | 参考无/本次有: {ref_empty_new_not} | 参考有/本次无: {ref_not_new_empty}")
    print()
    print(f"{'会议':<6}{'参考':>4}{'本次':>4}{'覆盖':>5}{'参考独有':>7}{'本次独有':>7}")
    for r in rows:
        print(
            f"meeting_{r['idx']:02d} {len(r['ref']):>4} {len(r['new']):>4} "
            f"{r['ref_matched']:>5} {len(r['ref'])-r['ref_matched']:>7} "
            f"{len(r['new'])-r['new_matched']:>7}"
        )

    # 详细报告
    lines = [f"# 待办提取语义对比报告（{args.results_dir}，cos>={thr}）", ""]
    lines.append("| 会议 | 参考 | 本次 | 覆盖 | 参考独有 | 本次独有 |")
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| meeting_{r['idx']:02d} | {len(r['ref'])} | {len(r['new'])} | "
            f"{r['ref_matched']} | {len(r['ref'])-r['ref_matched']} | "
            f"{len(r['new'])-r['new_matched']} |"
        )
    lines.append("")
    for r in rows:
        lines.append(f"## meeting_{r['idx']:02d}")
        lines.append("")
        if r["ref"]:
            lines.append("### 参考待办（xlsx 既有产出）")
            for i, t in enumerate(r["ref"], 1):
                pair = next((p for p in r["pairs"] if p[0] == i - 1), None)
                mark = f"✓({pair[2]:.2f})" if pair else "✗"
                lines.append(f"- [{mark}] {t}")
        else:
            lines.append("### 参考：未产生明确待办")
        lines.append("")
        lines.append("### 本次待办（当前系统）")
        for j, t in enumerate(r["new"]):
            pair = next((p for p in r["pairs"] if p[1] == j), None)
            mark = f"✓({pair[2]:.2f})" if pair else "+"
            lines.append(f"- [{mark}] {t}")
        lines.append("")
    report_path = out_dir / "compare_embed.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"详细报告: {report_path}")


if __name__ == "__main__":
    main()
