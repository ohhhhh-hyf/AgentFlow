# -*- coding: utf-8 -*-
from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import tools.ocr.paddle_ocr as paddle_ocr
import tools.ocr.rapid_ocr as rapid_ocr


def _reset_pool(module) -> None:
    module._CREATED = 0
    while True:
        try:
            module._IDLE.get_nowait()
        except queue.Empty:
            break


def test_paddle_pool_runs_four_way_then_reuses(monkeypatch):
    created: list[object] = []
    barrier = threading.Barrier(4)

    class FakeEngine:
        def predict(self, path):
            barrier.wait(timeout=2)
            time.sleep(0.02)
            return []

    def build():
        engine = FakeEngine()
        created.append(engine)
        return engine

    _reset_pool(paddle_ocr)
    monkeypatch.setattr(paddle_ocr, "_build_engine", build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(paddle_ocr.ocr_image, f"img{i}.jpg") for i in range(8)]
        payloads = [future.result() for future in as_completed(futures)]
    assert len(payloads) == 8
    assert all(item["engine"] == "paddleocr" for item in payloads)
    assert len(created) == 4
    assert paddle_ocr._CREATED == 4
    assert paddle_ocr._IDLE.qsize() == 4


def test_rapid_pool_runs_four_way_then_reuses(monkeypatch):
    created: list[object] = []

    class FakeEngine:
        def __call__(self, path):
            time.sleep(0.02)
            return [], None

    def build():
        engine = FakeEngine()
        created.append(engine)
        return engine

    _reset_pool(rapid_ocr)
    monkeypatch.setattr(rapid_ocr, "_build_engine", build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(rapid_ocr.ocr_image, f"img{i}.jpg") for i in range(8)]
        payloads = [future.result() for future in as_completed(futures)]
    assert len(payloads) == 8
    assert all(item["engine"] == "rapidocr" for item in payloads)
    assert len(created) == 4
    assert rapid_ocr._IDLE.qsize() == 4
