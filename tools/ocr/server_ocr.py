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

import requests

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


def _corner_points_to_bbox(points):
    if not points:
        return None
    bbox = []
    try:
        for point in points:
            bbox.append([float(point["x"]), float(point["y"])])
    except Exception:
        return None
    return bbox if len(bbox) >= 4 else None


def extract_lines(result: dict) -> list[dict]:
    lines: list[dict] = []
    try:
        for block in result.get("text") or []:
            for text_block in block.get("blocks") or []:
                for line in text_block.get("textLines") or []:
                    value = str(line.get("value") or "").strip()
                    if not value:
                        continue
                    bbox = (
                        _corner_points_to_bbox(line.get("cornerPoints"))
                        or line.get("bbox")
                        or line.get("box")
                        or line.get("points")
                        or line.get("polygon")
                    )
                    lines.append(
                        {
                            "text": value,
                            "conf": float(line.get("confidence") or line.get("score") or 1.0),
                            "bbox": bbox,
                        }
                    )
    except Exception:
        return lines
    return lines


def ocr_image(path: str) -> dict:
    with open(path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")
    result = ServerOcrClient().get_ocr(image_base64)
    return {"engine": "serverocr", "lines": extract_lines(result)}
