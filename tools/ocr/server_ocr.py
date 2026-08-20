"""服务器 OCR 接口适配。

给 tools.ocr.runner_ocr 使用，避免运行目录缺少根目录 ``ocr/`` 包时报
``No module named 'ocr'``。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

import requests
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_env_file() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except Exception:
        return


class ServerOcrClient:
    def __init__(self):
        _load_env_file()
        self.ocr_url = os.getenv("SERVER_OCR_URL", "http://10.33.111.33:8080/service")
        self.request_id = os.getenv("SERVER_OCR_REQUEST_ID", "test")
        self.uuid = os.getenv("SERVER_OCR_UUID", "test")
        self.appid = os.getenv("SERVER_OCR_APPID", "hiai")
        self.bid = os.getenv("SERVER_OCR_BID", "test_focusocr_fun")
        self.flowid = os.getenv("SERVER_OCR_FLOWID", "test_focusocr_fun")
        self.language = os.getenv("SERVER_OCR_LANGUAGE", "AUTO")
        self.shape = os.getenv("SERVER_OCR_TEXT_SHAPE", "curve_enable")
        self.sign_key = os.getenv(
            "SERVER_OCR_SIGN_KEY",
            "CB663177458347D19A07D03E7728C878D1C413811F0C4526AEDD26DDD4334980",
        )
        self.language_map = {
            "AUTO": "0",
            "CHINESE": "1",
            "SPANISH": "2",
            "ENGLISH": "3",
            "PORTUGUESE": "4",
            "ITALIAN": "5",
            "GERMAN": "6",
            "FRENCH": "7",
            "RUSSIAN": "8",
            "JAPANESE": "9",
            "KOREAN": "10",
        }

    def get_ocr(self, image_base64: str) -> dict:
        request_data = {
            "image": image_base64,
            "ocrLanguage": self.language_map.get(self.language, "0"),
            "textShape": self.shape,
            "requestId": self.request_id,
            "deviceId": "grey",
            "timeZone": "timeZone",
            "time": "time",
            "language": "language",
            "ext": "ext",
            "resize": "False",
            "enableFilter": "False",
        }
        return self._ocr_post(request_data)

    def _get_sign(self) -> tuple[int, str]:
        timestamp = int(time.time() * 1000)
        sign_str = f"POST&/service&&&appid={self.appid}&timestamp={timestamp}"
        sign = base64.b64encode(
            hmac.new(
                self.sign_key.encode("utf-8"),
                sign_str.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        return timestamp, sign

    def _ocr_post(self, request_data: dict) -> dict:
        timestamp, sign = self._get_sign()
        payload = {
            "data": request_data,
            "meta": {
                "subId": "2",
                "bId": self.bid,
                "flowId": self.flowid,
                "uuId": self.uuid,
            },
            "version": "1.2",
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": (
                "CLOUDSOA-HMAC-SHA256 "
                f"appid={self.appid}, "
                f"timestamp={timestamp}, "
                "signmode=easy, "
                f'signature="{sign}"'
            ),
        }
        response = requests.post(
            self.ocr_url,
            json=payload,
            headers=headers,
            timeout=float(os.getenv("SERVER_OCR_TIMEOUT", "60")),
        )
        response.raise_for_status()
        result = response.json()
        if result["result"]["code"] != "0":
            return {}
        content = result["result"]["content"][0]
        if isinstance(content, str):
            return json.loads(content)
        return content


def _first_present(data: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return None


def _point_xy(point: Any) -> tuple[float, float] | None:
    try:
        if isinstance(point, dict):
            x = _first_present(point, ("x", "X", "left", "Left"))
            y = _first_present(point, ("y", "Y", "top", "Top"))
            if x is None or y is None:
                return None
            return float(x), float(y)
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            return float(point[0]), float(point[1])
    except Exception:
        return None
    return None


def _rect_to_bbox(rect: Any) -> list[list[float]] | None:
    if not rect:
        return None
    try:
        if isinstance(rect, dict):
            x = _first_present(rect, ("x", "X", "left", "Left"))
            y = _first_present(rect, ("y", "Y", "top", "Top"))
            w = _first_present(rect, ("w", "W", "width", "Width"))
            h = _first_present(rect, ("h", "H", "height", "Height"))
            right = _first_present(rect, ("right", "Right", "x2", "X2"))
            bottom = _first_present(rect, ("bottom", "Bottom", "y2", "Y2"))
            if x is not None and y is not None and w is not None and h is not None:
                left, top = float(x), float(y)
                right, bottom = left + float(w), top + float(h)
            elif x is not None and y is not None and right is not None and bottom is not None:
                left, top = float(x), float(y)
                right, bottom = float(right), float(bottom)
            else:
                return None
        elif isinstance(rect, (list, tuple)) and len(rect) >= 4:
            left, top, third, fourth = [float(v) for v in rect[:4]]
            # 兼容 [x,y,w,h] 与 [x1,y1,x2,y2]；后者通常第三/第四项更大。
            if third > left and fourth > top:
                right, bottom = third, fourth
            else:
                right, bottom = left + third, top + fourth
        else:
            return None
    except Exception:
        return None
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def _points_to_bbox(points: Any) -> list[list[float]] | None:
    if not points:
        return None
    if isinstance(points, dict):
        for key in ("points", "polygon", "vertices", "cornerPoints"):
            if points.get(key):
                return _points_to_bbox(points.get(key))
        return _rect_to_bbox(points)
    if not isinstance(points, (list, tuple)):
        return None
    parsed = [_point_xy(point) for point in points]
    parsed = [point for point in parsed if point is not None]
    if len(parsed) >= 4:
        return [[float(x), float(y)] for x, y in parsed[:4]]
    if len(points) >= 4 and all(isinstance(v, (int, float, str)) for v in points[:4]):
        return _rect_to_bbox(points)
    return None


def _normalize_bbox(raw: Any, image_size: tuple[int, int] | None = None) -> list[list[float]] | None:
    bbox = _points_to_bbox(raw) or _rect_to_bbox(raw)
    if not bbox:
        return None
    width, height = image_size or (0, 0)
    try:
        max_x = max(point[0] for point in bbox)
        max_y = max(point[1] for point in bbox)
        min_x = min(point[0] for point in bbox)
        min_y = min(point[1] for point in bbox)
        is_percent = width > 1 and height > 1 and 0 <= min_x and 0 <= min_y and max_x <= 1.5 and max_y <= 1.5
        if is_percent:
            bbox = [[x * width, y * height] for x, y in bbox]
    except Exception:
        return None
    return [[round(float(x), 2), round(float(y), 2)] for x, y in bbox]


def _iter_line_nodes(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from _iter_line_nodes(item)
        return
    if not isinstance(node, dict):
        return
    text_value = _first_present(
        node,
        ("value", "text", "content", "words", "label", "transcription", "recognizedText"),
    )
    if isinstance(text_value, (str, int, float)) or (
        isinstance(text_value, list)
        and all(isinstance(item, (str, int, float)) for item in text_value)
    ):
        yield node
    for key in ("text", "blocks", "textLines", "lines", "words", "items", "regions", "paragraphs", "results", "data"):
        child = node.get(key)
        if isinstance(child, (list, dict)):
            yield from _iter_line_nodes(child)


def _line_text(line: dict) -> str:
    value = _first_present(
        line,
        ("value", "text", "content", "words", "label", "transcription", "recognizedText"),
    )
    if isinstance(value, list):
        value = "".join(str(v) for v in value)
    return str(value or "").strip()


def _line_conf(line: dict) -> float:
    raw = _first_present(line, ("confidence", "conf", "score", "prob", "probability"))
    try:
        conf = float(raw)
    except Exception:
        return 1.0
    return conf / 100 if conf > 1.0 else conf


def _line_bbox(line: dict, image_size: tuple[int, int] | None = None) -> list[list[float]] | None:
    raw = _first_present(
        line,
        (
            "cornerPoints",
            "bbox",
            "box",
            "points",
            "polygon",
            "poly",
            "vertices",
            "rect",
            "position",
            "location",
        ),
    )
    if raw is None:
        raw = line
    return _normalize_bbox(raw, image_size)


def extract_lines(result: dict, image_size: tuple[int, int] | None = None) -> list[dict]:
    lines: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line in _iter_line_nodes(result):
        value = _line_text(line)
        if not value:
            continue
        bbox = _line_bbox(line, image_size)
        key = (value, json.dumps(bbox, ensure_ascii=False) if bbox else "")
        if key in seen:
            continue
        seen.add(key)
        item = {"text": value, "conf": _line_conf(line)}
        if bbox:
            item["bbox"] = bbox
        lines.append(item)
    return lines


def ocr_image(path: str) -> dict:
    with open(path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")
    image_size = None
    try:
        with Image.open(path) as img:
            image_size = img.size
    except Exception:
        image_size = None
    result = ServerOcrClient().get_ocr(image_base64)
    return {"engine": "serverocr", "lines": extract_lines(result, image_size=image_size)}
