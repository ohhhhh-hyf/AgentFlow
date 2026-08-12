"""Run minutes cases 1-5 and summarize body han vs budget."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
MG = OUT / "meeting" / "minutes_generation"


def body_han(text: str) -> int:
    from tools.template_router import _body_han_count

    return _body_han_count(text)


def budget_label(i: int) -> str:
    from tools.template_eval import parse_document_char_budget

    tpl = (
        ROOT / "samples/meeting/minutes_generation_template" / f"{i}.md"
    ).read_text(encoding="utf-8")
    b = parse_document_char_budget(tpl)
    if not b.get("hi"):
        return "无全文预算"
    lo, hi, cap = b.get("lo"), b["hi"], b.get("cap")
    return f"{lo or '?'}-{hi} (cap={cap})"


def judge(i: int, han: int) -> str:
    from tools.template_eval import parse_document_char_budget

    tpl = (
        ROOT / "samples/meeting/minutes_generation_template" / f"{i}.md"
    ).read_text(encoding="utf-8")
    b = parse_document_char_budget(tpl)
    if not b.get("hi"):
        return "无全文预算"
    lo, hi, cap = b.get("lo"), int(b["hi"]), int(b.get("cap") or b["hi"] * 1.5)
    lo_i = int(lo) if lo else None
    if lo_i and han < lo_i:
        return "偏短"
    if han <= hi:
        return "落在区间"
    if han <= cap:
        return "略超hi≤cap"
    return "超cap"


def flags(i: int, text: str) -> list[str]:
    out: list[str] = []
    if i == 3:
        # count sentence-ending periods on content lines
        n = len(re.findall(r"[。！？]", text))
        out.append(f"句号类={n}")
    if i == 4:
        if "聚结" in text and "装反" in text:
            out.append("装反-聚结")
        if "PTFE" in text and ("水" in text or "疏水" in text):
            out.append("PTFE-水样/疏水")
    if i == 5:
        if "秩序" in text:
            out.append("含秩序感")
        if "精确" in text:
            out.append("含精确")
    if i == 1:
        if "任教" in text or "代表作" in text:
            out.append("疑似百科补全")
        if "筹备" in text or "收尾" in text:
            out.append("疑似空壳流程")
    if i == 2:
        if "倩蕾" in text and "范倩磊" not in text:
            out.append("示例名倩蕾")
        if "预计" in text or "可能" in text or "有望" in text:
            out.append("含预计语气")
    return out


def main() -> int:
    sys.path.insert(0, str(ROOT))
    summary = []
    for i in range(1, 6):
        cmd = [
            sys.executable,
            str(ROOT / "bootstrap.py"),
            "--domain",
            "meeting",
            "--task",
            "minutes_generation",
            "--file",
            f"samples/meeting/file/{i}.txt",
            "--profile",
            "samples/meeting/profile/object_profile.json",
            "--minutes_generation_template",
            f"samples/meeting/minutes_generation_template/{i}.md",
        ]
        print(f"=== CASE {i} ===", flush=True)
        p = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print(p.stdout[-2500:] if p.stdout else "", flush=True)
        if p.returncode != 0:
            print(p.stderr[-1500:] if p.stderr else "", flush=True)
        results = sorted(
            [x for x in MG.glob("result_*.md") if "_rejected" not in x.name],
            key=lambda x: x.stat().st_mtime,
        )
        if not results:
            summary.append((i, None, None, [], "NO_RESULT"))
            continue
        latest = results[-1]
        text = latest.read_text(encoding="utf-8")
        (OUT / f"{i}.md").write_text(text, encoding="utf-8")
        h = body_han(text)
        j = judge(i, h)
        fl = flags(i, text)
        summary.append((i, h, j, fl, latest.name))
        print(
            f"-> {latest.name} body_han={h} judge={j} flags={fl}",
            flush=True,
        )

    print("\n===== SUMMARY =====", flush=True)
    for i, h, j, fl, name in summary:
        print(
            f"Case{i}: han={h} | {j} | flags={fl} | budget={budget_label(i)} | {name}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
