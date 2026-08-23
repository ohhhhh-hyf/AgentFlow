"""OCR recognition levels."""

from .light import LightOcrResult, run_light_ocr
from .medium import MediumOcrResult, run_medium_ocr

__all__ = ["LightOcrResult", "MediumOcrResult", "run_light_ocr", "run_medium_ocr"]
