# -*- coding: utf-8 -*-
"""S3 碎片行合并（OCR_MERGE_FRAGMENTS）离线测试。

运行：python ocr_baseline/test_step5.py（零网络）。
验证点：保守邻接判定各分支（合并成功/句读停/间距大/无水平重叠/编号开头/
公式隔断/中英空格），conf 取最低，bbox 取并集，链式合并，默认关。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.CRITICAL)

from tools.ocr import layout


def line(text: str, x0: float, x1: float, y0: float, y1: float, conf: float | None = None, formula: str = ""):
    item: dict = {"text": text, "bbox": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}
    if conf is not None:
        item["conf"] = conf
    if formula:
        item["formula"] = formula
    return item


def merge_on(lines):
    os.environ["OCR_MERGE_FRAGMENTS"] = "1"
    try:
        return layout.merge_fragment_lines(lines)
    finally:
        os.environ.pop("OCR_MERGE_FRAGMENTS", None)


def main() -> None:
    # ── 默认关：原样返回 ──
    ls = [line("第一段碎片内容足够长甲乙丙丁戊己庚辛壬癸", 0, 400, 10, 30, 0.9),
          line("第二段碎片内容足够长甲乙丙丁戊己庚辛壬癸", 0, 400, 31, 51, 0.8)]
    assert layout.merge_fragment_lines(ls) == ls
    print("PASS 默认关原样返回")

    # ── 合并成功：中文连续无空格、conf 取最低、bbox 取并集 ──
    out = merge_on([
        line("定义：函数在闭区间上", 100, 500, 100, 120, 0.9),
        line("必有界且能取得最值", 100, 520, 121, 141, 0.7),
    ])
    assert len(out) == 1, out
    assert out[0]["text"] == "定义：函数在闭区间上必有界且能取得最值", out[0]["text"]
    assert out[0]["conf"] == 0.7
    assert out[0]["bbox"][0] == [100, 100] and out[0]["bbox"][2] == [520, 141]
    print("PASS 合并成功（中文拼接/最低 conf/bbox 并集）")

    # ── 中英交界加空格 ──
    out = merge_on([
        line("设 x", 0, 200, 10, 30, 0.9),
        line("趋近于零", 0, 200, 31, 51, 0.9),
    ])
    assert out[0]["text"] == "设 x 趋近于零", out[0]["text"]
    print("PASS 中英交界空格")

    # ── 不合并分支 ──
    base = [
        line("前段内容足够长甲", 0, 400, 10, 30, 0.9),
        line("后段内容足够长乙", 0, 400, 31, 51, 0.9),
    ]
    # 句读结束
    out = merge_on([line("句子结束了。", 0, 400, 10, 30, 0.9),
                    line("后段内容足够长乙", 0, 400, 31, 51, 0.9)])
    assert len(out) == 2
    # 间距过大（间隙 40 > 中位高 20×0.6）
    out = merge_on([line("前段内容足够长甲", 0, 400, 10, 30, 0.9),
                    line("后段内容足够长乙", 0, 400, 71, 91, 0.9)])
    assert len(out) == 2
    # 无水平重叠（不同栏）
    out = merge_on([line("前段内容足够长甲", 0, 300, 10, 30, 0.9),
                    line("后段内容足够长乙", 600, 900, 31, 51, 0.9)])
    assert len(out) == 2
    # 后行编号开头（新条目）
    out = merge_on([line("前段内容足够长甲", 0, 400, 10, 30, 0.9),
                    line("1.2 极限定义内容足够长", 0, 400, 31, 51, 0.9)])
    assert len(out) == 2
    # 公式隔断
    out = merge_on([line("前段文字内容足够长甲", 0, 400, 10, 30, 0.9),
                    line("x^2+y^2=z^2", 0, 400, 31, 51, 0.9, formula="x^2+y^2=z^2"),
                    line("后段文字内容足够长乙", 0, 400, 52, 72, 0.9)])
    assert len(out) == 3
    print("PASS 不合并分支（句读/间距/分栏/编号/公式）")

    # ── 链式合并：三碎片 → 一行 ──
    out = merge_on([
        line("洛必达法则：当分子", 0, 400, 10, 30, 0.9),
        line("分母同时趋于零或", 0, 405, 31, 51, 0.8),
        line("无穷大时可使用", 0, 400, 52, 72, 0.85),
    ])
    assert len(out) == 1
    assert out[0]["text"] == "洛必达法则：当分子分母同时趋于零或无穷大时可使用", out[0]["text"]
    assert out[0]["conf"] == 0.8
    print("PASS 链式合并")

    # ── 无 conf 行参与合并后不带 conf ──
    out = merge_on([line("第一段碎片内容足够长甲", 0, 400, 10, 30),
                    line("第二段碎片内容足够长乙", 0, 400, 31, 51)])
    assert len(out) == 1 and "conf" not in out[0]
    print("PASS 无 conf 合并")

    print("ALL_STEP5_TESTS_OK")


if __name__ == "__main__":
    main()
