"""服务器 OCR 接口适配。

供 OCR 引擎调用，避免运行目录缺少根目录包时报
``No module named 'ocr'``。
"""
from __future__ import annotations

import base64
import io
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OCR_FAILURE_DIR = Path(ROOT) / "log" / "ocr_failed"
MAX_BASE64_BYTES = int(os.getenv("SERVER_OCR_MAX_BASE64_BYTES", str(950 * 1024)))


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


def _write_failure_log(title: str, detail: str) -> None:
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        folder = OCR_FAILURE_DIR / stamp
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "error.txt").write_text(
            f"{title}\n\n{detail}",
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return


class ServerOcrClient:
    def __init__(self):
        _load_env_file()
        self.ocr_url = os.getenv("SERVER_OCR_URL", "http://10.33.111.33:8080/service")
        self.request_id = os.getenv("SERVER_OCR_REQUEST_ID", "scripts")
        self.uuid = os.getenv("SERVER_OCR_UUID", "scripts")
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
        try:
            result = response.json()
        except Exception as exc:  # noqa: BLE001
            _write_failure_log(
                "服务器 OCR 响应不是合法 JSON",
                f"error={type(exc).__name__}: {exc}\n"
                f"status={response.status_code}\n"
                f"headers={dict(response.headers)}\n"
                f"body_head={(response.text or '')[:2000]}",
            )
            raise
        try:
            result_info = result["result"]
            code = str(result_info.get("code") or "")
            if code != "0":
                des = str(result_info.get("des") or "").strip()
                raise RuntimeError(
                    f"服务器 OCR 失败 code={code}"
                    + (f" des={des}" if des else "")
                )
            content = result_info["content"][0]
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            _write_failure_log(
                "服务器 OCR 响应结构不符合预期",
                f"error={type(exc).__name__}: {exc}\n"
                + json.dumps(result, ensure_ascii=False, indent=2)[:4000],
            )
            raise
        if isinstance(content, str):
            try:
                return json.loads(content)
            except Exception as exc:  # noqa: BLE001
                _write_failure_log(
                    "服务器 OCR content 不是合法 JSON",
                    f"error={type(exc).__name__}: {exc}\n"
                    f"content_head={content[:4000]}",
                )
                raise
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


_FOCUS_CHILD_KEYS = (
    "text",
    "blocks",
    "textLines",
    "lines",
    "words",
    "items",
    "regions",
    "paragraphs",
    "results",
    "data",
)
_MATHISH_RE = re.compile(r"[=＋+\-×÷−√∫∑∏≥≤≠≈∞^_\\]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _as_size(value: Any) -> tuple[int, int] | None:
    if not value or not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        width, height = int(value[0]), int(value[1])
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _focus_canvas_size(payload: dict) -> tuple[int, int] | None:
    return _as_size((payload.get("imgWidth"), payload.get("imgHeight")))


def _looks_like_focus(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    text = payload.get("text")
    if not isinstance(text, list):
        return False
    if payload.get("imgWidth") and payload.get("imgHeight"):
        return True
    return any(isinstance(page, dict) and page.get("blocks") for page in text)


def _unwrap_server_payload(result: dict) -> dict:
    if not isinstance(result, dict):
        return {}
    if _looks_like_focus(result):
        return result
    info = result.get("result")
    if not isinstance(info, dict):
        return result
    content = info.get("content")
    if not isinstance(content, list) or not content:
        return result
    raw = content[0]
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return result
        if isinstance(parsed, dict):
            return parsed
    return result


def _iter_focus_text_lines(payload: dict):
    """只遍历 FOCUS 的 text[].blocks[].textLines[]，不把页/块拼接全文当行。"""
    for page in payload.get("text") or []:
        if not isinstance(page, dict):
            continue
        for block in page.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            orientation = block.get("orientation")
            for line in block.get("textLines") or []:
                if isinstance(line, dict):
                    yield line, orientation


def _iter_line_nodes(node: Any):
    """非 FOCUS 兜底：只收叶子行，避免把带 textLines/blocks 的父节点 value 当行。"""
    if isinstance(node, list):
        for item in node:
            yield from _iter_line_nodes(item)
        return
    if not isinstance(node, dict):
        return
    has_line_children = any(
        isinstance(node.get(key), (list, dict)) and node.get(key)
        for key in ("blocks", "textLines", "lines", "words", "items", "regions", "paragraphs")
    )
    text_value = _first_present(
        node,
        ("value", "text", "content", "words", "label", "transcription", "recognizedText"),
    )
    if (
        not has_line_children
        and (
            isinstance(text_value, (str, int, float))
            or (
                isinstance(text_value, list)
                and all(isinstance(item, (str, int, float)) for item in text_value)
            )
        )
    ):
        yield node
    for key in _FOCUS_CHILD_KEYS:
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


def _optional_conf(line: dict) -> float | None:
    """缺失或全 0 视为 unknown，不写成 conf=0。

    候选字段名按优先级（服务端实际命名以响应体为准）：
    confidence / conf / score / prob / probability / accuracy 等（含嵌套）。
    当前观测：服务端响应未带出任何置信字段 → 返回 None。
    """
    raw = _first_present(line, ("confidence", "conf", "score", "prob", "probability"))
    if raw is None:
        return None
    try:
        conf = float(raw)
    except Exception:
        return None
    if conf > 1.0:
        conf = conf / 100.0
    if conf <= 0.0:
        return None
    return conf


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


def _resolve_orientation(
    raw_orientation: Any,
    focus_size: tuple[int, int] | None,
    image_size: tuple[int, int] | None,
) -> int:
    try:
        orientation = int(raw_orientation)
    except Exception:
        orientation = 0
    if orientation not in (0, 1, 2, 3):
        orientation = 0
    if not focus_size or not image_size:
        return orientation
    focus_w, focus_h = focus_size
    image_w, image_h = image_size
    if orientation == 0 and (focus_w, focus_h) == (image_h, image_w) and (focus_w, focus_h) != (image_w, image_h):
        return 1
    return orientation


def _map_focus_point(
    x: float,
    y: float,
    *,
    orientation: int,
    focus_size: tuple[int, int],
    image_size: tuple[int, int],
) -> tuple[float, float]:
    focus_w, focus_h = focus_size
    image_w, image_h = image_size
    if orientation == 1 and (focus_w, focus_h) == (image_h, image_w):
        return y, image_h - x
    if orientation == 3 and (focus_w, focus_h) == (image_h, image_w):
        return image_w - y, x
    if orientation == 2 and (focus_w, focus_h) == (image_w, image_h):
        return image_w - x, image_h - y
    return x, y


def _map_bbox_to_image(
    bbox: list[list[float]] | None,
    *,
    orientation: int,
    focus_size: tuple[int, int] | None,
    image_size: tuple[int, int] | None,
) -> list[list[float]] | None:
    if not bbox or not focus_size or not image_size:
        return bbox
    mapped: list[list[float]] = []
    for point in bbox:
        x, y = _map_focus_point(
            float(point[0]),
            float(point[1]),
            orientation=orientation,
            focus_size=focus_size,
            image_size=image_size,
        )
        mapped.append([round(x, 2), round(y, 2)])
    return mapped


def _is_thai_empty_noise(line: dict) -> bool:
    if str(line.get("modelType") or "") != "THAI_recog":
        return False
    return not (line.get("elements") or [])


def _is_eu_margin_branding(
    text: str,
    bbox: list[list[float]] | None,
    image_size: tuple[int, int] | None,
) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 3 or len(compact) > 16:
        return False
    if _CJK_RE.search(compact) or _MATHISH_RE.search(compact):
        return False
    letters = sum(1 for char in compact if char.isalpha())
    if letters < 4 or letters / len(compact) < 0.75:
        return False
    if not bbox or not image_size:
        return False
    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    width, height = image_size
    margin_x, margin_y = width * 0.08, height * 0.08
    return (
        min(xs) <= margin_x
        or min(ys) <= margin_y
        or max(xs) >= width - margin_x
        or max(ys) >= height - margin_y
    )


def _line_item(value: str, bbox: list[list[float]] | None, conf: float | None) -> dict:
    item: dict[str, Any] = {"text": value}
    if conf is not None:
        item["conf"] = conf
    if bbox:
        item["bbox"] = bbox
    return item


def _extract_focus_lines(
    payload: dict,
    image_size: tuple[int, int] | None = None,
) -> list[dict]:
    focus_size = _focus_canvas_size(payload)
    original_size = _as_size(image_size)
    lines: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for line, block_orientation in _iter_focus_text_lines(payload):
        value = _line_text(line)
        if not value or _is_thai_empty_noise(line):
            continue
        bbox = _normalize_bbox(line.get("cornerPoints"))
        orientation = _resolve_orientation(block_orientation, focus_size, original_size)
        bbox = _map_bbox_to_image(
            bbox,
            orientation=orientation,
            focus_size=focus_size,
            image_size=original_size,
        )
        if str(line.get("modelType") or "") == "EU_recog" and _is_eu_margin_branding(
            value, bbox, original_size
        ):
            continue
        key = (value, json.dumps(bbox, ensure_ascii=False) if bbox else "")
        if key in seen:
            continue
        seen.add(key)
        lines.append(_line_item(value, bbox, _optional_conf(line)))
    return lines


def _extract_generic_lines(
    result: dict,
    image_size: tuple[int, int] | None = None,
) -> list[dict]:
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
        lines.append(_line_item(value, bbox, _optional_conf(line)))
    return lines


def extract_lines(result: dict, image_size: tuple[int, int] | None = None) -> list[dict]:
    payload = _unwrap_server_payload(result or {})
    if _looks_like_focus(payload):
        return _extract_focus_lines(payload, image_size)
    return _extract_generic_lines(payload, image_size)


def ocr_image(path: str) -> dict:
    image_base64 = _image_base64_for_request(path)
    image_size = None
    try:
        with Image.open(path) as img:
            image_size = img.size
    except Exception:
        image_size = None
    result = ServerOcrClient().get_ocr(image_base64)
    lines = extract_lines(result, image_size=image_size)
    return {"engine": "serverocr", "lines": lines}


def _image_base64_for_request(path: str) -> str:
    raw = Path(path).read_bytes()
    encoded = base64.b64encode(raw)
    if len(encoded) <= MAX_BASE64_BYTES:
        return encoded.decode("ascii")

    with Image.open(path) as img:
        img = img.convert("RGB")
        longest = int(os.getenv("SERVER_OCR_COMPRESS_LONGEST", "2200"))
        if max(img.size) > longest:
            img.thumbnail((longest, longest), Image.Resampling.LANCZOS)

        for quality in (88, 84, 80, 76, 72, 68, 64, 60, 55, 50, 45, 40):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            encoded = base64.b64encode(data)
            if len(encoded) <= MAX_BASE64_BYTES:
                return encoded.decode("ascii")

        buf = io.BytesIO()
        img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        img.save(buf, format="JPEG", quality=40, optimize=True)
        encoded = base64.b64encode(buf.getvalue())
        if len(encoded) <= MAX_BASE64_BYTES:
            return encoded.decode("ascii")

    raise ValueError(
        "图片压缩后仍超过服务器 base64 1M 限制，请裁剪图片或拆成单页后再上传。"
    )
