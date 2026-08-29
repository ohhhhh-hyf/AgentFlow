"""OCR 引擎分派：按 ``OCR_ENGINE`` 选择引擎，主进程直调，统一重试与失败落盘。

三种引擎各自成文件（``tools/ocr/{server_ocr,paddle_ocr,rapid_ocr}.py``），
本模块只做分派，不含任何引擎实现：

- ``serverocr``（别名 server / remote）：远程 OCR 服务 HTTP 直调
- ``paddleocr``（别名 paddle）：PaddleOCR 3.x / PP-OCRv5，模型懒加载
- ``rapidocr``（别名 rapid）：RapidOCR（CPU 本地，onnxruntime）

三种引擎互不兜底；引擎不可用或三次失败 → 失败样本落盘 ``log/ocr_failed/``
并返回空结果，不阻断主流程。
"""
from __future__ import annotations

import importlib
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_OCR_FAILURE_DIR = ROOT / "log" / "ocr_failed"

# OCR_ENGINE 取值别名 → 引擎模块名（tools/ocr/{module}.py）
_ENGINE_ALIASES: dict[str, str] = {
    "server": "server_ocr",
    "serverocr": "server_ocr",
    "remote": "server_ocr",
    "paddle": "paddle_ocr",
    "paddleocr": "paddle_ocr",
    "rapid": "rapid_ocr",
    "rapidocr": "rapid_ocr",
}


def _log_ocr_failure(image_path: str, detail: str) -> None:
    try:
        src = Path(image_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        folder = _OCR_FAILURE_DIR / stamp
        folder.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(src, folder / src.name)
        (folder / "error.txt").write_text(detail, encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.warning("记录 OCR 失败样本失败：%s", exc)


def run_ocr_subprocess(image_path: str, timeout: int = 180) -> dict:
    """识别一张图：按 ``OCR_ENGINE`` 分派到对应引擎模块，统一 3 次重试。

    返回 ``{"engine": 展示名, "lines": [...]}``；三次失败 / 引擎名未知 →
    失败样本落盘并返回空 lines，不抛异常（超时除外，见下）。
    """
    del timeout  # 超时由各引擎自身的环境变量配置（SERVER_OCR_TIMEOUT / PADDLE_OCR_*）
    alias = os.environ.get("OCR_ENGINE", "").strip().lower()
    module_name = _ENGINE_ALIASES.get(alias)
    if module_name is None:
        detail = f"未知 OCR_ENGINE={alias!r}（可选：serverocr / paddleocr / rapidocr）"
        logger.warning(detail)
        _log_ocr_failure(image_path, detail)
        return {"engine": alias or "unknown", "lines": []}

    engine = module_name.replace("_", "")  # 展示名：serverocr / paddleocr / rapidocr
    module = importlib.import_module(f"tools.ocr.{module_name}")
    errors: list[str] = []
    for attempt in range(1, 4):
        try:
            payload = module.ocr_image(image_path)
            if payload.get("lines"):
                return payload
            errors.append(f"[attempt {attempt}] {engine} 返回空结果")
            logger.warning("%s 第 %s 次返回空结果", engine, attempt)
        except TimeoutError:
            errors.append(f"[attempt {attempt}] 超时，不再重试")
            break
        except Exception as exc:  # noqa: BLE001 - 引擎异常降级为重试
            errors.append(f"[attempt {attempt}] {type(exc).__name__}: {exc}")
            logger.warning("%s 第 %s 次失败：%s", engine, attempt, exc)
        if attempt < 3:
            time.sleep(0.6 * attempt)
    detail = "\n".join(errors)[-4000:]
    _log_ocr_failure(image_path, detail)
    logger.warning("%s 三次失败，返回空结果", engine)
    return {"engine": engine, "lines": []}


def get_llm_client():
    """项目现有 LLM 客户端（DeepSeek）——重构用。失败返回 None。"""
    try:
        from client import LLMClient
        from client.config import load_env

        load_env(ROOT / ".env")
        return LLMClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 客户端不可用（%s），OCR 将只输出原始文本", exc)
        return None


__all__ = ["get_llm_client", "run_ocr_subprocess"]
