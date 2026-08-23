"""OCR recognition levels."""

from .light import LightOcrResult, run_light_ocr
from .standard import StandardOcrResult, run_standard_ocr

__all__ = [
    "LightOcrResult",
    "StandardOcrResult",
    "run_light_ocr",
    "run_standard_ocr",
]
