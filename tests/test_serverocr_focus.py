# -*- coding: utf-8 -*-
"""服务器 FOCUS OCR：只收 textLines，转回原图坐标，过滤噪声。RapidOCR 不受影响。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from tools.ocr.layout import ocr_image_lines
from tools.ocr.reconstruct import _lines_to_structured_payload
from tools.ocr.server_ocr import extract_lines

IMAGE_SIZE = (1280, 960)

FOCUS_MINI = {
    "description": "FOCUS OCR process is completed successfully!",
    "imgHeight": 1280,
    "imgWidth": 960,
    "statusCode": "0000000000",
    "text": [
        {
            "value": "CONCAT-PAGE-DURSTOR＋波函数的色续性",
            "blocks": [
                {
                    "orientation": 1,
                    "value": "CONCAT-BLOCK-DURSTOR＋波函数的色续性",
                    "textLines": [
                        {
                            "value": "DURSTOR",
                            "modelType": "EU_recog",
                            "probability": 0,
                            "elements": [{"value": "DURSTOR", "probability": 0}],
                            "cornerPoints": [
                                {"x": 902, "y": 848},
                                {"x": 903, "y": 912},
                                {"x": 888, "y": 912},
                                {"x": 887, "y": 848},
                            ],
                        },
                        {
                            "value": "＋波函数的色续性",
                            "modelType": "JK_recog",
                            "probability": 0,
                            "elements": [{"value": "＋"}, {"value": "波"}],
                            "cornerPoints": [
                                {"x": 835, "y": 43},
                                {"x": 842, "y": 190},
                                {"x": 821, "y": 191},
                                {"x": 814, "y": 44},
                            ],
                        },
                        {
                            "value": "pa~raa. IT'=70",
                            "modelType": "THAI_recog",
                            "probability": 0,
                            "elements": [],
                            "cornerPoints": [
                                {"x": 646, "y": 88},
                                {"x": 686, "y": 416},
                                {"x": 646, "y": 416},
                                {"x": 646, "y": 88},
                            ],
                        },
                        {
                            "value": "Aeβ+Be-βa=TeTKA",
                            "modelType": "EU_recog",
                            "probability": 0,
                            "elements": [{"value": "A"}],
                            "cornerPoints": [
                                {"x": 767, "y": 210},
                                {"x": 806, "y": 210},
                                {"x": 806, "y": 394},
                                {"x": 767, "y": 394},
                            ],
                        },
                    ],
                }
            ],
        }
    ],
}

WRAPPER = {
    "version": "1.2",
    "result": {"code": "0", "length": 2, "content": [json.dumps(FOCUS_MINI, ensure_ascii=False), "441"]},
}

_REAL_JSON_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "samples" / "examples" / "U202314948_1.json",
    Path(r"D:\study\AgentFlow\samples\examples\U202314948_1.json"),
]


def _bbox_wh(bbox):
    xs = [pt[0] for pt in bbox]
    ys = [pt[1] for pt in bbox]
    return max(xs) - min(xs), max(ys) - min(ys), min(xs), min(ys)


def test_focus_skips_page_and_block_concat():
    lines = extract_lines(FOCUS_MINI, image_size=IMAGE_SIZE)
    texts = [item["text"] for item in lines]
    assert "CONCAT-PAGE-DURSTOR＋波函数的色续性" not in texts
    assert "CONCAT-BLOCK-DURSTOR＋波函数的色续性" not in texts
    assert any("波函数" in text for text in texts)


def test_focus_drops_thai_empty_and_eu_margin_branding():
    lines = extract_lines(FOCUS_MINI, image_size=IMAGE_SIZE)
    texts = [item["text"] for item in lines]
    assert "DURSTOR" not in texts
    assert not any("pa~raa" in text for text in texts)
    assert any("Aeβ+Be-βa=TeTKA" in text for text in texts)


def test_focus_maps_orientation_1_boxes_back_to_landscape():
    lines = extract_lines(FOCUS_MINI, image_size=IMAGE_SIZE)
    heading = next(item for item in lines if "波函数" in item["text"])
    width, height, left, top = _bbox_wh(heading["bbox"])
    assert width > height * 1.5
    assert left < 250
    assert top < 200


def test_focus_omits_zero_probability_conf():
    lines = extract_lines(FOCUS_MINI, image_size=IMAGE_SIZE)
    assert lines
    assert all("conf" not in item for item in lines)


def test_focus_unwraps_cloudsoa_wrapper():
    lines = extract_lines(WRAPPER, image_size=IMAGE_SIZE)
    texts = [item["text"] for item in lines]
    assert any("波函数" in text for text in texts)
    assert "DURSTOR" not in texts


def test_llm_payload_omits_unknown_conf_keeps_rapidocr_conf():
    server_lines = [{"text": "标题", "bbox": [[1, 1], [20, 1], [20, 8], [1, 8]]}]
    rapid_lines = [
        {"text": "牛顿第一定律", "conf": 0.91, "bbox": [[1, 1], [20, 1], [20, 8], [1, 8]]}
    ]
    server_payload = json.loads(_lines_to_structured_payload(server_lines))
    rapid_payload = json.loads(_lines_to_structured_payload(rapid_lines))
    assert "conf" not in server_payload[0]
    assert rapid_payload[0]["conf"] == 0.91


def test_rapidocr_layout_still_keeps_conf(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    Image.new("RGB", (32, 16), "white").save(image)

    def fake_ocr(_path, formula=False, timeout=180):
        del formula, timeout
        return {
            "engine": "rapidocr",
            "lines": [
                {
                    "text": "牛顿第一定律",
                    "conf": 0.91,
                    "bbox": [[1, 1], [20, 1], [20, 10], [1, 10]],
                }
            ],
        }

    monkeypatch.setenv("OCR_ENGINE", "rapidocr")
    monkeypatch.setattr("tools.ocr.engines.run_ocr_subprocess", fake_ocr)

    lines = ocr_image_lines(str(image))
    assert lines[0]["text"] == "牛顿第一定律"
    assert lines[0]["conf"] == 0.91


def test_real_focus_dump_if_present():
    path = next((item for item in _REAL_JSON_CANDIDATES if item.is_file()), None)
    if path is None:
        pytest.skip("U202314948_1.json 不在工作区")
    raw = json.loads(path.read_text(encoding="utf-8"))
    lines = extract_lines(raw, image_size=IMAGE_SIZE)
    texts = [item["text"] for item in lines]
    assert lines
    assert all(len(text) < 400 for text in texts)
    assert "DURSTOR" not in texts
    assert not any("เท" in text or "ﺃ" in text for text in texts)
    assert any("波函数" in text for text in texts)
    heading = next(item for item in lines if "波函数" in item["text"])
    width, height, _left, _top = _bbox_wh(heading["bbox"])
    assert width > height
    assert all("conf" not in item for item in lines)


def test_server_ocr_code_102_raises_instead_of_empty(monkeypatch):
    from tools.ocr.server_ocr import ServerOcrClient

    class FakeResp:
        status_code = 200
        headers = {}
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "result": {
                    "code": "102",
                    "des": "Response from mep is null.",
                    "content": [],
                }
            }

    monkeypatch.setattr("tools.ocr.server_ocr.requests.post", lambda *_a, **_k: FakeResp())
    monkeypatch.setattr(ServerOcrClient, "_get_sign", lambda self: (1, "sig"))
    with pytest.raises(RuntimeError, match="code=102"):
        ServerOcrClient().get_ocr("abc")
