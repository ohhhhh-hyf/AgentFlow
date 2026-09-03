# -*- coding: utf-8 -*-
"""组间流水线重叠（OCR_PIPELINE_OVERLAP）离线测试。

运行：python ocr_baseline/test_step4.py（零网络）。
验证点：
- 事件顺序与串行一致：第 1 组 batch_done 先于第 2 组 ocr_start；
- 真实重叠发生：第 2 组 OCR 与第 1 组整理并行执行（观测标志）；
- 墙钟下降：重叠 < 串行（同输入同耗时参数）；
- chunk_stats 携带真实 OCR/整理墙钟；
- OCR_PIPELINE_OVERLAP=0 回退串行。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.CRITICAL)

from tools.ocr.levels import light

OCR_SLEEP = 0.10   # 每张假 OCR 耗时
REVIEW_SLEEP = 0.50  # 每次假整理耗时（> OCR_SLEEP，保证重叠窗口真实存在）


def fake_ocr(path):
    global OVERLAP_OBSERVED
    if REVIEWING.is_set():
        OVERLAP_OBSERVED = True
    time.sleep(OCR_SLEEP)
    return "x", [
        {"text": f"第{Path(path).stem}页正文内容足够长避免噪声判定甲乙丙丁戊己庚辛壬癸",
         "conf": 0.95, "role_hint": "body", "title_decision": "locked_body"},
    ]


def fake_review(pages):
    REVIEWING.set()
    try:
        time.sleep(REVIEW_SLEEP)
    finally:
        REVIEWING.clear()
    return "\n\n".join(
        f"第{p['name']}页整理稿内容甲乙丙丁戊己庚辛壬癸子丑寅卯" for p in pages
    )


REVIEWING = threading.Event()
OVERLAP_OBSERVED = False


def run(overlap: bool) -> tuple[float, list[str], list[dict]]:
    global OVERLAP_OBSERVED
    OVERLAP_OBSERVED = False
    os.environ["OCR_PIPELINE_OVERLAP"] = "1" if overlap else "0"
    os.environ["OCR_ENGINE"] = "rapidocr"
    os.environ["OCR_PARALLEL"] = "4"
    entries = [(Path(f"img_{i}.jpg"), f"img_{i}.jpg") for i in range(3)]
    t0 = time.monotonic()
    events = list(light.iter_ocr_review_pipeline(
        entries, ocr_fn=fake_ocr, review_fn=fake_review, batch_size=2,
    ))
    wall = time.monotonic() - t0
    kinds = [e["type"] for e in events]
    stats = [e for e in events if e["type"] == "chunk_stats"]
    return wall, kinds, stats


def main() -> None:
    # ── 重叠模式：事件顺序保持、真实重叠、chunk_stats 存在 ──
    wall_on, kinds_on, stats_on = run(overlap=True)
    first_batch_done = kinds_on.index("batch_done")
    second_ocr_start = [i for i, k in enumerate(kinds_on) if k == "ocr_start"][1]
    assert first_batch_done < second_ocr_start, kinds_on      # 事件顺序与串行一致
    assert kinds_on.count("chunk_stats") == 2
    assert all(s["ocr_seconds"] > 0 and s["review_seconds"] >= REVIEW_SLEEP - 0.05 for s in stats_on)
    assert OVERLAP_OBSERVED, "未观测到第 2 组 OCR 与第 1 组整理并行"
    print(f"PASS 重叠：墙钟 {wall_on:.2f}s，事件顺序保持，重叠已发生")

    # ── 串行对照：墙钟应显著更大 ──
    wall_off, kinds_off, stats_off = run(overlap=False)
    assert wall_on < wall_off - 0.05, (wall_on, wall_off)
    assert kinds_off.count("chunk_stats") == 2
    print(f"PASS 开关回退：重叠 {wall_on:.2f}s < 串行 {wall_off:.2f}s")

    os.environ.pop("OCR_PIPELINE_OVERLAP", None)
    os.environ.pop("OCR_PARALLEL", None)
    print("ALL_STEP4_TESTS_OK")


if __name__ == "__main__":
    main()
