"""Visual Minutes (图文智能纪要) 核心包。"""
from .agent import VisualMinutesAgent
from .models.ir import VisualDocumentIR
from .parsing.parser import ParsedMinutes, parse_minutes
from .rendering.compositor import DocumentCompositor
from .pipeline import (
    VisualMinutesResult,
    agenerate_visual_minutes,
    build_visual_ir,
    generate_visual_minutes,
)

__all__ = [
    "DocumentCompositor",
    "ParsedMinutes",
    "VisualDocumentIR",
    "VisualMinutesAgent",
    "VisualMinutesResult",
    "agenerate_visual_minutes",
    "build_visual_ir",
    "generate_visual_minutes",
    "parse_minutes",
]
