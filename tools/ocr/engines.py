"""OCR 引擎桥接：远程 OCR 主进程直调；本地引擎走子进程隔离依赖。

OCR 依赖现在统一安装在 conda 的 ``agentflow`` 环境中。
serverocr / paddleocr / rapidocr 均在主进程直调并复用实例；仅公式识别走子进程。

LLM 重构仍在主环境（client），不冲突。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_OCR_ENV_PY = Path(sys.executable)

_RUNNER = ROOT / "tools" / "ocr" / "runner_ocr.py"
_SERVER_ENGINES = {"server", "serverocr", "remote"}
_PADDLE_ENGINES = {"paddle", "paddleocr"}
_RAPID_ENGINES = {"rapid", "rapidocr"}


def _is_server_engine() -> bool:
    return os.environ.get("OCR_ENGINE", "").strip().lower() in _SERVER_ENGINES


def _is_paddle_engine() -> bool:
    return os.environ.get("OCR_ENGINE", "").strip().lower() in _PADDLE_ENGINES


def _is_rapid_engine() -> bool:
    return os.environ.get("OCR_ENGINE", "").strip().lower() in _RAPID_ENGINES


def run_ocr_subprocess(image_path: str, formula: bool = False, timeout: int = 180) -> dict:
    """识别一张图。serverocr 调 HTTP；paddleocr / rapidocr 主进程单例复用；公式识别走子进程。"""
    if not formula and _is_server_engine():
        return _run_serverocr_inprocess(image_path, timeout=timeout)
    if not formula and _is_paddle_engine():
        return _run_paddle_inprocess(image_path, timeout=timeout)
    if not formula and _is_rapid_engine():
        return _run_rapid_inprocess(image_path, timeout=timeout)
    return _spawn_ocr_runner(image_path, formula=formula, timeout=timeout)


def _empty_payload(engine: str) -> dict:
    return {"engine": engine, "lines": []}


def _run_serverocr_inprocess(image_path: str, timeout: int = 180) -> dict:
    del timeout
    from tools.ocr.server_ocr import ocr_image

    errors: list[str] = []
    for attempt in range(1, 4):
        try:
            payload = ocr_image(image_path)
            if payload.get("lines"):
                return payload
            errors.append(f"[attempt {attempt}] serverocr 返回空结果")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[attempt {attempt}] {type(exc).__name__}: {exc}")
            logger.warning("服务器 OCR 第 %s 次失败：%s", attempt, exc)
        if attempt < 3:
            time.sleep(0.6 * attempt)
    detail = "\n".join(errors)[-4000:]
    logger.warning("服务器 OCR 三次失败，返回空结果")
    return _empty_payload("serverocr")


def _run_paddle_inprocess(image_path: str, timeout: int = 180) -> dict:
    del timeout
    from tools.ocr.paddle_ocr import ocr_image

    errors: list[str] = []
    for attempt in range(1, 4):
        try:
            payload = ocr_image(image_path)
            if payload.get("lines"):
                return payload
            errors.append(f"[attempt {attempt}] paddleocr 返回空结果")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[attempt {attempt}] {type(exc).__name__}: {exc or repr(exc)}")
            logger.warning("PaddleOCR 第 %s 次失败：%s", attempt, exc)
            if isinstance(exc, TimeoutError):
                break
    detail = "\n".join(errors)[-4000:]
    logger.warning("PaddleOCR 三次失败，返回空结果")
    return _empty_payload("paddleocr")


def _run_rapid_inprocess(image_path: str, timeout: int = 180) -> dict:
    del timeout
    from tools.ocr.rapid_ocr import ocr_image

    errors: list[str] = []
    for attempt in range(1, 4):
        try:
            payload = ocr_image(image_path)
            if payload.get("lines"):
                return payload
            errors.append(f"[attempt {attempt}] rapidocr 返回空结果")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[attempt {attempt}] {type(exc).__name__}: {exc}")
            logger.warning("RapidOCR 第 %s 次失败：%s", attempt, exc)
    detail = "\n".join(errors)[-4000:]
    logger.warning("RapidOCR 三次失败，返回空结果")
    return _empty_payload("rapidocr")


def _spawn_ocr_runner(image_path: str, formula: bool = False, timeout: int = 180) -> dict:
    """子进程调用 OCR 环境识别；返回 dict（``{"lines": [...]}`` 或 ``{"formula": ...}``）。"""
    cmd = [str(_OCR_ENV_PY), str(_RUNNER), "--input", str(image_path)]
    if formula:
        cmd.append("--formula")
    attempts = 1 if formula else 3
    errors: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[attempt {attempt}] {type(exc).__name__}: {exc}")
            continue
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "")[-1200:]
            errors.append(f"[attempt {attempt}] OCR 环境识别失败：{detail}")
            continue
        for line in reversed((proc.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"[attempt {attempt}] JSON 解析失败：{exc}; line={line[-300:]}")
                    break
        else:
            errors.append(f"[attempt {attempt}] OCR 环境无 JSON 输出：{(proc.stdout or '')[-500:]}")
    detail = "\n".join(errors)[-4000:]
    if formula:
        raise RuntimeError(detail)
    engine = os.environ.get("OCR_ENGINE", "rapidocr").strip().lower() or "rapidocr"
    logger.warning("OCR 子进程三次失败，返回空结果：%s", engine)
    return _empty_payload(engine)


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

