"""OCR 引擎桥接：子进程调用独立 OCR 环境（.ocrvenv），避免与主环境 C 扩展冲突。

主环境（agentflow）带 torch/paddle/chromadb 等，与 OCR 推理库（onnxruntime/
opencv/LaTeX-OCR）存在 OpenMP/DLL 冲突，推理会挂起。因此 OCR 识别在
``.ocrvenv``（独立 venv，只装 OCR 依赖）中执行，本模块以 subprocess 桥接。

LLM 重构仍在主环境（llm_client），不冲突。
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
# 独立 OCR 环境（Windows venv）；不存在则回退系统 PATH 的 python
_OCR_ENV_PY = ROOT / ".ocrvenv" / "Scripts" / "python.exe"
if not _OCR_ENV_PY.is_file():
    _OCR_ENV_PY = ROOT / ".ocrvenv" / "bin" / "python"
    if not _OCR_ENV_PY.is_file():
        _OCR_ENV_PY = Path("python")

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
        from llm_client import LLMClient
        from llm_client.config import load_env

        load_env(ROOT / ".env")
        return LLMClient()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 客户端不可用（%s），OCR 将只输出原始文本", exc)
        return None


__all__ = ["get_llm_client", "run_ocr_subprocess"]
