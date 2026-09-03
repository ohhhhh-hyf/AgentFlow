# -*- coding: utf-8 -*-
"""Step3（paddle 路线收尾项）离线单元测试：review 旁路/留痕 + paddle 识别前放大。

运行：python ocr_baseline/test_step3.py（零网络，LLM 用假实现）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import logging

logging.basicConfig(level=logging.CRITICAL)

from tools.ocr import engines as eng_mod
from tools.ocr.levels import light


ROW_A = "正文低置信行内容足够长触发审校门控判定甲乙丙丁戊己庚辛壬癸子丑寅卯1"
ROW_B = "正文低置信行内容足够长触发审校门控判定甲乙丙丁戊己庚辛壬癸子丑寅卯2"
ROW_C = "正文低置信行内容足够长触发审校门控判定甲乙丙丁戊己庚辛壬癸子丑寅卯3"


class FakeClient:
    provider, model = "fake", "fake"
    calls: list[dict] = []

    async def text(self, system, user, **kw):
        label = kw.get("label") or "text"
        self.calls.append({"label": label})
        if label == "ocr/reconstruct":
            return "# 整理标题\n\n" + ROW_A + "\n\n" + ROW_B + "\n\n" + ROW_C
        return "{}"      # review：无补丁


def env_clean():
    os.environ["OCR_PAGE_RECONSTRUCT"] = "0"   # 本测试走整批路径，隔离变量
    os.environ["OCR_COMPLETENESS_FIX"] = "0"
    os.environ["OCR_REVIEW"] = "1"
    os.environ.pop("OCR_UPSCALE", None)


def messy_page():
    return [{
        "name": "messy.jpg",
        "raw_text": "x",
        "lines": [
            {"text": "第三章 需要整理的章节标题内容", "conf": 0.96, "role_hint": "heading", "title_decision": "locked_heading", "heading_level_hint": 2},
            {"text": ROW_A, "conf": 0.55},
            {"text": ROW_B, "conf": 0.6},
            {"text": ROW_C, "conf": 0.6},
        ],
    }]


def main() -> None:
    eng_mod.get_llm_client = lambda: _FAKE

    # ── review 默认开：needs_review 时执行并留痕；假模型无补丁 → draft 不变 ──
    env_clean()
    _FAKE.calls = []
    light.take_review_events()
    md_on = light.reconstruct_and_review_pages(messy_page())
    assert any(c["label"] == "ocr/review" for c in _FAKE.calls)
    ev = light.take_review_events()
    assert len(ev) == 1 and ev[0]["ran"] is True and ev[0]["draft_changed"] is False
    assert ev[0]["applied_patches"] == 0 and ev[0]["needs_review"] is True
    print("PASS review 默认开 + 留痕")

    # ── OCR_REVIEW=0：即使 needs_review 也不调用、事件记录 disabled ──
    env_clean()
    os.environ["OCR_REVIEW"] = "0"
    _FAKE.calls = []
    light.take_review_events()
    md_off = light.reconstruct_and_review_pages(messy_page())
    assert not any(c["label"] == "ocr/review" for c in _FAKE.calls)
    ev = light.take_review_events()
    assert len(ev) == 1 and ev[0]["review_enabled"] is False and ev[0]["ran"] is False
    assert md_off == md_on                     # 无补丁场景下旁路不改变成稿
    print("PASS OCR_REVIEW=0 旁路 + disabled 留痕")

    # ── 事件 1:1 且可取空 ──
    env_clean()
    light.take_review_events()
    light.reconstruct_and_review_pages(messy_page())
    ev = light.take_review_events()
    assert len(ev) == 1 and light.take_review_events() == []
    print("PASS review 事件配对与清空")

    # ── paddle 识别前放大：默认关 / 非 paddle 引擎跳过 / paddle 开启生效 ──
    os.environ["OCR_ENGINE"] = "paddleocr"
    small = Path(tempfile.gettempdir()) / "agentflow_test_small.png"
    from PIL import Image

    Image.new("RGB", (300, 200), "white").save(small)
    try:
        os.environ.pop("OCR_UPSCALE", None)
        p, applied = light._prepare_ocr_image(small)
        assert p == small and applied is False          # 默认关
        os.environ["OCR_UPSCALE"] = "1"
        p2, applied2 = light._prepare_ocr_image(small)
        assert applied2 is True and p2 != small
        with Image.open(p2) as img:
            assert max(img.size) >= 2400
        p2.unlink(missing_ok=True)                       # 调用方负责清理
        os.environ["OCR_ENGINE"] = "rapidocr"
        p3, applied3 = light._prepare_ocr_image(small)
        assert p3 == small and applied3 is False         # 非 paddle 引擎跳过
        os.environ["OCR_ENGINE"] = "paddleocr"
        print("PASS paddle 识别前放大（默认关/引擎限定/生效）")
    finally:
        small.unlink(missing_ok=True)
        os.environ.pop("OCR_UPSCALE", None)

    print("ALL_STEP3_TESTS_OK")


_FAKE = FakeClient()

if __name__ == "__main__":
    main()
