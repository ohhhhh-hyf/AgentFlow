"""OCR recognition levels."""

from .heavy import HeavyOcrResult, run_heavy_ocr
from .light import LightOcrResult, run_light_ocr
from .medium import MediumOcrResult, run_medium_ocr

__all__ = [
    "HeavyOcrResult",
    "LightOcrResult",
    "MediumOcrResult",
    "run_heavy_ocr",
    "run_light_ocr",
    "run_medium_ocr",
]
