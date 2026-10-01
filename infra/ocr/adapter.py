from __future__ import annotations


def _clean_ocr_text(value) -> str:
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gb18030", "latin1"):
            try:
                return value.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return value.decode("utf-8", errors="replace").strip()
    return str(value or "").strip()


def raw_text_from_lines(lines: list[dict]) -> str:
    raw_lines = [
        _clean_ocr_text(item.get("text") or item.get("formula"))
        for item in lines
        if isinstance(item, dict) and _clean_ocr_text(item.get("text") or item.get("formula"))
    ]
    return "\n".join(raw_lines).strip()


__all__ = ["raw_text_from_lines"]
