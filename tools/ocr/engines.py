"""OCR 引擎桥接：子进程调用当前 Python 环境执行 OCR。

OCR 依赖现在统一安装在 conda 的 ``agentflow`` 环境中。启动 Gradio/CLI 时只要
使用 ``agentflow``，OCR 子进程也会沿用同一个 Python。

LLM 重构仍在主环境（client），不冲突。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
_OCR_ENV_PY = Path(sys.executable)

_RUNNER = ROOT / "tools" / "ocr" / "runner_ocr.py"
_OCR_FAILURE_DIR = ROOT / "log" / "ocr_failed"


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


def run_ocr_subprocess(image_path: str, formula: bool = False, timeout: int = 180) -> dict:
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
    if not formula:
        _log_ocr_failure(image_path, detail)
    raise RuntimeError(detail)


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

