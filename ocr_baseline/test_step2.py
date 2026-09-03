# -*- coding: utf-8 -*-
"""Step2（页级并行整理）离线单元测试。

运行：python ocr_baseline/test_step2.py（零网络，LLM 用假实现）。
验证点：
- 页级模式：每页一次短整理调用（调用数 = 需 LLM 的页数），整批模式 = 1 次；
- 跨页上下文：第 N 页 prompt 携带上一页末尾 locked 标题（层级连续）；
- 页级确定性门控：干净页零 LLM 调用且内容仍在（确定性路径）；
- OCR_PAGE_RECONSTRUCT=0 回退整批单调用（A/B 用）。
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

from tools.ocr import engines as eng_mod
from tools.ocr.levels import light


class FakeClient:
    provider, model = "fake", "fake"
    calls: list[dict] = []

    async def text(self, system, user, **kw):
        label = kw.get("label") or "text"
        self.calls.append({"label": label, "user": user, "max_tokens": kw.get("max_tokens")})
        if label == "ocr/reconstruct":
            return "# 整理标题\n\n正文内容占位"
        return "{}"


def env_on(**kw):
    os.environ["OCR_PAGE_RECONSTRUCT"] = kw.get("page", "1")
    os.environ["OCR_RECONSTRUCT_WORKERS"] = str(kw.get("workers", 4))
    os.environ["OCR_COMPLETENESS_FIX"] = "0"   # 本测试只观察整理调用，关闭完整性闭环


def clean_body(page_no: int) -> dict:
    """高置信、版面已锁定的正文行（确定性页用料）。"""
    return {
        "text": f"第{page_no}页正文完整内容足够长避免跨页重复标记甲乙丙丁戊己庚辛壬癸子丑寅卯{page_no}",
        "conf": 0.95,
        "role_hint": "body",
        "title_decision": "locked_body",
        "heading_level_hint": 0,
    }


def clean_heading(text: str) -> dict:
    return {
        "text": text,
        "conf": 0.96,
        "role_hint": "heading",
        "title_decision": "locked_heading",
        "heading_level_hint": 2,
    }


def messy_body(page_no: int) -> dict:
    """低置信 + 版面未锁定行（保证页级门控走 LLM）。"""
    return {
        "text": f"第{page_no}页存在低置信待整理内容行需模型判断归并甲乙丙丁戊己庚辛壬癸子丑寅卯{page_no}",
        "conf": 0.55,
        "role_hint": "body",
        "title_decision": "ambiguous",
    }


def make_pages():
    pages = []
    for idx in range(3):
        lines = []
        if idx == 0:
            lines.append(clean_heading("第一章 态矢与表象"))
        else:
            lines.append(clean_heading(f"第{idx + 1}章 后续章节标题{idx}"))
        lines.append(clean_body(idx))
        for k in range(5):                       # 每页 ≥5 条低置信/未锁定行 → 页级必走 LLM
            lines.append(messy_body(idx * 10 + k))
        pages.append({"name": f"p{idx}.jpg", "raw_text": "x", "lines": lines})
    return pages


def main() -> None:
    eng_mod.get_llm_client = lambda: _FAKE
    _FAKE.calls = []

    # ── 页级模式：3 页 → 3 次整理调用；后两页 prompt 带上一页 locked 标题 ──
    env_on()
    md = light.reconstruct_and_review_pages(make_pages())
    rec_calls = [c for c in _FAKE.calls if c["label"] == "ocr/reconstruct"]
    assert len(rec_calls) == 3, [c["label"] for c in _FAKE.calls]
    hinted = [c for c in rec_calls if "跨页上下文" in c["user"]]
    assert len(hinted) == 2, len(hinted)                       # 并发完成顺序不定，按集合断言
    assert any("第一章 态矢与表象" in c["user"] for c in hinted)
    assert any("第2章 后续章节标题1" in c["user"] for c in hinted)
    assert md.strip()
    print("PASS 页级 3 调用 + 跨页上下文传递")

    # ── 确定性页零 LLM：整页高置信锁定 → 该页不产生调用且内容在稿中 ──
    _FAKE.calls = []
    pages2 = [{
        "name": "clean.jpg",
        "raw_text": "x",
        "lines": [clean_heading("第二章 干净的章节"), clean_body(9)],
    }, {
        "name": "messy.jpg",
        "raw_text": "x",
        "lines": [clean_heading("第三章 需要整理的章节")]
        + [messy_body(10 + k) for k in range(5)],
    }]
    md2 = light.reconstruct_and_review_pages(pages2)
    rec2 = [c for c in _FAKE.calls if c["label"] == "ocr/reconstruct"]
    assert len(rec2) == 1, len(rec2)          # 只有 messy 页调用 LLM
    assert "干净的章节" in md2
    print("PASS 确定性页零 LLM 且内容保留")

    # ── 整批模式回退：同输入 → 1 次整批调用 ──
    _FAKE.calls = []
    env_on(page="0")
    light.reconstruct_and_review_pages(make_pages())
    rec3 = [c for c in _FAKE.calls if c["label"] == "ocr/reconstruct"]
    assert len(rec3) == 1, len(rec3)
    print("PASS OCR_PAGE_RECONSTRUCT=0 回退整批单调用")

    # ── reconstruct_markdown 的跨页上下文参数直达 prompt ──
    from tools.ocr import reconstruct as rc

    _FAKE.calls = []
    rc.reconstruct_markdown([messy_body(1)], max_tokens=9000, context="## 上一章末尾标题")
    assert _FAKE.calls and "上一章末尾标题" in _FAKE.calls[-1]["user"]
    _FAKE.calls = []
    rc.reconstruct_markdown([messy_body(1)], max_tokens=9000)
    assert _FAKE.calls and "跨页上下文" not in _FAKE.calls[-1]["user"]
    print("PASS context 参数直达 prompt（空 context 行为不变）")

    print("ALL_STEP2_TESTS_OK")


_FAKE = FakeClient()

if __name__ == "__main__":
    main()
