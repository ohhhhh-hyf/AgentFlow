"""通用 id 安全化：把任意名称变成可直接用作文件/目录段或集合名的 id。

2026-09-22 从 ``tools/memory/store.py`` 提到这里：它被 profiles / runner / outputs /
ocr / knowledge / meeting_memory 与 notes 域的 17 处引用，是**通用工具**而非某个业务域
的实现（域支撑包下沉时因此单独提出来，避免域之间互引）。

2026-09-29 清理：本文件当时连带把 store 的整块档案读写实现一并复制了过来
（``user_dir`` / ``record_path`` / ``load_record`` / ``history_path`` … 约 145 行），
但那些函数依赖的 ``json`` / ``Path`` / ``Any`` / ``datetime`` 一个都没 import，
且 ``__all__`` 只导出 ``safe_id``——是不可达的死副本（ruff F821 可直接看出）。
档案读写留在 ``tools/memory/store.py`` 这一处，本文件只保留 ``safe_id``。
"""
from __future__ import annotations


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_id(name: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (name or "").strip()
    )[:80] or "default"
    if cleaned.upper() in _WINDOWS_RESERVED:
        cleaned = f"{cleaned}_"
    return cleaned


__all__ = ["safe_id"]
