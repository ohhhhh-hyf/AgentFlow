# -*- coding: utf-8 -*-
"""serverocr 应在主进程直接调用，不再为远程识别起 Python 子进程。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from tools.ocr.layout import ocr_image_lines


def _png(path: Path) -> Path:
    Image.new("RGB", (32, 16), "white").save(path)
    return path


def test_serverocr_calls_ocr_image_in_process(tmp_path, monkeypatch):
    image = _png(tmp_path / "page.png")
    calls = {"ocr_image": 0, "subprocess": 0}

    def fake_ocr(path):
        calls["ocr_image"] += 1
        assert path == str(image)
        return {
            "engine": "serverocr",
            "lines": [
                {
                    "text": "牛顿第一定律",
                    "conf": 0.91,
                    "bbox": [[1, 1], [20, 1], [20, 10], [1, 10]],
                }
            ],
        }

    def fake_run(*_args, **_kwargs):
        calls["subprocess"] += 1
        raise AssertionError("serverocr 成功路径不应启动 OCR 子进程")

    monkeypatch.setenv("OCR_ENGINE", "serverocr")
    monkeypatch.setattr("tools.ocr.server_ocr.ocr_image", fake_ocr)
    monkeypatch.setattr("subprocess.run", fake_run)

    lines = ocr_image_lines(str(image))

    assert calls["ocr_image"] == 1
    assert calls["subprocess"] == 0
    assert lines[0]["text"] == "牛顿第一定律"
    assert lines[0]["conf"] == 0.91


def test_serverocr_retries_three_times_then_returns_empty(tmp_path, monkeypatch):
    image = _png(tmp_path / "page.png")
    calls = {"ocr_image": 0, "subprocess": 0}

    def fake_ocr(_path):
        calls["ocr_image"] += 1
        raise RuntimeError("server down")

    def fake_run(*_args, **_kwargs):
        calls["subprocess"] += 1
        raise AssertionError("serverocr 失败后不应再走 RapidOCR")

    monkeypatch.setenv("OCR_ENGINE", "serverocr")
    monkeypatch.setattr("tools.ocr.server_ocr.ocr_image", fake_ocr)
    monkeypatch.setattr("subprocess.run", fake_run)

    lines = ocr_image_lines(str(image))

    assert calls["ocr_image"] == 3
    assert calls["subprocess"] == 0
    assert lines == []


def test_rapidocr_calls_ocr_image_in_process(tmp_path, monkeypatch):
    image = _png(tmp_path / "page.png")
    calls = {"ocr_image": 0, "subprocess": 0}

    def fake_ocr(path):
        calls["ocr_image"] += 1
        assert path == str(image)
        return {
            "engine": "rapidocr",
            "lines": [
                {
                    "text": "牛顿第一定律",
                    "conf": 0.88,
                    "bbox": [[1, 1], [20, 1], [20, 10], [1, 10]],
                }
            ],
        }

    def fake_run(*_args, **_kwargs):
        calls["subprocess"] += 1
        raise AssertionError("rapidocr 成功路径不应启动 OCR 子进程")

    monkeypatch.setenv("OCR_ENGINE", "rapidocr")
    monkeypatch.setattr("tools.ocr.rapid_ocr.ocr_image", fake_ocr)
    monkeypatch.setattr("subprocess.run", fake_run)

    lines = ocr_image_lines(str(image))

    assert calls["ocr_image"] == 1
    assert calls["subprocess"] == 0
    assert lines[0]["text"] == "牛顿第一定律"
    assert lines[0]["conf"] == 0.88


def test_rapidocr_retries_three_times_then_returns_empty(tmp_path, monkeypatch):
    image = _png(tmp_path / "page.png")
    calls = {"ocr_image": 0, "subprocess": 0}

    def fake_ocr(_path):
        calls["ocr_image"] += 1
        raise RuntimeError("rapidocr failed")

    def fake_run(*_args, **_kwargs):
        calls["subprocess"] += 1
        raise AssertionError("rapidocr 失败后不应再走子进程")

    monkeypatch.setenv("OCR_ENGINE", "rapidocr")
    monkeypatch.setattr("tools.ocr.rapid_ocr.ocr_image", fake_ocr)
    monkeypatch.setattr("subprocess.run", fake_run)

    lines = ocr_image_lines(str(image))

    assert calls["ocr_image"] == 3
    assert calls["subprocess"] == 0
    assert lines == []
