"""OCR 引擎桥接：子进程调用独立 OCR 环境（.ocrvenv），避免与主环境 C 扩展冲突。

主环境（agentflow）带 torch/paddle/chromadb 等，与 OCR 推理库（onnxruntime/
opencv/LaTeX-OCR）存在 OpenMP/DLL 冲突，推理会挂起。因此 OCR 识别在
``.ocrvenv``（独立 venv，只装 OCR 依赖）中执行，本模块以 subprocess 桥接。

LLM 重构仍在主环境（llm_client），不冲突。
"""
from __future__ import annotations

import json
import logging
import subprocess
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


def run_ocr_subprocess(image_path: str, formula: bool = False, timeout: int = 180) -> dict:
    """子进程调用 OCR 环境识别；返回 dict（``{"lines": [...]}`` 或 ``{"formula": ...}``）。"""
    cmd = [str(_OCR_ENV_PY), str(_RUNNER), "--input", str(image_path)]
    if formula:
        cmd.append("--formula")
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[-800:]
        raise RuntimeError(f"OCR 环境识别失败：{detail}")
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"OCR 环境无 JSON 输出：{proc.stdout[-300:]}")


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
