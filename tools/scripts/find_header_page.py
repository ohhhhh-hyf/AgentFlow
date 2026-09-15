"""找出哪张图片的 OCR 里出现校名残留，并报告其页面位置。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.config import load_env  # noqa: E402

load_env()
from tools.ocr.paddle_ocr import _HEADER_RE, _HEADER_Y, _is_paddle_chrome  # noqa: E402
from tools.ocr.layout import ocr_image_lines  # noqa: E402

DOCS = ROOT / "data" / "1" / "docs"
KEYWORDS = ("科技", "UNIVERSITY", "华中", "刚德", "TECHNOLOGY", "Wuhan", "Hubei")
NAMES = [f"U202314751_{i}.jpg" for i in (15, 16, 17, 18)]


def rect(bbox):
    if not bbox:
        return None
    ys = [float(p[1]) for p in bbox]
    return min(ys), max(ys)


for name in NAMES:
    lines = ocr_image_lines(str(DOCS / name))
    rects = [rect(l.get("bbox")) for l in lines]
    tops = [r[0] for r in rects if r]
    bottoms = [r[1] for r in rects if r]
    span_top, span_bottom = (min(tops), max(bottoms)) if tops else (0, 1)
    span = max(1.0, span_bottom - span_top)
    hits = []
    for idx, (line, r) in enumerate(zip(lines, rects)):
        text = str(line.get("text") or "")
        if any(k in text for k in KEYWORDS):
            y0 = (r[0] - span_top) / span if r else -1
            compact = "".join(text.split())
            hits.append((idx, y0, text, bool(_HEADER_RE.search(compact)) if compact else False,
                         _is_paddle_chrome(text, line.get("bbox"), None)))
    print(f"\n### {name}（{len(lines)} 行）")
    if not hits:
        print("   （无校名残留关键词）")
    for idx, y0, text, hit, chrome in hits:
        print(f"   [{idx:2d}] y={y0:5.2f} 正则命中={hit}  {text[:52]!r}")
print(f"\n（引擎判据：位置带 y0 <= {_HEADER_Y} 且命中机构/联系式正则 → 丢弃）")
